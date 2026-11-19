"""Plain-data composition using real registered movements on both rig profiles."""
from dataclasses import replace
from pathlib import Path
import unittest

from avatar_app.motion import Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment
from avatar_app.movement_library.composer import compose_recipe, schedule_instances
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.registry import validate_instance

ROOT = Path(__file__).parent / 'fixtures'


def context(rig='demo', case='lower-rise-neutral'):
    directory = ROOT / 'coordinated_body_moves/v1' / rig / case
    profile = c.loads(c.AvatarProfile, (directory / 'profile.json').read_text())
    entry = c.loads(c.MotionStateSnapshot, (directory / 'entry.json').read_text())
    return profile, entry, catalog_for_profile(profile)


def instance(profile, catalog, id, movement, **parameters):
    return validate_instance(c.MovementInstance(id, movement, 1,
                             tuple(c.ParameterValue(name, value) for name, value in parameters.items()),
                             (id + '.clause',)), profile, catalog)


def recipe(profile, entry, instances, relations=()):
    return c.MotionRecipe('recipe.test', profile.avatar_id, profile.version, entry.revision, 'new',
                          tuple(instances), tuple(relations), (), (), None,
                          tuple(c.ClauseCoverage(item.instance_id + '.clause', item.definition_id,
                                                'fulfilled', (item.instance_id,)) for item in instances))


class RecipeCompositionTests(unittest.TestCase):
    def setUp(self):
        self.profile, self.entry, self.catalog = context()

    def make(self, id, movement, **parameters):
        return instance(self.profile, self.catalog, id, movement, **parameters)

    def compose(self, value, entry=None):
        return compose_recipe(value, entry or self.entry, self.profile, (Surface(),), self.catalog)

    def rejection(self, code, fn):
        with self.assertRaises(c.MotionContractError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_parallel_walk_wave_look_both_rigs_and_non_neutral_entries(self):
        for rig in ('demo', 'mixamo'):
            for case in ('lower-rise-neutral', 'lower-rise-turned-crouched'):
                with self.subTest(rig=rig, case=case):
                    profile, entry, catalog = context(rig, 'step-left')
                    if case.endswith('turned-crouched'):
                        # Translation is a valid distinct measured entry; shift
                        # all world-space positions and captured anchors together.
                        delta = (.2, -.15, 0)
                        entry = replace(entry, root_transform=replace(entry.root_transform,
                            position=tuple(a+b for a,b in zip(entry.root_transform.position, delta))),
                            measured_controls=tuple(replace(value, value=tuple(a+b for a,b in zip(value.value, delta)))
                                if value.frame == 'world' and value.unit == 'metre' and isinstance(value.value, tuple) and len(value.value) == 3 else value
                                for value in entry.measured_controls),
                            contact_anchors=tuple(replace(anchor, position=tuple(a+b for a,b in zip(anchor.position, delta)))
                                                  for anchor in entry.contact_anchors))
                    items = (instance(profile, catalog, 'walk', 'body.step', side='left', distance_m=.06, clearance_m=.04),
                             instance(profile, catalog, 'wave', 'arm.stroke', side='right'),
                             instance(profile, catalog, 'look', 'head.look', yaw=15))
                    value = recipe(profile, entry, items)
                    before = c.dumps(value), c.dumps(entry)
                    resolved = compose_recipe(value, entry, profile, (Surface(),), catalog)
                    self.assertEqual(resolved, compose_recipe(value, entry, profile, (Surface(),), catalog))
                    self.assertTrue(all(item.interval.start_s == 0 for item in resolved.scheduled_instances))
                    self.assertEqual((c.dumps(value), c.dumps(entry)), before)
                    self.assertEqual(c.loads(c.ResolvedRecipe, c.dumps(resolved)), resolved)
                    self.assertEqual({source.output_id for source in resolved.source_map}, {'walk', 'wave', 'look'})

    def test_sequential_seat_gesture_inherits_support_without_fabricated_pose(self):
        for rig in ('demo', 'mixamo'):
            profile, entry, catalog = context(rig, 'standing-to-seated')
            items = (instance(profile, catalog, 'seat', 'body.floor_transfer', route='standing_to_seated'),
                     instance(profile, catalog, 'gesture', 'arm.stroke'))
            value = recipe(profile, entry, items, (c.Relation('then', 'after', 'seat', 'gesture', 0),))
            resolved = compose_recipe(value, entry, profile, (Surface(),), catalog)
            times = {item.instance_id: item.interval for item in resolved.scheduled_instances}
            self.assertEqual(times['gesture'].start_s, times['seat'].end_s)
            self.assertTrue(any('gesture' in event.source_instance_ids and event.anchor_id == 'pelvis.support'
                                for event in resolved.merged_contacts))
            binding = next(item for item in resolved.parameter_bindings if item.parameter_name == 'entry_state')
            self.assertEqual((binding.source, binding.value, binding.predecessor_id), ('measured_exit', None, 'seat'))
            self.assertEqual(resolved.transitions, ())

    def test_support_is_retained_before_delayed_step_and_after_seating_gap(self):
        profile, entry, catalog = context('demo', 'step-left')
        look = instance(profile, catalog, 'look', 'head.look')
        step = instance(profile, catalog, 'step', 'body.step', distance_m=.06, clearance_m=.04)
        value = recipe(profile, entry, (look, step), (c.Relation('delay', 'parallel', 'look', 'step', .5),))
        resolved = compose_recipe(value, entry, profile, (Surface(),), catalog)
        self.assertEqual({event.anchor_id for event in resolved.merged_contacts if event.interval.start_s == 0},
                         set(entry.active_contacts))

        profile, entry, catalog = context('demo', 'standing-to-seated')
        seat = instance(profile, catalog, 'seat', 'body.floor_transfer', route='standing_to_seated')
        arm = instance(profile, catalog, 'arm', 'arm.stroke')
        value = recipe(profile, entry, (seat, arm), (c.Relation('gap', 'after', 'seat', 'arm', .5),))
        resolved = compose_recipe(value, entry, profile, (Surface(),), catalog)
        times = {item.instance_id: item.interval for item in resolved.scheduled_instances}
        self.assertTrue(any(event.anchor_id == 'pelvis.support' and event.interval.start_s < times['seat'].end_s
                            and event.interval.end_s == times['arm'].end_s for event in resolved.merged_contacts))

    def test_event_offset_and_negative_after_overlap(self):
        a, b = self.make('a', 'head.look'), self.make('b', 'arm.stroke')
        fragments = {item.instance_id: build_fragment(item, self.entry, self.profile, (Surface(),), self.catalog)
                     for item in (a, b)}
        phase = next(item for item in fragments['a'].phase_landmarks if item.name == 'arrival')
        event = recipe(self.profile, self.entry, (a, b), (c.Relation('event', 'after_event', 'a', 'b', .1, 'arrival'),))
        resolved = self.compose(event)
        self.assertAlmostEqual(resolved.scheduled_instances[1].interval.start_s, phase.time_s + .1)
        self.assertEqual(resolved.resolution_v1.entry_bindings[1].source, 'measured_activation')
        self.assertFalse(any(binding.parameter_name == 'entry_state' for binding in resolved.parameter_bindings))
        overlap = replace(event, relations=(c.Relation('overlap', 'after', 'a', 'b', -.2),))
        schedule = schedule_instances(overlap, fragments)
        self.assertAlmostEqual(schedule[1].interval.start_s, fragments['a'].duration_s - .2)

    def test_physical_chain_conflict_names_instances(self):
        hold, path = self.make('hold', 'hand.hold'), self.make('path', 'arm.stroke')
        error = self.rejection('CONSTRAINT_CONFLICT', lambda: self.compose(recipe(self.profile, self.entry, (hold, path))))
        self.assertEqual(error.details['instance_ids'], ['hold', 'path'])
        self.assertTrue(error.details['chain'].startswith('left.'))

    def test_optional_swing_yields_only_chosen_arm_and_preserves_ids(self):
        swing = replace(self.make('swing', 'arm.swing', side='both'), clause_ids=())
        wave = self.make('wave', 'arm.stroke', side='left')
        value = recipe(self.profile, self.entry, (swing, wave))
        resolved = self.compose(value)
        self.assertTrue(any('swing' in item.source_instance_ids and item.chain_id.startswith('right.') for item in resolved.ownership))
        self.assertTrue(any('yields' in text for text in resolved.resolution_v1.explanations))
        self.assertEqual(resolved.recipe.instances, value.instances)

    def test_duplicate_contacts_merge_provenance(self):
        self.entry = replace(self.entry, active_contacts=('right.sole',))
        a, b = self.make('a', 'support.acquire_release', operation='acquire'), self.make('b', 'support.acquire_release', operation='acquire')
        resolved = self.compose(recipe(self.profile, self.entry, (a, b)))
        self.assertTrue(resolved.merged_contacts)
        self.assertTrue(all(event.source_instance_ids == ('a', 'b') for event in resolved.merged_contacts))

    def test_cycles_missing_ids_and_multiple_starts_reject(self):
        a, b = self.make('a', 'head.look'), self.make('b', 'arm.stroke')
        for relations, code in (
            ((c.Relation('a.b', 'after', 'a', 'b', 0), c.Relation('b.a', 'after', 'b', 'a', 0)), 'CONSTRAINT_CONFLICT'),
            ((c.Relation('missing', 'after', 'missing', 'b', 0),), 'UNKNOWN_ID'),
            ((c.Relation('one', 'after', 'a', 'b', 0), c.Relation('two', 'parallel', 'a', 'b', 0)), 'CONSTRAINT_CONFLICT'),
        ):
            self.rejection(code, lambda: recipe(self.profile, self.entry, (a, b), relations))

    def test_append_edit_and_stale_revision(self):
        value = recipe(self.profile, self.entry, (self.make('look', 'head.look'),))
        entry = replace(self.entry, captured_time_s=12)
        self.assertEqual(self.compose(replace(value, operation='append'), entry).scheduled_instances[0].interval.start_s, 12)
        self.assertEqual(self.compose(replace(value, operation='edit'), entry).scheduled_instances[0].interval.start_s, 0)
        self.rejection('STALE_REVISION', lambda: self.compose(replace(value, base_revision=value.base_revision + 1)))

    def test_missing_surface_and_invalid_entry_are_not_reset(self):
        value = recipe(self.profile, self.entry, (self.make('step', 'body.step'),))
        self.rejection('UNRESOLVED_SURFACE', lambda: compose_recipe(value, self.entry, self.profile, (), self.catalog))
        self.rejection('ENTRY_MISMATCH', lambda: self.compose(value, replace(self.entry, active_contacts=())))

    def test_time_budget_and_before_origin(self):
        a, b = self.make('a', 'head.look'), self.make('b', 'arm.stroke')
        for offset, code in ((60, 'RESOURCE_LIMIT'), (-60, 'CONSTRAINT_CONFLICT')):
            value = recipe(self.profile, self.entry, (a, b), (c.Relation('delay', 'parallel', 'a', 'b', offset),))
            self.rejection(code, lambda: self.compose(value))

    def test_incompatible_explicit_goals_and_unmapped_goal_reject(self):
        look = self.make('look', 'head.look')
        value = recipe(self.profile, self.entry, (look,))
        fragment = build_fragment(look, self.entry, self.profile, (Surface(),), self.catalog)
        track = fragment.tracks[0]
        goal = c.GoalSpec('goal.one', look.clause_ids[0],
                          c.ControlValue(track.control_id, track.unit, track.frame, track.curve.end_value),
                          c.TimeInterval(0, 1), .001)
        # Quaternion antipodes are equivalent, so use a different valid rotation.
        target = (1., 0., 0., 0.) if goal.target.value != (1., 0., 0., 0.) else (0., 1., 0., 0.)
        other = replace(goal, goal_id='goal.two', target=replace(goal.target, value=target))
        self.rejection('CONSTRAINT_CONFLICT', lambda: self.compose(replace(value, hard_goals=(goal, other))))
        arm = self.make('arm', 'arm.stroke')
        unmapped = recipe(self.profile, self.entry, (arm,))
        self.rejection('UNSUPPORTED_GOAL', lambda: self.compose(replace(unmapped,
            hard_goals=(replace(goal, clause_id=arm.clause_ids[0]),))))

    def test_fixture_publication_is_current(self):
        import json
        from publish_recipe_schedules import OUT, cases
        for name, value in cases():
            self.assertEqual(json.loads((OUT / name).read_text()), value)

    def test_legacy_resolved_fixture_roundtrip(self):
        path = ROOT / 'movement_contracts/v1/valid/resolved-recipe.json'
        original = path.read_text()
        value = c.loads(c.ResolvedRecipe, original)
        self.assertIsNone(value.resolution_v1)
        self.assertNotIn('resolution_v1', c.to_dict(value))


if __name__ == '__main__':
    unittest.main()
