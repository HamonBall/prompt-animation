"""Pure shoulder/arm catalog, mirroring, path bounds and capability tests."""
from dataclasses import replace
import math
from pathlib import Path
import unittest
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.limbs import IDS,with_shoulders_v1
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment
from avatar_app.movement_library.curves import arc,line,tangent_rotation_axes,axis_rotation,segment_distance
from avatar_app.movement_library.spatial import rotate
from avatar_app.motion import Surface

FIX=Path(__file__).parent/'fixtures/spine_pelvis/v1/mixamo'


class ShouldersArmsTests(unittest.TestCase):
    def setUp(self):
        self.profile=with_shoulders_v1(c.loads(c.AvatarProfile,(FIX/'profile.json').read_text()))
        source=c.loads(c.MotionStateSnapshot,(FIX/'torso.wave-entry.json').read_text())
        old={v.control_id:v.value for v in source.measured_controls}
        self.entry=replace(source,profile_version=4,measured_controls=tuple(c.ControlValue(v.id,v.unit,v.frames[0],
            old.get(v.id,(1,0,0,0) if v.value_shape=='quaternion' else 0)) for v in self.profile.controls))

    def build(self,id,parameters=None,profile=None,entry=None):
        p=profile or self.profile;e=entry or self.entry;catalog=catalog_for_profile(p)
        i=instantiate_movement(id,parameters or {},instance_id='arm.1',profile=p,entry_state=e,catalog=catalog)
        f=build_fragment(i,e,p,(Surface(),),catalog);return f,prepare_fragment(f,e,p)

    def test_ten_defaults_both_sides_and_returns(self):
        for id in IDS:
            for side in ('left','right','both'):
                with self.subTest(id=id,side=side):
                    f,x=self.build(id,{'side':side})
                    self.assertEqual(c.loads(c.ExecutableMotion,c.dumps(x)),x)
                    self.assertLessEqual(x.duration_s,60)
                    for key in {t.control_id for t in f.tracks}:
                        tracks=[t for t in f.tracks if t.control_id==key]
                        self.assertEqual(tracks[0].curve.start_value,tracks[-1].curve.end_value)
                    self.assertFalse(any(t.control_id.startswith(('torso.','root.','head.','pelvis.')) for t in f.tracks))

    def test_ranges_and_unknown_nonfinite_inputs(self):
        for id in IDS:
            for name in ('angle','duration_s','hold_s'):
                spec=next((p for p in catalog_for_profile(self.profile).definitions[id].parameter_specs if p.name==name),None)
                if spec is None:continue
                for value in (spec.minimum,spec.maximum):
                    with self.subTest(id=id,name=name,value=value):self.build(id,{name:value})
                for value in (spec.minimum-1,spec.maximum+1,float('nan'),True):
                    with self.assertRaises(c.MotionContractError):self.build(id,{name:value})
            with self.assertRaises(c.MotionContractError):self.build(id,{'unknown':1})

    def test_independent_bilateral_angles_and_preserved_end(self):
        f,_=self.build('arm.raise',{'side':'both','left_angle':5,'right_angle':30,'return_policy':'preserve_end'})
        a,b=(next(t for t in f.tracks if t.control_id==s+'.upper_arm.orientation') for s in ('left','right'))
        self.assertNotEqual(a.curve.end_value,b.curve.end_value)
        self.assertNotEqual(a.curve.start_value,a.curve.end_value)

    def test_endpoint_distance_and_stroke_amplitude_reject_invalid_contract_inputs(self):
        catalog=catalog_for_profile(self.profile)
        for id,name,valid,invalid in (
            ('arm.reach','distance_m',(-.08,0,.08),(-.0801,.0801,float('nan'),float('inf'),True)),
            ('arm.stroke','amplitude_m',(0,.08,.16),(-.0001,.1601,float('nan'),float('inf'),False))):
            for value in valid:self.build(id,{name:value})
            for value in invalid:
                with self.subTest(id=id,value=value):
                    with self.assertRaises(c.MotionContractError) as error:
                        instantiate_movement(id,{name:value},instance_id='invalid.1',profile=self.profile,entry_state=self.entry,catalog=catalog)
                    self.assertEqual(error.exception.code,'INVALID_PARAMETER')

    def test_missing_clavicle_is_explicit_and_not_an_arm_approximation(self):
        controls=tuple(v for v in self.profile.controls if not v.id.startswith('left.clavicle.'))
        p=replace(self.profile,controls=controls,joint_limits=tuple(replace(v,mirror_control_id=None) if v.mirror_control_id and v.mirror_control_id.startswith('left.clavicle.') else v for v in self.profile.joint_limits if not v.control_id.startswith('left.clavicle.')),
                  capabilities=tuple(v for v in self.profile.capabilities if 'left.clavicle' not in v))
        e=replace(self.entry,measured_controls=tuple(v for v in self.entry.measured_controls if not v.control_id.startswith('left.clavicle.')))
        for id in IDS[:3]:
            with self.assertRaises(c.MotionContractError) as error:self.build(id,profile=p,entry=e)
            self.assertEqual(error.exception.code,'MISSING_CAPABILITY')
        self.build('arm.raise',profile=p,entry=e)

    def test_unreachable_endpoint_and_ambiguous_bilateral_world_target(self):
        for id in ('arm.reach','arm.fold','arm.stroke'):
            with self.assertRaises(c.MotionContractError):self.build(id,{'target':[19,19,19]})
            with self.assertRaises(c.MotionContractError):self.build(id,{'side':'both','target':[0,0,1]})

    def test_available_shoulder_does_not_require_missing_opposite_clavicle(self):
        for missing,available in (('left','right'),('right','left')):
            prefix=missing+'.clavicle.'
            controls=tuple(v for v in self.profile.controls if not v.id.startswith(prefix))
            limits=tuple(replace(v,mirror_control_id=None) if v.mirror_control_id and v.mirror_control_id.startswith(prefix) else v
                         for v in self.profile.joint_limits if not v.control_id.startswith(prefix))
            profile=replace(self.profile,controls=controls,joint_limits=limits,
                            capabilities=tuple(v for v in self.profile.capabilities if missing+'.clavicle' not in v))
            entry=replace(self.entry,measured_controls=tuple(v for v in self.entry.measured_controls if not v.control_id.startswith(prefix)))
            for id in IDS[:3]:
                fragment,_=self.build(id,{'side':available},profile,entry)
                self.assertTrue(all(t.control_id.startswith(available+'.clavicle.') for t in fragment.tracks))
                for side in (missing,'both'):
                    with self.assertRaises(c.MotionContractError) as error:self.build(id,{'side':side},profile,entry)
                    self.assertEqual(error.exception.code,'MISSING_CAPABILITY')

    def test_bounded_curves_close_and_are_deterministic(self):
        points=arc((0,0,0),(1,0,0),(0,1,0),.2)
        self.assertEqual(points[0],points[-1]);self.assertEqual(len(points),33)
        self.assertTrue(all(abs(math.dist((0,0,0),p)-.2)<1e-12 for p in points))
        self.assertEqual(points,arc((0,0,0),(1,0,0),(0,1,0),.2))
        self.assertEqual(line((0,0,0),(1,0,0),2)[1],(.5,0,0))
        for n in (0,65,True):
            with self.assertRaises(c.MotionContractError):line((0,0,0),(1,0,0),n)
        with self.assertRaises(c.MotionContractError):arc((0,0,0),(1,0,0),(1,0,0),.2)
        tangent=arc((1,0,0),(-1,0,0),(0,1,0),1,phase_easing='smooth')
        self.assertEqual(tangent[0],(0,0,0));self.assertEqual(tangent[-1],tangent[0])
        self.assertTrue(all(v[0]>=0 for v in tangent))
        self.assertLess(math.dist(tangent[0],tangent[1]),.03)
        with self.assertRaises(c.MotionContractError):arc((0,0,0),(1,0,0),(0,1,0),1,phase_easing='unknown')

    def test_circle_is_entry_tangent_and_recovers_full_orientation(self):
        for angle in (-20,0,12,20):
            f,_=self.build('arm.circle',{'angle':angle,'side':'both'})
            values={v.control_id:v.value for v in self.entry.measured_controls}
            for side in ('left','right'):
                key=side+'.upper_arm.orientation';tracks=[t for t in f.tracks if t.control_id==key]
                self.assertEqual(tracks[0].curve.start_value,values[key])
                self.assertEqual(tracks[0].curve.end_value,values[key])
                self.assertEqual(tracks[-1].curve.end_value,values[key])

    def test_tangent_axes_fan_away_from_body_above_and_below_shoulders(self):
        for direction in ((0,0,-1),(0,.5,math.sqrt(.75)),(-1,0,0)):
            side,forward=tangent_rotation_axes(direction,(-1,0,0),(0,1,0))
            self.assertAlmostEqual(sum(v*v for v in side),1)
            self.assertAlmostEqual(sum(v*v for v in forward),1)
            self.assertAlmostEqual(sum(a*b for a,b in zip(side,forward)),0)
            if direction!=(-1,0,0):
                turned=rotate(axis_rotation(side,1),direction)
                self.assertGreater(-turned[0],-direction[0])
            self.assertEqual((side,forward),tangent_rotation_axes(direction,(-1,0,0),(0,1,0)))

    def test_signed_shoulder_roll_reverses_traversal(self):
        positive,_=self.build('shoulder.roll',{'angle':4});negative,_=self.build('shoulder.roll',{'angle':-4})
        key='left.clavicle.protraction'
        origin=next(v.value for v in self.entry.measured_controls if v.control_id==key)
        a=[t.curve.end_value-origin for t in positive.tracks if t.control_id==key]
        b=[t.curve.end_value-origin for t in negative.tracks if t.control_id==key]
        self.assertTrue(all(abs(x+y)<1e-12 for x,y in zip(a,b)))
        origin=next(v.value for v in self.entry.measured_controls if v.control_id=='left.clavicle.elevation')
        elevations=[t.curve.end_value-origin for t in positive.tracks if t.control_id=='left.clavicle.elevation']
        self.assertGreaterEqual(min(elevations),0)
        self.assertAlmostEqual(max(elevations),4)

    def test_segment_clearance_handles_crossing_parallel_and_degenerate_paths(self):
        self.assertAlmostEqual(segment_distance((-1,0,0),(1,0,0),(0,-1,0),(0,1,0)),0)
        self.assertAlmostEqual(segment_distance((0,0,0),(1,0,0),(0,1,0),(1,1,0)),1)
        self.assertAlmostEqual(segment_distance((0,0,0),(0,0,0),(1,0,0),(2,0,0)),1)
        self.assertAlmostEqual(segment_distance((0,0,0),(1,0,0),(3,0,0),(2,0,0)),1)

    def test_bilateral_default_strokes_keep_separate_working_areas(self):
        for amplitude in (0,.08,.16):
            f,_=self.build('arm.stroke',{'side':'both','amplitude_m':amplitude})
            tracks={side:[t for t in f.tracks if t.control_id==side+'.hand.position'] for side in ('left','right')}
            left,right=tracks['left'],tracks['right']
            # Both sweep segments have identical timing. Their closest separation
            # must leave the combined arm radius, including max-amplitude strokes.
            a,b=left[2].curve,right[2].curve
            minimum=min(math.dist(tuple(x+(y-x)*i/100 for x,y in zip(a.start_value,a.end_value)),
                                  tuple(x+(y-x)*i/100 for x,y in zip(b.start_value,b.end_value))) for i in range(101))
            self.assertGreater(minimum,.036*self.profile.height_m)

    def test_baseline_matrix_compiles_with_unique_names(self):
        from shoulders_arms_cases import cases,case_parameters
        names=set()
        for name,id,parameters,_ in cases():
            with self.subTest(case=name):
                self.assertNotIn(name,names);names.add(name)
                self.build(id,case_parameters(name,parameters,self.entry,self.profile))

    def test_inactive_side_and_ambiguous_overrides_rejected(self):
        for params in ({'right_angle':5},{'side':'right','left_angle':5}):
            with self.assertRaises(c.MotionContractError):self.build('arm.raise',params)
        with self.assertRaises(c.MotionContractError):self.build('arm.reach',{'target':[0,0,1],'left_target':[0,0,1]})


if __name__=='__main__':unittest.main()

