"""Stage 05.1a real-rig evidence. --render renders every frame; --quick is a smoke subset."""
from dataclasses import replace
import json
import math
from pathlib import Path
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
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.registry import parameter_schema
from avatar_app.movement_library.joints import IDS,catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment,value_error
from avatar_app.movement_library.spatial import rotate,angle_rotation
from avatar_app.motion import Surface
from tools.preview_movement import load_entry,capture_entry

OUT=ROOT/'artifacts/stages/05.1a'; OUT.mkdir(parents=True,exist_ok=True)
ENTRY=ROOT/'tests/fixtures/movement_fragments/v1'
RENDER='--render' in sys.argv
QUICK='--quick' in sys.argv


def cases():
    yield 'look-small','head.look',{'yaw':5,'pitch':-5,'duration_s':.8,'hold_s':0},'bent-turned',False
    yield 'look-left','head.look',{},'neutral',False
    yield 'look-right','head.look',{'yaw':-25},'bent-turned',False
    yield 'look-min','head.look',{'yaw':-60,'pitch':-40,'duration_s':.8,'hold_s':0},'neutral',False
    yield 'look-max','head.look',{'yaw':60,'pitch':40,'duration_s':3,'hold_s':1},'bent-turned',False
    yield 'look-return','head.look',{'yaw':0,'pitch':0,'return_policy':'return_to_entry'},'bent-turned',False
    for side in ('left','right'):
        yield 'world-'+side,'head.look',{'frame':'world','target_side':side},'bent-turned',False
    yield 'world-turn','head.look',{'frame':'world','target_side':'left','hold_s':1},'bent-turned',True
    yield 'world-return','head.look',{'frame':'world','target_side':'right','hold_s':1,'return_policy':'return_to_entry'},'bent-turned',True
    for id in ('head.nod','head.shake','head.tilt'):
        name=id.split('.')[1]
        yield name+'-small',id,{'angle':5,'duration_s':.8,'hold_s':0},'bent-turned',False
        yield name+'-default',id,{},'neutral',False
        yield name+'-min',id,{'angle':0 if id=='head.shake' else -35,'duration_s':.8,'hold_s':0},'bent-turned',False
        yield name+'-max',id,{'angle':35,'duration_s':3,'hold_s':1},'bent-turned',False
        yield name+'-zero',id,{'angle':0},'bent-turned',False
        yield name+'-preserve',id,{'return_policy':'preserve_end'},'bent-turned',False
    yield 'shake-right','head.shake',{'direction':'right'},'bent-turned',False
    yield 'tilt-left','head.tilt',{'angle':-20},'bent-turned',False
    yield 'lead-small','neck.lead',{'yaw':5,'pitch':5,'duration_s':.8,'hold_s':0},'bent-turned',False
    yield 'lead-default','neck.lead',{},'neutral',False
    yield 'lead-min','neck.lead',{'yaw':-50,'pitch':-30,'neck_share':.2,'duration_s':.8,'hold_s':0},'bent-turned',False
    yield 'lead-max','neck.lead',{'yaw':50,'pitch':30,'neck_share':.6,'duration_s':3,'hold_s':1},'bent-turned',False
    yield 'lead-zero','neck.lead',{'yaw':0,'pitch':0},'bent-turned',False
    yield 'lead-preserve','neck.lead',{'yaw':-30,'return_policy':'preserve_end'},'bent-turned',False
    yield 'lead-head-only','neck.lead',{'neck_policy':'head_only'},'bent-turned',False


def render(h,profile,out,*,side=False):
    import numpy as np
    scene=h.scene
    scene.render.engine='BLENDER_WORKBENCH'; scene.display.shading.light='STUDIO'
    scene.display.shading.color_type='MATERIAL'; scene.display.shading.show_shadows=True
    scene.view_settings.view_transform='Standard'
    scene.render.resolution_percentage=100; scene.render.resolution_x=112; scene.render.resolution_y=112
    scene.render.image_settings.file_format='PNG'
    scene.frame_set(1)
    head=rp.semantic_frame(h,profile,'head').translation
    basis=rp.semantic_frame(h,profile,'pelvis').to_3x3()
    focus=head-basis.col[2]*.10
    scene.camera.location=focus+(basis.col[0] if side else basis.col[1])*1.4+basis.col[2]*.08
    scene.camera.rotation_euler=(focus-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.camera.data.lens=55
    width=112; columns=12; count=scene.frame_end; rows=math.ceil(count/columns)
    sheet=np.zeros((rows*width,columns*width,4),dtype=np.float32); sheet[:,:,3]=1
    label='side' if side else 'front'; frames=out/label; frames.mkdir(exist_ok=True)
    expected=json.loads((out/'result.json').read_text())['samples']
    for index in range(count):
        scene.frame_set(index+1); path=frames/f'{index+1:04d}.png'
        actual=tuple(rp.semantic_frame(h,profile,'head').to_quaternion())
        assert value_error(actual,tuple(expected[index]['measured']['head.orientation']),'quaternion')<.001,('Saved action playback',out,index)
        scene.render.filepath=str(path); bpy.ops.render.render(write_still=True)
        image=bpy.data.images.load(str(path),check_existing=False)
        pixels=np.array(image.pixels[:],dtype=np.float32).reshape((width,width,4))
        x=index%columns*width; y=(rows-1-index//columns)*width
        sheet[y:y+width,x:x+width]=pixels; bpy.data.images.remove(image)
    image=bpy.data.images.new('Head-neck '+label,columns*width,rows*width,alpha=True)
    image.pixels.foreach_set(sheet.ravel()); image.save_render(str(out/(label+'-sheet.png')),scene=scene)
    bpy.data.images.remove(image); scene.frame_set(1)


def checkpoint(report):
    (OUT/'execution-review.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def rollback_check(h,profile):
    h.rig.animation_data_clear(); load_entry(h,ENTRY/'entry-bent-turned.json')
    catalog=catalog_for_profile(profile); entry=capture_entry(h,profile)
    i=instantiate_movement('head.look',{'yaw':30},instance_id='rollback.1',profile=profile,entry_state=entry,catalog=catalog)
    f=build_fragment(i,entry,profile,(Surface(),),catalog); motion=prepare_fragment(f,entry,profile)
    result=build_action(h,motion,profile=profile)
    h.scene.frame_set(8,subframe=.25); h.scene.render.fps_base=1.001
    entry=capture_entry(h,profile)
    i=instantiate_movement('head.look',{'yaw':-30},instance_id='rollback.2',profile=profile,entry_state=entry,catalog=catalog)
    f=build_fragment(i,entry,profile,(Surface(),),catalog); motion=prepare_fragment(f,entry,profile)
    def state():
        scene=h.scene
        return (h.rig.animation_data.action,h.rig.animation_data.action_slot,
            tuple((b.name,b.rotation_mode,tuple(v for row in b.matrix_basis for v in row)) for b in h.rig.pose.bones),
            (scene.frame_start,scene.frame_end,scene.frame_current,scene.frame_subframe,scene.render.fps,scene.render.fps_base),
            tuple(v for row in scene.camera.matrix_world for v in row),frozenset(bpy.data.actions))
    before=state()
    maxima={'pose_matrix':0,'camera_matrix':0}
    def preserved():
        after=state()
        assert all(after[i]==before[i] for i in (0,1,3,5)),'Rollback changed action/slot/timing/action set'
        assert all(a[:2]==b[:2] for a,b in zip(before[2],after[2])),'Rollback changed rotation modes'
        pose=max(abs(x-y) for a,b in zip(before[2],after[2]) for x,y in zip(a[2],b[2]))
        camera=max(abs(x-y) for x,y in zip(before[4],after[4]))
        assert pose<1e-6 and camera<1e-6,('Rollback matrix residual',pose,camera)
        maxima['pose_matrix']=max(maxima['pose_matrix'],pose); maxima['camera_matrix']=max(maxima['camera_matrix'],camera)
    it=build_action_frames(h,motion,profile=profile)
    for _ in range(8): next(it)
    it.close(); preserved()
    goal=motion.goal_checks[0]
    failed=replace(motion,goal_checks=(replace(goal,target=replace(goal.target,value=angle_rotation(yaw=70))),)+motion.goal_checks[1:])
    try:
        build_action(h,failed,profile=profile)
        raise AssertionError('Unachieved orientation goal committed')
    except Exception as error: assert hasattr(error,'review') and not error.review['passed']
    preserved()
    print('HEAD_NECK_ORIENTATION_ROLLBACK_PASSED',profile.avatar_id,flush=True)
    return maxima


if '--rollback-only' in sys.argv:
    rollback={}
    for rig in ('demo','mixamo'):
        h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'))
        prepare_preview(h)
        profile=rp.calibrate_joint_frames(h,avatar_id='rollback.'+rig,recorded_at='2026-10-23',include_head_aim=True)
        rollback[rig]=rollback_check(h,profile); discard_avatar(h)
    (OUT/'rollback-review.json').write_text(json.dumps(rollback,indent=2)+'\n',encoding='utf-8')
    print('ALL_HEAD_NECK_ROLLBACK_CHECKS_PASSED',flush=True)
    raise SystemExit(0)


if '--render-only' in sys.argv:
    rendered=0
    for rig in ('demo','mixamo'):
        if '--render-rig' in sys.argv and rig!=sys.argv[sys.argv.index('--render-rig')+1]: continue
        h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'))
        prepare_preview(h)
        profile=c.loads(c.AvatarProfile,(OUT/rig/'profile.json').read_text())
        for name,id,parameters,entry_name,torso_turn in cases():
            out=OUT/rig/name
            if '--render-ready' in sys.argv and not (out/'result.json').exists(): continue
            needs_side=name.endswith('default') or name in ('look-left','world-turn','tilt-left')
            if '--skip-rendered' in sys.argv and (out/'visual-preview.blend').exists() and (out/'front-sheet.png').exists() and (not needs_side or (out/'side-sheet.png').exists()): continue
            result=json.loads((out/'result.json').read_text())
            with bpy.data.libraries.load(str(out/'preview.blend')) as (source,target):
                target.actions=[result['action']]
            action=target.actions[0]
            h.rig.animation_data_create(); h.rig.animation_data.action=action
            h.rig.animation_data.action_slot=action.slots[0]
            for bone in h.rig.pose.bones: bone.rotation_mode='QUATERNION'
            h.scene.frame_start=1; h.scene.frame_end=result['frames']; h.scene.render.fps=30; h.scene.render.fps_base=1
            render(h,profile,out)
            if needs_side: render(h,profile,out,side=True)
            bpy.ops.wm.save_as_mainfile(filepath=str(out/'visual-preview.blend'))
            rendered+=1; print('HEAD_NECK_VISUAL_RENDERED',rig,name,result['frames'],flush=True)
            h.rig.animation_data.action=None
        discard_avatar(h)
    print('ALL_HEAD_NECK_VISUALS_RENDERED',rendered,flush=True)
    raise SystemExit(0)


report=json.loads((OUT/'execution-review.json').read_text()) if '--small-only' in sys.argv else {}
total=0
for rig in ('demo','mixamo'):
    h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'))
    prepare_preview(h)
    profile=rp.calibrate_joint_frames(h,avatar_id='head-neck.'+rig,recorded_at='2026-10-23',source_revision='stage05.1a',include_head_aim=True)
    catalog=catalog_for_profile(profile)
    rig_out=OUT/rig; rig_out.mkdir(exist_ok=True)
    (rig_out/'profile.json').write_text(c.dumps(profile)+'\n',encoding='utf-8')
    (rig_out/'schemas.json').write_text(json.dumps({id:parameter_schema(v) for id,v in catalog.definitions.items()},indent=2)+'\n',encoding='utf-8')
    report.setdefault(rig,{'profile_version':profile.version,'neck_capable':'anatomy.neck' in profile.capabilities,'cases':{}})
    for name,id,parameters,entry_name,torso_turn in cases():
        if '--small-only' in sys.argv and not name.endswith('-small'): continue
        if QUICK and name not in ('look-left','world-turn','nod-default','shake-default','tilt-left','lead-default','world-return'): continue
        h.rig.animation_data_clear(); load_entry(h,ENTRY/('entry-'+entry_name+'.json'))
        entry=capture_entry(h,profile); original=parameters; parameters=dict(parameters)
        if 'target_side' in parameters:
            side=parameters.pop('target_side'); torso=rp.semantic_frame(h,profile,'spine.upper' if rig=='mixamo' else 'torso').to_quaternion()
            direction=Vector(rotate(tuple(torso),rotate(angle_rotation(yaw=25 if side=='left' else -25),(0,1,0))))
            parameters['target']=list(Vector(rp.semantic_frame(h,profile,'head').translation)+direction*3)
        if id=='neck.lead' and not report[rig]['neck_capable']: parameters['neck_policy']='head_only'
        instance=instantiate_movement(id,parameters,instance_id='move.1',profile=profile,entry_state=entry,catalog=catalog)
        fragment=build_fragment(instance,entry,profile,(Surface(),),catalog)
        external=None
        if torso_turn:
            current=next(v.value for v in entry.measured_controls if v.control_id=='torso.yaw')
            spec=next(v for v in profile.controls if v.id=='torso.yaw')
            # Explicit compatible fixture, not a general recipe/composition implementation.
            external=c.TrackSpec('fixture.turn',('fixture.torso',),'torso.yaw','degree',spec.frames[0],'scalar',1,
                c.CurveSpec('transition',current,current+30,1,'smooth'),'explicit',c.TimeInterval(1,2))
            fragment=replace(fragment,source_instance_ids=fragment.source_instance_ids+('fixture.torso',),tracks=fragment.tracks+(external,))
        motion=prepare_fragment(fragment,entry,profile)
        result=build_action(h,motion,profile=profile)
        assert result['review']['passed'],(rig,name,result['review'])
        initial={v.control_id:v.value for v in entry.measured_controls}; specs={v.id:v for v in profile.controls}
        start=max(value_error(v,initial[k],specs[k].value_shape) for k,v in result['samples'][0]['measured'].items())
        assert start<.001,(name,start)
        checked={g for s in result['samples'] for g in s['checked_goal_ids']}
        assert checked=={g.goal_id for g in motion.goal_checks},(name,checked)
        tracking=max(e for s in result['samples'] for e in s['tracking_errors'].values())
        world_error=0
        if parameters.get('frame')=='world':
            for sample in result['samples']:
                if not 1-1e-9<=sample['time_s']<1+parameters.get('hold_s',.2)-1e-9: continue
                position=Vector(sample['measured']['head.position']); target=Vector(parameters['target'])
                actual=Vector(rotate(tuple(sample['measured']['head.orientation']),(0,1,0)))
                error=math.degrees(actual.angle((target-position).normalized()))
                world_error=max(world_error,error)
            assert world_error<.1,(name,world_error)
        playback=0
        for sample in result['samples']:
            h.scene.frame_set(sample['frame']); measured=rp.capture_motion_state(h,profile,revision=entry.revision)
            for value in measured.measured_controls:
                expected=sample['measured'][value.control_id]; expected=tuple(expected) if isinstance(expected,list) else expected
                playback=max(playback,value_error(value.value,expected,specs[value.control_id].value_shape))
        assert playback<.001,(rig,name,playback)
        # Exact source/sample support is preserved by every family builder.
        assert all('move.1' in s['source_instance_ids'] for s in result['samples'])
        assert all(set(s['contacts'])=={'left_foot','right_foot'} for s in result['samples'])
        if external:
            h.rig.animation_data.action=None; load_entry(h,ENTRY/('entry-'+entry_name+'.json'))
            baseline=c.MotionFragment('fixture.base',('fixture.torso',),(),fragment.duration_s,(external,),
                tuple(replace(e,source_instance_ids=('fixture.torso',)) for e in fragment.contact_events),(),(),())
            reference=build_action(h,prepare_fragment(baseline,entry,profile),profile=profile)
            for expected,actual in zip(reference['samples'],result['samples']):
                for control in profile.controls:
                    if control.chain in ('head','neck'): continue
                    a,b=expected['measured'][control.id],actual['measured'][control.id]
                    if isinstance(a,list): a,b=tuple(a),tuple(b)
                    assert value_error(a,b,control.value_shape)<.001,(rig,name,control.id)
            h.rig.animation_data.action=bpy.data.actions[result['action']]
            h.rig.animation_data.action_slot=h.rig.animation_data.action.slots[0]
        out=rig_out/name; out.mkdir(exist_ok=True)
        for filename,record in (('entry',entry),('instance',instance),('fragment',fragment),('executable',motion)):
            (out/(filename+'.json')).write_text(c.dumps(record)+'\n',encoding='utf-8')
        (out/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        if RENDER:
            render(h,profile,out)
            if name.endswith('default') or name in ('look-left','world-turn','tilt-left'): render(h,profile,out,side=True)
        h.scene.frame_set(1); bpy.ops.wm.save_as_mainfile(filepath=str(out/'preview.blend'))
        if RENDER: bpy.ops.wm.save_as_mainfile(filepath=str(out/'visual-preview.blend'))
        summary={'id':id,'parameters':parameters,'entry':entry_name,'frames':result['frames'],'passed':True,
            'max_start_error':start,'max_tracking_error_deg':tracking,'max_playback_error':playback,
            'max_world_aim_error_deg':world_error,'goals_measured':len(checked),'review':result['review'],
            'head_only_approximation':any(v.name=='head_only_approximation' for v in fragment.phase_landmarks),
            'external_torso_preserved':bool(external)}
        report[rig]['cases'][name]=summary; total+=1; checkpoint(report)
        print('HEAD_NECK_CASE_PASSED',rig,name,result['frames'],tracking,flush=True)
    # Missing capability and unreachable inputs never create an action or alter pose.
    h.rig.animation_data.action=None; load_entry(h,ENTRY/'entry-neutral.json'); entry=capture_entry(h,profile)
    for id in IDS:
        caps=tuple(v for v in profile.capabilities if v!='measure.head.yaw')
        missing=replace(profile,capabilities=caps,controls=tuple(v for v in profile.controls if v.id!='head.yaw'),
                        joint_limits=tuple(v for v in profile.joint_limits if v.control_id!='head.yaw'))
        missing_entry=replace(entry,measured_controls=tuple(v for v in entry.measured_controls if v.control_id!='head.yaw'))
        try:
            instantiate_movement(id,{},instance_id='bad',profile=missing,entry_state=missing_entry,catalog=catalog_for_profile(missing))
            raise AssertionError('Missing capability accepted')
        except c.MotionContractError as error: assert error.code=='MISSING_CAPABILITY'
    for params in ({'frame':'world','target':[0,0,-10]},{'yaw':90}):
        try:
            i=instantiate_movement('head.look',params,instance_id='bad',profile=profile,entry_state=entry,catalog=catalog)
            build_fragment(i,entry,profile,(Surface(),),catalog)
            raise AssertionError('Unreachable head look accepted')
        except c.MotionContractError as error: assert error.code=='INVALID_PARAMETER'
    if not report[rig]['neck_capable']:
        try:
            i=instantiate_movement('neck.lead',{},instance_id='bad',profile=profile,entry_state=entry,catalog=catalog)
            build_fragment(i,entry,profile,(Surface(),),catalog)
            raise AssertionError('Missing neck advertised as articulated')
        except c.MotionContractError as error: assert error.code=='MISSING_CAPABILITY'
    report[rig]['negative_checks_passed']=True; checkpoint(report)
    discard_avatar(h)
print('ALL_HEAD_NECK_CHECKS_PASSED',total,flush=True)
