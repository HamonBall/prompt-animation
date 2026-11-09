"""Pure Stage 05.5 support schedules, range rejection and optional anatomy."""
from dataclasses import replace
from pathlib import Path
import unittest

from avatar_app.motion import Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment, instantiate_movement, prepare_fragment
from avatar_app.movement_library.feet import IDS, MARKER, POINTS
from avatar_app.movement_library.joints import catalog_for_profile


FIXTURES = Path(__file__).parent / 'fixtures/hips_knees/v1'


def synthetic_profile_and_entry(rig, raised=False):
    directory = FIXTURES / rig
    old = c.loads(c.AvatarProfile, (directory / 'profile.json').read_text())
    fixture = 'knee.orient-entry.json' if raised else 'hip.lift-entry.json'
    entry = c.loads(c.MotionStateSnapshot, (directory / fixture).read_text())
    anchors = {item.anchor_id: item for item in entry.contact_anchors}
    landmarks = list(old.landmarks)
    controls = list(old.controls)
    values = list(entry.measured_controls)
    limits = list(old.joint_limits)
    for side, other, sign in (('left', 'right', 1), ('right', 'left', -1)):
        chain = f'{side}.ankle'
        sole = next(item for item in landmarks if item.id == f'{side}.sole')
        captured = anchors[sole.id]
        for part, offset in (('heel', -.06), ('forefoot', .08)):
            id = f'{side}.{part}'
            offset_point = lambda value: (value[0], value[1] + offset, value[2])
            landmarks.append(replace(sole, id=id, position=offset_point(sole.position)))
            anchors[id] = replace(captured, anchor_id=id, position=offset_point(captured.position))
        for part in POINTS:
            id = f'{side}.{part}.position'
            controls.append(c.ControlSpec(id, 'metre', 'vector', 3, ('world',), chain, 'measure.' + id))
            values.append(c.ControlValue(id, 'metre', 'world', anchors[f'{side}.{part}'].position))
        id = f'{side}.ankle.tilt'
        frame = f'joint:{side}.shin'
        controls.append(c.ControlSpec(id, 'degree', 'scalar', 1, (frame,), chain, 'measure.' + id))
        limits.append(c.JointLimit(id, -25, 25, 0, (0, sign, 0), f'{other}.ankle.tilt', 1, 'synthetic', -15, 15))
        values.append(c.ControlValue(id, 'degree', frame, 0))
    profile = replace(old, version=8, controls=tuple(controls), landmarks=tuple(landmarks), joint_limits=tuple(limits),
                      capabilities=tuple(sorted(set(old.capabilities) | {item.capability for item in controls})),
                      calibration_provenance=replace(old.calibration_provenance,
                                                     evidence=old.calibration_provenance.evidence + (MARKER,)))
    entry = replace(entry, profile_version=8, contact_anchors=tuple(anchors.values()), measured_controls=tuple(values))
    return old, profile, entry


def compile_case(profile, entry, move, **params):
    catalog = catalog_for_profile(profile)
    instance = instantiate_movement(move, params, instance_id='feet.test', profile=profile,
                                    entry_state=entry, catalog=catalog)
    fragment = build_fragment(instance, entry, profile, (Surface(),), catalog)
    return prepare_fragment(fragment, entry, profile)


class FootContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old, cls.profile, cls.entry = synthetic_profile_and_entry('demo')
        _, cls.raised_profile, cls.raised = synthetic_profile_and_entry('demo', raised=True)

    def test_version_and_optional_toes(self):
        self.assertFalse(set(IDS) & set(catalog_for_profile(self.old).definitions))
        self.assertNotIn('toes.curl', catalog_for_profile(self.profile).definitions)
        _, capable, raised = synthetic_profile_and_entry('mixamo', raised=True)
        self.assertIn('toes.curl', catalog_for_profile(capable).definitions)
        motion = compile_case(capable, raised, 'toes.curl', angle=8)
        self.assertEqual({track.control_id for track in motion.tracks}, {'left.toe.flexion'})

    def test_roll_uses_three_fixed_support_phases(self):
        motion = compile_case(self.profile, self.entry, 'foot.roll')
        self.assertEqual(c.loads(c.ExecutableMotion, c.dumps(motion)), motion)
        selected = [event for event in motion.contact_events if event.anchor_id.startswith('left.')]
        fixed = [event.anchor_id for event in selected if not (event.acquire_s or event.release_s)]
        self.assertEqual(fixed, ['left.heel', 'left.sole', 'left.forefoot'])
        self.assertEqual(selected[-1].release_s, .2)
        self.assertTrue(all(track.control_id == 'left.foot.orientation' for track in motion.tracks))

    def test_place_tap_and_lift_have_explicit_acquisition(self):
        for move in ('foot.place', 'foot.tap', 'foot.lift'):
            with self.subTest(move=move):
                params = {} if move == 'foot.lift' else {'distance_m': 0}
                motion = compile_case(self.profile, self.entry, move, **params)
                contacts = sorted((event for event in motion.contact_events if event.anchor_id == 'left.sole'),
                                  key=lambda event: event.interval.start_s)
                self.assertGreater(contacts[0].release_s, 0)
                self.assertGreater(contacts[1].acquire_s, 0)
                self.assertLess(contacts[0].interval.end_s, contacts[1].interval.start_s)
                self.assertEqual(contacts[-1].interval.end_s, motion.duration_s)

    def test_joint_only_motion_does_not_author_parent_tracks(self):
        for move, key in (('ankle.flex', 'left.ankle.flexion'), ('ankle.tilt', 'left.ankle.tilt')):
            motion = compile_case(self.raised_profile, self.raised, move, angle=0)
            self.assertEqual({track.control_id for track in motion.tracks}, {key})
            self.assertEqual([event.anchor_id for event in motion.contact_events], ['right.sole'])

    def test_invalid_anchor_target_and_support_fail_before_execution(self):
        inputs = (
            ('foot.pivot', {'anchor': 'sole'}, 'INVALID_PARAMETER'),
            ('foot.place', {'target': (10, 10, 0)}, 'INVALID_PARAMETER'),
            ('foot.place', {'target': (0, 0, .2)}, 'INVALID_PARAMETER'),
            ('ankle.flex', {'support': 'free'}, 'CONSTRAINT_CONFLICT'),
            ('ankle.tilt', {'support': 'pivot', 'angle': 4}, 'INVALID_PARAMETER'),
            ('heel.raise', {'angle': float('nan')}, 'INVALID_PARAMETER'),
        )
        for move, params, code in inputs:
            with self.subTest(move=move, params=params), self.assertRaises(c.MotionContractError) as caught:
                compile_case(self.profile, self.entry, move, **params)
            self.assertEqual(caught.exception.code, code)
        missing = replace(self.entry, contact_anchors=tuple(a for a in self.entry.contact_anchors if a.anchor_id != 'left.heel'))
        with self.assertRaises(c.MotionContractError) as caught:
            compile_case(self.profile, missing, 'foot.pivot')
        self.assertEqual(caught.exception.details['anchor_id'], 'left.heel')
