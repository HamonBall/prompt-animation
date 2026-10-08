"""End-to-end checks using actual FBX imports and Blender's dependency graph."""
from pathlib import Path
from contextlib import redirect_stdout
import io
import sys
import time
import json
import unittest
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))
from avatar_app.blender.avatar import import_avatar, discard_avatar
from avatar_app.blender.animation import build_transition
from avatar_app.blender.scene import prepare_preview
from avatar_app.planning.interpreter import interpret
from avatar_app.models import MotionPlan
import test_planning

suite = unittest.defaultTestLoader.loadTestsFromModule(test_planning)
assert unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()

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
    plan = interpret('T-rex pose')
    initial = build_transition(handle, plan)
    before_action = handle.rig.animation_data.action
    handle.scene.frame_set(handle.scene.frame_end)
    before_height = handle.bones['Hips'].head.dot(handle.up)
    feet_before = {side: handle.bones[side + 'Foot'].head.copy() for side in ('Left', 'Right')}
    changed = interpret('crouch lower', plan)
    correction = build_transition(handle, changed)
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
        build_transition(handle, changed, interrupt_build)
        raise AssertionError('Expected injected failure')
    except RuntimeError:
        assert handle.rig.animation_data.action == good_action
    try:
        build_transition(handle, MotionPlan(crouch=0.9))
        raise AssertionError('Invalid plan was accepted')
    except ValueError:
        assert handle.rig.animation_data.action == good_action
    # Every local transform must remain finite, and scaling is preserved.
    import math
    for bone in handle.rig.pose.bones:
        assert all(math.isfinite(x) for row in bone.matrix for x in row)
        assert max(abs(v - 1) for v in bone.scale) < 0.001
    print('VERIFIED ' + json.dumps({'avatar': filename, 'initial': initial,
                                    'correction': correction,
                                    'elapsed_seconds': time.perf_counter() - started}))
    if filename == 'Hip Hop Andrejs.fbx' and '--no-render' not in sys.argv:
        output = ROOT / 'artifacts'
        output.mkdir(exist_ok=True)
        handle.scene.render.filepath = str(output / 'trex-preview.png')
        handle.scene.render.resolution_percentage = 60
        bpy.ops.render.render(write_still=True)
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
print('ALL_CHECKS_PASSED')
