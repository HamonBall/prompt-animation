import unittest

import style_evidence as evidence
import style_range_evidence as ranges
import style_pattern_evidence as patterns
from blender_style_patterns import parameters as pattern_parameters
from blender_movement_styles import case_parameters


class StyleEvidenceRoutingTests(unittest.TestCase):
    def test_pattern_routes_and_invalid_inputs(self):
        self.assertEqual(len(patterns.CASES), 6)
        for key, (style, family, frames) in patterns.CASES.items():
            rig, name = key.split('/')
            self.assertEqual(name, style.removeprefix('style.') + '-' + family)
            self.assertIn(pattern_parameters(style, family, rig), ('neutral', 'turned-crouched'))
            self.assertIn(frames, (97, 115, 121))
            self.assertTrue(patterns.case_path(key).is_relative_to(evidence.OUT))
        for key in ('demo/unknown', '../05.7a', 'bad/fluid-stroke'):
            with self.assertRaises(ValueError):
                patterns.case_path(key)

    def test_all_declared_routes_are_known_and_confined(self):
        self.assertEqual(len(evidence.CASES), 12)
        for key, (style, pose, frames) in evidence.CASES.items():
            rig, case = key.split('/')
            self.assertEqual(case_parameters(rig, pose, '1'), 1.)
            self.assertEqual(frames, 121)
            self.assertEqual(case, style.removeprefix('style.') + '-visible-maximum')
            self.assertTrue(evidence.case_path(key).is_relative_to(evidence.OUT))
        for key in ('../05.7a', 'demo/unknown', 'bad/fluid-maximum', '/tmp/style'):
            with self.assertRaises(ValueError):
                evidence.case_path(key)

    def test_default_routes_use_opposite_entries_and_each_rig_has_a_zero_control(self):
        self.assertEqual(len(ranges.CASES), 14)
        for key, (style, pose, frames, intensity) in ranges.CASES.items():
            rig, name = key.split('/')
            self.assertEqual(case_parameters(rig, pose, intensity), float(intensity))
            self.assertEqual(frames, 121)
            self.assertTrue(ranges.case_path(key).is_relative_to(evidence.OUT))
            if name == 'source-zero':
                self.assertEqual(intensity, '0')
            else:
                family = style.removeprefix('style.')
                self.assertEqual((name, intensity), (family + '-default', '0.5'))
                self.assertNotEqual(pose, evidence.CASES[f'{rig}/{family}-visible-maximum'][1])
        for key in ('../05.7a', 'demo/unknown', 'bad/source-zero'):
            with self.assertRaises(ValueError):
                ranges.case_path(key)


if __name__ == '__main__':
    unittest.main()
