"""Native leg support errors, transaction rollback and authored arm preservation."""
from pathlib import Path
from dataclasses import replace
import sys,math
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar,discard_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action,build_action_frames
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.legs import with_legs_v1
from avatar_app.movement_library.joints import catalog_for_profile,_fragment
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment,value_error
from avatar_app.motion import Surface
from blender_movement_hips_knees import fixture
from tools.artifact_store import atomic_json,input_identity
OUT=ROOT/'artifacts/stages/05.4';report={};producer=input_identity(OUT)['producer_sha256']


def state(h):
    ad=h.rig.animation_data
    return (ad.action if ad else None,ad.action_slot if ad else None,
        {b.name:(b.rotation_mode,b.matrix_basis.copy()) for b in h.rig.pose.bones},
        (h.scene.frame_start,h.scene.frame_end,h.scene.frame_current,h.scene.frame_subframe,h.scene.render.fps,h.scene.render.fps_base),
        h.rig.matrix_world.copy(),h.scene.camera.matrix_world.copy())


def same(a,h):
    b=state(h);assert a[:2]==b[:2] and a[3]==b[3];maximum=0
    for name,(mode,matrix) in a[2].items():
        assert mode==b[2][name][0]
        maximum=max(maximum,max(abs(x) for row in matrix-b[2][name][1] for x in row))
    for x,y in zip(a[4:],b[4:]):maximum=max(maximum,max(abs(v) for row in x-y for v in row))
    assert maximum<1e-6,maximum
    return maximum


def built(h,p,id,params=None,pose='neutral',instance='boundary.1'):
    h.rig.animation_data_clear();e=fixture(h,p,pose,(params or {}).get('side','left'));cat=catalog_for_profile(p)
    i=instantiate_movement(id,params or {},instance_id=instance,profile=p,entry_state=e,catalog=cat)
    f=build_fragment(i,e,p,(Surface(),),cat);return e,f,prepare_fragment(f,e,p)


for rig in ('demo','mixamo'):
    h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
    p=with_legs_v1(rp.calibrate_joint_frames(h,avatar_id='leg-boundaries.'+rig,recorded_at='2026-11-02',include_head_aim=True))
    cat=catalog_for_profile(p);e=fixture(h,p,'neutral','left');before=state(h);errors=[]
    for id,params in (('hip.lift',{'support':'both_planted'}),('leg.cross',{'target':(10,10,10)}),
                      ('leg.extend',{}),('knee.orient',{}),('leg.kick',{'side':'both'})):
        try:
            i=instantiate_movement(id,params,instance_id='invalid.1',profile=p,entry_state=e,catalog=cat)
            build_fragment(i,e,p,(Surface(),),cat)
        except c.MotionContractError as error:errors.append(error.to_dict());same(before,h)
        else:raise AssertionError('Invalid support/entry/target accepted: '+id)
    # Cancellation and failure must retain action/slot, complete pose and scene.
    e,f,x=built(h,p,'knee.lift');before=state(h);it=build_action_frames(h,x,profile=p)
    for _ in range(12):next(it)
    it.close();cancel=same(before,h)
    values={v.control_id:v.value for v in e.measured_controls};target=tuple(a+b for a,b in zip(values['left.foot.position'],(5,5,5)))
    bad=_fragment(instantiate_movement('leg.cross',{},instance_id='bad.1',profile=p,entry_state=e,catalog=cat),e,p,
        {'left.foot.position':[(0,1,values['left.foot.position'],target,None)]},1,(c.PhaseLandmark('end',1),))
    # Release selected foot so failure is unreachable geometry, not a fake planted swing.
    bad=replace(bad,contact_events=tuple(replace(event,release_s=1) if event.anchor_id=='left.sole' else event for event in bad.contact_events))
    before=state(h)
    try:build_action(h,prepare_fragment(bad,e,p),profile=p)
    except Exception as error:failed=str(error);rollback=same(before,h)
    else:raise AssertionError('Unreachable execution accepted')
    # Explicit pre-resolved compatible overlap, not a general composer.
    e,leg,_=built(h,p,'knee.lift',instance='leg.1');arm_i=instantiate_movement('wrist.flex',{'angle':10},instance_id='arm.1',profile=p,entry_state=e,catalog=cat)
    arm=build_fragment(arm_i,e,p,(Surface(),),cat)
    tracks=list(arm.tracks)
    for key in {t.control_id for t in tracks}:
        last=max((t for t in tracks if t.control_id==key),key=lambda t:t.interval.end_s)
        tracks.append(replace(last,track_id=last.track_id+'.padding',curve=c.CurveSpec('hold',last.curve.end_value,last.curve.end_value,leg.duration_s-arm.duration_s,'smooth'),interval=c.TimeInterval(arm.duration_s,leg.duration_s)))
    contacts=tuple(replace(event,source_instance_ids=('arm.1',)) for event in leg.contact_events)
    baseline=replace(arm,duration_s=leg.duration_s,tracks=tuple(tracks),contact_events=contacts)
    a=build_action(h,prepare_fragment(baseline,e,p),profile=p)
    h.rig.animation_data_clear();e=fixture(h,p,'neutral','left')
    both=replace(leg,source_instance_ids=('leg.1','arm.1'),tracks=leg.tracks+tuple(tracks),
        entry_requirements=leg.entry_requirements+arm.entry_requirements,goals=leg.goals+arm.goals)
    b=build_action(h,prepare_fragment(both,e,p),profile=p)
    degrees=metres=0;specs={v.id:v for v in p.controls}
    for left,right in zip(a['samples'],b['samples']):
        for key,actual in left['measured'].items():
            if not any(suffix in key for suffix in ('.hand.','.wrist.','.elbow.','.upper_arm.','.forearm.')):continue
            actual=tuple(actual) if isinstance(actual,list) else actual;other=right['measured'][key];other=tuple(other) if isinstance(other,list) else other
            error=value_error(actual,other,specs[key].value_shape)
            if specs[key].unit=='metre':metres=max(metres,error);assert error<=.002
            else:degrees=max(degrees,error);assert error<=.5
    report[rig]={'passed':True,'expected_errors':errors,'cancellation_matrix_residual':cancel,'failed_execution_matrix_residual':rollback,
        'failure':failed,'authored_wrist_path_with_knee_lift':{'baseline_passed':a['review']['passed'],'combined_passed':b['review']['passed'],
            'max_unrelated_arm_error_deg_or_unitless':degrees,'max_unrelated_hand_error_m':metres,'samples':b['frames']}}
    atomic_json(OUT/'boundary-review.json',report);discard_avatar(h)
assert input_identity(OUT)['producer_sha256']==producer
print('LEGS_BOUNDARIES_PASSED',report,flush=True)
