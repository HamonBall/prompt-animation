"""Managed evidence gates for the initial Stage 05.6b support cases."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.root_motion_evidence import VIEWS, WIDTH, check_process, read, run_native, runtime, PYTHON
from tools.storage_policy import ARTIFACTS, MiB, confined, enforce, inventory, temporary_bytes

OUT = ARTIFACTS / 'stages/05.6b'
NATIVE = 'tests/blender_movement_support_transfers.py'
ENVELOPE = 'tests/blender_support_envelope.py'
RENDERER = ROOT / 'tools/render_support_motion.py'
FRAMING = ROOT / 'tools/render_root_motion.py'
HARNESS = (NATIVE, 'tests/test_movement_support_transfers.py', 'tests/blender_movement_root_travel_flight.py',
           'tests/blender_movement_hips_knees.py', 'tools/preview_movement.py',
           'tests/blender_support_body.py', 'tests/blender_support_palm.py', 'tests/blender_support_foot_points.py',
           'tests/blender_movement_ankles_feet_toes.py', 'tests/fixtures/movement_fragments/v1/entry-neutral.json')
INITIAL_FRAMES = {'balance-left': 61, 'balance-right': 61, 'sole-transfer': 55, 'sole-cycle': 88}
ADDITIONAL_FRAMES = {'heel-cycle': 82, 'forefoot-cycle': 82, 'palm-transfer': 67,
                     'pelvis-transfer': 82, 'knee-transfer': 82, 'back-cycle': 82}
ENVELOPE_FRAMES = {'heel-right-fast': 34, 'forefoot-right-slow': 151, 'palm-left-fast': 34,
                   'knee-right-slow': 151, 'balance-fast': 43, 'balance-slow': 121,
                   'palm-left-cycle': 82, 'pelvis-cycle': 82, 'knee-right-cycle': 82}
FRAMES = {**INITIAL_FRAMES, **ADDITIONAL_FRAMES, **ENVELOPE_FRAMES}
KEYS = tuple(f'{rig}/{case}' for case in INITIAL_FRAMES for rig in ('demo', 'mixamo'))
ADDITIONAL_KEYS = tuple(f'{rig}/{case}' for case in ADDITIONAL_FRAMES for rig in ('demo', 'mixamo'))
ENVELOPE_KEYS = tuple(f'{rig}/{case}' for case in ENVELOPE_FRAMES for rig in ('demo', 'mixamo'))


def case_path(key):
    if key not in KEYS + ADDITIONAL_KEYS + ENVELOPE_KEYS:
        raise ValueError('Unknown support evidence case')
    return confined(OUT / key, OUT)


def numeric_valid(out):
    manifest, _, _ = validate_manifest(out)
    result = read(out / 'result.json')
    stamp = result['stage_05_6b']
    source = read(out / 'source.json')
    if out.parent.name == 'demo':
        assert source == {'kind': 'procedural-demo-v1'}
    else:
        assert source['kind'] == 'imported' and source['sha256'] == store.digest(ROOT / 'Hip Hop Mixamo.fbx')
    check_process(out, 'numeric', 'SUPPORT_NUMERIC_PASSED')
    assert result['review']['passed'] and result['frames'] == len(result['samples']) == len(manifest['expected_frames'])
    assert result['frames'] == FRAMES[out.name]
    assert stamp['rig'] == out.parent.name and stamp['case'] == out.name
    assert manifest['entry']['entry_fixture'] == 'authored:' + out.name
    assert stamp['parameters'] == manifest['entry']['movement_parameters']
    assert manifest['inputs'] == store.input_identity(out) and stamp['producer'] == manifest['inputs']['producer_sha256']
    assert set(stamp['harness']) == set(HARNESS)
    assert all(store.digest(ROOT / name) == digest for name, digest in stamp['harness'].items())
    if out.name in ENVELOPE_FRAMES:
        assert result['envelope_authoring_sha256'] == store.digest(ROOT / ENVELOPE)
    return result


def render_check(out):
    numeric_valid(out)
    manifest, _, motion = validate_manifest(out)
    if not manifest['views'] and not any((out / item).exists() for item in
                                        (*VIEWS, 'support-playback.json', 'render.log.gz', 'render-process.json')):
        return 10
    check_process(out, 'render', 'SUPPORT_RENDER_PASSED')
    playback = read(out / 'support-playback.json')
    assert manifest['complete'] and set(manifest['views']) == set(VIEWS) and store.files_complete(out, manifest)
    assert playback['frames'] == len(manifest['expected_frames']) and playback['passed']
    assert playback['motion_sha256'] == store.digest(motion) and playback['result_sha256'] == store.digest(out / 'result.json')
    assert playback['renderer_sha256'] == store.digest(RENDERER) and playback['runtime'] == runtime()
    assert playback['framing_sha256'] == store.digest(FRAMING)
    for label, view in manifest['views'].items():
        assert view['sheet_sha256'] == store.digest(out / (label + '-sheet.png'))
    return 0


def produce(out, phase):
    if phase == 'numeric':
        if (out / 'preview-manifest.json').exists():
            numeric_valid(out)
            return
        if out.exists() and any(out.iterdir()):
            raise RuntimeError(f'Interrupted output needs reconciliation: {out}')
        enforce(out, growth=8 * MiB, temporary=32 * MiB)
        if out.name in INITIAL_FRAMES:
            script, args = NATIVE, ['--save', out.name]
        elif out.name in ENVELOPE_FRAMES:
            script, args = ENVELOPE, [out.name, '--save']
        else:
            kind = out.name.split('-')[0]
            if kind in ('heel', 'forefoot'):
                script, args = 'tests/blender_support_foot_points.py', [kind, '--save']
            elif kind == 'palm':
                script, args = 'tests/blender_support_palm.py', ['right', '--save']
            else:
                script, args = 'tests/blender_support_body.py', [kind, '--save']
        run_native(out, 'numeric', script, [out.parent.name, *args])
        numeric_valid(out)
    else:
        assert render_check(out) == 10
        run_native(out, 'render', RENDERER, [f'{out.parent.name}/{out.name}'])
        assert render_check(out) == 0


def identity(out):
    assert render_check(out) == 0
    manifest, _, motion = validate_manifest(out)
    return {'motion': store.digest(motion),
            'views': {label: (view['media']['sha256'], view['sheet_sha256'])
                      for label, view in manifest['views'].items()}}


def gate(label, keys, operation):
    paths = [case_path(key) for key in keys]
    expected = ARTIFACTS / 'maintenance/jobs' / label / '.artifact-writer.lock'
    assert all(Path(item['path']) == expected for item in inventory()['leases'])
    assert temporary_bytes(ARTIFACTS) == 0
    if operation == 'storage':
        print(enforce(OUT), flush=True)
    else:
        frames = sum(FRAMES[out.name] for out in paths)
        growth = len(paths) * 8 * MiB + frames * 25000
        temporary = max(FRAMES[out.name] for out in paths) * WIDTH ** 2 * 24 + 32 * MiB
        print(enforce(OUT, growth=growth, temporary=temporary), flush=True)


def make_plan(label, keys):
    from tools.evidence_job import load_plan
    from tools.evidence_pipeline import build

    folder = confined(ARTIFACTS / 'maintenance/stage-05.6b' / label, ARTIFACTS)
    enforce(folder, growth=MiB)
    folder.mkdir(parents=True, exist_ok=True)

    def argv(operation, selection):
        return [str(PYTHON), '-B', __file__, operation, label, *selection]

    config = folder / 'pipeline.json'
    plan = folder / 'plan.json'
    store.atomic_json(config, {
        'schema_version': 1, 'preflight_argv': argv('preflight', keys), 'numeric_gate_argv': argv('verify-numeric', keys),
        'verify_argv': argv('verify-render', keys), 'review_check_argv': argv('review', keys),
        'storage_argv': argv('storage', keys), 'review_directory': str(folder / 'review'),
        'cases': [{'id': key.replace('/', '.'), 'directory': str(case_path(key)), 'check_argv': argv('check', [key]),
                   'render_argv': argv('render', [key]), 'timeout_s': 900} for key in keys],
    })
    build(config, plan)
    value = read(plan)
    numeric_steps = [
        {'id': 'numeric-' + key.replace('/', '.'), 'phase': 'numeric',
         'argv': argv('numeric', [key]), 'timeout_s': 360, 'case_id': key.replace('/', '.')} for key in keys
    ]
    if any(key in ENVELOPE_KEYS for key in keys):
        from tools.legs_evidence import BLENDER
        numeric_steps[:0] = [
            {'id': rig + '.missing-palm', 'phase': 'numeric', 'timeout_s': 240,
             'argv': [str(BLENDER), '--background', '--factory-startup', '--threads', '2', '--python-exit-code',
                      '1', '--python', ENVELOPE, '--', rig, 'missing-palm']}
            for rig in ('demo', 'mixamo')
        ]
    value['steps'][1:1] = numeric_steps
    store.atomic_json(plan, value)
    load_plan(plan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('plan', 'preflight', 'numeric', 'verify-numeric',
                                              'check', 'render', 'verify-render', 'review', 'record-review', 'storage'))
    parser.add_argument('label')
    parser.add_argument('keys', nargs='*')
    parser.add_argument('--front')
    parser.add_argument('--side')
    args = parser.parse_args()
    if not args.label or not args.label[0].isalnum() or not all(char.isalnum() or char in '.-' for char in args.label):
        parser.error('Invalid label')
    keys = args.keys or KEYS
    paths = [case_path(key) for key in keys]
    if len(set(paths)) != len(paths):
        parser.error('Repeated support case')
    operation = args.operation
    if operation == 'plan':
        make_plan(args.label, keys)
    elif operation in ('preflight', 'storage'):
        gate(args.label, keys, operation)
    elif operation in ('verify-numeric', 'verify-render'):
        for out in paths:
            if operation == 'verify-numeric':
                numeric_valid(out)
            else:
                assert render_check(out) == 0
    elif operation == 'review':
        path = OUT / 'visual-review.json'
        reviewed = read(path) if path.exists() else {}
        for key, out in zip(keys, paths):
            if key not in reviewed:
                return 75
            assert all(reviewed[key]['observations'][label].strip() for label in VIEWS)
            current = identity(out)
            assert reviewed[key]['motion'] == current['motion']
            assert reviewed[key]['views'] == {label: list(ids) for label, ids in current['views'].items()}
    else:
        if len(paths) != 1:
            parser.error('Select one case')
        out, = paths
        if operation == 'check':
            return render_check(out)
        if operation == 'record-review':
            if not args.front or not args.side:
                parser.error('Both views need an actual observation')
            path = OUT / 'visual-review.json'
            with store.producer_lease(OUT):
                reviewed = read(path) if path.exists() else {}
                reviewed[keys[0]] = {**identity(out), 'observations': {'front': args.front, 'side': args.side}}
                store.atomic_json(path, reviewed)
        else:
            produce(out, operation)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
