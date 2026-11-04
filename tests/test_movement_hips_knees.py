"""Pure leg schemas, support contracts and version isolation."""
import unittest
from pathlib import Path
from dataclasses import replace
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.legs import IDS,with_legs_v1
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment
from avatar_app.motion import Surface

ROOT=Path(__file__).resolve().parents[1]


class LegsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base=ROOT/'tests/fixtures/elbows_wrists_hands/v1/demo'
        cls.old=c.loads(c.AvatarProfile,(base/'profile.json').read_text());cls.profile=with_legs_v1(cls.old)
        old=c.loads(c.MotionStateSnapshot,(base/'entry.json').read_text())
        # Synthetic plain-data builder input, not claimed native calibration.
        cls.entry=replace(old,profile_version=7,measured_controls=tuple(
            replace(x,value=abs(x.value)) if x.control_id.endswith('.knee.flexion') else x for x in old.measured_controls)+tuple(
            c.ControlValue(x.id,x.unit,x.frames[0],0) for x in cls.profile.controls if x.id not in {a.control_id for a in old.measured_controls}))

    def build(self,id,parameters=None,entry=None,profile=None):
        p=profile or self.profile;e=entry or self.entry;catalog=catalog_for_profile(p)
        i=instantiate_movement(id,parameters or {},instance_id='legs.test',profile=p,entry_state=e,catalog=catalog)
        f=build_fragment(i,e,p,(Surface(),),catalog);return f,prepare_fragment(f,e,p)

    def special_entry(self,id):
        if id not in ('leg.extend','knee.orient'):return self.entry
        values=tuple(replace(x,value=45) if x.control_id in ('left.knee.flexion','left.hip.flexion','right.knee.flexion','right.hip.flexion') else x for x in self.entry.measured_controls)
        return replace(self.entry,measured_controls=values,active_contacts=('right.sole',))

    def test_all_ids_compile_and_roundtrip(self):
        for id in IDS:
            f,x=self.build(id,entry=self.special_entry(id))
            self.assertEqual(c.loads(c.ExecutableMotion,c.dumps(x)),x)
            self.assertLessEqual(len(f.tracks),256)
            self.assertTrue(all('.hand.' not in t.control_id for t in f.tracks))

    def test_support_release_recovery_and_no_bilateral_flight(self):
        f,x=self.build('hip.lift')
        left=[e for e in f.contact_events if e.anchor_id=='left.sole']
        self.assertEqual(len(left),2);self.assertEqual(left[0].release_s,.2)
        self.assertEqual(left[1].interval.end_s,f.duration_s)
        right=[e for e in f.contact_events if e.anchor_id=='right.sole']
        self.assertEqual(right[0].interval,c.TimeInterval(0,f.duration_s))
        for p in ({'side':'both'},{'support':'both_planted'}):
            with self.assertRaises(c.MotionContractError):self.build('leg.kick',p)
        with self.assertRaises(c.MotionContractError):self.build('hip.lift',entry=replace(self.entry,active_contacts=()))

    def test_entry_and_unreachable_fail_before_execution(self):
        for id in ('leg.extend','knee.orient'):
            with self.assertRaises(c.MotionContractError):self.build(id)
        with self.assertRaises(c.MotionContractError):self.build('leg.cross',{'target':(10,10,10)})
        with self.assertRaises(c.MotionContractError):self.build('knee.pulse',entry=replace(self.entry,active_contacts=('right.sole',)))

    def test_ranges_nonfinite_and_unknown_parameters(self):
        for id in IDS:
            for spec in catalog_for_profile(self.profile).definitions[id].parameter_specs:
                if spec.type!='number':continue
                for bound in (spec.minimum,spec.maximum):self.build(id,{spec.name:bound},entry=self.special_entry(id))
                for bad in (spec.minimum-.01,spec.maximum+.01,float('nan'),float('inf'),True,'5'):
                    with self.assertRaises(c.MotionContractError):self.build(id,{spec.name:bad},entry=self.special_entry(id))
            with self.assertRaises(c.MotionContractError):self.build(id,{'unknown':1})

    def test_profiles_are_opt_in_and_missing_quantity_is_precise(self):
        self.assertFalse(set(IDS)&set(catalog_for_profile(self.old).definitions))
        self.assertEqual(self.old.version,5);self.assertEqual(with_legs_v1(self.profile),self.profile)
        key='left.hip.abduction';p=replace(self.profile,controls=tuple(x for x in self.profile.controls if x.id!=key),joint_limits=tuple(replace(x,mirror_control_id=None) if x.mirror_control_id==key else x for x in self.profile.joint_limits if x.control_id!=key))
        e=replace(self.entry,measured_controls=tuple(x for x in self.entry.measured_controls if x.control_id!=key))
        with self.assertRaises(c.MotionContractError) as caught:self.build('hip.lift',profile=p,entry=e)
        self.assertEqual(caught.exception.code,'MISSING_CAPABILITY')

    def test_optional_finger_profile_migration_retains_existing_controls(self):
        from avatar_app.movement_library.fingers import with_fingers_v1
        base=ROOT/'tests/fixtures/elbows_wrists_hands/v1/mixamo/profile.json'
        fingers=with_fingers_v1(c.loads(c.AvatarProfile,base.read_text()));legs=with_legs_v1(fingers)
        self.assertEqual(legs.controls[:len(fingers.controls)],fingers.controls)
        self.assertEqual(legs.joint_limits[:len(fingers.joint_limits)],tuple(
            replace(x,minimum=0,maximum=150,preferred_minimum=0,preferred_maximum=100,
                measurement_method='geometric unsigned thigh/shin segment angle; straight=0')
            if x.control_id.endswith('.knee.flexion') else x for x in fingers.joint_limits))
        self.assertIn('hand.gesture',catalog_for_profile(legs).definitions)
        self.assertNotIn('hand.gesture',catalog_for_profile(self.profile).definitions)

    def test_explicit_world_targets_match_the_verified_derived_trajectories(self):
        for id in ('leg.swing','leg.cross','leg.fold'):
            derived,_=self.build(id)
            points=[t.curve.end_value for t in derived.tracks if t.control_id=='left.foot.position' and t.curve.kind=='transition']
            target=points[0] if id=='leg.swing' else points[1]
            explicit,_=self.build(id,{'target':target})
            self.assertEqual(explicit,derived)


if __name__=='__main__':unittest.main()
