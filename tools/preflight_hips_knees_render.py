"""Project Stage 05.4 media growth from the two verified full-motion pilots."""
import gzip
import json
import math
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from hips_knees_cases import cases
from tools.artifact_bundle import validate_manifest
from tools.artifact_store import atomic_json
from tools.hips_knees_views import render_valid
from tools.legs_evidence import OUT
from tools.storage_policy import MiB,enforce,inventory

pilots={'demo':'leg.cross.crouched','mixamo':'hip.lift.default.left'}
audit=json.loads((OUT/'validation-summary.json').read_text())
assert audit['passed'] and audit['case_count']==2*len(cases())
inv=inventory()
assert not inv['leases']
components={'movies':0,'full_sheets':0,'selected_sheets':0,'render_metadata_and_logs':0}
report={'pilots':{},'remaining_cases':0,'remaining_frames_per_view':0}
for rig,pilot in pilots.items():
    directory=OUT/rig/pilot
    assert render_valid(directory)
    manifest,_,_=validate_manifest(directory)
    frames=len(manifest['expected_frames'])
    movies=sum((directory/view['media']['path']).stat().st_size for view in manifest['views'].values())
    journal=directory/'sheet-retention.json'
    full_sheets=(sum(v['original_bytes'] for v in json.loads(journal.read_text())['views'].values()) if journal.exists()
                 else sum(p.stat().st_size for p in directory.glob('*-sheet.png')))
    metadata=len(gzip.compress((directory/'render.log').read_bytes()))+sum((directory/name).stat().st_size for name in
                 ('saved-rotations.json','saved-playback-review.json','media-build.json',
                  'media-retirement.json','render-timing.json','render-process.json','preview-manifest.json'))
    report['pilots'][rig]={'frames_per_view':frames,'movie_bytes':movies,'full_sheet_bytes':full_sheets,
                           'render_metadata_upper_bound_bytes':metadata}
    for name,_,_,_ in cases():
        if name==pilot:continue
        count=audit['cases'][rig+'/'+name]['frames']
        report['remaining_cases']+=1
        report['remaining_frames_per_view']+=count
        components['movies']+=math.ceil(1.25*movies*count/frames)
        components['render_metadata_and_logs']+=math.ceil(1.1*metadata*count/frames)
        if name.endswith('.default.left') or name=='knee.pulse.default.both':
            components['full_sheets']+=math.ceil(1.15*full_sheets*count/frames)
        else:
            components['selected_sheets']+=64*1024
report.update(components=components,review_window=8,native_workers=2,
              concurrent_temporary_reservation_bytes=320*MiB,
              closure_and_queued_sheet_reservation_bytes=16*MiB,
              current_stage_bytes=inv['by_stage']['05.4']['bytes'])
report['projected_retained_growth_bytes']=sum(components.values())+report['closure_and_queued_sheet_reservation_bytes']
print(json.dumps(report,indent=2),flush=True)
report['budget']=enforce(OUT,growth=report['projected_retained_growth_bytes'],
                         temporary=report['concurrent_temporary_reservation_bytes'])
atomic_json(OUT/'render-batch-preflight.json',report)
