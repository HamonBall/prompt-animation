from dataclasses import replace
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import ExecutionCursor, prepare_fragment, sample_motion, value_error
from avatar_app.movement_library.patterns import (
    alternate_fragments, has_alternating_step_support, hold_fragment, mirror_fragment, overlap_fragments,
    phase_offset_fragments, repeat_fragment, step_pattern, stroke_pattern, synchronize_fragments,
    torso_pattern, transition_fragment, verify_translation_loop,
)
from avatar_app.motion import Surface


FIXTURES = Path(__file__).parent / 'fixtures/coordinated_body_moves/v1'


def load_case(case):
    directory = FIXTURES / case
    return tuple(c.loads(record, (directory / f'{name}.json').read_text(encoding='utf-8'))
                 for name, record in (('fragment', c.MotionFragment), ('entry', c.MotionStateSnapshot),
                                      ('profile', c.AvatarProfile)))


def samples(fragment, entry, profile):
    motion = prepare_fragment(fragment, entry, profile)
    cursor = ExecutionCursor()
    controls = {value.control_id: value for value in entry.measured_controls}
    state = entry
    frames = []
    for i in range(math.ceil(motion.duration_s * c.FPS) + 1):
        frame = sample_motion(motion, min(i / c.FPS, motion.duration_s), state, cursor)
        frames.append(frame)
        controls.update((value.control_id, value) for value in frame.controls)
        state = replace(state, measured_controls=tuple(controls.values()))
    return frames


class TimingPatternTests(unittest.TestCase):
    def setUp(self):
        self.fragment, self.entry, self.profile = load_case('demo/lower-rise-neutral')

    def repeat(self, count, fragment=None):
        return repeat_fragment(fragment or self.fragment, count, entry=self.entry, profile=self.profile)

    def reject(self, code, count, fragment=None):
        with self.assertRaises(c.MotionContractError) as raised:
            self.repeat(count, fragment)
        self.assertEqual(raised.exception.code, code)

    def test_repeat_preserves_poses_and_planted_anchors_on_both_profiles(self):
        for case in ('demo/lower-rise-neutral', 'mixamo/lower-rise-turned-crouched'):
            fragment, entry, profile = load_case(case)
            expected = samples(fragment, entry, profile)
            frames = round(fragment.duration_s * c.FPS)
            for count in (1, 2, 4):
                with self.subTest(case=case, count=count):
                    repeated = repeat_fragment(fragment, count, entry=entry, profile=profile)
                    self.assertEqual(repeated.duration_s, count * fragment.duration_s)
                    self.assertEqual(len(repeated.source_instance_ids), count)
                    self.assertEqual({e.interval for e in repeated.contact_events},
                                     {c.TimeInterval(0, repeated.duration_s)})
                    actual = samples(repeated, entry, profile)
                    self.assertEqual(len(actual), frames * count + 1)
                    for i, sample in enumerate(actual):
                        baseline = expected[i % frames]
                        self.assertEqual({e.anchor_id: e.target_world_v1 for e in sample.active_contacts},
                                         {e.anchor_id: e.target_world_v1 for e in baseline.active_contacts})
                        for value, original in zip(sample.controls, baseline.controls, strict=True):
                            self.assertEqual(value.control_id, original.control_id)
                            if isinstance(value.value, tuple):
                                for a, b in zip(value.value, original.value, strict=True):
                                    self.assertAlmostEqual(a, b, places=9)
                            else:
                                self.assertAlmostEqual(value.value, original.value, places=9)

    def test_finite_nested_repeat_has_stable_ids_and_retains_original_provenance(self):
        first = self.repeat(2)
        nested = self.repeat(2, first)
        self.assertEqual(nested, self.repeat(2, first))
        self.assertEqual(len(nested.source_instance_ids), 4)
        self.assertEqual(nested.tracks[:len(first.tracks)], first.tracks)
        self.assertEqual(nested.phase_landmarks[:len(first.phase_landmarks)], first.phase_landmarks)
        self.assertEqual(nested.goals[:len(first.goals)], first.goals)
        self.assertTrue(all(self.fragment.source_instance_ids[0] in track.source_instance_ids
                            for track in nested.tracks))
        self.assertIsNone(prepare_fragment(nested, self.entry, self.profile).loop)

    def test_reject_count_and_expanded_duration_instance_and_track_budgets(self):
        for count in (0, -1, True, 1.5):
            self.reject('INVALID_PARAMETER', count)
        self.reject('RESOURCE_LIMIT', c.MAX_INSTANCES + 1)
        self.reject('RESOURCE_LIMIT', 2, replace(self.fragment, duration_s=31))
        sources = tuple(f'instance.{i}' for i in range(c.MAX_INSTANCES))
        crowded = replace(self.fragment, source_instance_ids=self.fragment.source_instance_ids + sources[1:])
        self.reject('RESOURCE_LIMIT', 2, crowded)
        track = self.fragment.tracks[0]
        tracks = tuple(replace(track, track_id=f'track.{i}', control_id=f'control.{i}')
                       for i in range(c.MAX_TRACKS))
        self.reject('RESOURCE_LIMIT', 2, replace(self.fragment, tracks=tracks))

    def test_repeat_rejects_expanded_contact_phase_goal_and_source_map_budgets(self):
        event, goal, track = self.fragment.contact_events[0], self.fragment.goals[0], self.fragment.tracks[0]
        contacts = tuple(replace(event, event_id=f'event.{i}', anchor_id=f'anchor.{i}')
                         for i in range(c.MAX_CONTACTS // 2 + 1))
        phases = tuple(c.PhaseLandmark(f'phase.{i}', 0) for i in range(c.MAX_INSTANCES // 2 + 1))
        goals = tuple(replace(goal, goal_id=f'goal.{i}') for i in range(c.MAX_TRACKS // 2 + 1))
        total_budget_slice = (c.MAX_TRACKS + c.MAX_CONTACTS) // 6 + 1
        tracks = tuple(replace(track, track_id=f'track.{i}', control_id=f'control.{i}')
                       for i in range(total_budget_slice))
        with patch('avatar_app.movement_library.patterns.prepare_fragment') as prepare:
            for fields in ({'contact_events': contacts}, {'phase_landmarks': phases}, {'goals': goals},
                           {'tracks': tracks, 'contact_events': contacts[:total_budget_slice],
                            'goals': goals[:total_budget_slice]}):
                with self.subTest(fields=tuple(fields)):
                    self.reject('RESOURCE_LIMIT', 2, replace(self.fragment, **fields))
            prepare.assert_not_called()

    def test_reject_open_pose_and_lost_support_at_seam(self):
        fragment, entry, profile = load_case('demo/step-left')
        with self.assertRaises(c.MotionContractError) as raised:
            repeat_fragment(fragment, 2, entry=entry, profile=profile)
        self.assertEqual(raised.exception.code, 'ENTRY_MISMATCH')
        contacts = self.fragment.contact_events
        self.reject('ENTRY_MISMATCH', 2, replace(self.fragment,
                    contact_events=(replace(contacts[0], release_s=.1), *contacts[1:])))

    def test_hold_keeps_terminal_targets_anchors_and_goals(self):
        fragment = hold_fragment(self.fragment, .4, entry=self.entry, profile=self.profile)
        original = samples(self.fragment, self.entry, self.profile)
        extended = samples(fragment, self.entry, self.profile)
        self.assertAlmostEqual(fragment.duration_s - self.fragment.duration_s, .4)
        self.assertEqual(len(extended) - len(original), 12)
        for frame in extended[len(original):]:
            self.assertEqual(frame.controls, original[-1].controls)
            self.assertEqual({event.anchor_id for event in frame.active_contacts}, set(self.entry.active_contacts))
            self.assertEqual(frame.expected_goals, extended[-1].expected_goals)
        self.assertEqual(fragment.source_instance_ids, self.fragment.source_instance_ids)
        with self.assertRaises(c.MotionContractError) as raised:
            hold_fragment(self.fragment, 60, entry=self.entry, profile=self.profile)
        self.assertEqual(raised.exception.code, 'RESOURCE_LIMIT')

    def test_timing_accepts_exact_duration_and_repeat_limits(self):
        start = next(value for value in self.entry.measured_controls if value.control_id == 'head.yaw')
        kwargs = dict(entry=self.entry, profile=self.profile)
        arguments = dict(instance_id='timing.limit', **kwargs)
        shortest = transition_fragment((start,), 1e-9, **arguments)
        longest = transition_fragment((start,), c.MAX_SECONDS, **arguments)
        self.assertEqual(math.ceil(longest.duration_s * c.FPS) + 1, c.MAX_SAMPLES)
        self.assertEqual(shortest.duration_s, 1e-9)
        held = hold_fragment(self.fragment, c.MAX_SECONDS - self.fragment.duration_s, **kwargs)
        self.assertEqual(held.duration_s, c.MAX_SECONDS)
        self.assertTrue(all(event.interval.end_s == c.MAX_SECONDS for event in held.contact_events))
        short = transition_fragment((start,), .1, **arguments)
        repeated = repeat_fragment(replace(short, phase_landmarks=()), c.MAX_INSTANCES, **kwargs)
        self.assertEqual(len(repeated.source_instance_ids), c.MAX_INSTANCES)
        self.assertAlmostEqual(repeated.duration_s, c.MAX_INSTANCES * .1)

    def test_transition_from_measured_state(self):
        for case in ('demo/lower-rise-neutral', 'mixamo/lower-rise-turned-crouched'):
            _, entry, profile = load_case(case)
            start = next(value for value in entry.measured_controls if value.control_id == 'head.yaw')
            target = replace(start, value=start.value + 5)
            kwargs = dict(instance_id='timing.transition', entry=entry, profile=profile)
            transition = transition_fragment((target,), 1., **kwargs)
            frames = samples(transition, entry, profile)
            self.assertEqual(frames[0].controls, (start,))
            self.assertEqual(frames[15].controls[0].value, start.value + 2.5)
            self.assertEqual(frames[-1].controls, (target,))
            for frame in frames:
                self.assertEqual({event.anchor_id for event in frame.active_contacts}, set(entry.active_contacts))
            for value, duration in ((target, 0), (replace(target, value=1000), 1.)):
                with self.assertRaises(c.MotionContractError) as raised:
                    transition_fragment((value,), duration, **kwargs)
                self.assertEqual(raised.exception.code, 'INVALID_PARAMETER')

    def test_overlap_accepts_only_compatible_ownership_and_support(self):
        measured = {value.control_id: value for value in self.entry.measured_controls}

        def movement(id, duration):
            target = measured[id]
            return transition_fragment((replace(target, value=target.value + 5),), duration,
                                       instance_id=id, entry=self.entry, profile=self.profile)

        head = movement('head.yaw', 1.)
        arm = movement('left.elbow.flexion', 1.4)
        args = dict(fragment_id='timing.overlap', entry=self.entry, profile=self.profile)
        fragment = overlap_fragments(head, arm, **args)
        self.assertEqual(fragment, overlap_fragments(head, arm, **args))
        self.assertEqual(fragment.duration_s, 1.4)
        self.assertEqual(fragment.source_instance_ids, ('head.yaw', 'left.elbow.flexion'))
        frames = samples(fragment, self.entry, self.profile)
        for frame in frames[30:]:
            values = {value.control_id: value.value for value in frame.controls}
            self.assertAlmostEqual(values['head.yaw'], measured['head.yaw'].value + 5)
            self.assertEqual({event.anchor_id for event in frame.active_contacts}, set(self.entry.active_contacts))
        altered_contacts = (replace(arm.contact_events[0], clearance_m=.01), *arm.contact_events[1:])
        for incompatible in (movement('head.pitch', 1.), replace(arm, contact_events=altered_contacts)):
            with self.assertRaises(c.MotionContractError) as raised:
                overlap_fragments(head, incompatible, **args)
            self.assertEqual(raised.exception.code, 'CONSTRAINT_CONFLICT')

    def test_alignment_signed_phase_and_alternating_duration(self):
        measured = {value.control_id: value for value in self.entry.measured_controls}

        def movement(id, duration):
            target = replace(measured[id], value=measured[id].value + 5)
            return transition_fragment((target,), duration, instance_id=id, entry=self.entry, profile=self.profile)

        first, second = movement('left.elbow.flexion', 1.), movement('right.elbow.flexion', 2.)
        args = dict(fragment_id='timing.pair', entry=self.entry, profile=self.profile)
        aligned = synchronize_fragments(first, 'arrival', second, 'arrival', **args)
        self.assertEqual([track.interval for track in aligned.tracks], [c.TimeInterval(1, 2), c.TimeInterval(0, 2)])
        for offset, starts in ((.5, (0, 1)), (-.5, (1, 0))):
            shifted = phase_offset_fragments(first, second, offset, **args)
            self.assertEqual(tuple(track.interval.start_s for track in shifted.tracks), starts)
            self.assertEqual(shifted.duration_s, max(starts[0] + 1, starts[1] + 2))
            self.assertTrue(all(event.interval == c.TimeInterval(0, shifted.duration_s)
                                for event in shifted.contact_events))
        pair = alternate_fragments(first, second, 1, **args)
        self.assertEqual([track.interval for track in pair.tracks], [c.TimeInterval(0, 1), c.TimeInterval(1, 3)])
        with self.assertRaises(c.MotionContractError) as raised:
            synchronize_fragments(first, 'missing', second, 'arrival', **args)
        self.assertEqual(raised.exception.code, 'UNKNOWN_ID')
        for offset, starts in ((1., (0, 2)), (-1., (2, 0))):
            shifted = phase_offset_fragments(first, second, offset, **args)
            self.assertEqual(tuple(track.interval.start_s for track in shifted.tracks), starts)
        for offset in (-1.01, 1.01, float('nan'), True):
            with self.subTest(offset=offset), self.assertRaises(c.MotionContractError) as raised:
                phase_offset_fragments(first, second, offset, **args)
            self.assertEqual(raised.exception.code, 'INVALID_PARAMETER')

    def test_mirror_applies_calibrated_sign_frames_and_swaps_contact_ids(self):
        measured = {value.control_id: value for value in self.entry.measured_controls}
        initial = measured['left.elbow.flexion']
        other = measured['right.elbow.flexion']
        # Explicit starts require a compatible destination entry.
        entry = replace(self.entry, measured_controls=tuple(
            replace(value, value=initial.value) if value.control_id == other.control_id else value
            for value in self.entry.measured_controls))
        targets = (replace(initial, value=initial.value + 5), replace(measured['head.yaw'], value=5))
        original = transition_fragment(targets, 1., instance_id='mirror.source', entry=entry, profile=self.profile)
        mirrored = mirror_fragment(original, fragment_id='mirror.target', entry=entry, profile=self.profile)
        self.assertEqual(mirrored.source_instance_ids, original.source_instance_ids)
        self.assertEqual(tuple(event.anchor_id for event in mirrored.contact_events),
                         tuple(reversed([event.anchor_id for event in original.contact_events])))
        end = {value.control_id: value for value in samples(mirrored, entry, self.profile)[-1].controls}
        self.assertEqual(end[other.control_id], replace(other, value=initial.value + 5))
        self.assertAlmostEqual(end['head.yaw'].value, -5)

    def test_mirror_rejects_a_control_without_a_calibrated_partner(self):
        target = next(value for value in self.entry.measured_controls if value.control_id == 'left.elbow.plane')
        original = transition_fragment((target,), 1., instance_id='mirror.unavailable',
                                       entry=self.entry, profile=self.profile)
        with self.assertRaises(c.MotionContractError) as raised:
            mirror_fragment(original, fragment_id='mirror.invalid', entry=self.entry, profile=self.profile)
        self.assertEqual(raised.exception.code, 'MISSING_CAPABILITY')

    def test_strokes_keep_finite_cycles_and_separate_arm_ownership(self):
        for mode in ('synchronized', 'alternating'):
            with self.subTest(mode=mode):
                fragment = stroke_pattern(mode, {'duration_s': 1., 'hold_s': .1}, 2,
                                          fragment_id='stroke.test', entry=self.entry,
                                          profile=self.profile, surfaces=(Surface(),))
                starts = {side: min(track.interval.start_s for track in fragment.tracks
                                    if track.control_id == side + '.hand.position'
                                    and track.curve.kind == 'transition') for side in ('left', 'right')}
                self.assertEqual(starts['left'], 0)
                self.assertAlmostEqual(starts['right'], 0 if mode == 'synchronized' else 1.6)
                self.assertEqual(len(fragment.source_instance_ids), 4)
                motion = prepare_fragment(fragment, self.entry, self.profile)
                self.assertIsNone(motion.loop)

    def test_stroke_and_torso_parameter_corners_author_on_both_profiles(self):
        corners = (
            (stroke_pattern, 'synchronized', {'amplitude_m': 0, 'duration_s': 1, 'hold_s': 0},
             {'amplitude_m': .16, 'duration_s': 3, 'hold_s': 1}, 'amplitude_m', .161),
            (stroke_pattern, 'alternating', {'amplitude_m': 0, 'duration_s': 1, 'hold_s': 0},
             {'amplitude_m': .16, 'duration_s': 3, 'hold_s': 1}, 'duration_s', 3.01),
            (torso_pattern, 'sway', {'angle': -20, 'duration_s': .8, 'hold_s': 0},
             {'angle': 20, 'duration_s': 3, 'hold_s': 1}, 'angle', 20.01),
            (torso_pattern, 'undulation', {'angle': -20, 'duration_s': .8, 'hold_s': 0},
             {'angle': 20, 'duration_s': 3, 'hold_s': 1}, 'hold_s', 1.01),
        )
        for case in ('demo/lower-rise-neutral', 'mixamo/lower-rise-turned-crouched'):
            _, entry, profile = load_case(case)
            kwargs = dict(fragment_id='range.probe', entry=entry, profile=profile, surfaces=(Surface(),))
            for build, mode, minimum, maximum, name, outside in corners:
                with self.subTest(case=case, mode=mode):
                    low = build(mode, minimum, 1, **kwargs)
                    high = build(mode, maximum, 1, **kwargs)
                    self.assertLess(low.duration_s, high.duration_s)
                    with self.assertRaises(c.MotionContractError) as raised:
                        build(mode, {**maximum, name: outside}, 1, **kwargs)
                    self.assertEqual(raised.exception.code, 'INVALID_PARAMETER')

    def test_supported_sway_and_phased_undulation_with_optional_arm(self):
        for mode, side in (('sway', None), ('undulation', None), ('undulation', 'right')):
            with self.subTest(mode=mode, side=side):
                fragment = torso_pattern(mode, {'angle': 5}, 2, fragment_id='torso.test',
                                         entry=self.entry, profile=self.profile, surfaces=(Surface(),),
                                         follow_through=side)
                frames = samples(fragment, self.entry, self.profile)
                self.assertEqual(len(fragment.source_instance_ids), 4 if side else 2)
                self.assertEqual({event.anchor_id for event in frames[-1].active_contacts}, set(self.entry.active_contacts))
                axes = {value.control_id for value in frames[-1].controls}
                self.assertIn('torso.roll' if mode == 'sway' else 'torso.pitch', axes)
                self.assertEqual('right.upper_arm.orientation' in axes, bool(side))
                if side:
                    opening = next(track for track in fragment.tracks if track.control_id == 'right.upper_arm.orientation')
                    self.assertEqual(opening.interval.start_s, 0.)
                    self.assertEqual(opening.curve.kind, 'hold')
                for target in frames[-1].controls:
                    value = next(value for value in self.entry.measured_controls if value.control_id == target.control_id)
                    control = next(control for control in self.profile.controls if control.id == target.control_id)
                    self.assertEqual((target.frame, target.unit), (value.frame, value.unit))
                    self.assertLess(value_error(target.value, value.value, control.value_shape), 1e-5)

    def test_undulation_reports_unavailable_arm_follow_through(self):
        capability = 'measure.left.upper_arm.orientation'
        removed = {control.id for control in self.profile.controls if control.capability == capability}
        self.assertTrue(removed)
        profile = replace(self.profile, controls=tuple(control for control in self.profile.controls
                                                      if control.id not in removed),
                          capabilities=tuple(value for value in self.profile.capabilities if value != capability))
        entry = replace(self.entry, measured_controls=tuple(value for value in self.entry.measured_controls
                                                           if value.control_id not in removed))
        kwargs = dict(fragment_id='torso.optional', entry=entry, profile=profile, surfaces=(Surface(),))
        torso_pattern('undulation', {'angle': 5}, 1, **kwargs)
        with self.assertRaises(c.MotionContractError) as raised:
            torso_pattern('undulation', {'angle': 5}, 1, follow_through='left', **kwargs)
        self.assertEqual(raised.exception.code, 'MISSING_CAPABILITY')

    def test_steps_alternate_without_dropping_both_supports(self):
        _, entry, profile = load_case('demo/step-left')
        for lead, count in (('left', 2), ('right', 4)):
            with self.subTest(lead=lead, count=count):
                fragment = step_pattern(lead, {'distance_m': .06}, count, fragment_id='steps.test',
                                        entry=entry, profile=profile, surfaces=(Surface(),))
                motion = prepare_fragment(fragment, entry, profile)
                controls = {track.control_id for track in motion.tracks}
                self.assertTrue(has_alternating_step_support(motion, controls))
                self.assertFalse(has_alternating_step_support(motion, controls | {'head.yaw'}))
                self.assertEqual(len(motion.contact_events), count + 2)
                stance = {anchor.anchor_id: anchor.position for anchor in entry.contact_anchors}
                frames = samples(fragment, entry, profile)
                self.assertTrue(all(frame.active_contacts for frame in frames))
                self.assertEqual({event.anchor_id for event in frames[-1].active_contacts}, set(entry.active_contacts))
                for event in frames[-1].active_contacts:
                    self.assertAlmostEqual(math.dist(event.target_world_v1, stance[event.anchor_id]), .03 * count)

    def test_step_parameter_corners_require_a_reachable_entry(self):
        low = {'distance_m': .06, 'clearance_m': .04, 'phase_s': .7}
        high = {'distance_m': .16, 'clearance_m': .09, 'phase_s': 1.4}
        for case in ('demo/step-left', 'mixamo/step-right'):
            with self.subTest(case=case):
                _, entry, profile = load_case(case)
                kwargs = dict(fragment_id='step.range', entry=entry, profile=profile, surfaces=(Surface(),))
                self.assertAlmostEqual(step_pattern('left', low, 1, **kwargs).duration_s, 1.8)
                self.assertAlmostEqual(step_pattern('right', high, 4, **kwargs).duration_s, 12.8)
                with self.assertRaises(c.MotionContractError) as raised:
                    step_pattern('right', high, 5, **kwargs)
                self.assertEqual(raised.exception.code, 'INVALID_PARAMETER')
        with self.assertRaises(c.MotionContractError) as raised:
            step_pattern('left', low, 1, fragment_id='step.range', entry=self.entry,
                         profile=self.profile, surfaces=(Surface(),))
        self.assertEqual(raised.exception.control_id, 'left.foot.position')

    def test_landing_height_does_not_accumulate_when_a_sole_swings_again(self):
        _, entry, profile = load_case('mixamo/step-right')
        self.assertTrue(any(abs(anchor.position[2]) > .001 for anchor in entry.contact_anchors
                            if anchor.anchor_id in entry.active_contacts))
        fragment = step_pattern('right', {'distance_m': .16, 'clearance_m': .09, 'phase_s': 1.4}, 4,
                                fragment_id='step.floor-height', entry=entry, profile=profile, surfaces=(Surface(),))
        for side in ('left', 'right'):
            landings = [event for event in fragment.contact_events if event.anchor_id == f'{side}.sole'
                        and event.interval.start_s > 0]
            self.assertEqual([event.target_world_v1[2] for event in landings], [0., 0.])
            control = f'{side}.foot.position'
            land_tracks = [track for track in fragment.tracks if track.control_id == control
                           and any(track.interval.end_s == event.interval.start_s for event in landings)]
            self.assertEqual(len(land_tracks), 2)
            self.assertEqual(land_tracks[0].curve.end_value[2], land_tracks[1].curve.end_value[2])

    def test_loop_attaches_metadata_only_after_matching_seam(self):
        motion = prepare_fragment(self.fragment, self.entry, self.profile)
        times = (0, 1 / c.FPS, motion.duration_s - 1 / c.FPS, motion.duration_s)
        stationary = tuple(replace(self.entry, captured_time_s=time) for time in times)
        loop = c.LoopSpec(2, c.Transform((0., 0., 0.), (1., 0., 0., 0.), 'entry_body', 'metre'), 3., .01, 10.)
        verified, metrics = verify_translation_loop(motion, loop, self.profile, *stationary)
        self.assertEqual(verified.loop, loop)
        self.assertIsNone(motion.loop)
        self.assertLess(metrics['endpoint_m'], .001)
        traveling = replace(loop, per_cycle_root_transform=replace(loop.per_cycle_root_transform, position=(.06, 0., 0.)))
        with self.assertRaises(c.MotionContractError) as raised:
            verify_translation_loop(motion, traveling, self.profile, *stationary)
        self.assertEqual(raised.exception.code, 'ENTRY_MISMATCH')
        self.assertGreater(raised.exception.details['endpoint_m'], .05)


if __name__ == '__main__':
    unittest.main()
