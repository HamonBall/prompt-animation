"""Pure-Python validation of the measured Stage 03 rig handoff."""
import json
from pathlib import Path
import unittest

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.registry import CATALOG

ROOT=Path(__file__).parent/'fixtures/rig_profiles'


class RigProfileFixtureTests(unittest.TestCase):
    def setUp(self):
        self.profiles={name:c.loads(c.AvatarProfile,(ROOT/(name+'.json')).read_text(encoding='utf-8'))
                       for name in ('demo','mixamo')}

    def test_both_real_profile_records_round_trip(self):
        manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['calibration_version'],1)
        self.assertEqual(manifest['profiles'],['demo.json','mixamo.json'])
        for name,profile in self.profiles.items():
            with self.subTest(rig=name):
                self.assertEqual(c.loads(c.AvatarProfile,c.dumps(profile)),profile)
                self.assertGreater(profile.height_m,1)
                self.assertLess(profile.height_m,2)
                self.assertTrue(profile.calibration_provenance.source_revision)
                self.assertTrue(any(e.startswith('rig_sha256:') for e in profile.calibration_provenance.evidence))

    def test_distinct_proportions_and_unit_conversion(self):
        ratios=[]
        for profile in self.profiles.values():
            lengths={v.id:v.value_m for v in profile.lengths}
            self.assertGreater(lengths['rig.unit'],0)
            self.assertGreater(lengths['left.thigh'],.3)
            self.assertLess(lengths['left.thigh'],.6)
            self.assertGreater(lengths['left.upper_arm'],.15)
            self.assertLess(lengths['left.upper_arm'],.4)
            ratios.append(lengths['left.upper_arm']/lengths['left.thigh'])
        self.assertGreater(abs(ratios[0]-ratios[1]),.001)

    def test_every_scalar_has_axis_limits_parent_frame_mirror_and_measurement(self):
        for profile in self.profiles.values():
            limits={v.control_id:v for v in profile.joint_limits}
            for control in profile.controls:
                if control.value_shape!='scalar': continue
                with self.subTest(rig=profile.avatar_id,control=control.id):
                    limit=limits[control.id]
                    self.assertEqual(control.unit,'degree')
                    self.assertEqual(control.dimensions,1)
                    self.assertTrue(control.frames[0].startswith('joint:'))
                    self.assertLessEqual(limit.minimum,limit.zero)
                    self.assertGreaterEqual(limit.maximum,limit.zero)
                    self.assertAlmostEqual(sum(v*v for v in limit.positive_axis),1,places=5)
                    self.assertTrue(limit.measurement_method)
                    self.assertIn(limit.mirror_control_id,limits)

    def test_optional_anatomy_is_detected_without_movement_claims(self):
        demo,mixamo=self.profiles['demo'],self.profiles['mixamo']
        self.assertNotIn('anatomy.neck',demo.capabilities)
        self.assertNotIn('anatomy.left.finger.thumb',demo.capabilities)
        self.assertIn('anatomy.neck',mixamo.capabilities)
        self.assertIn('anatomy.left.finger.thumb',mixamo.capabilities)
        self.assertIn('anatomy.left.clavicle',mixamo.capabilities)
        self.assertIn('anatomy.left.toe',mixamo.capabilities)
        self.assertNotIn('anatomy.left.twist.forearm',mixamo.capabilities)
        self.assertEqual(set(CATALOG.definitions),{'head.look','head.nod','head.shake','head.tilt','neck.lead','torso.lean','torso.twist','torso.curl','torso.wave','torso.sway','pelvis.shift','pelvis.raise_lower','pelvis.tilt_turn','pelvis.circle','shoulder.shrug','shoulder.reach','shoulder.roll','arm.raise','arm.sweep','arm.swing','arm.circle','arm.fold','arm.reach','arm.stroke'})
        self.assertFalse(CATALOG.reviews)  # Anatomy/calibration never grants movement reviews.
        self.assertFalse(any('.finger.' in v.id for v in mixamo.controls))

    def test_palm_sole_and_poles_have_parent_relative_references(self):
        for profile in self.profiles.values():
            landmarks={v.id:v for v in profile.landmarks}
            for side in ('left','right'):
                for suffix in ('palm.normal','palm.forward','palm.radial','sole.normal','sole.forward','sole','forearm.pole','shin.pole'):
                    landmark=landmarks[side+'.'+suffix]
                    self.assertEqual(landmark.frame,'joint:'+landmark.joint_id)
                    self.assertEqual(landmark.unit,'metre')
                self.assertAlmostEqual(sum(x*x for x in landmarks[side+'.palm.normal'].position),.05**2,places=6)

    def test_semantic_hinges_are_distinct_from_legacy_segment_controls(self):
        for profile in self.profiles.values():
            controls={v.id:v for v in profile.controls}
            self.assertIn('left.knee.flexion',controls)
            self.assertIn('left.wrist.flexion',controls)
            self.assertIn('left.wrist.deviation',controls)
            self.assertIn('left.forearm.twist',controls)
            self.assertIn('left.hand.direction',controls)
            self.assertIn('left.forearm.direction',controls)
            self.assertIn('left.shin.direction',controls)
            self.assertIn('left.hand.position',controls)
            self.assertNotIn('left_shin_elevation',controls)
            self.assertNotIn('left_hand_roll',controls)


if __name__=='__main__': unittest.main()
