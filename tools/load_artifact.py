"""Open/play a stored v1 scene or v2 bundle; optionally export an owned standalone."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]


def export_standalone(directory,target,*,temporary=False):
    import bpy
    from tools.artifact_store import open_preview,save_standalone,atomic_json,digest
    from tools.storage_policy import ARTIFACTS,confined,enforce,MiB
    target=confined(target);directory=Path(directory)
    if target.exists():raise RuntimeError('Explicit exports do not overwrite existing deliverables')
    if temporary:
        if '.scratch' not in target.parts:raise RuntimeError('Temporary export must be owned scratch')
    elif not target.is_relative_to(ARTIFACTS/'exports'):raise RuntimeError('Standalone exports belong in artifacts/exports')
    owned=list((ARTIFACTS/'exports').rglob('*.blend')) if (ARTIFACTS/'exports').exists() else []
    if not temporary and len(owned)>=2:raise RuntimeError('Two standalone exports already retained')
    estimate=96*MiB
    enforce(target.parent,growth=estimate,temporary=estimate,migration=temporary)
    open_preview(directory)
    bpy.ops.object.make_local(type='ALL')
    for collection in (bpy.data.objects,bpy.data.meshes,bpy.data.armatures,bpy.data.materials,bpy.data.images,
                       bpy.data.actions,bpy.data.worlds,bpy.data.collections,bpy.data.node_groups,bpy.data.cameras,bpy.data.lights):
        for data in list(collection):
            if data.library:data.make_local()
    # Appending actions retains a library weak-reference record even though all
    # IDs are local. Remove that record only after excluding real linked users.
    linked=[data for data in bpy.data.user_map() if getattr(data,'library',None)]
    if linked:raise RuntimeError('Export still has linked IDs: '+','.join(d.name for d in linked))
    for library in list(bpy.data.libraries):bpy.data.libraries.remove(library,do_unlink=True)
    result=save_standalone(target)
    if result['bytes']>256*MiB or sum(p.stat().st_size for p in owned)+result['bytes']>256*MiB:
        target.unlink();raise RuntimeError('Standalone export budget exceeded')
    atomic_json(target.with_suffix('.export.json'),{'owner':'artifact-storage-v2','temporary':temporary,
                'bytes':result['bytes'],'sha256':digest(target),'source_case':str(directory)})
    return result


def main():
    import bpy
    from tools.artifact_store import open_preview,resolve_historical
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',type=Path,required=True)
    parser.add_argument('--export',type=Path);parser.add_argument('--temporary',action='store_true')
    parser.add_argument('--report',type=Path)
    parser.add_argument('--extract-view');parser.add_argument('--frames-output',type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    args.case=resolve_historical(args.case)
    if args.extract_view:
        if not args.frames_output:parser.error('--extract-view requires --frames-output in .scratch')
        from tools.lossless_evidence import decode_view
        value=decode_view(args.case,args.extract_view,args.frames_output)
    elif args.export:value=export_standalone(args.case,args.export,temporary=args.temporary)
    else:
        h=open_preview(args.case)
        value={'rig':h.rig.name,'action':h.rig.animation_data.action.name,'slot':h.rig.animation_data.action_slot.identifier,
               'frames':[h.scene.frame_start,h.scene.frame_end],'current_frame':h.scene.frame_current,
               'libraries':[{'path':lib.filepath,'users':lib.users} for lib in bpy.data.libraries]}
    if args.report:
        from tools.artifact_store import atomic_json
        atomic_json(args.report,value)
    if not bpy.app.background:
        for area in bpy.context.screen.areas:
            if area.type=='VIEW_3D':area.spaces.active.region_3d.view_perspective='CAMERA'
    print('STORED_ARTIFACT_READY',json.dumps(value),flush=True)


if __name__=='__main__':main()
