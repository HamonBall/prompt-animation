"""Measured neutral-entry fold target trials; no scenes or motion files retained."""
from pathlib import Path
import sys
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.limbs import with_shoulders_v1,shoulder_position
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment
from avatar_app.movement_library.spatial import rotate
from avatar_app.motion import Surface
from tools.preview_movement import load_entry,capture_entry
from tools.artifact_store import atomic_json

h=import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
p=with_shoulders_v1(rp.calibrate_joint_frames(h,avatar_id='fold.probe',include_head_aim=True,recorded_at='2026-10-28'))
catalog=catalog_for_profile(p);report={}
for lateral,forward in ((.04,.17),(.04,.20),(.06,.20),(.08,.20),(.04,.23)):
    h.rig.animation_data_clear()
    load_entry(h,ROOT/'tests/fixtures/movement_fragments/v1/entry-neutral.json');entry=capture_entry(h,p)
    values={v.control_id:v.value for v in entry.measured_controls}
    left=shoulder_position(values,p,'left');right=shoulder_position(values,p,'right');center=tuple((a+b)/2 for a,b in zip(left,right))
    offset=rotate(entry.root_transform.orientation,(-lateral*p.height_m,forward*p.height_m,-.06*p.height_m))
    target=tuple(a+b for a,b in zip(center,offset))
    i=instantiate_movement('arm.fold',{'target':target},instance_id='probe.1',profile=p,entry_state=entry,catalog=catalog)
    motion=prepare_fragment(build_fragment(i,entry,p,(Surface(),),catalog),entry,p)
    try:
        result=build_action(h,motion,profile=p)
        record={'passed':True,'min_clearance_m':min(v for s in result['samples'] for v in s['arm_clearance_m'].values()),'review':result['review']}
    except Exception as error:
        record={'passed':False,'review':getattr(error,'review',None),'error':str(error),'details':error.to_dict() if hasattr(error,'to_dict') else None}
    report[str((lateral,forward))]=record
    atomic_json(ROOT/'artifacts/stages/05.2/fold-neutral-diagnostic.json',report)
    print('FOLD_NEUTRAL_TRIAL',lateral,forward,record['passed'],record.get('min_clearance_m',record.get('error')),flush=True)
