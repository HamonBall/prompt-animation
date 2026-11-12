"""Bake, render and index Stage 05.6c review batches."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.evidence_job import load_plan
from tools.evidence_pipeline import build
from tools.root_motion_evidence import PYTHON, VIEWS, WIDTH, check_process, read, run_native, runtime
from tools.storage_policy import ARTIFACTS, MiB, confined, enforce, inventory, temporary_bytes

OUT = ARTIFACTS / 'stages/05.6c'
NATIVE = ROOT / 'tests/blender_coordinated_evidence.py'
FRAMING = ROOT / 'tools/render_root_motion.py'
HARNESS = (
    'tools/coordinated_evidence.py', 'tests/blender_coordinated_evidence.py',
    'tests/blender_movement_coordinated_body_moves.py', 'tests/blender_movement_crawl.py',
    'tests/blender_movement_root_travel_flight.py', 'tests/blender_movement_hips_knees.py',
    'tests/blender_movement_ankles_feet_toes.py', 'tests/blender_support_body.py',
    'tests/test_movement_support_transfers.py', 'tests/fixtures/movement_fragments/v1/entry-neutral.json',
)


def batch_cases():
    cases = {}

    def add(rig, case, move, pose, frames, **parameters):
        cases[f'{rig}/{case}'] = {'move': 'body.' + move, 'pose': pose,
                                  'max_frames': frames, 'parameters': parameters}

    for rig in ('demo', 'mixamo'):
        for pose, depth in (('neutral', .06), ('turned-crouched', .10)):
            add(rig, 'lower-rise-' + pose, 'lower_rise', pose, 80, depth_m=depth)
            add(rig, 'takeoff-land-push-off-' + pose, 'takeoff_land', pose, 132)
        add(rig, 'step-left', 'step', 'turned-crouched', 62, side='left')
        add(rig, 'step-right', 'step', 'crouched', 62, side='right')
        lead, pose = ('left', 'turned-crouched') if rig == 'demo' else ('right', 'crouched')
        add(rig, 'lunge-' + lead, 'lunge', pose, 80, lead=lead)
        add(rig, 'low-crawl-' + lead, 'crawl', pose, 170, lead=lead, distance_m=.04, swing_s=.5)
        add(rig, 'prepared-seat', 'floor_transfer', 'pelvis', 44)
        add(rig, 'prepared-kneel', 'kneel_rise', 'knee', 80)
        pose = 'neutral' if rig == 'demo' else 'turned-crouched'
        add(rig, 'standing-to-seated', 'floor_transfer', pose, 128, route='standing_to_seated')
        add(rig, 'seated-to-back', 'floor_transfer', pose, 128, route='seated_to_back')
        add(rig, 'planted-kneel-' + lead, 'kneel_rise', pose, 260, route='planted_to_knee', side=lead)
    return cases


CASES = batch_cases()


def case_path(key):
    if key not in CASES:
        raise ValueError(f'Unknown coordinated movement case: {key}')
    return confined(OUT / key, OUT)


def numeric_valid(key):
    out = case_path(key)
    manifest, _, _ = validate_manifest(out)
    result = read(out / 'result.json')
    stamp = result['stage_05_6c']
    source = read(out / 'source.json')
    if out.parent.name == 'demo':
        assert source == {'kind': 'procedural-demo-v1'}
    else:
        assert source['kind'] == 'imported' and source['sha256'] == store.digest(ROOT / 'Hip Hop Mixamo.fbx')
    check_process(out, 'numeric', 'COORDINATED_NUMERIC_PASSED')
    assert stamp['key'] == key and stamp['spec'] == CASES[key]
    assert stamp['parameters'] == manifest['entry']['movement_parameters']
    assert manifest['entry']['entry_fixture'] == 'authored:' + CASES[key]['pose']
    assert result['review']['passed'] and not result['experimental']
    assert 0 < result['frames'] <= CASES[key]['max_frames']
    assert result['frames'] == len(result['samples']) == len(manifest['expected_frames'])
    assert manifest['inputs'] == store.input_identity(out)
    assert stamp['producer'] == manifest['inputs']['producer_sha256']
    assert set(stamp['harness']) == set(HARNESS)
    assert all(store.digest(ROOT / name) == digest for name, digest in stamp['harness'].items())
    return result


def render_check(key):
    out = case_path(key)
    numeric_valid(key)
    manifest, _, motion = validate_manifest(out)
    if not manifest['views'] and not any((out / name).exists() for name in (
            *VIEWS, 'playback.json', 'render.log.gz', 'render-process.json')):
        return 10
    check_process(out, 'render', 'COORDINATED_RENDER_PASSED')
    playback = read(out / 'playback.json')
    assert manifest['complete'] and set(manifest['views']) == set(VIEWS) and store.files_complete(out, manifest)
    assert playback['passed'] and playback['frames'] == len(manifest['expected_frames'])
    assert playback['motion_sha256'] == store.digest(motion) and playback['result_sha256'] == store.digest(out / 'result.json')
    assert playback['validator_sha256'] == store.digest(NATIVE) and playback['runtime'] == runtime()
    assert playback['framing_sha256'] == store.digest(FRAMING)
    for label, view in manifest['views'].items():
        assert view['sheet_sha256'] == store.digest(out / (label + '-sheet.png'))
    return 0


def review_identity(key):
    assert render_check(key) == 0
    manifest, _, motion = validate_manifest(case_path(key))
    return {'motion': store.digest(motion), 'views': {
        label: [view['media']['sha256'], view['sheet_sha256']] for label, view in manifest['views'].items()}}


def storage_gate(label, keys, preflight):
    lease = ARTIFACTS / 'maintenance/jobs' / label / '.artifact-writer.lock'
    assert all(Path(item['path']) == lease for item in inventory()['leases'])
    assert temporary_bytes(ARTIFACTS) == 0
    frames = [CASES[key]['max_frames'] for key in keys]
    growth = (len(keys) * 8 + 96) * MiB + sum(frames) * 25000 if preflight else 0
    temporary = max(frames) * WIDTH ** 2 * 24 + 32 * MiB if preflight else 0
    print(enforce(OUT, growth=growth, temporary=temporary), flush=True)


def make_plan(label, keys):
    folder = confined(ARTIFACTS / 'maintenance/stage-05.6c' / label, ARTIFACTS)
    enforce(folder, growth=MiB)
    folder.mkdir(parents=True, exist_ok=True)

    def argv(operation, selection):
        return [str(PYTHON), '-B', __file__, operation, label, *selection]

    config, plan = folder / 'pipeline.json', folder / 'plan.json'
    store.atomic_json(config, {
        'schema_version': 1, 'preflight_argv': argv('preflight', keys),
        'numeric_gate_argv': argv('verify-numeric', keys), 'verify_argv': argv('verify-render', keys),
        'review_check_argv': argv('review', keys), 'storage_argv': argv('storage', keys),
        'review_directory': str(folder / 'review'),
        'cases': [{'id': key.replace('/', '.'), 'directory': str(case_path(key)),
                   'check_argv': argv('check', [key]), 'render_argv': argv('render', [key]),
                   'timeout_s': 900} for key in keys],
    })
    build(config, plan)
    value = read(plan)
    value['steps'][1:1] = [{'id': 'numeric-' + key.replace('/', '.'), 'phase': 'numeric',
                           'argv': argv('numeric', [key]), 'timeout_s': 420,
                           'case_id': key.replace('/', '.')} for key in keys]
    store.atomic_json(plan, value)
    load_plan(plan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('plan', 'preflight', 'numeric', 'verify-numeric', 'check',
                                              'render', 'verify-render', 'review', 'record-review', 'storage'))
    parser.add_argument('label')
    parser.add_argument('keys', nargs='*')
    parser.add_argument('--front')
    parser.add_argument('--side')
    args = parser.parse_args()
    if not args.label or not args.label[0].isalnum() or not all(char.isalnum() or char in '.-' for char in args.label):
        parser.error('Invalid label')
    keys = args.keys or list(CASES)
    if len(set(keys)) != len(keys) or not set(keys) <= CASES.keys():
        parser.error('Expected unique known cases')
    operation = args.operation
    if operation == 'plan':
        make_plan(args.label, keys)
    elif operation in ('preflight', 'storage'):
        storage_gate(args.label, keys, operation == 'preflight')
    elif operation in ('verify-numeric', 'verify-render'):
        for key in keys:
            if operation == 'verify-numeric':
                numeric_valid(key)
            else:
                assert render_check(key) == 0
        if operation == 'verify-render':
            storage_gate(args.label, keys, False)
    elif operation == 'review':
        path = OUT / 'visual-review.json'
        reviewed = read(path) if path.exists() else {}
        for key in keys:
            if key not in reviewed:
                return 75
            assert all(reviewed[key]['observations'][view].strip() for view in VIEWS)
            assert {name: reviewed[key][name] for name in ('motion', 'views')} == review_identity(key)
    else:
        if len(keys) != 1:
            parser.error('Select one case')
        key, = keys
        out = case_path(key)
        if operation == 'check':
            return render_check(key)
        if operation == 'numeric':
            if (out / 'preview-manifest.json').is_file():
                numeric_valid(key)
                return 0
            if out.exists() and any(out.iterdir()):
                raise RuntimeError(f'Interrupted case needs reconciliation: {out}')
            enforce(out, growth=8 * MiB, temporary=32 * MiB)
            run_native(out, operation, NATIVE, [operation, key])
            numeric_valid(key)
        elif operation == 'render':
            assert render_check(key) == 10
            run_native(out, operation, NATIVE, [operation, key])
            assert render_check(key) == 0
        else:
            if not args.front or not args.side:
                parser.error('Both views need an actual observation')
            path = OUT / 'visual-review.json'
            with store.producer_lease(OUT):
                reviewed = read(path) if path.exists() else {}
                reviewed[key] = {**review_identity(key), 'observations': {'front': args.front, 'side': args.side}}
                store.atomic_json(path, reviewed)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
