"""Targeted prior-profile mechanics and known-sign finger calibration probes."""
import sys,json
from pathlib import Path
from dataclasses import replace
import bpy
from mathutils import Quaternion,Vector
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar,discard_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.fingers import with_fingers_v1
from avatar_app.movement_library.hands import with_hands_v1
from avatar_app.movement_library.joints import catalog_for_profile,_fragment,_path
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment,value_error
from avatar_app.motion import Surface
from tools.preview_movement import load_entry,capture_entry
from tools.artifact_store import atomic_json
OUT=ROOT/'artifacts/stages/05.3b';report={}
for rig in ('demo','mixamo'):
    h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
    old=with_hands_v1(rp.calibrate_joint_frames(h,avatar_id='regressions.'+rig,recorded_at='2026-11-02',include_head_aim=True));new=with_fingers_v1(old)
    results={}
    for id,parameters in (('elbow.flex',{}),('forearm.twist',{}),('wrist.circle',{}),('hand.trace',{'path':'circle'})):
        runs=[]
        for p in (old,new):
            h.rig.animation_data_clear()
            for b in h.rig.pose.bones:b.matrix_basis.identity()
            load_entry(h,ROOT/'tests/fixtures/shoulders_arms/v1/entry-shoulders-bent.json');entry=capture_entry(h,p)
            catalog=catalog_for_profile(p);i=instantiate_movement(id,parameters,instance_id='regression.1',profile=p,entry_state=entry,catalog=catalog)
            f=build_fragment(i,entry,p,(Surface(),),catalog);runs.append(build_action(h,prepare_fragment(f,entry,p),profile=p))
        maximum=0
        assert len(runs[0]['samples'])==len(runs[1]['samples'])
        for a,b in zip(runs[0]['samples'],runs[1]['samples']):
            for key,actual in a['measured'].items():
                spec=next(x for x in old.controls if x.id==key);expected=b['measured'][key]
                if isinstance(actual,list):actual=tuple(actual);expected=tuple(expected)
                maximum=max(maximum,value_error(actual,expected,spec.value_shape))
        assert maximum<.01,(rig,id,maximum)
        results[id]={'profile5_vs_profile6_maximum_numeric_residual':maximum,'samples':len(runs[0]['samples']),'both_reviews_passed':True}
    if rig=='mixamo':
        probes={};p=new
        for pose in ('neutral','bent-turned'):
            for suffix in ('curl','spread'):
                for sign in (-1,1):
                    h.rig.animation_data_clear()
                    for b in h.rig.pose.bones:b.matrix_basis.identity()
                    load_entry(h,ROOT/('tests/fixtures/movement_fragments/v1/entry-neutral.json' if pose=='neutral' else 'tests/fixtures/shoulders_arms/v1/entry-shoulders-bent.json'))
                    entry=capture_entry(h,p);values={x.control_id:x.value for x in entry.measured_controls}
                    catalog=catalog_for_profile(p);i=instantiate_movement('finger.curl_spread',{'side':'both'},instance_id='calibration.1',profile=p,entry_state=entry,catalog=catalog)
                    paths={key:_path(value,[sign*5],1.5,0,'return_to_entry')[0] for key,value in values.items() if '.finger.' in key and key.endswith('.'+suffix)}
                    f=_fragment(i,entry,p,paths,3,(c.PhaseLandmark('arrival',1.5),c.PhaseLandmark('end',3)))
                    r=build_action(h,prepare_fragment(f,entry,p),profile=p)
                    residual=max(abs(r['samples'][45]['measured'][key]-sign*5) for key in paths)
                    assert residual<.01
                    probes[pose+'.'+suffix+'.'+str(sign)]={'controls':len(paths),'signed_angle_residual_deg':residual,'review_passed':r['review']['passed']}
        results['signed_calibration_probes']=probes
    report[rig]=results;discard_avatar(h)
atomic_json(OUT/'regression-review.json',report);print('FINGERS_REGRESSIONS_PASSED',report,flush=True)
