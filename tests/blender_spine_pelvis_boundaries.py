"""Reach rejection, cancellation, failed-review rollback and reduced-spine evidence."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar,discard_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action,build_action_frames,set_contact
from avatar_app.motion import Surface,ContactConstraint
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.torso_pelvis import with_pelvis_v1
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment
from tools.preview_movement import load_entry,capture_entry

OUT=ROOT/'artifacts/stages/05.1b';OUT.mkdir(parents=True,exist_ok=True)

def crouch(h):
    load_entry(h,ROOT/'tests/fixtures/movement_fragments/v1/entry-bent-turned.json')
    feet={s:(h.bones[s+'Foot'].head.copy(),h.bones[s+'Foot'].matrix.to_quaternion().copy()) for s in ('Left','Right')}
    bone=h.bones['Hips'];matrix=bone.matrix.copy();matrix.translation+=h.rig.matrix_world.inverted().to_3x3() @ Vector((0,0,-.09));bone.matrix=matrix;bpy.context.view_layer.update()
    hips=h.bones['Hips'];pole=(hips.matrix.to_quaternion() @ hips.bone.matrix_local.to_quaternion().conjugated()) @ h.forward
    for side,(point,rotation) in feet.items():set_contact(h,ContactConstraint(side.lower()+'_foot'),point,rotation,leg_pole=pole)

def motion(h,p,id='pelvis.shift',parameters=None):
    entry=capture_entry(h,p);catalog=catalog_for_profile(p)
    instance=instantiate_movement(id,parameters or {},instance_id='boundary.1',profile=p,entry_state=entry,catalog=catalog)
    fragment=build_fragment(instance,entry,p,(Surface(),),catalog)
    return entry,fragment,prepare_fragment(fragment,entry,p)

def state(h):
    scene=h.scene;animation=h.rig.animation_data
    return (animation.action if animation else None,animation.action_slot if animation else None,
        tuple((b.name,b.rotation_mode,tuple(v for row in b.matrix_basis for v in row)) for b in h.rig.pose.bones),
        (scene.frame_start,scene.frame_end,scene.frame_current,scene.frame_subframe,scene.render.fps,scene.render.fps_base),
        tuple(v for row in scene.camera.matrix_world for v in row),frozenset(bpy.data.actions))

def same(before,after):
    assert all(before[i]==after[i] for i in (0,1,3,5)),'Action, slot, timing or action set changed'
    assert all(a[:2]==b[:2] for a,b in zip(before[2],after[2]))
    assert max(abs(x-y) for a,b in zip(before[2],after[2]) for x,y in zip(a[2],b[2]))<1e-6,'Pose changed'
    assert max(abs(x-y) for x,y in zip(before[4],after[4]))<1e-6,'Camera changed'

report={}
for rig in ('demo','mixamo'):
    h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
    p=with_pelvis_v1(rp.calibrate_joint_frames(h,avatar_id='boundaries.'+rig,recorded_at='2026-10-23',include_head_aim=True))
    crouch(h);entry,f,x=motion(h,p);result=build_action(h,x,profile=p)
    h.scene.frame_set(8,subframe=.25);h.scene.render.fps_base=1.001
    entry,f,x=motion(h,p);before=state(h)
    iterator=build_action_frames(h,x,profile=p)
    for _ in range(8):next(iterator)
    iterator.close();same(before,state(h))
    goal=x.goal_checks[0]
    failed=replace(x,goal_checks=(replace(goal,target=replace(goal.target,value=tuple(v+.1 for v in goal.target.value))),)+x.goal_checks[1:])
    try:build_action(h,failed,profile=p);raise AssertionError('Failed goal committed')
    except Exception as error:assert hasattr(error,'review') and not error.review['passed']
    same(before,state(h))
    # Authored invalid lowering fixture exercises actual leg reach, beyond builder schema.
    track=next(t for t in f.tracks if t.control_id=='pelvis.position')
    target=tuple(v-(2 if index==2 else 0) for index,v in enumerate(track.curve.end_value))
    tracks=[]
    for t in f.tracks:
        if t.control_id=='pelvis.position':
            curve=replace(t.curve,start_value=target if t.curve.start_value==track.curve.end_value else t.curve.start_value,
                end_value=target if t.curve.end_value==track.curve.end_value else t.curve.end_value)
            t=replace(t,curve=curve)
        tracks.append(t)
    bad=replace(f,tracks=tuple(tracks))
    try:build_action(h,prepare_fragment(bad,entry,p),profile=p);raise AssertionError('Unreachable lowering accepted')
    except c.MotionContractError as error:assert error.code=='INVALID_PARAMETER',error.code
    same(before,state(h))
    try:
        unsupported=prepare_fragment(replace(f,contact_events=()),entry,p)
        build_action(h,unsupported,profile=p);raise AssertionError('Unsupported pelvis accepted')
    except c.MotionContractError as error:assert error.code=='ENTRY_MISMATCH'
    same(before,state(h))
    report[rig]={'cancellation':'passed','failed_goal_rollback':'passed','unreachable_lowering':'passed','missing_support':'passed'}
    discard_avatar(h)

h=create_demo_avatar();prepare_preview(h)
# Remove optional bones from a disposable test avatar; retain the existing skin weights.
bpy.context.view_layer.objects.active=h.rig;h.rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
for name in ('Spine2','Spine1'):
    bone=h.rig.data.edit_bones[name]
    for child in list(bone.children):child.parent=h.rig.data.edit_bones['Spine']
    h.rig.data.edit_bones.remove(bone)
bpy.ops.object.mode_set(mode='OBJECT')
h.bones={name:bone for name,bone in h.bones.items() if name not in ('Spine1','Spine2')}
for obj in h.objects:
    if obj.type=='MESH':
        for group in obj.vertex_groups:
            if group.name in ('Spine1','Spine2'):group.name='Spine'
p=with_pelvis_v1(rp.calibrate_joint_frames(h,avatar_id='single-spine',recorded_at='2026-10-23',include_head_aim=True))
load_entry(h,ROOT/'tests/fixtures/movement_fragments/v1/entry-neutral.json')
entry,f,x=motion(h,p,'torso.wave')
assert any(v.name=='single_spine_approximation' for v in f.phase_landmarks)
assert not any(t.control_id.startswith('spine.') for t in f.tracks)
result=build_action(h,x,profile=p);assert result['review']['passed']
out=OUT/'single-spine';out.mkdir(exist_ok=True)
(out/'profile.json').write_text(c.dumps(p));(out/'fragment.json').write_text(c.dumps(f));(out/'result.json').write_text(json.dumps(result,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(out/'preview.blend'))
from tools.movement_evidence import render
render(h,p,out);render(h,p,out,True)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'visual-preview.blend'))
report['single_spine']={'declared_approximation':True,'frames':result['frames'],'review':result['review']}
(OUT/'boundary-review.json').write_text(json.dumps(report,indent=2))
print('ALL_SPINE_PELVIS_BOUNDARY_CHECKS_PASSED',flush=True)
