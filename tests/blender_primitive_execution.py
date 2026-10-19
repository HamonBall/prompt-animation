"""Real-rig single-fragment execution, playback, review and rollback checks."""
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar,discard_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action,build_action_frames
from avatar_app.blender.geometry import skin_bounds
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import value_error,instantiate_movement
from avatar_app.motion import ActionPlan,ContactConstraint
from avatar_app.planning.movements import movement
from primitive_fixtures import ROOT as FIXTURES,executable,make_catalog,LEGACY_BASELINE
from tools.preview_movement import load_entry,capture_entry,render_preview

OUT=ROOT/'artifacts/stages/04'; OUT.mkdir(parents=True,exist_ok=True)
legacy_spec=importlib.util.spec_from_file_location('avatar_app.blender.stage04_baseline',OUT/'legacy-motion.py')
baseline=importlib.util.module_from_spec(legacy_spec)
sys.modules[legacy_spec.name]=baseline
legacy_code=subprocess.check_output(['git','show',LEGACY_BASELINE+':src/avatar_app/blender/motion.py'],cwd=ROOT,text=True)
exec(compile(legacy_code,LEGACY_BASELINE+':blender/motion.py','exec'),baseline.__dict__)
reports={}


def state(h):
    return {'action':h.rig.animation_data.action,'slot':h.rig.animation_data.action_slot,
        'actions':set(bpy.data.actions),'basis':{b.name:b.matrix_basis.copy() for b in h.rig.pose.bones},
        'modes':{b.name:b.rotation_mode for b in h.rig.pose.bones},
        'timeline':(h.scene.frame_start,h.scene.frame_end,h.scene.frame_current,h.scene.frame_subframe,h.scene.render.fps,h.scene.render.fps_base),
        'camera':h.scene.camera.matrix_world.copy()}


def assert_preserved(h,before):
    assert h.rig.animation_data.action==before['action']
    assert h.rig.animation_data.action_slot==before['slot']
    assert set(bpy.data.actions)==before['actions']
    assert (h.scene.frame_start,h.scene.frame_end,h.scene.frame_current,h.scene.frame_subframe,h.scene.render.fps,h.scene.render.fps_base)==before['timeline']
    assert max(abs(v) for row in h.scene.camera.matrix_world-before['camera'] for v in row)<1e-6
    for bone in h.rig.pose.bones:
        assert bone.rotation_mode==before['modes'][bone.name]
        assert max(abs(v) for row in bone.matrix_basis-before['basis'][bone.name] for v in row)<1e-5,bone.name


def legacy_samples(h):
    values=[]
    for f in range(h.scene.frame_start,h.scene.frame_end+1):
        h.scene.frame_set(f)
        values.append({'positions':{b.name:tuple(h.rig.matrix_world @ b.head) for b in h.rig.pose.bones},
                       'rotations':{b.name:tuple(b.matrix.to_quaternion()) for b in h.rig.pose.bones},
                       'floor':skin_bounds(h)[0].z})
    return values


for rig_name in ('demo','mixamo'):
    h=create_demo_avatar() if rig_name=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'))
    prepare_preview(h)
    profile=rp.calibrate_joint_frames(h,avatar_id='execution.'+rig_name,source_revision='stage04-working-tree',recorded_at='2026-10-19')
    cases={}
    for entry_name in ('neutral','bent-turned'):
        if h.rig.animation_data: h.rig.animation_data.action=None
        h.scene.frame_set(1)
        load_entry(h,FIXTURES/('entry-'+entry_name+'.json'))
        entry=capture_entry(h,profile)
        instance,fragment,motion=executable(profile,entry)
        result=build_action(h,motion,profile=profile)
        assert result['review']['passed']
        assert result['frames']==49
        assert h.scene.render.fps==30 and h.scene.render.fps_base==1
        expected={v.control_id:v for v in entry.measured_controls}
        first=result['samples'][0]['measured']
        start_errors={id:value_error(first[id],value.value,next(v.value_shape for v in profile.controls if v.id==id)) for id,value in expected.items()}
        assert max(start_errors.values())<.001,(rig_name,entry_name,'start',start_errors)
        assert abs(result['samples'][-1]['measured']['head.yaw']-25)<.1
        assert all(s['source_instance_ids']==['preview.1'] for s in result['samples'])
        playback=0
        for sample in result['samples']:
            h.scene.frame_set(sample['frame'])
            solved=rp.capture_motion_state(h,profile,revision=1,captured_time_s=sample['time_s'])
            for value in solved.measured_controls:
                control=next(v for v in profile.controls if v.id==value.control_id)
                error=value_error(value.value,sample['measured'][value.control_id],control.value_shape)
                tolerance=.002 if control.unit=='metre' else .05 if control.unit=='degree' or control.value_shape=='quaternion' else .001
                assert error<tolerance,(rig_name,entry_name,'playback',value.control_id,error)
                playback=max(playback,error)
        good=h.rig.animation_data.action
        good.use_fake_user=True
        h.scene.frame_set(8,subframe=.25); h.scene.render.fps=24; h.scene.render.fps_base=1.001
        fresh=capture_entry(h,profile,revision=2)
        _,_,next_motion=executable(profile,fresh)
        before=state(h)
        iterator=build_action_frames(h,next_motion,profile=profile)
        for _ in range(10): next(iterator)
        iterator.close()
        assert_preserved(h,before)
        def cancel(value):
            if value>.07: raise RuntimeError('Injected cancellation')
        try:
            build_action(h,next_motion,progress=cancel,profile=profile)
            raise AssertionError('Cancellation did not raise')
        except RuntimeError as error: assert str(error)=='Injected cancellation'
        assert_preserved(h,before)
        bad_goal=replace(next_motion.goal_checks[0],target=replace(next_motion.goal_checks[0].target,value=50))
        try:
            build_action(h,replace(next_motion,goal_checks=(bad_goal,)),profile=profile)
            raise AssertionError('Unachieved symbolic goal was accepted')
        except Exception as error:
            assert hasattr(error,'review') and not error.review['passed'],str(error)
        assert_preserved(h,before)
        _,_,unreachable=executable(profile,fresh,id='test.hand_target',parameters={'target':[10,10,10]})
        try:
            build_action(h,unreachable,profile=profile)
            raise AssertionError('Unreachable target accepted')
        except c.MotionContractError as error: assert error.code=='INVALID_PARAMETER'
        assert_preserved(h,before)
        catalog=make_catalog()
        catalog._definitions['test.head_transition']=replace(catalog.definitions['test.head_transition'],required_capabilities=('missing',))
        try:
            instantiate_movement('test.head_transition',{},instance_id='bad',profile=profile,entry_state=fresh,catalog=catalog)
            raise AssertionError('Missing capability accepted')
        except c.MotionContractError as error: assert error.code=='MISSING_CAPABILITY'
        assert_preserved(h,before)
        stale=replace(next_motion,entry_snapshot=replace(fresh,measured_controls=tuple(
            replace(v,value=v.value+5) if v.control_id=='head.yaw' else v for v in fresh.measured_controls)))
        try:
            build_action(h,stale,profile=profile)
            raise AssertionError('Incompatible supplied state accepted')
        except c.MotionContractError as error: assert error.code=='ENTRY_MISMATCH'
        assert_preserved(h,before)
        result.update(max_start_error=max(start_errors.values()),max_playback_error=playback,
                      generator_close_rollback=True,callback_cancel_rollback=True,semantic_failure_rollback=True,
                      unreachable_rejected=True,missing_capability_rejected=True,entry_mismatch_rejected=True)
        out=OUT/(rig_name+'-'+entry_name); out.mkdir(exist_ok=True)
        for filename,record in (('profile',profile),('entry',entry),('instance',instance),('fragment',fragment),('executable',motion)):
            (out/(filename+'.json')).write_text(c.dumps(record)+'\n',encoding='utf-8')
        (out/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        h.scene.render.fps=30; h.scene.render.fps_base=1; h.scene.frame_set(1)
        if '--render' in sys.argv: render_preview(h,profile,out)
        bpy.ops.wm.save_as_mainfile(filepath=str(out/'preview.blend'))
        good.use_fake_user=False
        cases[entry_name]={'frames':result['frames'],'review':result['review'],
            'max_start_error':result['max_start_error'],'max_playback_error':playback,
            'cancellation_and_failure_rollback':True}
        print('PRIMITIVE_VERIFIED',rig_name,entry_name,flush=True)
    # Legacy baseline is loaded from the unmodified source saved before adapter edits.
    plan=ActionPlan((movement('legacy','Legacy head test',{'head_yaw':25},1,
        (ContactConstraint('left_foot'),ContactConstraint('right_foot'))),))
    old=baseline.build_action(h,plan); reference=legacy_samples(h)
    new=build_action(h,plan); actual=legacy_samples(h)
    assert len(reference)==len(actual)==31
    positional=0; angular=0; floor=0
    for previous,current in zip(reference,actual):
        floor=max(floor,abs(previous['floor']-current['floor']))
        for name,point in previous['positions'].items():
            positional=max(positional,(Vector(point)-Vector(current['positions'][name])).length)
            angular=max(angular,value_error(previous['rotations'][name],current['rotations'][name],'quaternion'))
    assert positional<.00001 and angular<.05 and floor<.00001,(rig_name,positional,angular,floor)
    reports[rig_name]={'cases':cases,'legacy_equivalence':{'frames':31,'max_position_delta_m':positional,
        'max_quaternion_delta_deg':angular,'max_floor_delta_m':floor,'old_review':old['review'],'new_review':new['review']}}
    print('LEGACY_EQUIVALENCE_PASSED',rig_name,positional,angular,floor,flush=True)
    h.rig.animation_data.action=None
    load_entry(h,FIXTURES/'entry-bent-turned.json')
    entry=capture_entry(h,profile,revision=3)
    hand=Vector(rp.measure_endpoint(h,profile,'left.hand'))
    shoulder=h.rig.matrix_world @ h.bones['LeftArm'].head
    target=hand+(shoulder-hand).normalized()*.01+rp.semantic_frame(h,profile,'pelvis').to_3x3().col[1]*.01
    _,_,reach=executable(profile,entry,id='test.hand_target',parameters={'target':list(target)})
    reached=build_action(h,reach,profile=profile)
    residual=(Vector(reached['samples'][-1]['measured']['left.hand.position'])-target).length
    assert reached['review']['passed'] and residual<.01
    (OUT/(rig_name+'-endpoint.json')).write_text(json.dumps(reached,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    reports[rig_name]['endpoint_reach']={'frames':reached['frames'],'residual_m':residual,'review':reached['review']}
    print('ENDPOINT_BRIDGE_VERIFIED',rig_name,residual,flush=True)
    discard_avatar(h)
(OUT/'execution-review.json').write_text(json.dumps(reports,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print('ALL_PRIMITIVE_EXECUTION_CHECKS_PASSED',flush=True)
