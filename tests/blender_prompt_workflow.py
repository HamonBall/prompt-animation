"""Exercise real foreground Blender modal generation, playback and cancellation."""
import json
from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch
import bpy

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'src/avatar_app/main.py').is_file())
sys.path.insert(0, str(ROOT/'src'))
from avatar_app import main as app
from avatar_app.motion import ActionPlan

phase_name = sys.argv[sys.argv.index('--')+1] if '--' in sys.argv else 'before'
output = ROOT/'artifacts'/'stages'/'01'
output.mkdir(parents=True, exist_ok=True)
assert not bpy.app.background, 'This harness requires the actual Blender UI event loop'
original_scene = bpy.context.scene
original_objects = set(original_scene.objects)
with patch.object(app, '_default_avatar', return_value=ROOT/'absent.fbx'):
    app.main()
scene = bpy.context.scene
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
data = {'background': bpy.app.background, 'blender': bpy.app.version_string,
        'phase': phase_name, 'checks': [], 'samples': []}
state = {'phase': 'generate', 'started': time.monotonic()}


def finish(error=None):
    data.update(passed=error is None, error=error, seconds=time.monotonic()-state['started'])
    (output/(phase_name+'-prompt-workflow.json')).write_text(json.dumps(data, indent=2), encoding='utf-8')
    print('PROMPT_WORKFLOW_PASSED' if error is None else 'PROMPT_WORKFLOW_FAILED', phase_name, error or '', flush=True)
    bpy.ops.wm.quit_blender()


def tick():
    try:
        if time.monotonic()-state['started'] > 90:
            raise AssertionError('UI workflow exceeded 90 seconds')
        with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region):
            if state['phase'] == 'generate':
                scene.avatar_prompt = 'wave with your left hand'
                assert bpy.ops.avatar.prompt() == {'RUNNING_MODAL'}
                assert app._state['busy']
                data['checks'].append('prompt uses modal worker')
                state['phase'] = 'await_generation'
            elif state['phase'] == 'await_generation':
                if app._state['busy']: return .1
                assert not app._state['last_error'], scene.avatar_status
                assert isinstance(app._state['plan'], ActionPlan)
                assert app._state['plan'].description == 'Wave left hand 3 times'
                assert not hasattr(bpy.types.Scene, 'avatar_preset')
                assert set(original_scene.objects) == original_objects
                data['checks'].append('prompt result and original scene preserved')
                for frame in range(scene.frame_start, scene.frame_end+1):
                    scene.frame_set(frame)
                    data['samples'].append({'frame':frame,
                        'head':list(app._state['avatar'].rig.matrix_world @ app._state['avatar'].bones['Head'].head),
                        'left_hand':list(app._state['avatar'].rig.matrix_world @ app._state['avatar'].bones['LeftHand'].head),
                        'left_foot':list(app._state['avatar'].rig.matrix_world @ app._state['avatar'].bones['LeftFoot'].head)})
                assert bpy.ops.avatar.play() == {'RUNNING_MODAL'}
                assert window.screen.is_animation_playing
                data['checks'].append('play starts real screen animation')
                state['phase'] = 'await_playback'
            elif state['phase'] == 'await_playback':
                if window.screen.is_animation_playing: return .1
                assert scene.frame_current == scene.frame_end
                data['checks'].append('play once stops at final frame')
                state.update(old_action=app._state['avatar'].rig.animation_data.action,
                             old_plan=app._state['plan'], old_frame=scene.frame_current,
                             history=len(app._state['history']))
                scene.avatar_prompt = 'jump'
                assert bpy.ops.avatar.prompt() == {'RUNNING_MODAL'}
                state['phase'] = 'request_cancel'
            elif state['phase'] == 'request_cancel':
                assert app._state['busy'], 'Generation finished before cancellation'
                assert bpy.ops.avatar.cancel() == {'FINISHED'}
                state['phase'] = 'await_cancel'
            elif state['phase'] == 'await_cancel':
                if app._state['busy']: return .1
                assert app._state['plan'] is state['old_plan']
                assert app._state['avatar'].rig.animation_data.action == state['old_action']
                assert scene.frame_current == state['old_frame']
                assert len(app._state['history']) == state['history']
                data['checks'].append('cancel preserves previous motion, frame and history')
                finish()
                return None
        return .1
    except Exception:
        finish(traceback.format_exc())
        return None


bpy.app.timers.register(tick, first_interval=.5)
