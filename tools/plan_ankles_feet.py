"""Build bounded Stage 05.5 numeric and render jobs for the shared supervisor."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from ankles_feet_toes_cases import cases
from tools.ankles_feet_evidence import OUT, PYTHON, case_path, numeric_valid, read, render_valid, review_identity, runtime
from tools.artifact_store import atomic_json
from tools.evidence_job import load_plan
from tools.evidence_pipeline import build
from tools.storage_policy import ARTIFACTS, confined, enforce

EVIDENCE = str(ROOT / 'tools/ankles_feet_evidence.py')
HERE = str(Path(__file__).resolve())
PLAN_DIR = ARTIFACTS / 'maintenance' / 'stage-05.5'


def python(*args):
    return [str(PYTHON), '-B', *args]


def selected(names):
    available = [(rig, name) for rig in ('demo', 'mixamo') for name, movement, *_ in cases()
                 if not (rig == 'demo' and movement == 'toes.curl')]
    if not names:
        return available
    keys = set(names)
    selection = [(rig, name) for rig, name in available if f'{rig}/{name}' in keys]
    if len(selection) != len(names):
        raise ValueError('Unknown, unavailable or duplicate selected case')
    return selection


def case_command(operation, rig, name):
    return python(EVIDENCE, operation, '--rig', rig, '--case', name)


def stage_gate(operation, rows):
    keys = [f'{rig}/{name}' for rig, name in rows]
    return python(HERE, operation, *keys)


def make_plan(operation, rows, label):
    folder = confined(PLAN_DIR / label, PLAN_DIR)
    enforce(folder, growth=1024**2)
    folder.mkdir(parents=True, exist_ok=True)
    plan = folder / 'plan.json'
    preflight = stage_gate('preflight-' + operation, rows)
    if operation == 'numeric':
        steps = [{'id': 'preflight', 'phase': 'preflight', 'argv': preflight, 'timeout_s': 120}]
        for rig, name in rows:
            steps.append({'id': f'{rig}.{name}', 'phase': 'numeric',
                          'argv': case_command('numeric', rig, name), 'timeout_s': 240})
        steps.extend([
            {'id': 'verify', 'phase': 'verify', 'argv': stage_gate('verify-numeric', rows), 'timeout_s': 900},
            {'id': 'storage', 'phase': 'storage', 'argv': stage_gate('storage', rows), 'timeout_s': 120},
        ])
        atomic_json(plan, {'schema_version': 1, 'steps': steps})
        load_plan(plan)
    else:
        config = {
            'schema_version': 1, 'preflight_argv': preflight,
            'numeric_gate_argv': stage_gate('verify-numeric', rows),
            'verify_argv': stage_gate('verify-render', rows),
            'review_check_argv': stage_gate('review', rows),
            'storage_argv': stage_gate('storage', rows),
            'review_directory': str(folder / 'review'),
            'cases': [{'id': f'{rig}.{name}', 'directory': str(case_path(rig, name)),
                       'check_argv': case_command('check', rig, name),
                       'render_argv': case_command('render', rig, name), 'timeout_s': 600}
                      for rig, name in rows],
        }
        config_path = folder / 'config.json'
        atomic_json(config_path, config)
        build(config_path, plan)
    print(plan, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('numeric', 'render', 'preflight-numeric', 'preflight-render',
                                              'verify-numeric', 'verify-render', 'review', 'storage'))
    parser.add_argument('keys', nargs='*')
    parser.add_argument('--label', default='matrix')
    args = parser.parse_args()
    rows = selected(args.keys)
    paths = [case_path(*row) for row in rows]
    operation = args.operation
    if operation in ('numeric', 'render'):
        if operation == 'render' and len(rows) > 8:
            parser.error('Render at most eight cases per review batch')
        make_plan(operation, rows, args.label)
    elif operation == 'preflight-numeric':
        runtime()
        missing = sum(not (path / 'preview-manifest.json').exists() for path in paths)
        print(enforce(OUT, growth=missing * 3 * 1024**2, temporary=32 * 1024**2))
    elif operation == 'preflight-render':
        runtime()
        # Reserve original frame PNGs and one full sheet per view. Actual case
        # allocation is also guarded inside the shared frame writer.
        counts = [read(path / 'result.json')['frames'] for path in paths
                  if not read(path / 'preview-manifest.json')['complete']]
        frames = sum(counts)
        temporary = max(counts, default=0) * 160**2 * 24
        print(enforce(OUT, growth=frames * 14000, temporary=temporary))
        print(f'PREFLIGHT_RENDER {len(counts)} cases, {frames * 2} view frames (initial 14 KB retained/sample estimate)')
    elif operation in ('verify-numeric', 'verify-render'):
        validate = numeric_valid if operation == 'verify-numeric' else render_valid
        for path in paths:
            assert validate(path), path
        print(f'{operation} passed for {len(paths)} current cases', flush=True)
    elif operation == 'review':
        review = OUT / 'visual-review.json'
        values = read(review)['cases'] if review.exists() else {}
        for (rig, name), path in zip(rows, paths):
            record = values.get(f'{rig}/{name}')
            if record is None:
                return 75
            assert record['actually_inspected'] and record['observation'].strip()
            assert all(record[key] == value for key, value in review_identity(path).items()), path
    else:
        print(enforce(OUT))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
