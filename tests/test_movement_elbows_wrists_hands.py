"""Pure v5 hand schemas, framed targets and bridge compatibility."""
from dataclasses import replace
import unittest
from pathlib import Path
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.hands import IDS,with_hands_v1
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment
from avatar_app.motion import Surface
from avatar_app.movement_library.spatial import palm_rotation,rotate
from avatar_app.movement_library.hands import forearm_twist_sign
from avatar_app.movement_library.registry import parameter_schema

FIX=Path(__file__).parent/'fixtures/shoulders_arms/v1/mixamo'


class HandMechanicsTests(unittest.TestCase):
    def setUp(self):
        fixture=Path(__file__).parent/'fixtures/elbows_wrists_hands/v1/demo'
        self.profile=c.loads(c.AvatarProfile,(fixture/'profile.json').read_text())
        self.entry=c.loads(c.MotionStateSnapshot,(fixture/'entry.json').read_text())
        self.catalog=catalog_for_profile(self.profile)

    def build(self,id,p=None,profile=None,entry=None):
        profile=profile or self.profile;entry=entry or self.entry;catalog=catalog_for_profile(profile)
        i=instantiate_movement(id,p or {},instance_id='hands.1',profile=profile,entry_state=entry,catalog=catalog)
        f=build_fragment(i,entry,profile,(Surface(),),catalog)
        return f,prepare_fragment(f,entry,profile)

    def test_nine_defaults_bilateral_and_roundtrip(self):
        for id in IDS:
            for side in ('left','right','both'):
                with self.subTest(id=id,side=side):
                    f,x=self.build(id,{'side':side})
                    self.assertEqual(c.loads(c.ExecutableMotion,c.dumps(x)),x)
                    self.assertLessEqual(x.duration_s,60)
                    self.assertTrue(all(t.control_id.startswith(('left.','right.')) for t in f.tracks))

    def test_all_numeric_parameter_limits_and_rejections(self):
        for id in IDS:
            for spec in self.catalog.definitions[id].parameter_specs:
                if spec.type!='number':continue
                # A hard elbow angle with a fixed endpoint is intentionally conditional.
                if spec.name=='flexion_deg':continue
                for value in (spec.minimum,spec.maximum):
                    with self.subTest(id=id,parameter=spec.name,value=value):
                        if spec.name.startswith('right_'):p={'side':'both',spec.name:value}
                        else:p={spec.name:value}
                        self.build(id,p)
                for value in (spec.minimum-.01,spec.maximum+.01,float('nan'),float('inf'),True):
                    with self.assertRaises(c.MotionContractError):self.build(id,{spec.name:value})
            with self.assertRaises(c.MotionContractError):self.build(id,{'unknown':1})

    def test_previous_profile_and_catalog_are_unchanged(self):
        old=c.loads(c.AvatarProfile,(FIX/'profile.json').read_text());saved=c.dumps(old)
        self.assertEqual(with_hands_v1(self.profile),self.profile)
        self.assertEqual(saved,c.dumps(old))
        self.assertFalse(set(IDS)&set(catalog_for_profile(old).definitions))
        upgraded=with_hands_v1(old)
        self.assertEqual(upgraded.controls[:len(old.controls)],old.controls)

    def test_missing_palm_reference_is_explicit(self):
        missing={v.id for v in self.profile.controls if v.id.startswith('left.wrist.') or v.id=='left.hand.orientation'}
        p=replace(self.profile,controls=tuple(v for v in self.profile.controls if v.id not in missing),
                  joint_limits=tuple(replace(v,mirror_control_id=None) if v.mirror_control_id in missing else v for v in self.profile.joint_limits if v.control_id not in missing))
        e=replace(self.entry,measured_controls=tuple(v for v in self.entry.measured_controls if v.control_id not in missing))
        for id in ('wrist.flex','wrist.deviate','wrist.circle','hand.orient','hand.hold','elbow.orient'):
            with self.assertRaises(c.MotionContractError) as error:self.build(id,profile=p,entry=e)
            self.assertEqual(error.exception.code,'MISSING_CAPABILITY')
        self.build('wrist.flex',{'side':'right'},p,e)

    def test_inactive_ambiguous_and_incompatible_targets(self):
        for p in ({'side':'left','right_target':[0,0,1]}, {'side':'both','target':[0,0,1]},
                  {'target':[19,19,19]}, {'flexion_deg':130}):
            with self.assertRaises(c.MotionContractError):self.build('hand.hold',p)

    def test_frames_curves_and_independent_orientations(self):
        values={v.control_id:v.value for v in self.entry.measured_controls}
        for frame in ('world','entry_body','current_torso'):
            key={'world':'orientation','entry_body':'entry_orientation','current_torso':'torso_orientation'}[frame]
            self.build('hand.hold',{'orientation_frame':frame,key:[1,0,0,0]})
        for shape in ('line','arc','circle'):
            self.build('hand.trace',{'path':shape})
        f,_=self.build('wrist.flex',{'side':'both','left_angle':-20,'right_angle':30})
        self.assertNotEqual(f.tracks[0].curve.end_value,f.tracks[3].curve.end_value)
        self.build('hand.orient',{'side':'both','left_orientation':values['left.hand.orientation'],
                                'right_orientation':values['right.hand.orientation']})

    def test_palm_axes_and_calibrated_twist_sign(self):
        for forward,normal in (((1,0,0),(0,0,1)),((0,-1,0),(0,0,-1))):
            q=palm_rotation(forward,normal)
            for a,b in zip(rotate(q,(0,1,0)),forward):self.assertAlmostEqual(a,b,places=7)
            for a,b in zip(rotate(q,(0,0,1)),normal):self.assertAlmostEqual(a,b,places=7)
        with self.assertRaises(c.MotionContractError):palm_rotation((1,0,0),(1,0,0))
        self.assertEqual(forearm_twist_sign(self.profile,'left'),-1)
        self.assertEqual(forearm_twist_sign(self.profile,'right'),1)
        with self.assertRaises(c.MotionContractError):self.build('hand.orient',{'orientation':[1,0,0,0],'angle':20})

    def test_explicit_spatial_frames_and_invalid_geometry(self):
        schema=parameter_schema(self.catalog.definitions['hand.hold'])['properties']
        values={v.control_id:v.value for v in self.entry.measured_controls}
        for prefix,frame in (('','world'),('entry_','entry_body'),('torso_','current_torso')):
            for kind in ('target','orientation'):
                self.assertEqual(schema[prefix+kind]['x-frame'],frame)
            for invalid in ([0,0,0,0],[1,1,0,0],[float('nan'),0,0,1],[1,0,0]):
                with self.assertRaises(c.MotionContractError):self.build('hand.hold',{prefix+'orientation':invalid})
            with self.assertRaises(c.MotionContractError):self.build('hand.hold',{prefix+'target':[float('inf'),0,0]})
        f,_=self.build('hand.hold',{'torso_target':values['left.hand.torso_position'],
                                   'torso_orientation':values['left.hand.torso_orientation']})
        self.assertTrue(all(t.frame=='current_torso' for t in f.tracks))
        with self.assertRaises(c.MotionContractError):self.build('hand.hold',{'position_frame':'current_torso','target':values['left.hand.position']})


if __name__=='__main__':unittest.main()
