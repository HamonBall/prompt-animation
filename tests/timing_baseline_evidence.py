"""Saved-motion evidence for remaining Stage 05.7a baseline and repeat cases."""

import argparse
from dataclasses import asdict, replace
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests')]

from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.evidence_pipeline import build
from tools.root_motion_evidence import PYTHON, VIEWS, WIDTH, check_process, read, run_native
from tools.storage_policy import ARTIFACTS, MiB, confined, enforce, inventory, temporary_bytes

OUT = ARTIFACTS / 'stages/05.7a'
JOB = ARTIFACTS / 'maintenance/jobs/stage-05.7a-baseline-evidence'
PLAN = ARTIFACTS / 'maintenance/stage-05.7a/baseline-evidence'
SCRIPT = Path(__file__).resolve()
HARNESS = (
    'tests/timing_baseline_evidence.py', 'tests/blender_movement_patterns.py',
    'tests/blender_timing_operators.py', 'tests/blender_movement_root_travel_flight.py',
    'tests/blender_movement_hips_knees.py', 'tests/blender_coordinated_evidence.py',
    'tests/blender_movement_coordinated_body_moves.py', 'tools/render_root_motion.py',
    'tools/root_motion_evidence.py', 'tests/fixtures/movement_fragments/v1/entry-neutral.json',
)
MARKERS = dict(numeric='TIMING_BASELINE_SAVED', render='TIMING_BASELINE_RENDERED')
POSES = {'demo': 'neutral', 'mixamo': 'turned-crouched'}
CASES = {
    f'{rig}/{name}': (rig, pose, operation, parameter, maximum)
    for rig, pose in POSES.items()
    for name, operation, parameter, maximum in (
        ('transition-hold', 'transition-hold', None, 43),
        ('repeat-one', 'repeat', 1, 79),
        ('repeat-two', 'repeat', 2, 157),
        ('repeat-four', 'repeat', 4, 313),
        ('phase-offset', 'phase', .5 if rig == 'demo' else -.5, 46),
        ('sway', 'torso', {'mode': 'sway', 'follow_through': None}, 97),
        ('undulation', 'torso', {'mode': 'undulation', 'follow_through': None}, 83),
        ('undulation-follow-through', 'torso', {'mode': 'undulation',
                                              'follow_through': 'right' if rig == 'demo' else 'left'}, 111),
        ('strokes-synchronized', 'stroke', 'synchronized', 115),
        ('mirror', 'operator', 'mirror', 31),
        ('synchronize', 'operator', 'synchronize', 121),
        ('overlap', 'operator', 'overlap', 121),
        ('alternate', 'operator', 'alternate', 211),
    )
}


def case_path(key):
    if key not in CASES:
        raise ValueError(f'Unknown baseline timing case: {key}')
    return confined(OUT / key, OUT)


def identity():
    return {name: store.digest(ROOT / name) for name in HARNESS}


def numeric_valid(key):
    out = case_path(key)
    check_process(out, 'numeric', MARKERS['numeric'])
    manifest, _, _ = validate_manifest(out)
    result = read(out / 'result.json')
    stamp = result['stage_05_7a_baseline']
    assert stamp['key'] == key and stamp['case'] == list(CASES[key]) and stamp['harness'] == identity()
    assert manifest['inputs'] == store.input_identity(out)
    assert manifest['entry']['movement_parameters'] == stamp['parameters']
    assert manifest['entry']['entry_fixture'] == stamp['fixture']
    assert result['review']['passed'] and not result['experimental']
    assert 0 < result['frames'] == len(result['samples']) == len(manifest['expected_frames']) <= CASES[key][-1]
    source = read(out / 'source.json')
    if out.parent.name == 'mixamo':
        assert source['kind'] == 'imported' and source['sha256'] == store.digest(ROOT / 'Hip Hop Mixamo.fbx')
    else:
        assert source == {'kind': 'procedural-demo-v1'}
    return result


def rendered(key):
    out = case_path(key)
    result = numeric_valid(key)
    manifest, _, motion = validate_manifest(out)
    if not manifest['views'] and not any((out / item).exists() for item in (*VIEWS, 'render.log.gz', 'playback.json')):
        return 10
    check_process(out, 'render', MARKERS['render'])
    replay = read(out / 'playback.json')
    assert replay['frames'] == result['frames'] and replay['harness'] == identity()
    assert replay['motion_sha256'] == store.digest(motion) and replay['result_sha256'] == store.digest(out / 'result.json')
    assert manifest['complete'] and manifest['visual_evidence']['complete']
    assert set(manifest['views']) == set(VIEWS) and store.files_complete(out, manifest)
    assert all(view['sheet_sha256'] == store.digest(out / f'{label}-sheet.png') for label, view in manifest['views'].items())
    return 0


def review_identity(key):
    assert rendered(key) == 0
    manifest, _, motion = validate_manifest(case_path(key))
    return {'motion': store.digest(motion), 'views': {
        label: [view['media']['sha256'], view['sheet_sha256']] for label, view in manifest['views'].items()}}


def capture(key):
    from avatar_app.blender.motion import build_action
    from avatar_app.movement_library.compiler import build_fragment, instantiate_movement, prepare_fragment
    from avatar_app.movement_library.joints import catalog_for_profile
    from avatar_app.movement_library.patterns import (hold_fragment, phase_offset_fragments, repeat_fragment,
        torso_pattern, transition_fragment)
    from blender_movement_patterns import check_stroke
    from blender_movement_root_travel_flight import setup
    from blender_timing_operators import check_operator

    rig, pose, operation, argument, _ = CASES[key]
    if operation == 'stroke':
        parameters = {'mode': argument, 'count': 1, 'duration_s': 1.2, 'hold_s': .1, 'amplitude_m': .04}
        return (*check_stroke(rig, argument), parameters)
    if operation == 'operator':
        return (*check_operator(argument, rig, pose), {'operation': argument})

    handle, profile, entry = setup(rig, pose)
    values = {value.control_id: value for value in entry.measured_controls}
    kwargs = dict(entry=entry, profile=profile)
    if operation == 'transition-hold':
        parameters = {'delta_deg': 5., 'duration_s': 1., 'hold_s': .4}
        start = values['head.yaw']
        target = replace(start, value=start.value + parameters['delta_deg'])
        transition = transition_fragment((target,), parameters['duration_s'], instance_id='baseline.transition', **kwargs)
        fragment = hold_fragment(transition, parameters['hold_s'], **kwargs)
    elif operation == 'phase':
        parameters = {'phase_cycles': argument, 'duration_s': 1., 'delta_deg': 5.}
        arms = []
        for side in ('left', 'right'):
            control = values[f'{side}.elbow.flexion']
            target = replace(control, value=control.value + parameters['delta_deg'])
            arms.append(transition_fragment((target,), 1., instance_id=f'baseline.phase.{side}', **kwargs))
        fragment = phase_offset_fragments(*arms, argument, fragment_id='baseline.phase', **kwargs)
    elif operation == 'repeat':
        parameters = {'count': argument, 'depth_m': .06 if rig == 'demo' else .10}
        catalog = catalog_for_profile(profile)
        instance = instantiate_movement('body.lower_rise', {'depth_m': parameters['depth_m']},
                                        instance_id='baseline.lower-rise', entry_state=entry, profile=profile, catalog=catalog)
        lowered = build_fragment(instance, entry, profile, handle.surfaces, catalog)
        fragment = repeat_fragment(lowered, argument, **kwargs)
    else:
        parameters = {**argument, 'angle': 5., 'count': 1}
        fragment = torso_pattern(argument['mode'], {'angle': 5.}, 1, fragment_id='baseline.torso',
                                 surfaces=handle.surfaces, follow_through=argument['follow_through'], **kwargs)

    motion = prepare_fragment(fragment, entry, profile)
    result = build_action(handle, motion, profile=profile)
    rows = result['samples']
    assert result['review']['passed'] and not result['experimental']
    assert len(rows) == math.ceil(motion.duration_s * motion.fps) + 1 and rows[-1]['time_s'] == motion.duration_s
    assert all(row['active_foot_anchors'].keys() == set(entry.active_contacts) for row in rows)
    if operation == 'transition-hold':
        assert max(abs(row['measured']['head.yaw'] - target.value) for row in rows[30:]) < .05
    if operation == 'phase':
        delayed = 'right' if argument > 0 else 'left'
        id = f'{delayed}.elbow.flexion'
        assert all(abs(row['measured'][id] - values[id].value) < .05 for row in rows[:16])
    return handle, profile, fragment, motion, result, parameters


def native(operation, key):
    from avatar_app.movement_library import contracts as c
    from blender_coordinated_evidence import restore_surfaces, verify_playback
    from tools.lossless_evidence import encode_view, recover_evidence, retire_pngs
    from tools.render_root_motion import render_view

    out = case_path(key)
    if operation == 'numeric':
        harness = identity()
        producer = store.input_identity(out)['producer_sha256']
        handle, profile, fragment, motion, result, parameters = capture(key)
        assert result['frames'] <= CASES[key][-1] and harness == identity()
        assert producer == store.input_identity(out)['producer_sha256']
        rig, pose, _, _, _ = CASES[key]
        fixture = 'authored:entry-neutral.json' if pose == 'neutral' else 'authored:' + pose
        result['stage_05_7a_baseline'] = {'key': key, 'case': CASES[key], 'harness': harness,
            'fixture': fixture, 'parameters': parameters, 'surfaces': [asdict(surface) for surface in handle.surfaces]}
        with store.producer_lease(out):
            for name, value in (('profile', profile), ('entry', motion.entry_snapshot),
                                ('fragment', fragment), ('executable', motion)):
                store.atomic_json(out / f'{name}.json', c.to_dict(value))
            store.write_source_identity(out, rig)
            store.atomic_json(out / 'result.json', result, compact=True)
            handle.scene.frame_set(1)
            store.save_scene(out / 'preview.blend')
            store.write_manifest(out, handle.scene, metadata=store.entry_metadata(fixture, parameters, handle.scene))
    else:
        result = numeric_valid(key)
        manifest, _, motion_path = validate_manifest(out)
        assert not manifest['views']
        motion_sha = store.digest(motion_path)
        handle = store.open_preview(out)
        restore_surfaces(handle, {'stage_05_6c': result['stage_05_7a_baseline']})
        profile = c.loads(c.AvatarProfile, (out / 'profile.json').read_text(encoding='utf-8'))
        motion = c.loads(c.ExecutableMotion, (out / 'executable.json').read_text(encoding='utf-8'))
        with store.producer_lease(out):
            recover_evidence(out)
            bounds, maxima = verify_playback(handle, profile, motion, result)
            store.atomic_json(out / 'playback.json', {'frames': result['frames'], 'maxima': maxima,
                'motion_sha256': motion_sha, 'result_sha256': store.digest(out / 'result.json'), 'harness': identity()})
            views, retirement = {}, []
            for label in VIEWS:
                views[label] = render_view(handle, profile, out, label, bounds)
                media, plan = encode_view(out, label, manifest['expected_frames'], fps=manifest['fps'], fps_base=manifest['fps_base'])
                views[label].update(media=media, sheet_sha256=store.digest(out / (label + '-sheet.png')))
                retirement.append(plan)
                store.write_manifest(out, handle.scene, views=views)
            store.write_manifest(out, handle.scene, views=views, complete=True)
            retire_pngs(out, retirement)
            assert motion_sha == store.digest(motion_path)
    print(MARKERS[operation], out.parent.name, out.name, result['frames'], flush=True)


def run_case(operation, key):
    out = case_path(key)
    if operation == 'numeric':
        if (out / 'preview-manifest.json').is_file():
            numeric_valid(key)
            return
        if out.exists() and any(out.iterdir()):
            raise RuntimeError(f'Interrupted baseline case needs reconciliation: {out}')
        enforce(out, growth=32 * MiB, temporary=64 * MiB)
    else:
        assert rendered(key) == 10
    run_native(out, operation, SCRIPT, ['native', operation, key])
    if operation == 'numeric':
        numeric_valid(key)
    else:
        assert rendered(key) == 0


def budget(keys, preflight):
    leases = [lease for lease in inventory()['leases'] if lease['active']]
    assert all(Path(lease['path']) == JOB / '.artifact-writer.lock' for lease in leases)
    assert temporary_bytes(ARTIFACTS) == 0
    frames = [CASES[key][-1] for key in keys]
    growth = sum(frames) * 45000 + 32 * MiB if preflight else 0
    temporary = max(frames) * WIDTH ** 2 * 24 + 32 * MiB if preflight else 0
    print(enforce(OUT, growth=growth, temporary=temporary), flush=True)


def make_plan(keys):
    enforce(PLAN, growth=MiB)
    plan = PLAN / 'plan.json'
    config = PLAN / 'pipeline.json'

    def argv(operation, *selection):
        return [str(PYTHON), '-B', str(SCRIPT), operation, *selection]

    with store.producer_lease(PLAN):
        store.atomic_json(config, {'schema_version': 1, 'preflight_argv': argv('preflight', *keys),
            'numeric_gate_argv': argv('numeric-all', *keys), 'verify_argv': argv('verify', *keys),
            'review_check_argv': argv('review', *keys), 'storage_argv': argv('storage', *keys),
            'review_directory': str(PLAN / 'review'),
            'cases': [{'id': key.replace('/', '.'), 'directory': str(case_path(key)),
                       'check_argv': argv('check', key), 'render_argv': argv('render', key), 'timeout_s': 900}
                      for key in keys],
        })
        build(config, plan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('routes', 'native', 'numeric', 'render', 'check', 'plan', 'preflight',
                                              'numeric-all', 'verify', 'review', 'storage', 'record-review'))
    parser.add_argument('args', nargs='*')
    args = parser.parse_args()
    operation = args.operation
    if operation == 'native':
        native(*args.args)
        return 0
    reviews_path = OUT / 'visual-review.json'
    if operation == 'record-review':
        key, front, side = args.args
        if not front.strip() or not side.strip():
            parser.error('Supply actual observations for both views')
        proof = review_identity(key)
        with store.producer_lease(OUT):
            reviews = read(reviews_path) if reviews_path.exists() else {}
            reviews[key] = {**proof, 'observations': {'front': front, 'side': side}}
            store.atomic_json(reviews_path, reviews)
        return 0
    keys = args.args or tuple(CASES)
    if len(set(keys)) != len(keys) or not set(keys) <= CASES.keys():
        parser.error('Select unique known cases')
    if operation == 'routes':
        for key in keys:
            print(key, case_path(key), CASES[key])
    elif operation in ('numeric', 'render', 'check'):
        key, = keys
        if operation == 'check':
            return rendered(key)
        run_case(operation, key)
    elif operation == 'plan':
        make_plan(keys)
    elif operation in ('preflight', 'storage'):
        budget(keys, operation == 'preflight')
    elif operation == 'numeric-all':
        for key in keys:
            run_case('numeric', key)
    else:
        for key in keys:
            assert rendered(key) == 0
        if operation == 'review':
            reviews = read(reviews_path) if reviews_path.exists() else {}
            for key in keys:
                if key not in reviews:
                    return 75
                record = reviews[key]
                assert all(record['observations'][view].strip() for view in VIEWS)
                assert {field: record[field] for field in ('motion', 'views')} == review_identity(key)
    return 0


if __name__ == '__main__':
    if '--' in sys.argv:
        sys.argv[1:] = sys.argv[sys.argv.index('--') + 1:]
        main()
    else:
        raise SystemExit(main())
