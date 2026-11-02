"""Fresh native read-only playback after a diagnosed post-render driver crash."""
import sys,json
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from avatar_app.movement_library import contracts as c
from avatar_app.blender import rig_profile as rp
OUT=ROOT/'artifacts/stages/05.3b';name=sys.argv[sys.argv.index('--case')+1];out=OUT/'mixamo'/name
manifest,asset,motion=validate_manifest(out);assert store.render_complete(out,tuple(manifest['views']))
assert all(v.get('renderer_sha256')==store.digest(ROOT/'tools/render_fingers.py') and v['visibility_check']['passed'] for k,v in manifest['views'].items() if k not in ('front','side'))
paths=[asset,motion,*(out/v['media']['path'] for v in manifest['views'].values())]
def identity():return {str(path.relative_to(ROOT)):{'sha256':store.digest(path),'mtime_ns':path.stat().st_mtime_ns,'bytes':path.stat().st_size} for path in paths}
before=identity();h=store.open_preview(out);p=c.loads(c.AvatarProfile,(out.parent/'profile.json').read_text())
r=json.loads((out/'result.json').read_text());entry=c.loads(c.MotionStateSnapshot,(out/'entry.json').read_text());maximum=0
for sample in r['samples']:
    h.scene.frame_set(sample['frame']);state=rp.capture_motion_state(h,p,revision=entry.revision,captured_time_s=sample['time_s'])
    actual={x.control_id:x.value for x in state.measured_controls}
    for key in sample['targets']:
        error=abs(actual[key]-sample['measured'][key]);maximum=max(maximum,error);assert error<.001,(sample['frame'],key,error)
assert before==identity()
store.atomic_json(OUT/('cached-playback-'+name+'.json'),{'passed':True,'case':name,'frames':len(r['samples']),'maximum_saved_angle_residual_deg':maximum,
    'runtime':{'version':bpy.app.version_string,'build':bpy.app.build_hash.decode()},'payloads':before,'motion_or_media_regenerated':False})
print('FINGERS_FRESH_CACHED_PLAYBACK_PASSED',name,maximum,flush=True)
