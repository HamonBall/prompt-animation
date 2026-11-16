"""Native case checks for the timing operators that pair or reflect fragments."""

from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests')]

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment, instantiate_movement, prepare_fragment
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.patterns import (
    alternate_fragments, mirror_fragment, overlap_fragments, synchronize_fragments, transition_fragment,
)

OPERATORS = ('mirror', 'alternate', 'synchronize', 'overlap')
ENTRIES = {'demo': 'neutral', 'mixamo': 'turned-crouched'}
POSES = ('neutral', 'turned-crouched')


def case_parameters(operation, rig, pose=None):
    if operation not in OPERATORS or rig not in ENTRIES or pose is not None and pose not in POSES:
        raise ValueError('Expected a known timing operator, rig and entry pose')
    return ENTRIES[rig] if pose is None else pose


def check_operator(operation, rig, pose=None):
    from avatar_app.blender.motion import build_action
    from blender_movement_root_travel_flight import setup

    pose = case_parameters(operation, rig, pose)
    handle, profile, entry = setup(rig, pose)
    values = {control.control_id: control for control in entry.measured_controls}
    kwargs = dict(fragment_id=f'timing.{operation}.native', entry=entry, profile=profile)
    if operation == 'mirror':
        control = values['head.yaw']
        target = replace(control, value=control.value + 8)
        source = transition_fragment((target,), 1., instance_id='mirror.source', entry=entry, profile=profile)
        if abs(2 * control.value) > 1e-5:
            try:
                mirror_fragment(source, **kwargs)
            except c.MotionContractError as error:
                assert error.code == 'ENTRY_MISMATCH', error.to_dict()
            else:
                raise AssertionError('Mirrored explicit start jumped from an asymmetric entry')
            initial, = source.tracks
            source = replace(source, tracks=(replace(initial, start_source='measured_entry',
                                                     curve=replace(initial.curve, start_value=None)),))
        fragment = mirror_fragment(source, **kwargs)
        assert tuple(event.anchor_id for event in fragment.contact_events) == tuple(
            'right.sole' if event.anchor_id == 'left.sole' else 'left.sole' for event in source.contact_events
        )
        checks = [('head.yaw', 0., control.value), ('head.yaw', fragment.duration_s, -target.value)]
    else:
        catalog = catalog_for_profile(profile)
        arms, targets = {}, {}
        for side, duration in (('left', 1.5), ('right', 2.)):
            control_id = side + '.elbow.flexion'
            targets[side] = values[control_id].value + 5.
            instance = instantiate_movement('elbow.flex', {
                'side': side, 'angle': targets[side], 'duration_s': duration, 'hold_s': 0.,
            }, instance_id=f'timing.elbow.{side}', profile=profile, entry_state=entry, catalog=catalog)
            arms[side] = build_fragment(instance, entry, profile, handle.surfaces, catalog)

        left, right = arms['left'], arms['right']
        if operation == 'alternate':
            fragment = alternate_fragments(left, right, 1, **kwargs)
            left_arrival, right_arrival = 1.5, left.duration_s + 2.
            assert fragment.duration_s == left.duration_s + right.duration_s
        elif operation == 'synchronize':
            fragment = synchronize_fragments(left, 'arrival', right, 'arrival', **kwargs)
            left_arrival = right_arrival = 2.
        else:
            fragment = overlap_fragments(left, right, **kwargs)
            left_arrival, right_arrival = 1.5, 2.
        checks = [('left.elbow.flexion', left_arrival, targets['left']),
                  ('right.elbow.flexion', right_arrival, targets['right']),
                  ('left.elbow.flexion', fragment.duration_s, values['left.elbow.flexion'].value),
                  ('right.elbow.flexion', fragment.duration_s, values['right.elbow.flexion'].value)]
        if operation == 'alternate':
            checks.append(('right.elbow.flexion', left_arrival, values['right.elbow.flexion'].value))
            checks.append(('left.elbow.flexion', right_arrival, values['left.elbow.flexion'].value))
        if operation == 'synchronize':
            checks.append(('left.elbow.flexion', .5, values['left.elbow.flexion'].value))

    motion = prepare_fragment(fragment, entry, profile)
    result = build_action(handle, motion, profile=profile)
    assert result['review']['passed'] and not result['experimental']
    rows = result['samples']
    assert all(row['active_foot_anchors'].keys() == set(entry.active_contacts) for row in rows)
    assert abs(rows[-1]['time_s'] - fragment.duration_s) < 1e-9
    errors = [abs(rows[round(time * motion.fps)]['measured'][control] - target)
              for control, time, target in checks]
    assert max(errors) < .05
    print(f'TIMING_OPERATOR_PASSED {rig} {operation} {pose} frames={len(rows)} '
          f'max_angle_error={max(errors):.7f}', flush=True)
    return handle, profile, fragment, motion, result


if __name__ == '__main__':
    if '--' in sys.argv:
        check_operator(*sys.argv[sys.argv.index('--') + 1:])
    else:
        for operation in OPERATORS:
            for rig in ENTRIES:
                for pose in POSES:
                    print(rig, operation, case_parameters(operation, rig, pose))
        try:
            case_parameters('unknown', 'demo')
        except ValueError:
            pass
        else:
            raise AssertionError('Case router accepted an unknown operator')
