from dataclasses import replace
import unittest

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.patterns import transition_fragment
from avatar_app.movement_library.styles import apply_robotic, apply_style, restyle, STYLE_REGISTRY
from avatar_app.movement_library.curves import ease_weight
from avatar_app.movement_library.joints import catalog_for_profile
from test_movement_patterns import load_case, samples


class RoboticStyleTests(unittest.TestCase):
    def setUp(self):
        _, self.entry, self.profile = load_case('demo/lower-rise-neutral')
        values = {v.control_id: v for v in self.entry.measured_controls}
        self.targets = tuple(replace(values[key], value=values[key].value + 5.)
                             for key in ('left.elbow.flexion', 'head.yaw'))
        self.source = transition_fragment(self.targets, 2., instance_id='style.source',
                                         entry=self.entry, profile=self.profile)

    def apply(self, fragment=None, intensity=.5, controls=('left.elbow.flexion',)):
        return apply_robotic(fragment or self.source, controls, entry=self.entry,
                             profile=self.profile, intensity=intensity)

    def test_zero_identity_and_invalid_inputs(self):
        self.assertIs(self.apply(intensity=0.).fragment, self.source)
        for intensity in (-.1, 1.1, True, float('nan'), float('inf')):
            with self.subTest(intensity=intensity), self.assertRaises(c.MotionContractError):
                self.apply(intensity=intensity)
        for controls in ((), ('absent',), ('head.yaw', 'head.yaw'), ['head.yaw']):
            with self.assertRaises(c.MotionContractError):
                self.apply(controls=controls)

    def test_locality_provenance_endpoints_pause_and_determinism(self):
        original = samples(self.source, self.entry, self.profile)
        for intensity in (.5, 1.):
            styled = self.apply(intensity=intensity)
            self.assertEqual(styled, self.apply(intensity=intensity))
            self.assertEqual(styled.source_instance_ids, self.source.source_instance_ids)
            for field in ('duration_s', 'contact_events', 'phase_landmarks', 'goals'):
                self.assertEqual(getattr(styled.fragment, field), getattr(self.source, field))
            actual = samples(styled.fragment, self.entry, self.profile)
            self.assertEqual(actual[0].controls, original[0].controls)
            self.assertEqual(actual[-1].controls, original[-1].controls)
            pause_frames = round(2 * .2 * intensity * c.FPS)
            def value(frame, key):
                return next(v.value for v in frame.controls if v.control_id == key)
            for i, frame in enumerate(actual):
                self.assertEqual(value(frame, 'head.yaw'), value(original[i], 'head.yaw'))
                if i <= pause_frames:
                    self.assertEqual(value(frame, 'left.elbow.flexion'),
                                     value(original[0], 'left.elbow.flexion'))
            self.assertNotEqual(value(actual[15], 'left.elbow.flexion'),
                                value(original[15], 'left.elbow.flexion'))

    def test_conflicting_goal_stacking_and_binding_rejected(self):
        goal = c.GoalSpec('locked', 'request', self.targets[0], c.TimeInterval(.5, 1.), .01)
        with self.assertRaises(c.MotionContractError):
            self.apply(replace(self.source, goals=(goal,)))
        with self.assertRaises(c.MotionContractError):
            self.apply(self.apply().fragment)
        track = self.source.tracks[0]
        bound = replace(track, start_source='measured_entry',
                        curve=replace(track.curve, start_value=None))
        with self.assertRaises(c.MotionContractError):
            self.apply(replace(self.source, tracks=(bound,) + self.source.tracks[1:]))

    def test_unsupported_support_motion_and_identity_roundtrip(self):
        support, entry, profile = load_case('demo/lower-rise-neutral')
        with self.assertRaises(c.MotionContractError):
            apply_robotic(support, ('pelvis.position',), entry=entry, profile=profile)
        styled = self.apply().fragment
        self.assertEqual(c.loads(c.MotionFragment, c.dumps(styled)), styled)

    def test_continuous_timing_styles_and_legacy_curve_identity(self):
        for style in ('style.fluid', 'style.heavy', 'style.playful'):
            for amount in (0., .25, .5, 1.):
                timing = c.StyleTimingV1(style, amount)
                weights = [ease_weight(i / 100, 'smooth', timing) for i in range(101)]
                self.assertEqual((weights[0], weights[-1]), (0., 1.))
                self.assertEqual(weights, sorted(weights))
                if amount:
                    self.assertNotEqual(weights[25], ease_weight(.25, 'smooth'))
                else:
                    self.assertEqual(weights, [ease_weight(i / 100, 'smooth') for i in range(101)])
        curve = self.source.tracks[0].curve
        data = c.to_dict(curve)
        self.assertNotIn('style_timing', data)
        self.assertEqual(c.loads(c.CurveSpec, c.dumps(curve)), curve)
        data.pop('easing')
        with self.assertRaises(c.MotionContractError):
            c.from_dict(c.CurveSpec, data)

    def test_timing_styles_preserve_unselected_samples_and_edit_source(self):
        baseline = samples(self.source, self.entry, self.profile)
        for style in ('style.fluid', 'style.heavy', 'style.playful'):
            application = apply_style(self.source, style, ('left.elbow.flexion',),
                                      entry=self.entry, profile=self.profile)
            actual = samples(application.fragment, self.entry, self.profile)
            self.assertEqual(actual[0].controls, baseline[0].controls)
            self.assertEqual(actual[-1].controls, baseline[-1].controls)
            self.assertEqual(c.loads(c.StyledFragment, c.dumps(application)), application)
            for a, b in zip(actual, baseline):
                self.assertEqual(next(v for v in a.controls if v.control_id == 'head.yaw'),
                                 next(v for v in b.controls if v.control_id == 'head.yaw'))
            self.assertEqual(restyle(application, self.source, 0., entry=self.entry,
                                     profile=self.profile).fragment, self.source)
            with self.assertRaises(c.MotionContractError):
                restyle(application, replace(self.source, fragment_id='wrong'), 1.,
                        entry=self.entry, profile=self.profile)

    def test_amplitude_requires_optional_returning_excursion_and_preserves_endpoints(self):
        first = self.source.tracks[0]
        returning = replace(first, track_id='return', interval=c.TimeInterval(2., 4.),
                            curve=replace(first.curve, start_value=first.curve.end_value,
                                          end_value=first.curve.start_value))
        source = replace(self.source, duration_s=4., tracks=(first, returning))
        for style, scale in (('style.exaggerated', 1.25), ('style.tired', .75)):
            kwargs = dict(entry=self.entry, profile=self.profile, intensity=1.)
            with self.assertRaises(c.MotionContractError):
                apply_style(source, style, ('left.elbow.flexion',), **kwargs)
            result = apply_style(source, style, ('left.elbow.flexion',), amplitude_unlocked=True, **kwargs)
            a, b = result.fragment.tracks
            self.assertEqual(a.curve.start_value, first.curve.start_value)
            self.assertEqual(b.curve.end_value, first.curve.start_value)
            self.assertAlmostEqual(a.curve.end_value - a.curve.start_value, 5 * scale)
            self.assertEqual(b.curve.start_value, a.curve.end_value)
            goal = c.GoalSpec('peak', 'user', self.targets[0], c.TimeInterval(2., 2.), .01)
            with self.assertRaises(c.MotionContractError):
                apply_style(replace(source, goals=(goal,)), style, ('left.elbow.flexion',),
                            amplitude_unlocked=True, **kwargs)

    def test_catalog_has_all_six_styles_with_no_unearned_reviews(self):
        catalog = catalog_for_profile(self.profile)
        self.assertEqual(len(STYLE_REGISTRY), 6)
        for key in STYLE_REGISTRY:
            self.assertEqual(catalog.definitions[key].kind, 'style')
            self.assertFalse(any(record.definition_id == key for record in catalog.reviews.values()))


if __name__ == '__main__':
    unittest.main()
