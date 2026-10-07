"""Actual model checks across unrelated whole-body poses and narrow edits."""
from pathlib import Path
import sys
import json
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from avatar_app.pose import PosePlan, update_pose, serialize_pose
from avatar_app.planning.pose_interpreter import interpret_pose
from avatar_app.planning.local_model import get_model

def between(plan, name, low, high, inherit=None):
    return low <= plan.get(name, plan.get(inherit) if inherit else 0) <= high

CASES = [
    ('Reach straight up with both arms.', None, lambda p:
     all(between(p, side + '_arm_elevation', 160, 180) and
         between(p, side + '_forearm_elevation', 160, 180, side + '_arm_elevation')
         for side in ('left', 'right'))),
    ('Salute with your right hand, leaving the left arm relaxed.', None, lambda p:
     ((between(p, 'right_arm_elevation', 45, 110) and
       between(p, 'right_forearm_elevation', 120, 180)) or
      between(p, 'right_hand_target_height', .3, .5)) and p.get('left_arm_elevation') < 30),
    ('Sit as if on a chair, with knees bent and arms relaxed.', None, lambda p:
     p.get('pelvis_drop') >= 0.15 and all(between(p, side + '_thigh_elevation', 70, 110)
         and between(p, side + '_shin_elevation', 0, 30) for side in ('left', 'right'))),
    ('Bow deeply from the waist, arms relaxed.', None, lambda p:
     between(p, 'torso_pitch', 45, 100)),
    ('Stand on your left leg and raise the right knee to hip height.', None, lambda p:
     between(p, 'right_thigh_elevation', 70, 110) and between(p, 'right_shin_elevation', 0, 30)
     and abs(p.get('root_pitch')) < 20 and p.get('pelvis_drop') >= 0),
    ('Lie flat on your back with arms out to the sides.', None, lambda p:
     between(p, 'root_pitch', -110, -70) and p.contact == 'none'),
    ('Turn only your head to the left; keep arms, legs and timing unchanged.',
     update_pose(None, {'left_arm_elevation': 90, 'right_arm_elevation': 90, 'duration': 3}),
     lambda p: p.get('head_yaw') > 0 and p.get('left_arm_elevation') == 90
     and p.get('right_arm_elevation') == 90 and p.duration == 3),
]
output = Path(__file__).resolve().parents[1] / 'artifacts'
output.mkdir(exist_ok=True)
case_number = int(sys.argv[sys.argv.index('--case') + 1]) if '--case' in sys.argv else None
report_path = output / 'pose-benchmark.json'
results = json.loads(report_path.read_text(encoding='utf-8')) if case_number and report_path.exists() else []
for number, (text, current, check) in enumerate(CASES, 1):
    if case_number and number != case_number:
        continue
    started = time.perf_counter()
    replay = next((row for row in results if row['prompt'] == text), None) if '--replay' in sys.argv else None
    class Recorder:
        raw = None
        def complete(self, messages, schema):
            self.raw = replay['raw_reply'] if replay else get_model().complete(messages, schema)
            return self.raw
    recorder = Recorder()
    try:
        plan, summary = interpret_pose(text, current, model=recorder)
        result = {'prompt': text, 'plan': serialize_pose(plan), 'passed': check(plan)}
    except Exception as exc:
        result = {'prompt': text, 'error': str(exc), 'passed': False}
    if recorder.raw is not None:
        result['raw_reply'] = recorder.raw
    result['seconds'] = round(time.perf_counter() - started, 2)
    if replay:
        result['replayed'] = True
        result['original_inference_seconds'] = replay.get('original_inference_seconds', replay['seconds'])
    results = [row for row in results if row['prompt'] != text] + [result]
    results.sort(key=lambda row: [case[0] for case in CASES].index(row['prompt']))
    print(json.dumps(result), flush=True)
    report_path.write_text(json.dumps(results, indent=2), encoding='utf-8')
get_model().close()
raise SystemExit(0 if all(result['passed'] for result in results) else 1)
