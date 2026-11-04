"""Stage-05.4 runtime/provenance and bounded verified development replacement."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.artifact_store import digest,atomic_json,input_identity
from tools.artifact_bundle import validate_manifest
from tools.storage_policy import confined,active_writer
OUT=ROOT/'artifacts/stages/05.4'
BLENDER=Path('C:/Program Files/Blender Foundation/Blender 5.1/blender.exe')
PYTHON=BLENDER.parent/'5.1/python/bin/python.exe'
BUILD='Blender 5.1.0 (hash adfe2921d5f3 built 2026-03-17 01:37:32)'
_verified={}


def runtime(capture=False):
    target=OUT/'runtime-lock.json'
    if capture and not target.exists():
        atomic_json(target,{'owner':'05.4','build':BUILD,'threads':2,'factory_startup':True,'fps':30,
            'observation':'Captured after development pilots and before the final native matrix',
            'binaries':{str(p):{'sha256':digest(p),'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in (BLENDER,PYTHON)}})
    record=json.loads(target.read_text());assert record['build']==BUILD
    for name,value in record['binaries'].items():
        p=Path(name);stat=p.stat();assert (stat.st_size,stat.st_mtime_ns)==(value['bytes'],value['mtime_ns'])
        key=(name,stat.st_size,stat.st_mtime_ns)
        if key not in _verified:_verified[key]=digest(p)
        assert _verified[key]==value['sha256']
    return digest(target)


def numeric_valid(directory):
    try:
        directory=Path(directory);manifest,_,_=validate_manifest(directory)
        result=json.loads((directory/'result.json').read_text());record=result['stage_05_4']
        process=json.loads((directory/'native-process.json').read_text())
        if not result['review']['passed'] or process['exit_code']!=0 or process['runtime_lock_sha256']!=runtime():return False
        from tools.hips_knees_provenance import inputs_valid
        if not inputs_valid(directory,manifest,result) or record['application_producer_sha256']!=manifest['inputs']['producer_sha256']:return False
        if process['producer_at_start']!=manifest['inputs']['producer_sha256']:return False
        if not all(digest(ROOT/path)==sha for path,sha in record['stage_producer'].items()):return False
        log=directory/'execution.log';text=log.read_text()
        if process['log_sha256']!=digest(log) or BUILD not in text or 'LEGS_NUMERIC_PASSED' not in text or 'Blender quit' not in text:return False
        return True
    except (OSError,KeyError,ValueError,TypeError):return False


def publish_visuals(directory,scene,views,*,complete):
    """Publish standard media metadata without relabelling the motion producer.

    The shared atomic writer, manifest validator and full media integrity checker
    remain authoritative. View source identity is distinct from execution input.
    """
    from tools.artifact_store import files_complete
    from tools.storage_policy import enforce
    directory=Path(directory);manifest,_,motion=validate_manifest(directory)
    assert numeric_valid(directory)
    assert manifest['expected_frames']==list(range(scene.frame_start,scene.frame_end+1))
    assert (manifest['fps'],manifest['fps_base'])==(scene.render.fps,scene.render.fps_base)
    manifest['views']=views;manifest['current_frame']=scene.frame_current;manifest['complete']=complete
    manifest['visual_evidence']={'representation':'ffv1_mkv','views':list(views),'frames':manifest['expected_frames'],
        'fps':manifest['fps'],'fps_base':manifest['fps_base'],'result_sha256':manifest['inputs']['result.json'],'complete':complete}
    if complete:assert set(views)=={'front','side'} and files_complete(directory,manifest)
    atomic_json(directory/'preview-manifest.json',manifest)
    enforce(directory,case_bytes=motion.stat().st_size+(directory/'preview-manifest.json').stat().st_size)


def park_development(directory):
    directory=confined(Path(directory));assert directory.is_relative_to(OUT)
    backup=confined(directory.parent/('development-'+directory.name));assert not backup.exists()
    plan=json.loads((OUT/'development-smoke-status.json').read_text());key=directory.relative_to(OUT).as_posix()
    original=plan['cases'][key]['files'];actual={p.relative_to(directory).as_posix():p for p in directory.rglob('*') if p.is_file()}
    assert set(actual)==set(original) and not active_writer(directory)
    for name,p in actual.items():assert digest(p)==original[name]['sha256'] and p.stat().st_size==original[name]['bytes']
    target=OUT/'retention-journals'/('prepared-'+key.replace('/','-')+'.json')
    journal=json.loads(target.read_text()) if target.exists() else {'owner':'05.4','case':key,'operations':[]}
    journal['operations'].append({'retained_history_path':backup.relative_to(OUT).as_posix(),'files':original,'state':'preserved_pending_replacement'})
    atomic_json(target,journal);os.replace(directory,backup)
    return backup


def replace_development(directory,candidate):
    """Only explicitly pinned unreviewed development cases, after new acceptance."""
    directory,candidate=(confined(Path(p)) for p in (directory,candidate))
    assert directory.parent==candidate.parent and directory.is_relative_to(OUT)
    assert directory.name=='development-'+candidate.name
    assert not active_writer(directory) and not active_writer(candidate)
    plan=json.loads((OUT/'development-smoke-status.json').read_text());key=candidate.relative_to(OUT).as_posix()
    original=plan['cases'][key]['files']
    assert numeric_valid(candidate)
    actual={p.relative_to(directory).as_posix():p for p in directory.rglob('*') if p.is_file()}
    assert set(actual)==set(original)
    for name,p in actual.items():assert digest(p)==original[name]['sha256'] and p.stat().st_size==original[name]['bytes']
    target=OUT/'retention-journals'/('retired-'+key.replace('/','-')+'.json')
    journal=json.loads(target.read_text()) if target.exists() else {'owner':'05.4','case':key,'operations':[]}
    record={'state':'prepared','reason':'Unreviewed development pilot replaced by exact current-source/runtime native case',
        'files':original,'replacement_motion_sha256':digest(candidate/'motion.blend')}
    journal['operations'].append(record);atomic_json(target,journal)
    for p in actual.values():confined(p).unlink()
    for p in sorted(directory.rglob('*'),key=lambda p:len(p.parts),reverse=True):
        assert p.is_dir();p.rmdir()
    directory.rmdir()
    record['state']='complete';atomic_json(target,journal)
    assert numeric_valid(candidate)
