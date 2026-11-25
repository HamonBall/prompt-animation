"""Check foundation candidates through the public composer and compiler."""

from dataclasses import replace
import unittest

from avatar_app.motion import Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import compile_recipe, value_error
from avatar_app.movement_library.composer import compose_recipe
from avatar_app.movement_library.coordinated import RUN_ARM_CONTROLS, has_running_support, has_seated_extension
from avatar_app.movement_library.patterns import has_alternating_step_support
from avatar_app.movement_library.recipes import compile_walk_sequence, foundation_recipe
from test_recipe_composition import context


class FoundationRecipeTests(unittest.TestCase):
    def test_run_alternates_single_landings_and_finishes_with_both_soles(self):
        profile, entry, catalog = context('demo', 'step-left')
        for count in (2, 4):
            with self.subTest(count=count):
                surfaces = (Surface(),)
                recipe = foundation_recipe('run', entry, profile, steps=count, run_height_m=1.65,
                                           run_arms=count == 4)
                resolved = compose_recipe(recipe, entry, profile, surfaces, catalog)
                motion = compile_recipe(resolved, entry, profile, catalog=catalog)
                controls = {track.control_id for track in motion.tracks}
                self.assertTrue(has_running_support(motion, controls))
                self.assertEqual(controls & RUN_ARM_CONTROLS, RUN_ARM_CONTROLS if count == 4 else set())
                landings = sorted((event for event in motion.contact_events if event.acquire_s),
                                  key=lambda event: event.interval.start_s)
                self.assertEqual([event.anchor_id for event in landings],
                                 ['left.sole', 'right.sole'] * (count // 2) + ['left.sole'])
                self.assertEqual({event.anchor_id for event in landings[-2:]
                                  if event.interval.end_s == motion.duration_s}, {'left.sole', 'right.sole'})

    def test_standing_chair_tracks_descent_before_pelvis_support(self):
        profile, entry, catalog = context('demo', 'standing-to-seated')
        seat = Surface('seat', .45, (0., -.34), (.6, .45))
        surfaces = (Surface(), seat)
        recipe = foundation_recipe('sit_seat', entry, profile, chair_descent=True)
        resolved = compose_recipe(recipe, entry, profile, surfaces, catalog)
        motion = compile_recipe(resolved, entry, profile, surfaces=surfaces, catalog=catalog)
        pelvis, = [event for event in motion.contact_events if event.anchor_id == 'pelvis.support']
        descent, = [track for track in motion.tracks if track.control_id == 'pelvis.position']
        self.assertEqual(pelvis.interval.start_s, descent.interval.end_s)
        self.assertGreater(pelvis.acquire_s, 0)
        self.assertEqual(motion.duration_s, 4.5)
        directed = [track.curve.end_value for track in motion.tracks
                    if track.control_id.endswith('.forearm.direction')]
        self.assertEqual(len(directed), 2)
        self.assertEqual(*directed)
        self.assertEqual(pelvis.target_world_v1[2], seat.height)
        self.assertTrue(all(event.surface_id == 'floor' and event.interval.start_s == 0
                            for event in motion.contact_events if event.anchor_id != 'pelvis.support'))

    def test_compact_jump_arm_tracks_preserve_the_bilateral_flight_interval(self):
        profile, entry, catalog = context('demo', 'takeoff-land-push-off-neutral')
        recipe = foundation_recipe('jump', entry, profile, compact_jump=True)
        resolved = compose_recipe(recipe, entry, profile, (Surface(),), catalog)
        motion = compile_recipe(resolved, entry, profile, catalog=catalog)
        self.assertEqual(motion.duration_s, 2.6)
        self.assertEqual({track.control_id for track in motion.tracks if 'jump_arms' in track.source_instance_ids},
                         {'left.upper_arm.orientation', 'right.upper_arm.orientation'})
        self.assertEqual(len(motion.contact_events), 4)
        self.assertTrue(all(event.interval.end_s <= 1. or event.interval.start_s >= 1.6
                            for event in motion.contact_events))

    def test_wave_resolves_side_count_speed_and_measured_return(self):
        for rig, side, waves, tempo in (('demo', 'left', 4, 1.25), ('mixamo', 'right', 1, 1.)):
            with self.subTest(rig=rig):
                profile, entry, catalog = context(rig, 'step-left')
                recipe = foundation_recipe('wave', entry, profile, side=side, waves=waves, tempo=tempo)
                resolved = compose_recipe(recipe, entry, profile, (Surface(),), catalog)
                motion = compile_recipe(resolved, entry, profile, catalog=catalog)
                self.assertEqual(motion.entry_snapshot, entry)
                self.assertLess(abs(motion.duration_s - (3. + 1.3 * waves) * tempo), 1 / c.FPS)
                self.assertTrue(all(track.control_id.startswith(side + '.') for track in motion.tracks))
                forearm = side + '.forearm.direction'
                baseline = next(item.value for item in entry.measured_controls if item.control_id == forearm)
                targets = [track.curve.end_value for track in motion.tracks if track.control_id == forearm]
                lift, peak = targets[:2]
                self.assertNotEqual(lift, peak)
                self.assertEqual(targets, [lift, *([peak, lift] * waves), baseline])
                wrist = side + '.wrist.flexion'
                neutral = next(item.value for item in entry.measured_controls if item.control_id == wrist)
                wrist_swing = -15. if side == 'left' else 15.
                wrist_targets = [track.curve.end_value for track in motion.tracks if track.control_id == wrist]
                self.assertEqual(wrist_targets, [neutral, *([neutral + wrist_swing, neutral - wrist_swing] * waves), neutral])
                self.assertEqual({event.anchor_id for event in motion.contact_events}, {'left.sole', 'right.sole'})

    def test_legacy_distance_walk_closes_the_trailing_foot_without_pelvis_travel(self):
        profile, entry, _ = context('demo', 'step-left')
        _, continuations = compile_walk_sequence(entry, profile, (Surface(),),
                                                 steps=2, preset_height_m=1.65)
        closing = continuations[-2](entry)
        self.assertEqual(closing.entry_snapshot, entry)
        self.assertEqual(closing.duration_s, 1.4)
        pelvis = [track for track in closing.tracks if track.control_id == 'pelvis.position']
        self.assertTrue(pelvis)
        self.assertTrue(all(track.curve.start_value == track.curve.end_value for track in pelvis))
        landing, = [event for event in closing.contact_events if event.acquire_s]
        self.assertEqual(landing.anchor_id, 'left.sole')
        self.assertEqual(landing.interval.end_s, closing.duration_s)
        stance, = [event for event in closing.contact_events if event.anchor_id == 'right.sole']
        self.assertEqual(stance.interval, c.TimeInterval(0, closing.duration_s))

    def test_gait_arm_orientations_compose_with_one_authored_stance_change(self):
        profile, entry, _ = context('demo', 'step-left')
        _, continuations = compile_walk_sequence(entry, profile, (Surface(),), steps=2,
                                                 preset_height_m=1.65, arm_motion=True)
        step = continuations[0](entry)
        controls = {track.control_id for track in step.tracks}
        self.assertTrue({'left.upper_arm.orientation', 'right.upper_arm.orientation'} <= controls)
        self.assertEqual({event.anchor_id for event in step.contact_events}, {'left.sole', 'right.sole'})
        self.assertEqual(step.duration_s, 1.2)

    def test_walk_expands_registry_pattern_with_fixed_support_and_finite_steps(self):
        surfaces = (Surface(),)
        for rig in ('demo', 'mixamo'):
            for count in (2, 4):
                with self.subTest(rig=rig, count=count):
                    profile, entry, catalog = context(rig, 'step-left')
                    recipe = foundation_recipe('walk', entry, profile, steps=count)
                    resolved = compose_recipe(recipe, entry, profile, surfaces, catalog)
                    motion = compile_recipe(resolved, entry, profile, catalog=catalog)
                    self.assertTrue(has_alternating_step_support(
                        motion, {track.control_id for track in motion.tracks}))
                    landings = sorted((event for event in motion.contact_events if event.acquire_s),
                                      key=lambda event: event.interval.start_s)
                    self.assertEqual([event.anchor_id for event in landings],
                                     ['left.sole', 'right.sole'] * (count // 2))
                    entry_anchors = {anchor.anchor_id: anchor.position for anchor in entry.contact_anchors}
                    for event in landings[-2:]:
                        self.assertEqual(event.interval.end_s, motion.duration_s)
                        # An imported sole can begin slightly above the floor.
                        # Travel is horizontal and the landing target is on z=0.
                        self.assertAlmostEqual(value_error(entry_anchors[event.anchor_id][:2],
                                                           event.target_world_v1[:2]), count * .03, places=5)
                    self.assertTrue(all(source.source_instance_ids == ('foundation',)
                                        for source in motion.source_map))

        with self.assertRaises(c.MotionContractError) as error:
            foundation_recipe('walk', entry, profile, steps=3)
        self.assertEqual(error.exception.code, 'INVALID_PARAMETER')

    def test_jump_releases_and_reacquires_the_measured_soles(self):
        for rig in ('demo', 'mixamo'):
            for pose in ('neutral', 'turned-crouched'):
                with self.subTest(rig=rig, pose=pose):
                    profile, entry, catalog = context(rig, f'takeoff-land-push-off-{pose}')
                    recipe = foundation_recipe('jump', entry, profile)
                    resolved = compose_recipe(recipe, entry, profile, (Surface(),), catalog)
                    motion = compile_recipe(resolved, entry, profile, catalog=catalog)
                    self.assertEqual(motion.entry_snapshot, entry)
                    for anchor in entry.contact_anchors:
                        if anchor.anchor_id not in entry.active_contacts:
                            continue
                        release, landing = sorted(
                            (event for event in motion.contact_events if event.anchor_id == anchor.anchor_id),
                            key=lambda event: event.interval.start_s,
                        )
                        self.assertLess(release.interval.end_s, landing.interval.start_s)
                        self.assertEqual(landing.surface_id, anchor.surface_id)
                        self.assertGreater(landing.acquire_s, 0)
                        self.assertEqual(landing.interval.end_s, motion.duration_s)

    def test_floor_sit_acquires_pelvis_support_after_descent(self):
        for rig in ('demo', 'mixamo'):
            with self.subTest(rig=rig):
                profile, entry, catalog = context(rig, 'standing-to-seated')
                recipe = foundation_recipe('sit_floor', entry, profile)
                resolved = compose_recipe(recipe, entry, profile, (Surface(),), catalog)
                motion = compile_recipe(resolved, entry, profile, catalog=catalog)
                self.assertEqual(motion.entry_snapshot, entry)
                seat, = [event for event in motion.contact_events if event.anchor_id == 'pelvis.support']
                self.assertGreater(seat.interval.start_s, 0)
                self.assertEqual(seat.surface_id, 'floor')
                self.assertEqual(seat.interval.end_s, motion.duration_s)

    def test_floor_sit_can_move_both_arms_without_delaying_the_descent(self):
        profile, entry, catalog = context('demo', 'standing-to-seated')
        surfaces = (Surface(),)
        recipe = foundation_recipe('sit_floor', entry, profile, floor_sit_arms=True)
        resolved = compose_recipe(recipe, entry, profile, surfaces, catalog)
        motion = compile_recipe(resolved, entry, profile, catalog=catalog)
        self.assertEqual({item.interval.start_s for item in resolved.scheduled_instances}, {0})
        self.assertEqual(motion.entry_snapshot, entry)
        controls = {track.control_id for track in motion.tracks}
        self.assertTrue({f'{side}.{joint}' for side in ('left', 'right')
                         for joint in ('upper_arm.orientation', 'elbow.flexion')} <= controls)

    def test_requires_both_measured_floor_soles(self):
        for name, fixture in (('jump', 'takeoff-land-push-off-neutral'), ('sit_floor', 'standing-to-seated')):
            profile, entry, catalog = context('demo', fixture)
            entry = replace(entry, active_contacts=('right.sole',))
            with self.subTest(name=name), self.assertRaises(c.MotionContractError) as error:
                compose_recipe(foundation_recipe(name, entry, profile), entry, profile, (Surface(),), catalog)
            self.assertEqual(error.exception.code, 'ENTRY_MISMATCH')

    def test_seated_extension_releases_soles_before_moving_and_holds_pelvis(self):
        for rig in ('demo', 'mixamo'):
            with self.subTest(rig=rig):
                profile, entry, catalog = context(rig, 'seated-to-back')
                recipe = foundation_recipe('sit_extend', entry, profile)
                resolved = compose_recipe(recipe, entry, profile, (Surface(),), catalog)
                motion = compile_recipe(resolved, entry, profile, catalog=catalog)
                controls = {track.control_id for track in motion.tracks}
                self.assertTrue(has_seated_extension(motion, controls))
                pelvis_only = replace(entry, active_contacts=('pelvis.support',))
                with self.assertRaises(c.MotionContractError) as error:
                    compose_recipe(recipe, pelvis_only, profile, (Surface(),), catalog)
                self.assertEqual(error.exception.code, 'ENTRY_MISMATCH')

    def test_lie_back_transfers_measured_floor_seat_support_to_the_back(self):
        for rig in ('demo', 'mixamo'):
            with self.subTest(rig=rig):
                profile, entry, catalog = context(rig, 'seated-to-back')
                recipe = foundation_recipe('lie_back', entry, profile)
                resolved = compose_recipe(recipe, entry, profile, (Surface(),), catalog)
                motion = compile_recipe(resolved, entry, profile, catalog=catalog)
                self.assertEqual(motion.entry_snapshot, entry)
                events = {event.anchor_id: event for event in motion.contact_events}
                self.assertEqual(set(events), {'left.sole', 'right.sole', 'pelvis.support', 'back.support'})
                self.assertGreater(events['pelvis.support'].release_s, 0)
                back = events['back.support']
                self.assertGreater(back.interval.start_s, events['pelvis.support'].interval.end_s)
                self.assertEqual(back.surface_id, 'floor')
                self.assertEqual(back.interval.end_s, motion.duration_s)

                standing = replace(entry, active_contacts=('left.sole', 'right.sole'))
                with self.assertRaises(c.MotionContractError) as error:
                    compose_recipe(recipe, standing, profile, (Surface(),), catalog)
                self.assertEqual(error.exception.code, 'ENTRY_MISMATCH')

    def test_chair_seat_requires_a_resolved_surface_under_the_measured_pelvis(self):
        for rig in ('demo', 'mixamo'):
            with self.subTest(rig=rig):
                profile, entry, catalog = context(rig, 'prepared-seat')
                point = next(item.value for item in entry.measured_controls
                             if item.control_id == 'pelvis.support.position')
                seat = Surface('seat', point[2] - .04, point[:2], (.24, .24))
                recipe = foundation_recipe('sit_seat', entry, profile)
                surfaces = (Surface(), seat)
                resolved = compose_recipe(recipe, entry, profile, surfaces, catalog)
                motion = compile_recipe(resolved, entry, profile, surfaces=surfaces, catalog=catalog)
                pelvis, = [event for event in motion.contact_events if event.anchor_id == 'pelvis.support']
                self.assertEqual((pelvis.surface_id, pelvis.target_world_v1), ('seat', (*point[:2], seat.height)))
                self.assertEqual(motion.entry_snapshot, entry)

                outside = replace(seat, center=(point[0] + .3, point[1]))
                for candidate, code in (
                    ((), 'UNRESOLVED_SURFACE'),
                    ((replace(seat, height=seat.height - .2),), 'ENTRY_MISMATCH'),
                    ((outside,), 'INVALID_PARAMETER'),
                ):
                    with self.subTest(code=code), self.assertRaises(c.MotionContractError) as error:
                        compose_recipe(recipe, entry, profile, (Surface(), *candidate), catalog)
                    self.assertEqual(error.exception.code, code)

                moved = replace(seat, height=seat.height + .01)
                with self.assertRaises(c.MotionContractError) as error:
                    compile_recipe(resolved, entry, profile, surfaces=(Surface(), moved), catalog=catalog)
                self.assertEqual(error.exception.code, 'ENTRY_MISMATCH')
