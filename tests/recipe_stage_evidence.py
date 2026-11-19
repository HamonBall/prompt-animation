"""Bounded Stage 07 managed evidence plan and verification gates."""
import argparse
import json
from pathlib import Path
import sys

from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.evidence_job import load_plan
from tools.evidence_pipeline import build
from tools.storage_policy import ARTIFACTS, MiB, enforce, inventory, temporary_bytes

ROOT = Path(__file__).resolve().parents[1]
OUT = ARTIFACTS / 'stages/07'
BLENDER = Path(sys.executable).parents[3] / 'blender.exe'
CASES = tuple((rig, route, pose) for rig in ('demo', 'mixamo') for route, pose in (
    ('seat', 'neutral' if rig == 'demo' else 'crouched'), ('seat', 'turned-crouched'), ('step', 'turned-crouched'), ('step', 'crouched'),
    ('loop', 'neutral'), ('air', 'air'),
))


def key(case):
    rig, route, pose = case
    return f'{rig}/{route}-{pose}'


MEDIA = tuple(key(case) for case in CASES if case[2] != 'crouched'
              and (case[1] != 'seat' or case[2] == ('neutral' if case[0] == 'demo' else 'turned-crouched')))


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def native(script, *args):
    return [str(BLENDER), '--background', '--factory-startup', '--threads', '2', '--python-exit-code', '1',
            '--python', f'tests/{script}.py', '--', *args]


def command(operation, *args):
    return [sys.executable, '-B', __file__, operation, *args]


def numeric_valid(name):
    path = OUT / name
    manifest, _, baked = validate_manifest(path)
    result = read(path / 'result.json')
    assert result['review']['passed'] and result['frames'] == len(result['samples']) == len(manifest['expected_frames'])
    assert manifest['inputs'] == store.input_identity(path)
    return manifest, baked


def render_valid(name):
    path = OUT / name
    manifest, baked = numeric_valid(name)
    if not manifest['views'] and not any((path / label).exists() for label in ('front', 'side', 'playback.json')):
        return 10
    playback = read(path / 'playback.json')
    assert playback['motion_sha256'] == store.digest(baked) and playback['result_sha256'] == store.digest(path / 'result.json')
    assert playback['renderer_sha256'] == store.digest(ROOT / 'tests/blender_recipe_review.py')
    assert manifest['complete'] and set(manifest['views']) == {'front', 'side'} and store.files_complete(path, manifest)
    return 0


def account(mode):
    data = inventory()
    temp = temporary_bytes(ARTIFACTS)
    assert temp == 0, temp
    assert all(Path(item['path']).parent.name == 'stage-07-final' for item in data['leases'] if item['active'])
    limits = enforce(OUT, growth=128 * MiB if mode == 'before' else 0, temporary=288 * MiB if mode == 'before' else 0)
    snapshot = {name: data[name] for name in ('bytes', 'file_count', 'free_bytes', 'by_class', 'leases')}
    snapshot.update(stage=data['by_stage'].get('07'), limits=limits, temporary_bytes=temp)
    store.atomic_json(OUT / f'accounting-{mode}.json', snapshot)
    print(json.dumps(limits), flush=True)


def plan():
    assert BLENDER.is_file(), BLENDER
    assert len(set(map(key, CASES))) == len(CASES) and set(MEDIA) <= set(map(key, CASES))
    enforce(OUT, growth=MiB)
    cfg, job = OUT / 'pipeline.json', OUT / 'plan.json'
    store.atomic_json(cfg, {
        'schema_version': 1, 'preflight_argv': command('before'), 'numeric_gate_argv': command('numeric'),
        'verify_argv': command('verify'), 'review_check_argv': command('review'), 'storage_argv': command('after'),
        'review_directory': str(OUT / 'review'),
        'cases': [{'id': name.replace('/', '.'), 'directory': str(OUT / name), 'check_argv': command('check', name),
                   'render_argv': native('blender_recipe_review', name), 'timeout_s': 900} for name in MEDIA],
    })
    build(cfg, job)
    value = read(job)
    checks = [('unit-discovery', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-q'])]
    for rig in ('demo', 'mixamo'):
        checks.append((f'activation-{rig}', native('blender_motion_compiler', rig)))
        checks.append((f'legacy-{rig}', native('blender_presets', rig, '--output-dir', str(OUT / 'legacy'))))
    checks.extend((('legacy-pose', native('blender_poses')),
                   ('legacy-clip', native('blender_clips', '--output-dir', str(OUT / 'legacy')))))
    for case in CASES:
        args = (*case, 'save') if key(case) in MEDIA else case
        checks.append((key(case).replace('/', '.'), native('blender_motion_compiler', *args)))
    value['steps'][1:1] = [{'id': name, 'phase': 'numeric', 'argv': argv, 'timeout_s': 900} for name, argv in checks]
    store.atomic_json(job, value)
    load_plan(job)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('plan', 'before', 'after', 'numeric', 'check', 'verify', 'review'))
    parser.add_argument('case', nargs='?', choices=MEDIA)
    args = parser.parse_args()
    if args.operation == 'plan':
        plan()
    elif args.operation in ('before', 'after'):
        account(args.operation)
    elif args.operation == 'numeric':
        for name in MEDIA:
            numeric_valid(name)
    elif args.operation == 'check':
        return render_valid(args.case)
    elif args.operation == 'verify':
        for name in MEDIA:
            assert render_valid(name) == 0
    else:
        review_path = OUT / 'visual-review.json'
        if not review_path.exists():
            return 75
        observations = read(review_path)
        assert set(observations) == set(MEDIA)
        for name, review in observations.items():
            manifest, baked = numeric_valid(name)
            assert review['motion_sha256'] == store.digest(baked)
            assert set(review['views']) == {'front', 'side'}
            for label, view in review['views'].items():
                assert view['sha256'] == manifest['views'][label]['media']['sha256'] and view['observations'].strip()
    return 0


if __name__ == '__main__':
    sys.exit(main())
