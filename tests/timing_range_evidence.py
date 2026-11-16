"""Stage 05.7a range cases using the validated timing evidence runner."""

from dataclasses import replace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import timing_baseline_evidence as evidence


def build_cases():
    cases = {}
    for rig in ('demo', 'mixamo'):
        pose = 'turned-crouched' if rig == 'demo' else 'crouched'
        for bound, n, lead, distance, clearance, phase, frames in (
            ('min', 1, 'left', .06, .04, .7, 55), ('max', 4, 'right', .16, .09, 1.4, 385),
        ):
            cases[f'{rig}/range-steps-{bound}'] = (rig, pose, 'steps', {
                'count': n, 'lead': lead, 'distance_m': distance, 'clearance_m': clearance, 'phase_s': phase,
            }, frames)
        for bound, amplitude, duration, hold in (('min', 0., 1., 0.), ('max', .16, 3., 1.)):
            for mode in ('synchronized', 'alternating'):
                frames = (91 if bound == 'min' else 331) if mode == 'synchronized' else (136 if bound == 'min' else 496)
                cases[f'{rig}/range-strokes-{mode}-{bound}'] = (rig, pose, 'stroke', {
                    'mode': mode, 'amplitude_m': amplitude, 'duration_s': duration, 'hold_s': hold,
                }, frames)
        for bound, angle, duration, hold in (('min', -20., .8, 0.), ('max', 20., 3., 1.)):
            for mode in ('sway', 'undulation'):
                frames = (73 if bound == 'min' else 331) if mode == 'sway' else (121 if bound == 'min' else 337)
                side = ('both' if bound == 'max' else None) if mode == 'undulation' else None
                cases[f'{rig}/range-{mode}-{bound}'] = (rig, pose, 'torso', {
                    'mode': mode, 'angle': angle, 'duration_s': duration, 'hold_s': hold, 'follow_through': side,
                }, frames)
        for bound, offset in (('min', -1.), ('max', 1.)):
            cases[f'{rig}/range-phase-{bound}'] = (rig, pose, 'phase', {'phase_cycles': offset}, 61)
        for bound, transition, hold, angle in (('short', .4, .1, 2.), ('long', 3., 1., 10.)):
            cases[f'{rig}/range-transition-hold-{bound}'] = (rig, pose, 'transition-hold', {
                'duration_s': transition, 'hold_s': hold, 'delta_deg': angle,
            }, round((transition + hold) * 30) + 1)
        cases[f'{rig}/range-undulation-follow-through-current'] = (rig, evidence.POSES[rig], 'torso', {
            'mode': 'undulation', 'angle': 5., 'duration_s': 1., 'hold_s': .1,
            'follow_through': 'right' if rig == 'demo' else 'left',
        }, 111)
    # The bridge may retain one additional capped sample after floating-point
    # duration arithmetic. Reserve it without changing the sampled duration.
    return {key: (*case[:-1], case[-1] + 1) for key, case in cases.items()}


CASES = build_cases()


def capture(key):
    from math import dist
    from avatar_app.blender.motion import build_action
    from avatar_app.movement_library.compiler import prepare_fragment, value_error
    from avatar_app.movement_library.patterns import (hold_fragment, phase_offset_fragments, step_pattern,
        stroke_pattern, torso_pattern, transition_fragment)
    from blender_movement_root_travel_flight import setup

    rig, pose, operation, parameters, _ = CASES[key]
    handle, profile, entry = setup(rig, pose)
    kwargs = dict(entry=entry, profile=profile)
    common = dict(**kwargs, fragment_id='range.' + key.split('/')[1], surfaces=handle.surfaces)
    measured = {value.control_id: value for value in entry.measured_controls}
    if operation == 'steps':
        lead, count = parameters['lead'], parameters['count']
        tuning = {name: parameters[name] for name in ('distance_m', 'clearance_m', 'phase_s')}
        fragment = step_pattern(lead, tuning, count, **common)
    elif operation == 'stroke':
        tuning = {name: parameters[name] for name in ('amplitude_m', 'duration_s', 'hold_s')}
        fragment = stroke_pattern(parameters['mode'], tuning, 1, **common)
    elif operation == 'torso':
        tuning = {name: parameters[name] for name in ('angle', 'duration_s', 'hold_s')}
        fragment = torso_pattern(parameters['mode'], tuning, 1, follow_through=parameters['follow_through'], **common)
    elif operation == 'phase':
        arms = []
        for side in ('left', 'right'):
            start = measured[f'{side}.elbow.flexion']
            arms.append(transition_fragment((replace(start, value=start.value + 5.),), 1.,
                                            instance_id=f'range.phase.{side}', **kwargs))
        fragment = phase_offset_fragments(*arms, parameters['phase_cycles'], fragment_id=common['fragment_id'], **kwargs)
    else:
        start = measured['head.yaw']
        target = replace(start, value=start.value + parameters['delta_deg'])
        transition = transition_fragment((target,), parameters['duration_s'], instance_id='range.transition', **kwargs)
        fragment = hold_fragment(transition, parameters['hold_s'], **kwargs)

    motion = prepare_fragment(fragment, entry, profile)
    result = build_action(handle, motion, profile=profile)
    rows = result['samples']
    assert result['review']['passed'] and not result['experimental']
    assert rows[-1]['time_s'] == motion.duration_s
    if operation == 'steps':
        assert all(row['active_foot_anchors'] for row in rows)
        assert rows[0]['active_foot_anchors'].keys() == rows[-1]['active_foot_anchors'].keys() == set(entry.active_contacts)
        pelvis = 'pelvis.position'
        displacement = dist(rows[0]['measured'][pelvis], rows[-1]['measured'][pelvis])
        assert abs(displacement - parameters['count'] * parameters['distance_m'] * .5) < .002
    else:
        assert all(row['active_foot_anchors'].keys() == set(entry.active_contacts) for row in rows)
    if operation == 'stroke':
        for side in ('left', 'right'):
            id = f'{side}.hand.position'
            start = rows[0]['measured'][id]
            assert max(dist(row['measured'][id], start) for row in rows) > .04
            assert dist(rows[-1]['measured'][id], start) < .002
    if operation == 'torso':
        id = 'torso.roll' if parameters['mode'] == 'sway' else 'torso.pitch'
        assert max(abs(row['measured'][id] - rows[0]['measured'][id]) for row in rows) > 3.
        assert abs(rows[-1]['measured'][id] - rows[0]['measured'][id]) < .05
    if operation == 'phase':
        delayed = 'right' if parameters['phase_cycles'] > 0 else 'left'
        id = f'{delayed}.elbow.flexion'
        assert all(abs(row['measured'][id] - measured[id].value) < .05 for row in rows[:31])
        assert abs(rows[-1]['measured'][id] - measured[id].value - 5.) < .05
    if operation == 'transition-hold':
        arrival = round(parameters['duration_s'] * motion.fps)
        assert max(abs(row['measured']['head.yaw'] - target.value) for row in rows[arrival:]) < .05
    if operation != 'transition-hold':
        head = rows[0]['measured']['head.orientation']
        assert max(value_error(row['measured']['head.orientation'], head, 'quaternion') for row in rows) < .5
    return handle, profile, fragment, motion, result, parameters


def configure():
    # A dedicated process supplies range cases to the same strict writer and
    # validator. Reviewed baseline records keep their original harness identity.
    evidence.CASES = CASES
    evidence.SCRIPT = Path(__file__).resolve()
    evidence.HARNESS = (*evidence.HARNESS, 'tests/timing_range_evidence.py')
    evidence.JOB = evidence.ARTIFACTS / 'maintenance/jobs/stage-05.7a-range-evidence'
    evidence.PLAN = evidence.ARTIFACTS / 'maintenance/stage-05.7a/range-evidence'
    evidence.capture = capture


def main():
    configure()
    return evidence.main()


if __name__ == '__main__':
    if '--' in sys.argv:
        sys.argv[1:] = sys.argv[sys.argv.index('--') + 1:]
        if sys.argv[1] == 'pilot':
            key, = sys.argv[2:]
            result = capture(key)[4]
            assert result['frames'] <= CASES[key][-1]
            print('TIMING_RANGE_PASSED', key, result['frames'], result['review']['metrics'], flush=True)
        else:
            main()
    else:
        raise SystemExit(main())
