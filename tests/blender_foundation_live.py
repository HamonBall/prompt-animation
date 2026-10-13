"""Actual local interpretation adapts internal mechanics through the prompt UI."""
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from avatar_app import main as app
from avatar_app.motion import ActionPlan, serialize_action
from avatar_app.planning.local_model import get_model

with patch.object(app, '_default_avatar', return_value=ROOT/'absent.fbx'):
    app.main()
engine = get_model()
report = {}
(ROOT/'artifacts').mkdir(exist_ok=True)


class RecordingModel:
    def complete(self, messages, schema, **kwargs):
        started = time.perf_counter()
        raw = engine.complete(messages, schema, **kwargs)
        report.update(response=json.loads(raw), interpretation_seconds=time.perf_counter()-started)
        (ROOT/'artifacts'/'foundation-live.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        return raw


scene = bpy.context.scene
scene.avatar_prompt = 'Greet someone with a gentle left-handed wave, turning your head toward the left.'
before = app._state['plan']
started = time.perf_counter()
try:
    with patch('avatar_app.planning.action_interpreter.get_model', return_value=RecordingModel()):
        assert bpy.ops.avatar.prompt() == {'FINISHED'}
    after = app._state['plan']
    assert report['response']['kind'] == 'adapt', report['response']
    assert report['response']['base']['name'] == 'wave'
    assert report['response']['base']['side'] == 'left'
    assert isinstance(after, ActionPlan) and len(after.stages) > 1
    assert after.revision == before.revision+1
    assert after.final_pose.get('head_yaw') >= 10
    assert all(stage.contacts for stage in after.stages)
    assert not app._state['experimental']
    report.update(plan=serialize_action(after),
                  construction_seconds=time.perf_counter()-started-report['interpretation_seconds'])
    (ROOT/'artifacts'/'foundation-live.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('LIVE_PROMPT_FOUNDATION_PASSED', scene.avatar_status, flush=True)
finally:
    engine.close()
