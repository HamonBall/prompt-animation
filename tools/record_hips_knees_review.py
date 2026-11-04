"""Record observations only after actually inspecting both complete case sheets."""
import sys,json,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.legs_evidence import OUT
from tools.hips_knees_views import render_valid
from tools.artifact_store import atomic_json,digest
from tools.artifact_bundle import validate_manifest
from hips_knees_cases import cases
parser=argparse.ArgumentParser();parser.add_argument('--rig',required=True,choices=('demo','mixamo'));parser.add_argument('--case',required=True);parser.add_argument('--observation',required=True);args=parser.parse_args()
assert args.case in {r[0] for r in cases()};out=OUT/args.rig/args.case;assert render_valid(out)
manifest,_,motion=validate_manifest(out);target=OUT/'visual-review.json'
assert not any('sheet_representation' in view for view in manifest['views'].values()),'Selected summaries do not replace a new full-motion inspection; retain the original reviewed record'
review=json.loads(target.read_text()) if target.exists() else {'method':'Actually opened complete front/side sheets with image tools; all saved motion frames retained','cases':{}}
key=args.rig+'/'+args.case
review['cases'][key]={'actually_inspected':True,'observations':args.observation,'motion_sha256':digest(motion),
    'frames_per_view':len(manifest['expected_frames']),'sheets':{label:digest(out/(label+'-sheet.png')) for label in ('front','side')},
    'media':{label:view['media']['sha256'] for label,view in manifest['views'].items()},
    'retention_complete':args.case.endswith('.default.left') or args.case=='knee.pulse.default.both'}
review['complete']=set(review['cases'])=={rig+'/'+name for rig in ('demo','mixamo') for name,_,_,_ in cases()}
atomic_json(target,review);print('RECORDED_ACTUAL_LEG_REVIEW',key,len(review['cases']),review['complete'],flush=True)
