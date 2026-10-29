"""Blender CLI for an explicit catalog clip (not an automatic asset download)."""
from pathlib import Path
import argparse
import json
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT / 'src'),str(ROOT)]
from tools.artifact_store import save_scene,hold_producer_lease
from avatar_app.clips import load_catalog
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender.clips import build_clip

parser = argparse.ArgumentParser()
parser.add_argument('--catalog', required=True)
parser.add_argument('--clip', required=True)
parser.add_argument('--avatar', default=str(ROOT / 'Hip Hop Andrejs.fbx'))
parser.add_argument('--duration', type=float)
parser.add_argument('--pelvis-height', type=float)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
records = load_catalog(args.catalog)
record = next((c for c in records if c.id == args.clip), None)
if record is None:
    raise SystemExit('Clip ID not found in catalog.')
handle = import_avatar(args.avatar)
prepare_preview(handle)
out = ROOT / 'artifacts' / 'clips'
out.mkdir(parents=True, exist_ok=True)
hold_producer_lease(out)
from tools.storage_policy import measured_preflight
import math
measured_preflight(out,[('.',math.ceil((args.duration or 10)*30)+1,0)],reference=ROOT/'artifacts/stages/05.1b')
try:
    result = build_clip(handle, record, args.duration, args.pelvis_height)
    (out / 'retarget-review.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    save_scene(out / 'adapted.blend')
    print('CLIP_ADAPTED', json.dumps(result))
except Exception as exc:
    (out / 'retarget-review.json').write_text(json.dumps(
        {'error': str(exc), 'review': getattr(exc, 'review', None)}, indent=2), encoding='utf-8')
    raise
