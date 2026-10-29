"""Published handoff examples and review status must agree with the current API."""
import json
from pathlib import Path
import unittest

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment,prepare_fragment
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.limbs import IDS
from avatar_app.movement_library.registry import parameter_schema
from avatar_app.motion import Surface

FIXTURES=Path(__file__).parent/'fixtures/shoulders_arms/v1'


class PublishedShouldersArmsTests(unittest.TestCase):
    def test_versioned_examples_compile_and_round_trip(self):
        manifest=json.loads((FIXTURES/'manifest.json').read_text())
        self.assertEqual(manifest['profile_version'],4)
        for rig in ('demo','mixamo'):
            profile=c.loads(c.AvatarProfile,(FIXTURES/rig/'profile.json').read_text())
            catalog=catalog_for_profile(profile)
            self.assertEqual(profile.version,4)
            self.assertEqual(set(manifest['rigs'][rig]),set(IDS))
            for id,record in manifest['rigs'][rig].items():
                with self.subTest(rig=rig,id=id):
                    missing=rig=='demo' and id.startswith('shoulder.')
                    self.assertEqual(record['status'],'unavailable_on_rig' if missing else 'reviewed_for_envelope')
                    if missing:
                        self.assertEqual(record['records'],{})
                        continue
                    values={key:c.loads(kind,(FIXTURES/path).read_text()) for key,kind in
                            (('entry',c.MotionStateSnapshot),('instance',c.MovementInstance),('fragment',c.MotionFragment))
                            for path in (record['records'][key],)}
                    built=build_fragment(values['instance'],values['entry'],profile,(Surface(),),catalog)
                    self.assertEqual(built,values['fragment'])
                    executable=prepare_fragment(built,values['entry'],profile)
                    self.assertEqual(c.loads(c.ExecutableMotion,c.dumps(executable)),executable)

    def test_reviews_are_explicit_and_schemas_match_catalog(self):
        for rig in ('demo','mixamo'):
            profile=c.loads(c.AvatarProfile,(FIXTURES/rig/'profile.json').read_text())
            catalog=catalog_for_profile(profile)
            self.assertFalse(catalog.reviews)
            schemas=json.loads((FIXTURES/rig/'schemas.json').read_text())
            reviews=json.loads((FIXTURES/rig/'reviews.json').read_text())
            self.assertEqual(len(reviews),10)
            for raw in reviews:
                review=c.from_dict(c.VerificationRecord,raw)
                catalog.register_review(review,profile)
                self.assertEqual(schemas[review.definition_id],parameter_schema(catalog.definitions[review.definition_id]))
                self.assertEqual(review.profile_version,4)
                self.assertTrue(review.evidence)
                self.assertEqual(review.status,'unavailable_on_rig' if rig=='demo' and review.definition_id.startswith('shoulder.') else 'reviewed_for_envelope')


if __name__=='__main__':unittest.main()
