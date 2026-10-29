"""Complete FFV1 conversion, decoded pixels, resume and no-growth integration."""
from pathlib import Path
import json
import os
import shutil
import sys
import tempfile
from unittest.mock import patch
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tools.artifact_store import atomic_json,digest,open_preview,save_scene,write_manifest,files_complete
from tools.lossless_evidence import encode_view,retire_pngs,resume_retirement,decode_view,recover_evidence
from tools.media_transaction import published_frame_plans
from tools import media_transaction
from tools.storage_policy import ARTIFACTS
OUT=ARTIFACTS/'maintenance/storage-v2';scratch=OUT/'.scratch';scratch.mkdir(exist_ok=True)
# A stable previously accepted fixture, outside the concurrently running matrix.
source=OUT/'writer-torso/demo/torso.wave.default'

with tempfile.TemporaryDirectory(dir=scratch,prefix='video-integration-') as temporary:
    case=Path(temporary).resolve();assert case.is_relative_to(scratch.resolve())
    for p in source.iterdir():
        if p.is_file():shutil.copy2(p,case/p.name)
        elif p.name in ('front','side'):shutil.copytree(p,case/p.name)
    m=json.loads((case/'preview-manifest.json').read_text());asset=(source/m['asset']['path']).resolve()
    m['asset']['path']=os.path.relpath(asset,case);m['bundle_root']=os.path.relpath(ARTIFACTS,case)
    shutil.copy2(source/m['profile']['path'],case/'profile.json');m['profile']['path']='profile.json'
    atomic_json(case/'preview-manifest.json',m);h=open_preview(case)
    plans=[];views={v:{} for v in ('front','side') if (case/v/'0001.png').exists()}
    assert len(views)==2,'Pixel fixtures require both previously rendered views'
    with patch.object(media_transaction,'atomic_replace',side_effect=OSError('injected movie publication failure')):
        try:encode_view(case,'front',m['expected_frames'],fps=m['fps'],fps_base=m['fps_base']);raise AssertionError('Publication failure not injected')
        except OSError:pass
    assert (case/'.front.pending.mkv').exists(),'Verified candidate was discarded after interrupted publication'
    for view in views:
        media,plan=encode_view(case,view,m['expected_frames'],fps=m['fps'],fps_base=m['fps_base'])
        views[view]['media']=media;plans.append(plan)
    # Simulate retry after verified movies exist but the manifest is still old.
    # Identical PNGs must reuse the verified files rather than accumulate copies.
    for view in views:
        media,_=encode_view(case,view,m['expected_frames'],fps=m['fps'],fps_base=m['fps_base'])
        assert media==views[view]['media']
    assert len(list(case.glob('*.mkv')))==2
    save_scene(case/'preview.blend')
    try:write_manifest(case,h.scene,views=views,complete=True)
    except RuntimeError:
        from tools.lossless_evidence import media_complete
        observed=write_manifest(case,h.scene,views=views,complete=False)
        print('MEDIA_DEBUG',observed['fps'],observed['fps_base'],len(observed['expected_frames']),
              {v:{'media':media_complete(case,details['media'],observed['expected_frames'],fps=observed['fps'],fps_base=observed['fps_base']),
                   'sheet':(case/(v+'-sheet.png')).exists(),'frames':len(details['media']['frames'])} for v,details in views.items()},flush=True)
        raise
    assert files_complete(case,json.loads((case/'preview-manifest.json').read_text()))
    assert sum(len(p) for p in published_frame_plans(case))==2*len(m['expected_frames'])
    original=Path.unlink;counter=[0]
    def interrupted(path,*args,**kwargs):
        if path.suffix=='.png' and path.parent.name=='front':
            counter[0]+=1
            if counter[0]==2:raise RuntimeError('injected media interruption')
        return original(path,*args,**kwargs)
    with patch.object(Path,'unlink',interrupted):
        try:retire_pngs(case,plans);raise AssertionError('Interruption was not injected')
        except RuntimeError as error:assert 'injected' in str(error)
    recover_evidence(case);assert not list((case/'front').glob('*.png')) and not list((case/'side').glob('*.png'))
    decoded={}
    for view in views:
        folder=case/'.scratch'/view;decoded[view]=decode_view(case,view,folder)
        for p in folder.glob('*.png'):shutil.copy2(p,case/view/p.name)
    plans=[]
    for view in views:
        media,plan=encode_view(case,view,m['expected_frames'],fps=m['fps'],fps_base=m['fps_base']);views[view]['media']=media;plans.append(plan)
    write_manifest(case,h.scene,views=views,complete=True);retire_pngs(case,plans)
    assert len(list(case.glob('*.mkv')))==2 and not list(case.glob('*.blend1'))
    sizes={view:(case/views[view]['media']['path']).stat().st_size for view in views}
    atomic_json(OUT/'lossless-evidence-review.json',{'passed':True,'frames_per_view':len(m['expected_frames']),
                'decoded':{k:v['passed'] for k,v in decoded.items()},'interrupted_cleanup_resumed':True,'repeat_media_files':2,
                'pre_manifest_reuse':True,'post_manifest_retirement_plan_recovered':True,'video_bytes':sizes,
                'publication_failure_resumed':True,
                'sheet_bytes':sum((case/(v+'-sheet.png')).stat().st_size for v in views)})
print('ALL_LOSSLESS_EVIDENCE_CHECKS_PASSED',flush=True)
