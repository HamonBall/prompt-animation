"""Recheck actual-review identities without generating or claiming inspection."""
import json
from pathlib import Path
from tools.artifact_store import digest
from tools.artifact_bundle import validate_manifest
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/stages/05.3b'


def validate_visual_reviews():
    from finger_cases import cases
    review=json.loads((OUT/'visual-review.json').read_text())
    assert review['complete'] and set(review['cases'])=={row[0] for row in cases()}
    for name,_,parameters,_ in cases():
        record=review['cases'][name];out=OUT/'mixamo'/name;manifest,_,motion=validate_manifest(out)
        assert record['actually_inspected'] and record['motion_sha256']==digest(motion)
        for label,view in manifest['views'].items():
            if label in ('front','side'):continue
            assert view['renderer_sha256']==digest(ROOT/'tools/render_fingers.py')
            visible=view['visibility_check'];assert visible['passed'] and visible['frames']==len(manifest['expected_frames'])
            assert visible['minimum_luminance_contrast']>.08 and visible['minimum_luminance_std']>.005 and visible['minimum_foreground_pixels']>=32
        labels=set()
        for page in record['pages']:
            assert digest(OUT/page['path'])==page['sha256']
            assert all(digest(OUT/path)==sha for path,sha in page['sheets'].items())
            labels.update(page['views'])
        sides=('left','right') if parameters.get('side')=='both' else (parameters.get('side','left'),)
        expected={'front','side',*(side+'-'+angle for side in sides for angle in ('palm','edge'))}
        assert labels==expected==set(manifest['views'])
    return review
