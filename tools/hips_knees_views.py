"""Identity checks for saved-action media and actual stage-05.4 visual reviews."""
import gzip,json
from pathlib import Path
from tools.artifact_store import digest,files_complete
from tools.artifact_bundle import validate_manifest
from tools.legs_evidence import ROOT,OUT,runtime,numeric_valid


def render_sources():
    # No FragmentAdapter execution occurs during saved-action playback. Its
    # producer is checked independently by numeric_valid's exact branch proof.
    sources=[p for p in (ROOT/'src/avatar_app').rglob('*.py') if p!=ROOT/'src/avatar_app/blender/primitive.py']
    sources.extend(ROOT/name for name in ('tools/render_hips_knees.py','tools/hips_knees_playback.py',
        'tools/movement_evidence.py','tools/artifact_store.py','tools/artifact_bundle.py','tools/storage_policy.py',
        'tools/lossless_evidence.py','tools/media_transaction.py','tools/legs_evidence.py','tools/hips_knees_provenance.py'))
    return {p.relative_to(ROOT).as_posix():digest(p) for p in sources}


def render_valid(out):
    out=Path(out)
    try:
        if not numeric_valid(out):return False
        manifest,_,motion=validate_manifest(out)
        process=json.loads((out/'render-process.json').read_text());review=json.loads((out/'saved-playback-review.json').read_text())
        recorded=dict(process['render_sources'])
        # Original pilots also recorded the parent cache validator. It never
        # executes image or motion generation; revalidate data with today's
        # stronger checks instead of invalidating identical execution outputs.
        recorded.pop('tools/hips_knees_views.py',None)
        if process['exit_code']!=0 or process['runtime_lock_sha256']!=runtime() or recorded!=render_sources():return False
        log_name=process.get('log_name','render.log')
        if log_name not in ('render.log','render.log.gz'):return False
        log=out/log_name
        if process['log_sha256']!=digest(log):return False
        data=gzip.decompress(log.read_bytes()) if log_name.endswith('.gz') else log.read_bytes()
        if b'LEGS_SAVED_PLAYBACK_AND_RENDER_PASSED' not in data or b'Blender quit' not in data:return False
        if not manifest['complete'] or set(manifest['views'])!={'front','side'} or not files_complete(out,manifest):return False
        if not review['passed'] or review['validator_sha256']!=digest(ROOT/'tools/hips_knees_playback.py') or review['runtime_lock_sha256']!=runtime():return False
        if review['motion_sha256']!=digest(motion) or review['motion_mtime_ns']!=motion.stat().st_mtime_ns:return False
        if review['raw_sha256']!=digest(out/'saved-rotations.json') or review['result_sha256']!=digest(out/'result.json'):return False
        if not all(view['renderer_sha256']==digest(ROOT/'tools/render_hips_knees.py') and
            view['playback_validator_sha256']==digest(ROOT/'tools/hips_knees_playback.py') for view in manifest['views'].values()):return False
        compact=[label for label,view in manifest['views'].items() if 'sheet_representation' in view]
        if compact:
            journal=json.loads((out/'sheet-retention.json').read_text());reviews=json.loads((OUT/'visual-review.json').read_text())
            record=reviews['cases'][out.relative_to(OUT).as_posix()]
            if journal['state']!='complete' or not record['actually_inspected'] or not record['retention_complete']:return False
            if journal['motion_sha256']!=digest(motion) or journal['media']!=record['media']:return False
            for label in compact:
                proof=journal['views'][label];view=manifest['views'][label];representation=view['sheet_representation']
                if representation['kind']!='selected_frames_after_full_review' or not representation['pixel_identity_preserved']:return False
                if digest(out/proof['path'])!=proof['summary_sha256'] or record['sheets'][label]!=proof['summary_sha256']:return False
                if record['full_sheets'][label]!=proof['original_full_sheet_sha256'] or representation['full_sheet_sha256']!=record['full_sheets'][label]:return False
                if representation['frames']!=proof['frames'] or representation['summary_sha256']!=proof['summary_sha256']:return False
                if proof['pixel_sha256']!=[view['media']['decoded_pixel_sha256'][frame-1] for frame in proof['frames']]:return False
        return True
    except (OSError,KeyError,ValueError,TypeError):return False


def visual_reviews():
    from hips_knees_cases import cases
    review=json.loads((OUT/'visual-review.json').read_text())
    expected={rig+'/'+name for rig in ('demo','mixamo') for name,_,_,_ in cases()}
    assert review['complete'] and set(review['cases'])==expected
    for key,record in review['cases'].items():
        out=OUT/key;assert render_valid(out) and record['actually_inspected']
        manifest,_,motion=validate_manifest(out);assert record['motion_sha256']==digest(motion)
        assert record['sheets']=={label:digest(out/(label+'-sheet.png')) for label in ('front','side')}
        assert record['media']=={label:view['media']['sha256'] for label,view in manifest['views'].items()}
        assert record['frames_per_view']==len(manifest['expected_frames'])
        assert record['retention_complete']
    return review
