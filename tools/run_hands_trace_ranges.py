"""Fresh-process execution of the supplemental arc/circle range cases."""
import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from hands_trace_range_cases import cases
from tools.artifact_store import input_identity
from tools.artifact_bundle import validate_manifest
for rig in ('demo','mixamo'):
    for name,_,_,_ in cases():
        out=ROOT/'artifacts/stages/05.3a'/rig/name;reusable=False
        if (out/'result.json').exists() and (out/'preview-manifest.json').exists():
            r=json.loads((out/'result.json').read_text());m=json.loads((out/'preview-manifest.json').read_text());identity=input_identity(out)
            reusable=r.get('producer_sha256')==identity['producer_sha256'] and m['inputs']==identity
        if reusable:validate_manifest(out);continue
        out.mkdir(parents=True,exist_ok=True)
        with (out/'execution.log').open('w',encoding='utf-8') as log:
            subprocess.run(['C:/Program Files/Blender Foundation/Blender 5.1/blender.exe','--background','--threads','2','--factory-startup',
                            '--python-exit-code','1','--python',str(ROOT/'tools/run_hands_trace_range_case.py'),'--','--rig',rig,'--case',name],
                            cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        validate_manifest(out);print('HANDS_TRACE_RANGE_PASSED',rig,name,flush=True)
print('ALL_HANDS_TRACE_RANGES_PASSED',flush=True)
