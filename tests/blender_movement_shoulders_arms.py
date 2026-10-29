"""Stage 05.2 measured cases through the shared transactional executor."""
from pathlib import Path
import json
import hashlib
import sys
import bpy

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar,discard_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.limbs import IDS,with_shoulders_v1
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment,value_error
from avatar_app.motion import Surface
from tools.preview_movement import load_entry,capture_entry
from tools.artifact_store import atomic_json,save_scene,write_manifest,entry_metadata,write_source_identity,hold_producer_lease,render_complete,open_preview,input_identity
from tools.storage_policy import enforce,measured_preflight
from tools.movement_evidence import render

OUT=ROOT/'artifacts/stages/05.2'
if '--output-dir' in sys.argv:OUT=Path(sys.argv[sys.argv.index('--output-dir')+1]).resolve()
OUT.mkdir(parents=True,exist_ok=True)
hold_producer_lease(OUT/sys.argv[sys.argv.index('--rig')+1] if '--rig' in sys.argv else OUT)
RENDER='--render' in sys.argv;summary={};VALIDATE_ONLY='--validate-only' in sys.argv
PRODUCER=input_identity(OUT/'identity')['producer_sha256']

if '--render-only' in sys.argv:
    if OUT==ROOT/'artifacts/stages/05.2':
        from tools.shoulders_arms_storage_preflight import preflight
        preflight()
    else:
        requests=[(str(path.parent.relative_to(OUT)),json.loads(path.read_text())['frames'],2)
                  for path in OUT.glob('*/*/result.json')]
        measured_preflight(OUT,requests,reference=ROOT/'artifacts/stages/05.1b')
    for rig in ('demo','mixamo'):
        if '--rig' in sys.argv and rig!=sys.argv[sys.argv.index('--rig')+1]:continue
        base=OUT/rig;p=c.loads(c.AvatarProfile,(base/'profile.json').read_text(encoding='utf-8'))
        for out in sorted(base.iterdir()):
            if not out.is_dir() or not (out/'result.json').exists():continue
            if '--case' in sys.argv and out.name!=sys.argv[sys.argv.index('--case')+1]:continue
            from tools.lossless_evidence import recover_evidence,encode_view,retire_pngs
            recover_evidence(out)
            if '--skip-rendered' in sys.argv and render_complete(out,('front','side')):continue
            result=json.loads((out/'result.json').read_text());assert result['review']['passed']
            enforce(out)
            h=open_preview(out)
            views={'front':render(h,p,out),'side':render(h,p,out,True)}
            plans=[]
            if '--lossless-video' in sys.argv:
                for view in views:
                    media,plan=encode_view(out,view,range(h.scene.frame_start,h.scene.frame_end+1),fps=h.scene.render.fps,fps_base=h.scene.render.fps_base)
                    views[view]['media']=media;plans.append(plan)
            # Rendering reads the accepted action; publish view metadata/media
            # without serializing that same motion or shared asset again.
            h.scene.frame_set(1);write_manifest(out,h.scene,views=views,complete=True)
            if plans:retire_pngs(out,plans)
            print('SHOULDERS_ARMS_STORED_RENDER_PASSED',rig,out.name,result['frames']*2,flush=True)
    print('ALL_SHOULDERS_ARMS_STORED_RENDERS_PASSED',flush=True)
    raise SystemExit(0)


from shoulders_arms_cases import cases,expected_frames,case_parameters


selected=[v for v in cases(quick='--quick' in sys.argv) if '--case' not in sys.argv or v[0]==sys.argv[sys.argv.index('--case')+1]]
if '--case-prefix' in sys.argv:selected=[v for v in selected if v[0].startswith(sys.argv[sys.argv.index('--case-prefix')+1])]
if '--start-at' in sys.argv:
    first=sys.argv[sys.argv.index('--start-at')+1]
    selected=selected[next(i for i,v in enumerate(selected) if v[0]==first):]
rigs=[sys.argv[sys.argv.index('--rig')+1]] if '--rig' in sys.argv else ['demo','mixamo']
reference=OUT if any(OUT.rglob('result.json')) else ROOT/'artifacts/stages/05.1b'
measured_preflight(OUT,[(rig+'/'+name,expected_frames(id,parameters),
                       2 if RENDER else 0) for rig in rigs for name,id,parameters,_ in selected
                       if not (rig=='demo' and id.startswith('shoulder.'))],reference=reference)
for rig in ('demo','mixamo'):
    if '--rig' in sys.argv and rig!=sys.argv[sys.argv.index('--rig')+1]:continue
    h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
    p=with_shoulders_v1(rp.calibrate_joint_frames(h,avatar_id='shoulders-arms.'+rig,recorded_at='2026-10-26',include_head_aim=True))
    catalog=catalog_for_profile(p);base=OUT/rig;base.mkdir(exist_ok=True)
    enforce(base);atomic_json(base/'schemas.json',{id:__import__('avatar_app.movement_library.registry',fromlist=['parameter_schema']).parameter_schema(catalog.definitions[id]) for id in IDS})
    profile_path=base/'profile.json'
    if profile_path.exists() and c.loads(c.AvatarProfile,profile_path.read_text(encoding='utf-8'))!=p:
        raise RuntimeError('Calibrated profile changed; preserve accepted bundles before migrating their profile')
    if not profile_path.exists():profile_path.write_text(c.dumps(p),encoding='utf-8')
    write_source_identity(base,rig)
    review_path=base/('mechanics-review.json' if VALIDATE_ONLY else 'execution-review.json')
    summary[rig]=json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else {}
    for name,id,parameters,pose in selected:
        out=base/name
        if '--resume' in sys.argv and render_complete(out,('front','side')):
            summary[rig][name]={'status':'reused'};continue
        h.rig.animation_data_clear()
        for bone in h.rig.pose.bones:bone.matrix_basis.identity()
        fixture=ROOT/'tests/fixtures'/('shoulders_arms/v1' if pose in ('overhead','shoulders-bent','cross-body-clearance') else 'movement_fragments/v1')/('entry-'+pose+'.json')
        load_entry(h,fixture)
        entry=capture_entry(h,p);obj=h.rig.matrix_world.copy()
        parameters=case_parameters(name,parameters,entry,p)
        try:
            instance=instantiate_movement(id,parameters,instance_id='arm.1',profile=p,entry_state=entry,catalog=catalog)
            fragment=build_fragment(instance,entry,p,(Surface(),),catalog);motion=prepare_fragment(fragment,entry,p)
        except c.MotionContractError as error:
            if id.startswith('shoulder.') and rig=='demo' and error.code=='MISSING_CAPABILITY':
                summary[rig][name]={'status':'unavailable_on_rig','error':error.to_dict()};continue
            raise
        try:result=build_action(h,motion,profile=p)
        except Exception as error:
            atomic_json(OUT/'development-failure.json',{'rig':rig,'case':name,'error':str(error),'review':getattr(error,'review',None)})
            print('ARM_EXECUTION_FAILED',rig,name,str(error),flush=True);raise
        assert result['review']['passed']
        assert h.rig.matrix_world==obj
        initial={v.control_id:v.value for v in entry.measured_controls};elbow=0;unrelated=0
        active=('left','right') if parameters.get('side','left')=='both' else (parameters.get('side','left'),)
        for sample in result['samples']:
            for side in ('left','right'):
                error=abs(sample['measured'][side+'.elbow.flexion']-initial[side+'.elbow.flexion'])
                if id not in ('arm.fold','arm.reach','arm.stroke'):elbow=max(elbow,error);assert error<.5,(name,side,'elbow',error)
                if side not in active:
                    error=value_error(tuple(sample['measured'][side+'.hand.position']),initial[side+'.hand.position'],'vector')
                    unrelated=max(unrelated,error);assert error<.002
        summary[rig][name]={'status':'passed','frames':result['frames'],'elbow_preservation_deg':elbow,'other_hand_m':unrelated,
                            'tracking_max':max(v for s in result['samples'] for v in s['tracking_errors'].values()),
                            'producer_sha256':PRODUCER,
                            'input_sha256':hashlib.sha256(''.join(c.dumps(v) for v in (p,entry,instance,fragment,motion)).encode()).hexdigest(),
                            'min_clearance_m':min(v for s in result['samples'] for v in s.get('arm_clearance_m',{}).values())}
        if input_identity(out)['producer_sha256']!=PRODUCER:raise RuntimeError('Producer source changed during validation; rerun this case')
        if VALIDATE_ONLY:
            atomic_json(review_path,summary[rig]);print('SHOULDERS_ARMS_MEASURED',rig,name,result['frames'],flush=True);continue
        out.mkdir(exist_ok=True)
        for filename,record in (('entry',entry),('instance',instance),('fragment',fragment),('executable',motion)):
            (out/(filename+'.json')).write_text(c.dumps(record),encoding='utf-8')
        atomic_json(out/'result.json',result,compact=True)
        views={'front':render(h,p,out),'side':render(h,p,out,True)} if RENDER else {}
        h.scene.frame_set(1);save_scene(out/'preview.blend')
        write_manifest(out,h.scene,views=views,metadata=entry_metadata('entry-'+pose+'.json',parameters,h.scene),complete=RENDER)
        atomic_json(review_path,summary[rig])
        atomic_json(OUT/'execution-review.json',summary)
        print('SHOULDERS_ARMS_PASSED',rig,name,result['frames'],flush=True)
    atomic_json(review_path,summary[rig]);discard_avatar(h)
atomic_json(OUT/('mechanics-review.json' if VALIDATE_ONLY else 'execution-review.json'),summary)
print('ALL_SHOULDERS_ARMS_CHECKS_PASSED',flush=True)
