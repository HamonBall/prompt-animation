import json
from dataclasses import replace
from pathlib import Path
import unittest

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library import registry as r
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment,sample_motion,ExecutionCursor,value_error
from avatar_app.movement_library.joints import IDS,catalog_for_profile
from avatar_app.movement_library.spatial import with_head_aim_v1,angle_rotation,look_rotation,rotate
from avatar_app.motion import Surface

ROOT=Path(__file__).parent/'fixtures'


class HeadNeckTests(unittest.TestCase):
    def setUp(self):
        self.profile=with_head_aim_v1(c.loads(c.AvatarProfile,(ROOT/'rig_profiles/mixamo.json').read_text()))
        source=c.loads(c.MotionStateSnapshot,(ROOT/'movement_fragments/v1/entry-snapshot.json').read_text())
        old={v.control_id:v.value for v in source.measured_controls}
        values=[]
        for spec in self.profile.controls:
            value=old.get(spec.id,0)
            if spec.id=='head.position': value=(0,0,1.6)
            elif spec.value_shape=='quaternion': value=(1,0,0,0)
            elif spec.value_shape=='vector' and spec.id not in old: value=(0,1,0)
            values.append(c.ControlValue(spec.id,spec.unit,spec.frames[0],value))
        self.entry=replace(source,avatar_id=self.profile.avatar_id,profile_version=2,measured_controls=tuple(values))
        self.catalog=catalog_for_profile(self.profile)

    def build(self,id,parameters=None,profile=None,entry=None):
        p=profile or self.profile; e=entry or self.entry; cat=catalog_for_profile(p)
        i=instantiate_movement(id,parameters or {},instance_id='case.1',profile=p,entry_state=e,catalog=cat)
        return build_fragment(i,e,p,(Surface(),),cat)

    def test_registered_ids_and_generated_parameter_schemas(self):
        self.assertEqual(set(r.CATALOG.definitions),set(IDS))
        self.assertFalse(r.CATALOG.reviews)
        for definition in self.catalog.definitions.values():
            schema=r.parameter_schema(definition)
            self.assertFalse(schema['additionalProperties'])
            self.assertEqual(set(schema['properties']),{p.name for p in definition.parameter_specs})

    def test_all_defaults_compile_and_round_trip(self):
        for id in IDS:
            with self.subTest(id=id):
                f=self.build(id); x=prepare_fragment(f,self.entry,self.profile)
                self.assertEqual(c.loads(c.ExecutableMotion,c.dumps(x)),x)
                self.assertTrue(f.goals)
                self.assertEqual(f.source_instance_ids,('case.1',))
                self.assertLessEqual(len(f.tracks),c.MAX_TRACKS)

    def test_parameter_bounds_zero_sides_and_policies(self):
        for id in IDS:
            for spec in self.catalog.definitions[id].parameter_specs:
                if spec.type=='number': values=(spec.minimum,spec.maximum)
                elif spec.type=='enum': values=spec.enum_values
                else: continue
                for value in values:
                    # World mode is a paired frame+point parameter, not a guessed target.
                    p={spec.name:value}
                    if spec.name=='frame' and value=='world': p['target']=(.5,2,1.6)
                    with self.subTest(id=id,parameter=spec.name,value=value): self.build(id,p)
            if id in ('head.nod','head.shake','head.tilt'): self.build(id,{'angle':0})

    def test_invalid_numbers_unknown_keys_and_out_of_range(self):
        for id in IDS:
            for p in ({'duration_s':.01},{'hold_s':-1},{'duration_s':True},{'duration_s':float('nan')},{'unknown':1}):
                with self.subTest(id=id,p=p),self.assertRaises(c.MotionContractError): self.build(id,p)
        for target in ((0,0,1.6),(0,0,5),(20,20,20),(0,-3,1.6)):
            with self.assertRaises(c.MotionContractError): self.build('head.look',{'frame':'world','target':target})
        for p in ({'frame':'world'},{'target':(0,2,1.6)},{'frame':'world','target':(0,2,1.6),'yaw':0}):
            with self.assertRaises(c.MotionContractError): self.build('head.look',p)

    def test_each_parameter_rejects_values_outside_its_schema(self):
        for id,definition in self.catalog.definitions.items():
            for spec in definition.parameter_specs:
                if spec.type=='number': values=(spec.minimum-.01,spec.maximum+.01)
                elif spec.type=='enum': values=('not_a_supported_choice',)
                else: values=((1,2),(True,0,0))
                for value in values:
                    with self.subTest(id=id,name=spec.name,value=value),self.assertRaises(c.MotionContractError):
                        self.build(id,{spec.name:value})

    def test_shake_direction_and_tilt_sign_have_geometric_meaning(self):
        left=self.build('head.shake',{'direction':'left','angle':20})
        right=self.build('head.shake',{'direction':'right','angle':20})
        self.assertEqual(left.tracks[0].curve.end_value,20)
        self.assertEqual(right.tracks[0].curve.end_value,-20)
        self.assertEqual(next(t for t in left.tracks if t.curve.end_value==-20).control_id,'head.yaw')
        self.assertEqual(self.build('head.tilt',{'angle':-20}).tracks[0].curve.end_value,-20)

    def test_entry_angles_are_not_reset_and_return_is_explicit(self):
        values=tuple(replace(v,value=10) if v.control_id=='head.pitch' else v for v in self.entry.measured_controls)
        entry=replace(self.entry,measured_controls=values)
        f=self.build('head.nod',{'angle':20},entry=entry)
        self.assertEqual(f.tracks[0].curve.start_value,10)
        self.assertEqual(f.tracks[0].curve.end_value,30)
        self.assertEqual(f.tracks[-1].curve.end_value,10)
        f=self.build('head.nod',{'return_policy':'preserve_end'},entry=entry)
        self.assertEqual(f.tracks[-1].curve.end_value,30)
        with self.assertRaises(c.MotionContractError): self.build('head.nod',{'angle':35},entry=replace(entry,
            measured_controls=tuple(replace(v,value=40) if v.control_id=='head.pitch' else v for v in values)))

    def test_profile_extension_preserves_old_profile_and_requires_opt_in(self):
        base=c.loads(c.AvatarProfile,(ROOT/'rig_profiles/mixamo.json').read_text())
        self.assertEqual(base.version,1)
        self.assertFalse(any(v.id=='head.orientation' for v in base.controls))
        self.assertEqual(self.profile.controls[:len(base.controls)],base.controls)
        self.assertEqual(with_head_aim_v1(self.profile),self.profile)
        with self.assertRaises(c.MotionContractError): self.build('head.look',profile=base,entry=replace(self.entry,
            profile_version=1,measured_controls=tuple(v for v in self.entry.measured_controls if v.control_id in {s.id for s in base.controls})))

    def test_missing_neck_is_explicit_and_approximation_is_labelled(self):
        profile=replace(self.profile,capabilities=tuple(v for v in self.profile.capabilities if v!='anatomy.neck'))
        with self.assertRaises(c.MotionContractError) as error: self.build('neck.lead',profile=profile)
        self.assertEqual(error.exception.code,'MISSING_CAPABILITY')
        f=self.build('neck.lead',{'neck_policy':'head_only'},profile=profile)
        self.assertTrue(any(v.name=='head_only_approximation' for v in f.phase_landmarks))
        self.assertTrue(all(t.control_id.startswith('head.') for t in f.tracks))
        self.assertIn('head_only_approximation_requires_opt_in',catalog_for_profile(profile).definitions['neck.lead'].semantic_tags)

    def test_neck_lead_staggers_only_requested_chains(self):
        f=self.build('neck.lead')
        self.assertEqual({t.control_id.split('.')[0] for t in f.tracks},{'head','neck'})
        self.assertEqual(next(t for t in f.tracks if t.control_id=='head.yaw').curve.kind,'hold')
        self.assertEqual(next(t for t in f.tracks if t.control_id=='neck.yaw').curve.kind,'transition')

    def test_world_binding_tracks_current_position_and_measured_goal(self):
        f=self.build('head.look',{'frame':'world','target':(0,3,1.6),'hold_s':1})
        motion=prepare_fragment(f,self.entry,self.profile); cursor=ExecutionCursor()
        state=self.entry
        checked=[]
        for frame in range(61):
            if frame==30:
                state=replace(state,measured_controls=tuple(replace(v,value=(.3,0,1.6)) if v.control_id=='head.position' else v for v in state.measured_controls))
            sampled=sample_motion(motion,frame/30,state,cursor)
            checked.extend(sampled.expected_goals)
        desired=look_rotation((.3,0,1.6),(0,3,1.6))
        self.assertLess(value_error(sampled.controls[0].value,desired,'quaternion'),1e-5)
        self.assertTrue(checked)
        self.assertEqual(checked[-1].target.value,desired)

    def test_non_frame_aligned_timing_is_bounded_and_goal_covered(self):
        for id in IDS:
            f=self.build(id,{'duration_s':.913,'hold_s':.071})
            x=prepare_fragment(f,self.entry,self.profile)
            self.assertTrue(all(abs(g.interval.start_s*30-round(g.interval.start_s*30))<1e-6 for g in x.goal_checks))

    def test_world_return_binds_achieved_rotation_and_checks_hold_before_release(self):
        f=self.build('head.look',{'frame':'world','target':(.3,3,1.6),'return_policy':'return_to_entry','hold_s':0})
        last=f.tracks[-1]
        self.assertEqual(last.start_source,'measured_entry')
        self.assertIsNone(last.curve.look_at_world_v1)
        self.assertEqual(last.curve.end_value,(1,0,0,0))
        prepare_fragment(f,self.entry,self.profile)

    def test_versioned_curve_extension_does_not_change_legacy_serialization(self):
        old=c.CurveSpec('transition',0,20,1)
        saved=c.to_dict(old)
        self.assertNotIn('look_at_world_v1',saved)
        self.assertEqual(c.from_dict(c.CurveSpec,saved),old)
        new=c.CurveSpec('transition',(1,0,0,0),angle_rotation(yaw=20),1,'smooth',(0,2,1.6))
        self.assertEqual(c.loads(c.CurveSpec,c.dumps(new)),new)
        with self.assertRaises(c.MotionContractError): c.TrackSpec('bad',('i',),'head.yaw','degree','joint:neck','scalar',1,new,'explicit',c.TimeInterval(0,1))

    def test_initial_dynamic_hold_cannot_reset_the_entry_pose(self):
        f=self.build('head.look',{'frame':'world','target':(1,3,1.6)})
        first=replace(f.tracks[0],curve=c.CurveSpec('hold',None,None,1,'smooth',(1,3,1.6)),start_source='measured_entry')
        bad=replace(f,tracks=(first,)+f.tracks[1:])
        with self.assertRaises(c.MotionContractError) as error: prepare_fragment(bad,self.entry,self.profile)
        self.assertEqual(error.exception.code,'ENTRY_MISMATCH')

    def test_measured_published_examples_rebuild_and_reviews_are_rig_scoped(self):
        root=ROOT/'head_neck/v1'
        manifest=json.loads((root/'manifest.json').read_text())
        for rig,entries in manifest['rigs'].items():
            profile=c.loads(c.AvatarProfile,(root/rig/'profile.json').read_text())
            catalog=catalog_for_profile(profile)
            for id,example in entries.items():
                files=example['records']
                entry=c.loads(c.MotionStateSnapshot,(root/files['entry']).read_text())
                instance=c.loads(c.MovementInstance,(root/files['instance']).read_text())
                saved=c.loads(c.MotionFragment,(root/files['fragment']).read_text())
                self.assertEqual(build_fragment(instance,entry,profile,(Surface(),),catalog),saved)
                prepare_fragment(saved,entry,profile)
            for saved in json.loads((root/rig/'reviews.json').read_text()):
                review=c.from_dict(c.VerificationRecord,saved)
                catalog.register_review(review,profile)
                if rig=='demo' and review.definition_id=='neck.lead': self.assertEqual(review.status,'unavailable_on_rig')
                else: self.assertEqual(review.status,'reviewed_for_envelope')


if __name__=='__main__': unittest.main()
