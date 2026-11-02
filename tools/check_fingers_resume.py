"""Two read-only strict resume passes with protected payload hash/mtime proof."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from finger_cases import cases
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.fingers_provenance import producer_valid
from tools.fingers_runtime import validate as validate_runtime
from tools.fingers_native_cache import verified_native_cache
OUT=ROOT/'artifacts/stages/05.3b'


def collect():
    validate_runtime()
    paths=set();movies=0
    for name,_,_,_ in cases():
        out=OUT/'mixamo'/name;manifest,asset,motion=validate_manifest(out)
        assert producer_valid(out)
        assert verified_native_cache(out)
        assert store.render_complete(out,tuple(manifest['views']))
        assert all(v.get('renderer_sha256')==store.digest(ROOT/'tools/render_fingers.py') and v.get('visibility_check',{}).get('passed') for k,v in manifest['views'].items() if k not in ('front','side'))
        paths.update((asset,motion));paths.update(out/v['media']['path'] for v in manifest['views'].values());movies+=len(manifest['views'])
    # All immutable shared assets, including those not used by this stage.
    paths.update((ROOT/'artifacts/assets').glob('*/avatar.blend'))
    return {str(p.relative_to(ROOT)):{'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns,'sha256':store.digest(p)} for p in sorted(paths)},movies


before,movies=collect();repeats=[]
for _ in range(2):
    current,n=collect();assert before==current and n==movies
    repeats.append({'same_hashes_mtimes_counts':True,'payloads':len(current)})
store.atomic_json(OUT/'resume-no-growth.json',{'passed':True,'repeats':repeats,'movies':movies,'payloads':before,
    'bytes':sum(x['bytes'] for x in before.values()),'newly_executed_motion_or_render':False})
print('FINGERS_RESUME_NO_GROWTH_PASSED',len(before),movies,flush=True)
