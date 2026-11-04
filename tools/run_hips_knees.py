"""One isolated native case at a time, strict source/runtime reuse and budgets."""
import sys,json,time,subprocess,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from hips_knees_cases import cases
from tools.legs_evidence import OUT,BLENDER,runtime,numeric_valid,replace_development,park_development
from tools.artifact_store import atomic_json,digest,input_identity
from tools.storage_policy import enforce
parser=argparse.ArgumentParser();parser.add_argument('--rig',choices=('demo','mixamo'),required=True);parser.add_argument('--case');args=parser.parse_args()
runtime(capture=True);jobs=[r for r in cases() if not args.case or r[0]==args.case];assert jobs
enforce(OUT,growth=len(jobs)*2*1024**2,temporary=64*1024**2)
record={'rig':args.rig,'executed':[],'reused':[],'fresh_process_per_case':True,'threads':2};started=time.perf_counter()
for name,_,_,_ in jobs:
    out=OUT/args.rig/name
    backup=out.parent/('development-'+name)
    if out.exists() and numeric_valid(out) and backup.exists():replace_development(backup,out)
    if out.exists() and numeric_valid(out):record['reused'].append(name);print('LEGS_NUMERIC_REUSED',args.rig,name,flush=True);continue
    stale=out.exists() and any(out.iterdir())
    if stale:
        plan=json.loads((OUT/'development-smoke-status.json').read_text());assert out.relative_to(OUT).as_posix() in plan['cases'],'Stale accepted output needs explicit reconciliation'
    assert not backup.exists(),'Investigate an interrupted development replacement before retry'
    if stale:backup=park_development(out)
    candidate=out
    assert not candidate.exists() or not any(candidate.iterdir()),'Investigate existing candidate before retry: '+str(candidate)
    candidate.mkdir(parents=True,exist_ok=True);source=input_identity(candidate)['producer_sha256'];begin=time.perf_counter()
    log=candidate/'execution.log'
    with log.open('w',encoding='utf-8') as stream:
        result=subprocess.run([str(BLENDER),'--background','--threads','2','--factory-startup','--python-exit-code','1',
            '--python',str(ROOT/'tests/blender_movement_hips_knees.py'),'--','--rig',args.rig,'--case',name,'--output-dir',str(candidate)],
            cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    atomic_json(candidate/'native-process.json',{'exit_code':result.returncode,'log_sha256':digest(log),'runtime_lock_sha256':runtime(),
        'elapsed_s':time.perf_counter()-begin,'producer_at_start':source})
    assert result.returncode==0,'Native case failed; inspect '+str(log)
    assert source==input_identity(candidate)['producer_sha256'] and numeric_valid(candidate),'Source/runtime/output identity changed'
    if stale:replace_development(backup,candidate)
    record['executed'].append(name);record['elapsed_s']=time.perf_counter()-started;atomic_json(OUT/('numeric-run-'+args.rig+'.json'),record)
    print('LEGS_NUMERIC_COMPLETE',args.rig,name,flush=True)
atomic_json(OUT/('numeric-run-'+args.rig+'.json'),record);print('LEGS_ALL_NUMERIC_PASSED',args.rig,len(jobs),flush=True)
