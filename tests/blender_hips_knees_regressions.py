"""Known-sign leg probes and prior profile mechanics comparisons on both rigs."""
import sys,math
from pathlib import Path
import bpy
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar,discard_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.hands import with_hands_v1
from avatar_app.movement_library.legs import with_legs_v1
from avatar_app.movement_library.joints import catalog_for_profile,_fragment
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment,value_error
from avatar_app.motion import Surface
from blender_movement_hips_knees import fixture
from tools.artifact_store import atomic_json,input_identity,digest
from tools.preview_movement import load_entry,capture_entry
OUT=ROOT/'artifacts/stages/05.4';report={};producer=input_identity(OUT)['producer_sha256']
for rig in ('demo','mixamo'):
    h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
    old=with_hands_v1(rp.calibrate_joint_frames(h,avatar_id='leg-regression.'+rig,recorded_at='2026-11-02',include_head_aim=True));new=with_legs_v1(old)
    world=h.rig.matrix_world.copy();comparisons={}
    for id,params in (('head.nod',{}),('arm.raise',{'angle':10}),('elbow.flex',{}),('wrist.circle',{}),('hand.trace',{'path':'line','distance_m':.01})):
        runs=[]
        for p in (old,new):
            h.rig.animation_data_clear();h.rig.matrix_world=world.copy();entry=fixture(h,p,'neutral','left');cat=catalog_for_profile(p)
            if id=='hand.trace':
                load_entry(h,ROOT/'tests/fixtures/elbows_wrists_hands/v1/entry-chest.json');entry=capture_entry(h,p)
            i=instantiate_movement(id,params,instance_id='prior.1',profile=p,entry_state=entry,catalog=cat)
            f=build_fragment(i,entry,p,(Surface(),),cat);r=build_action(h,prepare_fragment(f,entry,p),profile=p);assert r['review']['passed'];runs.append(r)
        assert runs[0]['frames']==runs[1]['frames'];maximum=0
        shapes={v.id:v.value_shape for v in old.controls}
        for a,b in zip(runs[0]['samples'],runs[1]['samples']):
            for key,x in a['measured'].items():
                if key.endswith('.knee.flexion'):continue  # Explicit versioned geometric correction.
                y=b['measured'][key];x=tuple(x) if isinstance(x,list) else x;y=tuple(y) if isinstance(y,list) else y
                error=value_error(x,y,shapes[key]);maximum=max(maximum,error);assert error<.001,(rig,id,key,error)
        comparisons[id]={'passed':True,'max_error':maximum,'frames':runs[0]['frames'],'executions':2}
    probes=[]
    for pose in ('raised','raised-turned'):
        for side in ('left','right'):
            for suffix in ('hip.flexion','hip.abduction','hip.rotation','knee.flexion'):
                for delta in (-5,5):
                    h.rig.animation_data_clear();h.rig.matrix_world=world.copy();entry=fixture(h,new,pose,side)
                    values={v.control_id:v.value for v in entry.measured_controls};key=side+'.'+suffix;target=values[key]+delta
                    cat=catalog_for_profile(new);i=instantiate_movement('knee.lift',{'side':side},instance_id='sign.1',profile=new,entry_state=entry,catalog=cat)
                    f=_fragment(i,entry,new,{key:[(0,.5,values[key],target,None)]},.5,(c.PhaseLandmark('end',.5),))
                    r=build_action(h,prepare_fragment(f,entry,new),profile=new);assert r['review']['passed']
                    actual=r['samples'][-1]['measured'][key];error=abs(actual-target);assert error<.01
                    probes.append({'pose':pose,'side':side,'control':key,'delta_deg':delta,'actual_delta_deg':actual-values[key],'error_deg':error})
    report[rig]={'passed':True,'profile_comparisons':comparisons,'known_sign_probes':probes,
        'maximum_known_sign_error_deg':max(x['error_deg'] for x in probes)}
    atomic_json(OUT/'regression-review.json',report);discard_avatar(h)
assert input_identity(OUT)['producer_sha256']==producer
print('LEGS_PRIOR_PROFILE_AND_SIGN_PROBES_PASSED',[(rig,x['maximum_known_sign_error_deg']) for rig,x in report.items()],flush=True)
