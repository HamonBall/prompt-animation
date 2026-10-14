"""Shared bone aiming and two-segment leg IK for pose, motion and clips."""
import math
import bpy
from mathutils import Matrix


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
