"""Managed numeric, render and review gates for Stage 05.6a."""
import argparse
import gzip
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.legs_evidence import BLENDER, BUILD, PYTHON, runtime
from tools.storage_policy import ARTIFACTS, MiB, confined, enforce, inventory, temporary_bytes

OUT = ARTIFACTS / 'stages/05.6a'
NATIVE = 'tests/blender_movement_root_travel_flight.py'
MARKER = 'ROOT_NUMERIC_PASSED'
RENDERER = ROOT / 'tools/render_root_motion.py'
PLAYBACK = ROOT / 'tools/root_motion_playback.py'
RENDER_MARKER = 'ROOT_RENDER_PASSED'
VIEWS = ('front', 'side')
WIDTH = 192
HARNESS = {
    NATIVE, 'tests/test_movement_root_travel_flight.py', 'tests/blender_movement_hips_knees.py',
    'tools/preview_movement.py', 'tests/fixtures/movement_fragments/v1/entry-neutral.json',
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def case_path(key):
    rig, _, case = key.partition('/')
    if rig not in ('demo', 'mixamo') or not case or not all(c.isascii() and (c.isalnum() or c == '-') for c in case):
        raise ValueError('Expected a Demo or Mixamo root-motion case')
    return confined(OUT / rig / case, OUT)


def check_process(out, operation, marker):
    process = read(out / (operation + '-process.json'))
    log = out / (operation + '.log.gz')
    assert process['exit_code'] == 0 and process['runtime'] == runtime()
    assert process['log_sha256'] == store.digest(log) and not process['truncated']
    with gzip.open(log, 'rb') as stream:
        data = stream.read(8 * MiB + 1)
    marker = f'{marker} {out.parent.name} {out.name} '.encode()
    assert len(data) <= 8 * MiB and marker in data and BUILD.encode() in data and b'Blender quit' in data


def numeric_valid(out):
    manifest, _, _ = validate_manifest(out)
    result = read(out / 'result.json')
    stamp = result['stage_05_6a']
    inputs = manifest['inputs']
    source = read(out / 'source.json')
    if out.parent.name == 'demo':
        assert source == {'kind': 'procedural-demo-v1'}
    else:
        assert source['kind'] == 'imported' and source['sha256'] == store.digest(ROOT / 'Hip Hop Mixamo.fbx')
    check_process(out, 'numeric', MARKER)
    assert result['review']['passed'] and result['frames'] == len(result['samples']) == len(manifest['expected_frames'])
    assert stamp['case'] == out.name and stamp['rig'] == out.parent.name
    assert manifest['entry']['entry_fixture'] == 'authored:' + stamp['fixture']
    assert inputs == store.input_identity(out) and stamp['application_producer_sha256'] == inputs['producer_sha256']
    assert set(stamp['stage_producer']) == HARNESS
    assert all(store.digest(ROOT / path) == digest for path, digest in stamp['stage_producer'].items())
    return result


def run_native(out, operation, script, args):
    run_runtime = runtime()
    out.mkdir(parents=True, exist_ok=True)
    log = out / (operation + '.log.gz')
    command = [str(BLENDER), '--background', '--factory-startup', '--threads', '2',
               '--python-exit-code', '1', '--python', str(script), '--', *args]
    started = time.perf_counter()
    total = 0
    with subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as child:
        with log.open('xb') as raw, gzip.GzipFile(fileobj=raw, mode='wb') as output:
            for chunk in iter(lambda: child.stdout.read(65536), b''):
                if total < 8 * MiB:
                    output.write(chunk[:8 * MiB - total])
                total += len(chunk)
        code = child.wait()
    store.atomic_json(out / (operation + '-process.json'), {
        'exit_code': code, 'runtime': run_runtime, 'log_sha256': store.digest(log),
        'elapsed_s': time.perf_counter() - started, 'truncated': total > 8 * MiB,
    })
    if code or total > 8 * MiB:
        raise RuntimeError(f'Blender {operation} case failed with exit {code}. See {log}')


def produce(out):
    if (out / 'preview-manifest.json').exists():
        numeric_valid(out)
        print('REUSED_CURRENT_ROOT_NUMERIC', out, flush=True)
        return
    if out.exists() and any(out.iterdir()):
        raise RuntimeError(f'Existing numeric output needs reconciliation: {out}')
    enforce(out, growth=8 * MiB, temporary=32 * MiB)
    run_native(out, 'numeric', NATIVE, ['--rig', out.parent.name, '--case', out.name, '--save'])
    result = numeric_valid(out)
    print(MARKER, out.parent.name, out.name, result['frames'], result['review']['metrics'], flush=True)


def render_check(out):
    numeric_valid(out)
    manifest, _, motion = validate_manifest(out)
    if not manifest['views'] and not any((out / item).exists() for item in
                                        (*VIEWS, 'saved-playback-review.json', 'render.log.gz', 'render-process.json')):
        return 10
    check_process(out, 'render', RENDER_MARKER)
    review = read(out / 'saved-playback-review.json')
    assert manifest['complete'] and manifest['visual_evidence']['complete']
    assert set(manifest['views']) == set(VIEWS) and store.files_complete(out, manifest)
    assert review['passed'] and review['frames'] == len(manifest['expected_frames'])
    assert review['motion_sha256'] == store.digest(motion)
    assert review['result_sha256'] == store.digest(out / 'result.json')
    assert review['validator_sha256'] == store.digest(PLAYBACK) and review['runtime'] == runtime()
    for label, view in manifest['views'].items():
        assert view['renderer_sha256'] == store.digest(RENDERER)
        assert view['sheet_sha256'] == store.digest(out / (label + '-sheet.png'))
    return 0


def review_identity(out):
    assert render_check(out) == 0
    manifest, _, motion = validate_manifest(out)
    return {'motion_sha256': store.digest(motion), 'frames_per_view': len(manifest['expected_frames']),
            'media': {label: view['media']['sha256'] for label, view in manifest['views'].items()},
            'sheets': {label: view['sheet_sha256'] for label, view in manifest['views'].items()}}


def record_review(out, observations):
    assert all(observations.get(label, '').strip() for label in VIEWS)
    target = OUT / 'visual-review.json'
    with store.producer_lease(OUT):
        records = read(target) if target.exists() else {'cases': {}}
        records['cases'][f'{out.parent.name}/{out.name}'] = {
            **review_identity(out), 'observations': observations, 'actually_inspected': True,
        }
        store.atomic_json(target, records)


def review_gate(paths):
    target = OUT / 'visual-review.json'
    records = read(target)['cases'] if target.exists() else {}
    for out in paths:
        record = records.get(f'{out.parent.name}/{out.name}')
        if record is None:
            return 75
        assert record['actually_inspected'] and all(record['observations'][label].strip() for label in VIEWS)
        assert all(record[key] == value for key, value in review_identity(out).items())
    return 0


def gate(label, paths, *, operation):
    expected = ARTIFACTS / 'maintenance/jobs' / label / '.artifact-writer.lock'
    current = inventory()
    assert all(Path(item['path']) == expected for item in current['leases']), current['leases']
    assert temporary_bytes(ARTIFACTS) == 0
    growth = temporary = 0
    if operation == 'preflight':
        missing = sum(not (path / 'preview-manifest.json').exists() for path in paths)
        growth, temporary = missing * 8 * MiB, 32 * MiB
    elif operation == 'preflight-render':
        counts = [read(path / 'result.json')['frames'] for path in paths
                  if not read(path / 'preview-manifest.json')['complete']]
        growth = sum(counts) * 25000
        temporary = max(counts, default=0) * WIDTH ** 2 * 24 + 16 * MiB
        print(f'PREFLIGHT_ROOT_RENDER {len(counts)} cases, {sum(counts) * len(VIEWS)} view frames', flush=True)
    print(enforce(OUT, growth=growth, temporary=temporary), flush=True)


def make_plan(label, keys, *, render=False):
    folder = confined(ARTIFACTS / 'maintenance/stage-05.6a' / label, ARTIFACTS)
    enforce(folder, growth=MiB)
    folder.mkdir(parents=True, exist_ok=True)

    def argv(operation, selected):
        return [str(PYTHON), '-B', __file__, operation, label, *selected]

    if render:
        from tools.evidence_pipeline import build
        config = folder / 'pipeline.json'
        store.atomic_json(config, {
            'schema_version': 1, 'preflight_argv': argv('preflight-render', keys),
            'numeric_gate_argv': argv('verify', keys), 'verify_argv': argv('verify-render', keys),
            'review_check_argv': argv('review', keys), 'storage_argv': argv('storage', keys),
            'review_directory': str(folder / 'review'),
            'cases': [{'id': key.replace('/', '.'), 'directory': str(case_path(key)),
                       'check_argv': argv('check-render', [key]), 'render_argv': argv('render', [key]),
                       'timeout_s': 900} for key in keys],
        })
        build(config, folder / 'render.json')
        return

    def step(id, phase, args, timeout, **metadata):
        return dict(id=id, phase=phase, argv=[str(PYTHON), '-B', __file__, *args],
                    timeout_s=timeout, **metadata)

    plan = folder / 'numeric.json'
    store.atomic_json(plan, {'schema_version': 1, 'steps': [
        step('preflight', 'preflight', ['preflight', label, *keys], 120),
        *(step(key.replace('/', '.'), 'numeric', ['produce', label, key], 360, case_id=key.replace('/', '.'))
          for key in keys),
        step('verify', 'verify', ['verify', label, *keys], 900),
        step('storage', 'storage', ['storage', label, *keys], 120),
    ]})
    from tools.evidence_job import load_plan
    load_plan(plan)
    print(plan, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('plan', 'preflight', 'produce', 'verify', 'storage',
                                              'plan-render', 'preflight-render', 'check-render', 'render',
                                              'verify-render', 'review', 'record-review'))
    parser.add_argument('label')
    parser.add_argument('keys', nargs='+')
    parser.add_argument('--front')
    parser.add_argument('--side')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', args.label):
        parser.error('Use an ASCII job label with letters, digits, dots or hyphens')
    paths = [case_path(key) for key in args.keys]
    if len(set(paths)) != len(paths) or len(paths) > 64:
        parser.error('Expected up to 64 distinct root-motion cases')
    if args.operation in ('plan', 'plan-render'):
        if args.operation == 'plan-render' and len(paths) > 32:
            parser.error('Render at most 32 cases in one review batch')
        make_plan(args.label, args.keys, render=args.operation == 'plan-render')
    elif args.operation in ('preflight', 'storage', 'preflight-render'):
        gate(args.label, paths, operation=args.operation)
    elif args.operation == 'produce':
        if len(paths) != 1:
            parser.error('A producer handles one case at a time')
        produce(paths[0])
    elif args.operation == 'verify':
        for path in paths:
            numeric_valid(path)
        print(f'Verified {len(paths)} current numeric cases', flush=True)
    elif args.operation == 'verify-render':
        for out in paths:
            assert render_check(out) == 0
        print(f'Verified {len(paths)} current render cases', flush=True)
    elif args.operation == 'review':
        return review_gate(paths)
    else:
        if len(paths) != 1:
            parser.error('Expected one render case')
        out = paths[0]
        if args.operation == 'check-render':
            return render_check(out)
        if args.operation == 'record-review':
            if not args.front or not args.side:
                parser.error('Provide actual observations for both views')
            record_review(out, {'front': args.front, 'side': args.side})
        else:
            assert render_check(out) == 10
            run_native(out, 'render', RENDERER, args.keys)
            assert render_check(out) == 0


if __name__ == '__main__':
    raise SystemExit(main())
