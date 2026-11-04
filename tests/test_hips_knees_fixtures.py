"""Published leg examples rebuild and reviewed status requires explicit records."""
import unittest,json
from pathlib import Path
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.legs import IDS
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import build_fragment,prepare_fragment
from avatar_app.movement_library.registry import parameter_schema
from avatar_app.motion import Surface
FIX=Path(__file__).parent/'fixtures/hips_knees/v1'


@unittest.skipUnless((FIX/'manifest.json').exists(),'Stage 05.4 publication gate has not run yet')
class LegFixtureTests(unittest.TestCase):
    def test_every_published_profile_schema_review_and_example(self):
        manifest=json.loads((FIX/'manifest.json').read_text());self.assertEqual(manifest['profile_version'],7)
        for rig,rows in manifest['rigs'].items():
            p=c.loads(c.AvatarProfile,(FIX/rig/'profile.json').read_text());cat=catalog_for_profile(p);self.assertFalse(cat.reviews)
            schemas=json.loads((FIX/rig/'schemas.json').read_text());self.assertEqual(set(rows),set(IDS))
            for raw in json.loads((FIX/rig/'reviews.json').read_text()):
                record=c.from_dict(c.VerificationRecord,raw);self.assertEqual(record.status,'reviewed_for_envelope');cat.register_review(record,p)
                self.assertEqual(schemas[record.definition_id],parameter_schema(cat.definitions[record.definition_id]))
            for id,row in rows.items():
                r={key:c.loads(kind,(FIX/row['records'][key]).read_text()) for key,kind in (('entry',c.MotionStateSnapshot),('instance',c.MovementInstance),('fragment',c.MotionFragment),('executable',c.ExecutableMotion))}
                f=build_fragment(r['instance'],r['entry'],p,(Surface(),),cat)
                self.assertEqual(f,r['fragment']);self.assertEqual(prepare_fragment(f,r['entry'],p),r['executable'])


if __name__=='__main__':unittest.main()
