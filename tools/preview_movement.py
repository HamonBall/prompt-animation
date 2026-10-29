"""Developer-only, no-model single-fragment preview through the shared executor.

blender -b --factory-startup --python tools/preview_movement.py -- --id test.head_transition
  --version 1 --parameters '{"angle":25}' --rig demo --entry <fixture.json>
  --output-dir <directory> --test-catalog --render
"""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tools.artifact_store import save_scene,write_manifest,entry_metadata,write_source_identity,hold_producer_lease


def read_json(text):
    from avatar_app.movement_library import contracts as c
    if len(text.encode('utf-8'))>c.MAX_JSON_BYTES: c.fail('RESOURCE_LIMIT','Developer JSON exceeds byte budget')
    def pairs(items):
        c.distinct(tuple(key for key,_ in items),None)
        return dict(items)
    try:
        return json.loads(text,object_pairs_hook=pairs,
                          parse_constant=lambda value:c.fail('INVALID_SCHEMA','Nonfinite JSON value'))
    except (ValueError,RecursionError) as error:
        if isinstance(error,c.MotionContractError): raise
        c.fail('INVALID_SCHEMA','Malformed developer JSON')


def load_entry(handle,path):
    from avatar_app.pose import update_pose
    from avatar_app.blender.pose import target_pose
    from avatar_app.movement_library import contracts as c
    path=Path(path)
    if path.stat().st_size>c.MAX_JSON_BYTES: c.fail('RESOURCE_LIMIT','Entry fixture exceeds byte budget')
    data=read_json(path.read_text(encoding='utf-8'))
    if type(data) is not dict or set(data)!={'schema_version','controls','contact'}:
        c.fail('INVALID_SCHEMA','Entry fixture needs schema_version, controls and contact only')
    if type(data['schema_version']) is not int or data['schema_version']!=1:
        c.fail('VERSION_MISMATCH','Unsupported developer entry fixture version')
    plan=update_pose(None,data['controls'],data['contact'])
    target_pose(handle,plan)
    return plan


def capture_entry(handle,profile,revision=1):
    from avatar_app.blender import rig_profile as rp
    from avatar_app.movement_library import contracts as c
    anchors=tuple(c.ContactAnchor(side+'.sole','floor',rp.measure_endpoint(handle,profile,side+'.sole'),'world','metre')
                  for side in ('left','right'))
    return rp.capture_motion_state(handle,profile,revision=revision,captured_time_s=0,
                                  contact_anchors=anchors,active_contacts=tuple(a.anchor_id for a in anchors))


def render_preview(handle,profile,out):
    from tools.movement_evidence import render
    return {view: render(handle,profile,out,side=(view=='side'),width=256) for view in ('front','side')}


def main(argv=None):
    import bpy
    from avatar_app.blender.demo import create_demo_avatar
    from avatar_app.blender.avatar import import_avatar
    from avatar_app.blender.scene import prepare_preview
    from avatar_app.blender import rig_profile as rp
    from avatar_app.blender.motion import build_action
    from avatar_app.movement_library import contracts as c
    from avatar_app.movement_library.registry import CATALOG, get_movement
    from avatar_app.movement_library.compiler import instantiate_movement, build_fragment, prepare_fragment
    from avatar_app.motion import Surface
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id',required=True); parser.add_argument('--version',required=True,type=int)
    params=parser.add_mutually_exclusive_group()
    params.add_argument('--parameters',default=None); params.add_argument('--parameters-file',type=Path)
    parser.add_argument('--rig',required=True)
    parser.add_argument('--entry',type=Path,required=True); parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--test-catalog',action='store_true'); parser.add_argument('--render',action='store_true')
    args=parser.parse_args(argv)
    # Blender resolves render paths relative to its project, not Python's cwd.
    args.output_dir=args.output_dir.resolve()
    catalog=CATALOG
    if args.test_catalog:
        sys.path.insert(0,str(ROOT/'tests'))
        from primitive_fixtures import make_catalog
        catalog=make_catalog()
    get_movement(args.id,args.version,catalog)
    handle=create_demo_avatar() if args.rig=='demo' else import_avatar(str(ROOT/('Hip Hop Mixamo.fbx' if args.rig=='mixamo' else args.rig)))
    prepare_preview(handle)
    load_entry(handle,args.entry)
    profile=rp.calibrate_joint_frames(handle,avatar_id='preview.'+('demo' if args.rig=='demo' else 'import'),
                                     source_revision='developer-preview',recorded_at='2026-10-23',include_head_aim=not args.test_catalog)
    if not args.test_catalog:
        if args.id.startswith(('arm.','shoulder.')):
            from avatar_app.movement_library.limbs import with_shoulders_v1
            profile=with_shoulders_v1(profile)
        if args.id.startswith('pelvis.'):
            from avatar_app.movement_library.torso_pelvis import with_pelvis_v1
            profile=with_pelvis_v1(profile)
        from avatar_app.movement_library.joints import catalog_for_profile
        catalog=catalog_for_profile(profile)
    entry=capture_entry(handle,profile)
    if args.parameters_file and args.parameters_file.stat().st_size>c.MAX_JSON_BYTES:
        c.fail('RESOURCE_LIMIT','Parameter file exceeds byte budget')
    parameters=read_json(args.parameters_file.read_text(encoding='utf-8') if args.parameters_file else args.parameters or '{}')
    instance=instantiate_movement(args.id,parameters,instance_id='preview.1',profile=profile,entry_state=entry,catalog=catalog)
    fragment=build_fragment(instance,entry,profile,(Surface(),),catalog)
    motion=prepare_fragment(fragment,entry,profile)
    from tools.storage_policy import measured_preflight
    import math
    measured_preflight(args.output_dir,[('.',math.ceil(motion.duration_s*motion.fps)+1,2 if args.render else 0)],
                       reference=ROOT/'artifacts/stages/05.1b')
    result=build_action(handle,motion,profile=profile)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    hold_producer_lease(args.output_dir)
    write_source_identity(args.output_dir,args.rig)
    for name,record in (('profile',profile),('entry',entry),('instance',instance),('fragment',fragment),('executable',motion)):
        (args.output_dir/(name+'.json')).write_text(c.dumps(record)+'\n',encoding='utf-8')
    (args.output_dir/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    write_manifest(args.output_dir,handle.scene)
    views=render_preview(handle,profile,args.output_dir) if args.render else {}
    save_scene(args.output_dir/'preview.blend')
    write_manifest(args.output_dir,handle.scene,views=views,metadata=entry_metadata(args.entry,parameters,handle.scene),complete=args.render)
    print('MOVEMENT_PREVIEW_PASSED',args.id,'frames',result['frames'],'output',args.output_dir,flush=True)
    return result


if __name__=='__main__': main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
