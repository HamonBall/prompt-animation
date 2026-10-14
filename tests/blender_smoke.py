"""General pose/action smoke checks with actual imported avatars and rollback."""
from pathlib import Path
from contextlib import redirect_stdout
import io
import sys
import time
import json
import importlib
import pkgutil
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import avatar_app
from avatar_app.blender.avatar import import_avatar, discard_avatar
from avatar_app.blender.pose import build_pose_transition
from avatar_app.blender.motion import build_action
from avatar_app.blender.scene import prepare_preview
from avatar_app.pose import update_pose
from avatar_app.planning.action_interpreter import interpret_action
from avatar_app.planning.presets import preset_plan
from avatar_app.models import PlanError

for module in pkgutil.walk_packages(avatar_app.__path__, avatar_app.__name__+'.'):
    importlib.import_module(module.name)
print('ALL_ACTIVE_MODULE_IMPORTS_PASSED', flush=True)
output = ROOT/'artifacts'/'stages'/'01'
output.mkdir(parents=True, exist_ok=True)
reports = {}


class CompoundModel:
    def complete(self, messages, schema):
        return json.dumps({'kind':'action', 'base':None, 'stages':[
            {'id':'reach', 'targets':{'left_arm':'out:110', 'right_arm':'out:70'},
             'duration':1.5, 'contacts':[{'part':'left_foot'},{'part':'right_foot'}]},
            {'id':'look', 'targets':{'head':'left:25', 'torso':'forward:10'},
             'duration':1.5, 'contacts':[{'part':'left_foot'},{'part':'right_foot'}]}],
            'changes':{}, 'contact':None, 'factor':None, 'message':'Reach diagonally and look left.'})

original_scene = bpy.context.scene
original_objects = set(original_scene.objects)
for filename in ('Hip Hop Andrejs.fbx', 'Hip Hop Mixamo.fbx'):
    started = time.perf_counter()
    import_output = io.StringIO()
    with redirect_stdout(import_output):
        handle = import_avatar(str(ROOT / filename))
    assert "User property type 'Short' is not supported" not in import_output.getvalue(), import_output.getvalue()
    material_ids = {obj.name: tuple(slot.material for slot in obj.material_slots)
                    for obj in handle.objects if obj.type == 'MESH'}
    prepare_preview(handle)
    world_head = handle.rig.matrix_world @ handle.bones['Head'].head
    world_foot = handle.rig.matrix_world @ handle.bones['LeftFoot'].head
    assert world_head.z - world_foot.z > 1.0, 'Avatar was not oriented upright'
    plan = update_pose(None, {'pelvis_drop':.08, 'right_arm_elevation':45}, 'both')
    initial = build_pose_transition(handle, plan)
    handle.scene.frame_set(handle.scene.frame_end)
    before_height = handle.bones['Hips'].head.dot(handle.up)
    feet_before = {side: handle.bones[side + 'Foot'].head.copy() for side in ('Left', 'Right')}
    changed = update_pose(plan, {'pelvis_drop':.11})
    correction = build_pose_transition(handle, changed)
    handle.scene.frame_set(handle.scene.frame_end)
    assert handle.bones['Hips'].head.dot(handle.up) < before_height
    for side in feet_before:
        assert (handle.bones[side + 'Foot'].head - feet_before[side]).length < 0.002 * handle.height
    assert correction['contact_error'] < 0.002 * handle.height, correction
    for obj in handle.objects:
        if obj.type == 'MESH':
            assert tuple(slot.material for slot in obj.material_slots) == material_ids[obj.name]
    good_action = handle.rig.animation_data.action
    def interrupt_build(value):
        if value > 0.4:
            raise RuntimeError('Injected build failure')
    try:
        build_pose_transition(handle, changed, interrupt_build)
        raise AssertionError('Expected injected failure')
    except RuntimeError:
        assert handle.rig.animation_data.action == good_action
    try:
        build_pose_transition(handle, update_pose(None, {'pelvis_drop':2}))
        raise AssertionError('Invalid plan was accepted')
    except ValueError:
        assert handle.rig.animation_data.action == good_action
    # Every local transform must remain finite, and scaling is preserved.
    import math
    for bone in handle.rig.pose.bones:
        assert all(math.isfinite(x) for row in bone.matrix for x in row)
        assert max(abs(v - 1) for v in bone.scale) < 0.001
    foundation = build_action(handle, preset_plan('wave'))
    creative, _ = interpret_action('Reach diagonally, then look over your left shoulder.', model=CompoundModel())
    compound = build_action(handle, creative)
    assert foundation['review']['passed'] and compound['review']['passed']
    good_action = handle.rig.animation_data.action
    old_frame = handle.scene.frame_current
    try:
        build_action(handle, creative, interrupt_build)
        raise AssertionError('Expected interrupted action build')
    except RuntimeError:
        assert handle.rig.animation_data.action == good_action
        assert handle.scene.frame_current == old_frame
    for obj in handle.objects:
        if obj.type == 'MESH':
            assert tuple(slot.material for slot in obj.material_slots) == material_ids[obj.name]
    reports[filename] = {'initial':initial, 'correction':correction,
                         'foundation':foundation, 'compound':compound,
                         'elapsed_seconds':time.perf_counter()-started}
    print('GENERAL_SMOKE_VERIFIED', filename, json.dumps(reports[filename]), flush=True)
    bpy.context.window.scene = original_scene
    discard_avatar(handle)
assert set(original_scene.objects) == original_objects
from avatar_app import main as app
app.main()
assert app._state['avatar'] is not None and app._state['plan'] is not None
bpy.context.scene.avatar_prompt = 'neutral pose'
assert bpy.ops.avatar.prompt() == {'FINISHED'}
assert app._state['plan'].values == ()
good_plan = app._state['plan']
good_handle = app._state['avatar']
bpy.context.scene.avatar_path = str(ROOT / 'does-not-exist.fbx')
try:
    bpy.ops.avatar.load()
except RuntimeError:
    pass  # Blender propagates an operator ERROR report as RuntimeError.
assert app._state['avatar'] is good_handle
assert app._state['plan'] == good_plan
assert bpy.context.scene == good_handle.scene
assert set(original_scene.objects) == original_objects
print('UI_STARTUP_AND_RECOVERY_PASSED')
(output/'imported-smoke.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
print('ALL_CHECKS_PASSED')
