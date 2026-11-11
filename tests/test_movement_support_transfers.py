"""Contract checks for fixed world support and overlapping transfer."""
from dataclasses import replace
from pathlib import Path
import unittest

from avatar_app.motion import Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment, instantiate_movement, prepare_fragment
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.support import schedule, sole_region_margin, validate_support_drivers

FIXTURES = Path(__file__).parent / 'fixtures/ankles_feet_toes/v1/demo'


def compile_support(profile, entry, move, params, surfaces=(Surface(),)):
    catalog = catalog_for_profile(profile)
    instance = instantiate_movement(move, params, instance_id='support.test', profile=profile,
                                    entry_state=entry, catalog=catalog)
    fragment = build_fragment(instance, entry, profile, surfaces, catalog)
    return prepare_fragment(fragment, entry, profile)


class SupportSchedules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = c.loads(c.AvatarProfile, (FIXTURES / 'profile.json').read_text())
        original = c.loads(c.MotionStateSnapshot, (FIXTURES / 'heel.raise-entry.json').read_text())
        cls.entry = replace(original, active_contacts=('right.sole',))

    def test_transfer_reaches_new_support_before_release(self):
        motion = compile_support(self.profile, self.entry, 'support.transfer', {})
        old, new = sorted(motion.contact_events, key=lambda event: event.acquire_s)
        self.assertEqual((old.anchor_id, new.anchor_id), ('right.sole', 'left.sole'))
        self.assertGreater(motion.duration_s - old.release_s - new.acquire_s, 1 / c.FPS)
        self.assertEqual(new.release_s, 0)
        self.assertEqual(c.loads(c.ExecutableMotion, c.dumps(motion)), motion)
        data = c.to_dict(old)
        data.pop('target_world_v1')
        legacy = c.from_dict(c.ContactEvent, data)
        self.assertIsNone(legacy.target_world_v1)
        self.assertEqual(c.to_dict(legacy), data)

    def test_world_target_needs_matching_resolved_region(self):
        seat = Surface('platform', .1, (0, 0), (.4, .6))
        for target, surface, code in (
            ((0, 0, .101), 'unknown', 'UNRESOLVED_SURFACE'),
            ((0, 0, .15), 'platform', 'INVALID_PARAMETER'),
            ((.25, 0, .1), 'platform', 'INVALID_PARAMETER'),
        ):
            with self.subTest(target=target, surface=surface), self.assertRaises(c.MotionContractError) as caught:
                compile_support(self.profile, self.entry, 'support.transfer', {'surface': surface, 'target': target},
                                (Surface(), seat))
            self.assertEqual(caught.exception.code, code)
        motion = compile_support(self.profile, self.entry, 'support.transfer',
                                 {'surface': 'platform', 'target': (.05, 0, .1)}, (Surface(), seat))
        event = next(event for event in motion.contact_events if event.surface_id == 'platform')
        self.assertEqual(event.target_world_v1, (.05, 0, .1))

    def test_releasing_last_support_requires_airborne_intent(self):
        options = dict(operation='release', anchor='right.sole')
        with self.assertRaises(c.MotionContractError) as caught:
            compile_support(self.profile, self.entry, 'support.acquire_release', options)
        self.assertEqual(caught.exception.code, 'CONSTRAINT_CONFLICT')
        motion = compile_support(self.profile, self.entry, 'support.acquire_release',
                                 {**options, 'allow_airborne': True})
        self.assertEqual(len(motion.contact_events), 1)
        self.assertGreater(motion.contact_events[0].release_s, 0)

    def test_same_anchor_cannot_attach_to_two_surfaces(self):
        old = next(anchor for anchor in self.entry.contact_anchors if anchor.anchor_id == 'right.sole')
        with self.assertRaises(c.MotionContractError) as caught:
            schedule('support.test', self.entry, (Surface(),), acquire=old, acquire_frames=10)
        self.assertEqual(caught.exception.code, 'CONSTRAINT_CONFLICT')
        motion = compile_support(self.profile, self.entry, 'support.transfer', {})
        event = motion.contact_events[-1]
        before = replace(event, event_id='other', surface_id='platform', acquire_s=0,
                         interval=c.TimeInterval(0, .5))
        after = replace(event, acquire_s=0, interval=c.TimeInterval(.5, 1))
        with self.assertRaises(c.MotionContractError) as caught:
            replace(motion, contact_events=(before, after), source_map=())
        self.assertEqual(caught.exception.code, 'CONSTRAINT_CONFLICT')

    def test_geometric_balance_uses_measured_one_sole_region(self):
        values = tuple(replace(value, value=(*value.value[:2], .1))
                       if value.control_id == 'left.sole.position' else value for value in self.entry.measured_controls)
        entry = replace(self.entry, measured_controls=values)
        motion = compile_support(self.profile, entry, 'body.balance', {'anchor': 'right.sole'})
        track, = motion.tracks
        self.assertEqual(track.control_id, 'pelvis.position')
        self.assertEqual(track.curve.start_value[2], track.curve.end_value[2])
        self.assertGreater(motion.duration_s, track.interval.end_s)
        measured = {value.control_id: value.value for value in values}
        heel = measured['right.heel.position']
        forefoot = measured['right.forefoot.position']
        self.assertGreater(sole_region_margin(track.curve.end_value, heel, forefoot), .005)
        self.assertLess(sole_region_margin((10, 0, 0), heel, forefoot), 0)
        for state, params, code in (
            (self.entry, {'anchor': 'right.sole'}, 'ENTRY_MISMATCH'),
            (entry, {'anchor': 'left.sole'}, 'ENTRY_MISMATCH'),
            (entry, {'anchor': 'right.sole', 'target': (10, 0, track.curve.end_value[2])}, 'INVALID_PARAMETER'),
        ):
            with self.subTest(params=params), self.assertRaises(c.MotionContractError) as caught:
                compile_support(self.profile, state, 'body.balance', params)
            self.assertEqual(caught.exception.code, code)

    def test_rigid_heel_and_forefoot_share_schedule_but_not_a_leg(self):
        values = {value.control_id: value.value for value in self.entry.measured_controls}
        for part in ('heel', 'forefoot'):
            with self.subTest(part=part):
                anchor = 'left.' + part
                motion = compile_support(self.profile, self.entry, 'support.transfer', {'anchor': anchor})
                event = next(event for event in motion.contact_events if event.anchor_id == anchor)
                self.assertEqual(event.target_world_v1, (*values[anchor + '.position'][:2], 0))
                with self.assertRaises(c.MotionContractError) as caught:
                    compile_support(self.profile, self.entry, 'support.transfer', {'anchor': 'right.' + part})
                self.assertEqual(caught.exception.code, 'CONSTRAINT_CONFLICT')

    def test_pelvis_driven_contact_ownership(self):
        for anchors in (('back.support', 'pelvis.support'), ('left.knee.support', 'left.heel')):
            with self.subTest(anchors=anchors), self.assertRaises(c.MotionContractError) as caught:
                validate_support_drivers(anchors)
            self.assertEqual(caught.exception.code, 'CONSTRAINT_CONFLICT')
        validate_support_drivers(('left.knee.support', 'right.sole'))
        validate_support_drivers(('right.palm', 'right.sole'))
