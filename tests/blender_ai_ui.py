"""Exercise UI result handoff without reading personal assets or problems/."""
from pathlib import Path
import sys
import time
import queue
from types import SimpleNamespace
from unittest.mock import patch
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from avatar_app import main as app
from avatar_app.models import PlanError
from avatar_app.pose import update_pose

app.main()
avatar = SimpleNamespace(scene=bpy.context.scene)
original = update_pose(None, {'right_arm_elevation': 90})
candidate = update_pose(original, {'head_yaw': 30})
app._state.update(avatar=avatar, plan=original)
with patch.object(app, 'build_transition', return_value={'frames': 61}) as build:
    app.apply_candidate(bpy.context, candidate, 'Test checked patch', time.perf_counter(), avatar, original)
    assert app._state['plan'] is candidate
    assert build.call_count == 1
    try:
        app.apply_candidate(bpy.context, original, '', time.perf_counter(), avatar, original)
        raise AssertionError('Stale result was accepted')
    except PlanError:
        assert build.call_count == 1

before_history = list(app._state['history'])
with patch.object(app, 'build_transition', side_effect=RuntimeError('Injected backend failure')):
    try:
        app.apply_candidate(bpy.context, original, '', time.perf_counter(), avatar, candidate)
        raise AssertionError('Expected backend failure')
    except RuntimeError:
        assert app._state['plan'] is candidate
        assert app._state['history'] == before_history

bpy.context.scene.avatar_prompt = 'neutral pose'
with patch.object(app, 'build_transition', return_value={'frames': 61}):
    assert bpy.ops.avatar.prompt() == {'FINISHED'}
    assert app._state['plan'].values == ()
assert bpy.types.AVATAR_OT_cancel is not None

# A completed result already in the queue must be discarded if canceled first.
app._state['busy'] = True
app._state['cancel_requested'] = True
pending = queue.Queue()
pending.put((True, (original, 'Late result')))
finished = []
fake_operator = SimpleNamespace(_scene=bpy.context.scene, _avatar=avatar,
                                _results=pending, finish=lambda context: finished.append(True))
with patch.object(app, 'apply_candidate') as commit:
    status = app.AVATAR_OT_prompt.modal(fake_operator, bpy.context, SimpleNamespace(type='TIMER'))
    assert status == {'CANCELLED'}
    assert not commit.called
    assert finished
app._state.update(busy=False, cancel_requested=False)
print('BLENDER_AI_HANDOFF_CHECKS_PASSED')
