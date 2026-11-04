"""Bounded diagnostic phase probes; no baking, media or final case cache claims."""
from pathlib import Path
import sys,time,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.primitive import FragmentAdapter
from avatar_app.blender.leg_mechanics import apply as apply_legs,clearance
from avatar_app.blender.motion import capture_sample
from avatar_app.movement_library.legs import with_legs_v1
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment,value_error
from avatar_app.motion import Surface
from blender_movement_hips_knees import fixture
from hips_knees_cases import cases
from tools.artifact_store import atomic_json,digest,input_identity
OUT=ROOT/'artifacts/stages/05.4'
rig=sys.argv[sys.argv.index('--rig')+1];started=time.perf_counter()
h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
p=with_legs_v1(rp.calibrate_joint_frames(h,avatar_id='probes.'+rig,recorded_at='2026-11-02',include_head_aim=True));catalog=catalog_for_profile(p)
world=h.rig.matrix_world.copy();report={'rig':rig,'purpose':'Diagnostic phase-only native probes; not full-motion execution or acceptance','cases':{}}
source=input_identity(OUT)['producer_sha256']
for name,id,params,pose in cases():
    h.rig.matrix_world=world.copy();entry=fixture(h,p,pose,params.get('side','left'))
    try:
        i=instantiate_movement(id,params,instance_id='probe.1',profile=p,entry_state=entry,catalog=catalog)
        f=build_fragment(i,entry,p,(Surface(),),catalog);x=prepare_fragment(f,entry,p)
        times=sorted({0,x.duration_s,*[t.interval.end_s for t in x.tracks]})
        count=0
        for time_s in times:
            # Independent static application/calibration probe. Never jump the
            # execution cursor or claim this as sampler/full-motion evidence.
            h.rig.matrix_world=world.copy();fresh=fixture(h,p,pose,params.get('side','left'))
            adapter=FragmentAdapter(h,x,p);requested={}
            for track in sorted(x.tracks,key=lambda t:t.interval.start_s):
                if track.interval.end_s<=time_s+1e-9:requested[track.control_id]=track.curve.end_value
            if 'pelvis.position' in requested:adapter._pelvis(requested)
            apply_legs(adapter,requested)
            state=rp.capture_motion_state(h,p,revision=entry.revision,captured_time_s=time_s)
            actual={v.control_id:v.value for v in state.measured_controls};specs={v.id:v for v in p.controls}
            for key,target in requested.items():
                assert value_error(actual[key],target,specs[key].value_shape)<(3 if specs[key].unit=='degree' or specs[key].value_shape=='quaternion' else .01),(key,actual[key],target)
            sample=capture_sample(h,1,'static_probe',{});count+=1
            assert sample['floor']>=-.003,('floor',sample['floor'])
            assert clearance(adapter)>=-.003,('leg_clearance',clearance(adapter))
        report['cases'][name]={'passed':True,'samples':count}
        print('LEGS_PHASE_PROBE_PASSED',rig,name,count,flush=True)
    except Exception as error:
        report['cases'][name]={'passed':False,'error':error.to_dict() if hasattr(error,'to_dict') else str(error)}
        print('LEGS_PHASE_PROBE_FAILED',rig,name,report['cases'][name],flush=True)
    report['elapsed_s']=time.perf_counter()-started;atomic_json(OUT/('phase-probes-'+rig+'.json'),report)
assert input_identity(OUT)['producer_sha256']==source,'Application changed during phase probes'
report['producer_sha256']=source;report['passed']=all(v['passed'] for v in report['cases'].values());atomic_json(OUT/('phase-probes-'+rig+'.json'),report)
print('LEGS_PHASE_PROBE_COMPLETE',rig,report['passed'],report['elapsed_s'],flush=True)
