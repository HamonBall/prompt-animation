"""Read-only local anatomy inspection; no reconstruction or downloads."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar,discard_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender import rig_profile as rp
from tools.artifact_store import atomic_json
rows={}
for name in ('demo','mixamo'):
    h=create_demo_avatar() if name=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'))
    p=rp.calibrate_joint_frames(h,avatar_id='fingers.'+name,recorded_at='2026-11-02',include_head_aim=True)
    rows[name]={'capabilities':rp.inspect_capabilities(h).__dict__,'fingers':[
        {'id':j.semantic_id,'bone':j.source_bones[0],'parent':j.parent_id,
         'length':next(x.value_m for x in p.lengths if x.id==j.semantic_id)}
        for j in p.rest_to_semantic_mappings if '.finger.' in j.semantic_id]}
    discard_avatar(h)
atomic_json(ROOT/'artifacts/stages/05.3b/rig-inspection.json',rows)
print('FINGER_RIG_INSPECTION',[(k,len(v['fingers'])) for k,v in rows.items()],flush=True)
