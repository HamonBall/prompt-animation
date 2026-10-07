"""Run actual local inference; write measurements without requiring an avatar."""
from pathlib import Path
import json
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from avatar_app.models import MotionPlan, PlanError
from avatar_app.planning.ai import interpret_ai
from avatar_app.planning.local_model import get_model

CASES = [
    ('Please move into a tyrannosaurus-like pose over three seconds.', None,
     {'duration': 3.0}),
    ('Sink a little lower, but keep the speed and arms the same.', MotionPlan(),
     {'crouch': 0.11}),
    ('Could you lift both arms a bit?', MotionPlan(), {'arm_lift': 0.1}),
    ('Take twice as long to do the same movement.', MotionPlan(), {'duration': 4.0}),
    ('Raise the arms slightly and make the transition last four seconds.', MotionPlan(),
     {'arm_lift': 0.1, 'duration': 4.0}),
    ('Stand a bit taller without changing the arm position.', MotionPlan(), {'crouch': 0.05}),
    ('Walk forward like a T-rex.', MotionPlan(), None),
    ('Lift only the left hand.', MotionPlan(), None),
    ('Do not crouch lower.', MotionPlan(), None),
    ('Make a T-rex pose and dance.', None, None),
    ('Make it better.', MotionPlan(), None),
    ('Set the transition to twenty seconds.', MotionPlan(), None),
]

results = []
for prompt, current, expected in CASES:
    started = time.perf_counter()
    try:
        plan, message = interpret_ai(prompt, current)
        changed = {name: getattr(plan, name) for name in ('duration', 'crouch', 'arm_lift')
                   if getattr(plan, name) != getattr(current or MotionPlan(), name)}
        ok = expected is not None and changed.keys() == expected.keys() and all(
            abs(changed[name] - expected[name]) < 1e-6 for name in expected)
        result = {'prompt': prompt, 'changes': changed, 'message': message, 'passed': ok}
    except PlanError as exc:
        result = {'prompt': prompt, 'message': str(exc), 'passed': expected is None}
    result['seconds'] = round(time.perf_counter() - started, 2)
    results.append(result)
    print(json.dumps(result), flush=True)
get_model().close()
output = Path(__file__).resolve().parents[1] / 'artifacts'
output.mkdir(exist_ok=True)
(output / 'ai-benchmark.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
raise SystemExit(0 if all(row['passed'] for row in results) else 1)
