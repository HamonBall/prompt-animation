"""Verify retargeting on a supplied dance asset; this is not a sitting-clip test."""
from pathlib import Path
import json
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar_app.blender.avatar import import_avatar, discard_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender.clips import build_clip
from avatar_app.clips import ClipRecord

source = import_avatar(str(ROOT / 'Hip Hop Mixamo.fbx'), import_motion=True)
assert len(source.source_actions) == 1, [a.name for a in source.source_actions]
low, high = source.source_actions[0].frame_range
print('SOURCE_CLIP_RANGE', low, high, flush=True)
discard_avatar(source)
handle = import_avatar(str(ROOT / 'Hip Hop Andrejs.fbx'))
prepare_preview(handle)
materials = {o.name: tuple(slot.material for slot in o.material_slots)
             for o in handle.objects if o.type == 'MESH'}
record = ClipRecord('supplied-dance', str(ROOT / 'Hip Hop Mixamo.fbx'), ('dance',),
                    'standing', 'standing', 'Mixamo', 'User-supplied local test asset',
                    low, min(high, low + 24))
result = build_clip(handle, record, duration=2)
assert result['review']['passed'], result
assert result['review']['metrics']['joint_speed_deg_s'] > 1, 'Retargeted animation was static'
assert result['frames'] == 61
for o in handle.objects:
    if o.type == 'MESH':
        assert tuple(slot.material for slot in o.material_slots) == materials[o.name]
assert len(bpy.data.scenes) == 2  # factory scene and the target preview; source cleaned up
out = ROOT / 'artifacts' / 'clips'
out.mkdir(parents=True, exist_ok=True)
(out / 'test-review.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print('CLIP_RETARGET_CHECKS_PASSED', json.dumps(result), flush=True)
