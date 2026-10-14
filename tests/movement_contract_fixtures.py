"""Generate v1 handoff artifacts from Python contracts; never production content.

Run with PYTHONPATH=src: python tests/movement_contract_fixtures.py
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library import registry as r

FIXTURE_ROOT = Path(__file__).parent / 'fixtures' / 'movement_contracts' / 'v1'


def forbidden_builder(*args, **kwargs):
    raise AssertionError('Stage 02 validates data and must never execute a builder')


def test_catalog():
    profile = c.AvatarProfile(
        'test.avatar', 1, 1.8,
        ('world', 'entry_body', 'current_root', 'current_torso', 'current_pelvis', 'joint:head'),
        (c.JointMapping('root', None, ('Synthetic Root',),
                        c.Transform((0, 0, 0), (1, 0, 0, 0), 'world', 'metre')),
         c.JointMapping('head', 'root', ('Synthetic Head',),
                        c.Transform((0, 0, 1.6), (1, 0, 0, 0), 'world', 'metre'))),
        (c.LengthSpec('arm.left', .65),),
        (c.Landmark('foot.left', 'root', (-.1, 0, 0), 'world', 'metre'),),
        (c.JointLimit('head.yaw', -70, 70, 0, (0, 0, 1), None, 1,
                      'Synthetic test bounds; no anatomical calibration', -45, 45),),
        (c.ControlSpec('head.yaw', 'degree', 'scalar', 1, ('joint:head',), 'head', 'head.turn'),
         c.ControlSpec('hand.left.target', 'metre', 'vector', 3, ('world',), 'arm.left', 'endpoint.left'),
         c.ControlSpec('root.orientation', 'unitless', 'quaternion', 4, ('world',), 'root', 'root.orient')),
        ('head.turn', 'endpoint.left', 'root.orient'),
        c.Provenance('Synthetic test profile only', 'test-source-v1',
                     ('tests/test_movement_contracts.py',), '2026-10-14'))
    angle = c.ParameterSpec('angle', 'number', 'degree', 'joint:head', False, True, 15,
                            -45, 45, control_id='head.yaw')
    duration = c.ParameterSpec('duration_s', 'number', 'second', None, False, True, 1, .2, 8)
    target = c.ParameterSpec('target', 'vector', 'metre', 'world', True, False, None,
                             -20, 20, dimensions=3, control_id='hand.left.target')
    definitions = (
        c.MovementDefinition('test.turn', 1, 'joint', 'Test-only head turn contract',
                             (angle, duration), ('head.turn',), (), ('head',), (), (),
                             'test.builder', ('test_only',), ('arrival',)),
        c.MovementDefinition('test.target', 1, 'limb', 'Test-only endpoint contract',
                             (target, duration), ('endpoint.left',), (), ('arm.left',), (), (),
                             'test.builder', ('test_only',)),
        c.MovementDefinition('test.style', 1, 'style', 'Test-only style metadata',
                             (c.ParameterSpec('amount', 'number', 'unitless', None, False, True, .5, 0, 1),),
                             (), (), (), (), (), 'test.builder', ('test_only',)))
    catalog = r.Catalog({'test.builder': forbidden_builder})
    for definition in definitions:
        r.register_movement(definition, catalog)
    return profile, catalog


def records():
    profile, catalog = test_catalog()
    first = c.MovementInstance('turn.1', 'test.turn', 1, (c.ParameterValue('angle', 0),), ('clause.1',))
    second = c.MovementInstance('turn.2', 'test.turn', 1, (c.ParameterValue('angle', 25),), ('clause.2',))
    goal = c.GoalSpec('goal.1', 'clause.1', c.ControlValue('head.yaw', 'degree', 'joint:head', 0),
                      c.TimeInterval(.8, 1), 3)
    coverage = (c.ClauseCoverage('clause.1', 'Turn to zero', 'fulfilled', ('turn.1',)),
                c.ClauseCoverage('clause.2', 'Then turn to 25 degrees', 'fulfilled', ('turn.2',)))
    sequential = r.validate_recipe(c.MotionRecipe('recipe.sequence', profile.avatar_id, profile.version, 7, 'new',
        (first, second), (c.Relation('relation.1', 'after', 'turn.1', 'turn.2', 0),),
        (goal,), (), None, coverage), profile, catalog)
    target = c.MovementInstance('reach.1', 'test.target', 1,
                               (c.ParameterValue('target', (.2, .3, 1.2)),), ('clause.2',))
    parallel = r.validate_recipe(replace(sequential, recipe_id='recipe.parallel', instances=(first, target),
        relations=(c.Relation('relation.1', 'parallel', 'turn.1', 'reach.1', .25),),
        clause_coverage=(coverage[0], replace(coverage[1], source_clause='Reach alongside the turn',
                                              source_instance_ids=('reach.1',)))), profile, catalog)
    patch = c.RecipePatch(sequential.recipe_id, 7,
                          (c.InstancePatch('turn.2', (c.ParameterValue('angle', 20),)),), ('goal.1',))
    snapshot = c.MotionStateSnapshot(profile.avatar_id, 1, 7, 0,
        c.Transform((0, 0, 0), (1, 0, 0, 0), 'world', 'metre'),
        (c.ControlValue('head.yaw', 'degree', 'joint:head', -10),),
        (c.ContactAnchor('foot.left', 'floor', (-.1, 0, 0), 'world', 'metre'),), ('foot.left',))
    track = c.TrackSpec('track.1', ('turn.1',), 'head.yaw', 'degree', 'joint:head', 'scalar', 1,
                         c.CurveSpec('transition', None, 0, 1, 'smooth'), 'measured_entry', c.TimeInterval(0, 1))
    contact = c.ContactEvent('contact.1', ('turn.1',), 'foot.left', 'floor', c.TimeInterval(0, 1), .1, .1, .003)
    requirement = c.StateRequirement('entry.1', snapshot.measured_controls[0], 3)
    fragment = c.MotionFragment('fragment.1', ('turn.1',), (requirement,), 1, (track,), (contact,),
                                 (c.PhaseLandmark('arrival', 1),), (), (goal,))
    source = c.SourceMapEntry('track.1', ('turn.1',), ('clause.1',))
    resolved = c.ResolvedRecipe(sequential,
        (c.ScheduledInstance('turn.1', c.TimeInterval(0, 1)), c.ScheduledInstance('turn.2', c.TimeInterval(1, 2))),
        (c.ChainOwnership('head', ('turn.1',), c.TimeInterval(0, 1)),
         c.ChainOwnership('head', ('turn.2',), c.TimeInterval(1, 2))), (), (contact,),
        (c.ParameterBinding('turn.1', 'angle', 'explicit', 0),
         c.ParameterBinding('turn.2', 'entry_angle', 'measured_exit', None, 'turn.1')), (source,))
    executable = c.ExecutableMotion(snapshot, 1, 30, (track,), (contact,),
        (c.RuntimeEntryBinding('track.1', 'turn.1', 0, None),), (source,), None, (goal,))
    frame = c.FrameTargets(.9, (goal.target,), (contact,), snapshot.root_transform, ('turn.1',), (goal,), ())
    review = c.VerificationRecord('test.turn', 1, profile.avatar_id, 1,
        (replace(catalog.definitions['test.turn'].parameter_specs[0], minimum=-30, maximum=30),),
        ('Synthetic contract test; no rig-motion verification',),
        (c.ParameterValue('residual_deg', 0),), 'experimental')
    loop = c.LoopSpec(2, c.Transform((.1, 0, 0), (1, 0, 0, 0), 'entry_body', 'metre'), 3, .01, 10)
    styled = r.validate_recipe(replace(parallel, recipe_id='recipe.styled', loop=loop,
        optional_styles=(c.StyleRequest('test.style', 1, (), ('reach.1',), ('clause.2',)),)), profile, catalog)
    return {
        'avatar-profile': profile, 'definition-turn': catalog.definitions['test.turn'],
        'definition-target': catalog.definitions['test.target'], 'definition-style': catalog.definitions['test.style'],
        'sequential-recipe': sequential, 'parallel-recipe': parallel, 'narrow-patch': patch,
        'entry-snapshot': snapshot, 'single-fragment': fragment, 'resolved-recipe': resolved,
        'executable-motion': executable, 'frame-targets': frame, 'verification-envelope': review,
        'styled-loop-recipe': styled,
        'support-requirement': c.SupportRequirement('foot.left', 'floor', 'active'),
    }


def validate_fixture(record, context):
    profile, catalog = test_catalog()
    if type(record) is c.MotionRecipe: return r.validate_recipe(record, profile, catalog)
    if type(record) is c.RecipePatch: return r.validate_patch(record, context['sequential-recipe'], profile, catalog)
    if type(record) is c.MotionStateSnapshot: return r.validate_snapshot(record, profile)
    if type(record) is c.MotionFragment: return r.validate_fragment(record, profile, resolved_surface_ids=('floor',))
    if type(record) is c.VerificationRecord: return catalog.register_review(record, profile)
    if type(record) is c.MovementDefinition:
        fresh = r.Catalog({'test.builder': forbidden_builder})
        return r.register_movement(record, fresh)
    return record


def pretty(value):
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n'


def generated_files():
    examples = records()
    files, manifest = {}, {'schema_version': 1, 'valid': [], 'invalid': []}
    for name, record in examples.items():
        path = f'valid/{name}.json'
        files[path] = pretty(c.to_dict(record))
        manifest['valid'].append({'path': path, 'record_type': type(record).__name__})
    for name, record_type in sorted(c.RECORD_TYPES.items()):
        files[f'schemas/{name}.json'] = pretty(c.json_schema(record_type))
    _, catalog = test_catalog()
    for definition in catalog.definitions.values():
        files[f'schemas/parameters-{definition.id}.json'] = pretty(r.parameter_schema(definition))

    def invalid(name, original, error, change):
        value = deepcopy(c.to_dict(examples[original]))
        change(value)
        path = f'invalid/{name}.json'
        files[path] = pretty(value)
        manifest['invalid'].append({'path': path, 'record_type': type(examples[original]).__name__, 'error': error})

    def set_parameter(value, name, item):
        value['instances'][0]['parameters'] = [c.to_dict(c.ParameterValue(name, item))]
        value['instances'][0]['explicit_parameters'] = [name]

    invalid('unknown-definition', 'sequential-recipe', 'UNKNOWN_ID',
            lambda v: v['instances'][0].update(definition_id='missing.movement'))
    invalid('definition-version', 'sequential-recipe', 'VERSION_MISMATCH',
            lambda v: v['instances'][0].update(definition_version=2))
    invalid('unknown-parameter', 'sequential-recipe', 'INVALID_PARAMETER', lambda v: set_parameter(v, 'unknown', 1))
    invalid('boolean-as-number', 'sequential-recipe', 'INVALID_PARAMETER', lambda v: set_parameter(v, 'angle', True))
    invalid('wrong-parameter-type', 'sequential-recipe', 'INVALID_PARAMETER', lambda v: set_parameter(v, 'angle', 'left'))
    invalid('parameter-range', 'sequential-recipe', 'INVALID_PARAMETER', lambda v: set_parameter(v, 'angle', 90))
    invalid('schema-version', 'sequential-recipe', 'VERSION_MISMATCH', lambda v: v.update(schema_version=2))
    invalid('profile-version', 'sequential-recipe', 'VERSION_MISMATCH', lambda v: v.update(profile_version=2))
    invalid('unknown-frame', 'sequential-recipe', 'INVALID_PARAMETER',
            lambda v: v['hard_goals'][0]['target'].update(frame='camera'))
    invalid('unavailable-frame', 'sequential-recipe', 'INVALID_PARAMETER',
            lambda v: v['hard_goals'][0]['target'].update(frame='joint:missing'))
    invalid('incomplete-coordinates', 'parallel-recipe', 'INVALID_PARAMETER',
            lambda v: v['instances'][1]['parameters'][1].update(value=[.2, .3]))
    invalid('duplicate-instance', 'sequential-recipe', 'CONSTRAINT_CONFLICT',
            lambda v: v['instances'].append(deepcopy(v['instances'][0])))
    invalid('duplicate-parameter', 'sequential-recipe', 'CONSTRAINT_CONFLICT',
            lambda v: v['instances'][0]['parameters'].append(deepcopy(v['instances'][0]['parameters'][0])))
    invalid('unknown-serialized-field', 'sequential-recipe', 'INVALID_SCHEMA', lambda v: v.update(python='print(1)'))
    invalid('unknown-relation-source', 'sequential-recipe', 'UNKNOWN_ID',
            lambda v: v['relations'][0].update(source_instance_id='missing.instance'))
    invalid('stale-patch', 'narrow-patch', 'STALE_REVISION', lambda v: v.update(base_revision=6))
    invalid('missing-capability', 'avatar-profile', 'MISSING_CAPABILITY', lambda v: v.update(capabilities=[]))
    invalid('bad-quaternion', 'entry-snapshot', 'INVALID_PARAMETER',
            lambda v: v['root_transform'].update(orientation=[0, 0, 0, 0]))
    invalid('incomplete-transform', 'entry-snapshot', 'INVALID_SCHEMA',
            lambda v: v['root_transform'].update(position=[0, 0]))
    # Generated nonfinite payload: deliberately invalid JSON, rejected at parsing.
    path = 'invalid/nonfinite-number.json'
    files[path] = files['valid/sequential-recipe.json'].replace('"value": 0', '"value": NaN', 1)
    manifest['invalid'].append({'path': path, 'record_type': 'MotionRecipe', 'error': 'INVALID_SCHEMA'})
    files['manifest.json'] = pretty(manifest)
    return files


if __name__ == '__main__':
    output = generated_files()
    for relative, contents in output.items():
        path = FIXTURE_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding='utf-8', newline='\n')
    print(f'Generated {len(output)} files in {FIXTURE_ROOT}')
