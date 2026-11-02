"""Native optional-anatomy, rollback and authored parent-motion preservation."""
from pathlib import Path
from dataclasses import replace
import sys
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar,discard_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action,build_action_frames
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.fingers import with_fingers_v1,IDS
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment,value_error
from avatar_app.motion import Surface
from tools.preview_movement import capture_entry,load_entry
from tools.artifact_store import atomic_json
OUT=ROOT/'artifacts/stages/05.3b';report={}


def state(h):
    ad=h.rig.animation_data;s=h.scene
    return (ad.action if ad else None,ad.action_slot if ad else None,
        {b.name:(b.rotation_mode,b.matrix_basis.copy()) for b in h.rig.pose.bones},
        (s.frame_start,s.frame_end,s.frame_current,s.frame_subframe,s.render.fps,s.render.fps_base),
        h.rig.matrix_world.copy(),s.camera.matrix_world.copy())


def same(before,h):
    after=state(h);assert before[:2]==after[:2] and before[3]==after[3]
    residual=0
    for name,(mode,matrix) in before[2].items():
        assert mode==after[2][name][0]
        residual=max(residual,max(abs(v) for row in matrix-after[2][name][1] for v in row))
    for a,b in zip(before[4:],after[4:]):residual=max(residual,max(abs(v) for row in a-b for v in row))
    assert residual<1e-6,residual
    return residual


def merge(a,b):
    assert a.duration_s==b.duration_s
    return replace(b,source_instance_ids=a.source_instance_ids+b.source_instance_ids,tracks=a.tracks+b.tracks,
                   entry_requirements=a.entry_requirements+b.entry_requirements,goals=a.goals+b.goals)


for rig in ('demo','mixamo'):
    h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
    p=with_fingers_v1(rp.calibrate_joint_frames(h,avatar_id='fingers.'+rig,recorded_at='2026-11-02',include_head_aim=True))
    base=OUT/rig;base.mkdir(exist_ok=True)
    if not (base/'profile.json').exists():(base/'profile.json').write_text(c.dumps(p),encoding='utf-8')
    catalog=catalog_for_profile(p)
    load_entry(h,ROOT/'tests/fixtures/shoulders_arms/v1/entry-shoulders-bent.json');entry=capture_entry(h,p)
    def fragment(id,params,instance):
        i=instantiate_movement(id,params,instance_id=instance,profile=p,entry_state=entry,catalog=catalog)
        return build_fragment(i,entry,p,(Surface(),),catalog)
    if rig=='demo':
        parent=fragment('arm.raise',{'angle':10},'parent.1');build_action(h,prepare_fragment(parent,entry,p),profile=p)
        before=state(h);errors=[]
        for id in IDS:
            for side in ('left','right','both'):
                try:fragment(id,{'side':side},'detail.1');raise AssertionError('Missing anatomy was accepted')
                except c.MotionContractError as error:
                    assert error.code=='MISSING_CAPABILITY' and error.details['missing'];errors.append(error.to_dict())
                same(before,h)
        report[rig]={'missing_detail_results':errors,'major_arm_action_preserved':True,'no_finger_controls':not any('.finger.' in x.id for x in p.controls)}
        discard_avatar(h);continue
    baseline_pose={b.name:b.matrix_basis.copy() for b in h.rig.pose.bones}
    def reset():
        h.rig.animation_data_clear()
        for b in h.rig.pose.bones:b.matrix_basis=baseline_pose[b.name]
        bpy.context.view_layer.update()
    parent=fragment('arm.raise',{'angle':10},'parent.1');wrist=fragment('wrist.flex',{'angle':15},'wrist.1')
    authored=merge(parent,wrist);baseline=build_action(h,prepare_fragment(authored,entry,p),profile=p)
    reset();entry=capture_entry(h,p)
    fingers=fragment('finger.curl_spread',{'selection':'index','curl':.6},'detail.1')
    edited=build_action(h,prepare_fragment(merge(authored,fingers),entry,p),profile=p);max_position=max_angle=0
    for a,b in zip(baseline['samples'],edited['samples']):
        for key in a['measured']:
            if key.startswith('left.finger.index.'):continue
            spec=next(x for x in p.controls if x.id==key)
            actual=a['measured'][key];expected=b['measured'][key]
            if isinstance(actual,list):actual=tuple(actual);expected=tuple(expected)
            error=value_error(actual,expected,spec.value_shape)
            if spec.unit=='metre':max_position=max(max_position,error);assert error<=.002
            elif spec.unit=='degree' or spec.value_shape=='quaternion':max_angle=max(max_angle,error);assert error<=.5
    h.scene.frame_set(8,subframe=.25);entry=capture_entry(h,p)
    motion=prepare_fragment(fragment('hand.gesture',{},'detail.1'),entry,p);before=state(h)
    iterator=build_action_frames(h,motion,profile=p)
    for _ in range(8):next(iterator)
    iterator.close();cancel=same(before,h)
    goal=motion.goal_checks[0];bad=replace(motion,goal_checks=(replace(goal,target=replace(goal.target,value=goal.target.value+10)),)+motion.goal_checks[1:])
    try:build_action(h,bad,profile=p);raise AssertionError('Failed goal committed')
    except Exception as error:assert getattr(error,'review',{}).get('passed') is False
    failed=same(before,h)
    report[rig]={'authored_arm_wrist_preservation_max_m':max_position,'unrelated_angles_max_deg':max_angle,
                 'cancel_matrix_residual':cancel,'failed_review_matrix_residual':failed,'both_reviews_passed':True}
    discard_avatar(h)
atomic_json(OUT/'boundary-review.json',report)
print('FINGERS_BOUNDARIES_PASSED',report,flush=True)
