"""A new movement must preserve a crouched, contact-solved starting posture."""
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.motion import build_action
from avatar_app.pose import update_pose
from avatar_app.motion import ActionPlan, ContactConstraint
from avatar_app.planning.movements import movement

handle = import_avatar(str(ROOT / 'Hip Hop Andrejs.fbx'))
rest_height = (handle.rig.matrix_world @ handle.bones['Hips'].head).z
initial = update_pose(None, {'pelvis_drop': .2, 'torso_pitch': 25}, 'both')
plan = ActionPlan((movement('reach', 'Reach without losing the crouch', {'right_arm': 'up'}, 1.0,
                           [ContactConstraint('left_foot'), ContactConstraint('right_foot')]),), initial=initial)
result = build_action(handle, plan)
handle.scene.frame_set(1)
start = (handle.rig.matrix_world @ handle.bones['Hips'].head).z
assert start < rest_height - .25, (start, rest_height)
handle.scene.frame_set(handle.scene.frame_end)
end = (handle.rig.matrix_world @ handle.bones['Hips'].head).z
print('START_END_HEIGHTS', start, end, flush=True)
assert abs(end - start) < .025
assert result['review']['passed']
forearm = (handle.bones['RightForeArm'].tail - handle.bones['RightForeArm'].head).normalized()
assert forearm.dot(handle.up) > .99, 'An unspecified forearm did not follow the upper arm'
print('SOLVED_STARTING_STATE_PRESERVED', start, end, flush=True)
