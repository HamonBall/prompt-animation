"""Published examples rebuild, reviews are explicit, absent digits stay absent."""
import unittest,json
from pathlib import Path
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import build_fragment,prepare_fragment
from avatar_app.movement_library.registry import parameter_schema
from avatar_app.motion import Surface
FIX=Path(__file__).parent/'fixtures/fingers/v1'


class FingerFixtureTests(unittest.TestCase):
    def test_published_profiles_schemas_examples_and_review_status(self):
        manifest=json.loads((FIX/'manifest.json').read_text());self.assertEqual(manifest['profile_version'],6)
        for rig,ids in manifest['rigs'].items():
            p=c.loads(c.AvatarProfile,(FIX/rig/'profile.json').read_text());catalog=catalog_for_profile(p);self.assertFalse(catalog.reviews)
            schemas=json.loads((FIX/rig/'schemas.json').read_text())
            for raw in json.loads((FIX/rig/'reviews.json').read_text()):
                review=c.from_dict(c.VerificationRecord,raw);catalog.register_review(review,p)
                self.assertEqual(schemas[review.definition_id],parameter_schema(catalog.definitions[review.definition_id]))
                self.assertEqual(review.status,'unavailable_on_rig' if rig=='demo' else 'reviewed_for_envelope')
            for id,record in ids.items():
                if rig=='demo':self.assertFalse(record['records']);continue
                values={key:c.loads(kind,(FIX/record['records'][key]).read_text()) for key,kind in (
                    ('entry',c.MotionStateSnapshot),('instance',c.MovementInstance),('fragment',c.MotionFragment),('executable',c.ExecutableMotion))}
                built=build_fragment(values['instance'],values['entry'],p,(Surface(),),catalog)
                self.assertEqual(built,values['fragment']);self.assertEqual(prepare_fragment(built,values['entry'],p),values['executable'])


if __name__=='__main__':unittest.main()
