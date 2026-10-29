"""Disposable Blender verification/extraction worker; never regenerates motion."""
import argparse
import json
from pathlib import Path
import sys
import traceback

import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tools.artifact_store import atomic_json,digest
from tools.blender_artifact_worker import signature,verify_saved_measurements,hashed
from tools.artifact_bundle import trajectory,write_bundle,open_bundle,static_identity,check_supported,capture_state


def rendered_proof(directory,folder,phase):
    """Compare decoded pixels at entry, midpoint and exit for boundary pilots."""
    if directory.name not in ('nod-default','torso.wave.max','pelvis.shift.max','single-spine'):return None
    import hashlib
    from array import array
    scene=bpy.context.scene;current,sub=scene.frame_current,scene.frame_subframe
    values={}
    try:
        for frame in sorted({scene.frame_start,(scene.frame_start+scene.frame_end)//2,scene.frame_end}):
            scene.frame_set(frame);path=folder/(phase+'-'+str(frame)+'.png')
            scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)
            image=bpy.data.images.load(str(path),check_existing=False)
            values[str(frame)]={'size':list(image.size),'pixels_sha256':hashlib.sha256(array('f',image.pixels[:]).tobytes()).hexdigest()}
            bpy.data.images.remove(image)
    finally:scene.frame_set(current,subframe=sub)
    return values


def compact_signature(sig):
    return {k:v for k,v in sig.items() if k not in ('poses','material_names','cameras')}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--job',type=Path,required=True)
    parser.add_argument('--mode',choices=('accepted','extract','verify'),required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);job=json.loads(args.job.read_text(encoding='utf-8'))
    source=Path(job['source']);directory=Path(job['directory']);trace=Path(job['trajectory'])
    try:
        if args.mode in ('accepted','extract'):
            if digest(source)!=job['source_sha256']:raise RuntimeError('Original scene changed')
            bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False,use_scripts=False)
            check_supported();sig=signature()
            if args.mode=='accepted':
                numeric=verify_saved_measurements(directory)
                bpy.context.scene.frame_set(sig['current_frame'])
                samples=trajectory(trace)
                rendered=rendered_proof(directory,args.report.parent,'original')
                manifest,_=write_bundle(directory,migration=True,original_scene={'path':str(source),'sha256':job['source_sha256']},source_signature=sig,authorization=job.get('lease'))
                value={'source_sha256':job['source_sha256'],'signature':compact_signature(sig),
                       'numeric_error':numeric,'playback':samples,'trajectory_sha256':digest(trace),
                       'prepared_bundle':True,'asset':manifest['asset'],'motion':manifest['motion'],'rendered':rendered}
            else:
                accepted=json.loads(Path(job['accepted']).read_text(encoding='utf-8'))
                if accepted['source_sha256']!=job['source_sha256'] or digest(trace)!=accepted['trajectory_sha256']:
                    raise RuntimeError('Accepted verification no longer matches source')
                manifest,before=write_bundle(directory,migration=True,original_scene={'path':str(source),'sha256':job['source_sha256']},authorization=job.get('lease'))
                pending=directory/'preview-manifest.pending.json'
                # The orchestrator owns manifest publication. The writer creates
                # a candidate only in migration mode.
                value={'source_sha256':job['source_sha256'],'asset':manifest['asset'],'motion':manifest['motion'],
                       'pending_manifest':str(pending),'signature':compact_signature(before)}
        else:
            accepted=json.loads(Path(job['accepted']).read_text(encoding='utf-8'))
            pending=directory/'preview-manifest.pending.json'
            manifest=open_bundle(directory,manifest_path=pending if pending.exists() else None)
            check_supported();sig=signature();original=accepted['signature']
            state,_=capture_state()
            if state!=manifest['state']:raise RuntimeError('Saved custom/pose/object/view state mismatch')
            for key in ('rig','action','timing','rest','geometry','materials','images','asset_exact','current_frame','active_action_name','slot_identifier'):
                if sig[key]!=original[key]:raise RuntimeError('Saved bundle mismatch: '+key)
            samples=trajectory(trace,expected=True)
            rendered=rendered_proof(directory,args.report.parent,'bundle')
            if rendered!=accepted.get('rendered'):raise RuntimeError('Decoded representative render pixels differ')
            numeric=verify_saved_measurements(directory)
            value={'numeric_error':numeric,'playback':samples,'static_hash':static_identity(sig)[0],
                   'active_action':sig['active_action_name'],'slot':sig['slot_identifier'],'timing':sig['timing'],'rendered':rendered}
        atomic_json(args.report,{'passed':True,**value})
    except Exception as error:
        atomic_json(args.report,{'passed':False,'error':str(error)})
        traceback.print_exc();raise


if __name__=='__main__':main()
