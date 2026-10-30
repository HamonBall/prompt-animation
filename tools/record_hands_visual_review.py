"""Record explicitly inspected pages; page generation never invokes this tool."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.artifact_store import atomic_json,digest
OUT=ROOT/'artifacts/stages/05.3a'
parser=argparse.ArgumentParser();parser.add_argument('--page',action='append',required=True);parser.add_argument('--note',required=True);args=parser.parse_args()
index=json.loads((OUT/'visual-index.json').read_text());target=OUT/'visual-review.json'
record=json.loads(target.read_text()) if target.exists() else {rig:{'inspected_pages':[],'reviewed_cases':[]} for rig in ('demo','mixamo')}
for requested in args.page:
    matches=[(rig,page) for rig,kinds in index.items() for kind,value in kinds.items() for page in value['pages'] if page['path']==requested]
    assert len(matches)==1;rig,page=matches[0]
    assert digest(OUT/page['path'])==page['sha256']
    for name,views in page['source_sheets'].items():
        for view,sha in views.items():assert digest(OUT/rig/name/(view+'-sheet.png'))==sha
    item={**page,'reviewer':'Codex actual image inspection','review_date':'2026-10-30','observations':args.note}
    record[rig]['inspected_pages']=[p for p in record[rig]['inspected_pages'] if p['path']!=requested]+[item]
    record[rig]['reviewed_cases']=sorted({name for p in record[rig]['inspected_pages'] if p['path'].startswith('review-full/') for name in p['cases']})
atomic_json(target,record);print('RECORDED_ACTUAL_VISUAL_REVIEW',len(args.page),flush=True)
