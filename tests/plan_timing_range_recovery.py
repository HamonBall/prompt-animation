"""Resume 05.7a range evidence on the corrected pattern source."""

import argparse
from pathlib import Path
import subprocess
import sys

import timing_baseline_evidence as evidence
import timing_follow_through_evidence as follow_through
import timing_range_evidence as ranges
from tools.artifact_store import atomic_json, producer_lease
from tools.evidence_job import load_plan
from tools.evidence_pipeline import build
from tools.root_motion_evidence import read
from tools.storage_policy import MiB, enforce

CASES = ranges.CASES
ORDER = tuple(sorted(CASES, key=lambda key: (-CASES[key][-1], key)))
PLAN = evidence.ARTIFACTS / 'maintenance/stage-05.7a/range-completion'
HERE = Path(__file__).resolve().parent
PRODUCER = 'timing_range_evidence.py'
FOLLOW_THROUGH_PRODUCER = 'timing_follow_through_evidence.py'


def producer(key):
    return FOLLOW_THROUGH_PRODUCER if key in follow_through.CASES else PRODUCER


def argv(script, operation, *keys):
    return [sys.executable, '-B', str(HERE / script), operation, *keys]


def command(arguments, timeout):
    return subprocess.run(arguments, cwd=evidence.ROOT, check=False, timeout=timeout).returncode


def numeric():
    failed = []
    for key in ORDER:
        print('TIMING_RANGE_CASE_START', key, flush=True)
        try:
            code = command(argv(producer(key), 'numeric', key), 420)
        except subprocess.TimeoutExpired:
            code = 124
        if code:
            failed.append(key)
        print('TIMING_RANGE_CASE_RESULT', key, code, flush=True)
    if failed:
        print('TIMING_RANGE_FAILED', ','.join(failed), flush=True)
        return 1
    return 0


def make_plan():
    enforce(PLAN, growth=MiB)
    config, path = PLAN / 'pipeline.json', PLAN / 'plan.json'
    script = Path(__file__).name
    value = {'schema_version': 1, 'preflight_argv': argv(script, 'preflight'),
             'numeric_gate_argv': argv(script, 'numeric'), 'verify_argv': argv(script, 'verify'),
             'review_check_argv': argv(script, 'review'), 'storage_argv': argv(script, 'storage'),
             'review_directory': str(PLAN / 'review'), 'cases': []}
    for key in ORDER:
        value['cases'].append({'id': key.replace('/', '.'), 'directory': str(evidence.case_path(key)),
            'check_argv': argv(producer(key), 'check', key), 'render_argv': argv(producer(key), 'render', key),
            'timeout_s': 900})
    with producer_lease(PLAN):
        atomic_json(config, value)
        build(config, path)
        plan = read(path)
        previous = read(evidence.ARTIFACTS / 'maintenance/stage-05.7a/range-evidence/plan.json')
        selected = {item['id']: item for item in previous['steps']}
        plan['steps'][2:2] = [selected['affected-native-regressions']]
        atomic_json(path, plan)
    load_plan(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('routes', 'plan', 'numeric', 'verify', 'review', 'preflight', 'storage'))
    operation = parser.parse_args().operation
    evidence.CASES = CASES
    ranges_job = evidence.ARTIFACTS / 'maintenance/jobs/stage-05.7a-range-completion'
    evidence.JOB = ranges_job
    if operation == 'routes':
        for key in ORDER:
            print(key, evidence.case_path(key), producer(key), CASES[key][-1])
    elif operation == 'plan':
        make_plan()
    elif operation == 'numeric':
        return numeric()
    elif operation in ('verify', 'review'):
        fixed = tuple(key for key in ORDER if key in follow_through.CASES)
        unchanged = tuple(key for key in ORDER if key not in follow_through.CASES)
        return (command(argv(FOLLOW_THROUGH_PRODUCER, operation, *fixed), 900)
                or command(argv(PRODUCER, operation, *unchanged), 900))
    else:
        evidence.budget(ORDER, operation == 'preflight')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
