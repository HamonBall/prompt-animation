"""Current-source mirrored and timing-boundary checks for Stage 05.6b."""
from dataclasses import replace
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.blender import rig_profile as rp
from avatar_app.blender.geometry import support_skin_height
from avatar_app.blender.motion import build_action, set_contact
from avatar_app.blender.support_mechanics import calibrate_support
from avatar_app.motion import ContactConstraint, Surface
from avatar_app.movement_library import contracts as c
from blender_movement_root_travel_flight import setup
from blender_movement_support_transfers import save_case
from blender_support_body import body_fixture, make_pad
from blender_support_palm import palm_fixture
from test_movement_support_transfers import compile_support
from tools.preview_movement import capture_entry
from tools.artifact_store import digest

CASES = ('heel-right-fast', 'forefoot-right-slow', 'palm-left-fast',
         'knee-right-slow', 'balance-fast', 'balance-slow',
         'palm-left-cycle', 'pelvis-cycle', 'knee-right-cycle')
FAST = {'acquire_s': .5, 'hold_s': .1, 'release_s': .5}
SLOW = {'acquire_s': 2, 'hold_s': 1, 'release_s': 2}
CYCLE = {'acquire_s': 1.2, 'hold_s': .3, 'release_s': 1.2}


def fixture(rig, case):
    if case.startswith('palm-left'):
        handle, profile, entry, pad, point = palm_fixture(rig, 'left')
        if case.endswith('cycle'):
            return handle, profile, entry, 'support.acquire_release', {
                **CYCLE, 'anchor': 'left.palm', 'surface': pad.name, 'target': tuple(point),
            }
        return handle, profile, entry, 'support.transfer', {
            **FAST, 'anchor': 'left.palm', 'from_anchor': 'left.sole',
            'surface': pad.name, 'target': tuple(point),
        }
    if case == 'pelvis-cycle':
        handle, profile, entry, pad, anchor = body_fixture(rig, 'pelvis')
        return handle, profile, entry, 'support.acquire_release', {**CYCLE, 'anchor': anchor, 'surface': pad.name}
    handle, profile, entry = setup(rig, 'turned-crouched-raised-right')
    if case.startswith('knee-right'):
        profile = calibrate_support(handle, profile)
        entry = capture_entry(handle, profile)
        anchor = 'right.knee.support'
        point = rp.measure_endpoint(handle, profile, anchor)
        region = Surface('knee-pad', 0, point[:2], (.16, .16))
        skin = support_skin_height(handle, 'right_knee', region)
        make_pad(handle, Surface(region.name, skin - .025, region.center, region.size))
        if case.endswith('cycle'):
            return handle, profile, entry, 'support.acquire_release', {
                **CYCLE, 'anchor': anchor, 'surface': region.name,
            }
        return handle, profile, entry, 'support.transfer', {
            **SLOW, 'anchor': anchor, 'from_anchor': 'left.sole', 'surface': region.name,
        }
    if case.startswith('balance'):
        duration, hold = (1.2, .2) if case.endswith('fast') else (3, 1)
        return handle, profile, entry, 'body.balance', {'anchor': 'left.sole', 'duration_s': duration, 'hold_s': hold}
    if case == 'heel-right-fast':
        # Keep the shortest ramp's travel within a small, visible reach.
        foot = handle.bones['RightFoot']
        clearance = rp.measure_endpoint(handle, profile, 'right.sole')[2]
        inverse = handle.rig.matrix_world.inverted().to_3x3()
        target = foot.head + inverse @ Vector((0, 0, .065 - clearance))
        pole = inverse @ rp.semantic_frame(handle, profile, 'pelvis').to_3x3().col[1]
        set_contact(handle, ContactConstraint('right_foot'), target, foot.matrix.to_quaternion(), leg_pole=pole)
        bpy.context.view_layer.update()
        entry = capture_entry(handle, profile)
        point, timing = 'heel', FAST
    else:
        point, timing = 'forefoot', SLOW
    return handle, profile, entry, 'support.acquire_release', {**timing, 'anchor': 'right.' + point}


def main(rig, case, *flags):
    if case == 'missing-palm':
        handle, profile, entry = setup(rig, 'turned-crouched-raised-left')
        assert 'measure.left.palm.position' not in profile.capabilities
        motion = compile_support(profile, entry, 'support.transfer', {})
        events = tuple(replace(event, anchor_id='left.palm') if event.anchor_id == 'left.sole' else event
                       for event in motion.contact_events)
        before = handle.rig.matrix_world.copy()
        action = getattr(handle.rig.animation_data, 'action', None)
        try:
            build_action(handle, replace(motion, contact_events=events), profile=profile)
        except c.MotionContractError as error:
            assert error.code == 'MISSING_CAPABILITY', error.to_dict()
            assert getattr(handle.rig.animation_data, 'action', None) == action and handle.rig.matrix_world == before
        else:
            raise AssertionError('A palm without calibration was accepted')
        print('SUPPORT_ENVELOPE_PASSED', rig, case, flush=True)
        return
    assert case in CASES
    handle, profile, entry, movement, params = fixture(rig, case)
    executable = compile_support(profile, entry, movement, params, handle.surfaces)
    try:
        result = build_action(handle, executable, profile=profile)
    except c.PlanError as error:
        diagnostic = error.to_dict() if isinstance(error, c.MotionContractError) else str(error)
        print('SUPPORT_ENVELOPE_FAILED', rig, case, getattr(error, 'review', None) or diagnostic, flush=True)
        raise
    anchor = params['anchor']
    rows = result['samples']
    supports = [set(row.get('active_support_anchors', row['active_foot_anchors'])) for row in rows]
    assert any(anchor in held for held in supports)
    assert all(supports)
    assert (anchor in supports[-1]) == (movement != 'support.acquire_release')
    if movement == 'support.transfer':
        assert any({anchor, params['from_anchor']} <= held for held in supports)
        assert params['from_anchor'] not in supports[-1]
    if '--save' in flags:
        result['envelope_authoring_sha256'] = digest(Path(__file__))
        save_case(rig, case, handle, profile, executable, result, params)
    print('SUPPORT_ENVELOPE_PASSED', rig, case, result['frames'], result['review']['metrics'], flush=True)


if __name__ == '__main__':
    main(*sys.argv[sys.argv.index('--') + 1:])
