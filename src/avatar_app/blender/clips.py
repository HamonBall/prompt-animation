"""Retarget, trim and time-adjust a selected local Mixamo clip, then review it."""
import math
import bpy
from mathutils import Matrix, Quaternion, Vector
from ..models import PlanError
from .avatar import import_avatar, discard_avatar
from .pose import axes, ground_pose, frame_transition
from .animation import solve_leg
from .motion import capture_sample, review_samples, linear_keys
from ..pose import PosePlan


def anatomical_frame(handle):
    return Matrix(axes(handle)).transposed().to_quaternion()


def build_clip(handle, record, duration=None, pelvis_height=None, progress=lambda value: None):
    """Standalone adapted segment; prior candidate is preserved on any failure.

    Pelvis destination is in world metres, blended over the last half of the
    clip. Planted intervals must be supplied by catalog metadata, not inferred.
    This adapter does not invent a sitting clip when none has been supplied.
    """
    rig, scene = handle.rig, handle.scene
    rig.animation_data_create()
    old_action = rig.animation_data.action
    basis = {b.name: b.matrix_basis.copy() for b in rig.pose.bones}
    modes = {b.name: b.rotation_mode for b in rig.pose.bones}
    timeline = scene.frame_start, scene.frame_end, scene.frame_current, scene.render.fps
    camera = scene.camera.matrix_world.copy() if scene.camera else None
    source, action = None, None
    try:
        source = import_avatar(record.path, import_motion=True)
        if not source.source_actions:
            raise PlanError('The selected FBX contains no animation clip.')
        if len(source.source_actions) != 1:
            raise PlanError('Provide a single-clip FBX; multiple takes need an explicit take selector.')
        clip = source.source_actions[0]
        low, high = clip.frame_range
        start = low if record.start_frame is None else record.start_frame
        end = high if record.end_frame is None else record.end_frame
        if start < low or end > high or end <= start:
            raise PlanError('Clip trimming is outside the source timeline.')
        duration = (end - start) / source.scene.render.fps if duration is None else duration
        if type(duration) not in (int, float) or not math.isfinite(duration) or not .2 <= duration <= 60:
            raise PlanError('Adapted clip duration must be .2–60 seconds.')
        if pelvis_height is not None and (type(pelvis_height) not in (int, float)
                                          or not math.isfinite(pelvis_height) or not 0 <= pelvis_height <= 2):
            raise PlanError('Invalid pelvis destination.')
        source.rig.animation_data_create()
        source.rig.animation_data.action = clip
        if len(clip.slots) != 1:
            raise PlanError('Provide a single-rig clip action.')
        source.rig.animation_data.action_slot = clip.slots[0]
        conversion = anatomical_frame(handle) @ anatomical_frame(source).conjugated()
        mapping = {}
        for name, bone in handle.bones.items():
            if name not in source.bones:
                continue
            sr = source.bones[name].bone.matrix_local.to_quaternion()
            tr = bone.bone.matrix_local.to_quaternion()
            mapping[name] = tr.conjugated() @ conversion @ sr
        count = math.ceil(duration * 30)
        frames = []
        # Sampling and applying are separate: no source scene dependencies during commit.
        for i in range(count + 1):
            bpy.context.window.scene = source.scene
            f = start + (end - start) * i / count
            source.scene.frame_set(math.floor(f), subframe=f - math.floor(f))
            bpy.context.view_layer.update()
            frames.append({name: source.bones[name].matrix_basis.copy() for name in mapping})
        bpy.context.window.scene = scene
        action = bpy.data.actions.new('Avatar adapted ' + record.id)
        rig.animation_data.action = action
        for b in rig.pose.bones:
            b.matrix_basis.identity()
            b.rotation_mode = 'QUATERNION'
        bpy.context.view_layer.update()
        feet = {s: handle.bones[s.title() + 'Foot'].head.copy() for s in record.planted_feet}
        orientations = {s: handle.bones[s.title() + 'Foot'].matrix.to_quaternion() for s in feet}
        samples = []
        for i, transforms in enumerate(frames):
            scene.frame_set(i + 1)
            for b in rig.pose.bones:
                b.matrix_basis.identity()
            for name, matrix in transforms.items():
                location, q, scale = matrix.decompose()
                bone = handle.bones[name]
                c = mapping[name]
                bone.rotation_quaternion = c @ q @ c.conjugated()
                if name == 'Hips':
                    bone.location = (c @ location) * handle.height / source.height
            bpy.context.view_layer.update()
            if pelvis_height is not None:
                t = max(0, (i / count - .5) * 2)
                weight = t * t * (3 - 2 * t)
                hips = handle.bones['Hips']
                height = (rig.matrix_world @ hips.head).z
                offset = rig.matrix_world.inverted().to_3x3() @ Vector((0, 0, (pelvis_height - height) * weight))
                matrix = hips.matrix.copy()
                matrix.translation += offset
                hips.matrix = matrix
                bpy.context.view_layer.update()
            for s, target in feet.items():
                solve_leg(handle, s.title(), target)
                foot = handle.bones[s.title() + 'Foot']
                foot.matrix = Matrix.Translation(foot.head) @ orientations[s].to_matrix().to_4x4()
                bpy.context.view_layer.update()
            if not feet:
                ground_pose(handle, settle=False)
            errors = {s + '_foot': (rig.matrix_world.to_3x3() @
                      (handle.bones[s.title() + 'Foot'].head - feet[s])).length for s in feet}
            samples.append(capture_sample(handle, i + 1, record.id, errors))
            for bone in rig.pose.bones:
                bone.keyframe_insert('location', frame=i + 1, group=bone.name)
                bone.keyframe_insert('rotation_quaternion', frame=i + 1, group=bone.name)
                bone.keyframe_insert('scale', frame=i + 1, group=bone.name)
            progress((i + 1) / (count + 1))
        report = review_samples(samples)
        if not report.passed:
            error = PlanError('Adapted clip failed timeline review. Previous animation kept.')
            error.review = report.to_dict()
            raise error
        linear_keys(action)
        scene.render.fps = 30
        scene.frame_start, scene.frame_end = 1, count + 1
        frame_transition(handle, PosePlan(), [1, count // 2 + 1, count + 1])
        scene.frame_set(1)
        if old_action and old_action.users == 0:
            bpy.data.actions.remove(old_action)
        return {'frames': count + 1, 'duration': duration, 'source_duration': (end - start) / source.scene.render.fps,
                'action': action.name, 'review': report.to_dict()}
    except Exception:
        bpy.context.window.scene = scene
        rig.animation_data.action = old_action
        if action:
            bpy.data.actions.remove(action)
        scene.frame_start, scene.frame_end, frame, scene.render.fps = timeline
        scene.frame_set(frame)
        if camera is not None:
            scene.camera.matrix_world = camera
        for bone in rig.pose.bones:
            bone.rotation_mode = modes[bone.name]
            bone.matrix_basis = basis[bone.name]
        bpy.context.view_layer.update()
        raise
    finally:
        bpy.context.window.scene = scene
        if source:
            discard_avatar(source)
