"""Fresh native renderer per case; strict resume, bounded preflight, no rebuilding."""
import sys,json,subprocess,time,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from finger_cases import cases
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.storage_policy import enforce
from tools.fingers_runtime import validate as validate_runtime
from tools.fingers_native_cache import verified_native_cache
OUT=ROOT/'artifacts/stages/05.3b';BLENDER='C:/Program Files/Blender Foundation/Blender 5.1/blender.exe'
parser=argparse.ArgumentParser();parser.add_argument('--shard',type=int,default=0);parser.add_argument('--shards',type=int,default=1);parser.add_argument('--case');args=parser.parse_args()
assert 0<=args.shard<args.shards<=2
validate_runtime()
jobs=[row for i,row in enumerate(cases()) if i%args.shards==args.shard and (not args.case or row[0]==args.case)]
assert jobs
pilot=OUT/'mixamo/gesture.fist.neutral';pm=json.loads((pilot/'preview-manifest.json').read_text());frames=0;growth=0;views=0
for name,_,parameters,_ in jobs:
    out=OUT/'mixamo'/name;manifest,_,_=validate_manifest(out)
    assert manifest['inputs']==store.input_identity(out)
    count=len(manifest['expected_frames']);n=6 if parameters.get('side')=='both' else 4
    frames+=count*n;views+=n
    growth+=int(sum((pilot/v['media']['path']).stat().st_size+(pilot/(k+'-sheet.png')).stat().st_size for k,v in pm['views'].items())*count/94*n/6*1.5)+1024**2
enforce(OUT,growth=growth,temporary=128*1024**2)
store.atomic_json(OUT/('render-preflight-'+str(args.shard)+'.json'),{'case_count':len(jobs),'views':views,'frames':frames,
    'measured_reference':'mixamo/gesture.fist.neutral','reserved_growth_bytes':growth,'temporary_reservation_bytes':128*1024**2,
    'fresh_native_process_per_case':True,'worker_threads':2})
record={'executed':[],'reused':[]};started=time.perf_counter()
for name,_,_,_ in jobs:
    out=OUT/'mixamo'/name;manifest=json.loads((out/'preview-manifest.json').read_text())
    assert verified_native_cache(out),'Native failure needs explicit fresh recovery: '+name
    if store.render_complete(out,tuple(manifest['views'])) and len(manifest['views'])>=4 and all(
        v.get('renderer_sha256')==store.digest(ROOT/'tools/render_fingers.py') and v.get('visibility_check',{}).get('passed') for k,v in manifest['views'].items() if k not in ('front','side')):
        record['reused'].append(name);print('FINGERS_RENDER_REUSED',name,flush=True);continue
    with (out/'render.log').open('w',encoding='utf-8') as log:
        subprocess.run([BLENDER,'--background','--threads','2','--factory-startup','--python-exit-code','1','--python',str(ROOT/'tools/render_fingers.py'),'--','--case',name],
            cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    manifest=json.loads((out/'preview-manifest.json').read_text());assert store.render_complete(out,tuple(manifest['views']))
    record['executed'].append(name);record['elapsed_s']=time.perf_counter()-started
    store.atomic_json(OUT/('render-run-'+str(args.shard)+'.json'),record);print('FINGERS_RENDER_CASE_COMPLETE',name,flush=True)
store.atomic_json(OUT/('render-run-'+str(args.shard)+'.json'),record);print('ALL_FINGERS_RENDER_PASSED',args.shard,flush=True)
