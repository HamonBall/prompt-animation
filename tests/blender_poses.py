"""Check general pose geometry, contacts, isolation and representative renders."""
from pathlib import Path
import sys
import math
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar_app.pose import update_pose
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.pose import build_pose_transition
from avatar_app.blender.scene import prepare_preview
from avatar_app.models import PlanError

filename = sys.argv[sys.argv.index('--avatar') + 1] if '--avatar' in sys.argv else 'Hip Hop Andrejs.fbx'
handle = import_avatar(str(ROOT / filename))
prepare_preview(handle)
material_ids = {obj.name: tuple(slot.material for slot in obj.material_slots)
                for obj in handle.objects if obj.type == 'MESH'}
CASES = {
    'overhead': {'left_arm_elevation': 180, 'right_arm_elevation': 180},
    'salute': {'right_hand_target_side': .08, 'right_hand_target_forward': .09,
               'right_hand_target_height': .4},
    'seated': {'pelvis_drop': .25, 'left_thigh_elevation': 90, 'right_thigh_elevation': 90,
               'left_thigh_azimuth': 90, 'right_thigh_azimuth': 90,
               'left_shin_elevation': 0, 'right_shin_elevation': 0},
    'bow': {'torso_pitch': 65},
    'balance': {'right_thigh_elevation': 90, 'right_thigh_azimuth': 90,
                'right_shin_elevation': 0, 'left_arm_elevation': 90,
                'right_arm_elevation': 90},
    'lying': {'root_pitch': -90, 'pelvis_drop': .45, 'left_arm_elevation': 90,
              'right_arm_elevation': 90},
}
output = ROOT / 'artifacts' / 'poses'
output.mkdir(parents=True, exist_ok=True)
for name, values in CASES.items():
    plan = update_pose(None, {'duration': .5, **values},
                       contact='none' if name in ('seated', 'lying') else 'auto')
    result = build_pose_transition(handle, plan)
    handle.scene.frame_set(handle.scene.frame_end)
    rig = handle.rig
    head = rig.matrix_world @ handle.bones['Head'].head
    hips = rig.matrix_world @ handle.bones['Hips'].head
    left_hand = rig.matrix_world @ handle.bones['LeftHand'].head
    right_hand = rig.matrix_world @ handle.bones['RightHand'].head
    if name == 'overhead':
        assert left_hand.z > head.z and right_hand.z > head.z
    if name == 'salute':
        assert right_hand.z > left_hand.z + .4
    if name == 'seated':
        for side in ('Left', 'Right'):
            knee = rig.matrix_world @ handle.bones[side + 'Leg'].head
            thigh = rig.matrix_world @ handle.bones[side + 'UpLeg'].head
            assert abs(knee.z - thigh.z) < .03
    if name == 'balance':
        assert (rig.matrix_world @ handle.bones['RightFoot'].head).z > .3
    if name == 'lying':
        assert abs(head.z - hips.z) < .12
        graph = bpy.context.evaluated_depsgraph_get()
        points = [obj.matrix_world @ Vector(corner) for obj in handle.objects if obj.type == 'MESH'
                  for corner in obj.evaluated_get(graph).bound_box]
        assert abs(min(point.z for point in points)) < .002
    for bone in rig.pose.bones:
        assert all(math.isfinite(x) for row in bone.matrix for x in row)
        assert max(abs(x - 1) for x in bone.scale) < .002
    for obj in handle.objects:
        if obj.type == 'MESH':
            assert tuple(slot.material for slot in obj.material_slots) == material_ids[obj.name]
    print('GENERAL_POSE_VERIFIED', name, result, flush=True)
    if '--render' in sys.argv:
        handle.scene.render.filepath = str(output / (name + '.png'))
        handle.scene.render.resolution_percentage = 60
        bpy.ops.render.render(write_still=True)
good_action = handle.rig.animation_data.action
good_frame = handle.scene.frame_current
good_basis = {bone.name: bone.matrix_basis.copy() for bone in handle.rig.pose.bones}
try:
    impossible = update_pose(None, {'right_hand_target_side': .8,
                                    'right_hand_target_forward': .8,
                                    'right_hand_target_height': .8})
    build_pose_transition(handle, impossible)
    raise AssertionError('Unreachable wrist target was accepted')
except PlanError:
    assert handle.rig.animation_data.action == good_action
    assert handle.scene.frame_current == good_frame
    for bone in handle.rig.pose.bones:
        difference = bone.matrix_basis - good_basis[bone.name]
        assert max(abs(value) for row in difference for value in row) < 1e-5
print('UNREACHABLE_TARGET_ROLLBACK_PASSED')
print('ALL_GENERAL_POSE_CHECKS_PASSED')
