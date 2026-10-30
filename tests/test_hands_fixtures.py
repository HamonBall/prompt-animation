"""Published hand examples rebuild through the supported single-fragment API."""
import json
from pathlib import Path
import unittest

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment, prepare_fragment
from avatar_app.movement_library.hands import IDS
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.registry import parameter_schema
from avatar_app.motion import Surface

FIXTURES = Path(__file__).parent / 'fixtures/elbows_wrists_hands/v1'


class PublishedHandsTests(unittest.TestCase):
    def test_examples_schemas_and_explicit_reviews(self):
        manifest = json.loads((FIXTURES / 'manifest.json').read_text())
        self.assertEqual(manifest['profile_version'], 5)
        for rig in ('demo', 'mixamo'):
            profile = c.loads(c.AvatarProfile, (FIXTURES / rig / 'profile.json').read_text())
            catalog = catalog_for_profile(profile)
            self.assertFalse(catalog.reviews)
            self.assertEqual(set(manifest['rigs'][rig]), set(IDS))
            schemas = json.loads((FIXTURES / rig / 'schemas.json').read_text())
            reviews = json.loads((FIXTURES / rig / 'reviews.json').read_text())
            self.assertEqual({v['definition_id'] for v in reviews}, set(IDS))
            for raw in reviews:
                review = c.from_dict(c.VerificationRecord, raw)
                catalog.register_review(review, profile)
                self.assertEqual(review.status, 'reviewed_for_envelope')
                self.assertEqual(schemas[review.definition_id], parameter_schema(catalog.definitions[review.definition_id]))
            for id, record in manifest['rigs'][rig].items():
                with self.subTest(rig=rig, id=id):
                    self.assertEqual(record['status'], 'reviewed_for_envelope')
                    values = {key: c.loads(kind, (FIXTURES / record['records'][key]).read_text())
                              for key, kind in (('entry', c.MotionStateSnapshot), ('instance', c.MovementInstance),
                                                ('fragment', c.MotionFragment), ('executable', c.ExecutableMotion))}
                    built = build_fragment(values['instance'], values['entry'], profile, (Surface(),), catalog)
                    self.assertEqual(built, values['fragment'])
                    self.assertEqual(prepare_fragment(built, values['entry'], profile), values['executable'])


if __name__ == '__main__':
    unittest.main()
