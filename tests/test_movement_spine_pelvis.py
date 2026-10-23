import json
from dataclasses import replace
from pathlib import Path
import unittest

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment,sample_motion,ExecutionCursor
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.torso_pelvis import IDS,with_pelvis_v1
from avatar_app.motion import Surface

ROOT=Path(__file__).parent/'fixtures'


class SpinePelvisTests(unittest.TestCase):
    def setUp(self):
        self.profile=with_pelvis_v1(c.loads(c.AvatarProfile,(ROOT/'rig_profiles/mixamo.json').read_text()))
        source=c.loads(c.MotionStateSnapshot,(ROOT/'movement_fragments/v1/entry-snapshot.json').read_text())
        previous={v.control_id:v.value for v in source.measured_controls}
        values=[]
        for spec in self.profile.controls:
            value=previous.get(spec.id,0)
            if spec.id=='pelvis.position':value=source.root_transform.position
            elif spec.value_shape=='quaternion':value=(1,0,0,0)
            elif spec.value_shape=='vector' and spec.id not in previous:value=(0,0,1.6)
            values.append(c.ControlValue(spec.id,spec.unit,spec.frames[0],value))
        anchors=tuple(c.ContactAnchor(side+'.sole','floor',(-.1 if side=='left' else .1,0,0),'world','metre') for side in ('left','right'))
        self.entry=replace(source,avatar_id=self.profile.avatar_id,profile_version=3,measured_controls=tuple(values),contact_anchors=anchors,active_contacts=('left.sole','right.sole'))

    def build(self,id,parameters=None,profile=None,entry=None):
        p=profile or self.profile;e=entry or self.entry;catalog=catalog_for_profile(p)
        i=instantiate_movement(id,parameters or {},instance_id='body.1',profile=p,entry_state=e,catalog=catalog)
        return build_fragment(i,e,p,(Surface(),),catalog)

    def test_all_nine_defaults_compile_and_round_trip(self):
        for id in IDS:
            with self.subTest(id=id):
                f=self.build(id);x=prepare_fragment(f,self.entry,self.profile)
                self.assertEqual(c.loads(c.ExecutableMotion,c.dumps(x)),x)
                self.assertEqual({e.anchor_id for e in f.contact_events},{'left.sole','right.sole'})
                self.assertTrue(f.goals)
                self.assertFalse(any(t.control_id.startswith('root.') for t in f.tracks))

    def test_authored_matrix_uses_the_same_schema_and_compiler(self):
        from spine_pelvis_cases import cases
        names=set()
        for name,id,parameters,pose in cases():
            with self.subTest(case=name):
                self.assertNotIn(name,names);names.add(name)
                prepare_fragment(self.build(id,parameters),self.entry,self.profile)

    def test_each_range_enum_zero_and_invalid_parameter(self):
        catalog=catalog_for_profile(self.profile)
        for id in IDS:
            for spec in catalog.definitions[id].parameter_specs:
                good=(spec.minimum,0,spec.maximum) if spec.type=='number' and spec.minimum<=0 else (spec.minimum,spec.maximum) if spec.type=='number' else spec.enum_values
                for value in good:
                    with self.subTest(id=id,name=spec.name,value=value):
                        f=self.build(id,{spec.name:value});prepare_fragment(f,self.entry,self.profile)
                bad=(spec.minimum-.01,spec.maximum+.01,True,float('nan')) if spec.type=='number' else ('unknown',)
                for value in bad:
                    with self.subTest(id=id,name=spec.name,value=value),self.assertRaises(c.MotionContractError):self.build(id,{spec.name:value})
            with self.assertRaises(c.MotionContractError):self.build(id,{'unknown':1})

    def test_world_head_lock_local_arms_and_entry_return(self):
        for id in IDS:
            f=self.build(id)
            head=next(t for t in f.tracks if t.control_id=='head.orientation')
            self.assertEqual(head.curve.kind,'hold')
            self.assertFalse(any('.hand.' in t.control_id for t in f.tracks))
            for control in {t.control_id for t in f.tracks}:
                tracks=[t for t in f.tracks if t.control_id==control]
                self.assertEqual(tracks[0].curve.start_value,tracks[-1].curve.end_value)

    def test_wave_is_distributed_with_ordered_delays(self):
        f=self.build('torso.wave')
        transitions=[t for t in f.tracks if t.curve.kind=='transition' and t.curve.end_value>t.curve.start_value]
        self.assertEqual([t.control_id for t in transitions],['torso.pitch','spine.mid.pitch','spine.upper.pitch'])
        self.assertEqual([round(t.interval.start_s*30) for t in transitions],[0,8,16])
        self.assertAlmostEqual(sum(t.curve.end_value-t.curve.start_value for t in transitions),10)
        pulse=self.build('torso.wave',{'return_policy':'preserve_end'})
        for id in ('torso.pitch','spine.mid.pitch','spine.upper.pitch'):
            tracks=[t for t in pulse.tracks if t.control_id==id]
            self.assertEqual(tracks[-1].curve.end_value,tracks[0].curve.start_value)

    def test_missing_spine_and_declared_single_segment_approximation(self):
        controls=tuple(replace(v,frames=tuple('joint:torso' if f.startswith('joint:spine.') else f for f in v.frames)) for v in self.profile.controls if not v.id.startswith('spine.'))
        mappings=tuple(v for v in self.profile.rest_to_semantic_mappings if not v.semantic_id.startswith('spine.'))
        # Keep the head parent mapping valid when optional intermediates are absent.
        mappings=tuple(replace(v,parent_id='torso' if v.parent_id and v.parent_id.startswith('spine.') else v.parent_id,
            rest_to_semantic=replace(v.rest_to_semantic,frame='joint:torso') if v.rest_to_semantic.frame.startswith('joint:spine.') else v.rest_to_semantic) for v in mappings)
        frames=tuple(v for v in self.profile.canonical_frames if not v.startswith('joint:spine.'))
        limits=tuple(v for v in self.profile.joint_limits if v.control_id in {s.id for s in controls})
        landmarks=tuple(replace(v,frame='joint:torso') if v.frame.startswith('joint:spine.') else v for v in self.profile.landmarks if not v.joint_id.startswith('spine.'))
        profile=replace(self.profile,controls=controls,rest_to_semantic_mappings=mappings,canonical_frames=frames,joint_limits=limits,landmarks=landmarks)
        entry=replace(self.entry,measured_controls=tuple(replace(v,frame='joint:torso') if v.frame.startswith('joint:spine.') else v for v in self.entry.measured_controls if v.control_id in {s.id for s in controls}))
        f=self.build('torso.wave',profile=profile,entry=entry)
        self.assertIn('single_spine_approximation',{v.name for v in f.phase_landmarks})
        no_spine=replace(profile,controls=tuple(v for v in controls if v.id!='torso.pitch'),joint_limits=tuple(v for v in limits if v.control_id!='torso.pitch'),capabilities=tuple(v for v in profile.capabilities if v!='measure.torso.pitch'))
        no_entry=replace(entry,measured_controls=tuple(v for v in entry.measured_controls if v.control_id!='torso.pitch'))
        with self.assertRaises(c.MotionContractError) as error:self.build('torso.curl',profile=no_spine,entry=no_entry)
        self.assertEqual(error.exception.code,'MISSING_CAPABILITY')

    def test_pelvis_support_and_profile_opt_in_are_required(self):
        for id in IDS:
            profile=replace(self.profile,controls=tuple(v for v in self.profile.controls if v.id!='head.orientation'),capabilities=tuple(v for v in self.profile.capabilities if v!='measure.head.orientation'))
            entry=replace(self.entry,measured_controls=tuple(v for v in self.entry.measured_controls if v.control_id!='head.orientation'))
            with self.assertRaises(c.MotionContractError) as error:self.build(id,profile=profile,entry=entry)
            self.assertEqual(error.exception.code,'MISSING_CAPABILITY')
        for id in IDS[5:]:
            with self.assertRaises(c.MotionContractError):self.build(id,entry=replace(self.entry,active_contacts=()))
            profile=replace(self.profile,controls=tuple(v for v in self.profile.controls if v.id!='pelvis.position'),capabilities=tuple(v for v in self.profile.capabilities if v!='measure.pelvis.position'))
            entry=replace(self.entry,measured_controls=tuple(v for v in self.entry.measured_controls if v.control_id!='pelvis.position'))
            with self.assertRaises(c.MotionContractError) as error:self.build(id,profile=profile,entry=entry)
            self.assertEqual(error.exception.code,'MISSING_CAPABILITY')

    def test_profile_extension_is_versioned_and_nonmutating(self):
        base=c.loads(c.AvatarProfile,(ROOT/'rig_profiles/mixamo.json').read_text())
        self.assertEqual(base.version,1);self.assertEqual(self.profile.version,3)
        self.assertEqual(base.controls,self.profile.controls[:len(base.controls)])
        self.assertEqual(with_pelvis_v1(self.profile),self.profile)

    def test_published_measured_examples_rebuild_and_reviews_are_rig_scoped(self):
        root=ROOT/'spine_pelvis/v1'
        manifest=json.loads((root/'manifest.json').read_text())
        for rig,entries in manifest['rigs'].items():
            profile=c.loads(c.AvatarProfile,(root/rig/'profile.json').read_text());catalog=catalog_for_profile(profile)
            self.assertEqual(set(entries),set(IDS))
            for id,example in entries.items():
                files=example['records']
                entry=c.loads(c.MotionStateSnapshot,(root/files['entry']).read_text())
                instance=c.loads(c.MovementInstance,(root/files['instance']).read_text())
                fragment=c.loads(c.MotionFragment,(root/files['fragment']).read_text())
                self.assertEqual(build_fragment(instance,entry,profile,(Surface(),),catalog),fragment)
                prepare_fragment(fragment,entry,profile)
            for saved in json.loads((root/rig/'reviews.json').read_text()):
                review=c.from_dict(c.VerificationRecord,saved);catalog.register_review(review,profile)
                self.assertEqual(review.status,'reviewed_for_envelope')

    def test_circle_is_closed_bounded_and_has_both_axes(self):
        f=self.build('pelvis.circle',{'distance_m':.04,'return_policy':'preserve_end'})
        tracks=[t for t in f.tracks if t.control_id=='pelvis.position' and t.curve.kind=='transition']
        self.assertEqual(len(tracks),34)
        self.assertEqual(tracks[0].curve.start_value,tracks[-1].curve.end_value)
        self.assertGreater(len({t.curve.end_value for t in tracks}),30)
        self.assertEqual(sum(t.curve.easing=='linear' for t in tracks),32)

if __name__=='__main__':unittest.main()
