"""Stage 07 compiler checks using published measured entry data."""
from dataclasses import replace
import math
import unittest

from avatar_app.motion import Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import (
    ExecutionCursor, build_fragment, compile_recipe, prepare_fragment, prepare_recipe_activation, sample_motion,
)
from avatar_app.movement_library.composer import compose_recipe, schedule_instances
from test_recipe_composition import context, instance, recipe


class MotionCompilerTests(unittest.TestCase):
    def test_execution_expansion_budgets_reject_before_scene_access(self):
        profile, entry, catalog = context()
        first = instance(profile, catalog, 'first', 'head.look')
        second = instance(profile, catalog, 'second', 'head.look')
        value = recipe(profile, entry, (first, second))
        surfaces = (Surface(),)
        planned = {move.instance_id: build_fragment(move, entry, profile, surfaces, catalog)
                   for move in (first, second)}

        def rejects(fn):
            with self.assertRaises(c.MotionContractError) as result:
                fn()
            self.assertEqual(result.exception.code, 'RESOURCE_LIMIT')

        rejects(lambda: replace(value, instances=(first,) * (c.MAX_INSTANCES + 1)))
        rejects(lambda: schedule_instances(value, planned, origin_s=59))
        source = planned['first']
        track = source.tracks[0]
        tracks = tuple(replace(track, track_id=f'track.{index}', control_id=f'control.{index}')
                       for index in range(c.MAX_TRACKS))
        rejects(lambda: schedule_instances(value, {**planned, 'first': replace(source, tracks=tracks)}))
        contact = source.contact_events[0]
        contacts = tuple(replace(contact, event_id=f'contact.{index}', anchor_id=f'anchor.{index}')
                         for index in range(c.MAX_CONTACTS))
        rejects(lambda: schedule_instances(value, {**planned, 'first': replace(source, contact_events=contacts)}))

    def test_thirteen_recipe_instances_use_the_typed_timeline(self):
        profile, entry, catalog = context()
        items = tuple(instance(profile, catalog, f'look.{index}', 'head.look', yaw=10*(-1)**index,
                               hold_s=0.) for index in range(13))
        relations = tuple(c.Relation(f'then.{i}', 'after', first.instance_id, second.instance_id, 0)
                          for i, (first, second) in enumerate(zip(items, items[1:])))
        value = recipe(profile, entry, items, relations)
        resolved = compose_recipe(value, entry, profile, (Surface(),), catalog)
        result = compile_recipe(resolved, entry, profile, catalog=catalog)
        self.assertEqual((result.duration_s, len(result.recipe_activation_v1)), (13, 12))
        self.assertEqual(c.loads(c.ExecutableMotion, c.dumps(result)), result)

    def test_append_uses_measured_end_as_its_local_time_origin(self):
        profile, entry, catalog = context()
        entry = replace(entry, captured_time_s=12.25)
        first = instance(profile, catalog, 'first', 'head.look', hold_s=0.)
        second = instance(profile, catalog, 'second', 'head.look', hold_s=0.)
        value = replace(recipe(profile, entry, (first, second), (c.Relation('then', 'after', 'first', 'second', 0),)),
                        operation='append')
        resolved = compose_recipe(value, entry, profile, (Surface(),), catalog)
        motion = compile_recipe(resolved, entry, profile, catalog=catalog)
        self.assertEqual(resolved.scheduled_instances[0].interval.start_s, 12.25)
        self.assertEqual(motion.entry_snapshot, entry)
        self.assertEqual(motion.recipe_activation_v1[0].time_s, 1.)
        self.assertEqual(motion.duration_s, 2.)

    def test_off_grid_delayed_activation_rejects_before_baking(self):
        profile, entry, catalog = context()
        first = instance(profile, catalog, 'first', 'head.look', hold_s=0.)
        second = instance(profile, catalog, 'second', 'head.look', hold_s=0.)
        value = recipe(profile, entry, (first, second), (c.Relation('then', 'after', 'first', 'second', .01),))
        resolved = compose_recipe(value, entry, profile, (Surface(),), catalog)
        with self.assertRaises(c.MotionContractError) as raised:
            compile_recipe(resolved, entry, profile, catalog=catalog)
        self.assertEqual(raised.exception.code, 'UNSUPPORTED_GOAL')

    def test_activation_rebuild_preserves_measured_head_pose_and_rejects_changed_topology(self):
        profile, entry, catalog = context()
        surfaces = (Surface(),)
        first = instance(profile, catalog, 'first', 'head.look', yaw=10, hold_s=0.)
        second = instance(profile, catalog, 'second', 'head.look', yaw=-10, hold_s=0.)
        initial = build_fragment(first, entry, profile, surfaces, catalog)
        planned = build_fragment(second, entry, profile, surfaces, catalog)
        track = initial.tracks[-1]
        measured = replace(entry, captured_time_s=initial.duration_s, measured_controls=tuple(
            replace(value, value=track.curve.end_value) if value.control_id == track.control_id else value
            for value in entry.measured_controls))
        continuation = prepare_recipe_activation(second, planned, measured, profile, surfaces, catalog)
        sampled = sample_motion(continuation, 0, measured, ExecutionCursor())
        for actual, expected in zip(sampled.controls[0].value, track.curve.end_value, strict=True):
            self.assertAlmostEqual(actual, expected, places=12)
        self.assertNotEqual(continuation.tracks[0].curve.start_value, planned.tracks[0].curve.start_value)
        with self.assertRaises(c.MotionContractError) as changed:
            prepare_recipe_activation(second, planned, replace(measured, active_contacts=()), profile, surfaces, catalog)
        self.assertEqual(changed.exception.code, 'ENTRY_MISMATCH')

    def test_parallel_gesture_and_look_share_one_sampler(self):
        for rig in ('demo', 'mixamo'):
            with self.subTest(rig=rig):
                profile, entry, catalog = context(rig, 'lower-rise-turned-crouched')
                look = instance(profile, catalog, 'look', 'head.look', yaw=15)
                wave = instance(profile, catalog, 'wave', 'arm.stroke', side='right')
                value = recipe(profile, entry, (wave, look),
                               (c.Relation('while', 'parallel', 'wave', 'look', 0),))
                resolved = compose_recipe(value, entry, profile, (Surface(),), catalog)
                compiled = compile_recipe(resolved, entry, profile, catalog=catalog)
                cursor = ExecutionCursor()
                frame = sample_motion(compiled, 0, entry, cursor)
                self.assertEqual(set(frame.source_instance_ids), {'look', 'wave'})
                self.assertEqual(len(frame.active_contacts), len(entry.active_contacts))
                self.assertTrue(any(value.control_id.startswith('head.') for value in frame.controls))
                self.assertTrue(any(value.control_id.startswith('right.') for value in frame.controls))
                self.assertEqual(set(compiled.contact_events), set(resolved.merged_contacts))

    def test_one_instance_matches_the_direct_fragment_at_every_sample(self):
        for rig in ('demo', 'mixamo'):
            with self.subTest(rig=rig):
                profile, entry, catalog = context(rig, 'lower-rise-turned-crouched')
                move = instance(profile, catalog, 'test.look', 'head.look', yaw=15)
                value = recipe(profile, entry, (move,))
                surfaces = (Surface(),)
                resolved = compose_recipe(value, entry, profile, surfaces, catalog)
                direct = prepare_fragment(build_fragment(move, entry, profile, surfaces, catalog), entry, profile)
                compiled = compile_recipe(resolved, entry, profile, surfaces=surfaces, catalog=catalog)
                self.assertEqual(replace(compiled, source_map=direct.source_map, recipe_surfaces_v1=None), direct)
                self.assertTrue(all(move.clause_ids[0] in source.clause_ids for source in compiled.source_map))
                direct_cursor, compiled_cursor = ExecutionCursor(), ExecutionCursor()
                for frame in range(math.ceil(compiled.duration_s * compiled.fps) + 1):
                    time_s = min(frame / compiled.fps, compiled.duration_s)
                    self.assertEqual(sample_motion(direct, time_s, entry, direct_cursor),
                                     sample_motion(compiled, time_s, entry, compiled_cursor))

    def test_stale_revision_and_changed_schedule_fail_before_sampling(self):
        profile, entry, catalog = context()
        move = instance(profile, catalog, 'test.look', 'head.look')
        value = recipe(profile, entry, (move,))
        resolved = compose_recipe(value, entry, profile, (Surface(),), catalog)
        with self.assertRaises(c.MotionContractError) as stale:
            compile_recipe(resolved, replace(entry, revision=entry.revision + 1), profile)
        self.assertEqual(stale.exception.code, 'STALE_REVISION')
        schedule = resolved.scheduled_instances[0]
        edited = replace(resolved, scheduled_instances=(replace(schedule, interval=replace(
            schedule.interval, end_s=schedule.interval.end_s + .1)),))
        with self.assertRaises(c.MotionContractError) as mismatch:
            compile_recipe(edited, entry, profile, catalog=catalog)
        self.assertEqual(mismatch.exception.code, 'ENTRY_MISMATCH')
