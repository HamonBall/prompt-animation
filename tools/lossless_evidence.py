"""Lossless FFV1 evidence using Blender's bundled encoder; no external binary."""
from array import array
import hashlib
import json
import os
from pathlib import Path
import tempfile

from tools.artifact_store import atomic_json,atomic_replace,digest
from tools.storage_policy import confined,enforce,active_writer
from tools.media_transaction import valid_view,source_identity,cached_media,prepare_publication,resume_build,published_frame_plans

OWNER='lossless-evidence-v1'


def pixel_identity(path):
    import bpy
    image=bpy.data.images.load(str(path),check_existing=False)
    try:return {'size':list(image.size),'sha256':hashlib.sha256(array('f',image.pixels[:]).tobytes()).hexdigest()}
    finally:bpy.data.images.remove(image)


def video_scene(width,height,frames,fps,fps_base):
    import bpy
    scene=bpy.data.scenes.new('Owned lossless evidence')
    scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=width;scene.render.resolution_y=height
    scene.render.resolution_percentage=100;scene.render.fps=fps;scene.render.fps_base=fps_base
    scene.frame_start=1;scene.frame_end=frames;scene.view_settings.view_transform='Standard'
    scene.view_settings.look='None';scene.render.dither_intensity=0
    return scene


def encode_view(directory,view,frames,*,fps,fps_base=1):
    """Return a verified media record and retirement plan; leave PNGs intact."""
    import bpy
    directory=confined(directory);valid_view(view);resume_build(directory)
    if active_writer(directory):raise RuntimeError('Active evidence producer')
    frames=list(frames)
    if not frames or len(frames)>1801 or frames!=list(range(frames[0],frames[-1]+1)):
        raise ValueError('Evidence requires a bounded contiguous frame range')
    paths=[confined(directory/view/(str(n).zfill(4)+'.png')) for n in frames]
    source=[{'path':str(p.relative_to(directory)),'bytes':p.stat().st_size,'sha256':digest(p)} for p in paths]
    cached=cached_media(directory,view,source_identity(source,fps,fps_base))
    if cached and media_complete(directory,cached,frames,fps=fps,fps_base=fps_base):return cached,source
    identities=[pixel_identity(p) for p in paths];width,height=identities[0]['size']
    if any(v['size']!=[width,height] for v in identities):raise RuntimeError('Mixed frame dimensions')
    reserve=width*height*len(frames)*8+16*1024**2
    enforce(directory,growth=reserve,temporary=reserve)
    scratch=directory/'.scratch';scratch.mkdir(exist_ok=True)
    scene=video_scene(width,height,len(frames),fps,fps_base);clip=None;publication_prepared=False
    candidate=directory/('.'+view+'.pending.mkv')
    try:
        with tempfile.TemporaryDirectory(dir=scratch,prefix='ffv1-') as temporary:
            temporary=Path(temporary).resolve();assert temporary.is_relative_to(scratch.resolve())
            scene.render.image_settings.media_type='VIDEO';scene.render.image_settings.file_format='FFMPEG'
            scene.render.ffmpeg.format='MKV';scene.render.ffmpeg.codec='FFV1';scene.render.image_settings.color_mode='RGBA'
            scene.render.filepath=str(candidate)
            editor=scene.sequence_editor_create();strip=editor.strips.new_image('PNG source',str(paths[0]),channel=1,frame_start=1)
            for p in paths[1:]:strip.elements.append(p.name)
            strip.frame_final_duration=len(paths)
            bpy.ops.render.render(animation=True,scene=scene.name)
            clip=bpy.data.movieclips.load(str(candidate))
            if clip.frame_duration!=len(paths) or abs(clip.fps-fps/fps_base)>1e-4:
                raise RuntimeError('Video frame count/timing mismatch')
            editor.strips.remove(strip);editor.strips.new_movie('Decoded video',str(candidate),channel=1,frame_start=1)
            scene.render.image_settings.media_type='IMAGE';scene.render.image_settings.file_format='PNG'
            scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.compression=100
            scene.render.filepath=str(temporary)+'/'
            bpy.ops.render.render(animation=True,scene=scene.name)
            observed=[pixel_identity(temporary/(str(i+1).zfill(4)+'.png')) for i in range(len(paths))]
            if identities!=observed:raise RuntimeError('Decoded FFV1 pixels differ; retain all PNG originals')
            # Release Windows movie handles before publishing/cleaning scratch.
            bpy.data.scenes.remove(scene);scene=None;bpy.data.movieclips.remove(clip);clip=None
        with candidate.open('r+b') as stream:os.fsync(stream.fileno())
        sha=digest(candidate);target=directory/(view+'-'+sha+'.mkv')
        record={'owner':OWNER,'representation':'ffv1_mkv','path':target.name,'sha256':sha,'codec':'FFV1',
                'frames':frames,'fps':fps,'fps_base':fps_base,'size':[width,height],
                'decoded_pixel_sha256':[v['sha256'] for v in identities],'verified':True}
        prepare_publication(directory,view,source,record,candidate)
        publication_prepared=True
        resume_build(directory)
        return record,source
    finally:
        if scene is not None:bpy.data.scenes.remove(scene)
        if clip is not None:bpy.data.movieclips.remove(clip)
        if not publication_prepared:candidate.unlink(missing_ok=True)


def media_complete(directory,media,expected_frames,*,fps,fps_base):
    directory=Path(directory)
    if not (media.get('owner')==OWNER and media.get('representation')=='ffv1_mkv' and media.get('verified')
            and media.get('codec')=='FFV1' and media.get('frames')==expected_frames
            and len(media.get('decoded_pixel_sha256',[]))==len(expected_frames)
            and media.get('fps')==fps and media.get('fps_base')==fps_base):return False
    path=confined(directory/media['path'])
    return path.parent==directory and path.is_file() and digest(path)==media['sha256']


def retire_pngs(directory,plans):
    """Only retire enumerated unchanged PNGs after durable manifest publication."""
    directory=confined(directory);manifest=json.loads((directory/'preview-manifest.json').read_text())
    if active_writer(directory):raise RuntimeError('Active evidence producer')
    from tools.artifact_store import files_complete
    if not manifest['complete'] or not files_complete(directory,manifest):raise RuntimeError('Media manifest is not complete')
    previous=directory/'media-retirement.json'
    old=json.loads(previous.read_text()) if previous.exists() else {}
    if old and old.get('owner')!=OWNER:raise RuntimeError('Unknown media retirement owner')
    current={v['media']['path']:v['media']['sha256'] for v in manifest['views'].values() if 'media' in v}
    files=[item for plan in plans for item in plan]
    for name,sha in old.get('current_media',{}).items():
        if name not in current:
            p=confined(directory/name)
            if p.exists():files.append({'path':name,'sha256':sha,'bytes':p.stat().st_size})
    record={'owner':OWNER,'state':'prepared','current_media':current,'files':files}
    for item in files:_retirable(directory,item,manifest,current)
    atomic_json(previous,record)
    resume_retirement(directory)


def _retirable(directory,item,manifest,current):
    path=confined(directory/item['path']);relative=path.relative_to(directory)
    if path.suffix=='.png':
        if not (len(relative.parts)==2 and relative.parts[0] in manifest['views'] and path.stem.isdecimal()
                and int(path.stem) in manifest['expected_frames']):raise ValueError('Not an owned numbered frame')
    elif not (path.parent==directory and path.name not in current and
              any(path.name==view+'-'+item['sha256']+'.mkv' for view in manifest['views'])):
        raise ValueError('Not an owned superseded video')
    return path


def resume_retirement(directory):
    directory=confined(directory);path=directory/'media-retirement.json'
    if not path.exists():return
    value=json.loads(path.read_text())
    if value.get('owner')!=OWNER or value.get('state')!='prepared':return
    manifest=json.loads((directory/'preview-manifest.json').read_text())
    current={v['media']['path']:v['media']['sha256'] for v in manifest['views'].values() if 'media' in v}
    if current!=value['current_media']:raise RuntimeError('Interrupted media manifest changed')
    from tools.artifact_store import files_complete
    if not files_complete(directory,manifest) or active_writer(directory):raise RuntimeError('Media is no longer safe to retire')
    for item in value['files']:
        p=_retirable(directory,item,manifest,current)
        if p.exists():
            if digest(p)!=item['sha256']:raise RuntimeError('PNG/obsolete video changed during retirement')
            p.unlink()
    atomic_json(path,{'owner':OWNER,'state':'complete','current_media':current,
                      'removed_files':len(value['files']),'removed_bytes':sum(v['bytes'] for v in value['files'])})


def recover_evidence(directory):
    """Reconcile both sides of video publication before checking render resume."""
    directory=confined(directory);resume_build(directory);resume_retirement(directory)
    manifest_path=directory/'preview-manifest.json'
    if not manifest_path.exists():return
    manifest=json.loads(manifest_path.read_text())
    from tools.artifact_store import files_complete
    if manifest.get('complete') and files_complete(directory,manifest):
        plans=published_frame_plans(directory)
        if plans:retire_pngs(directory,plans)
    resume_build(directory)


def decode_view(directory,view,output):
    """Expand one verified view into explicit owned scratch for inspection."""
    import bpy
    from tools.artifact_store import producer_lease
    directory=confined(directory);output=confined(output)
    if '.scratch' not in output.parts:raise ValueError('Decoded frames belong in owned scratch')
    m=json.loads((directory/'preview-manifest.json').read_text());media=m['views'][view]['media']
    if not media_complete(directory,media,m['expected_frames'],fps=m['fps'],fps_base=m['fps_base']):
        raise RuntimeError('Video hash/timing/verification is invalid')
    width,height=media['size'];frames=media['frames']
    enforce(output,temporary=width*height*len(frames)*8+16*1024**2)
    if output.exists() and any(output.iterdir()):raise ValueError('Decode output must be empty')
    with producer_lease(output):
        scene=video_scene(width,height,len(frames),media['fps'],media['fps_base'])
        try:
            editor=scene.sequence_editor_create();editor.strips.new_movie('Verified view',str(directory/media['path']),channel=1,frame_start=frames[0])
            scene.frame_start=frames[0];scene.frame_end=frames[-1]
            scene.render.image_settings.media_type='IMAGE';scene.render.image_settings.file_format='PNG'
            scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.compression=100
            scene.render.filepath=str(output)+'/'
            bpy.ops.render.render(animation=True,scene=scene.name)
            actual=[pixel_identity(output/(str(n).zfill(4)+'.png'))['sha256'] for n in frames]
            if actual!=media['decoded_pixel_sha256']:raise RuntimeError('Decoded media pixel hashes differ')
            atomic_json(output/'decoded.json',{'owner':OWNER,'source':str(directory),'view':view,'frames':frames,'passed':True})
        finally:bpy.data.scenes.remove(scene)
    return {'passed':True,'frames':len(frames),'directory':str(output)}
