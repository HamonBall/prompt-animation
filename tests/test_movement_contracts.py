import dataclasses
import json
import math
import subprocess
import sys
import unittest
from pathlib import Path

from avatar_app.models import PlanError
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library import registry as r
from movement_contract_fixtures import FIXTURE_ROOT, generated_files, records, test_catalog, validate_fixture


class MovementContractTests(unittest.TestCase):
    def setUp(self):
        self.profile, self.catalog = test_catalog()
        self.examples = records()
        self.instance = c.MovementInstance('test.1', 'test.turn', 1, (), ('clause.1',))

    def rejects(self, code, function, *args, **kwargs):
        with self.assertRaises(c.MotionContractError) as raised:
            function(*args, **kwargs)
        self.assertIsInstance(raised.exception, PlanError)
        self.assertEqual(raised.exception.code, code)
        return raised.exception

    def test_generated_artifacts_match_python_source(self):
        expected = generated_files()
        actual = {p.relative_to(FIXTURE_ROOT).as_posix(): p.read_text(encoding='utf-8')
                  for p in FIXTURE_ROOT.rglob('*.json')}
        self.assertEqual(set(actual), set(expected))
        for name, contents in expected.items():
            with self.subTest(file=name): self.assertEqual(actual[name], contents)

    def test_all_valid_fixture_round_trips(self):
        manifest = json.loads((FIXTURE_ROOT / 'manifest.json').read_text(encoding='utf-8'))
        for entry in manifest['valid']:
            with self.subTest(file=entry['path']):
                kind = c.RECORD_TYPES[entry['record_type']]
                saved = (FIXTURE_ROOT / entry['path']).read_text(encoding='utf-8')
                record = c.loads(kind, saved)
                validated = validate_fixture(record, self.examples)
                self.assertEqual(validated, record)
                self.assertEqual(c.loads(kind, c.dumps(record)), record)
                self.assertEqual(c.dumps(c.loads(kind, c.dumps(record))), c.dumps(record))

    def test_all_invalid_fixtures_fail_before_execution(self):
        manifest = json.loads((FIXTURE_ROOT / 'manifest.json').read_text(encoding='utf-8'))
        for entry in manifest['invalid']:
            with self.subTest(file=entry['path']):
                def load_and_validate():
                    record = c.loads(c.RECORD_TYPES[entry['record_type']],
                                     (FIXTURE_ROOT / entry['path']).read_text(encoding='utf-8'))
                    return validate_fixture(record, self.examples)
                self.rejects(entry['error'], load_and_validate)

    def test_import_is_pure_in_fresh_process_and_catalog_is_explicit(self):
        script = '''
import importlib.abc, json, sys
blocked = ('bpy', 'avatar_app.blender', 'avatar_app.planning.local_model', 'llama_cpp', 'torch', 'transformers')
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if any(fullname == n or fullname.startswith(n+'.') for n in blocked):
            raise AssertionError('Unexpected import: '+fullname)
sys.meta_path.insert(0, Guard())
from avatar_app.movement_library import contracts, registry
assert set(registry.CATALOG.definitions)=={'head.look','head.nod','head.shake','head.tilt','neck.lead','torso.lean','torso.twist','torso.curl','torso.wave','torso.sway','pelvis.shift','pelvis.raise_lower','pelvis.tilt_turn','pelvis.circle','shoulder.shrug','shoulder.reach','shoulder.roll','arm.raise','arm.sweep','arm.swing','arm.circle','arm.fold','arm.reach','arm.stroke'}
assert not registry.CATALOG.reviews
assert not any(n in sys.modules for n in blocked)
print(json.dumps({'record_types':len(contracts.RECORD_TYPES), 'catalog_size':len(registry.CATALOG.definitions), 'blocked_imports':list(blocked)}))
'''
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"catalog_size": 24', result.stdout)
        self.assertFalse(r.CATALOG.reviews)

    def test_defaults_preserve_explicit_zero_and_resolution_is_idempotent(self):
        unresolved = dataclasses.replace(self.instance, parameters=(c.ParameterValue('angle', 0),))
        result = r.validate_instance(unresolved, self.profile, self.catalog)
        self.assertEqual({p.name:p.value for p in result.parameters}, {'angle':0, 'duration_s':1})
        self.assertEqual(result.explicit_parameters, ('angle',))
        self.assertIsNone(unresolved.explicit_parameters)
        self.assertEqual(r.validate_instance(result, self.profile, self.catalog), result)
        defaulted = r.validate_instance(self.instance, self.profile, self.catalog)
        self.assertEqual(defaulted.parameters[0].value, 15)
        self.assertEqual(defaulted.explicit_parameters, ())

    def test_omitted_optional_controls_are_not_fabricated(self):
        definition = dataclasses.replace(self.catalog.definitions['test.turn'], id='test.optional',
            parameter_specs=(dataclasses.replace(self.catalog.definitions['test.turn'].parameter_specs[0],
                                                 has_default=False, default=None),))
        r.register_movement(definition, self.catalog)
        result = r.validate_instance(dataclasses.replace(self.instance, definition_id=definition.id), self.profile, self.catalog)
        self.assertEqual(result.parameters, ())

    def test_required_parameter_and_unknown_parameter_rejected(self):
        self.rejects('INVALID_PARAMETER', r.validate_instance,
                     dataclasses.replace(self.instance, definition_id='test.target'), self.profile, self.catalog)
        self.rejects('INVALID_PARAMETER', r.validate_instance,
                     dataclasses.replace(self.instance, parameters=(c.ParameterValue('raw_bone', 'Head'),)),
                     self.profile, self.catalog)

    def test_null_requires_declared_meaning(self):
        spec = self.catalog.definitions['test.turn'].parameter_specs[0]
        self.rejects('INVALID_PARAMETER', c.validate_parameter, spec, None)
        c.validate_parameter(dataclasses.replace(spec, nullable=True), None)
        self.rejects('INVALID_PARAMETER', dataclasses.replace, spec, has_default=True, default=None)

    def test_parameter_type_matrix_and_finite_numbers(self):
        good = {
            'number': (0, None, None, ()), 'integer': (2, None, None, ()),
            'boolean': (True, None, None, ()), 'string': ('text', None, None, ()),
            'enum': ('a', None, None, ('a','b')),
            'vector': ((1,2,3), 'world', 3, ()),
            'quaternion': ((1,0,0,0), 'world', 4, ())}
        bad = {'number':(True, '1', math.nan, math.inf), 'integer':(True, 1.1),
               'boolean':(0,'true'), 'string':('',2), 'enum':('c',),
               'vector':((1,2),(1,True,3)), 'quaternion':((0,0,0,0),(1,0,0))}
        for kind, (value, frame, dimensions, choices) in good.items():
            spec = c.ParameterSpec('value', kind, 'unitless', frame, True, True, value,
                                   enum_values=choices, dimensions=dimensions)
            c.validate_parameter(spec, value)
            for rejected in bad[kind]:
                with self.subTest(kind=kind, value=rejected):
                    self.rejects('INVALID_PARAMETER', c.validate_parameter, spec, rejected)

    def test_bounds_and_shapes_apply_to_defaults(self):
        spec = self.catalog.definitions['test.turn'].parameter_specs[0]
        for value in (-46,46,True):
            self.rejects('INVALID_PARAMETER', dataclasses.replace, spec, default=value)
        self.rejects('INVALID_PARAMETER', dataclasses.replace, spec, minimum=46)
        vector = self.catalog.definitions['test.target'].parameter_specs[0]
        self.rejects('INVALID_PARAMETER', dataclasses.replace, vector, frame=None)
        self.rejects('INVALID_PARAMETER', dataclasses.replace, vector, dimensions=None)

    def test_duplicate_catalog_ids_and_untrusted_builders_are_atomic(self):
        before = dict(self.catalog.definitions)
        definition = self.catalog.definitions['test.turn']
        self.rejects('CONSTRAINT_CONFLICT', r.register_movement, definition, self.catalog)
        self.rejects('CONSTRAINT_CONFLICT', r.register_movement, dataclasses.replace(definition, version=2), self.catalog)
        self.rejects('UNKNOWN_ID', r.register_movement,
                     dataclasses.replace(definition, id='test.other', builder_id='os.system'), self.catalog)
        self.assertEqual(dict(self.catalog.definitions), before)
        with self.assertRaises(TypeError): self.catalog.definitions['new'] = definition
        self.rejects('INVALID_PARAMETER', r.Catalog, {'bad': 'import os'})

    def test_definition_lookup_versions_and_ids(self):
        self.assertIs(r.get_movement('test.turn', 1, self.catalog), self.catalog.definitions['test.turn'])
        self.rejects('UNKNOWN_ID', r.get_movement, 'missing', 1, self.catalog)
        self.rejects('VERSION_MISMATCH', r.get_movement, 'test.turn', 2, self.catalog)
        self.rejects('INVALID_PARAMETER', r.get_movement, 'test.turn', True, self.catalog)
        self.rejects('INVALID_PARAMETER', dataclasses.replace, self.instance, instance_id='')

    def test_incompatible_capabilities_owned_chains_and_anchors(self):
        profile = dataclasses.replace(self.profile, controls=(), joint_limits=(), capabilities=())
        error = self.rejects('MISSING_CAPABILITY', r.validate_instance, self.instance, profile, self.catalog)
        self.assertEqual(error.instance_id, 'test.1')
        definition = self.catalog.definitions['test.turn']
        for change in ({'owned_chains':('missing.chain',)},
                       {'contact_requirements':(c.SupportRequirement('missing.anchor','floor','available'),)},
                       {'parameter_specs':(dataclasses.replace(definition.parameter_specs[0], capability='missing.cap'),)}):
            catalog = r.Catalog({'test.builder':lambda: None})
            r.register_movement(dataclasses.replace(definition, **change), catalog)
            self.rejects('MISSING_CAPABILITY', r.validate_instance, self.instance, self.profile, catalog)

    def test_profile_bounds_and_frame_checks(self):
        spec = self.catalog.definitions['test.turn'].parameter_specs[0]
        catalog = r.Catalog({'test.builder':lambda: None})
        r.register_movement(dataclasses.replace(self.catalog.definitions['test.turn'],
            parameter_specs=(dataclasses.replace(spec, minimum=-100, maximum=100),)), catalog)
        error = self.rejects('INVALID_PARAMETER', r.validate_instance,
            dataclasses.replace(self.instance, parameters=(c.ParameterValue('angle', 80),)), self.profile, catalog)
        self.assertEqual(error.control_id, 'head.yaw')
        self.assertEqual(error.details['parameter'], 'angle')
        self.rejects('INVALID_PARAMETER', r.validate_control_value,
                     c.ControlValue('head.yaw','degree','world',0), self.profile)
        self.rejects('INVALID_PARAMETER', r.validate_control_value,
                     c.ControlValue('head.yaw','metre','joint:head',0), self.profile)
        self.rejects('UNKNOWN_ID', r.validate_control_value,
                     c.ControlValue('unknown','degree','world',0), self.profile)

    def test_immutable_records_and_input_aliasing(self):
        with self.assertRaises(dataclasses.FrozenInstanceError): self.instance.instance_id = 'new'
        self.rejects('INVALID_PARAMETER', dataclasses.replace, self.instance, parameters=[])
        data = c.to_dict(self.examples['parallel-recipe'])
        saved = c.from_dict(c.MotionRecipe, data)
        data['instances'][1]['parameters'][1]['value'][0] = 100
        self.assertEqual(saved.instances[1].parameters[1].value[0], .2)
        changed = dataclasses.replace(saved, base_revision=8)
        self.assertEqual(saved.base_revision, 7)
        self.assertEqual(changed.base_revision, 8)

    def test_serialization_requires_known_versions_and_all_fields(self):
        data = c.to_dict(self.examples['entry-snapshot'])
        for value in (2, True, '1'):
            self.rejects('VERSION_MISMATCH', c.from_dict, c.MotionStateSnapshot, {**data,'schema_version':value})
        del data['schema_version']
        self.rejects('VERSION_MISMATCH', c.from_dict, c.MotionStateSnapshot, data)
        data = c.to_dict(self.examples['entry-snapshot'])
        del data['velocities']
        self.rejects('INVALID_SCHEMA', c.from_dict, c.MotionStateSnapshot, data)
        data = c.to_dict(self.examples['entry-snapshot'])
        data['root_transform']['schema_version'] = 2
        self.rejects('VERSION_MISMATCH', c.from_dict, c.MotionStateSnapshot, data)

    def test_json_duplicates_nonfinite_values_and_byte_budget(self):
        self.rejects('INVALID_SCHEMA', c.loads, c.TimeInterval, '{"schema_version":1,"start_s":0,"start_s":1,"end_s":2}')
        for raw in ('NaN','Infinity','-Infinity'):
            self.rejects('INVALID_SCHEMA', c.loads, c.TimeInterval,
                         '{"schema_version":1,"start_s":0,"end_s":'+raw+'}')
        self.rejects('INVALID_PARAMETER', c.loads, c.TimeInterval, '{"schema_version":1,"start_s":0,"end_s":1e999}')
        self.rejects('RESOURCE_LIMIT', c.loads, c.TimeInterval, ' '* (c.MAX_JSON_BYTES+1))
        self.rejects('INVALID_SCHEMA', c.loads, c.TimeInterval, '{} trailing')
        self.rejects('INVALID_PARAMETER', c.TimeInterval,0,10**500)
        self.rejects('INVALID_SCHEMA', c.loads,c.TimeInterval,chr(0xd800))
        self.rejects('INVALID_PARAMETER', c.ParameterValue,'text',chr(0xd800))

    def test_recipe_round_trip_preserves_timing_ids_constraints_and_locks(self):
        recipe = self.examples['sequential-recipe']
        result = c.loads(c.MotionRecipe, c.dumps(recipe))
        self.assertEqual(result, recipe)
        self.assertEqual([i.instance_id for i in result.instances], ['turn.1','turn.2'])
        self.assertEqual(result.relations[0].offset_s, 0)
        self.assertTrue(result.hard_goals[0].locked)
        self.assertEqual(result.instances[0].explicit_parameters, ('angle',))

    def test_relations_reject_cycles_and_multiple_start_constraints(self):
        recipe = self.examples['sequential-recipe']
        reverse = c.Relation('reverse','after','turn.2','turn.1',0)
        self.rejects('CONSTRAINT_CONFLICT', dataclasses.replace, recipe, relations=recipe.relations+(reverse,))
        duplicate = c.Relation('another','parallel','turn.1','turn.2',0)
        self.rejects('CONSTRAINT_CONFLICT', dataclasses.replace, recipe, relations=recipe.relations+(duplicate,))
        self.rejects('CONSTRAINT_CONFLICT', c.Relation, 'self','after','turn.1','turn.1',0)

    def test_after_event_requires_known_declared_landmark(self):
        recipe = self.examples['sequential-recipe']
        good = dataclasses.replace(recipe, relations=(c.Relation('r','after_event','turn.1','turn.2',0,'arrival'),))
        self.assertEqual(r.validate_recipe(good,self.profile,self.catalog), good)
        bad = dataclasses.replace(good, relations=(dataclasses.replace(good.relations[0],source_event='missing'),))
        self.rejects('UNKNOWN_ID', r.validate_recipe, bad, self.profile, self.catalog)
        self.rejects('INVALID_PARAMETER', c.Relation, 'r','after_event','turn.1','turn.2',0)

    def test_clause_goals_styles_and_profile_versions(self):
        self.rejects('INVALID_PARAMETER', c.ClauseCoverage, 'c','Unknown goal','unsupported',())
        c.ClauseCoverage('c','Unknown goal','unsupported',(),'No supported capability')
        recipe = self.examples['styled-loop-recipe']
        r.validate_recipe(recipe,self.profile,self.catalog)
        self.rejects('VERSION_MISMATCH', r.validate_recipe, dataclasses.replace(recipe,profile_version=2),self.profile,self.catalog)
        self.rejects('ENTRY_MISMATCH', r.validate_recipe, dataclasses.replace(recipe,avatar_id='other'),self.profile,self.catalog)
        self.rejects('VERSION_MISMATCH', r.validate_recipe,
                     dataclasses.replace(recipe,optional_styles=(dataclasses.replace(recipe.optional_styles[0],definition_version=2),)),
                     self.profile,self.catalog)
        self.rejects('UNKNOWN_ID', dataclasses.replace, recipe,
                     hard_goals=(dataclasses.replace(recipe.hard_goals[0],clause_id='missing'),))

    def test_patch_envelope_validation_preserves_original(self):
        recipe, patch = self.examples['sequential-recipe'], self.examples['narrow-patch']
        before = c.dumps(recipe)
        self.assertIs(r.validate_patch(patch,recipe,self.profile,self.catalog), patch)
        self.assertEqual(c.dumps(recipe), before)
        self.rejects('STALE_REVISION', r.validate_patch, dataclasses.replace(patch,base_revision=6),recipe,self.profile,self.catalog)
        self.rejects('UNKNOWN_ID', r.validate_patch, dataclasses.replace(patch,locked_goal_ids=('missing',)),recipe,self.profile,self.catalog)
        bad = dataclasses.replace(patch,instance_changes=(c.InstancePatch('turn.2',(c.ParameterValue('angle',46),)),))
        self.rejects('INVALID_PARAMETER', r.validate_patch, bad,recipe,self.profile,self.catalog)

    def test_review_envelope_is_separate_versioned_and_narrower(self):
        review = self.examples['verification-envelope']
        definition = self.catalog.definitions['test.turn']
        self.catalog.register_review(review,self.profile)
        self.assertEqual(self.catalog.definitions['test.turn'], definition)
        self.assertEqual(list(self.catalog.reviews), [('test.turn',1,'test.avatar',1)])
        self.rejects('CONSTRAINT_CONFLICT', self.catalog.register_review, review,self.profile)
        catalog = test_catalog()[1]
        too_wide = dataclasses.replace(review,parameter_envelope=(dataclasses.replace(review.parameter_envelope[0],minimum=-46),))
        self.rejects('INVALID_PARAMETER', catalog.register_review, too_wide,self.profile)
        self.rejects('VERSION_MISMATCH', catalog.register_review, dataclasses.replace(review,profile_version=2),self.profile)
        self.rejects('INVALID_PARAMETER', catalog.register_review,
                     dataclasses.replace(review,status='reviewed_for_envelope'),self.profile)
        full = dataclasses.replace(review,status='reviewed_for_envelope',
            parameter_envelope=review.parameter_envelope+(definition.parameter_specs[1],))
        self.assertEqual(catalog.register_review(full,self.profile), full)

    def test_snapshot_unknown_motion_state_is_null_and_derivative_units_are_explicit(self):
        snapshot = self.examples['entry-snapshot']
        self.assertIsNone(snapshot.velocities)
        self.assertIsNone(snapshot.phase)
        velocity = c.ControlValue('head.yaw','degree_per_second','joint:head',120)
        r.validate_snapshot(dataclasses.replace(snapshot,velocities=(velocity,),phase=.5),self.profile)
        self.rejects('INVALID_PARAMETER', r.validate_snapshot,
                     dataclasses.replace(snapshot,velocities=(snapshot.measured_controls[0],)),self.profile)
        self.rejects('ENTRY_MISMATCH', dataclasses.replace, snapshot,active_contacts=('missing',))

    def test_profile_hierarchy_frames_and_axes_are_validated(self):
        mapping = self.profile.rest_to_semantic_mappings
        self.rejects('CONSTRAINT_CONFLICT', dataclasses.replace, self.profile,
                     rest_to_semantic_mappings=(dataclasses.replace(mapping[0],parent_id='head'),mapping[1]))
        self.rejects('UNKNOWN_ID', dataclasses.replace, self.profile,
                     rest_to_semantic_mappings=(mapping[0],dataclasses.replace(mapping[1],parent_id='missing')))
        self.rejects('INVALID_PARAMETER', dataclasses.replace, self.profile,
                     canonical_frames=self.profile.canonical_frames+('joint:missing',))
        self.rejects('INVALID_PARAMETER', dataclasses.replace, self.profile.joint_limits[0],positive_axis=(1,1,0))
        self.rejects('INVALID_PARAMETER', dataclasses.replace, self.profile.joint_limits[0],preferred_minimum=-100)

    def test_tracks_preserve_measured_entry_and_validate_shapes(self):
        track = self.examples['single-fragment'].tracks[0]
        hold = dataclasses.replace(track,curve=c.CurveSpec('hold',None,None,1))
        self.assertIsNone(hold.curve.start_value)
        self.rejects('INVALID_PARAMETER', dataclasses.replace, hold,dimensions=2)
        self.rejects('INVALID_PARAMETER', dataclasses.replace, track,start_source='explicit')
        self.rejects('INVALID_PARAMETER', dataclasses.replace, track,interval=c.TimeInterval(0,2))
        self.rejects('INVALID_PARAMETER', c.CurveSpec,'transition',None,None,1)
        self.rejects('INVALID_PARAMETER', c.CurveSpec,'hold',0,1,1)
        self.rejects('INVALID_PARAMETER', c.CurveSpec,'hold',0,None,0)

    def test_fragment_contacts_ownership_and_surface_resolution(self):
        fragment = self.examples['single-fragment']
        self.rejects('UNRESOLVED_SURFACE', r.validate_fragment, fragment,self.profile)
        r.validate_fragment(fragment,self.profile,resolved_surface_ids=('floor',))
        self.rejects('CONSTRAINT_CONFLICT', dataclasses.replace, fragment,
                     tracks=fragment.tracks+(dataclasses.replace(fragment.tracks[0],track_id='other'),))
        self.rejects('CONSTRAINT_CONFLICT', dataclasses.replace, fragment,
                     contact_events=fragment.contact_events+(dataclasses.replace(fragment.contact_events[0],event_id='other'),))
        self.rejects('INVALID_PARAMETER', dataclasses.replace, fragment.contact_events[0],acquire_s=.9,release_s=.9)
        self.rejects('INVALID_PARAMETER', dataclasses.replace, fragment,duration_s=.5)
        bad = dataclasses.replace(fragment, tracks=(dataclasses.replace(fragment.tracks[0],unit='metre'),))
        self.rejects('INVALID_PARAMETER', r.validate_fragment,bad,self.profile,resolved_surface_ids=('floor',))

    def test_resolved_data_rejects_inconsistent_schedule_and_provenance(self):
        resolved = self.examples['resolved-recipe']
        self.rejects('UNKNOWN_ID', dataclasses.replace,resolved,scheduled_instances=resolved.scheduled_instances[:1])
        self.rejects('CONSTRAINT_CONFLICT', dataclasses.replace,resolved,transitions=(resolved.recipe.instances[0],))
        self.rejects('UNKNOWN_ID', dataclasses.replace,resolved,
                     source_map=(dataclasses.replace(resolved.source_map[0],clause_ids=('missing',)),))
        self.rejects('UNKNOWN_ID', dataclasses.replace,resolved,
                     parameter_bindings=(c.ParameterBinding('missing','angle','explicit',0),))
        self.rejects('CONSTRAINT_CONFLICT', dataclasses.replace,resolved,
                     ownership=resolved.ownership+(resolved.ownership[0],))

    def test_executable_requires_runtime_entry_bindings_without_fabricated_values(self):
        executable = self.examples['executable-motion']
        self.rejects('ENTRY_MISMATCH', dataclasses.replace,executable,runtime_entry_bindings=())
        self.rejects('ENTRY_MISMATCH', dataclasses.replace,executable,
                     runtime_entry_bindings=(dataclasses.replace(executable.runtime_entry_bindings[0],activation_s=.5),))
        self.rejects('INVALID_PARAMETER', dataclasses.replace,executable,
                     goal_checks=(dataclasses.replace(executable.goal_checks[0],interval=c.TimeInterval(0,2)),))
        self.rejects('INVALID_PARAMETER', dataclasses.replace,self.examples['frame-targets'],time_s=2)
        self.rejects('UNKNOWN_ID', dataclasses.replace,executable,
                     source_map=(dataclasses.replace(executable.source_map[0],output_id='missing'),))

    def test_resource_limits_and_finite_loops(self):
        recipe = self.examples['sequential-recipe']
        loop = self.examples['styled-loop-recipe'].loop
        self.rejects('RESOURCE_LIMIT', dataclasses.replace,recipe,instances=recipe.instances*65)
        self.rejects('RESOURCE_LIMIT', dataclasses.replace,recipe,loop=dataclasses.replace(loop,repetitions=65))
        self.rejects('INVALID_PARAMETER', dataclasses.replace,loop,repetitions=True)
        self.rejects('INVALID_PARAMETER', dataclasses.replace,loop,endpoint_tolerance_m=.02)
        self.rejects('INVALID_PARAMETER', dataclasses.replace,loop,
                     per_cycle_root_transform=dataclasses.replace(loop.per_cycle_root_transform,frame='world'))
        self.rejects('RESOURCE_LIMIT', c.Transform,(21,0,0),(1,0,0,0),'world','metre')
        self.rejects('RESOURCE_LIMIT', c.ControlValue,'hand.left.target','metre','world',(20,20,0))
        self.rejects('RESOURCE_LIMIT', c.ContactAnchor,'foot.left','floor',(21,0,0),'world','metre')
        self.rejects('INVALID_PARAMETER', dataclasses.replace,self.examples['executable-motion'],duration_s=61)
        self.rejects('RESOURCE_LIMIT', dataclasses.replace,self.examples['single-fragment'],
                     tracks=self.examples['single-fragment'].tracks*257)
        self.rejects('RESOURCE_LIMIT', c.ParameterValue,'vector',tuple(range(17)))
        data = c.to_dict(recipe)
        data['instances'] *= 65
        self.rejects('RESOURCE_LIMIT', c.from_dict,c.MotionRecipe,data)

    def test_generated_schemas_expose_exact_fields_units_bounds_and_defaults(self):
        schema = c.json_schema(c.MotionRecipe)
        self.assertEqual(schema['$defs']['MotionRecipe']['additionalProperties'], False)
        self.assertEqual(set(schema['$defs']['MotionRecipe']['required']), {f.name for f in dataclasses.fields(c.MotionRecipe)})
        parameters = r.parameter_schema(self.catalog.definitions['test.turn'])
        self.assertEqual(parameters['properties']['angle']['default'], 15)
        self.assertEqual(parameters['properties']['angle']['x-frame'], 'joint:head')
        self.assertEqual(parameters['properties']['angle']['x-unit'], 'degree')
        self.assertEqual(parameters['properties']['angle']['maximum'], 45)
        target = r.parameter_schema(self.catalog.definitions['test.target'])
        self.assertEqual(target['required'], ['target'])
        self.assertEqual(target['properties']['target']['minItems'], 3)

    def test_structured_error_context_and_distinct_unsupported_goal(self):
        error = c.MotionContractError('UNSUPPORTED_GOAL','No capability for clause',instance_id='i',
                                      control_id='head.yaw',details={'clause_id':'c'})
        self.assertEqual(error.to_dict(), {'code':'UNSUPPORTED_GOAL','message':'No capability for clause',
            'instance_id':'i','control_id':'head.yaw','details':{'clause_id':'c'}})
        self.assertIsInstance(error, PlanError)

    def test_legacy_action_plan_limit_remains_twelve_stages(self):
        from avatar_app.motion import ActionPlan, validate_action
        from avatar_app.planning.movements import crouch
        stages = tuple(dataclasses.replace(crouch(), id=f's{i}',duration=.2) for i in range(12))
        validate_action(ActionPlan(stages))
        with self.assertRaises(PlanError): validate_action(ActionPlan(stages+(dataclasses.replace(stages[0],id='s12'),)))


if __name__ == '__main__':
    unittest.main()
