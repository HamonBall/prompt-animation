"""First native fixed-support check on both supported rigs."""
from dataclasses import asdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.blender.motion import build_action
from avatar_app.movement_library import contracts as c
from avatar_app.motion import Surface
from blender_movement_root_travel_flight import setup
from test_movement_support_transfers import compile_support
from tools import artifact_store as store
from tools.storage_policy import ARTIFACTS, enforce


def main(rig, *, save=False, cycle=False):
    handle, profile, entry = setup(rig, 'turned-crouched-raised-left')
    assert entry.active_contacts == ('right.sole',)
    move = 'support.acquire_release' if cycle else 'support.transfer'
    params = {'acquire_s': 1.2, 'hold_s': .5, 'release_s': 1.2} if cycle else {}
    motion = compile_support(profile, entry, move, params)
    result = build_action(handle, motion, profile=profile)
    anchors = [set(row['active_foot_anchors']) for row in result['samples']]
    assert anchors[0] == {'right.sole'}
    assert {'right.sole', 'left.sole'} in anchors
    expected = 'right.sole' if cycle else 'left.sole'
    assert anchors[-1] == {expected} and all(anchors)
    assert result['review']['metrics']['contact_error_m'] < .001
    ending = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    assert ending.active_contacts == (expected,)
    assert ending.contact_anchors[0].surface_id == 'floor'
    if save:
        save_case(rig, 'sole-cycle' if cycle else 'sole-transfer', handle, profile, motion, result, params)
        return
    handle.scene.frame_set(handle.scene.frame_end)
    try:
        impossible = compile_support(profile, ending, 'support.transfer',
                                     {'anchor': 'right.sole', 'from_anchor': 'left.sole', 'target': (2, 2, 0)},
                                     (Surface(),))
        build_action(handle, impossible, profile=profile)
    except c.MotionContractError as error:
        assert error.code == 'INVALID_PARAMETER', error.to_dict()
    else:
        raise AssertionError('An unreachable sole target passed')
    print('FIXED_SOLE_TRANSFER_PASSED', rig, result['frames'], result['review']['metrics'], flush=True)


def balance(rig, side, *, save=False):
    free = 'right' if side == 'left' else 'left'
    anchor = side + '.sole'
    handle, profile, entry = setup(rig, 'turned-crouched-raised-' + free)
    assert entry.active_contacts == (anchor,)
    motion = compile_support(profile, entry, 'body.balance', {'anchor': anchor})
    try:
        result = build_action(handle, motion, profile=profile)
    except c.PlanError as error:
        print('GEOMETRIC_BALANCE_FAILED', getattr(error, 'review', None) or str(error), flush=True)
        raise
    rows = result['samples']
    assert all(set(row['active_foot_anchors']) == {anchor} for row in rows)
    settled = [row['geometric_balance'] for row in rows if row['geometric_balance']['settled']]
    assert len(settled) >= 7 and min(row['margin_m'] for row in settled) >= .005
    assert result['review']['metrics']['contact_error_m'] < .001
    controls = [value.control_id for value in entry.measured_controls if value.unit == 'degree'
                and not value.control_id.startswith(side + '.')]
    assert max(abs(row['measured'][key] - rows[0]['measured'][key]) for row in rows for key in controls) < .5
    if save:
        save_case(rig, 'balance-' + side, handle, profile, motion, result, {'anchor': anchor})
        return
    print('GEOMETRIC_BALANCE_PASSED', rig, side, result['frames'],
          min(row['margin_m'] for row in settled), result['review']['metrics'], flush=True)


def save_case(rig, case, handle, profile, motion, result, params):
    from tools.support_evidence import HARNESS, case_path

    out = case_path(rig + '/' + case)
    enforce(out, growth=8 * 1024**2, temporary=32 * 1024**2)
    source = store.input_identity(out)['producer_sha256']
    result['stage_05_6b'] = {'rig': rig, 'case': case, 'parameters': params, 'producer': source,
                            'harness': {path: store.digest(ROOT / path) for path in HARNESS},
                            'surfaces': [asdict(surface) for surface in handle.surfaces]}
    with store.producer_lease(out):
        for name, value in (('profile', profile), ('entry', motion.entry_snapshot), ('executable', motion)):
            store.atomic_json(out / (name + '.json'), c.to_dict(value))
        store.atomic_json(out / 'result.json', result, compact=True)
        store.write_source_identity(out, rig)
        handle.scene.frame_set(1)
        store.save_scene(out / 'preview.blend')
        store.write_manifest(out, handle.scene, metadata=store.entry_metadata('authored:' + case, params, handle.scene),
                             complete=False)
    print('SUPPORT_NUMERIC_PASSED', rig, case, result['frames'], flush=True)


if __name__ == '__main__':
    rig, *options = sys.argv[sys.argv.index('--') + 1:]
    if options and options[0] == '--save':
        _, case = options
        if case in ('balance-left', 'balance-right'):
            balance(rig, case.split('-')[1], save=True)
        else:
            assert case in ('sole-transfer', 'sole-cycle')
            main(rig, save=True, cycle=case == 'sole-cycle')
    elif options:
        balance(rig, options[0])
    else:
        main(rig)
