"""05.3a transaction, incompatible constraints and authored path preservation."""
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
from avatar_app.movement_library.hands import with_hands_v1
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment,value_error
from avatar_app.motion import Surface
from tools.preview_movement import capture_entry,load_entry
from tools.artifact_store import atomic_json
OUT=ROOT/'artifacts/stages/05.3a';report={}


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


for rig in ('demo','mixamo'):
    h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
    p=with_hands_v1(rp.calibrate_joint_frames(h,avatar_id='hands.'+rig,recorded_at='2026-10-29',include_head_aim=True))
    catalog=catalog_for_profile(p)
    load_entry(h,ROOT/'tests/fixtures/shoulders_arms/v1/entry-shoulders-bent.json');entry=capture_entry(h,p)
    def fragment(id,parameters,instance='boundary.1'):
        i=instantiate_movement(id,parameters,instance_id=instance,profile=p,entry_state=entry,catalog=catalog)
        return build_fragment(i,entry,p,(Surface(),),catalog)
    motion=prepare_fragment(fragment('wrist.flex',{}),entry,p)
    build_action(h,motion,profile=p);h.scene.frame_set(8,subframe=.25);entry=capture_entry(h,p)
    motion=prepare_fragment(fragment('wrist.flex',{}),entry,p);before=state(h)
    iterator=build_action_frames(h,motion,profile=p)
    for _ in range(8):next(iterator)
    iterator.close();cancel=same(before,h)
    goal=motion.goal_checks[0]
    bad=replace(motion,goal_checks=(replace(goal,target=replace(goal.target,value=goal.target.value+10)),)+motion.goal_checks[1:])
    try:build_action(h,bad,profile=p);raise AssertionError('Failed goal was committed')
    except Exception as error:assert getattr(error,'review',{}).get('passed') is False
    failed=same(before,h);errors={}
    for name,params,code in (('unreachable',{'target':[5,5,5]},'INVALID_PARAMETER'),
                             ('incompatible',{'flexion_deg':130},'CONSTRAINT_CONFLICT')):
        try:fragment('hand.hold',params);raise AssertionError('Invalid constraints accepted')
        except c.MotionContractError as error:assert error.code==code;errors[name]=error.to_dict()
        same(before,h)
    palm=fragment('hand.orient',{},'palm.1');twist=fragment('forearm.twist',{},'twist.1')
    conflicting=replace(palm,source_instance_ids=('palm.1','twist.1'),tracks=palm.tracks+twist.tracks,
                        entry_requirements=palm.entry_requirements+twist.entry_requirements,goals=palm.goals+twist.goals)
    try:build_action(h,prepare_fragment(conflicting,entry,p),profile=p);raise AssertionError('Conflicting hard palm/twist constraints accepted')
    except c.MotionContractError as error:assert error.code=='CONSTRAINT_CONFLICT';errors['hard_palm_twist']=error.to_dict()
    same(before,h)
    # An explicit compatible authored parent trajectory uses the same fragment
    # and sampler. This fixture is not a recipe scheduler or family composer.
    h.rig.animation_data_clear();load_entry(h,ROOT/'tests/fixtures/shoulders_arms/v1/entry-shoulders-bent.json');entry=capture_entry(h,p)
    parent=fragment('arm.raise',{'angle':10},'parent.1')
    parent_result=build_action(h,prepare_fragment(parent,entry,p),profile=p)
    h.rig.animation_data_clear();load_entry(h,ROOT/'tests/fixtures/shoulders_arms/v1/entry-shoulders-bent.json');entry=capture_entry(h,p)
    wrist=fragment('wrist.flex',{'angle':20},'wrist.1')
    authored=replace(wrist,source_instance_ids=('parent.1','wrist.1'),tracks=parent.tracks+wrist.tracks,
                     entry_requirements=parent.entry_requirements+wrist.entry_requirements,goals=parent.goals+wrist.goals)
    edited=build_action(h,prepare_fragment(authored,entry,p),profile=p);residual=0
    for a,b in zip(parent_result['samples'],edited['samples']):
        residual=max(residual,value_error(tuple(a['measured']['left.hand.position']),tuple(b['measured']['left.hand.position']),'vector'))
    assert residual<=.002,residual
    holds={}
    for frame in ('world','current_torso'):
        h.rig.animation_data_clear();load_entry(h,ROOT/'tests/fixtures/shoulders_arms/v1/entry-shoulders-bent.json');entry=capture_entry(h,p)
        torso=fragment('torso.twist',{'angle':8,'duration_s':1.5},'torso.1')
        hand=fragment('hand.hold',{'position_frame':frame,'orientation_frame':frame},'hold.1')
        authored=replace(hand,source_instance_ids=('torso.1','hold.1'),tracks=torso.tracks+hand.tracks,
                         entry_requirements=torso.entry_requirements+hand.entry_requirements,goals=torso.goals+hand.goals)
        result=build_action(h,prepare_fragment(authored,entry,p),profile=p)
        initial={v.control_id:v.value for v in entry.measured_controls}
        world_motion=max(value_error(tuple(s['measured']['left.hand.position']),initial['left.hand.position'],'vector') for s in result['samples'])
        local_motion=max(value_error(tuple(s['measured']['left.hand.torso_position']),initial['left.hand.torso_position'],'vector') for s in result['samples'])
        if frame=='world':assert world_motion<.01 and local_motion>.01,(world_motion,local_motion)
        else:assert local_motion<.01 and world_motion>.01,(world_motion,local_motion)
        holds[frame]={'world_hand_displacement_m':world_motion,'torso_relative_hand_displacement_m':local_motion,'frames':result['frames']}
    h.rig.animation_data_clear();load_entry(h,ROOT/'tests/fixtures/movement_fragments/v1/entry-neutral.json');entry=capture_entry(h,p);before=state(h)
    try:fragment('hand.hold',{'elbow_plane_deg':0,'plane_policy':'hard'});raise AssertionError('Hard straight-arm plane accepted')
    except c.MotionContractError as error:assert error.code=='CONSTRAINT_CONFLICT';errors['undefined_hard_plane']=error.to_dict()
    same(before,h)
    soft=fragment('hand.hold',{'elbow_plane_deg':0,'plane_policy':'soft'})
    assert not any(t.control_id.endswith('.elbow.plane') for t in soft.tracks)
    assert build_action(h,prepare_fragment(soft,entry,p),profile=p)['review']['passed']
    report[rig]={'cancel_matrix_residual':cancel,'failed_review_matrix_residual':failed,'specific_errors':errors,
                 'authored_parent_path_frames':edited['frames'],'isolated_wrist_hand_path_error_m':residual,'moving_parent_hold_checks':holds}
    atomic_json(OUT/'boundary-review.json',report);discard_avatar(h)
    print('HANDS_BOUNDARIES_PASSED',rig,flush=True)
print('ALL_HANDS_BOUNDARIES_PASSED',flush=True)
