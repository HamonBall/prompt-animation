"""Bounded ownership journal for verified videos before manifest publication."""
import hashlib
import json
from pathlib import Path
import re
from tools.artifact_store import atomic_json,atomic_replace,digest
from tools.storage_policy import confined,active_writer,MiB

OWNER='lossless-evidence-v1'
NAME='media-build.json'


def valid_view(view):
    if not isinstance(view,str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',view):
        raise ValueError('Invalid evidence view identifier')
    return view


def source_identity(source,fps,fps_base):
    return hashlib.sha256(json.dumps([source,fps,fps_base],sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _json(path,default):
    if not path.exists():return default
    if path.stat().st_size>8*MiB:raise RuntimeError('Oversized media transaction metadata')
    return json.loads(path.read_text(encoding='utf-8'))


def _load(directory):
    value=_json(directory/NAME,{'owner':OWNER,'views':{},'owned':{},'pending':None,'retired_bytes':0})
    if value.get('owner')!=OWNER:raise RuntimeError('Unknown media transaction owner')
    return value


def _video(directory,name,sha):
    path=confined(directory/name)
    match=re.fullmatch(r'([a-z][a-z0-9_-]{0,63})-([0-9a-f]{64})\.mkv',path.name)
    if path.parent!=directory or not match or match[2]!=sha:raise ValueError('Invalid owned video reference')
    return path


def _references(directory,value):
    manifest=_json(directory/'preview-manifest.json',{})
    references={v['media']['path'] for v in manifest.get('views',{}).values() if isinstance(v,dict) and 'media' in v}
    retirement=_json(directory/'media-retirement.json',{})
    if retirement:
        if retirement.get('owner')!=OWNER:raise RuntimeError('Unknown media retirement owner')
        references.update(retirement.get('current_media',{}))
    references.update(v['media']['path'] for v in value['views'].values())
    return references


def resume_build(directory):
    directory=confined(directory)
    if active_writer(directory):raise RuntimeError('Active media writer')
    path=directory/NAME
    if not path.exists():return _load(directory)
    value=_load(directory);changed=False;pending=value.get('pending')
    if pending:
        view=valid_view(pending['view']);media=pending['entry']['media']
        target=_video(directory,media['path'],media['sha256'])
        candidate=confined(directory/pending['candidate'])
        if candidate.parent!=directory or candidate.name!='.'+view+'.pending.mkv':raise ValueError('Invalid media candidate')
        if target.exists():
            if digest(target)!=media['sha256']:raise RuntimeError('Published candidate video changed')
            if candidate.exists():
                if digest(candidate)!=media['sha256']:raise RuntimeError('Pending video changed')
                candidate.unlink()
        else:
            if not candidate.exists() or digest(candidate)!=media['sha256']:raise RuntimeError('Verified pending video missing or changed')
            atomic_replace(candidate,target)
        value['owned'][target.name]=media['sha256'];value['views'][view]=pending['entry'];value['pending']=None
        atomic_json(path,value);changed=True
    references=_references(directory,value)
    # Every obsolete file was enumerated with its hash before publication.
    # Keep current manifest, current retirement and latest candidate references.
    for name,sha in list(value['owned'].items()):
        if name in references:continue
        video=_video(directory,name,sha)
        if video.exists():
            if digest(video)!=sha:raise RuntimeError('Owned obsolete video changed')
            value['retired_bytes']+=video.stat().st_size;video.unlink()
        del value['owned'][name];changed=True
    if changed:atomic_json(path,value)
    return value


def cached_media(directory,view,source_id):
    directory=confined(directory);valid_view(view);value=resume_build(directory)
    entry=value['views'].get(view)
    if not entry or entry['source_id']!=source_id:return None
    media=entry['media'];path=_video(directory,media['path'],media['sha256'])
    return media if path.exists() and digest(path)==media['sha256'] else None


def prepare_publication(directory,view,source,media,candidate):
    """Durably record both rename endpoints before publishing a verified movie."""
    directory=confined(directory);valid_view(view);value=resume_build(directory)
    candidate=confined(candidate)
    if candidate.parent!=directory or candidate.name!='.'+view+'.pending.mkv':raise ValueError('Unowned media candidate')
    if media.get('owner')!=OWNER or not media.get('verified'):raise RuntimeError('Video lacks verification')
    _video(directory,media['path'],media['sha256'])
    if digest(candidate)!=media['sha256']:raise RuntimeError('Verified video changed before publication')
    if len(source)!=len(media['frames']):raise ValueError('Frame source count mismatch')
    for item,frame in zip(source,media['frames']):
        expected=Path(view)/(str(frame).zfill(4)+'.png')
        if Path(item['path'])!=expected:raise ValueError('Unowned source frame')
    entry={'source_id':source_identity(source,media['fps'],media['fps_base']),'media':media,
           'png_sha256':[v['sha256'] for v in source],'png_bytes':[v['bytes'] for v in source]}
    value['pending']={'view':view,'candidate':candidate.name,'entry':entry}
    atomic_json(directory/NAME,value)


def published_frame_plans(directory):
    """Recover PNG retirement if the process stopped just after manifest commit."""
    directory=confined(directory);value=resume_build(directory);manifest=_json(directory/'preview-manifest.json',{})
    if not manifest.get('complete'):return []
    plans=[]
    for view,details in manifest.get('views',{}).items():
        media=details.get('media');entry=value['views'].get(view)
        if not media or not entry or entry['media']!=media:continue
        plan=[]
        for frame,sha,size in zip(media['frames'],entry['png_sha256'],entry['png_bytes']):
            relative=Path(view)/(str(frame).zfill(4)+'.png');path=confined(directory/relative)
            if path.exists():
                if digest(path)!=sha:raise RuntimeError('Source PNG changed after video verification')
                plan.append({'path':relative.as_posix(),'sha256':sha,'bytes':size})
        if plan:plans.append(plan)
    return plans
