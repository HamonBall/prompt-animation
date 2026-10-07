"""Actual local model -> checked plan -> Blender motion, using a root-level FBX."""
from pathlib import Path
import sys
import time
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar_app import main as app
from avatar_app.planning.local_model import get_model

app.main()
assert app._state['avatar'] is not None, 'Choose a root-level demo FBX before this check.'
before = app._state['plan']
rig = app._state['avatar'].rig
old_action = rig.animation_data.action.name
bpy.context.scene.avatar_prompt = 'Reach straight up with both arms.'
started = time.perf_counter()
assert bpy.ops.avatar.prompt() == {'FINISHED'}
after = app._state['plan']
assert after.get('left_arm_elevation') >= 160
assert after.get('right_arm_elevation') >= 160
assert after.duration == before.duration
assert after.revision == before.revision + 1
assert rig.animation_data.action.name != old_action
print('LIVE_AI_TO_BLENDER_PASSED', round(time.perf_counter() - started, 2),
      bpy.context.scene.avatar_status, flush=True)
get_model().close()
