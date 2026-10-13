"""Geometric pose transition with two-segment leg contact solving."""
import math
import bpy
from mathutils import Matrix, Quaternion
from ..planning.validation import validate_plan


def aim(bone, direction):
    direction = direction.normalized()
    current = (bone.tail - bone.head).normalized()
    if (current - direction).length_squared < 1e-14:
        return
    rotation = current.rotation_difference(direction)
    head = bone.head.copy()
    bone.matrix = (Matrix.Translation(head) @ rotation.to_matrix().to_4x4()
                   @ Matrix.Translation(-head) @ bone.matrix)
    bpy.context.view_layer.update()


def solve_leg(handle, side, target):
    upper = handle.bones[side + 'UpLeg']
    lower = handle.bones[side + 'Leg']
    foot = handle.bones[side + 'Foot']
    origin = upper.head.copy()
    a = (lower.head - origin).length
    b = (foot.head - lower.head).length
    delta = target - origin
    distance = delta.length
    if distance > a + b + 1e-4 or distance < abs(a - b) + 1e-5:
        raise ValueError('The foot target is beyond this avatar’s leg reach.')
    axis = delta.normalized()
    bend = handle.forward - axis * handle.forward.dot(axis)
    bend.normalize()
    along = (a * a - b * b + distance * distance) / (2 * distance)
    knee = origin + axis * along + bend * math.sqrt(max(0, a * a - along * along))
    aim(upper, knee - origin)
    aim(lower, target - lower.head)


def build_transition(handle, plan, progress=lambda value: None):
    """Build a new action, restoring the previous action and pose on failure."""
    validate_plan(plan)
    rig = handle.rig
    scene = handle.scene
    rig.animation_data_create()
    old_action = rig.animation_data.action
    old_basis = {b.name: b.matrix_basis.copy() for b in rig.pose.bones}
    old_frame = scene.frame_current
    action = bpy.data.actions.new(f'Avatar transition r{plan.revision}')
    rig.animation_data.action = action
    try:
        for bone in rig.pose.bones:
            bone.matrix_basis.identity()
            bone.rotation_mode = 'QUATERNION'
        bpy.context.view_layer.update()
        rest = {bone.name: bone.matrix_basis.copy() for bone in rig.pose.bones}
        feet = {side: handle.bones[side + 'Foot'].head.copy() for side in ('Left', 'Right')}
        foot_rotation = {side: handle.bones[side + 'Foot'].matrix.to_quaternion()
                         for side in feet}
        count = round(plan.duration * plan.fps)
        max_error = 0.0
        for i in range(count + 1):
            scene.frame_set(i + 1)
            for bone in rig.pose.bones:
                bone.matrix_basis = rest[bone.name]
            bpy.context.view_layer.update()
            t = i / count
            weight = t * t * (3 - 2 * t)
            hips = handle.bones['Hips']
            transform = hips.matrix.copy()
            transform.translation -= handle.up * (plan.crouch * handle.height * weight)
            hips.matrix = transform
            bpy.context.view_layer.update()
            if i:
                for side in feet:
                    solve_leg(handle, side, feet[side])
                    foot = handle.bones[side + 'Foot']
                    foot.matrix = (Matrix.Translation(foot.head)
                                   @ foot_rotation[side].to_matrix().to_4x4())
                    bpy.context.view_layer.update()
                    max_error = max(max_error, (foot.head - feet[side]).length)
            for side, sign in (('Left', -1), ('Right', 1)):
                for suffix, desired in (
                    ('Arm', handle.forward * 0.35 + handle.up * (-1 + plan.arm_lift)
                     + handle.right * sign * 0.12),
                    ('ForeArm', handle.forward + handle.up * (0.75 + plan.arm_lift)),
                    ('Hand', handle.forward * 0.7 - handle.up * 0.7),
                ):
                    bone = handle.bones[side + suffix]
                    start = (bone.tail - bone.head).normalized()
                    rotation = start.rotation_difference(desired.normalized())
                    blended = Quaternion().slerp(rotation, weight)
                    aim(bone, blended @ start)
            for bone in rig.pose.bones:
                bone.keyframe_insert('location', frame=i + 1, group=bone.name)
                bone.keyframe_insert('rotation_quaternion', frame=i + 1, group=bone.name)
                bone.keyframe_insert('scale', frame=i + 1, group=bone.name)
            progress((i + 1) / (count + 1))
        # Every frame is sampled; avoid Bezier overshoot between contact samples.
        for slot in action.slots:
            for layer in action.layers:
                for strip in layer.strips:
                    bag = strip.channelbag(slot)
                    if bag:
                        for curve in bag.fcurves:
                            for key in curve.keyframe_points:
                                key.interpolation = 'LINEAR'
        scene.render.fps = plan.fps
        scene.frame_start = 1
        scene.frame_end = count + 1
        scene.frame_set(1)
        if old_action and old_action.users == 0:
            bpy.data.actions.remove(old_action)
        return {'frames': count + 1, 'contact_error': max_error,
                'action': action.name}
    except Exception:
        rig.animation_data.action = old_action
        for bone in rig.pose.bones:
            bone.matrix_basis = old_basis[bone.name]
        bpy.data.actions.remove(action)
        scene.frame_set(old_frame)
        raise
