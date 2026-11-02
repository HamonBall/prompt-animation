"""Require a clean fresh native exit before accepting a shutdown-crash cache."""
import sys,json,subprocess,argparse,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools import artifact_store as store
from tools.fingers_runtime import validate as validate_runtime
OUT=ROOT/'artifacts/stages/05.3b';parser=argparse.ArgumentParser();parser.add_argument('--case',required=True);args=parser.parse_args()
out=OUT/'mixamo'/args.case;original=out/'render.log';assert 'ig9icd64.dll' in original.read_text() and 'FINGERS_RENDER_PASSED' in original.read_text()
runtime_lock=validate_runtime()
started=time.perf_counter();log=OUT/('cached-playback-'+args.case+'.log')
with log.open('w',encoding='utf-8') as stream:
    result=subprocess.run(['C:/Program Files/Blender Foundation/Blender 5.1/blender.exe','--background','--threads','1','--factory-startup','--python-exit-code','1',
        '--python',str(ROOT/'tests/blender_fingers_cached_playback.py'),'--','--case',args.case],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
report=json.loads((OUT/('cached-playback-'+args.case+'.json')).read_text())
report.update(native_exit_code=result.returncode,elapsed_s=time.perf_counter()-started,original_failure_log_sha256=store.digest(original),
    checker_sha256=store.digest(ROOT/'tests/blender_fingers_cached_playback.py'),recovery_driver_sha256=store.digest(Path(__file__)),
    recovery_log_sha256=store.digest(log),runtime_lock_sha256=runtime_lock,
    renderer_sha256=store.digest(ROOT/'tools/render_fingers.py'),original_failure='Intel ig9icd64.dll access violation after all render checks; original nonzero process exit retained')
assert result.returncode==0 and report['passed'];assert not (out/'.artifact-writer.lock').exists()
path=OUT/'native-shutdown-recovery.json';records=json.loads(path.read_text()) if path.exists() else {'cases':{}}
records['cases'][args.case]=report;store.atomic_json(path,records);print('FINGERS_NATIVE_SHUTDOWN_RECOVERED',args.case,report['elapsed_s'],flush=True)
