"""Whole-timeline integration and comparison of direct vs staged lying down."""
from pathlib import Path
import json
import sys
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender.pose import build_pose_transition
from avatar_app.blender.motion import build_action, review_existing, review_samples
from avatar_app.pose import update_pose
from avatar_app.planning.movements import lying_down_plan, movement, sitting_plan
from avatar_app.motion import ActionPlan, ContactConstraint
from avatar_app.models import PlanError

handle = import_avatar(str(ROOT / ('Hip Hop Mixamo.fbx' if '--mixamo' in sys.argv else 'Hip Hop Andrejs.fbx')))
prepare_preview(handle)
output = ROOT / 'artifacts' / 'motion'
output.mkdir(parents=True, exist_ok=True)
report = {}
build_pose_transition(handle, update_pose(None, {'root_pitch': -90, 'pelvis_drop': .48}, 'none'))
report['direct'] = review_existing(handle).to_dict()
plan = lying_down_plan()
try:
    result = build_action(handle, plan)
except PlanError as exc:
    print('CANDIDATE_REVIEW', json.dumps(getattr(exc, 'review', {})), flush=True)
    raise
report['staged'] = result
assert result['review']['passed'], result
assert result['stages'] == 4
assert result['review']['metrics']['contact_error_m'] < .025
assert result['review']['metrics']['floor_penetration_m'] < .003
assert len(handle.rig.animation_data.action.layers) > 0
print('STAGED_MOTION_PASSED', json.dumps(result), flush=True)
if '--render' in sys.argv:
    # Review the route, not just its final posture.
    from avatar_app.motion import schedule
    for stage, start, end in schedule(plan):
        handle.scene.frame_set(round(end * plan.fps) + 1)
        handle.scene.render.resolution_percentage = 60
        handle.scene.render.filepath = str(output / (stage.id + '.png'))
        bpy.ops.render.render(write_still=True)

before = handle.rig.animation_data.action
handle.scene.frame_set(handle.scene.frame_end)
timeline = handle.scene.frame_start, handle.scene.frame_end, handle.scene.frame_current
basis = {b.name: b.matrix_basis.copy() for b in handle.rig.pose.bones}
bad = ActionPlan((movement('impossible', 'Unreachable hand contact', {'torso': 'forward:10'}, 1,
                         [ContactConstraint('right_hand', position=(1, 1))]),))
try:
    build_action(handle, bad)
    raise AssertionError('Unreachable candidate accepted')
except (PlanError, ValueError):
    assert handle.rig.animation_data.action == before
    assert (handle.scene.frame_start, handle.scene.frame_end, handle.scene.frame_current) == timeline
    for bone in handle.rig.pose.bones:
        assert max(abs(v) for row in (bone.matrix_basis - basis[bone.name]) for v in row) < 1e-5
print('MOTION_ROLLBACK_PASSED', flush=True)

# A resolved seat surface can be provided by the application; the AI cannot invent one.
for height in (.38, .52):
    seat_result = build_action(handle, sitting_plan(height))
    clearances = []
    for frame in range(handle.scene.frame_start, handle.scene.frame_end + 1):
        handle.scene.frame_set(frame)
        clearances.append((handle.rig.matrix_world @ handle.bones['Hips'].head).z - height)
    handle.scene.frame_set(handle.scene.frame_end)
    pelvis = handle.rig.matrix_world @ handle.bones['Hips'].head
    world_height = (handle.rig.matrix_world.to_3x3() @ (handle.up * handle.height)).length
    assert abs(pelvis.z - (height + .06 * world_height)) < .025, (height, pelvis.z)
    assert min(clearances) >= 0, 'Pelvis anchor penetrated the seat plane'
    seat_result['seat_metrics'] = {'minimum_pelvis_clearance_m': min(clearances),
                                   'final_pelvis_to_seat_distance_m': pelvis.z - height}
    report[f'seat_{height}'] = seat_result
    print('SEAT_CONTACT_PASSED', height, pelvis.z, flush=True)
    if '--render' in sys.argv:
        center = handle.rig.matrix_world @ handle.bones['Hips'].head
        bpy.ops.mesh.primitive_cube_add(size=1, location=(center.x, center.y, height - .04))
        seat = bpy.context.object
        seat.name = 'Seat verification surface'
        seat.scale = (.5, .4, .08)
        handle.scene.render.filepath = str(output / f'seat-{height:g}.png')
        bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(seat, do_unlink=True)

(output / ('review-mixamo.json' if '--mixamo' in sys.argv else 'review.json')).write_text(
    json.dumps(report, indent=2), encoding='utf-8')
print('ALL_MOTION_CHECKS_PASSED', flush=True)
