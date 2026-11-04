"""Fresh saved-action renderer per case, with exact media/process reuse checks."""
import sys,time,json,subprocess,argparse,gzip,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from hips_knees_cases import cases
from tools.legs_evidence import OUT,BLENDER,runtime,numeric_valid
from tools.hips_knees_views import render_sources,render_valid
from tools.artifact_store import atomic_json,digest
from tools.storage_policy import enforce
parser=argparse.ArgumentParser();parser.add_argument('--rig',required=True,choices=('demo','mixamo'));parser.add_argument('--case');parser.add_argument('--review-window',type=int,default=8);args=parser.parse_args()
runtime();jobs=[r for r in cases() if not args.case or r[0]==args.case];assert jobs
if not args.case:
    numeric=json.loads((OUT/'validation-summary.json').read_text())
    preflight=json.loads((OUT/'render-batch-preflight.json').read_text())
    trial=json.loads((OUT/'render-concurrency-trial.json').read_text())
    assert numeric['passed'] and numeric['case_count']==2*len(jobs)
    assert trial['passed'] and preflight['native_workers']==2
    assert 1<=args.review_window<=preflight['review_window']
    # The lossless encoder reserves per frame. Use its largest allocations
    # while retained occupancy is lowest.
    jobs.sort(key=lambda row:-numeric['cases'][args.rig+'/'+row[0]]['frames'])
record={'rig':args.rig,'executed':[],'reused':[],'fresh_process_per_case':True,'threads':2};started=time.perf_counter()
status_path=OUT/('render-run-'+args.rig+('-'+args.case if args.case else '')+'.json')
for name,_,_,_ in jobs:
    out=OUT/args.rig/name;assert numeric_valid(out)
    if render_valid(out):record['reused'].append(name);print('LEGS_RENDER_REUSED',args.rig,name,flush=True);continue
    if not args.case:
        while True:
            review_path=OUT/'visual-review.json';review=json.loads(review_path.read_text()) if review_path.exists() else {'cases':{}}
            waiting=0
            for rig in ('demo','mixamo'):
                for case,_,_,_ in cases():
                    path=OUT/rig/case/'preview-manifest.json'
                    if path.exists() and json.loads(path.read_text()).get('complete') and not review['cases'].get(rig+'/'+case,{}).get('retention_complete'):
                        waiting+=1
            if waiting<args.review_window:break
            print('NEEDS_ACTUAL_VISUAL_REVIEW_AND_RETENTION',waiting,
                  'Review the completed case sheets, record observations and retention, then resume. No polling worker remains.',flush=True)
            raise SystemExit(75)
    assert not (out/'render-process.json').exists(),'Investigate/reconcile existing failed or changed-source media first: '+str(out)
    enforce(out,growth=48*1024**2,temporary=128*1024**2)
    sources=render_sources();begin=time.perf_counter();log=out/'render.log.gz'
    with gzip.open(log,'xb') as stream,subprocess.Popen(
        [str(BLENDER),'--background','--threads','2','--factory-startup','--python-exit-code','1',
         '--python',str(ROOT/'tools/render_hips_knees.py'),'--','--rig',args.rig,'--case',name],
        cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
    ) as process:
        shutil.copyfileobj(process.stdout,stream)
        exit_code=process.wait()
    atomic_json(out/'render-process.json',{'exit_code':exit_code,'log_name':log.name,'log_sha256':digest(log),'runtime_lock_sha256':runtime(),
        'render_sources':sources,'elapsed_s':time.perf_counter()-begin})
    assert exit_code==0,'Native render failed; inspect '+str(log)
    assert sources==render_sources() and render_valid(out),'Render source/runtime/output changed'
    record['executed'].append(name);record['elapsed_s']=time.perf_counter()-started;atomic_json(status_path,record)
    print('LEGS_RENDER_COMPLETE',args.rig,name,flush=True)
record['elapsed_s']=time.perf_counter()-started
atomic_json(status_path,record);print('LEGS_ALL_RENDERS_PASSED',args.rig,len(jobs),flush=True)
