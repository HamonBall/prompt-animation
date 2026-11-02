"""Record only explicitly supplied observations after actual page inspection."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.artifact_store import atomic_json,digest
from tools.artifact_bundle import validate_manifest
from finger_cases import cases
OUT=ROOT/'artifacts/stages/05.3b'
parser=argparse.ArgumentParser();parser.add_argument('--case',required=True);parser.add_argument('--observation',required=True);args=parser.parse_args()
index=json.loads((OUT/'visual-index.json').read_text());pages=index['cases'][args.case]
for page in pages:
    assert digest(OUT/page['path'])==page['sha256']
    assert all(digest(OUT/path)==sha for path,sha in page['sheets'].items())
out=OUT/'mixamo'/args.case;manifest,asset,motion=validate_manifest(out);assert manifest['complete']
target=OUT/'visual-review.json';review=json.loads(target.read_text()) if target.exists() else {'complete':False,'cases':{}}
review['cases'][args.case]={'actually_inspected':True,'method':'All frames on complete per-view sheets/pages inspected with image tools; any identity-checked prior inspection is described in observations',
    'pages':pages,'motion_sha256':digest(motion),'observations':args.observation}
review['complete']=set(review['cases'])=={row[0] for row in cases()}
atomic_json(target,review);print('RECORDED_ACTUAL_FINGERS_REVIEW',args.case,len(review['cases']),review['complete'],flush=True)
