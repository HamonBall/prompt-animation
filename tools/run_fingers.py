"""Fresh-process bounded case runner with strict unchanged identity reuse."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from finger_cases import cases
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.storage_policy import enforce
from tools.fingers_provenance import producer_valid
from tools.fingers_runtime import capture as capture_runtime,validate as validate_runtime
OUT=ROOT/'artifacts/stages/05.3b';BLENDER='C:/Program Files/Blender Foundation/Blender 5.1/blender.exe'
parser=argparse.ArgumentParser();parser.add_argument('--case');args=parser.parse_args()
capture_runtime();validate_runtime()
jobs=[row for row in cases() if not args.case or row[0]==args.case];assert jobs
enforce(OUT,growth=len(jobs)*6*1024**2,temporary=32*1024**2)
record={'executed':[],'reused':[],'fresh_process_per_case':True};started=time.perf_counter()
for name,_,_,_ in jobs:
    out=OUT/'mixamo'/name;result=out/'result.json';manifest=out/'preview-manifest.json'
    if result.exists() and manifest.exists():
        r=json.loads(result.read_text());m=json.loads(manifest.read_text())
        if m['inputs']==store.input_identity(out) and producer_valid(out):
            validate_manifest(out);record['reused'].append(name);print('FINGERS_REUSED',name,flush=True);continue
        raise RuntimeError('Stale case must be explicitly reconciled before replacement: '+name)
    out.mkdir(parents=True,exist_ok=True)
    with (out/'execution.log').open('w',encoding='utf-8') as log:
        subprocess.run([BLENDER,'--background','--threads','2','--factory-startup','--python-exit-code','1','--python',
            str(ROOT/'tests/blender_movement_fingers.py'),'--','--case',name],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    validate_manifest(out);record['executed'].append(name);record['elapsed_s']=time.perf_counter()-started
    store.atomic_json(OUT/'numeric-run.json',record);print('FINGERS_CASE_COMPLETE',name,flush=True)
store.atomic_json(OUT/'numeric-run.json',record)
print('ALL_FINGERS_NUMERIC_PASSED',len(jobs),flush=True)
