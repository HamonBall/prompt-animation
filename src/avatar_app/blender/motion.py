"""Stage composition, contact solving, candidate review and transactional commit."""
from dataclasses import dataclass, asdict
import math
import bpy
from mathutils import Matrix, Quaternion, Vector
from ..models import PlanError
from ..motion import ActionPlan, validate_action, sample_controls, schedule
from ..pose import PosePlan
from .pose import target_pose, axes, position_hand, ground_pose, frame_transition, rotate_bone, contacts
from .animation import solve_leg


PART_BONES = {'left_foot': 'LeftFoot', 'right_foot': 'RightFoot',
              'left_hand': 'LeftHand', 'right_hand': 'RightHand',
              'pelvis': 'Hips', 'back': 'Spine'}


@dataclass(frozen=True)
class MotionIssue:
    kind: str
    frame: int
    body_part: str
    measured: float
    limit: float
    stage: str = ''


@dataclass
class MotionReview:
    issues: list
    metrics: dict

    @property
    def passed(self):
        return not self.issues

    def to_dict(self):
        return {'passed': self.passed, 'metrics': self.metrics,
                'issues': [asdict(issue) for issue in self.issues]}


def mesh_floor(handle):
    graph = bpy.context.evaluated_depsgraph_get()
    return min((obj.matrix_world @ Vector(corner)).z for obj in handle.objects
               if obj.type == 'MESH' for corner in obj.evaluated_get(graph).bound_box)


def review_samples(samples, height=1.8, fps=30):
    """Deterministic whole-timeline checks; report worst sample per kind/body/stage."""
    worst = {}
    metrics = {'floor_penetration_m': 0.0, 'contact_error_m': 0.0,
               'joint_speed_deg_s': 0.0, 'root_step_m': 0.0, 'frames': len(samples)}
    previous = None
    def issue(kind, frame, part, measured, limit, stage):
        if measured > limit:
            key = kind, part, stage
            item = MotionIssue(kind, frame, part, measured, limit, stage)
            if key not in worst or measured > worst[key].measured:
                worst[key] = item
    for sample in samples:
        frame, stage = sample['frame'], sample.get('stage', '')
        penetration = max(0.0, -sample['floor'])
        metrics['floor_penetration_m'] = max(metrics['floor_penetration_m'], penetration)
        issue('floor_penetration', frame, 'mesh', penetration, .003, stage)
        for part, error in sample.get('contacts', {}).items():
            metrics['contact_error_m'] = max(metrics['contact_error_m'], error)
            issue('contact_drift', frame, part, error, .025, stage)
        if previous:
            step = (sample['root'] - previous['root']).length
            metrics['root_step_m'] = max(metrics['root_step_m'], step)
            issue('root_discontinuity', frame, 'pelvis', step, height * .08, stage)
            for part, q in sample['rotations'].items():
                speed = math.degrees(q.rotation_difference(previous['rotations'][part]).angle)
                speed = min(speed, 360 - speed) * fps
                metrics['joint_speed_deg_s'] = max(metrics['joint_speed_deg_s'], speed)
                issue('abrupt_joint_change', frame, part, speed, 900, stage)
        previous = sample
    return MotionReview(list(worst.values()), metrics)


def capture_sample(handle, frame, stage='', errors=None):
    rig = handle.rig
    for bone in rig.pose.bones:
        if not all(math.isfinite(v) for row in bone.matrix_basis for v in row):
            raise PlanError('The candidate has invalid joint transforms.')
    return {'frame': frame, 'stage': stage, 'floor': mesh_floor(handle),
            'root': rig.matrix_world @ handle.bones['Hips'].head,
            'rotations': {k: b.matrix.to_quaternion() for k, b in handle.bones.items()},
            'contacts': errors or {}}


def review_existing(handle):
    old_frame = handle.scene.frame_current
    try:
        samples = []
        for frame in range(handle.scene.frame_start, handle.scene.frame_end + 1):
            handle.scene.frame_set(frame)
            samples.append(capture_sample(handle, frame))
        return review_samples(samples, fps=handle.scene.render.fps)
    finally:
        handle.scene.frame_set(old_frame)


def check_completion(plan, samples, report):
    completed = []
    for stage, start, end in schedule(plan):
        sample = samples[min(len(samples) - 1, math.ceil(end * plan.fps))]
        if 'targets' in stage.completion:
            for key, target in stage.targets:
                if target is None:
                    continue
                error = abs(sample['controls'].get(key, 0) - target)
                tolerance = .01 if key.startswith('pelvis_') or '_target_' in key else 2
                if error > tolerance:
                    report.issues.append(MotionIssue('incomplete_target', sample['frame'], key,
                                                     error, tolerance, stage.id))
        if 'contacts' in stage.completion:
            for c in stage.contacts:
                begin, finish = start + c.start * stage.duration, start + c.end * stage.duration
                reached = any(c.part in s['contacts'] and s['contacts'][c.part] <= .025
                              for s in samples if begin <= (s['frame'] - 1) / plan.fps <= finish)
                if not reached:
                    report.issues.append(MotionIssue('incomplete_contact', sample['frame'], c.part,
                                                     1, 0, stage.id))
        completed.append({'id': stage.id, 'end_frame': sample['frame'], 'conditions': stage.completion})
    report.metrics['completion'] = completed
    return report


def active_contacts(plan, time):
    result = []
    for stage, start, _ in schedule(plan):
        for index, c in enumerate(stage.contacts):
            begin, end = start + c.start * stage.duration, start + c.end * stage.duration
            if begin - 1e-8 <= time <= end + 1e-8:
                result.append(((stage.id, index), c, begin, end))
    # Adjacent attachment intervals share their boundary; use the later stage.
    unique = {c.part: (key, c, begin, end) for key, c, begin, end in result}
    return list(unique.values())


def set_contact(handle, constraint, target, foot_orientation, strength=1):
    bone = handle.bones[PART_BONES[constraint.part]]
    if constraint.part.endswith('_foot'):
        side = constraint.part.split('_')[0].title()
        solve_leg(handle, side, target)
        bone.matrix = Matrix.Translation(bone.head) @ foot_orientation.to_matrix().to_4x4()
        bpy.context.view_layer.update()
    elif constraint.part.endswith('_hand'):
        position_hand(handle, constraint.part.split('_')[0].title(), target, axes(handle))
        # Wrist support also orients the fingers along the surface, avoiding
        # a vertical hand driving the mesh below the floor.
        delta = (bone.tail - bone.head).normalized().rotation_difference(handle.forward.normalized())
        rotate_bone(bone, Quaternion().slerp(delta, strength))
    else:
        hips = handle.bones['Hips']
        matrix = hips.matrix.copy()
        matrix.translation += target - bone.head
        hips.matrix = matrix
        bpy.context.view_layer.update()


def linear_keys(action):
    for slot in action.slots:
        for layer in action.layers:
            for strip in layer.strips:
                bag = strip.channelbag(slot)
                if bag:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points:
                            key.interpolation = 'LINEAR'


def measured_controls(handle, values, origin):
    """Capture the solved ending state, including legs changed by contact IK."""
    from .pose import rotation
    result = dict(values)
    frame_axes = axes(handle, rotation(PosePlan(tuple(values.items())), 'root', axes(handle)))
    right, forward, up = frame_axes
    for side, sign in (('Left', -1), ('Right', 1)):
        for part, bone_name in (('arm', 'Arm'), ('forearm', 'ForeArm'), ('thigh', 'UpLeg'), ('shin', 'Leg')):
            bone = handle.bones[side + bone_name]
            vector = (bone.tail - bone.head).normalized()
            result[side.lower() + '_' + part + '_elevation'] = math.degrees(math.acos(max(-1, min(1, -vector.dot(up)))))
            result[side.lower() + '_' + part + '_azimuth'] = math.degrees(math.atan2(vector.dot(forward), sign * vector.dot(right)))
    delta = handle.bones['Hips'].head - origin
    right, forward, up = axes(handle)
    result.update(pelvis_side=delta.dot(right) / handle.height,
                  pelvis_forward=delta.dot(forward) / handle.height,
                  pelvis_drop=-delta.dot(up) / handle.height)
    return result


def compose_frame(plan, time, starting, baselines, measured):
    """Start each newly activated movement from the actual preceding solved state."""
    from ..motion import control_default
    values = dict(starting)
    for stage, start, end in sorted(schedule(plan), key=lambda row: row[1]):
        if time < start - 1e-8:
            continue
        if stage.id not in baselines:
            baselines[stage.id] = dict(measured)
        source = baselines[stage.id]
        weight = min(1.0, max(0.0, (time - start) / stage.duration))
        weight = weight * weight * (3 - 2 * weight)
        for key, target in stage.targets:
            before = source.get(key, control_default(source, key))
            if target is None:
                if '_hand_target_' in key or time >= end:
                    values.pop(key, None)
            elif key == 'grounding':
                values[key] = 0 if target == 0 else (target if time >= end else before)
            else:
                values[key] = before + (target - before) * weight
    # IK may have changed an unowned leg or pelvis. Carry that ending state
    # when the next movement does not own it, rather than resetting to rest.
    owned = {k for s, start, end in schedule(plan) if start <= time <= end for k, _ in s.targets}
    for key in measured:
        if key not in owned and (key.startswith('pelvis_') or '_thigh_' in key or '_shin_' in key):
            values[key] = measured[key]
    return values


def bake_candidate(handle, plan, repair_floor, progress):
    rig, scene = handle.rig, handle.scene
    action = bpy.data.actions.new(f'Avatar motion r{plan.revision}')
    rig.animation_data.action = action
    try:
        target_pose(handle, PosePlan())
        neutral_feet = {side: handle.bones[side + 'Foot'].head.copy() for side in ('Left', 'Right')}
        neutral_rotation = {side: handle.bones[side + 'Foot'].matrix.to_quaternion() for side in neutral_feet}
        control_origin = handle.bones['Hips'].head.copy()
        target_pose(handle, plan.initial)
        initial_support = contacts(plan.initial)
        for side in initial_support:
            solve_leg(handle, side, neutral_feet[side])
            foot = handle.bones[side + 'Foot']
            foot.matrix = Matrix.Translation(foot.head) @ neutral_rotation[side].to_matrix().to_4x4()
            bpy.context.view_layer.update()
        if not initial_support:
            ground_pose(handle, settle=bool(plan.initial.get('grounding', 1)))
        origin = handle.bones['Hips'].head.copy()
        world_height = (rig.matrix_world.to_3x3() @ (handle.up * handle.height)).length
        floor = {s.name: s.height for s in plan.surfaces}
        right, forward, up = axes(handle)
        rest_feet = {side: handle.bones[side.title() + 'Foot'].matrix.to_quaternion()
                     for side in ('left', 'right')}
        from ..motion import ContactConstraint
        cached = {}
        foot_padding = {}
        last_anchor = {side.lower() + '_foot': (0.0, ContactConstraint(side.lower() + '_foot'),
                                               neutral_feet[side], neutral_rotation[side])
                       for side in initial_support}
        samples = []
        # Existing wrist position is the start of a new wrist movement, not zero.
        initial = dict(plan.initial.values)
        from dataclasses import replace
        for side in ('left', 'right'):
            names = [side + '_hand_target_' + axis for axis in ('side', 'forward', 'height')]
            if any(k in dict(s.targets) for s in plan.stages for k in names) and not any(k in initial for k in names):
                delta = handle.bones[side.title() + 'Hand'].head - origin
                initial.update(zip(names, [delta.dot(v) / handle.height for v in (right, forward, up)]))
        sampling_plan = replace(plan, initial=PosePlan(tuple(sorted(initial.items())), 'none'))
        baselines = {}
        measured = measured_controls(handle, initial, control_origin)
        count = math.ceil(plan.duration * plan.fps)
        for i in range(count + 1):
            frame = i + 1
            scene.frame_set(frame)
            time = min(plan.duration, i / plan.fps)
            values = compose_frame(sampling_plan, time, initial, baselines, measured)
            # At the first frame wrist chains may be exactly straight; use the rest pose.
            if not i:
                values = dict(measured)
                for key in list(values):
                    if '_hand_target_' in key and key not in dict(plan.initial.values):
                        values.pop(key)
            target_pose(handle, PosePlan(tuple(sorted(values.items())), 'none'))
            active = active_contacts(plan, time)
            for key, c, begin, end in active:
                if key not in cached:
                    bone = handle.bones[PART_BONES[c.part]]
                    target = bone.head.copy()
                    old = last_anchor.get(c.part)
                    if old and abs(old[0] - begin) < 1e-6 and old[1].surface == c.surface and old[1].position == c.position:
                        target = old[2].copy()
                    elif c.position is not None:
                        target = origin + handle.height * (right * c.position[0] + forward * c.position[1])
                    world = rig.matrix_world @ target
                    if c.part.endswith('_foot') and c.position is None and c.surface == 'floor':
                        # Foot bone origin is above the sole; retain measured rest clearance.
                        if old is None:
                            rest = handle.bones[c.part.split('_')[0].title() + 'Foot'].bone.head_local
                            world.z = (rig.matrix_world @ rest).z
                    else:
                        world.z = floor[c.surface] + c.clearance * world_height
                    target = rig.matrix_world.inverted() @ world
                    orientation = rest_feet[c.part.split('_')[0]] if c.part.endswith('_foot') else bone.matrix.to_quaternion()
                    cached[key] = target, orientation
                target, orientation = cached[key]
                last_anchor[c.part] = end, c, target, orientation
            # Resolve torso supports before extremities so limb IK uses corrected hips.
            active.sort(key=lambda item: 0 if item[1].part in ('pelvis', 'back') else 1)
            strengths = {}
            for key, c, begin, end in active:
                target, orientation = cached[key]
                strength = 1.0
                if c.part.endswith('_foot'):
                    target = target + rig.matrix_world.inverted().to_3x3() @ Vector(
                        (0, 0, foot_padding.get(c.part, 0)))
                if not c.part.endswith('_foot'):
                    ramp = min(.2, (end - begin) / 3)
                    strength = min(1.0, max(0.0, (time - begin) / ramp))
                    if c.part.endswith('_hand'):
                        strength = min(strength, max(0.0, (end - time) / ramp))
                    strength = strength * strength * (3 - 2 * strength)
                    target = handle.bones[PART_BONES[c.part]].head.lerp(target, strength)
                strengths[key] = strength
                if strength > 1e-6:
                    set_contact(handle, c, target, orientation, strength)
            active_parts = {c.part for _, c, _, _ in active}
            for part, (end, _, _, held_rotation) in last_anchor.items():
                if part.endswith('_foot') and part not in active_parts and 0 <= time - end < .25:
                    foot = handle.bones[PART_BONES[part]]
                    weight = (time - end) / .25
                    weight = weight * weight * (3 - 2 * weight)
                    orientation = held_rotation.slerp(foot.matrix.to_quaternion(), weight)
                    foot.matrix = Matrix.Translation(foot.head) @ orientation.to_matrix().to_4x4()
                    bpy.context.view_layer.update()
            if not active:
                ground_pose(handle, settle=bool(values.get('grounding', 1)))
            elif repair_floor and mesh_floor(handle) < -.003:
                penetration = -mesh_floor(handle)
                ground_pose(handle, settle=False)
                for key, c, _, _ in active:
                    if c.part.endswith(('_foot', '_hand')):
                        target, orientation = cached[key]
                        if c.part.endswith('_foot'):
                            foot_padding[c.part] = min(.02, foot_padding.get(c.part, 0) + penetration)
                            lift = rig.matrix_world.inverted().to_3x3() @ Vector((0, 0, foot_padding[c.part]))
                            target = target + lift
                        if strengths[key] < .999:
                            target = handle.bones[PART_BONES[c.part]].head.lerp(target, strengths[key])
                        if strengths[key] > 1e-6:
                            set_contact(handle, c, target, orientation, strengths[key])
            errors = {}
            for key, c, _, _ in active:
                if strengths[key] < .999:
                    continue
                delta = rig.matrix_world.to_3x3() @ (handle.bones[PART_BONES[c.part]].head - cached[key][0])
                # Pelvis/back bone clearance is a lower bound on the floor:
                # mesh thickness may require a higher bone anchor after repair.
                if c.part in ('pelvis', 'back') and c.surface == 'floor':
                    delta.z = min(0.0, delta.z)
                errors[c.part] = delta.length
            stage_id = next((s.id for s, start, end in reversed(schedule(plan))
                             if start <= time <= end), '')
            samples.append(capture_sample(handle, frame, stage_id, errors))
            samples[-1]['controls'] = dict(values)
            measured = measured_controls(handle, values, control_origin)
            for bone in rig.pose.bones:
                bone.keyframe_insert('location', frame=frame, group=bone.name)
                bone.keyframe_insert('rotation_quaternion', frame=frame, group=bone.name)
                bone.keyframe_insert('scale', frame=frame, group=bone.name)
            progress((i + 1) / (count + 1))
        linear_keys(action)
        report = review_samples(samples, height=world_height, fps=plan.fps)
        return action, samples, check_completion(plan, samples, report)
    except Exception:
        rig.animation_data.action = None
        bpy.data.actions.remove(action)
        raise


def build_action(handle, plan, progress=lambda fraction: None):
    """Commit only reviewed motion. One measured repair attempt; restore everything on failure."""
    validate_action(plan)
    rig, scene = handle.rig, handle.scene
    rig.animation_data_create()
    old_action = rig.animation_data.action
    basis = {b.name: b.matrix_basis.copy() for b in rig.pose.bones}
    modes = {b.name: b.rotation_mode for b in rig.pose.bones}
    timeline = scene.frame_start, scene.frame_end, scene.frame_current, scene.render.fps
    camera = (scene.camera.matrix_world.copy() if scene.camera else None)
    action = None
    try:
        action, samples, report = bake_candidate(handle, plan, False, lambda f: progress(f * .5))
        before = report.to_dict()
        repaired = False
        if not report.passed and all(i.kind == 'floor_penetration' for i in report.issues):
            rig.animation_data.action = None
            bpy.data.actions.remove(action)
            action = None
            action, samples, report = bake_candidate(handle, plan, True, lambda f: progress(.5 + f * .5))
            repaired = report.metrics['floor_penetration_m'] < before['metrics']['floor_penetration_m']
        if not report.passed:
            issue = report.issues[0]
            error = PlanError(f'Motion review failed at frame {issue.frame}: {issue.kind.replace("_", " ")} '
                              f'({issue.body_part}). Previous animation kept.')
            error.review = report.to_dict()
            raise error
        scene.render.fps = plan.fps
        scene.frame_start, scene.frame_end = 1, len(samples)
        camera_frames = sorted({1, len(samples)} | {min(len(samples), round(t * plan.fps) + 1)
                               for _, start, end in schedule(plan) for t in (start, (start + end) / 2, end)})
        frame_transition(handle, plan.final_pose, camera_frames)
        scene.frame_set(1)
        if old_action and old_action.users == 0:
            bpy.data.actions.remove(old_action)
        progress(1)
        return {'frames': len(samples), 'action': action.name, 'review': report.to_dict(),
                'before_repair': before, 'repaired': repaired, 'stages': len(plan.stages)}
    except Exception:
        rig.animation_data.action = old_action
        if action and action.name in bpy.data.actions:
            bpy.data.actions.remove(action)
        scene.frame_start, scene.frame_end, frame, scene.render.fps = timeline
        if camera is not None:
            scene.camera.matrix_world = camera
        scene.frame_set(frame)
        for bone in rig.pose.bones:
            bone.rotation_mode = modes[bone.name]
            bone.matrix_basis = basis[bone.name]
        bpy.context.view_layer.update()
        raise
