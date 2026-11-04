"""Stage 05.4 saved-action replay, shared full-body views and lossless writer."""
import sys,json,time
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.movement_library import contracts as c
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.storage_policy import enforce
from tools.lossless_evidence import encode_view,retire_pngs,recover_evidence,media_complete
from tools.movement_evidence import render
from tools.legs_evidence import OUT,runtime,numeric_valid,publish_visuals
from tools.hips_knees_playback import verify
rig=sys.argv[sys.argv.index('--rig')+1];name=sys.argv[sys.argv.index('--case')+1];out=OUT/rig/name
runtime();assert numeric_valid(out);renderer=store.digest(Path(__file__));playback_source=store.digest(ROOT/'tools/hips_knees_playback.py')
with store.producer_lease(out):
    recover_evidence(out);manifest,asset,motion=validate_manifest(out);before=(store.digest(motion),motion.stat().st_mtime_ns)
    p=c.loads(c.AvatarProfile,(out.parent/'profile.json').read_text());result=json.loads((out/'result.json').read_text())
    h=store.open_preview(out);started=time.perf_counter();replay=verify(h,p,out,result);replay_s=time.perf_counter()-started
    views=dict(manifest['views']);plans=[];timings={}
    for label in ('front','side'):
        if label in views and views[label].get('renderer_sha256')==renderer and media_complete(out,views[label]['media'],manifest['expected_frames'],fps=30,fps_base=1):continue
        started=time.perf_counter();record=render(h,p,out,side=label=='side',width=192)
        media,plan=encode_view(out,label,manifest['expected_frames'],fps=manifest['fps'],fps_base=manifest['fps_base'])
        record.update(media=media,renderer_sha256=renderer,playback_validator_sha256=playback_source,framing='complete source mesh; full body')
        views[label]=record;plans.append(plan);timings[label]=time.perf_counter()-started
        publish_visuals(out,h.scene,views,complete=False)
    h.scene.frame_set(1);publish_visuals(out,h.scene,views,complete=True);retire_pngs(out,plans)
    assert before==(store.digest(motion),motion.stat().st_mtime_ns)
    assert renderer==store.digest(Path(__file__)) and playback_source==store.digest(ROOT/'tools/hips_knees_playback.py')
    store.atomic_json(out/'render-timing.json',{'saved_playback_s':replay_s,'seconds_by_view':timings,'rendered_frames':2*len(manifest['expected_frames'])})
    enforce(out);print('LEGS_SAVED_PLAYBACK_AND_RENDER_PASSED',rig,name,replay_s,timings,flush=True)
