"""Select completed current-renderer cases for the existing page assembler."""
import sys,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools import fingers_review_pages as pages
from tools.artifact_store import digest,atomic_json
from tools.storage_policy import enforce
from finger_cases import cases
OUT=ROOT/'artifacts/stages/05.3b';renderer=digest(ROOT/'tools/render_fingers.py');selected=[]
for row in cases():
    manifest=json.loads((OUT/'mixamo'/row[0]/'preview-manifest.json').read_text())
    detail=[view for label,view in manifest['views'].items() if label not in ('front','side')]
    if manifest['complete'] and detail and all(view.get('renderer_sha256')==renderer and view.get('visibility_check',{}).get('passed') for view in detail):selected.append(row)
assert selected,'No completed current hand views yet'
reserve=max(2*math.ceil(json.loads((OUT/'mixamo'/row[0]/'preview-manifest.json').read_text())['frame_end']/12)*192*2304*16 for row in selected)+256*1024**2
enforce(OUT,growth=80*1024**2,temporary=reserve)
atomic_json(OUT/'page-selection.json',{'selector_sha256':digest(Path(__file__)),'renderer_sha256':renderer,
    'selected_cases':[row[0] for row in selected],'case_selection_only':True,'page_algorithm_sha256':digest(ROOT/'tools/fingers_review_pages.py'),
    'combined_temporary_reservation_bytes':reserve})
# Only a selector; the unchanged assembler retains all frames, source/page hashes
# and its original layout. It confers no review status.
pages.cases=lambda:selected
pages.main()
