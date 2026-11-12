"""Exercise registered coordinated range endpoints on authored entry fixtures."""
from pathlib import Path
import sys

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'src'), str(Path(__file__).resolve().parent)]

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.joints import catalog_for_profile
from blender_coordinated_evidence import CASES, build_action, compile_support, make_entry


def verify_envelope(key, boundary, alternate_pose, lead=None):
    rig, _ = key.split('/')
    spec = CASES[key]
    if alternate_pose:
        spec = {**spec, 'pose': alternate_pose}
    try:
        handle, profile, entry, params = make_entry(rig, spec)
    except c.PlanError as error:
        diagnostic = error.to_dict() if isinstance(error, c.MotionContractError) else str(error)
        print('COORDINATED_ENVELOPE_ENTRY_FAILED', key, boundary, spec['pose'],
              getattr(error, 'review', None) or diagnostic, flush=True)
        raise
    move = spec['move']
    if lead is not None:
        assert move == 'body.crawl'
        params['lead'] = lead
    definition = catalog_for_profile(profile).definitions[move]
    bounds = [param for param in definition.parameter_specs
              if param.minimum is not None and param.maximum is not None]
    for param in bounds:
        for invalid in (param.minimum - .001, param.maximum + .001):
            try:
                compile_support(profile, entry, move, {**params, param.name: invalid}, handle.surfaces)
            except c.MotionContractError as error:
                assert error.code == 'INVALID_PARAMETER', error.to_dict()
            else:
                raise AssertionError(f'{move} accepted out-of-range {param.name}={invalid}')
        params[param.name] = getattr(param, boundary)
    motion = compile_support(profile, entry, move, params, handle.surfaces)
    try:
        result = build_action(handle, motion, profile=profile)
    except c.PlanError as error:
        diagnostic = error.to_dict() if isinstance(error, c.MotionContractError) else str(error)
        print('COORDINATED_ENVELOPE_FAILED', key, boundary, params,
              getattr(error, 'review', None) or diagnostic, flush=True)
        raise
    assert result['review']['passed'] and not result['experimental']
    if move == 'body.takeoff_land':
        samples = result['samples']
        soles = {'left.sole', 'right.sole'}
        assert set(samples[0]['active_foot_anchors']) == set(samples[-1]['active_foot_anchors']) == soles
        assert any(not row['active_foot_anchors'] and row['floor_m'] > .1 for row in samples)
        assert result['review']['metrics']['contact_error_m'] < .001
    print('COORDINATED_ENVELOPE_PASSED', key, boundary, spec['pose'], result['frames'],
          result['review']['metrics'], flush=True)


if __name__ == '__main__':
    key, boundary, pose, *options = sys.argv[sys.argv.index('--') + 1:]
    assert boundary in ('minimum', 'maximum')
    verify_envelope(key, boundary, None if pose == 'same' else pose, *options)
