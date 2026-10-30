"""Disjoint case-leased saved-action rendering through the shared evidence writer."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.movement_library import contracts as c
from tools.hands_evidence_cases import cases
from tools.artifact_store import producer_lease,open_preview,write_manifest,input_identity,digest
from tools.hands_render_state import render_complete
from tools.hands_source_compatibility import numeric_source_valid
from tools.artifact_bundle import validate_manifest
from tools.movement_evidence import render
from tools.lossless_evidence import recover_evidence,encode_view,retire_pngs
from tools.storage_policy import enforce
OUT=ROOT/'artifacts/stages/05.3a'
parser=argparse.ArgumentParser();parser.add_argument('--rig',required=True,choices=('demo','mixamo'))
parser.add_argument('--shard',type=int,default=0);parser.add_argument('--shards',type=int,default=1)
parser.add_argument('--case');args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
assert 0<=args.shard<args.shards<=8
forecast=json.loads((OUT/'render-batch-preflight.json').read_text());assert forecast['concurrent_workers']>=args.shards
p=c.loads(c.AvatarProfile,(OUT/args.rig/'profile.json').read_text())
selected=[v for i,v in enumerate(cases()) if i%args.shards==args.shard and (args.case is None or v[0]==args.case)]
for name,_,_,_ in selected:
    out=OUT/args.rig/name
    if render_complete(out,('front','side')):
        print('HANDS_RENDER_REUSED',args.rig,name,flush=True);continue
    with producer_lease(out):
        recover_evidence(out);manifest,asset,motion=validate_manifest(out)
        result=json.loads((out/'result.json').read_text());assert result['review']['passed']
        assert numeric_source_valid(out),'Numeric source is neither current nor explicitly verified compatible'
        before=(digest(motion),motion.stat().st_mtime_ns);h=open_preview(out);views={};plans=[]
        for view in ('front','side'):
            views[view]=render(h,p,out,view=='side')
            media,plan=encode_view(out,view,manifest['expected_frames'],fps=manifest['fps'],fps_base=manifest['fps_base'])
            views[view]['media']=media;views[view]['renderer_sha256']=digest(Path(__file__));plans.append(plan)
        h.scene.frame_set(1);write_manifest(out,h.scene,views=views,complete=True);retire_pngs(out,plans)
        assert before==(digest(motion),motion.stat().st_mtime_ns),'Render rewrote accepted motion'
        enforce(out);print('HANDS_RENDER_PASSED',args.rig,name,len(manifest['expected_frames'])*2,flush=True)
print('ALL_HANDS_RENDER_SHARD_PASSED',args.rig,args.shard,flush=True)
