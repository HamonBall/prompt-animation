"""Fix regressions: fresh checkout, real skin, measured goals, experimental preview."""
from pathlib import Path
import sys
import json
import math
from unittest.mock import patch
import bpy
from mathutils import Vector, Quaternion

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar_app import main as app
from avatar_app.motion import ActionPlan, ContactConstraint
from avatar_app.planning.movements import movement
from avatar_app.blender.motion import build_action, build_action_frames, check_completion, MotionReview, review_samples
from avatar_app.blender.geometry import skin_bounds
from avatar_app.models import PlanError

with patch.object(app, '_default_avatar', return_value=ROOT / 'absent-demo.fbx'):
    app.main()
handle = app._state['avatar']
assert handle and handle.rig.name == 'Built-in Avatar'
assert any(o.name == 'Preview floor' for o in handle.environment)
assert any(s.name == 'seat' and s.center for s in handle.surfaces)
assert all(o not in handle.objects for o in handle.environment)
assert abs(skin_bounds(handle)[0].z) < .003

# Modal construction can be interrupted without leaving a partial action.
old_action = handle.rig.animation_data.action
old_frame = handle.scene.frame_current
iterator = build_action_frames(handle, ActionPlan((movement('reach', 'Reach', {'right_arm':'up'}, 1),)))
next(iterator)
iterator.close()
assert handle.rig.animation_data.action == old_action and handle.scene.frame_current == old_frame

# The planned number can say "45" while the actual pose still says "0".
goal = ActionPlan((movement('look', 'Look left', {'head': 'left:45'}, 1),))
fake_sample = {'frame':31, 'controls': {'head_yaw':0}, 'planned_controls':{'head_yaw':45},
               'desired_rotations':{'head':Quaternion(Vector((0,0,1)), .785398)},
               'actual_rotations':{'head':Quaternion()}, 'contacts':{}}
report = check_completion(goal, [fake_sample]*31, MotionReview([], {}))
assert any(i.kind == 'incomplete_target' for i in report.issues)
contact_goal = ActionPlan((movement('touch', 'Touch floor', {'head':'left:45'}, 1,
                                   (ContactConstraint('left_hand'),)),))
report = check_completion(contact_goal, [fake_sample]*31, MotionReview([], {}))
assert any(i.kind == 'incomplete_contact' for i in report.issues)

# Equal speed in opposite directions is still angular acceleration.
reversal = [{'frame':i+1, 'floor':0, 'root':Vector(), 'rotations':{'arm':q}}
            for i,q in enumerate((Quaternion(), Quaternion(Vector((0,0,1)), math.radians(2)), Quaternion()))]
review = review_samples(reversal)
assert review.metrics['joint_speed_deg_s'] < 360
assert any(i.kind == 'joint_acceleration' for i in review.issues)

fast = ActionPlan((movement('fast', 'Raise arm abruptly', {'right_arm':'up'}, .2),))
old_action = handle.rig.animation_data.action
try:
    build_action(handle, fast)
    raise AssertionError('Excessive speed was accepted')
except PlanError as exc:
    assert handle.rig.animation_data.action == old_action
    assert any(i['kind'] == 'abrupt_joint_change' for i in exc.review['issues'])
preview = build_action(handle, fast, allow_experimental=True)
assert preview['experimental'] and not preview['review']['passed']
assert old_action.name in bpy.data.actions

out = ROOT/'artifacts'/'motionfix'
out.mkdir(parents=True, exist_ok=True)
# Restore a reviewed result and show the source-free character with its scene.
app.generate(bpy.context, 'neutral pose')
handle.scene.frame_set(handle.scene.frame_end)
handle.scene.render.resolution_percentage = 60
handle.scene.render.filepath = str(out/'builtin-avatar.png')
bpy.ops.render.render(write_still=True)
try:
    app.generate(bpy.context, 'Sit on a chair.')
except PlanError as exc:
    print('SEAT_REVIEW_FAILURE', json.dumps(getattr(exc, 'review', {})), flush=True)
    raise
handle.scene.frame_set(handle.scene.frame_end)
handle.scene.render.filepath = str(out/'builtin-seated.png')
bpy.ops.render.render(write_still=True)
app.generate(bpy.context, 'Lie down on the floor.')
assert not any(s.name == 'seat' for s in handle.surfaces)
assert not handle.scene.avatar_show_seat
assert app._state['plan'].resolved_final is not None
handle.scene.frame_set(handle.scene.frame_end)
handle.scene.render.filepath = str(out/'builtin-lying.png')
bpy.ops.render.render(write_still=True)
(out/'experimental-review.json').write_text(json.dumps(preview, indent=2), encoding='utf-8')
print('MOTIONFIX_FRESH_CHECKOUT_AND_REVIEW_PASSED', flush=True)
