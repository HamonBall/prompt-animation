"""Run the coordinated evidence pipeline for numerically checked boundaries."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests')]

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import value_error
from avatar_app.movement_library.coordinated import grounded_root_windows
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.root_motion import POSITION
from tools import coordinated_evidence as evidence

SCRIPT = Path(__file__).resolve()
# Case, alternate entry when applicable, and measured frame count.
BOUNDARIES = {
    'demo': {
        'lower-rise-neutral': (None, 58),
        'takeoff-land-push-off-neutral': (None, 126),
        'step-left': (None, 55),
        'lunge-left': (None, 58),
        'low-crawl-left': (None, 169),
        'prepared-seat': (None, 31),
        'prepared-kneel': (None, 58),
        'standing-to-seated': ('turned-crouched', 97),
        'seated-to-back': ('turned-crouched', 98),
        'planted-kneel-left': ('turned-crouched', 202),
    },
    'mixamo': {
        'lower-rise-neutral': (None, 139),
        'takeoff-land-push-off-neutral': (None, 167),
        'step-left': (None, 97),
        'lunge-right': (None, 139),
        'prepared-seat': (None, 79),
        'prepared-kneel': (None, 139),
        'standing-to-seated': ('crouched', 184),
        'seated-to-back': ('crouched', 185),
        'planted-kneel-right': ('neutral', 361),
    },
}


def boundary_cases():
    cases = {}
    for rig, boundary in (('demo', 'minimum'), ('mixamo', 'maximum')):
        for case, (pose, frames) in BOUNDARIES[rig].items():
            baseline = f'{rig}/{case}'
            spec = evidence.CASES[baseline]
            profile_path = evidence.case_path(baseline) / 'profile.json'
            profile = c.loads(c.AvatarProfile, profile_path.read_text(encoding='utf-8'))
            definition = catalog_for_profile(profile).definitions[spec['move']]
            params = dict(spec['parameters'])
            params.update((item.name, getattr(item, boundary)) for item in definition.parameter_specs
                          if item.minimum is not None and item.maximum is not None)
            cases[f'{baseline}-{boundary}'] = {
                **spec, 'pose': pose or spec['pose'], 'max_frames': frames, 'parameters': params,
            }
    return cases


def current_feet_crawl_cases():
    from tools import coordinated_crawl_limit_evidence as limit

    cases = {
        key + '-revised': {**spec, 'max_frames': 93}
        for key, spec in {**evidence.batch_cases(), **boundary_cases()}.items()
        if spec['move'] == 'body.crawl'
    }
    cases[limit.KEY + '-revised'] = {**limit.SPEC, 'max_frames': 141}
    return cases


def verify_takeoff(motion, rows):
    initial = rows[0]['measured']
    soles = {'left.sole', 'right.sole'}
    preparation, recovery = grounded_root_windows(motion, {track.control_id for track in motion.tracks})
    loaded = [row for row in rows if row['time_s'] < preparation.end_s]
    recovering = [row for row in rows if row['time_s'] >= recovery.start_s - 1e-9]
    airborne = [row for row in rows if row['floor_m'] > .10]
    assert airborne and all(not row['active_foot_anchors'] for row in airborne)
    assert all(abs(row['measured']['left.knee.flexion'] - initial['left.knee.flexion']) < .5 for row in airborne)
    for phase, window in ((loaded, preparation), (recovering, recovery)):
        target_z = min(track.curve.end_value[2] for track in motion.tracks
                       if track.control_id == 'pelvis.position'
                       and window.start_s - 1e-9 <= track.interval.start_s
                       and track.interval.end_s <= window.end_s + 1e-9)
        assert phase and all(set(row['active_foot_anchors']) == soles for row in phase)
        assert all(value_error(tuple(row['measured'][POSITION]), tuple(initial[POSITION])) < .001 for row in phase)
        assert abs(min(row['measured']['pelvis.position'][2] for row in phase) - target_z) < .002
        assert max(row['measured']['left.knee.flexion'] for row in phase) > initial['left.knee.flexion'] + 5
    assert value_error(tuple(rows[-1]['measured']['pelvis.position']), tuple(initial['pelvis.position'])) < .002
    assert value_error(tuple(rows[-1]['measured'][POSITION]), tuple(initial[POSITION])) < .001
    assert all(value_error(row['measured']['head.orientation'], initial['head.orientation'], 'quaternion') < .5
               for row in rows)


def make_plan(label, keys):
    folder = evidence.confined(evidence.ARTIFACTS / 'maintenance/stage-05.6c' / label)
    evidence.enforce(folder, growth=evidence.MiB)
    folder.mkdir(parents=True, exist_ok=True)

    def command(operation, selection):
        return [str(evidence.PYTHON), '-B', str(SCRIPT), operation, label, *selection]

    config, plan = folder / 'pipeline.json', folder / 'plan.json'
    evidence.store.atomic_json(config, {
        'schema_version': 1, 'preflight_argv': command('preflight', keys),
        'numeric_gate_argv': command('verify-numeric', keys), 'verify_argv': command('verify-render', keys),
        'review_check_argv': command('review', keys), 'storage_argv': command('storage', keys),
        'review_directory': str(folder / 'review'),
        'cases': [{'id': key.replace('/', '.'), 'directory': str(evidence.case_path(key)),
                   'check_argv': command('check', [key]), 'render_argv': command('render', [key]),
                   'timeout_s': 900} for key in keys],
    })
    evidence.build(config, plan)
    value = evidence.read(plan)
    value['steps'][1:1] = [
        {'id': 'numeric-' + key.replace('/', '.'), 'phase': 'numeric',
         'argv': command('numeric', [key]), 'timeout_s': 420, 'case_id': key.replace('/', '.')}
        for key in keys
    ]
    evidence.store.atomic_json(plan, value)
    evidence.load_plan(plan)


if __name__ == '__main__':
    feet_crawls = current_feet_crawl_cases()
    cases = {**boundary_cases(), **feet_crawls}
    evidence.CASES.clear()
    evidence.CASES.update(cases)
    evidence.NATIVE = SCRIPT
    evidence.HARNESS += (SCRIPT.relative_to(ROOT).as_posix(), 'tools/coordinated_crawl_limit_evidence.py')
    if '--' in sys.argv:
        import blender_coordinated_evidence as native

        phase, key = sys.argv[sys.argv.index('--') + 1:]
        native.check_takeoff = verify_takeoff
        if key == 'mixamo/low-crawl-right-maximum-revised':
            from tools.coordinated_crawl_limit_evidence import make_entry
            native.make_entry = make_entry
        {'numeric': native.bake, 'render': native.render}[phase](key)
    else:
        evidence.make_plan = make_plan
        raise SystemExit(evidence.main())
