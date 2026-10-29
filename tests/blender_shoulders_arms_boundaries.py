"""Arm cancellation/review rollback, reach rejection and unsafe shoulder entry."""
from dataclasses import replace
from pathlib import Path
import sys
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tools.artifact_store import open_preview,atomic_json
from tools.preview_movement import capture_entry,load_entry
from avatar_app.blender.motion import build_action,build_action_frames
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.motion import Surface

OUT=ROOT/'artifacts/stages/05.2';report={}


def state(h):
    ad=h.rig.animation_data;s=h.scene
    return (ad.action if ad else None,ad.action_slot if ad else None,
            {b.name:(b.rotation_mode,b.matrix_basis.copy()) for b in h.rig.pose.bones},
            (s.frame_start,s.frame_end,s.frame_current,s.frame_subframe,s.render.fps,s.render.fps_base),
            h.rig.matrix_world.copy(),s.camera.matrix_world.copy())


def same(before,h):
    after=state(h);assert before[:2]==after[:2] and before[3]==after[3]
    assert before[2].keys()==after[2].keys()
    residual=0
    for name,(mode,matrix) in before[2].items():
        assert mode==after[2][name][0]
        residual=max(residual,max(abs(v) for row in matrix-after[2][name][1] for v in row))
    for a,b in zip(before[4:],after[4:]):residual=max(residual,max(abs(v) for row in a-b for v in row))
    assert residual<1e-6,residual
    return residual


for rig in ('demo','mixamo'):
    case=OUT/rig/'arm.reach.default';h=open_preview(case)
    p=c.loads(c.AvatarProfile,(case.parent/'profile.json').read_text());catalog=catalog_for_profile(p)
    h.scene.frame_set(8,subframe=.25);entry=capture_entry(h,p)
    def movement(id,parameters):
        i=instantiate_movement(id,parameters,instance_id='boundary.1',profile=p,entry_state=entry,catalog=catalog)
        return prepare_fragment(build_fragment(i,entry,p,(Surface(),),catalog),entry,p)
    motion=movement('arm.reach',{});before=state(h)
    iterator=build_action_frames(h,motion,profile=p)
    for _ in range(8):next(iterator)
    iterator.close();cancel=same(before,h)
    goal=motion.goal_checks[0]
    bad=replace(motion,goal_checks=(replace(goal,target=replace(goal.target,value=tuple(v+.1 for v in goal.target.value))),)+motion.goal_checks[1:])
    try:build_action(h,bad,profile=p);raise AssertionError('Failed endpoint goal was committed')
    except Exception as error:assert getattr(error,'review',{}).get('passed') is False
    failed=same(before,h)
    try:movement('arm.reach',{'target':[5,5,5]});raise AssertionError('Unreachable endpoint accepted')
    except c.MotionContractError as error:assert error.code=='INVALID_PARAMETER'
    same(before,h)
    value={'cancel_matrix_residual':cancel,'failed_review_matrix_residual':failed,'unreachable_rejected':True}
    if rig=='mixamo':
        h.rig.animation_data_clear()
        for bone in h.rig.pose.bones:bone.matrix_basis.identity()
        load_entry(h,ROOT/'tests/fixtures/movement_fragments/v1/entry-bent-turned.json')
        entry=capture_entry(h,p);before=state(h)
        unsafe=movement('shoulder.shrug',{'side':'both','angle':-10})
        try:build_action(h,unsafe,profile=p);raise AssertionError('Unsafe lowered shoulder accepted')
        except Exception as error:
            review=getattr(error,'review',{})
            assert review.get('passed') is False and any(v['kind']=='body_clearance' for v in review['issues'])
            value['unsafe_entry_rejected']=True
        same(before,h)
        unsafe=movement('arm.sweep',{'angle':110})
        try:build_action(h,unsafe,profile=p);raise AssertionError('Unsafe inward sweep entry accepted')
        except Exception as error:
            review=getattr(error,'review',{})
            assert review.get('passed') is False and any(v['kind']=='body_clearance' for v in review['issues'])
            value['unsafe_sweep_entry_rejected']=True
            value['unsafe_sweep_penetration_m']=max(v['measured'] for v in review['issues'] if v['kind']=='body_clearance')
        same(before,h)
    report[rig]=value
    print('SHOULDERS_ARMS_BOUNDARIES_PASSED',rig,flush=True)
atomic_json(OUT/'boundary-review.json',report)
print('ALL_SHOULDERS_ARMS_BOUNDARIES_PASSED',flush=True)
