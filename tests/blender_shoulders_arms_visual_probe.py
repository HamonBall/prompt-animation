"""Early saved-motion visual inspection of a critical case, in owned scratch."""
from pathlib import Path
import json
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tools.artifact_store import open_preview,hold_producer_lease,atomic_json,digest
from tools.storage_policy import confined,enforce
from tools.movement_evidence import render
from avatar_app.movement_library import contracts as c

rig=sys.argv[sys.argv.index('--rig')+1];name=sys.argv[sys.argv.index('--case')+1]
assert rig in ('demo','mixamo') and '/' not in name and '\\' not in name
base=ROOT/'artifacts/stages/05.2';source=confined(base/rig/name)
out=confined(base/'.scratch'/('visual-probe-'+rig+'-'+name))
assert not out.exists(),'Inspect/reconcile the existing probe before repeating it'
enforce(out,growth=16*1024**2,temporary=32*1024**2)
out.mkdir(parents=True);hold_producer_lease(out)
record={'owner':'stage-05.2-visual-probe-v1','source_case':rig+'/'+name,'state':'rendering',
        'source_motion_sha256':digest(source/'motion.blend'),'source_result_sha256':digest(source/'result.json')}
atomic_json(out/'probe.json',record)
shutil.copy2(source/'result.json',out/'result.json')
h=open_preview(source);profile=c.loads(c.AvatarProfile,(source.parent/'profile.json').read_text())
render(h,profile,out);render(h,profile,out,True)
assert digest(source/'motion.blend')==record['source_motion_sha256']
assert digest(source/'result.json')==record['source_result_sha256']
record.update({'state':'ready_for_inspection','frames_per_view':h.scene.frame_end,
    'files':{p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':digest(p)}
             for p in out.rglob('*') if p.is_file() and p.name not in ('probe.json','.artifact-writer.lock')}})
atomic_json(out/'probe.json',record)
print('SAVED_MOTION_VISUAL_PROBE_READY',out,flush=True)
