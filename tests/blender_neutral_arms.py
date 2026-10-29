"""Check relaxed arms without replacing each rig's authored wrist/head angles."""
from pathlib import Path
import math
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar_app.blender.avatar import import_avatar, discard_avatar
from avatar_app.blender.pose import axes, target_pose, build_pose_transition, rotation
from avatar_app.pose import PosePlan, update_pose

original_scene = bpy.context.scene
for filename in ('Hip Hop Andrejs.fbx', 'Hip Hop Mixamo.fbx'):
    handle = import_avatar(str(ROOT / filename))
    build_pose_transition(handle, update_pose(None, {'duration': .5}))
    handle.scene.frame_set(handle.scene.frame_end)
    right, forward, up = axes(handle)
    for side, sign in (('Left', -1), ('Right', 1)):
        forearm = handle.bones[side + 'ForeArm']
        hand = handle.bones[side + 'Hand']
        upper = handle.bones[side + 'Arm']
        for bone in (upper, forearm):
            direction = (bone.tail - bone.head).normalized()
            assert abs(direction.dot(up) + math.cos(math.radians(8))) < 1e-4
            assert abs(direction.dot(right) - sign * math.sin(math.radians(8))) < 1e-4
            assert abs(direction.dot(forward)) < 1e-4
        assert (hand.head - upper.head).dot(right) * sign > 0
        assert hand.matrix_basis.to_quaternion().angle < 1e-4, 'Neutral pose changed the authored wrist angle'
    assert handle.bones['Head'].matrix_basis.to_quaternion().angle < 1e-4, 'Neutral pose added a head rotation'

    # Explicit down and wrist rotation must override the relaxed defaults.
    handle.rig.animation_data_clear()
    target_pose(handle, update_pose(None, {'right_arm_elevation': 0}))
    hand = handle.bones['RightHand']
    assert hand.matrix_basis.to_quaternion().angle < 1e-4
    baseline = hand.matrix.to_quaternion()
    plan = update_pose(None, {'right_arm_elevation': 0, 'right_hand_pitch': 30})
    target_pose(handle, plan)
    expected = rotation(plan, 'right_hand', axes(handle)) @ baseline
    actual = hand.matrix.to_quaternion()
    assert abs(expected.dot(actual)) > .9999
    # Parent rotations should carry wrists/head without adding local offsets.
    target_pose(handle, update_pose(None, {'torso_pitch': 20, 'left_arm_elevation': 90}))
    for name in ('LeftHand', 'RightHand', 'Head'):
        assert handle.bones[name].matrix_basis.to_quaternion().angle < 1e-4, name
    print('NEUTRAL_ARMS_VERIFIED', filename, flush=True)
    bpy.context.window.scene = original_scene
    discard_avatar(handle)
print('ALL_NEUTRAL_ARM_CHECKS_PASSED', flush=True)
