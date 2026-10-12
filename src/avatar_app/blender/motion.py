"""Stage composition, contact solving, candidate review and transactional commit."""
from dataclasses import dataclass, asdict
import math
import bpy
from mathutils import Matrix, Quaternion, Vector
from ..models import PlanError
from ..motion import ActionPlan, validate_action, sample_controls, schedule, blend_control
from ..pose import LIMITS, PosePlan, validate_pose, serialize_pose
from .pose import target_pose, axes, position_hand, ground_pose, frame_transition, rotate_bone, contacts
from .animation import solve_leg
from .geometry import skin_bounds, seat_penetration, support_floor, support_skin_height


PART_BONES = {'left_foot': 'LeftFoot', 'right_foot': 'RightFoot',
              'left_hand': 'LeftHand', 'right_hand': 'RightHand',
              'pelvis': 'Hips', 'back': 'Spine'}


def contact_ease(t):
    t = min(1.0, max(0.0, t))
    return 35*t**4 - 84*t**5 + 70*t**6 - 20*t**7


def palm_frame(handle, side):
    hand = handle.bones[side+'Hand']
    def finger(suffix):
        return next((b.bone.head_local for b in handle.rig.pose.bones if b.name.endswith(side+'Hand'+suffix)), None)
    index, pinky, middle = finger('Index1'), finger('Pinky1'), finger('Middle1')
    right, forward, up = axes(handle)
    if index is None or pinky is None or middle is None:
        return Matrix((right, forward, up)).transposed().to_quaternion()
    rest = hand.bone.matrix_local.to_3x3().inverted()
    width = (rest @ (index-pinky)).normalized()
    length = rest @ (middle-hand.bone.head_local)
    length = (length-width*length.dot(width)).normalized()
    local = Matrix((width, length, width.cross(length))).transposed()
    target_width = right * (1 if side == 'Left' else -1)
    target = Matrix((target_width, forward, target_width.cross(forward))).transposed()
    return (target @ local.transposed()).to_quaternion()


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
    return skin_bounds(handle)[0].z


def review_samples(samples, height=1.8, fps=30):
    """Deterministic whole-timeline checks; report worst sample per kind/body/stage."""
    worst = {}
    metrics = {'floor_penetration_m': 0.0, 'surface_penetration_m': 0.0, 'contact_error_m': 0.0,
               'joint_speed_deg_s': 0.0, 'joint_acceleration_deg_s2': 0.0,
               'root_step_m': 0.0, 'frames': len(samples)}
    previous = None
    last_velocities = {}
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
        for surface, penetration in sample.get('surfaces', {}).items():
            metrics['surface_penetration_m'] = max(metrics['surface_penetration_m'], penetration)
            issue('surface_penetration', frame, surface, penetration, .003, stage)
        for part, error in sample.get('contacts', {}).items():
            metrics['contact_error_m'] = max(metrics['contact_error_m'], error)
            issue('contact_drift', frame, part, error, .025, stage)
        if previous:
            step = (sample['root'] - previous['root']).length
            metrics['root_step_m'] = max(metrics['root_step_m'], step)
            issue('root_discontinuity', frame, 'pelvis', step, height * .08, stage)
            for part, q in sample['rotations'].items():
                delta = q @ previous['rotations'][part].conjugated()
                if delta.w < 0:
                    delta.negate()
                velocity = delta.axis * delta.angle * fps
                speed = math.degrees(velocity.length)
                metrics['joint_speed_deg_s'] = max(metrics['joint_speed_deg_s'], speed)
                issue('abrupt_joint_change', frame, part, speed, 360, stage)
                if part in last_velocities:
                    acceleration = math.degrees((velocity-last_velocities[part]).length) * fps
                    metrics['joint_acceleration_deg_s2'] = max(metrics['joint_acceleration_deg_s2'], acceleration)
                    issue('joint_acceleration', frame, part, acceleration, 3000, stage)
                last_velocities[part] = velocity
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
            checked_parts = set()
            for key, target in stage.targets:
                if target is None or key == 'grounding':
                    continue
                prefix = next((part for part in ('root', 'torso', 'head', 'left_hand', 'right_hand',
                                                 'left_foot', 'right_foot') if key.startswith(part+'_')
                               and '_target_' not in key), None)
                if prefix:
                    if prefix in checked_parts:
                        continue
                    checked_parts.add(prefix)
                    expected = sample['desired_rotations'][prefix]
                    actual = sample['actual_rotations'][prefix]
                    error = math.degrees(actual.rotation_difference(expected).angle)
                    error = min(error, 360-error)
                    tolerance = 6
                else:
                    actual = sample['controls'].get(key)
                    error = abs(actual-target) if actual is not None else float('inf')
                    tolerance = .03 if key.startswith('pelvis_') else .015 if '_target_' in key else 6
                    if key.endswith('_azimuth'):
                        elevation_key = key.replace('_azimuth', '_elevation')
                        elevation = dict(stage.targets).get(elevation_key, sample['controls'].get(elevation_key, 0))
                        if elevation < 3 or elevation > 177:
                            continue
                        error = abs((actual-target+180) % 360 - 180)
                if error > tolerance:
                    report.issues.append(MotionIssue('incomplete_target', sample['frame'], key,
                                                     error, tolerance, stage.id))
        if stage.contacts:
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


def keep_hand_above_floor(handle, side, pole=None):
    bone = handle.bones[side+'Hand']
    q = bone.matrix.to_quaternion()
    for _ in range(2):
        skin = support_skin_height(handle, side.lower()+'_hand')
        if skin >= -.0001 or not math.isfinite(skin):
            break
        lifted = bone.head + handle.rig.matrix_world.inverted().to_3x3() @ Vector((0, 0, -skin))
        position_hand(handle, side, lifted, axes(handle), pole=pole)
        bone.matrix = Matrix.Translation(bone.head) @ q.to_matrix().to_4x4()
        bpy.context.view_layer.update()


def set_contact(handle, constraint, target, foot_orientation, strength=1, elbow=None):
    bone = handle.bones[PART_BONES[constraint.part]]
    if constraint.part.endswith('_foot'):
        side = constraint.part.split('_')[0].title()
        solve_leg(handle, side, target)
        bone.matrix = Matrix.Translation(bone.head) @ foot_orientation.to_matrix().to_4x4()
        bpy.context.view_layer.update()
    elif constraint.part.endswith('_hand'):
        if elbow is not None and constraint.surface == 'floor':
            world = handle.rig.matrix_world @ elbow
            height = (handle.rig.matrix_world.to_3x3() @ (handle.up * handle.height)).length
            safe_height = (constraint.clearance + .09) * height
            world.z += max(0, safe_height-world.z) * strength
            elbow = handle.rig.matrix_world.inverted() @ world
        position_hand(handle, constraint.part.split('_')[0].title(), target, axes(handle), pole=elbow)
        # Wrist support also orients the fingers along the surface, avoiding
        # a vertical hand driving the mesh below the floor.
        desired = handle._palm_frames[constraint.part.split('_')[0].title()]
        q = bone.matrix.to_quaternion().slerp(desired, strength)
        bone.matrix = Matrix.Translation(bone.head) @ q.to_matrix().to_4x4()
        bpy.context.view_layer.update()
        if constraint.surface == 'floor':
            # During release the wrist rises while the palm turns. Keep the
            # rotating fingers clear rather than lifting the entire torso.
            keep_hand_above_floor(handle, constraint.part.split('_')[0].title(), elbow)
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
    def delta(name):
        bone = handle.bones[name]
        return bone.matrix.to_quaternion() @ bone.bone.matrix_local.to_quaternion().conjugated()
    root_q = delta('Hips')
    spine = next(name for name in ('Spine2', 'Spine1', 'Spine') if name in handle.bones)
    torso_absolute = delta(spine)
    torso_q = torso_absolute @ root_q.conjugated()
    head_q = delta('Head') @ torso_absolute.conjugated()
    bases = [axes(handle), axes(handle, root_q), tuple(torso_q @ v for v in axes(handle, root_q))]
    for prefix, q, frame_axes in zip(('root', 'torso', 'head'), (root_q, torso_q, head_q), bases):
        basis = Matrix(frame_axes).transposed().to_quaternion()
        e = (basis.conjugated() @ q @ basis).to_euler('XYZ')
        result.update({prefix+'_pitch': -math.degrees(e.x), prefix+'_roll': math.degrees(e.y),
                       prefix+'_yaw': math.degrees(e.z)})
    frame_axes = axes(handle, root_q)
    right, forward, up = frame_axes
    for side, sign in (('Left', -1), ('Right', 1)):
        for part, bone_name in (('arm', 'Arm'), ('forearm', 'ForeArm'), ('thigh', 'UpLeg'), ('shin', 'Leg')):
            bone = handle.bones[side + bone_name]
            vector = (bone.tail - bone.head).normalized()
            result[side.lower() + '_' + part + '_elevation'] = math.degrees(math.acos(max(-1, min(1, -vector.dot(up)))))
            result[side.lower() + '_' + part + '_azimuth'] = math.degrees(math.atan2(vector.dot(forward), sign * vector.dot(right)))
        wrist = handle.bones[side+'Hand'].head - handle.bones['Hips'].head
        for axis, vector in zip(('side', 'forward', 'height'), frame_axes):
            result[side.lower()+'_hand_target_'+axis] = wrist.dot(vector) / handle.height
    delta = handle.bones['Hips'].head - origin
    right, forward, up = axes(handle)
    result.update(pelvis_side=delta.dot(right) / handle.height,
                  pelvis_forward=delta.dot(forward) / handle.height,
                  pelvis_drop=-delta.dot(up) / handle.height)
    return result


def observed_rotations(handle):
    def delta(name):
        bone = handle.bones[name]
        return bone.matrix.to_quaternion() @ bone.bone.matrix_local.to_quaternion().conjugated()
    root = delta('Hips')
    spine = delta(next(name for name in ('Spine2', 'Spine1', 'Spine') if name in handle.bones))
    return {'root': root, 'torso': spine @ root.conjugated(), 'head': delta('Head') @ spine.conjugated(),
            **{side.lower()+'_'+part.lower(): handle.bones[side+part].matrix.to_quaternion()
               for side in ('Left', 'Right') for part in ('Hand', 'Foot')}}


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
                values[key] = blend_control(plan, stage, key, before, time)
        # Direction interpolation avoids sweeping a shin sideways when changing
        # from backward to forward through the azimuth wrap.
        for side, sign in (('left', -1), ('right', 1)):
            for part in ('arm', 'forearm', 'thigh', 'shin'):
                e, a = side+'_'+part+'_elevation', side+'_'+part+'_azimuth'
                targets = dict(stage.targets)
                if e not in targets or a not in targets or targets[e] is None or targets[a] is None:
                    continue
                se, sa = source.get(e, 0), source.get(a, 0)
                if abs(targets[a] - sa) < 45:
                    continue
                def vector(elev, az):
                    elev, az = math.radians(elev), math.radians(az)
                    return Vector((sign*math.sin(elev)*math.cos(az), math.sin(elev)*math.sin(az), -math.cos(elev)))
                first, last = vector(se, sa), vector(targets[e], targets[a])
                v = Quaternion().slerp(first.rotation_difference(last), weight) @ first
                values[e] = math.degrees(math.acos(max(-1, min(1, -v.z))))
                values[a] = math.degrees(math.atan2(v.y, sign*v.x))
    # IK may have changed an unowned leg or pelvis. Carry that ending state
    # when the next movement does not own it, rather than resetting to rest.
    owned = {k for s, start, end in schedule(plan) if start <= time <= end for k, _ in s.targets}
    explicit = set(starting) | {k for s, start, _ in schedule(plan) if start <= time
                               for k, _ in s.targets}
    for key in measured:
        implicit_lower = next((key.replace('_'+lower+'_', '_'+upper+'_')
                               for lower, upper in (('forearm', 'arm'), ('shin', 'thigh'))
                               if '_'+lower+'_' in key and key not in explicit), None)
        if implicit_lower in owned:
            values.pop(key, None)
            continue
        if key not in owned and (key.startswith('pelvis_') or any('_'+p+'_' in key for p in ('thigh','shin','arm','forearm'))):
            values[key] = measured[key]
    return values


def bake_candidate_frames(handle, plan, repair_floor, progress):
    rig, scene = handle.rig, handle.scene
    action = bpy.data.actions.new(f'Avatar motion r{plan.revision}')
    rig.animation_data.action = action
    try:
        target_pose(handle, PosePlan())
        neutral_feet = {side: handle.bones[side + 'Foot'].head.copy() for side in ('Left', 'Right')}
        neutral_rotation = {side: handle.bones[side + 'Foot'].matrix.to_quaternion() for side in neutral_feet}
        handle._palm_frames = {side: palm_frame(handle, side) for side in ('Left', 'Right')}
        palm_padding = {}
        for side in ('Left', 'Right'):
            hand = handle.bones[side+'Hand']
            basis = hand.matrix_basis.copy()
            hand.matrix = Matrix.Translation(hand.head) @ handle._palm_frames[side].to_matrix().to_4x4()
            bpy.context.view_layer.update()
            padding = (rig.matrix_world @ hand.head).z - support_skin_height(handle, side.lower()+'_hand')
            if math.isfinite(padding):
                palm_padding[side.lower()+'_hand'] = max(.005, padding)
            hand.matrix_basis = basis
            bpy.context.view_layer.update()
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
        entry_anchors = {}
        foot_padding = {}
        elbow_poles = {side: handle.bones[side+'ForeArm'].head.copy() for side in ('Left', 'Right')}
        last_anchor = {side.lower() + '_foot': (0.0, ContactConstraint(side.lower() + '_foot'),
                                               neutral_feet[side], neutral_rotation[side])
                       for side in initial_support}
        samples = []
        # New wrist movement starts from measured coordinates at activation.
        # Future wrist targets must not constrain the preceding crouch.
        initial = dict(plan.initial.values)
        sampling_plan = plan
        baselines = {}
        measured = measured_controls(handle, initial, control_origin)
        count = math.ceil(plan.duration * plan.fps)
        for i in range(count + 1):
            handle._skin_cache_enabled = True
            handle._skin_signature = None
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
            desired_rotations = observed_rotations(handle)
            active = active_contacts(plan, time)
            for key, c, begin, end in active:
                if key not in cached:
                    bone = handle.bones[PART_BONES[c.part]]
                    entry_anchors[key] = bone.head.copy()
                    target = bone.head.copy()
                    old = last_anchor.get(c.part)
                    if old and abs(old[0] - begin) < 1e-6 and old[1].surface == c.surface and old[1].position == c.position:
                        target = old[2].copy()
                    elif c.position is not None:
                        target = origin + handle.height * (right * c.position[0] + forward * c.position[1])
                    world = rig.matrix_world @ target
                    surface = next(s for s in plan.surfaces if s.name == c.surface)
                    if c.position is None and c.part in ('pelvis', 'back') and surface.center:
                        world.x, world.y = surface.center
                        if c.part == 'pelvis':
                            facing = (rig.matrix_world.to_3x3() @ forward).normalized()
                            extent = (surface.size[0]*abs(facing.x) + surface.size[1]*abs(facing.y))/2
                            # The pelvis sits on the forward half: centering the
                            # hip joint lets descending thighs pass through a
                            # high seat before the knee clears its front edge.
                            world += facing * extent * .55
                    if c.part.endswith('_foot') and c.position is None and c.surface == 'floor':
                        # Foot bone origin is above the sole; retain measured rest clearance.
                        if old is None:
                            rest = handle.bones[c.part.split('_')[0].title() + 'Foot'].bone.head_local
                            world.z = (rig.matrix_world @ rest).z
                    else:
                        world.z = floor[c.surface] + (palm_padding.get(c.part, c.clearance*world_height)
                                                     if c.part.endswith('_hand') else c.clearance*world_height)
                    target = rig.matrix_world.inverted() @ world
                    orientation = rest_feet[c.part.split('_')[0]] if c.part.endswith('_foot') else bone.matrix.to_quaternion()
                    cached[key] = target, orientation
                target, orientation = cached[key]
                last_anchor[c.part] = end, c, target, orientation
            # Resolve torso supports before extremities so limb IK uses corrected hips.
            active.sort(key=lambda item: 0 if item[1].part in ('pelvis', 'back') else 1)
            strengths = {}
            for key, c, begin, end in active:
                if c.part not in ('pelvis', 'back') and not any(item[1].part.endswith('_foot') for item in active):
                    minimum = support_floor(handle)
                    if minimum < -.001:
                        hips = handle.bones['Hips']
                        matrix = hips.matrix.copy()
                        matrix.translation += rig.matrix_world.inverted().to_3x3() @ Vector((0, 0, -minimum))
                        hips.matrix = matrix
                        bpy.context.view_layer.update()
                target, orientation = cached[key]
                strength = 1.0
                if c.part in ('pelvis', 'back'):
                    surface = next(s for s in plan.surfaces if s.name == c.surface)
                    bone_world = rig.matrix_world @ handle.bones[PART_BONES[c.part]].head
                    world = rig.matrix_world @ target
                    offset = world.x-bone_world.x, world.y-bone_world.y
                    # Only skin above the actual seat footprint can support it;
                    # the lower end of a descending thigh may be outside it.
                    skin = support_skin_height(handle, c.part, surface, offset)
                    if math.isfinite(skin):
                        # The skin offset changes as the body turns. Clearance
                        # is a fallback hint, not a reason to float above a seat.
                        world.z = floor[c.surface] + max(0.0, bone_world.z - skin)
                        target = rig.matrix_world.inverted() @ world
                        cached[key] = target, orientation
                if c.part.endswith('_foot'):
                    target = target + rig.matrix_world.inverted().to_3x3() @ Vector(
                        (0, 0, foot_padding.get(c.part, 0)))
                if not c.part.endswith('_foot'):
                    ramp = min(c.acquire, end - begin)
                    strength = min(1.0, max(0.0, (time - begin) / ramp))
                    if c.part.endswith('_hand'):
                        strength = min(strength, max(0.0, (end - time) / min(c.release, end-begin)))
                    strength = contact_ease(strength)
                    source = (entry_anchors[key] if c.part in ('pelvis', 'back') else
                              handle.bones[PART_BONES[c.part]].head)
                    target = source.lerp(target, strength)
                strengths[key] = strength
                if strength > 1e-6:
                    set_contact(handle, c, target, orientation, strength,
                                elbow_poles.get(c.part.split('_')[0].title()))
            active_parts = {c.part for _, c, _, _ in active}
            if active_parts & {'pelvis', 'back'} and not any(p.endswith('_foot') for p in active_parts):
                # Collision avoidance continues after a supporting hand releases;
                # ending a contact must not produce a one-frame solver jump.
                for side in ('Left', 'Right'):
                    if side.lower()+'_hand' not in active_parts:
                        keep_hand_above_floor(handle, side, elbow_poles[side])
            for part, (end, _, _, held_rotation) in last_anchor.items():
                if part.endswith('_foot') and part not in active_parts and 0 <= time - end < .6:
                    foot = handle.bones[PART_BONES[part]]
                    weight = contact_ease((time - end) / .6)
                    orientation = held_rotation.slerp(foot.matrix.to_quaternion(), weight)
                    foot.matrix = Matrix.Translation(foot.head) @ orientation.to_matrix().to_4x4()
                    bpy.context.view_layer.update()
            if not active:
                ground_pose(handle, settle=bool(values.get('grounding', 1)))
            surface_errors = {}
            for surface in plan.surfaces:
                if surface.name != 'floor':
                    for _ in range(4):
                        penetration = seat_penetration(handle, surface)
                        if penetration <= .001:
                            break
                        hips = handle.bones['Hips']
                        matrix = hips.matrix.copy()
                        matrix.translation += rig.matrix_world.inverted().to_3x3() @ Vector((0, 0, penetration))
                        hips.matrix = matrix
                        bpy.context.view_layer.update()
                        for key, c, _, _ in active:
                            if c.part.endswith('_foot'):
                                set_contact(handle, c, *cached[key])
                    surface_errors[surface.name] = seat_penetration(handle, surface)
            for _ in range(2 if repair_floor else 1):
                if not active or mesh_floor(handle) >= -.001:
                    break
                penetration = -mesh_floor(handle)
                ground_pose(handle, settle=False)
                for key, c, _, _ in active:
                    if c.part.endswith('_foot') or (c.part.endswith('_hand') and strengths[key] >= .999):
                        target, orientation = cached[key]
                        if c.part.endswith('_foot'):
                            foot_padding[c.part] = min(.02, foot_padding.get(c.part, 0) + penetration)
                            lift = rig.matrix_world.inverted().to_3x3() @ Vector((0, 0, foot_padding[c.part]))
                            target = target + lift
                        if strengths[key] > 1e-6:
                            set_contact(handle, c, target, orientation, strengths[key],
                                        elbow_poles.get(c.part.split('_')[0].title()))
            errors = {}
            for key, c, _, _ in active:
                if strengths[key] < .999:
                    continue
                delta = rig.matrix_world.to_3x3() @ (handle.bones[PART_BONES[c.part]].head - cached[key][0])
                # Other skin can require a higher anchor after projection;
                # the actual support gap is still checked independently.
                if c.part in ('pelvis', 'back') or c.part.endswith('_hand'):
                    delta.z = min(0.0, delta.z)
                    surface = next(s for s in plan.surfaces if s.name == c.surface)
                    skin_gap = abs(support_skin_height(handle, c.part, surface) - floor[c.surface])
                    errors[c.part] = max(delta.length, skin_gap)
                else:
                    errors[c.part] = delta.length
            stage_id = next((s.id for s, start, end in reversed(schedule(plan))
                             if start <= time <= end), '')
            samples.append(capture_sample(handle, frame, stage_id, errors))
            samples[-1]['surfaces'] = surface_errors
            measured = measured_controls(handle, values, control_origin)
            samples[-1]['planned_controls'] = dict(values)
            samples[-1]['controls'] = dict(measured)
            # Expected body rotations come from the requested values, not from
            # the same rig measurements that are being validated.
            from .pose import rotation
            requested = PosePlan(tuple(values.items()))
            rq = rotation(requested, 'root', axes(handle))
            tq = rotation(requested, 'torso', axes(handle, rq))
            hq = rotation(requested, 'head', tuple(tq @ v for v in axes(handle, rq)))
            desired_rotations.update(root=rq, torso=tq, head=hq)
            samples[-1]['desired_rotations'] = desired_rotations
            samples[-1]['actual_rotations'] = observed_rotations(handle)
            elbow_poles = {side: handle.bones[side+'ForeArm'].head.copy() for side in ('Left', 'Right')}
            for bone in rig.pose.bones:
                bone.keyframe_insert('location', frame=frame, group=bone.name)
                bone.keyframe_insert('rotation_quaternion', frame=frame, group=bone.name)
                bone.keyframe_insert('scale', frame=frame, group=bone.name)
            progress((i + 1) / (count + 1))
            handle._skin_cache_enabled = False
            yield (i + 1) / (count + 1)
        linear_keys(action)
        report = review_samples(samples, height=world_height, fps=plan.fps)
        return action, samples, check_completion(plan, samples, report)
    except BaseException:
        handle._skin_cache_enabled = False
        rig.animation_data.action = None
        bpy.data.actions.remove(action)
        raise


def build_action_frames(handle, plan, progress=lambda fraction: None, allow_experimental=False):
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
        action, samples, report = yield from bake_candidate_frames(handle, plan, False, lambda f: progress(f * .5))
        before = report.to_dict()
        repaired = False
        if not report.passed and all(i.kind == 'floor_penetration' for i in report.issues):
            rig.animation_data.action = None
            bpy.data.actions.remove(action)
            action = None
            action, samples, report = yield from bake_candidate_frames(handle, plan, True, lambda f: progress(.5 + f * .5))
            repaired = report.metrics['floor_penetration_m'] < before['metrics']['floor_penetration_m']
        if not report.passed and not allow_experimental:
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
        progress(1)
        endpoint = dict(samples[-1]['controls'])
        explicit = dict(plan.final_pose.values)
        solved_chains = {c.part.split('_')[0]+'_'+part
                         for stage in plan.stages for c in stage.contacts
                         for part in (('arm', 'forearm') if c.part.endswith('_hand') else
                                      ('thigh', 'shin') if c.part.endswith('_foot') else ())}
        endpoint = {k: v for k, v in endpoint.items() if k in LIMITS
                    and ('_hand_target_' not in k or k in explicit)
                    and (not any('_'+p+'_' in k for p in ('arm','forearm','thigh','shin'))
                         or k in explicit or any(k.startswith(chain+'_') for chain in solved_chains))}
        for key, value in endpoint.items():
            low, high = LIMITS[key]
            if low-1e-4 <= value <= high+1e-4:
                endpoint[key] = min(high, max(low, value))
        ending_pose = validate_pose(PosePlan(tuple(sorted(endpoint.items())), plan.final_pose.contact,
                                            plan.revision, plan.description))
        if report.passed and not allow_experimental and old_action and old_action.users == 0:
            bpy.data.actions.remove(old_action)
        return {'frames': len(samples), 'action': action.name, 'review': report.to_dict(),
                'before_repair': before, 'repaired': repaired, 'stages': len(plan.stages),
                'experimental': not report.passed, 'ending_pose': serialize_pose(ending_pose)}
    except BaseException:
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


def build_action(handle, plan, progress=lambda fraction: None, allow_experimental=False):
    iterator = build_action_frames(handle, plan, progress, allow_experimental)
    try:
        while True:
            next(iterator)
    except StopIteration as completed:
        return completed.value
