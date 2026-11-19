"""Storage-v2 numeric, replay and visual evidence for the 05.7b scalar style baseline."""

import argparse
from dataclasses import asdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests')]

from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.evidence_pipeline import build
from tools.root_motion_evidence import PYTHON, VIEWS, WIDTH, check_process, read, run_native, runtime
from tools.storage_policy import ARTIFACTS, MiB, confined, enforce, inventory, temporary_bytes

SCRIPT = Path(__file__).resolve()
OUT = ARTIFACTS / 'stages/05.7b'
LABEL = 'stage-05.7b-first-evidence'
JOB = ARTIFACTS / 'maintenance/jobs' / LABEL
PLAN = ARTIFACTS / 'maintenance/stage-05.7b/first-evidence'
CASES = {
    f'{rig}/{style}-visible-maximum': ('style.' + style, 'neutral' if rig == 'demo' else 'turned-crouched', 121)
    for rig in ('demo', 'mixamo')
    for style in ('fluid', 'robotic', 'heavy', 'playful', 'exaggerated', 'tired')
}

MARKERS = {'numeric': 'STYLE_BUNDLE_PASSED', 'replay': 'STYLE_REPLAY_PASSED', 'render': 'STYLE_RENDER_PASSED'}
HARNESS = (
    'tests/style_evidence.py', 'tests/blender_movement_styles.py', 'src/avatar_app/movement_library/styles.py',
    'tests/blender_movement_root_travel_flight.py', 'tests/blender_movement_hips_knees.py',
    'tests/blender_coordinated_evidence.py', 'tests/blender_movement_coordinated_body_moves.py',
    'tools/render_root_motion.py', 'tools/root_motion_evidence.py',
    'tests/fixtures/movement_fragments/v1/entry-neutral.json',
)


def case_path(key):
    if key not in CASES:
        raise ValueError(f'Unknown style evidence case: {key}')
    return confined(OUT / key)


def harness_identity():
    return {name: store.digest(ROOT / name) for name in HARNESS}


def numeric_valid(key):
    out = case_path(key)
    manifest, _, _ = validate_manifest(out)
    result = read(out / 'result.json')
    stamp = result['stage_05_7b']
    assert manifest['inputs'] == store.input_identity(out)
    assert stamp['key'] == key and stamp['spec'] == list(CASES[key]) and stamp['harness'] == harness_identity()
    assert manifest['entry']['movement_parameters'] == stamp['parameters']
    assert manifest['entry']['entry_fixture'] == stamp['fixture']
    from avatar_app.movement_library import contracts as c
    from hashlib import sha256
    application = c.loads(c.StyledFragment, (out / 'style.json').read_text(encoding='utf-8'))
    source = c.loads(c.MotionFragment, (out / 'source-fragment.json').read_text(encoding='utf-8'))
    assert application.source_sha256 == sha256(c.dumps(source).encode()).hexdigest()
    assert application.fragment == c.loads(c.MotionFragment, (out / 'fragment.json').read_text(encoding='utf-8'))
    assert result['style_records'] == {name: store.digest(out / name)
                                      for name in ('style.json', 'source-fragment.json')}
    assert result['review']['passed'] and not result['experimental']
    assert result['frames'] == len(result['samples']) == len(manifest['expected_frames']) == CASES[key][2]
    if out.parent.name == 'mixamo':
        assert read(out / 'source.json')['sha256'] == store.digest(ROOT / 'Hip Hop Mixamo.fbx')
    else:
        assert read(out / 'source.json') == {'kind': 'procedural-demo-v1'}
    check_process(out, 'numeric', MARKERS['numeric'])
    return result


def replay_valid(key):
    out = case_path(key)
    _, _, motion = validate_manifest(out)
    check_process(out, 'replay', MARKERS['replay'])
    replay = read(out / 'playback.json')
    assert replay['motion_sha256'] == store.digest(motion)
    assert replay['result_sha256'] == store.digest(out / 'result.json')
    assert replay['frames'] == CASES[key][2] and replay['harness'] == harness_identity()
    return replay


def render_check(key):
    out = case_path(key)
    numeric_valid(key)
    manifest, _, _ = validate_manifest(out)
    if not manifest['views'] and not any((out / item).exists() for item in (*VIEWS, 'render.log.gz')):
        return 10
    replay_valid(key)
    check_process(out, 'render', MARKERS['render'])
    assert manifest['complete'] and manifest['visual_evidence']['complete']
    assert set(manifest['views']) == set(VIEWS) and store.files_complete(out, manifest)
    for label, view in manifest['views'].items():
        assert view['sheet_sha256'] == store.digest(out / (label + '-sheet.png'))
    return 0


def review_identity(key):
    assert render_check(key) == 0
    manifest, _, motion = validate_manifest(case_path(key))
    return {'motion': store.digest(motion), 'views': {
        label: [view['media']['sha256'], view['sheet_sha256']] for label, view in manifest['views'].items()}}


def native(operation, key):
    from avatar_app.movement_library import contracts as c
    from blender_coordinated_evidence import restore_surfaces, verify_playback
    from blender_movement_styles import check_family
    from tools.lossless_evidence import encode_view, recover_evidence, retire_pngs
    from tools.render_root_motion import render_view

    out = case_path(key)
    rig = out.parent.name
    if operation == 'numeric':
        style, pose, frames = CASES[key]
        identity = harness_identity()
        producer = store.input_identity(out)['producer_sha256']
        handle, profile, entry, source, application, motion, result = check_family(style, rig, pose, '1', 40.)
        fragment = application.fragment
        assert result['frames'] == frames and identity == harness_identity()
        assert producer == store.input_identity(out)['producer_sha256']
        parameters = {'style_id': style, 'intensity': 1., 'excursion_deg': 40., 'control': 'left.elbow.flexion',
                      'source_sha256': application.source_sha256, 'amplitude_unlocked': application.amplitude_unlocked}
        stamp = {'key': key, 'spec': CASES[key], 'harness': identity, 'parameters': parameters,
                 'fixture': 'authored:' + pose, 'surfaces': [asdict(surface) for surface in handle.surfaces]}
        result['stage_05_7b'] = stamp
        with store.producer_lease(out):
            for name, value in (('profile', profile), ('entry', motion.entry_snapshot),
                                ('fragment', fragment), ('executable', motion), ('style', application), ('source-fragment', source)):
                store.atomic_json(out / (name + '.json'), c.to_dict(value))
            store.write_source_identity(out, rig)
            result['style_records'] = {name: store.digest(out / name)
                                      for name in ('style.json', 'source-fragment.json')}
            store.atomic_json(out / 'result.json', result, compact=True)
            handle.scene.frame_set(1)
            store.save_scene(out / 'preview.blend')
            store.write_manifest(out, handle.scene, metadata=store.entry_metadata(stamp['fixture'], parameters, handle.scene))
    else:
        result = numeric_valid(key)
        manifest, _, motion_path = validate_manifest(out)
        saved_sha = store.digest(motion_path)
        profile = c.loads(c.AvatarProfile, (out / 'profile.json').read_text(encoding='utf-8'))
        handle = store.open_preview(out)
        restore_surfaces(handle, {'stage_05_6c': result['stage_05_7b']})
        with store.producer_lease(out):
            if operation == 'replay':
                motion = c.loads(c.ExecutableMotion, (out / 'executable.json').read_text(encoding='utf-8'))
                bounds, maxima = verify_playback(handle, profile, motion, result)
                store.atomic_json(out / 'playback.json', {
                    'frames': result['frames'], 'bounds': bounds, 'maxima': maxima,
                    'motion_sha256': saved_sha, 'result_sha256': store.digest(out / 'result.json'),
                    'harness': harness_identity(),
                })
            else:
                replay = replay_valid(key)
                assert not manifest['views']
                recover_evidence(out)
                views, retirement = {}, []
                for label in VIEWS:
                    views[label] = render_view(handle, profile, out, label, replay['bounds'])
                    media, plan = encode_view(out, label, manifest['expected_frames'], fps=manifest['fps'],
                                              fps_base=manifest['fps_base'])
                    views[label].update(media=media, sheet_sha256=store.digest(out / (label + '-sheet.png')))
                    retirement.append(plan)
                    store.write_manifest(out, handle.scene, views=views)
                store.write_manifest(out, handle.scene, views=views, complete=True)
                retire_pngs(out, retirement)
            assert saved_sha == store.digest(motion_path)
    print(MARKERS[operation], rig, out.name, result['frames'], flush=True)


def run_case(operation, key):
    out = case_path(key)
    if operation == 'numeric':
        if (out / 'preview-manifest.json').exists():
            numeric_valid(key)
            return
        if out.exists() and any(out.iterdir()):
            raise RuntimeError(f'Interrupted numeric case needs reconciliation: {out}')
        enforce(out, growth=32 * MiB, temporary=64 * MiB)
    elif operation == 'replay':
        numeric_valid(key)
        if (out / 'playback.json').exists():
            replay_valid(key)
            return
        if (out / 'replay.log.gz').exists():
            raise RuntimeError(f'Interrupted replay needs reconciliation: {out}')
    else:
        assert render_check(key) == 10
        run_case('replay', key)
    run_native(out, operation, SCRIPT, ['native', operation, key])
    {'numeric': numeric_valid, 'replay': replay_valid, 'render': render_check}[operation](key)


def budget(preflight):
    active = [lease for lease in inventory()['leases'] if lease['active']]
    assert all(Path(lease['path']) == JOB / '.artifact-writer.lock' for lease in active)
    assert temporary_bytes(ARTIFACTS) == 0
    # The shared renderer bounds the active, uncompressed view separately.
    frame_max = max(case[2] for case in CASES.values())
    temporary = frame_max * WIDTH ** 2 * 24 + 32 * MiB if preflight else 0
    print(enforce(OUT, growth=192 * MiB if preflight else 0, temporary=temporary), flush=True)


def make_plan():
    enforce(PLAN, growth=MiB)
    plan_file, config_file = PLAN / 'plan.json', PLAN / 'pipeline.json'

    def argv(operation, *args):
        return [str(PYTHON), '-B', str(SCRIPT), operation, *args]

    with store.producer_lease(PLAN):
        store.atomic_json(config_file, {
            'schema_version': 1, 'preflight_argv': argv('preflight'), 'numeric_gate_argv': argv('numeric-all'),
            'verify_argv': argv('verify'), 'review_check_argv': argv('review'), 'storage_argv': argv('storage'),
            'review_directory': str(PLAN / 'review'),
            'cases': [{'id': key.replace('/', '.'), 'directory': str(case_path(key)),
                       'check_argv': argv('check', key), 'render_argv': argv('render', key), 'timeout_s': 900}
                      for key in CASES],
        })
        build(config_file, plan_file)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('route-check', 'plan', 'preflight', 'storage', 'numeric-all', 'verify',
                                              'numeric', 'replay', 'render', 'check', 'review', 'record-review', 'native'))
    parser.add_argument('args', nargs='*')
    args = parser.parse_args()
    operation = args.operation
    if operation == 'native':
        native(*args.args)
    elif operation in ('numeric', 'replay', 'render'):
        run_case(operation, *args.args)
    elif operation == 'check':
        return render_check(*args.args)
    elif operation == 'route-check':
        for key in CASES:
            print(key, case_path(key), CASES[key])
        try:
            case_path('../05.6c')
        except ValueError:
            pass
        else:
            raise AssertionError('Routing accepted an unknown case')
    elif operation == 'plan':
        make_plan()
    elif operation in ('preflight', 'storage'):
        budget(operation == 'preflight')
    elif operation == 'numeric-all':
        for key in CASES:
            run_case('numeric', key)
            run_case('replay', key)
    elif operation == 'record-review':
        key, front, side = args.args
        if not front.strip() or not side.strip():
            parser.error('Supply actual observations from both full-motion views')
        proof = review_identity(key)
        path = OUT / 'visual-review.json'
        with store.producer_lease(OUT):
            reviews = read(path) if path.exists() else {}
            reviews[key] = {**proof, 'observations': {'front': front, 'side': side}}
            store.atomic_json(path, reviews)
    else:
        for key in CASES:
            assert render_check(key) == 0
        if operation == 'review':
            path = OUT / 'visual-review.json'
            reviews = read(path) if path.exists() else {}
            for key in CASES:
                if key not in reviews:
                    return 75
                record = reviews[key]
                assert all(record['observations'][view].strip() for view in VIEWS)
                assert {name: record[name] for name in ('motion', 'views')} == review_identity(key)


if __name__ == '__main__':
    if '--' in sys.argv:
        sys.argv[1:] = sys.argv[sys.argv.index('--') + 1:]
        main()
    else:
        raise SystemExit(main())
