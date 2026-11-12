"""Contract checks for bounded coordinated routes."""
from dataclasses import replace
from pathlib import Path
import unittest

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.coordinated import (
    CRAWL_ANCHORS, KNEE_CRAWL_ANCHORS, grounded_root_windows, has_floor_body_transition, has_seated_approach,
    has_step_support, validate_crawl_support,
)
from avatar_app.movement_library.spatial import angle_rotation, rotate
from avatar_app.motion import Surface
from test_movement_support_transfers import compile_support

FIXTURES = Path(__file__).parent / 'fixtures' / 'ankles_feet_toes' / 'v1' / 'demo'


class LowerRiseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = c.loads(c.AvatarProfile, (FIXTURES / 'profile.json').read_text())
        cls.entry = c.loads(c.MotionStateSnapshot, (FIXTURES / 'heel.raise-entry.json').read_text())

    def test_holds_captured_soles_while_lowering_and_returning(self):
        for depth, phase, hold in ((.03, .9, .1), (.06, 1.2, .2), (.10, 2, .6)):
            with self.subTest(depth=depth):
                motion = compile_support(self.profile, self.entry, 'body.lower_rise',
                                         {'depth_m': depth, 'phase_s': phase, 'hold_s': hold})
                origin = next(item.value for item in self.entry.measured_controls if item.control_id == 'pelvis.position')
                down, stay, up = sorted(motion.tracks, key=lambda track: track.interval.start_s)
                self.assertEqual(down.curve.start_value, origin)
                self.assertEqual(down.curve.end_value, (*origin[:2], origin[2] - depth))
                self.assertEqual(stay.curve.start_value, stay.curve.end_value)
                self.assertEqual(up.curve.end_value, origin)
                self.assertEqual({event.anchor_id for event in motion.contact_events}, {'left.sole', 'right.sole'})
                for event in motion.contact_events:
                    self.assertEqual(event.interval, c.TimeInterval(0, motion.duration_s))
                    self.assertEqual((event.acquire_s, event.release_s), (0, 0))

    def test_rejects_out_of_range_depth(self):
        for depth in (0, .101):
            with self.subTest(depth=depth), self.assertRaises(c.MotionContractError) as error:
                compile_support(self.profile, self.entry, 'body.lower_rise', {'depth_m': depth})
            self.assertEqual(error.exception.code, 'INVALID_PARAMETER')

    def test_lunge_follows_the_measured_entry_heading(self):
        heading = rotate(self.entry.root_transform.orientation, (0, 1, 0))
        pelvis = self.entry.root_transform.position
        for side in ('left', 'right'):
            with self.subTest(side=side):
                anchors = []
                for anchor in self.entry.contact_anchors:
                    direction = 1 if anchor.anchor_id == side + '.sole' else -1
                    point = (*(pelvis[i] + .16 * heading[i] * direction for i in range(2)), 0)
                    anchors.append(replace(anchor, position=point) if anchor.anchor_id.endswith('.sole') else anchor)
                entry = replace(self.entry, contact_anchors=tuple(anchors))
                motion = compile_support(self.profile, entry, 'body.lunge', {'lead': side})
                load = min(motion.tracks, key=lambda track: track.interval.start_s)
                delta = tuple(b - a for a, b in zip(load.curve.start_value, load.curve.end_value))
                self.assertAlmostEqual(sum(delta[i] * heading[i] for i in range(2)), .06, delta=.002)
                self.assertAlmostEqual(delta[2], -.06)
                other = 'right' if side == 'left' else 'left'
                with self.assertRaises(c.MotionContractError) as error:
                    compile_support(self.profile, entry, 'body.lunge', {'lead': other})
                self.assertEqual(error.exception.code, 'ENTRY_MISMATCH')

    def test_reacquisition_starts_after_the_release_and_swing(self):
        for move, count in (('body.step', 1), ('body.takeoff_land', 2)):
            with self.subTest(move=move):
                motion = compile_support(self.profile, self.entry, move, {})
                releases = [event for event in motion.contact_events if event.release_s]
                landings = [event for event in motion.contact_events if event.acquire_s]
                self.assertEqual(len(releases), count)
                self.assertEqual({event.anchor_id for event in releases}, {event.anchor_id for event in landings})
                self.assertLess(max(event.interval.end_s for event in releases),
                                min(event.interval.start_s for event in landings))
                self.assertTrue(all(event.interval.end_s == motion.duration_s for event in landings))

    def test_step_advances_pelvis_with_the_other_sole_held(self):
        motion = compile_support(self.profile, self.entry, 'body.step', {'side': 'right'})
        controls = {track.control_id for track in motion.tracks}
        self.assertTrue(has_step_support(self.entry, motion.contact_events, controls, motion.duration_s))
        tracks = [track for track in motion.tracks if track.control_id == 'pelvis.position']
        advance = max(tracks, key=lambda track: track.interval.start_s)
        self.assertAlmostEqual(sum((b - a) ** 2 for a, b in zip(advance.curve.start_value, advance.curve.end_value)),
                               .05 ** 2)
        stance = next(event for event in motion.contact_events if event.anchor_id == 'left.sole')
        self.assertEqual(stance.interval, c.TimeInterval(0, motion.duration_s))
        self.assertEqual(stance.target_world_v1, next(anchor.position for anchor in self.entry.contact_anchors
                                                      if anchor.anchor_id == 'left.sole'))
        partial_stance = replace(stance, release_s=.2)
        events = tuple(partial_stance if event is stance else event for event in motion.contact_events)
        self.assertFalse(has_step_support(self.entry, events, controls, motion.duration_s))

    def test_flight_recovery_requires_both_soles_held_before_pelvis_moves(self):
        motion = compile_support(self.profile, self.entry, 'body.takeoff_land', {})
        controls = {track.control_id for track in motion.tracks}
        preparation, recovery = grounded_root_windows(motion, controls)
        self.assertEqual(preparation.start_s, 0)
        self.assertGreater(preparation.end_s, 1)
        first_recovery = recovery.start_s
        landing = next(event for event in motion.contact_events if event.acquire_s)
        delayed = replace(landing, acquire_s=first_recovery - landing.interval.start_s + 1 / c.FPS)
        events = tuple(delayed if event is landing else event for event in motion.contact_events)
        self.assertFalse(grounded_root_windows(replace(motion, contact_events=events), controls))

    def test_kneel_cycle_keeps_the_opposite_sole_and_requires_a_nearby_surface(self):
        root = Path(__file__).parent / 'fixtures' / 'support_transfers' / 'v1' / 'demo'
        profile = c.loads(c.AvatarProfile, (root / 'support.transfer-profile.json').read_text())
        entry = c.loads(c.MotionStateSnapshot, (root / 'support.transfer-entry.json').read_text())
        knee = next(item.value for item in entry.measured_controls if item.control_id == 'left.knee.support.position')
        surfaces = (Surface(), Surface('pad', knee[2] - .03, knee[:2], (.2, .2)))
        motion = compile_support(profile, entry, 'body.kneel_rise', {'surface': 'pad'}, surfaces)
        contacts = {event.anchor_id: event for event in motion.contact_events}
        self.assertEqual(set(contacts), {'left.knee.support', 'right.sole'})
        self.assertGreater(contacts['left.knee.support'].release_s, 0)
        self.assertEqual(contacts['right.sole'].release_s, 0)
        for params, code in (({'side': 'right', 'surface': 'pad'}, 'ENTRY_MISMATCH'), ({}, 'ENTRY_MISMATCH')):
            with self.subTest(params=params), self.assertRaises(c.MotionContractError) as error:
                compile_support(profile, entry, 'body.kneel_rise', params, surfaces)
            self.assertEqual(error.exception.code, code)

    def test_standing_to_seated_gives_the_floor_contact_ownership_after_descent(self):
        root = Path(__file__).parent / 'fixtures' / 'support_transfers' / 'v1' / 'demo'
        profile = c.loads(c.AvatarProfile, (root / 'support.transfer-profile.json').read_text())
        entry = c.loads(c.MotionStateSnapshot, (root / 'support.transfer-entry.json').read_text())
        values = {item.control_id: item.value for item in entry.measured_controls}
        soles = ('left.sole', 'right.sole')
        anchors = tuple(c.ContactAnchor(sole, 'floor', (*values[sole + '.position'][:2], 0), 'world', 'metre')
                        for sole in soles)
        entry = replace(entry, active_contacts=soles, contact_anchors=anchors)
        motion = compile_support(profile, entry, 'body.floor_transfer', {'route': 'standing_to_seated'})
        self.assertTrue(has_seated_approach(motion, {track.control_id for track in motion.tracks}))
        track = next(track for track in motion.tracks if track.control_id == 'pelvis.position')
        seat = next(event for event in motion.contact_events if event.anchor_id == 'pelvis.support')
        self.assertEqual(seat.interval.start_s, track.interval.end_s)
        self.assertEqual(seat.target_world_v1[2], 0)
        self.assertLess(track.curve.end_value[2], track.curve.start_value[2])

    def test_planted_kneel_folds_before_lowering_and_restores_the_sole(self):
        root = Path(__file__).parent / 'fixtures' / 'support_transfers' / 'v1' / 'demo'
        profile = c.loads(c.AvatarProfile, (root / 'support.transfer-profile.json').read_text())
        entry = c.loads(c.MotionStateSnapshot, (root / 'support.transfer-entry.json').read_text())
        measured = {item.control_id: item for item in entry.measured_controls}
        for item in self.entry.measured_controls:
            if item.control_id in measured:
                measured[item.control_id] = item
        values = {key: item.value for key, item in measured.items()}
        soles = ('left.sole', 'right.sole')
        anchors = tuple(c.ContactAnchor(sole, 'floor', (*values[sole + '.position'][:2], 0), 'world', 'metre')
                        for sole in soles)
        entry = replace(entry, root_transform=self.entry.root_transform, measured_controls=tuple(measured.values()),
                        active_contacts=soles, contact_anchors=anchors)
        motion = compile_support(profile, entry, 'body.kneel_rise', {'route': 'planted_to_knee', 'side': 'left'})
        controls = {track.control_id for track in motion.tracks}
        self.assertTrue(has_floor_body_transition(motion, controls))
        pelvis = [track for track in motion.tracks if track.control_id == 'pelvis.position']
        descent = next(track for track in pelvis if track.curve.end_value[2] < track.curve.start_value[2])
        folded = next(track for track in motion.tracks
                      if track.control_id == 'left.knee.flexion' and track.interval.end_s == descent.interval.start_s)
        released, restored = sorted((event for event in motion.contact_events if event.anchor_id == 'left.sole'),
                                    key=lambda event: event.interval.start_s)
        knee = next(event for event in motion.contact_events if event.anchor_id == 'left.knee.support')
        self.assertGreater(folded.curve.end_value, values['left.knee.flexion'])
        self.assertLess(released.interval.end_s, folded.interval.end_s)
        self.assertEqual(descent.interval.end_s, knee.interval.start_s)
        self.assertLess(knee.interval.end_s, restored.interval.start_s)
        self.assertEqual(restored.target_world_v1, released.target_world_v1)

    def test_crawl_moves_each_support_once_and_leaves_three_held(self):
        root = Path(__file__).parent / 'fixtures' / 'support_transfers' / 'v1' / 'demo'
        profile = c.loads(c.AvatarProfile, (root / 'support.transfer-profile.json').read_text())
        entry = c.loads(c.MotionStateSnapshot, (root / 'support.transfer-entry.json').read_text())
        values = {item.control_id: item.value for item in entry.measured_controls}
        surfaces = (Surface(), Surface('palm-plane', .55))
        anchors = tuple(c.ContactAnchor(anchor, surfaces[anchor.endswith('.palm')].name,
                                       (*values[anchor + '.position'][:2], surfaces[anchor.endswith('.palm')].height),
                                       'world', 'metre') for anchor in CRAWL_ANCHORS)
        entry = replace(entry, active_contacts=CRAWL_ANCHORS, contact_anchors=anchors)
        motion = compile_support(profile, entry, 'body.crawl', {'lead': 'right'}, surfaces)
        validate_crawl_support(motion.contact_events, motion.duration_s)
        self.assertAlmostEqual(motion.duration_s, 4 * (18 + 8) / c.FPS)
        pelvis = sorted((track for track in motion.tracks if track.control_id == 'pelvis.position'),
                        key=lambda track: track.interval.start_s)
        forward = rotate(entry.root_transform.orientation, (0, 1, 0))
        lateral = (forward[1], -forward[0])
        origin = pelvis[0].curve.start_value
        offsets = [sum((track.curve.end_value[i] - origin[i]) * lateral[i] for i in range(2))
                   for track in pelvis]
        self.assertLess(min(offsets), -.008)
        self.assertGreater(max(offsets), .008)
        self.assertAlmostEqual(offsets[-1], 0.)
        missing = tuple(event for event in motion.contact_events if event.anchor_id != 'right.palm')
        with self.assertRaises(c.MotionContractError):
            validate_crawl_support(missing, motion.duration_s)
        for anchor in anchors:
            old, new = sorted((event for event in motion.contact_events if event.anchor_id == anchor.anchor_id),
                              key=lambda event: event.interval.start_s)
            self.assertEqual(old.target_world_v1, anchor.position)
            self.assertLess(old.interval.end_s, new.interval.start_s)
            self.assertNotEqual(new.target_world_v1, anchor.position)
        for frame in range(round(motion.duration_s * c.FPS) + 1):
            time = frame / c.FPS
            held = [event for event in motion.contact_events
                    if event.interval.start_s + event.acquire_s <= time + 1e-8
                    and time <= event.interval.end_s - event.release_s + 1e-8]
            self.assertGreaterEqual(len(held), 3)

    def test_knee_crawl_requires_the_measured_knee_contacts(self):
        root = Path(__file__).parent / 'fixtures' / 'support_transfers' / 'v1' / 'demo'
        profile = c.loads(c.AvatarProfile, (root / 'support.transfer-profile.json').read_text())
        entry = c.loads(c.MotionStateSnapshot, (root / 'support.transfer-entry.json').read_text())
        values = {item.control_id: item.value for item in entry.measured_controls}
        anchors = tuple(c.ContactAnchor(key, 'floor', (*values[key + '.position'][:2], 0), 'world', 'metre')
                        for key in KNEE_CRAWL_ANCHORS)
        root_transform = replace(entry.root_transform, orientation=angle_rotation(pitch=85))
        entry = replace(entry, root_transform=root_transform, active_contacts=KNEE_CRAWL_ANCHORS,
                        contact_anchors=anchors)
        motion = compile_support(profile, entry, 'body.crawl', {'support': 'hands_knees'})
        validate_crawl_support(motion.contact_events, motion.duration_s)
        self.assertEqual({event.anchor_id for event in motion.contact_events}, set(KNEE_CRAWL_ANCHORS))
        self.assertTrue(all(any(track.control_id == anchor + '.position' for track in motion.tracks)
                            for anchor in KNEE_CRAWL_ANCHORS[2:]))
        with self.assertRaises(c.MotionContractError) as error:
            compile_support(profile, entry, 'body.crawl', {'support': 'hands_feet'})
        self.assertEqual(error.exception.code, 'ENTRY_MISMATCH')
