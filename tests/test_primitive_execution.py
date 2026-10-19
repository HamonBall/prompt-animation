from dataclasses import replace
import json
import math
import subprocess
import sys
import unittest

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library import registry as r
from avatar_app.movement_library.compiler import (ExecutionCursor, instantiate_movement,build_fragment,
    prepare_fragment,sample_motion,interpolate,value_error)
from avatar_app.motion import Surface
from primitive_fixtures import ROOT,make_catalog,executable


class PrimitiveExecutionTests(unittest.TestCase):
    def setUp(self):
        self.entry=c.loads(c.MotionStateSnapshot,(ROOT/'entry-snapshot.json').read_text(encoding='utf-8'))
        self.motion=c.loads(c.ExecutableMotion,(ROOT/'executable.json').read_text(encoding='utf-8'))
        self.fragment=c.loads(c.MotionFragment,(ROOT/'fragment.json').read_text(encoding='utf-8'))
        self.profile=c.loads(c.AvatarProfile,(ROOT.parents[1]/'rig_profiles/demo.json').read_text(encoding='utf-8'))
        self.catalog=make_catalog()

    def reject(self,code,function,*args,**kwargs):
        with self.assertRaises(c.MotionContractError) as raised: function(*args,**kwargs)
        self.assertEqual(raised.exception.code,code)

    def instantiate(self,params=None,**kwargs):
        return instantiate_movement('test.head_transition',params or {},instance_id='preview.1',
            profile=self.profile,entry_state=self.entry,catalog=kwargs.get('catalog',self.catalog))

    def test_definition_defaults_explicit_zero_and_no_production_content(self):
        instance=self.instantiate({'angle':0})
        self.assertEqual({p.name:p.value for p in instance.parameters},{'angle':0,'duration_s':1.2})
        self.assertEqual(instance.explicit_parameters,('angle',))
        self.assertFalse(r.CATALOG.definitions)

    def test_invalid_parameters_types_bounds_and_capabilities(self):
        for params in ({'angle':True},{'angle':math.inf},{'angle':61},{'raw_bone':'Head'}):
            with self.subTest(params=params): self.reject('INVALID_PARAMETER',self.instantiate,params)
        definition=self.catalog.definitions['test.head_transition']
        catalog=r.Catalog({'test.head_builder':self.catalog.builder('test.head_builder')})
        r.register_movement(replace(definition,required_capabilities=('missing',)),catalog)
        self.reject('MISSING_CAPABILITY',self.instantiate,{},catalog=catalog)

    def test_entry_requirement_rejects_without_reset(self):
        definition=self.catalog.definitions['test.head_transition']
        target=c.ControlValue('head.yaw','degree',next(v.frames[0] for v in self.profile.controls if v.id=='head.yaw'),30)
        catalog=r.Catalog({'test.head_builder':self.catalog.builder('test.head_builder')})
        r.register_movement(replace(definition,entry_conditions=(c.StateRequirement('need.turn',target,.1),)),catalog)
        saved=c.dumps(self.entry)
        self.reject('ENTRY_MISMATCH',self.instantiate,{},catalog=catalog)
        self.assertEqual(c.dumps(self.entry),saved)

    def test_builder_provenance_ownership_and_surface_validation(self):
        instance=self.instantiate()
        fragment=build_fragment(instance,self.entry,self.profile,(Surface(),),self.catalog)
        self.assertEqual(fragment,self.fragment)
        self.assertEqual(fragment.source_instance_ids,('preview.1',))
        self.reject('UNRESOLVED_SURFACE',build_fragment,instance,self.entry,self.profile,(Surface(height=1),),self.catalog)
        catalog=r.Catalog({'bad':lambda *args:replace(fragment,source_instance_ids=('wrong',),
            tracks=tuple(replace(t,source_instance_ids=('wrong',)) for t in fragment.tracks))})
        r.register_movement(replace(self.catalog.definitions['test.head_transition'],builder_id='bad'),catalog)
        self.reject('UNKNOWN_ID',build_fragment,instance,self.entry,self.profile,(Surface(),),catalog)

    def test_preparation_is_immutable_and_serialization_stable(self):
        before=c.dumps(self.fragment)
        result=prepare_fragment(self.fragment,self.entry,self.profile)
        self.assertEqual(result,self.motion)
        self.assertEqual(c.dumps(self.fragment),before)
        self.assertEqual(c.loads(c.ExecutableMotion,c.dumps(result)),result)
        self.assertEqual([b.track_id for b in result.runtime_entry_bindings],['preview.1.entry','preview.1.turn'])
        self.assertEqual(result.source_map[0].source_instance_ids,('preview.1',))

    def test_hold_transition_end_hold_and_continuity(self):
        cursor=ExecutionCursor(); state=self.entry; values=[]
        for index in range(round(self.motion.duration_s*30)+1):
            time=min(self.motion.duration_s,index/30)
            target=sample_motion(self.motion,time,state,cursor)
            values.append(target.controls[0].value)
            current={v.control_id:v for v in state.measured_controls}
            current.update({v.control_id:v for v in target.controls})
            state=replace(state,measured_controls=tuple(current.values()))
        self.assertEqual(values[0],0)
        self.assertEqual(values[6],0)
        self.assertAlmostEqual(values[-1],25)
        self.assertTrue(all(a<=b for a,b in zip(values,values[1:])))
        self.assertLess(max(abs(a-b) for a,b in zip(values,values[1:])),1.1)

    def test_runtime_binding_uses_actual_measured_entry_once(self):
        cursor=ExecutionCursor()
        for index in range(7):
            state=replace(self.entry,measured_controls=tuple(replace(v,value=7) if v.control_id=='head.yaw' else v
                for v in self.entry.measured_controls))
            sample_motion(self.motion,index/30,state,cursor)
        self.assertEqual(cursor.bindings['preview.1.turn'],7)
        changed=replace(state,measured_controls=tuple(replace(v,value=-30) if v.control_id=='head.yaw' else v for v in state.measured_controls))
        target=sample_motion(self.motion,7/30,changed,cursor)
        self.assertGreater(target.controls[0].value,7)
        self.assertEqual(cursor.bindings['preview.1.turn'],7)

    def test_all_activation_bindings_read_same_snapshot_regardless_track_order(self):
        first=self.motion.tracks[0]
        other=replace(first,track_id='other',control_id='head.pitch')
        sources=self.motion.source_map+(c.SourceMapEntry('other',('preview.1',),()),)
        forward=replace(self.motion,tracks=self.motion.tracks+(other,),source_map=sources,
            runtime_entry_bindings=self.motion.runtime_entry_bindings+(c.RuntimeEntryBinding('other','preview.1',0,None),))
        backward=replace(forward,tracks=tuple(reversed(forward.tracks)))
        a,b=ExecutionCursor(),ExecutionCursor()
        self.assertEqual(sample_motion(forward,0,self.entry,a),sample_motion(backward,0,self.entry,b))
        self.assertEqual(a.bindings,b.bindings)

    def test_cursor_rewind_jump_revision_and_cross_run_rejected(self):
        cursor=ExecutionCursor()
        self.reject('ENTRY_MISMATCH',sample_motion,self.motion,.1,self.entry,cursor)
        sample_motion(self.motion,0,self.entry,cursor)
        self.reject('ENTRY_MISMATCH',sample_motion,self.motion,.5,self.entry,cursor)
        self.reject('STALE_REVISION',sample_motion,self.motion,1/30,replace(self.entry,revision=9),cursor)
        self.reject('STALE_REVISION',sample_motion,replace(self.motion),0,self.entry,cursor)
        sample_motion(self.motion,1/30,self.entry,cursor)
        self.reject('STALE_REVISION',sample_motion,self.motion,0,self.entry,cursor)

    def test_explicit_initial_jump_rejected(self):
        first=replace(self.fragment.tracks[0],start_source='explicit',curve=c.CurveSpec('hold',30,30,.2))
        self.reject('ENTRY_MISMATCH',prepare_fragment,replace(self.fragment,tracks=(first,)+self.fragment.tracks[1:]),self.entry,self.profile)

    def test_non_neutral_entry_is_preserved(self):
        state=replace(self.entry,measured_controls=tuple(replace(v,value=-20) if v.control_id=='head.yaw' else v for v in self.entry.measured_controls))
        _,_,motion=executable(self.profile,state)
        target=sample_motion(motion,0,state,ExecutionCursor())
        self.assertEqual(target.controls[0].value,-20)

    def test_quaternion_slerp_sign_equivalence_and_vector_interpolation(self):
        self.assertAlmostEqual(value_error(interpolate((1,0,0,0),(-1,0,0,0),.5,'quaternion'),(1,0,0,0),'quaternion'),0)
        q=interpolate((1,0,0,0),(0,0,0,1),.5,'quaternion')
        self.assertAlmostEqual(sum(x*x for x in q),1)
        self.assertAlmostEqual(value_error(q,(1,0,0,0),'quaternion'),90)
        self.assertEqual(interpolate((0,0,0),(2,4,6),.5,'vector'),(1,2,3))

    def test_invalid_fixture_shapes_and_resource_limit(self):
        for name,code in (('invalid-number.json','INVALID_SCHEMA'),('invalid-frame.json','INVALID_PARAMETER'),('over-budget.json','RESOURCE_LIMIT')):
            def load():
                result=c.loads(c.MotionFragment,(ROOT/name).read_text(encoding='utf-8'))
                return prepare_fragment(result,self.entry,self.profile)
            with self.subTest(name=name): self.reject(code,load)

    def test_pure_compiler_import_needs_no_blender_or_model(self):
        script='''
import importlib.abc,sys
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, *args):
  if fullname.startswith(('bpy','avatar_app.blender','avatar_app.planning.local_model','llama_cpp')):
   raise AssertionError(fullname)
sys.meta_path.insert(0,Guard())
from avatar_app.movement_library.compiler import prepare_fragment,sample_motion
print('PURE_COMPILER_IMPORT_PASSED')
'''
        result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_endpoint_supporting_chains_are_explicit_in_frame_targets(self):
        _,_,motion=executable(self.profile,self.entry,id='test.hand_target',parameters={'target':[.2,0,1]})
        frame=sample_motion(motion,0,self.entry,ExecutionCursor())
        self.assertEqual(frame.permitted_supporting_changes,('left.forearm','left.upper_arm'))

    def test_entry_contact_cannot_be_dropped_silently(self):
        anchor=c.ContactAnchor('left.sole','floor',(0,0,0),'world','metre')
        entry=replace(self.entry,contact_anchors=(anchor,),active_contacts=('left.sole',))
        self.reject('ENTRY_MISMATCH',prepare_fragment,self.fragment,entry,self.profile)

    def test_goal_must_contain_an_execution_sample(self):
        goal=replace(self.fragment.goals[0],interval=c.TimeInterval(.017,.017))
        self.reject('UNSUPPORTED_GOAL',prepare_fragment,replace(self.fragment,goals=(goal,)),self.entry,self.profile)
        aligned=replace(goal,interval=c.TimeInterval(.2+.4,.2+.4))
        motion=prepare_fragment(replace(self.fragment,goals=(aligned,)),self.entry,self.profile)
        cursor=ExecutionCursor()
        for index in range(19): frame=sample_motion(motion,index/30,self.entry,cursor)
        self.assertEqual(frame.expected_goals,(aligned,))


if __name__=='__main__': unittest.main()
