"""Fresh native leg case through the shared transaction and bundle writer."""
from pathlib import Path
import sys,time,json,math
from dataclasses import replace
import bpy
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action,set_contact
from avatar_app.blender.kinematics import solve_leg
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.legs import IDS,with_legs_v1
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment
from avatar_app.movement_library.registry import parameter_schema
from avatar_app.motion import Surface,ContactConstraint
from tools.preview_movement import capture_entry,load_entry
from tools import artifact_store as store
from tools.storage_policy import enforce
from hips_knees_cases import cases


def fixture(h,p,pose,side):
    load_entry(h,ROOT/'tests/fixtures/movement_fragments/v1/entry-neutral.json')
    if 'turned' in pose:
        rig=h.rig;rig.matrix_world=Matrix.Rotation(math.pi/2,4,'Z') @ rig.matrix_world;bpy.context.view_layer.update()
    if 'crouched' in pose:
        feet={s:(h.bones[s+'Foot'].head.copy(),h.bones[s+'Foot'].matrix.to_quaternion().copy()) for s in ('Left','Right')}
        pelvis=h.bones['Hips'];m=pelvis.matrix.copy();m.translation-=h.rig.matrix_world.inverted().to_3x3() @ Vector((0,0,.035*p.height_m));pelvis.matrix=m;bpy.context.view_layer.update()
        for s,(head,q) in feet.items():set_contact(h,ContactConstraint(s.lower()+'_foot'),head,q)
    if 'raised' in pose:
        s=side.title();foot=h.bones[s+'Foot'];q=foot.matrix.to_quaternion().copy()
        basis=rp.semantic_frame(h,p,'pelvis').to_3x3();delta=basis @ Vector((0,.035*p.height_m,.12*p.height_m))
        target=foot.head+h.rig.matrix_world.inverted().to_3x3() @ delta
        solve_leg(h,s,target,pole=h.rig.matrix_world.inverted().to_3x3() @ basis.col[1])
        foot.matrix=Matrix.Translation(foot.head) @ q.to_matrix().to_4x4();bpy.context.view_layer.update()
    entry=capture_entry(h,p)
    if 'raised' in pose:entry=replace(entry,active_contacts=tuple(x for x in entry.active_contacts if x!=side+'.sole'))
    return entry


def main():
    started=time.perf_counter();name=sys.argv[sys.argv.index('--case')+1];rig=sys.argv[sys.argv.index('--rig')+1]
    _,id,params,pose=next(row for row in cases() if row[0]==name)
    out=ROOT/'artifacts/stages/05.4'/rig/name
    if '--output-dir' in sys.argv:out=Path(sys.argv[sys.argv.index('--output-dir')+1]).resolve()
    assert out.resolve().is_relative_to((ROOT/'artifacts/stages/05.4').resolve())
    enforce(out,growth=6*1024**2,temporary=32*1024**2)
    producer=store.input_identity(out)['producer_sha256']
    harness={path:store.digest(ROOT/path) for path in ('tests/blender_movement_hips_knees.py','tests/hips_knees_cases.py')}
    with store.producer_lease(out):
        h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
        p=with_legs_v1(rp.calibrate_joint_frames(h,avatar_id='legs.'+rig,recorded_at='2026-11-02',include_head_aim=True))
        catalog=catalog_for_profile(p);base=out.parent
        if (base/'profile.json').exists():assert c.loads(c.AvatarProfile,(base/'profile.json').read_text())==p
        else:(base/'profile.json').write_text(c.dumps(p),encoding='utf-8')
        if not (base/'source.json').exists():store.write_source_identity(base,rig)
        if not (base/'schemas.json').exists():store.atomic_json(base/'schemas.json',{id:parameter_schema(catalog.definitions[id]) for id in IDS})
        entry=fixture(h,p,pose,params.get('side','left'));fingerprint=rp._fingerprint(h)
        topology={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in h.objects if o.type=='MESH'}
        instance=instantiate_movement(id,params,instance_id='legs.1',profile=p,entry_state=entry,catalog=catalog)
        fragment=build_fragment(instance,entry,p,(Surface(),),catalog);motion=prepare_fragment(fragment,entry,p);prepared=time.perf_counter()
        try:result=build_action(h,motion,profile=p)
        except Exception as error:
            store.atomic_json(out/'failed-review.json',{'error':str(error),'report':getattr(error,'review',None),
                'context':error.to_dict() if hasattr(error,'to_dict') else None},compact=True)
            print('LEGS_CASE_FAILED',error.to_dict() if hasattr(error,'to_dict') else getattr(error,'review',str(error)),flush=True)
            raise
        assert result['review']['passed'];executed=time.perf_counter()
        assert fingerprint==rp._fingerprint(h)
        assert topology=={o.name:(len(o.data.vertices),len(o.data.polygons)) for o in h.objects if o.type=='MESH'}
        result['stage_05_4']={'case':name,'rig':rig,'fixture':pose,'no_topology_or_rest_change':True,
            'application_producer_sha256':producer,'stage_producer':harness,
            'timings_s':{'load_prepare':prepared-started,'execution_measurement':executed-prepared}}
        assert producer==store.input_identity(out)['producer_sha256'],'Application changed during native execution'
        assert all(store.digest(ROOT/path)==sha for path,sha in harness.items()),'Harness changed during native execution'
        for filename,record in (('entry',entry),('instance',instance),('fragment',fragment),('executable',motion)):
            (out/(filename+'.json')).write_text(c.dumps(record),encoding='utf-8')
        store.atomic_json(out/'result.json',result,compact=True)
        h.scene.frame_set(1);store.save_scene(out/'preview.blend')
        store.write_manifest(out,h.scene,metadata=store.entry_metadata('authored:'+pose,params,h.scene),complete=False)
        print('LEGS_NUMERIC_PASSED',rig,name,result['frames'],result['review'],flush=True)


if __name__=='__main__':main()
