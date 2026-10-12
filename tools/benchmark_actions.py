"""Compare real AI stage planning with the hand-authored executor reference."""
from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar_app.planning.action_interpreter import interpret_action
from avatar_app.planning.movements import lying_down_plan
from avatar_app.motion import ActionPlan, serialize_action
from avatar_app.planning.local_model import get_model


class Recorder:
    def complete(self, messages, schema):
        self.raw = get_model().complete(messages, schema)
        return self.raw


out = ROOT / 'artifacts' / 'motion'
out.mkdir(parents=True, exist_ok=True)
reference = lying_down_plan()
model = Recorder()
started = time.perf_counter()
result = {'request': 'Lie down on the ground, moving through a crouch and sitting before lowering the torso.',
          'reference': serialize_action(reference)}
try:
    plan, explanation = interpret_action(result['request'], model=model)
    result.update(plan=serialize_action(plan) if isinstance(plan, ActionPlan) else None,
                  stages_generated=isinstance(plan, ActionPlan), explanation=explanation)
    if isinstance(plan, ActionPlan):
        result['reference_comparison'] = {
            'reference_stage_count': len(reference.stages), 'model_stage_count': len(plan.stages),
            'reference_duration': reference.duration, 'model_duration': plan.duration,
            'lying_endpoint': abs(plan.final_pose.get('root_pitch') + 90) < 10,
            'legs_extended_along_body': all(plan.final_pose.get(side + '_' + part + '_elevation') < 15
                for side in ('left', 'right') for part in ('thigh', 'shin'))}
except Exception as exc:
    result.update(error=str(exc), stages_generated=False)
finally:
    result.update(raw=getattr(model, 'raw', None), seconds=time.perf_counter() - started)
    (out / 'ai-plan.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    get_model().close()
print(json.dumps(result, indent=2))
if not result['stages_generated'] or not all(result['reference_comparison'][key]
        for key in ('lying_endpoint', 'legs_extended_along_body')):
    raise SystemExit(1)
