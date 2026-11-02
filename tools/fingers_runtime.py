"""Stage-local runtime lock and native-build validation for evidence reuse."""
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/stages/05.3b'
sys.path.insert(0,str(ROOT))
from tools.artifact_store import digest,atomic_json
BLENDER=Path('C:/Program Files/Blender Foundation/Blender 5.1/blender.exe')
PYTHON=BLENDER.parent/'5.1/python/bin/python.exe'
BUILD='Blender 5.1.0 (hash adfe2921d5f3 built 2026-03-17 01:37:32)'
_verified={}


def capture():
    """Observation now, not an invented pre-execution binary hash."""
    target=OUT/'runtime-lock.json'
    if target.exists():validate();return
    atomic_json(target,{'owner':'stage-05.3b','expected_native_build':BUILD,'threads_per_worker':2,'factory_startup':True,'fps':30,
        'binary_hash_observation':'Captured after numeric execution and before final visual completion; all original native execution logs independently carry the same build string.',
        'binaries':{str(path):{'sha256':digest(path),'bytes':path.stat().st_size,'mtime_ns':path.stat().st_mtime_ns} for path in (BLENDER,PYTHON)}})


def validate():
    lock=json.loads((OUT/'runtime-lock.json').read_text());assert lock['expected_native_build']==BUILD
    for name,record in lock['binaries'].items():
        path=Path(name);stat=path.stat();assert stat.st_size==record['bytes'] and stat.st_mtime_ns==record['mtime_ns']
        key=(name,stat.st_size,stat.st_mtime_ns)
        if key not in _verified:_verified[key]=digest(path)
        assert _verified[key]==record['sha256']
    source=OUT/'mixamo/source.json'
    if source.exists():
        recorded=json.loads(source.read_text());path=ROOT/'Hip Hop Mixamo.fbx';stat=path.stat()
        key=(str(path),stat.st_size,stat.st_mtime_ns)
        if key not in _verified:_verified[key]=digest(path)
        assert _verified[key]==recorded['sha256'],'Current source FBX differs from the reviewed input version'
    for log in (OUT/'mixamo').glob('*/execution.log'):
        if log.parent.name.startswith('development-'):continue
        text=log.read_text();assert BUILD in text and 'FINGERS_NUMERIC_PASSED' in text and 'Blender quit' in text,log
    return digest(OUT/'runtime-lock.json')


if __name__=='__main__':capture();print('FINGERS_RUNTIME_IDENTITY_PASSED',validate(),flush=True)
