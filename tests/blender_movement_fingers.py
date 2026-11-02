"""Fresh per-case native execution through the shared transactional bridge."""
from pathlib import Path
import sys,json,time
from dataclasses import replace
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar,discard_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.fingers import IDS,with_fingers_v1,CURL_MAX
from avatar_app.movement_library.joints import catalog_for_profile,_path,_fragment
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment
from avatar_app.movement_library.registry import parameter_schema
from avatar_app.motion import Surface
from tools.preview_movement import load_entry,capture_entry
from tools import artifact_store as store
from tools.storage_policy import enforce
from finger_cases import cases

OUT=ROOT/'artifacts/stages/05.3b';started=time.perf_counter()
name=sys.argv[sys.argv.index('--case')+1];rig=sys.argv[sys.argv.index('--rig')+1] if '--rig' in sys.argv else 'mixamo'
_,id,parameters,pose=next(row for row in cases() if row[0]==name)
out=OUT/rig/name;enforce(out,growth=6*1024**2,temporary=32*1024**2)
with store.producer_lease(out):
    h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
    p=with_fingers_v1(rp.calibrate_joint_frames(h,avatar_id='fingers.'+rig,recorded_at='2026-11-02',include_head_aim=True))
    catalog=catalog_for_profile(p);base=OUT/rig;base.mkdir(exist_ok=True)
    profile=base/'profile.json'
    if profile.exists():assert c.loads(c.AvatarProfile,profile.read_text())==p,'Profile changed'
    else:profile.write_text(c.dumps(p),encoding='utf-8')
    if not (base/'source.json').exists():store.write_source_identity(base,rig)
    if not (base/'schemas.json').exists():store.atomic_json(base/'schemas.json',{id:parameter_schema(catalog.definitions[id]) for id in IDS})
    fixture=ROOT/('tests/fixtures/shoulders_arms/v1/entry-shoulders-bent.json' if pose=='bent-turned' else 'tests/fixtures/movement_fragments/v1/entry-neutral.json')
    load_entry(h,fixture);entry=capture_entry(h,p)
    initial_topology={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in h.objects if o.type=='MESH'}
    initial_bones=[b.name for b in h.rig.data.bones];fingerprint=rp._fingerprint(h)
    instance=instantiate_movement(id,parameters,instance_id='detail.1',profile=p,entry_state=entry,catalog=catalog)
    fragment=build_fragment(instance,entry,p,(Surface(),),catalog)
    if pose=='sequence':
        # One explicit authored fixture, not a recipe scheduler: open -> fist -> point.
        values={x.control_id:x.value for x in entry.measured_controls};paths={}
        for key in (t.control_id for t in fragment.tracks if t.control_id.endswith('.curl')):
            digit=key.split('.')[2]
            targets=[0,.72*CURL_MAX[digit],0 if digit=='index' else .72*CURL_MAX[digit]] if key.endswith('.curl') else [0,0,0]
            paths[key],end=_path(values[key],targets,1.5,.1,'return_to_entry')
        fragment=_fragment(instance,entry,p,paths,end,(c.PhaseLandmark('open',1.5),c.PhaseLandmark('fist',3.1),c.PhaseLandmark('point',4.7),c.PhaseLandmark('end',end)))
    motion=prepare_fragment(fragment,entry,p);prepared=time.perf_counter()
    result=build_action(h,motion,profile=p);assert result['review']['passed'];executed=time.perf_counter()
    assert initial_bones==[b.name for b in h.rig.data.bones] and fingerprint==rp._fingerprint(h)
    assert initial_topology=={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in h.objects if o.type=='MESH'}
    result['stage_05_3b']={'case':name,'fixture':pose,'no_topology_or_rest_skeleton_change':True,
        'source_identity':store.input_identity(out)['producer_sha256'],
        'stage_producer':{str(Path(__file__).relative_to(ROOT)):store.digest(Path(__file__)),
                          'tests/finger_cases.py':store.digest(ROOT/'tests/finger_cases.py')},
        'timings_s':{'startup_load_prepare':prepared-started,'execution_measurement':executed-prepared}}
    for filename,record in (('entry',entry),('instance',instance),('fragment',fragment),('executable',motion)):
        (out/(filename+'.json')).write_text(c.dumps(record),encoding='utf-8')
    store.atomic_json(out/'result.json',result,compact=True)
    h.scene.frame_set(1);store.save_scene(out/'preview.blend')
    store.write_manifest(out,h.scene,metadata=store.entry_metadata(str(fixture),parameters,h.scene),complete=False)
    enforce(out)
    print('FINGERS_NUMERIC_PASSED',rig,name,result['frames'],result['review'],flush=True)
