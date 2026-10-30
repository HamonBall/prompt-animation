"""Bounded disjoint matrix runner; a fresh Blender process owns each case."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from elbows_wrists_hands_cases import cases
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.hands_source_compatibility import numeric_source_valid
OUT=ROOT/'artifacts/stages/05.3a';HARNESS=ROOT/'tests/blender_movement_elbows_wrists_hands.py'
BLENDER='C:/Program Files/Blender Foundation/Blender 5.1/blender.exe'
parser=argparse.ArgumentParser();parser.add_argument('--shard',type=int,required=True);parser.add_argument('--shards',type=int,default=4)
args=parser.parse_args();assert 0<=args.shard<args.shards<=4
record={'driver_sha256':store.digest(Path(__file__)),'harness_sha256':store.digest(HARNESS),'shard':args.shard,'shards':args.shards,
        'fresh_factory_process_per_case':True,'completed':[],'reused':[]}
report=OUT/('numeric-fresh-worker-'+str(args.shard)+'.json')
jobs=[(rig,name) for rig in ('demo','mixamo') for name,_,_,_ in cases()]
for index,(rig,name) in enumerate(jobs):
    if index%args.shards!=args.shard:continue
    out=OUT/rig/name;reusable=False
    if (out/'result.json').exists() and (out/'preview-manifest.json').exists():
        result=json.loads((out/'result.json').read_text());manifest=json.loads((out/'preview-manifest.json').read_text());identity=store.input_identity(out)
        if numeric_source_valid(out,identity) and {k:v for k,v in manifest['inputs'].items() if k!='producer_sha256'}=={k:v for k,v in identity.items() if k!='producer_sha256'}:
            validate_manifest(out);reusable=True
    if reusable:record['reused'].append(rig+'/'+name)
    else:
        print('HANDS_FRESH_CASE',rig,name,flush=True)
        out.mkdir(parents=True,exist_ok=True)
        with (out/'execution.log').open('w',encoding='utf-8') as log:
            subprocess.run([BLENDER,'--background','--threads','2','--factory-startup','--python-exit-code','1','--python',str(ROOT/'tools/run_hands_numeric_case.py'),
                            '--','--rig',rig,'--case',name],cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        validate_manifest(out);record['completed'].append(rig+'/'+name)
    store.atomic_json(report,record)
print('ALL_HANDS_NUMERIC_FRESH_SHARD_PASSED',args.shard,flush=True)
