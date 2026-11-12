"""Fail cheaply on registry routing errors before starting Blender workers."""
import unittest
from unittest.mock import patch

import blender_coordinated_revalidate as validator


class RevalidationSelectionTests(unittest.TestCase):
    def test_all_existing_baseline_and_boundary_routes(self):
        original = dict(validator.CASES)
        boundaries = {
            f'{rig}/{key}-' + ('minimum' if rig == 'demo' else 'maximum'): {'route': key}
            for rig, cases in validator.boundary.BOUNDARIES.items() for key in cases
        }
        with patch.object(validator.boundary, 'boundary_cases', return_value=boundaries):
            for group, cases in (('baseline', original), ('boundary', boundaries)):
                for key, spec in cases.items():
                    with self.subTest(group=group, key=key):
                        path, actual = validator.resolve_case(key, group)
                        self.assertEqual(path, validator.OUT / key)
                        self.assertEqual(actual, spec)
        self.assertEqual(validator.CASES, original)

    def test_groups_do_not_fall_back_or_accept_unknown_cases(self):
        with patch.object(validator.boundary, 'boundary_cases', return_value={'demo/boundary-only': {}}):
            with self.assertRaises(ValueError):
                validator.resolve_case('demo/boundary-only', 'baseline')
            with self.assertRaises(ValueError):
                validator.resolve_case(next(iter(validator.CASES)), 'boundary')
            with self.assertRaises(ValueError):
                validator.resolve_case('demo/boundary-only', 'typo')

    def test_known_registry_entry_cannot_escape_output_root(self):
        with patch.object(validator.boundary, 'boundary_cases', return_value={'../../escape': {}}):
            with self.assertRaises((ValueError, RuntimeError)):
                validator.resolve_case('../../escape', 'boundary')
