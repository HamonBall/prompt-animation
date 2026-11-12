"""Check planted coordinated cycles and continuation on the two stage rigs."""
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

import bpy
from mathutils import Vector

from avatar_app.blender.motion import build_action, build_action_frames, set_contact
from avatar_app.blender.pose import axes, position_hand
from avatar_app.blender.rig_profile import semantic_frame
from avatar_app.blender.support_mechanics import calibrate_support
from avatar_app.motion import ContactConstraint
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import value_error
from avatar_app.movement_library.coordinated import grounded_root_windows
from avatar_app.movement_library.root_motion import POSITION
from avatar_app.movement_library.spatial import rotate
from blender_movement_root_travel_flight import setup
from blender_support_body import body_fixture
from test_movement_support_transfers import compile_support
from tools.preview_movement import capture_entry


def check_cycle(handle, profile, entry, depth, *, move='body.lower_rise', **params):
    motion = compile_support(profile, entry, move, {'depth_m': depth, **params})
    result = build_action(handle, motion, profile=profile)
    assert result['review']['passed']
    rows = result['samples']
    start = rows[0]['measured']
    assert abs(start['pelvis.position'][2] - min(row['measured']['pelvis.position'][2] for row in rows) - depth) < .002
    assert value_error(start['pelvis.position'], rows[-1]['measured']['pelvis.position']) < .002
    assert all(set(row['active_foot_anchors']) == {'left.sole', 'right.sole'} for row in rows)
    expected = {anchor.anchor_id: anchor.position for anchor in entry.contact_anchors
                if anchor.anchor_id in entry.active_contacts}
    assert all(all(value_error(row['active_foot_anchors'][key], point) < .001
                   for key, point in expected.items()) for row in rows)
    assert all(value_error(row['measured']['head.orientation'], start['head.orientation'], 'quaternion') < .5
               for row in rows)
    assert result['review']['metrics']['contact_error_m'] < .001
    handle.scene.frame_set(handle.scene.frame_end)
    return c.from_dict(c.MotionStateSnapshot, result['ending_state'])


def setup_lunge(rig, pose, lead):
    handle, profile, entry = setup(rig, pose)
    forward = rotate(entry.root_transform.orientation, (0, 1, 0))
    local_heading = handle.rig.matrix_world.inverted().to_3x3() @ Vector((*forward[:2], 0))
    for side in ('left', 'right'):
        foot = handle.bones[side.title() + 'Foot']
        stride = .15 if side == lead else -.15
        set_contact(handle, ContactConstraint(side + '_foot'), foot.head.copy() + stride * local_heading,
                    foot.matrix.to_quaternion())
    bpy.context.view_layer.update()
    return handle, profile, capture_entry(handle, profile)


def lunge(rig, pose, lead):
    handle, profile, entry = setup_lunge(rig, pose, lead)
    ending = check_cycle(handle, profile, entry, .06, move='body.lunge', lead=lead, advance_m=.06)
    other = 'right' if lead == 'left' else 'left'
    try:
        compile_support(profile, ending, 'body.lunge', {'lead': other})
    except c.MotionContractError as error:
        assert error.code == 'ENTRY_MISMATCH', error.to_dict()
    else:
        raise AssertionError('Lunge accepted an incompatible lead sole')
    continued = check_cycle(handle, profile, ending, .04, move='body.lunge', lead=lead, advance_m=.04)
    assert continued.contact_anchors == ending.contact_anchors
    print('LUNGE_PASSED', rig, pose, lead, flush=True)


def main(rig, pose):
    handle, profile, entry = setup(rig, pose)
    ending = check_cycle(handle, profile, entry, .06 if pose == 'neutral' else .10)
    assert ending.contact_anchors == tuple(anchor for anchor in entry.contact_anchors
                                            if anchor.anchor_id in entry.active_contacts)
    continued = check_cycle(handle, profile, ending, .03)
    assert continued.contact_anchors == ending.contact_anchors

    action = handle.rig.animation_data.action
    frame = handle.scene.frame_current
    incompatible = replace(continued, active_contacts=('right.sole',))
    try:
        compile_support(profile, incompatible, 'body.lower_rise', {})
    except c.MotionContractError as error:
        assert error.code == 'ENTRY_MISMATCH', error.to_dict()
    else:
        raise AssertionError('Lower/rise accepted a one-sole entry')
    motion = compile_support(profile, continued, 'body.lower_rise', {})
    candidate = build_action_frames(handle, motion, profile=profile)
    try:
        for _ in range(8):
            next(candidate)
    finally:
        candidate.close()
    assert handle.rig.animation_data.action == action
    assert handle.scene.frame_current == frame
    print('LOWER_RISE_PASSED', rig, pose, flush=True)


def check_takeoff(motion, rows):
    measured = rows[0]['measured']
    soles = {'left.sole', 'right.sole'}
    airborne = [row for row in rows if row['floor_m'] > .10]
    assert airborne and all(not row['active_foot_anchors'] for row in airborne)
    assert all(abs(row['measured']['left.knee.flexion'] - measured['left.knee.flexion']) < .5 for row in airborne)
    preparation, recovery = grounded_root_windows(motion, {track.control_id for track in motion.tracks})
    loaded = [row for row in rows if row['time_s'] < preparation.end_s]
    assert loaded and all(set(row['active_foot_anchors']) == soles for row in loaded)
    push_off = measured['pelvis.position'][2] - min(row['measured']['pelvis.position'][2] for row in loaded)
    assert abs(push_off - .075) < .002
    assert max(row['measured']['left.knee.flexion'] for row in loaded) > measured['left.knee.flexion'] + 5
    assert all(value_error(row['measured'][POSITION], measured[POSITION]) < .001 for row in loaded)
    recovering = [row for row in rows if row['time_s'] >= recovery.start_s - 1e-9]
    assert recovering and all(set(row['active_foot_anchors']) == soles for row in recovering)
    assert all(value_error(row['measured'][POSITION], measured[POSITION]) < .001 for row in recovering)
    compression = measured['pelvis.position'][2] - min(row['measured']['pelvis.position'][2] for row in recovering)
    assert abs(compression - .055) < .002
    assert max(row['measured']['left.knee.flexion'] for row in recovering) > measured['left.knee.flexion'] + 5
    assert value_error(rows[-1]['measured']['pelvis.position'], measured['pelvis.position']) < .002
    assert value_error(rows[-1]['measured'][POSITION], measured[POSITION]) < .001
    assert all(value_error(row['measured']['head.orientation'], measured['head.orientation'], 'quaternion') < .5
               for row in rows)


def check_transition(move, rig, pose, side='left'):
    handle, profile, entry = setup(rig, pose)
    step = move == 'step'
    motion = compile_support(profile, entry, 'body.' + move, {'side': side} if step else {})
    try:
        result = build_action(handle, motion, profile=profile)
    except c.PlanError as error:
        print(getattr(error, 'review', None) or str(error), flush=True)
        raise
    rows = result['samples']
    measured = rows[0]['measured']
    soles = {'left.sole', 'right.sole'}
    assert set(rows[0]['active_foot_anchors']) == set(rows[-1]['active_foot_anchors']) == soles
    if step:
        foot, stance = side + '.sole', next(sole for sole in soles if not sole.startswith(side))
        assert any(foot not in row['active_foot_anchors'] for row in rows)
        assert all(value_error(row['active_foot_anchors'][stance], measured[stance + '.position']) < .001 for row in rows)
        assert max(row['measured'][foot + '.position'][2] for row in rows) > .055
        distance = value_error(rows[-1]['measured'][foot + '.position'], measured[foot + '.position'])
        assert abs(distance - .10) < .002
        pelvis_advance = value_error(rows[-1]['measured']['pelvis.position'], measured['pelvis.position'])
        assert abs(pelvis_advance - .05) < .002
    else:
        check_takeoff(motion, rows)
    assert all(value_error(row['measured']['head.orientation'], measured['head.orientation'], 'quaternion') < .5
               for row in rows)
    assert result['review']['metrics']['contact_error_m'] < .001
    ending = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    handle.scene.frame_set(handle.scene.frame_end)
    continued = check_cycle(handle, profile, ending, .03)
    expected = {anchor.anchor_id: anchor for anchor in ending.contact_anchors}
    assert set(continued.active_contacts) == set(expected)
    for anchor in continued.contact_anchors:
        source = expected[anchor.anchor_id]
        assert replace(anchor, position=source.position) == source
        assert value_error(anchor.position, source.position) < .000001
    print('COORDINATED_TRANSITION_PASSED', move, rig, pose, side, flush=True)


def check_body_contact(rig, kind):
    handle, profile, entry, surface, anchor = body_fixture(rig, kind)
    kneel = kind == 'knee'
    move = 'body.kneel_rise' if kneel else 'body.floor_transfer'
    params = {'surface': surface.name}
    motion = compile_support(profile, entry, move, params, handle.surfaces)
    try:
        result = build_action(handle, motion, profile=profile)
    except c.PlanError as error:
        print(getattr(error, 'review', None) or str(error), flush=True)
        raise
    rows = result['samples']
    soles = set(entry.active_contacts)
    supported = soles | {anchor}
    assert set(rows[0]['active_support_anchors']) == soles
    assert all(soles <= set(row['active_support_anchors']) for row in rows)
    assert any(set(row['active_support_anchors']) == supported for row in rows)
    assert set(rows[-1]['active_support_anchors']) == (soles if kneel else supported)
    gaps = [row['support_skin_gaps_m'][anchor] for row in rows if anchor in row.get('support_skin_gaps_m', {})]
    assert gaps and max(gaps) <= .025
    initial = rows[0]['measured']
    assert min(row['measured']['pelvis.position'][2] for row in rows) < initial['pelvis.position'][2] - .01
    assert all(value_error(row['measured']['head.orientation'], initial['head.orientation'], 'quaternion') < .5
               for row in rows)
    ending = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    handle.scene.frame_set(handle.scene.frame_end)
    if kneel:
        assert value_error(rows[-1]['measured']['pelvis.position'], initial['pelvis.position']) < .002
        following_move, following_params = move, params
    else:
        following_move = 'support.acquire_release'
        following_params = {'anchor': anchor, 'operation': 'release'}
    following = compile_support(profile, ending, following_move, following_params, handle.surfaces)
    continued = build_action(handle, following, profile=profile)
    assert continued['review']['passed']
    assert value_error(continued['samples'][0]['measured']['pelvis.position'], rows[-1]['measured']['pelvis.position']) < .002
    assert set(continued['samples'][-1]['active_support_anchors']) == soles
    print('COORDINATED_BODY_CONTACT_PASSED', rig, kind, flush=True)


def setup_floor_sit(rig, pose):
    handle, profile, _ = setup(rig, pose)
    profile = calibrate_support(handle, profile)
    world = handle.rig.matrix_world
    inverse = world.inverted()
    basis = semantic_frame(handle, profile, 'pelvis').to_3x3()
    for side, sign in (('Left', -1), ('Right', 1)):
        if pose.endswith('crouched'):
            foot = handle.bones[side + 'Foot']
            spread = inverse.to_3x3() @ (basis.col[0] * (.035 * sign))
            knee_pole = inverse.to_3x3() @ (basis @ Vector((.10 * sign, 1, 0)))
            set_contact(handle, ContactConstraint(side.lower() + '_foot'), foot.head.copy() + spread,
                        foot.matrix.to_quaternion(), leg_pole=knee_pole)
        hand = handle.bones[side + 'Hand']
        shoulder = world @ handle.bones[side + 'Arm'].head
        target = world @ hand.head + basis @ Vector((.05 * sign, .15, .17))
        pole = shoulder + basis @ Vector((.35 * sign, -.15, -.20))
        position_hand(handle, side, inverse @ target, axes(handle), pole=inverse @ pole)
    bpy.context.view_layer.update()
    return handle, profile, capture_entry(handle, profile)


def check_floor_sit(rig, pose, follow='release'):
    handle, profile, entry = setup_floor_sit(rig, pose)
    motion = compile_support(profile, entry, 'body.floor_transfer', {'route': 'standing_to_seated'}, handle.surfaces)
    try:
        result = build_action(handle, motion, profile=profile)
    except c.PlanError as error:
        diagnostic = error.to_dict() if isinstance(error, c.MotionContractError) else str(error)
        print('FLOOR_SIT_FAILED', getattr(error, 'review', None) or diagnostic, flush=True)
        raise
    rows = result['samples']
    sole_ids = {'left.sole', 'right.sole'}
    assert set(rows[0]['active_support_anchors']) == sole_ids
    assert all(sole_ids <= set(row['active_support_anchors']) for row in rows)
    assert set(rows[-1]['active_support_anchors']) == sole_ids | {'pelvis.support'}
    assert rows[-1]['support_skin_gaps_m']['pelvis.support'] < .003
    assert rows[-1]['measured']['pelvis.position'][2] < .15 * profile.height_m
    assert all(value_error(row['measured']['head.orientation'], rows[0]['measured']['head.orientation'], 'quaternion') < .5
               for row in rows)
    for side in ('left', 'right'):
        key = side + '.hand.torso_position'
        assert all(value_error(row['measured'][key], rows[0]['measured'][key]) < .002 for row in rows)
    ending = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    handle.scene.frame_set(handle.scene.frame_end)
    move, params = ('body.floor_transfer', {'route': 'seated_to_back'}) if follow == 'back' else (
        'support.acquire_release', {'anchor': 'pelvis.support', 'operation': 'release'})
    following = compile_support(profile, ending, move, params, handle.surfaces)
    try:
        continuation = build_action(handle, following, profile=profile)
    except c.PlanError as error:
        diagnostic = error.to_dict() if isinstance(error, c.MotionContractError) else str(error)
        print('FLOOR_SIT_CONTINUATION_FAILED', getattr(error, 'review', None) or diagnostic, flush=True)
        raise
    assert continuation['review']['passed']
    assert value_error(continuation['samples'][0]['measured']['pelvis.position'], rows[-1]['measured']['pelvis.position']) < .002
    if follow == 'back':
        back_rows = continuation['samples']
        assert all(sole_ids <= row['active_support_anchors'].keys() for row in back_rows)
        assert set(back_rows[-1]['active_support_anchors']) == sole_ids | {'back.support'}
        assert back_rows[-1]['support_skin_gaps_m']['back.support'] < .003
        print('COORDINATED_SEAT_TO_BACK_PASSED', rig, pose, flush=True)
    print('COORDINATED_FLOOR_SIT_PASSED', rig, pose, flush=True)


def check_planted_kneel(rig, pose, side):
    handle, profile, _ = setup(rig, pose)
    profile = calibrate_support(handle, profile)
    entry = capture_entry(handle, profile)
    params = {'route': 'planted_to_knee', 'side': side}
    motion = compile_support(profile, entry, 'body.kneel_rise', params, handle.surfaces)
    try:
        result = build_action(handle, motion, profile=profile)
    except c.PlanError as error:
        diagnostic = error.to_dict() if isinstance(error, c.MotionContractError) else str(error)
        print('PLANTED_KNEEL_FAILED', getattr(error, 'review', None) or diagnostic, flush=True)
        raise
    rows = result['samples']
    knee = side + '.knee.support'
    stance = 'right.sole' if side == 'left' else 'left.sole'
    assert all(stance in row['active_support_anchors'] for row in rows)
    assert any(knee in row['active_support_anchors'] for row in rows)
    assert set(rows[-1]['active_support_anchors']) == {'left.sole', 'right.sole'}
    assert all(value_error(row['measured']['head.orientation'], rows[0]['measured']['head.orientation'], 'quaternion') < .5
               for row in rows)
    ending = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    handle.scene.frame_set(handle.scene.frame_end)
    check_cycle(handle, profile, ending, .03)
    print('COORDINATED_PLANTED_KNEEL_PASSED', rig, pose, side, flush=True)


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:]
    if args[0] == 'lunge':
        lunge(*args[1:])
    elif args[0] in ('step', 'takeoff_land'):
        check_transition(*args)
    elif args[0] == 'body_contact':
        check_body_contact(*args[1:])
    elif args[0] == 'floor_sit':
        check_floor_sit(*args[1:])
    elif args[0] == 'planted_kneel':
        check_planted_kneel(*args[1:])
    else:
        main(*args)
