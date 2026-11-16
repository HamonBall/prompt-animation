"""Exercise a returning repeat on a live rig without writing artifacts."""

from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.blender.motion import build_action, build_action_frames
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import (
    build_fragment, instantiate_movement, prepare_fragment, value_error,
)
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.patterns import (
    hold_fragment, phase_offset_fragments, repeat_fragment, step_pattern, stroke_pattern, torso_pattern,
    transition_fragment, verify_translation_loop,
)
from avatar_app.movement_library.spatial import inverse, rotate
from blender_movement_root_travel_flight import setup
from tools.preview_movement import capture_entry


def check_repeat(rig):
    pose, depth = {'demo': ('neutral', .06), 'mixamo': ('turned-crouched', .10)}[rig]
    handle, profile, entry = setup(rig, pose)
    catalog = catalog_for_profile(profile)
    instance = instantiate_movement('body.lower_rise', {'depth_m': depth}, instance_id='repeat.pilot',
                                    profile=profile, entry_state=entry, catalog=catalog)
    fragment = build_fragment(instance, entry, profile, handle.surfaces, catalog)
    repeated = repeat_fragment(fragment, 2, entry=entry, profile=profile)
    motion = prepare_fragment(repeated, entry, profile)

    rig_matrix = handle.rig.matrix_world.copy()
    frame_range = (handle.scene.frame_start, handle.scene.frame_end, handle.scene.frame_current)
    animation = handle.rig.animation_data
    action = animation.action if animation else None
    with_cancel = build_action_frames(handle, motion, profile=profile)
    try:
        next(with_cancel)
    finally:
        with_cancel.close()
    animation = handle.rig.animation_data
    assert (animation.action if animation else None) == action
    assert handle.rig.matrix_world == rig_matrix
    assert (handle.scene.frame_start, handle.scene.frame_end, handle.scene.frame_current) == frame_range

    result = build_action(handle, motion, profile=profile)
    assert result['review']['passed'] and not result['experimental']
    rows = result['samples']
    cycle_frames = round(fragment.duration_s * motion.fps)
    assert len(rows) == 2 * cycle_frames + 1 == result['frames']
    assert rows[-1]['time_s'] == motion.duration_s
    start, seam, end = (rows[i]['measured'] for i in (0, cycle_frames, -1))
    pelvis, head = 'pelvis.position', 'head.orientation'
    seam_error = max(value_error(start[pelvis], state[pelvis]) for state in (seam, end))
    assert seam_error < .002
    z = [row['measured'][pelvis][2] for row in rows]
    for cycle in range(2):
        segment = z[cycle * cycle_frames:(cycle + 1) * cycle_frames + 1]
        assert abs(segment[0] - min(segment) - depth) < .002
    seam_speed = max(abs(z[i + 1] - z[i]) * motion.fps for i in (cycle_frames - 1, cycle_frames))
    assert seam_speed < .03
    head_error = max(value_error(row['measured'][head], start[head], 'quaternion') for row in rows)
    assert head_error < .5
    anchors = {anchor.anchor_id: anchor.position for anchor in entry.contact_anchors
               if anchor.anchor_id in entry.active_contacts}
    assert anchors.keys() == {'left.sole', 'right.sole'}
    for row in rows:
        assert row['active_foot_anchors'].keys() == anchors.keys()
        assert all(value_error(row['active_foot_anchors'][key], point) < .001 for key, point in anchors.items())
    contact_error = result['review']['metrics']['contact_error_m']
    assert contact_error < .001
    print(f'PATTERN_REPEAT_PASSED {rig} frames={len(rows)} seam_m={seam_error:.7f} '
          f'seam_speed_m_s={seam_speed:.7f} contact_m={contact_error:.7f} head_deg={head_error:.7f}', flush=True)


def check_transition_hold(rig):
    pose = {'demo': 'neutral', 'mixamo': 'turned-crouched'}[rig]
    handle, profile, entry = setup(rig, pose)
    start = next(value for value in entry.measured_controls if value.control_id == 'head.yaw')
    target = replace(start, value=start.value + 5)
    fragment = transition_fragment((target,), 1., instance_id='transition.pilot', entry=entry, profile=profile)
    fragment = hold_fragment(fragment, .4, entry=entry, profile=profile)
    motion = prepare_fragment(fragment, entry, profile)
    result = build_action(handle, motion, profile=profile)
    assert result['review']['passed'] and result['frames'] == 43
    samples = result['samples']
    measured = [row['measured'][target.control_id] for row in samples]
    assert abs(measured[0] - start.value) < .05
    hold_error = max(abs(angle - target.value) for angle in measured[30:])
    assert hold_error < .05
    assert all(row['active_foot_anchors'].keys() == set(entry.active_contacts) for row in samples)
    ending = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    handle.scene.frame_set(handle.scene.frame_end)
    returning = transition_fragment((start,), 1., instance_id='transition.return', entry=ending, profile=profile)
    returned = build_action(handle, prepare_fragment(returning, ending, profile), profile=profile)
    assert returned['review']['passed'] and returned['frames'] == 31
    assert abs(returned['samples'][0]['measured'][target.control_id] - measured[-1]) < .05
    assert abs(returned['samples'][-1]['measured'][target.control_id] - start.value) < .05
    print(f'PATTERN_TRANSITION_HOLD_PASSED {rig} frames=43+31 hold_error_deg={hold_error:.7f}', flush=True)


def check_phase(rig):
    pose = {'demo': 'neutral', 'mixamo': 'turned-crouched'}[rig]
    handle, profile, entry = setup(rig, pose)
    measured = {value.control_id: value for value in entry.measured_controls}
    left_id, right_id = 'left.elbow.flexion', 'right.elbow.flexion'

    def raise_elbow(control_id):
        target = replace(measured[control_id], value=measured[control_id].value + 5)
        return transition_fragment((target,), 1., instance_id=control_id, entry=entry, profile=profile)

    phase = .5 if rig == 'demo' else -.5
    fragment = phase_offset_fragments(raise_elbow(left_id), raise_elbow(right_id), phase,
                                      fragment_id='phase.pilot', entry=entry, profile=profile)
    motion = prepare_fragment(fragment, entry, profile)
    result = build_action(handle, motion, profile=profile)
    rows = result['samples']
    assert result['review']['passed'] and len(rows) == result['frames'] == 46
    leading, delayed = (left_id, right_id) if phase > 0 else (right_id, left_id)
    assert all(abs(row['measured'][delayed] - measured[delayed].value) < .05 for row in rows[:16])
    assert abs(rows[15]['measured'][leading] - measured[leading].value - 2.5) < .05
    assert all(abs(rows[-1]['measured'][id] - measured[id].value - 5) < .05 for id in (left_id, right_id))
    assert all(row['active_foot_anchors'].keys() == set(entry.active_contacts) for row in rows)
    print(f'PATTERN_PHASE_PASSED {rig} frames={len(rows)} leading={leading}', flush=True)


def check_stroke(rig, mode):
    pose = {'demo': 'neutral', 'mixamo': 'turned-crouched'}[rig]
    handle, profile, entry = setup(rig, pose)
    fragment = stroke_pattern(mode, {'duration_s': 1.2, 'hold_s': .1, 'amplitude_m': .04}, 1,
                              fragment_id='stroke.pilot', entry=entry, profile=profile, surfaces=handle.surfaces)
    motion = prepare_fragment(fragment, entry, profile)
    result = build_action(handle, motion, profile=profile)
    rows = result['samples']
    assert result['review']['passed'] and not result['experimental']
    assert rows[-1]['time_s'] == motion.duration_s and motion.loop is None
    assert all(row['active_foot_anchors'].keys() == set(entry.active_contacts) for row in rows)
    relative_hand_error = {}
    for side in ('left', 'right'):
        key = side + '.hand.position'
        start = rows[0]['measured'][key]
        excursion = max(value_error(row['measured'][key], start) for row in rows)
        assert excursion > .04
        assert value_error(rows[-1]['measured'][key], start) < .002
        relative_hand_error[side] = max(row['tracking_errors'].get(key, 0.) for row in rows)
        assert relative_hand_error[side] < .001
    print(f'PATTERN_STROKE_PASSED {rig} {mode} frames={len(rows)} max_hand_m={max(relative_hand_error.values()):.7f}',
          flush=True)
    return handle, profile, fragment, motion, result


def check_torso(rig, mode, *side):
    pose = {'demo': 'neutral', 'mixamo': 'turned-crouched'}[rig]
    handle, profile, entry = setup(rig, pose)
    fragment = torso_pattern(mode, {'angle': 5}, 1, fragment_id='torso.pilot',
                             entry=entry, profile=profile, surfaces=handle.surfaces,
                             follow_through=side[0] if side else None)
    result = build_action(handle, prepare_fragment(fragment, entry, profile), profile=profile)
    rows = result['samples']
    assert result['review']['passed'] and not result['experimental']
    assert all(row['active_foot_anchors'].keys() == set(entry.active_contacts) for row in rows)
    axis = 'torso.roll' if mode == 'sway' else 'torso.pitch'
    assert max(abs(row['measured'][axis] - rows[0]['measured'][axis]) for row in rows) > 1.
    assert abs(rows[-1]['measured'][axis] - rows[0]['measured'][axis]) < .05
    print(f'PATTERN_TORSO_PASSED {rig} {mode} {side} frames={len(rows)}', flush=True)


def check_steps(rig, lead):
    handle, profile, entry = setup(rig, 'turned-crouched')
    fragment = step_pattern(lead, {'distance_m': .06, 'clearance_m': .04}, 2, fragment_id='steps.pilot',
                            entry=entry, profile=profile, surfaces=handle.surfaces)
    motion = prepare_fragment(fragment, entry, profile)
    result = build_action(handle, motion, profile=profile)
    rows = result['samples']
    assert result['review']['passed'] and not result['experimental']
    assert all(row['active_foot_anchors'] for row in rows)
    assert rows[0]['active_foot_anchors'].keys() == rows[-1]['active_foot_anchors'].keys() == set(entry.active_contacts)
    for id in entry.active_contacts:
        before, after = (row['active_foot_anchors'][id] for row in (rows[0], rows[-1]))
        assert abs(value_error(after, before) - .06) < .001
    assert abs(value_error(rows[-1]['measured']['pelvis.position'], rows[0]['measured']['pelvis.position']) - .06) < .002
    print(f'PATTERN_STEPS_PASSED {rig} {lead} frames={len(rows)}', flush=True)
    moving_sole = lead + '.sole'
    origin = next(anchor.position for anchor in entry.contact_anchors if anchor.anchor_id == moving_sole)
    target = next(event.target_world_v1 for event in motion.contact_events
                  if event.anchor_id == moving_sole and event.interval.end_s == motion.duration_s)
    delta = rotate(inverse(entry.root_transform.orientation), tuple(a - b for a, b in zip(target, origin)))
    loop = c.LoopSpec(2, c.Transform(delta, (1., 0., 0., 0.), 'entry_body', 'metre'), 3., .01, 10.)
    seam = []
    for row in (rows[0], rows[1], rows[-2], rows[-1]):
        handle.scene.frame_set(row['frame'])
        snapshot = capture_entry(handle, profile, revision=entry.revision)
        seam.append(replace(snapshot, captured_time_s=row['time_s']))
    looped, metrics = verify_translation_loop(motion, loop, profile, *seam)
    assert looped.loop == loop and motion.loop is None
    print(f'PATTERN_LOOP_PASSED {rig} {lead} {metrics}', flush=True)
    result['loop_seam'] = metrics
    return handle, profile, fragment, looped, result


if __name__ == '__main__':
    operation, rig, *extra = sys.argv[sys.argv.index('--') + 1:]
    {'repeat': check_repeat, 'transition-hold': check_transition_hold, 'phase': check_phase,
     'stroke': check_stroke, 'torso': check_torso, 'steps': check_steps}[operation](rig, *extra)
