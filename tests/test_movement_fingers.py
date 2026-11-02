"""Finger schema, pure build, optional anatomy and profile compatibility."""
from pathlib import Path
from dataclasses import replace
import unittest
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.fingers import IDS,DIGITS,with_fingers_v1
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment
from avatar_app.motion import Surface

ROOT=Path(__file__).resolve().parents[1]


class FingersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture=ROOT/'tests/fixtures/elbows_wrists_hands/v1'
        cls.profile=with_fingers_v1(c.loads(c.AvatarProfile,(fixture/'mixamo/profile.json').read_text()))
        old=c.loads(c.MotionStateSnapshot,(fixture/'mixamo/entry.json').read_text())
        cls.entry=replace(old,profile_version=6,measured_controls=old.measured_controls+tuple(
            c.ControlValue(x.id,x.unit,x.frames[0],0) for x in cls.profile.controls if '.finger.' in x.id))

    def build(self,id,p=None,profile=None,entry=None):
        profile=profile or self.profile;entry=entry or self.entry;catalog=catalog_for_profile(profile)
        i=instantiate_movement(id,p or {},instance_id='fingers.test',profile=profile,entry_state=entry,catalog=catalog)
        f=build_fragment(i,entry,profile,(Surface(),),catalog)
        return f,prepare_fragment(f,entry,profile)

    def test_every_gesture_and_digit_on_each_side_roundtrips(self):
        for side in ('left','right','both'):
            for gesture in ('open','relaxed','fist','point'):
                f,x=self.build('hand.gesture',{'side':side,'gesture':gesture})
                self.assertEqual(c.loads(c.ExecutableMotion,c.dumps(x)),x)
                self.assertTrue(all('.finger.' in t.control_id for t in f.tracks))
            for digit in ('all','four_fingers',*DIGITS):
                f,x=self.build('finger.curl_spread',{'side':side,'selection':digit})
                self.assertTrue(all('.finger.' in t.control_id for t in x.tracks))

    def test_numeric_ranges_and_invalid_types(self):
        for id in IDS:
            for spec in catalog_for_profile(self.profile).definitions[id].parameter_specs:
                if spec.type!='number':continue
                for value in (spec.minimum,spec.maximum):
                    p={spec.name:value}
                    if spec.name.endswith('spread_deg'):
                        if spec.name=='thumb_spread_deg':p[spec.name]=15 if value>0 else -15
                        else:p['selection']='four_fingers'
                    self.build(id,p)
                for bad in (spec.minimum-.01,spec.maximum+.01,float('nan'),float('inf'),True,'5'):
                    with self.assertRaises(c.MotionContractError):self.build(id,{spec.name:bad})
        for p in ({'selection':'thumb','spread_deg':20},{'selection':'index','ring_curl':.5},{'unknown':1}):
            with self.assertRaises(c.MotionContractError):self.build('finger.curl_spread',p)

    def test_missing_anatomy_and_partial_chain_error_is_precise(self):
        removed={x.id for x in self.profile.controls if x.id.startswith('left.finger.index.')}
        p=replace(self.profile,controls=tuple(x for x in self.profile.controls if x.id not in removed),
            joint_limits=tuple(x for x in self.profile.joint_limits if x.control_id not in removed))
        entry=replace(self.entry,measured_controls=tuple(x for x in self.entry.measured_controls if x.control_id not in removed))
        with self.assertRaises(c.MotionContractError) as caught:self.build('hand.gesture',profile=p,entry=entry)
        self.assertEqual(caught.exception.code,'MISSING_CAPABILITY')
        self.assertIn('left.finger.index',caught.exception.details['missing'])
        self.build('finger.curl_spread',{'selection':'ring'},p,entry)

    def test_opt_in_keeps_profiles_1_to_5_and_catalogs(self):
        for rig in ('demo','mixamo'):
            old=c.loads(c.AvatarProfile,(ROOT/'tests/fixtures/elbows_wrists_hands/v1'/rig/'profile.json').read_text())
            saved=c.dumps(old);new=with_fingers_v1(old)
            self.assertEqual(saved,c.dumps(old));self.assertEqual(new.version,6)
            self.assertEqual(new.controls[:len(old.controls)],old.controls)
            self.assertEqual(with_fingers_v1(new),new)
            self.assertFalse(set(IDS)&set(catalog_for_profile(old).definitions))
            self.assertFalse(catalog_for_profile(new).reviews)
            if rig=='demo':self.assertEqual(old.controls,new.controls)

    def test_per_digit_override_and_unselected_ownership(self):
        f,x=self.build('finger.curl_spread',{'selection':'index','index_curl':.8,'curl':0,'return_policy':'preserve_end'})
        self.assertEqual({t.control_id.split('.')[2] for t in f.tracks},{'index'})
        self.assertEqual({t.curve.end_value for t in f.tracks if t.control_id.endswith('.curl')},{72})
        self.assertEqual(x.duration_s,1.6)


if __name__=='__main__':unittest.main()
