"""Stage 05.3a two-rig measurements and storage-v2 saved-motion evidence."""
from pathlib import Path
import sys,json
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar,discard_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.hands import IDS,with_hands_v1
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment
from avatar_app.movement_library.registry import parameter_schema
from avatar_app.motion import Surface
from tools.preview_movement import load_entry,capture_entry
from tools.artifact_store import atomic_json,save_scene,write_manifest,entry_metadata,hold_producer_lease,open_preview,render_complete,write_source_identity,input_identity,digest
from tools.storage_policy import enforce,measured_preflight
from tools.movement_evidence import render

OUT=ROOT/'artifacts/stages/05.3a';OUT.mkdir(exist_ok=True)
PRODUCER=input_identity(OUT/'identity')['producer_sha256']
rigs=[sys.argv[sys.argv.index('--rig')+1]] if '--rig' in sys.argv else ['demo','mixamo']


from elbows_wrists_hands_cases import cases,parameters_for,expected_frames
selected=list(cases(quick='--quick' in sys.argv))
if '--case' in sys.argv:selected=[v for v in selected if v[0]==sys.argv[sys.argv.index('--case')+1]]
if '--palms' in sys.argv:selected=[v for v in selected if 'palms' in v[0]]
if '--start-at' in sys.argv:
    first=sys.argv[sys.argv.index('--start-at')+1];selected=selected[next(i for i,v in enumerate(selected) if v[0]==first):]
measured_preflight(OUT,[(rig+'/'+name,expected_frames(id,p),0) for rig in rigs for name,id,p,_ in selected],reference=ROOT/'artifacts/stages/05.2')
summary={}
for rig in rigs:
    hold_producer_lease(OUT/rig)
    base=OUT/rig;base.mkdir(exist_ok=True)
    if '--render-only' in sys.argv:
        p=c.loads(c.AvatarProfile,(base/'profile.json').read_text())
        for name,id,parameters,pose in selected:
            out=base/name
            if '--resume' in sys.argv and render_complete(out,('front','side')):continue
            from tools.lossless_evidence import encode_view,retire_pngs,recover_evidence
            recover_evidence(out);h=open_preview(out);plans=[];views={}
            for view in ('front','side'):
                views[view]=render(h,p,out,view=='side',width=128)
                media,plan=encode_view(out,view,range(h.scene.frame_start,h.scene.frame_end+1),fps=h.scene.render.fps,fps_base=h.scene.render.fps_base)
                views[view]['media']=media;plans.append(plan)
            h.scene.frame_set(1);write_manifest(out,h.scene,views=views,complete=True);retire_pngs(out,plans)
            print('HANDS_RENDER_PASSED',rig,name,flush=True)
        continue
    h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
    p=with_hands_v1(rp.calibrate_joint_frames(h,avatar_id='hands.'+rig,recorded_at='2026-10-29',include_head_aim=True))
    catalog=catalog_for_profile(p);profile_path=base/'profile.json'
    if profile_path.exists() and c.loads(c.AvatarProfile,profile_path.read_text())!=p:
        old=c.loads(c.AvatarProfile,profile_path.read_text())
        if '--reconcile-development-profile' not in sys.argv or old.version!=5 or any(x.id.endswith('.hand.torso_position') for x in old.controls):
            raise RuntimeError('Profile changed; reconcile accepted cases first')
        from tools.artifact_bundle import validate_manifest
        previous=base/'profile-development-before-parent.json';previous.write_text(c.dumps(old),encoding='utf-8')
        records=[]
        for target in base.glob('*/preview-manifest.json'):
            manifest,asset,motion=validate_manifest(target.parent)
            records.append({'path':str(target.relative_to(OUT)),'original_manifest_sha256':digest(target),'motion_sha256':digest(motion)})
            manifest['profile']['path']='../'+previous.name;manifest['profile']['sha256']=digest(previous)
            atomic_json(target,manifest);validate_manifest(target.parent)
        atomic_json(base/'development-profile-reconciliation.json',{'reason':'retain completed development motions against their original profile until validated replacement',
                    'old_profile_sha256':digest(previous),'cases':records})
        profile_path.write_text(c.dumps(p),encoding='utf-8')
    if not profile_path.exists():profile_path.write_text(c.dumps(p),encoding='utf-8')
    write_source_identity(base,rig)
    atomic_json(base/'schemas.json',{id:parameter_schema(catalog.definitions[id]) for id in IDS})
    for name,id,parameters,pose in selected:
        out=base/name
        if '--resume-numeric' in sys.argv and (out/'result.json').exists():
            manifest=json.loads((out/'preview-manifest.json').read_text())
            if manifest['inputs']==input_identity(out):
                print('HANDS_REUSED',rig,name,flush=True);continue
        h.rig.animation_data_clear()
        for bone in h.rig.pose.bones:bone.matrix_basis.identity()
        fixture='tests/fixtures/shoulders_arms/v1/entry-shoulders-bent.json' if pose=='bent-turned' else 'tests/fixtures/shoulders_arms/v1/entry-overhead.json' if pose=='overhead' else 'tests/fixtures/movement_fragments/v1/entry-neutral.json' if pose=='neutral' else 'tests/fixtures/elbows_wrists_hands/v1/entry-'+pose+'.json'
        load_entry(h,ROOT/fixture)
        entry=capture_entry(h,p)
        if id=='forearm.twist' and '.palms-' in name:
            from avatar_app.movement_library.spatial import palm_rotation,normalize
            values={x.control_id:x.value for x in entry.measured_controls};prep={'side':'both','return_policy':'preserve_end'}
            for side in ('left','right'):
                direction=values[side+'.forearm.direction']
                prep[side+'_orientation']=palm_rotation(normalize((direction[0],direction[1],0)),(0,0,1))
            i=instantiate_movement('hand.orient',prep,instance_id='prepare.1',profile=p,entry_state=entry,catalog=catalog)
            f=build_fragment(i,entry,p,(Surface(),),catalog);preparation=build_action(h,prepare_fragment(f,entry,p),profile=p)
            h.scene.frame_set(h.scene.frame_end);h.rig.animation_data_clear();entry=capture_entry(h,p)
        parameters=parameters_for(name,parameters,entry,p)
        instance=instantiate_movement(id,parameters,instance_id='hand.1',profile=p,entry_state=entry,catalog=catalog)
        fragment=build_fragment(instance,entry,p,(Surface(),),catalog);motion=prepare_fragment(fragment,entry,p)
        try:result=build_action(h,motion,profile=p)
        except Exception as error:
            atomic_json(OUT/'development-failure.json',{'rig':rig,'case':name,'error':str(error),'review':getattr(error,'review',None)})
            raise
        assert result['review']['passed'];out.mkdir(exist_ok=True)
        result['producer_sha256']=PRODUCER
        if input_identity(OUT/'identity')['producer_sha256']!=PRODUCER:raise RuntimeError('Producer source changed during execution; rerun with fixed source')
        if '.palms-' in name or name.endswith('.opposite-palms'):
            import math
            from avatar_app.movement_library.spatial import rotate
            arrival=result['samples'][round(parameters.get('duration_s',1.5)*30)]['measured']
            for side in ('left','right'):
                down='.palms-down' in name or name.endswith('.opposite-palms') and side=='right'
                normal=rotate(arrival[side+'.hand.orientation'],(0,0,1))
                assert normal[2]*(-1 if down else 1)>=math.cos(math.radians(3)),(rig,name,side,'actual palm normal',normal)
        if '--validate-only' in sys.argv:
            summary[rig+'/'+name]={'frames':result['frames'],'review':result['review']}
            atomic_json(OUT/('mechanics-review-'+rig+'.json'),summary)
            print('HANDS_MEASURED',rig,name,result['frames'],flush=True);continue
        for filename,record in (('entry',entry),('instance',instance),('fragment',fragment),('executable',motion)):
            (out/(filename+'.json')).write_text(c.dumps(record),encoding='utf-8')
        atomic_json(out/'result.json',result,compact=True)
        h.scene.frame_set(1);save_scene(out/'preview.blend')
        write_manifest(out,h.scene,metadata=entry_metadata(pose,parameters,h.scene),complete=False)
        summary[rig+'/'+name]={'frames':result['frames'],'review':result['review'],'max_tracking':max(x for s in result['samples'] for x in s['tracking_errors'].values())}
        atomic_json(OUT/('execution-review-'+rig+'.json'),summary)
        print('HANDS_PASSED',rig,name,result['frames'],flush=True)
    discard_avatar(h)
print('ALL_HANDS_CHECKS_PASSED',flush=True)
