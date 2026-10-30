"""Fresh-process, case-leased invocation of the unchanged stage evidence harness."""
import argparse,runpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tools import artifact_store as store
parser=argparse.ArgumentParser();parser.add_argument('--rig',required=True);parser.add_argument('--case',required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
out=ROOT/'artifacts/stages/05.3a'/args.rig/args.case
from tools.storage_policy import confined
confined(out)
with store.producer_lease(out):
    original=store.hold_producer_lease
    try:
        store.hold_producer_lease=lambda directory:None
        harness=ROOT/'tests/blender_movement_elbows_wrists_hands.py'
        sys.argv=[str(harness),'--','--rig',args.rig,'--case',args.case]
        runpy.run_path(str(harness),run_name='__main__')
        store.atomic_json(out/'execution-driver.json',{'driver_sha256':store.digest(Path(__file__)),'harness_sha256':store.digest(harness),
                          'fresh_factory_process':True,'lease_scope':'one disjoint selected case'})
    finally:store.hold_producer_lease=original
