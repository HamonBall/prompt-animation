"""Filesystem accounting, bounded retention and write budgets for artifact bundles."""
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=ROOT/'artifacts'
MiB=1024**2
GiB=1024**3
LIMITS={'global':4*GiB,'assets':512*MiB,'maintenance':256*MiB,'case':8*MiB,
        'stage':512*MiB,'05.1b':GiB,'temporary':512*MiB,'exports':256*MiB,'failures':128*MiB}


def confined(path,root=ARTIFACTS):
    path=Path(os.path.abspath(path));root=Path(os.path.abspath(root))
    if not path.is_relative_to(root):raise ValueError('Path escapes artifact root: '+str(path))
    for part in (path,*path.parents):
        if part.is_symlink() or part.is_junction():raise ValueError('Link/junction refused: '+str(part))
    if path.resolve()!=path:raise ValueError('Path does not resolve in place: '+str(path))
    return path


def classification(path,root=ARTIFACTS):
    p=Path(path);relative=p.relative_to(root);parts=relative.parts
    return _classification(parts,p.suffix)


def _classification(parts,suffix):
    name=parts[-1]
    if 'assets'==parts[0]:return 'shared_asset'
    if suffix=='.blend1':return 'historical_backup'
    if '.scratch' in parts or name.endswith('.f32.gz') or '.pending.' in name or name.startswith(('.candidate-','.compact-','.preview.')):return 'scratch'
    if parts[0]=='maintenance':return 'maintenance'
    if parts[0]=='exports':return 'export'
    if suffix=='.blend':return 'motion' if name=='motion.blend' else 'standalone_scene'
    if suffix=='.png':return 'sheet' if name.endswith('-sheet.png') else 'frame' if name[:-4].isdigit() else 'visual'
    if suffix=='.mkv':return 'lossless_sequence'
    if suffix=='.json':return 'measurements_metadata'
    return 'diagnostic'


def inventory(root=ARTIFACTS,*,hash_candidates=False):
    from tools.artifact_store import digest,process_alive
    root=confined(root,root);files={};leases=[]
    def visit(directory,parts=()):
        with os.scandir(directory) as entries:
            for entry in entries:
                child_parts=(*parts,entry.name);s=entry.stat(follow_symlinks=False)
                if entry.is_symlink() or getattr(s,'st_file_attributes',0)&0x400:
                    raise ValueError('Link/junction refused: '+entry.path)
                if entry.is_dir(follow_symlinks=False):visit(entry.path,child_parts);continue
                rel='/'.join(child_parts);suffix=Path(entry.name).suffix
                if entry.name=='.artifact-writer.lock':
                    try:
                        owner=json.loads(Path(entry.path).read_text(encoding='utf-8'))
                        leases.append({'path':entry.path,'pid':owner['pid'],'active':process_alive(owner['pid'])})
                    except Exception as e:leases.append({'path':entry.path,'active':True,'error':str(e)})
                record={'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'class':_classification(child_parts,suffix)}
                if hash_candidates and (suffix in ('.blend','.blend1') or record['class']=='maintenance'):
                    record['sha256']=digest(entry.path)
                files[rel]=record
    if root.exists():visit(root)
    by_ext=defaultdict(lambda:{'bytes':0,'files':0});by_class=defaultdict(lambda:{'bytes':0,'files':0});by_stage=defaultdict(lambda:{'bytes':0,'files':0})
    for rel,v in files.items():
        parts=rel.split('/');ext=Path(parts[-1]).suffix
        for table,key in ((by_ext,ext),(by_class,v['class']),(by_stage,parts[1] if len(parts)>1 and parts[0]=='stages' else parts[0])):
            table[key]['bytes']+=v['bytes'];table[key]['files']+=1
    total=sum(v['bytes'] for v in files.values())
    return {'bytes':total,'file_count':len(files),'free_bytes':shutil.disk_usage(root if root.exists() else root.parent).free,
            'by_extension':dict(by_ext),'by_class':dict(by_class),'by_stage':dict(by_stage),'leases':leases,'files':files}


def active_writer(directory,root=ARTIFACTS,authorization=None):
    from tools.artifact_store import process_alive
    directory=confined(directory,root)
    for parent in (directory,*directory.parents):
        if not parent.is_relative_to(root):break
        lock=parent/'.artifact-writer.lock'
        if lock.is_file():
            owner=json.loads(lock.read_text(encoding='utf-8'))
            delegated=bool(authorization and owner.get('token')==authorization.get('token') and owner['pid']==authorization.get('pid'))
            if owner['pid']!=os.getpid() and not delegated and process_alive(owner['pid']):return str(lock)
    return None


def fingerprint(files):
    return hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def temporary_bytes(root):
    total=0
    def visit(directory,scratch=False):
        nonlocal total
        with os.scandir(directory) as entries:
            for entry in entries:
                s=entry.stat(follow_symlinks=False)
                if entry.is_symlink() or getattr(s,'st_file_attributes',0)&0x400:raise ValueError('Reparse path in temporary inventory')
                if entry.is_dir(follow_symlinks=False):
                    child_scratch=scratch or entry.name=='.scratch'
                    if not child_scratch and entry.name in ('front','side','frames'):continue
                    visit(entry.path,child_scratch)
                elif scratch or entry.name.endswith('.f32.gz') or '.pending.' in entry.name or entry.name.startswith(('.candidate-','.compact-','.preview.')):
                    total+=s.st_size
    if Path(root).exists():visit(root)
    return total


def enforce(directory,*,growth=0,temporary=0,case_bytes=None,root=ARTIFACTS,migration=False):
    """Hard stop on allocation; migration can reduce an already over-budget tree."""
    directory=confined(directory,root);errors=[]
    if migration:
        # Retained totals are frozen/reconciled by the maintenance journal. While
        # deliberately reducing an over-budget tree, scan only allocation/scratch
        # state rather than rebuilding 50,000 unchanged media records per write.
        inv={'bytes':None,'free_bytes':shutil.disk_usage(root).free,
             'by_class':{'scratch':{'bytes':temporary_bytes(root)}}}
    else:inv=inventory(root)
    if temporary>LIMITS['temporary']:errors.append(('temporary',temporary,LIMITS['temporary']))
    actual_temporary=inv['by_class'].get('scratch',{}).get('bytes',0) if migration else temporary_bytes(root)
    if actual_temporary+temporary>LIMITS['temporary']:errors.append(('temporary_total',actual_temporary+temporary,LIMITS['temporary']))
    if inv['free_bytes']<temporary+16*MiB:errors.append(('free_space_required',temporary+16*MiB,inv['free_bytes']))
    if case_bytes is not None and case_bytes>LIMITS['case']:errors.append(('case',case_bytes,LIMITS['case']))
    if case_bytes is not None and case_bytes>2*MiB:
        import warnings
        warnings.warn('Case motion/manifest exceeds the 2 MiB warning threshold',RuntimeWarning)
    if not migration:
        if inv['bytes']+growth>LIMITS['global']:errors.append(('global',inv['bytes']+growth,LIMITS['global']))
        relative=directory.relative_to(root);parts=relative.parts
        category=parts[0] if parts else ''
        if category in ('assets','maintenance','exports'):
            used=sum(v['bytes'] for rel,v in inv['files'].items() if Path(rel).parts[0]==category)
            if used+growth>LIMITS[category]:errors.append((category,used+growth,LIMITS[category]))
        if category=='stages' and len(parts)>1:
            stage=parts[1];used=inv['by_stage'].get(stage,{}).get('bytes',0);limit=LIMITS.get(stage,LIMITS['stage'])
            if used+growth>256*MiB:
                import warnings
                warnings.warn('Stage '+stage+' exceeds the 256 MiB warning threshold',RuntimeWarning)
            if used+growth>limit:errors.append(('stage/'+stage,used+growth,limit))
    if errors:raise RuntimeError('Artifact budget exceeded: '+json.dumps(errors))
    return {'retained_bytes':inv['bytes'],'estimated_growth':growth,'reserved_temporary':temporary,'free_bytes':inv['free_bytes']}


def preflight_batch(directory,*,representative_case_bytes,cases,views,frames,frame_bytes=0,root=ARTIFACTS):
    growth=representative_case_bytes*cases+views*frames*cases*frame_bytes
    return enforce(directory,growth=growth,temporary=min(LIMITS['temporary'],representative_case_bytes*2+16*MiB),root=root)


def measured_preflight(directory,requests,*,reference,root=ARTIFACTS):
    """Bound a batch with measured metadata/media and explicit case/frame counts.

    requests contains (relative case path, frames, views). Existing output is
    credited only for that same case; shared assets remain globally counted.
    """
    from tools.artifact_store import atomic_json
    directory=confined(directory,root);reference=confined(reference,root)
    measured=[];pixel_bytes=0;measured_frames=0
    for result in reference.rglob('result.json'):
        try:
            value=json.loads(result.read_text(encoding='utf-8'));count=value['frames']
            if count<1:continue
            measured_frames=max(measured_frames,count)
            case=result.parent
            numeric=sum(p.stat().st_size for p in case.glob('*.json'))
            motion=(case/'motion.blend').stat().st_size if (case/'motion.blend').exists() else LIMITS['case']
            measured.append((numeric+motion)/count)
            for view in ('front','side','frames'):
                folder=case/view
                if folder.exists():
                    with os.scandir(folder) as entries:
                        pixel_bytes=max(pixel_bytes,max((e.stat().st_size for e in entries if e.name.endswith('.png')),default=0))
        except (KeyError,ValueError,OSError):continue
    if not measured:raise RuntimeError('No measured representative; run a focused storage pilot before expanding this batch')
    growth=0;total_frames=0
    for relative,frames,views in requests:
        target=confined(directory/relative,root);frames=int(frames)
        matching=reference/relative/'result.json'
        if matching.exists():
            frames=max(frames,int(json.loads(matching.read_text(encoding='utf-8'))['frames']))
        if frames<1 or views<0:raise ValueError('Invalid batch dimensions')
        if views and not pixel_bytes:raise RuntimeError('No measured render representative for batch')
        # Numeric/action growth scales with frames; two extra frame equivalents
        # cover contact sheets, with a measured 25% headroom for metadata.
        predicted=int(max(measured)*frames*1.25+pixel_bytes*(frames*2+2)*views)
        existing=sum(v['bytes'] for v in inventory(target)['files'].values()) if target.exists() else 0
        growth+=max(0,predicted-existing);total_frames+=frames*views
    result=enforce(directory,growth=growth,temporary=128*MiB,root=root)
    report={**result,'measured_reference':os.path.relpath(reference,directory),
            'case_count':len(requests),'rendered_frames':total_frames,'max_png_bytes':pixel_bytes}
    # One bounded estimate per producer root, overwritten on repeat.
    atomic_json(directory/'storage-preflight.json',report)
    return report


def pin_failure(directory,*,signature,owner,reason,review_trigger,root=ARTIFACTS):
    from tools.artifact_store import atomic_json
    directory=confined(directory,root)
    if not all(isinstance(v,str) and v.strip() for v in (signature,owner,reason,review_trigger)):
        raise ValueError('Failure pin needs signature, owner, reason and review trigger')
    pins=list(root.rglob('failure-pin.json'));stage=directory.relative_to(root).parts[:2]
    same=[p for p in pins if p.parent.relative_to(root).parts[:2]==stage]
    if len(same)>=5 and not (directory/'failure-pin.json').exists():raise RuntimeError('Five failure reproductions already pinned for stage')
    if any(json.loads(p.read_text(encoding='utf-8'))['signature']==signature and p.parent!=directory for p in same):
        raise RuntimeError('Failure signature already has a pinned reproduction')
    used=sum(sum(v['bytes'] for v in inventory(p.parent)['files'].values()) for p in same if p.parent!=directory)
    used+=sum(v['bytes'] for v in inventory(directory)['files'].values())
    if used>LIMITS['failures']:raise RuntimeError('Pinned failure budget exceeded')
    enforce(directory,root=root)
    atomic_json(directory/'failure-pin.json',{'signature':signature,'owner':owner,'reason':reason,'review_trigger':review_trigger})
