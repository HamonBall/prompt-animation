"""Execute the real benchmark reply; verify its endpoint and timeline separately."""
from pathlib import Path
import json
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender.motion import build_action
from avatar_app.planning.action_interpreter import decode_action
from avatar_app.models import PlanError

out = ROOT / 'artifacts' / 'motion'
data = json.loads((out / 'ai-plan.json').read_text(encoding='utf-8'))
assert data['stages_generated']
assert data['reference_comparison']['lying_endpoint'], 'Model missed the requested destination'
assert data['reference_comparison']['legs_extended_along_body']
plan, _ = decode_action(data['raw'])
handle = import_avatar(str(ROOT / 'Hip Hop Andrejs.fbx'))
prepare_preview(handle)
try:
    result = build_action(handle, plan)
    handle.scene.frame_set(handle.scene.frame_end)
    head = handle.rig.matrix_world @ handle.bones['Head'].head
    hips = handle.rig.matrix_world @ handle.bones['Hips'].head
    assert abs(head.z - hips.z) < .15, 'Final body was not horizontal'
    (out / 'ai-execution.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if '--render' in sys.argv:
        handle.scene.render.resolution_percentage = 60
        handle.scene.render.filepath = str(out / 'ai-endpoint.png')
        bpy.ops.render.render(write_still=True)
    print('REAL_AI_ACTION_EXECUTED', json.dumps(result), flush=True)
except Exception as exc:
    (out / 'ai-execution.json').write_text(json.dumps(
        {'error': str(exc), 'review': getattr(exc, 'review', None)}, indent=2), encoding='utf-8')
    raise
