"""Produce and verify representative Stage 08 recipe review bundles."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.evidence_job import load_plan
from tools.evidence_pipeline import build
from tools.storage_policy import ARTIFACTS, MiB, enforce, inventory, temporary_bytes


OUT = ARTIFACTS / 'stages/08'
RENDERER = Path(__file__).with_name('blender_recipe_review.py')
CASE_FAMILIES = {
    'walk': {
        'demo/walk-2-neutral': (('demo', 'atomic-walk', '2', 'preset-travel-arms', 'save'), 175),
        'mixamo/walk-4-turned': (('mixamo', 'atomic-walk', '4', 'preset-travel-turned-arms', 'save'), 247),
    },
    'wave': {
        'demo/wave-left-4-1.25': (('demo', 'wave-save', 'left', '4', '1.25'), 309),
        'mixamo/wave-right-1-1': (('mixamo', 'wave-save', 'right', '1', '1'), 130),
    },
    'jump': {f'{rig}/jump-compact-neutral': ((rig, 'jump-save'), 79) for rig in ('demo', 'mixamo')},
    'chair': {f'{rig}/chair-0.45-neutral': ((rig, 'chair-save', '.45'), 136) for rig in ('demo', 'mixamo')},
    'chair-refresh': {f'{rig}/chair-refresh-0.45-neutral': ((rig, 'chair-refresh', '.45'), 136)
                      for rig in ('demo', 'mixamo')},
}
CASES = {name: case for family in CASE_FAMILIES.values() for name, case in family.items()}


def family_cases(family):
    return tuple(CASE_FAMILIES[family])


def job_path(family):
    return ARTIFACTS / 'maintenance/jobs' / f'stage-08-{family}-visual'


def evidence_growth(family):
    # A chair scene may introduce one new shared rig and environment asset.
    return (112 if family in ('chair', 'chair-refresh') else 64) * MiB


def native(script, *args):
    blender = Path(sys.executable).parents[3] / 'blender.exe'
    assert blender.is_file()
    return [str(blender), '--background', '--factory-startup', '--threads', '2', '--python-exit-code', '1',
            '--python', f'tests/{script}.py', '--', *args]


def bake(name):
    path = OUT / name
    if path.exists():
        numeric(name)
        return 0
    return subprocess.run(native('blender_foundation_recipes', *CASES[name][0]), check=False).returncode


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def numeric(name):
    path = OUT / name
    manifest, _, motion = validate_manifest(path)
    result = read(path / 'result.json')
    assert result['review']['passed'] and not result['experimental']
    assert result['validation_source_sha256'] == store.digest(Path(__file__).with_name('blender_foundation_recipes.py'))
    assert result['frames'] == len(result['samples']) == len(manifest['expected_frames']) == CASES[name][-1]
    assert manifest['inputs'] == store.input_identity(path)
    return manifest, motion


def check(name):
    path = OUT / name
    manifest, motion = numeric(name)
    if not manifest['views'] and not any((path / item).exists() for item in ('playback.json', 'front', 'side')):
        return 10
    playback = read(path / 'playback.json')
    assert playback['motion_sha256'] == store.digest(motion)
    assert playback['result_sha256'] == store.digest(path / 'result.json')
    assert playback['renderer_sha256'] == store.digest(RENDERER)
    assert manifest['complete'] and set(manifest['views']) == {'front', 'side'}
    assert store.files_complete(path, manifest)
    return 0


def account(family, mode):
    state = inventory()
    assert all(Path(lease['path']).parent.resolve() == job_path(family).resolve()
               for lease in state['leases'] if lease['active'])
    temporary = temporary_bytes(ARTIFACTS)
    assert temporary == 0
    budget = enforce(OUT, growth=evidence_growth(family) if mode == 'before' else 0,
                     temporary=192 * MiB if mode == 'before' else 0)
    record = {key: state[key] for key in ('bytes', 'by_class', 'free_bytes', 'leases')}
    record.update(stage=state['by_stage'].get('08'), temporary_bytes=temporary, budget=budget)
    store.atomic_json(OUT / f'{family}-accounting-{mode}.json', record)
    print(json.dumps(budget), flush=True)


def review(family):
    path = OUT / f'{family}-visual-review.json'
    if not path.exists():
        return 75
    observations = read(path)
    assert set(observations) == set(family_cases(family))
    for name, result in observations.items():
        manifest, motion = numeric(name)
        assert result['motion_sha256'] == store.digest(motion)
        assert set(result['views']) == {'front', 'side'}
        for label, entry in result['views'].items():
            assert entry['sha256'] == manifest['views'][label]['media']['sha256']
            assert entry['observations'].strip()
    return 0


def plan(family):
    assert not job_path(family).exists()
    names = family_cases(family)
    missing = []
    for name in names:
        if (OUT / name).exists():
            numeric(name)
        else:
            missing.append(name)
    enforce(OUT, growth=evidence_growth(family), temporary=192 * MiB)

    def cmd(operation, *args):
        return [sys.executable, '-B', str(Path(__file__).resolve()), '--family', family, operation, *args]

    config, destination = (OUT / f'{family}-visual-pipeline.json', OUT / f'{family}-visual-plan.json')
    store.atomic_json(config, {
        'schema_version': 1, 'preflight_argv': cmd('before'), 'numeric_gate_argv': cmd('numeric'),
        'verify_argv': cmd('verify'), 'review_check_argv': cmd('review'), 'storage_argv': cmd('after'),
        'review_directory': str(OUT / f'{family}-review'),
        'cases': [{'id': name.replace('/', '.'), 'directory': str(OUT / name),
                   'check_argv': cmd('check', name), 'timeout_s': 900,
                   'render_argv': native('blender_recipe_review', name, '08')} for name in names],
    })
    build(config, destination)
    spec = read(destination)
    spec['steps'][1:1] = [
        {'id': name.replace('/', '.'), 'phase': 'numeric', 'timeout_s': 240,
         'argv': cmd('bake', name)}
        for name in missing
    ]
    store.atomic_json(destination, spec)
    load_plan(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--family', choices=tuple(CASE_FAMILIES), default='walk')
    parser.add_argument('operation', choices=('plan', 'before', 'after', 'bake', 'numeric', 'check', 'verify', 'review'))
    parser.add_argument('case', nargs='?', choices=CASES)
    args = parser.parse_args()
    names = family_cases(args.family)
    if args.operation == 'plan':
        plan(args.family)
    elif args.operation in ('before', 'after'):
        account(args.family, args.operation)
    elif args.operation in ('bake', 'check'):
        if args.case not in names:
            parser.error(f'{args.operation} requires a case from the selected family')
        return bake(args.case) if args.operation == 'bake' else check(args.case)
    elif args.operation == 'review':
        return review(args.family)
    else:
        for name in names:
            if args.operation == 'verify':
                assert check(name) == 0
            else:
                numeric(name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
