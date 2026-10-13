"""The reported basic prompt must execute without AI and acquire floor support."""
from pathlib import Path
import sys
from unittest.mock import patch
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar_app import main as app
from avatar_app.blender.geometry import support_skin_height
from avatar_app.motion import ActionPlan, Surface

app.main()
handle = app._state['avatar']
assert any(s.name == 'seat' for s in handle.surfaces)
with patch('avatar_app.planning.action_interpreter.get_model', side_effect=AssertionError('Slow inference')):
    app.generate(bpy.context, 'sit on the ground')
plan = app._state['plan']
assert isinstance(plan, ActionPlan) and len(plan.stages) == 2
handle.scene.frame_set(handle.scene.frame_end)
assert abs(support_skin_height(handle, 'pelvis', Surface())) < .025
assert abs(plan.final_pose.get('root_pitch')) < 1
assert not any(s.name == 'seat' for s in handle.surfaces)
assert not handle.scene.avatar_show_seat
assert not app._state['experimental']
print('GROUND_SITTING_PROMPT_EXECUTED_WITH_FLOOR_SUPPORT', flush=True)
