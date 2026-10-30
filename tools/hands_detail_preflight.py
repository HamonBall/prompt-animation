"""Forecast additional hand cameras from verified per-rig closeup pilots."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.hands_evidence_cases import detail_cases
from tools.hands_render_state import render_complete
from tools.artifact_store import atomic_json,digest
from tools.storage_policy import enforce,inventory
OUT=ROOT/'artifacts/stages/05.3a';rows=[]
for rig in ('demo','mixamo'):
    pilot=OUT/rig/'elbow.flex.default';m=json.loads((pilot/'preview-manifest.json').read_text())
    assert render_complete(pilot,('front','side','hand-front','hand-side'))
    assert all(m['views'][v].get('renderer_sha256')==digest(ROOT/'tools/render_hands_details.py') for v in ('hand-front','hand-side'))
    rate=sum((pilot/m['views'][v]['media']['path']).stat().st_size+(pilot/(v+'-sheet.png')).stat().st_size for v in ('hand-front','hand-side'))/len(m['expected_frames'])
    for name,_,_,_ in detail_cases():
        out=OUT/rig/name;r=json.loads((out/'result.json').read_text());m0=json.loads((out/'preview-manifest.json').read_text())
        complete=render_complete(out,('front','side','hand-front','hand-side')) and all(
            m0['views'][v].get('renderer_sha256')==digest(ROOT/'tools/render_hands_details.py') for v in ('hand-front','hand-side'))
        rows.append({'case':rig+'/'+name,'frames':r['frames'],'predicted_growth_bytes':0 if complete else int(rate*r['frames']*1.5)+r['frames']*768+16384})
growth=sum(x['predicted_growth_bytes'] for x in rows)+8*1024**2
normal=json.loads((OUT/'render-batch-preflight.json').read_text())
normal_remaining=sum(row['media_bytes']+row['metadata_reserve_bytes']+row['missing_numeric_growth']
    for row in normal['cases'] if not render_complete(OUT/row['case'],('front','side')))
# Reserve concurrently outstanding normal media, as well as the separate normal
# review/log allowance. A completed normal worker does not release its evidence.
# Most normal logs/review pages already exist. Keep a bounded 4 MiB reserve
# for their remaining writes, in addition to the separate 8 MiB detail reserve;
# the original 32 MiB allowance included work now present in current inventory.
normal_review_remaining=4*1024**2
combined=growth+normal_remaining+normal_review_remaining
atomic_json(OUT/'detail-forecast-calculation.json',{'detail_growth_bytes':growth,
    'outstanding_normal_media_reserve_bytes':normal_remaining,'normal_remaining_review_log_reserve_bytes':normal_review_remaining,
    'combined_growth_reserve_bytes':combined,'normal_logs_existing_bytes':sum(p.stat().st_size for p in OUT.glob('render-current-*.log')),
    'review_pages_existing_bytes':sum(p.stat().st_size for p in OUT.glob('review-full/*.png'))})
checked=enforce(OUT,growth=combined,temporary=256*1024**2)
atomic_json(OUT/'detail-batch-preflight.json',{**checked,'cases':rows,'growth_bytes':growth,'concurrent_workers':4,
            'outstanding_normal_media_reserve_bytes':normal_remaining,'combined_growth_reserve_bytes':combined,
            'normal_remaining_review_log_reserve_bytes':normal_review_remaining,
            'measured_pilots':['demo/elbow.flex.default','mixamo/elbow.flex.default'],'extra_review_reserve_bytes':8*1024**2})
print('HANDS_DETAIL_PREFLIGHT_PASSED',len(rows),growth,flush=True)
