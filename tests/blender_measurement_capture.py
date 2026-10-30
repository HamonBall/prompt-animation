"""Read-only batch optimization must exactly match uncached rig measurements."""
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from avatar_app.blender import rig_profile as rp
from avatar_app.movement_library import contracts as c
from tools.artifact_store import open_preview,atomic_json

OUT=ROOT/'artifacts/stages/05.2';report={}
if '--case-root' in sys.argv:OUT=Path(sys.argv[sys.argv.index('--case-root')+1]).resolve()
REPORT=Path(sys.argv[sys.argv.index('--output-dir')+1]).resolve() if '--output-dir' in sys.argv else OUT
CASE=sys.argv[sys.argv.index('--case')+1] if '--case' in sys.argv else 'arm.raise.default'
for rig in ('demo','mixamo'):
    case=OUT/rig/CASE;h=open_preview(case)
    p=c.loads(c.AvatarProfile,(case.parent/'profile.json').read_text())
    h.scene.frame_set(17,subframe=.25)
    with patch.object(rp,'_fingerprint',wraps=rp._fingerprint) as fingerprints:
        start=time.perf_counter();cached=rp.capture_motion_state(h,p,revision=1);cached_time=time.perf_counter()-start
        cached_calls=fingerprints.call_count
    binding=rp._MEASUREMENT_BINDING
    class Uncached:
        def get(self):return None
        def set(self,value):return binding.set(value)
        def reset(self,token):binding.reset(token)
    with patch.object(rp,'_MEASUREMENT_BINDING',Uncached()),patch.object(rp,'_fingerprint',wraps=rp._fingerprint) as fingerprints:
        start=time.perf_counter();uncached=rp.capture_motion_state(h,p,revision=1);uncached_time=time.perf_counter()-start
        uncached_calls=fingerprints.call_count
    assert cached==uncached,'Read-only batching changed measured values'
    assert cached_calls==1 and uncached_calls>10,(cached_calls,uncached_calls)
    assert binding.get() is None,'Binding escaped the capture call'
    scale=h.rig.scale.copy()
    try:
        h.rig.scale*=1.01;bpy.context.view_layer.update()
        for measure in (lambda:rp.capture_motion_state(h,p,revision=1),lambda:rp.measure_endpoint(h,p,'left.hand')):
            try:measure();raise AssertionError('Changed rig scale was accepted')
            except c.MotionContractError as error:assert error.code=='ENTRY_MISMATCH'
    finally:h.rig.scale=scale;bpy.context.view_layer.update()
    report[rig]={'exact_snapshot_equality':True,'fingerprint_calls_cached':cached_calls,'fingerprint_calls_uncached':uncached_calls,
                 'capture_seconds_cached':cached_time,'capture_seconds_uncached':uncached_time,'changed_scale_rejected':True}
atomic_json(REPORT/'measurement-capture-review.json',report)
print('ALL_MEASUREMENT_CAPTURE_CHECKS_PASSED',json.dumps(report),flush=True)
