"""General directional skeletal posing with optional foot contact and grounding."""
import math
import bpy
from mathutils import Matrix, Quaternion, Vector
from ..pose import validate_pose
from ..models import PlanError
from .animation import aim, solve_leg
from .geometry import skin_bounds


def axes(handle, rotation=None):
    rotation = rotation or Quaternion()
    up = handle.up.normalized()
    right = (handle.right - up * handle.right.dot(up)).normalized()
    forward = up.cross(right).normalized()
    return tuple(rotation @ v for v in (right, forward, up))


def rotation(plan, prefix, frame_axes):
    right, forward, up = frame_axes
    return (Quaternion(up, math.radians(plan.get(prefix + '_yaw')))
            @ Quaternion(forward, math.radians(plan.get(prefix + '_roll')))
            @ Quaternion(right, -math.radians(plan.get(prefix + '_pitch'))))


def rotate_bone(bone, quaternion):
    if quaternion.x ** 2 + quaternion.y ** 2 + quaternion.z ** 2 < 1e-14:
        return
    head = bone.head.copy()
    bone.matrix = (Matrix.Translation(head) @ quaternion.to_matrix().to_4x4()
                   @ Matrix.Translation(-head) @ bone.matrix)
    bpy.context.view_layer.update()


def direction(plan, prefix, side, frame_axes, inherit=None):
    elevation = plan.get(prefix + '_elevation', inherit[0] if inherit else 0)
    azimuth = plan.get(prefix + '_azimuth', inherit[1] if inherit else 0)
    right, forward, up = frame_axes
    e, a = math.radians(elevation), math.radians(azimuth)
    vector = (right * side * (math.sin(e) * math.cos(a))
              + forward * (math.sin(e) * math.sin(a)) - up * math.cos(e))
    return vector, (elevation, azimuth)


def position_hand(handle, side, target, frame_axes, pole=None):
    upper = handle.bones[side + 'Arm']
    lower = handle.bones[side + 'ForeArm']
    hand = handle.bones[side + 'Hand']
    origin = upper.head.copy()
    a, b = (lower.head - origin).length, (hand.head - lower.head).length
    delta = target - origin
    distance = delta.length
    if distance > a + b + 1e-5 or distance <= abs(a - b) + 1e-5:
        raise PlanError(f'The {side.lower()} hand target is beyond this avatar’s reach. Try a closer target.')
    axis = delta.normalized()
    right, forward, up = frame_axes
    pole = (pole - origin) if pole is not None else right * (-1 if side == 'Left' else 1) - up * .65 + forward * .2
    bend = pole - axis * pole.dot(axis)
    if bend.length < 1e-6:
        bend = forward - axis * forward.dot(axis)
    bend.normalize()
    along = (a * a - b * b + distance * distance) / (2 * distance)
    elbow = origin + axis * along + bend * math.sqrt(max(0, a * a - along * along))
    aim(upper, elbow - origin)
    aim(lower, target - lower.head)


def target_pose(handle, plan):
    rig, bones = handle.rig, handle.bones
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
        bone.rotation_mode = 'QUATERNION'
    bpy.context.view_layer.update()
    original_axes = axes(handle)
    root_rotation = rotation(plan, 'root', original_axes)
    hips = bones['Hips']
    rotate_bone(hips, root_rotation)
    right, forward, up = original_axes
    matrix = hips.matrix.copy()
    matrix.translation += handle.height * (right * plan.get('pelvis_side')
        + forward * plan.get('pelvis_forward') - up * plan.get('pelvis_drop'))
    hips.matrix = matrix
    bpy.context.view_layer.update()
    root_axes = axes(handle, root_rotation)
    torso_rotation = rotation(plan, 'torso', root_axes)
    spine_chain = [bones[name] for name in ('Spine', 'Spine1', 'Spine2') if name in bones]
    partial = Quaternion().slerp(torso_rotation, 1 / len(spine_chain))
    for bone in spine_chain:
        rotate_bone(bone, partial)
    torso_axes = tuple(torso_rotation @ axis for axis in root_axes)
    rotate_bone(bones['Head'], rotation(plan, 'head', torso_axes))
    specified = dict(plan.values)
    for side, sign in (('Left', -1), ('Right', 1)):
        key = side.lower()
        # A small outward angle keeps relaxed arms clear of the torso and hips.
        # Explicit elevations (including straight down) still take precedence.
        upper, inherited = direction(plan, key + '_arm', sign, root_axes, (8, 0))
        aim(bones[side + 'Arm'], upper)
        lower, _ = direction(plan, key + '_forearm', sign, root_axes, inherited)
        aim(bones[side + 'ForeArm'], lower)
        if key + '_hand_target_side' in specified:
            right, forward, up = root_axes
            target = hips.head + handle.height * (
                right * plan.get(key + '_hand_target_side')
                + forward * plan.get(key + '_hand_target_forward')
                + up * plan.get(key + '_hand_target_height'))
            position_hand(handle, side, target, root_axes)
        # Imported bind poses can have asymmetric wrist bends. Align the hand
        # with the solved forearm before applying the requested wrist rotation.
        forearm = bones[side + 'ForeArm']
        aim(bones[side + 'Hand'], forearm.tail - forearm.head)
        rotate_bone(bones[side + 'Hand'], rotation(plan, key + '_hand', root_axes))
        # Preserve the original stance unless the legs have explicit directions.
        if any(name.startswith((key + '_thigh_', key + '_shin_')) for name in specified):
            upper, inherited = direction(plan, key + '_thigh', sign, root_axes)
            aim(bones[side + 'UpLeg'], upper)
            lower, _ = direction(plan, key + '_shin', sign, root_axes, inherited)
            aim(bones[side + 'Leg'], lower)
        rotate_bone(bones[side + 'Foot'], rotation(plan, key + '_foot', root_axes))
    return {bone.name: bone.matrix_basis.copy() for bone in rig.pose.bones}


def contacts(plan):
    if plan.contact != 'auto':
        return {'both': ('Left', 'Right'), 'left': ('Left',), 'right': ('Right',), 'none': ()}[plan.contact]
    if any(plan.get('root_' + axis) for axis in ('pitch', 'yaw', 'roll')):
        return ()
    specified = dict(plan.values)
    return tuple(side for side in ('Left', 'Right') if not any(
        name.startswith((side.lower() + '_thigh_', side.lower() + '_shin_')) for name in specified))


def ground_pose(handle, settle=True):
    minimum = skin_bounds(handle)[0].z
    if minimum < -1e-4 or (settle and abs(minimum) > 1e-4):
        offset = handle.rig.matrix_world.inverted().to_3x3() @ Vector((0, 0, -minimum))
        hips = handle.bones['Hips']
        matrix = hips.matrix.copy()
        matrix.translation += offset
        hips.matrix = matrix
        bpy.context.view_layer.update()


def frame_transition(handle, plan, frames=None):
    if not handle.scene.camera:
        return
    points = []
    for frame in frames or (handle.scene.frame_start, handle.scene.frame_end):
        handle.scene.frame_set(frame)
        points.extend(skin_bounds(handle))
    low = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    high = Vector(tuple(max(point[i] for point in points) for i in range(3)))
    center = (low + high) * 0.5
    radius = (high - low).length * 0.5
    camera = handle.scene.camera
    backward = camera.rotation_euler.to_quaternion() @ Vector((0, 0, 1))
    if 60 <= abs(plan.get('root_pitch')) <= 120:
        right, forward, up = axes(handle)
        backward = (handle.rig.matrix_world.to_3x3()
                    @ (right * .8 + forward * .5 + up * .8)).normalized()
    half_angle = min(camera.data.angle_x, camera.data.angle_y) * 0.5
    camera.location = center + backward * (radius / math.sin(half_angle) * 1.1)
    camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()


def build_pose_transition(handle, plan, progress=lambda value: None):
    validate_pose(plan)
    rig, scene = handle.rig, handle.scene
    rig.animation_data_create()
    old_action = rig.animation_data.action
    old_basis = {bone.name: bone.matrix_basis.copy() for bone in rig.pose.bones}
    old_modes = {bone.name: bone.rotation_mode for bone in rig.pose.bones}
    old_frame = scene.frame_current
    action = bpy.data.actions.new(f'Avatar pose r{plan.revision}')
    rig.animation_data.action = action
    try:
        target = target_pose(handle, plan)
        for bone in rig.pose.bones:
            bone.matrix_basis.identity()
        bpy.context.view_layer.update()
        feet = {side: handle.bones[side + 'Foot'].head.copy() for side in ('Left', 'Right')}
        foot_orientation = {side: handle.bones[side + 'Foot'].matrix.to_quaternion() for side in feet}
        planted = contacts(plan)
        count = round(plan.duration * plan.fps)
        max_error = 0.0
        for i in range(count + 1):
            scene.frame_set(i + 1)
            t = i / count
            weight = t * t * (3 - 2 * t)
            for bone in rig.pose.bones:
                location, orientation, scale = target[bone.name].decompose()
                bone.location = location * weight
                bone.rotation_quaternion = Quaternion().slerp(orientation, weight)
                bone.scale = Vector((1, 1, 1)).lerp(scale, weight)
            bpy.context.view_layer.update()
            if i:
                for side in planted:
                    solve_leg(handle, side, feet[side])
                    foot = handle.bones[side + 'Foot']
                    foot_delta = Quaternion().slerp(rotation(plan, side.lower() + '_foot', axes(handle)), weight)
                    foot.matrix = (Matrix.Translation(foot.head)
                                   @ (foot_delta @ foot_orientation[side]).to_matrix().to_4x4())
                    bpy.context.view_layer.update()
                    max_error = max(max_error, (foot.head - feet[side]).length)
            if not planted:
                ground_pose(handle, settle=bool(plan.get('grounding', 1)))
            for bone in rig.pose.bones:
                if not all(math.isfinite(value) for row in bone.matrix_basis for value in row):
                    raise PlanError('The requested pose produced invalid joint transforms.')
                bone.keyframe_insert('location', frame=i + 1, group=bone.name)
                bone.keyframe_insert('rotation_quaternion', frame=i + 1, group=bone.name)
                bone.keyframe_insert('scale', frame=i + 1, group=bone.name)
            progress((i + 1) / (count + 1))
        for slot in action.slots:
            for layer in action.layers:
                for strip in layer.strips:
                    bag = strip.channelbag(slot)
                    if bag:
                        for curve in bag.fcurves:
                            for key in curve.keyframe_points:
                                key.interpolation = 'LINEAR'
        scene.render.fps = plan.fps
        scene.frame_start, scene.frame_end = 1, count + 1
        frame_transition(handle, plan)
        scene.frame_set(1)
        if old_action and old_action.users == 0:
            bpy.data.actions.remove(old_action)
        return {'frames': count + 1, 'action': action.name, 'contact_error': max_error}
    except Exception:
        rig.animation_data.action = old_action
        for bone in rig.pose.bones:
            bone.rotation_mode = old_modes[bone.name]
            bone.matrix_basis = old_basis[bone.name]
        bpy.data.actions.remove(action)
        scene.frame_set(old_frame)
        raise
