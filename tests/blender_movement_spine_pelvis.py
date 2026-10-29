"""Stage 05.1b measured two-rig validation and full-body frame renders."""
from dataclasses import replace
import json
import hashlib
import time
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
from avatar_app.blender.motion import build_action,set_contact
from avatar_app.motion import Surface,ContactConstraint
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.torso_pelvis import with_pelvis_v1
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment,value_error
from tools.preview_movement import load_entry,capture_entry

from tools.artifact_store import save_scene,write_manifest,entry_metadata,write_source_identity,render_complete,scene_path,hold_producer_lease,open_preview
OUT=ROOT/'artifacts/stages/05.1b'
if '--output-dir' in sys.argv: OUT=Path(sys.argv[sys.argv.index('--output-dir')+1]).resolve()
OUT.mkdir(parents=True,exist_ok=True)
hold_producer_lease(OUT)
RENDER='--render' in sys.argv

def entry_pose(h,name):
    load_entry(h,ROOT/'tests/fixtures/movement_fragments/v1'/('entry-'+('neutral' if name in ('neutral','free-space') else 'bent-turned')+'.json'))
    if name in ('neutral','free-space','turned-standing'): return
    # An explicitly authored supported crouch, never an executor standing reset.
    feet={s:(h.bones[s+'Foot'].head.copy(),h.bones[s+'Foot'].matrix.to_quaternion().copy()) for s in ('Left','Right')}
    bone=h.bones['Hips']; matrix=bone.matrix.copy()
    matrix.translation+=h.rig.matrix_world.inverted().to_3x3() @ Vector((0,0,-.09));bone.matrix=matrix
    bpy.context.view_layer.update()
    hips=h.bones['Hips'];pole=(hips.matrix.to_quaternion() @ hips.bone.matrix_local.to_quaternion().conjugated()) @ h.forward
    for side,(point,rotation) in feet.items(): set_contact(h,ContactConstraint(side.lower()+'_foot'),point,rotation,leg_pole=pole)

from spine_pelvis_cases import cases
from tools.storage_policy import measured_preflight
selected=[v for v in cases() if ('--case' not in sys.argv or v[0]==sys.argv[sys.argv.index('--case')+1])
          and ('--quick' not in sys.argv or v[0].endswith('.default'))]
rigs=[sys.argv[sys.argv.index('--rig')+1]] if '--rig' in sys.argv else ['demo','mixamo']
measured_preflight(OUT,[(rig+'/'+name,max(193,int((parameters.get('duration_s',3)+parameters.get('hold_s',1))*48+1)),
                        2 if RENDER or '--render-only' in sys.argv else 0)
                       for rig in rigs for name,_,parameters,_ in selected],reference=ROOT/'artifacts/stages/05.1b')

from tools.movement_evidence import render

report={}
for rig in ('demo','mixamo'):
    if '--rig' in sys.argv and rig!=sys.argv[sys.argv.index('--rig')+1]:continue
    rig_out=OUT/rig;rig_out.mkdir(exist_ok=True)
    if '--render-only' in sys.argv:
        p=c.loads(c.AvatarProfile,(rig_out/'profile.json').read_text(encoding='utf-8'))
    else:
        h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
        p=with_pelvis_v1(rp.calibrate_joint_frames(h,avatar_id='spine-pelvis.'+rig,recorded_at='2026-10-23',include_head_aim=True))
        (rig_out/'profile.json').write_text(c.dumps(p),encoding='utf-8')
        write_source_identity(rig_out,rig)
    catalog=catalog_for_profile(p)
    report[rig]={}
    if '--render-only' in sys.argv:
        for name,id,parameters,pose in cases():
            if '--case' in sys.argv and name!=sys.argv[sys.argv.index('--case')+1]:continue
            out=rig_out/name
            if not (out/'preview-manifest.json').exists() and not (out/'preview.blend').exists() and not (out/'visual-preview.blend').exists():continue
            saved_entry=c.loads(c.MotionStateSnapshot,(out/'entry.json').read_text())
            saved_instance=c.loads(c.MovementInstance,(out/'instance.json').read_text())
            if build_fragment(saved_instance,saved_entry,p,(Surface(),),catalog)!=c.loads(c.MotionFragment,(out/'fragment.json').read_text()):continue
            result=json.loads((out/'result.json').read_text())
            for view in ('front','side'):
                for previous in (out/view).glob('*.png'):
                    if previous.stem.isdigit() and int(previous.stem)>result['frames']:previous.unlink()
            digest=hashlib.sha256((out/'result.json').read_bytes()).hexdigest()
            marker=out/'visual-source.json'
            if '--skip-rendered' in sys.argv and '--detail' not in sys.argv and render_complete(out,('front','side')):continue
            h=open_preview(out)
            assert h.scene.frame_end-h.scene.frame_start+1==result['frames']
            detail='--detail' in sys.argv
            if detail:
                out=rig_out/(name+'.detail');out.mkdir(exist_ok=True)
                (out/'result.json').write_text(json.dumps(result,indent=2));marker=out/'visual-source.json'
            write_manifest(out,h.scene)
            views={'front':render(h,p,out,width=384 if detail else 128),'side':render(h,p,out,True,width=384 if detail else 128)}
            save_scene(out/'preview.blend')
            write_manifest(out,h.scene,views=views,metadata=entry_metadata('entry-'+('neutral' if pose in ('neutral','free-space') else 'bent-turned')+'.json; '+pose,parameters,h.scene),complete=True)
            print('SPINE_PELVIS_RENDERED',rig,name,result['frames']*2,flush=True)
        continue
    for name,id,parameters,pose in cases():
        if '--quick' in sys.argv and not name.endswith('.default'):continue
        if '--case' in sys.argv and name!=sys.argv[sys.argv.index('--case')+1]:continue
        h.rig.animation_data_clear();entry_pose(h,pose);entry=capture_entry(h,p)
        if pose=='free-space':entry=replace(entry,contact_anchors=(),active_contacts=())
        obj=tuple(v for row in h.rig.matrix_world for v in row)
        instance=instantiate_movement(id,parameters,instance_id='body.1',profile=p,entry_state=entry,catalog=catalog)
        fragment=build_fragment(instance,entry,p,(Surface(),),catalog);motion=prepare_fragment(fragment,entry,p)
        out=rig_out/name
        if '--resume' in sys.argv and (out/'result.json').exists() and all((out/(key+'.json')).read_text()==c.dumps(record) for key,record in (('entry',entry),('fragment',fragment),('instance',instance))):
            saved=json.loads((out/'result.json').read_text())
            assert saved['review']['passed']
            report[rig][name]={'frames':saved['frames'],'review':saved['review'],'reused_matching_records':True}
            (rig_out/'execution-review.json').write_text(json.dumps(report[rig],indent=2))
            print('SPINE_PELVIS_REUSED',rig,name,flush=True);continue
        try:result=build_action(h,motion,profile=p)
        except c.MotionContractError as error:
            print('BODY_EXECUTION_ERROR',rig,name,error.to_dict(),flush=True);raise
        assert result['review']['passed'],(rig,name,result['review'])
        specs={v.id:v for v in p.controls};initial={v.control_id:v.value for v in entry.measured_controls}
        tracking=max(v for s in result['samples'] for v in s['tracking_errors'].values())
        expected_contacts={side+'_foot' for side in ('left','right') if side+'.sole' in entry.active_contacts}
        assert all(set(s['contacts'])==expected_contacts for s in result['samples'])
        for sample in result['samples']:
            for spec in p.controls:
                arm=any(spec.chain==side+'.'+joint for side in ('left','right') for joint in ('upper_arm','forearm','wrist'))
                if arm and spec.value_shape=='scalar':
                    assert abs(sample['measured'][spec.id]-initial[spec.id])<.5,(rig,name,'Unrelated arm changed',spec.id)
        assert max(value_error(tuple(v) if isinstance(v,list) else v,initial[k],specs[k].value_shape) for k,v in result['samples'][0]['measured'].items())<.001
        playback=0;head=0
        for sample in result['samples']:
            h.scene.frame_set(sample['frame'])
            assert tuple(v for row in h.rig.matrix_world for v in row)==obj
            # Replay all requested controls; the baking review already measures all unrelated controls.
            for control in {t.control_id for t in motion.tracks}:
                spec=specs[control]
                if spec.value_shape=='scalar':actual=rp.measure_joint_angle(h,p,control)
                else:
                    frame=rp.semantic_frame(h,p,control.split('.')[0])
                    actual=tuple(frame.translation if spec.value_shape=='vector' else frame.to_quaternion())
                expected=sample['measured'][control];expected=tuple(expected) if isinstance(expected,list) else expected
                playback=max(playback,value_error(actual,expected,spec.value_shape))
            head=max(head,value_error(tuple(sample['measured']['head.orientation']),initial['head.orientation'],'quaternion'))
            if id.startswith('torso.'):
                assert value_error(tuple(sample['measured']['root.position']),initial['root.position'],'vector')<.00001
                assert value_error(tuple(sample['measured']['root.orientation']),initial['root.orientation'],'quaternion')<.01
        assert playback<.001 and head<.1,(name,playback,head)
        out=rig_out/name;out.mkdir(exist_ok=True)
        for filename,record in (('entry',entry),('instance',instance),('fragment',fragment),('executable',motion)):(out/(filename+'.json')).write_text(c.dumps(record))
        (out/'result.json').write_text(json.dumps(result,indent=2))
        write_manifest(out,h.scene)
        views={'front':render(h,p,out),'side':render(h,p,out,True)} if RENDER else {}
        h.scene.frame_set(1);save_scene(out/'preview.blend')
        write_manifest(out,h.scene,views=views,metadata=entry_metadata('entry-'+('neutral' if pose in ('neutral','free-space') else 'bent-turned')+'.json; '+pose,parameters,h.scene),complete=RENDER)
        report[rig][name]={'frames':result['frames'],'tracking_max':tracking,'head_error_deg':head,'playback_max':playback,'review':result['review'],
                         'entry_context':entry_metadata('entry-'+('neutral' if pose in ('neutral','free-space') else 'bent-turned')+'.json; '+pose,parameters,h.scene)}
        (rig_out/'execution-review.json').write_text(json.dumps(report[rig],indent=2))
        print('SPINE_PELVIS_PASSED',rig,name,result['frames'],flush=True)
    discard_avatar(h)
print('ALL_SPINE_PELVIS_CHECKS_PASSED',flush=True)
