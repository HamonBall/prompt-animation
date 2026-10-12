import json
import unittest
from dataclasses import replace
from avatar_app.models import PlanError
from avatar_app.motion import (ActionPlan, ContactConstraint, Surface, sample_controls,
                              validate_action, patch_stages, scale_timing, schedule)
from avatar_app.planning.movements import (movement, crouch, lying_down_plan, sitting_plan,
                                          construct_movement, AvatarMeasurements)
from avatar_app.planning.action_interpreter import decode_action, interpret_action


def reply(kind, stages=None, changes=None, factor=None):
    return json.dumps({'kind': kind, 'stages': stages or [], 'changes': changes or {},
                       'contact': None, 'factor': factor, 'message': 'Checked request'})


class MotionTests(unittest.TestCase):
    def test_reference_route_has_support_transfers_and_reuses_crouch(self):
        plan = lying_down_plan()
        self.assertEqual(plan.stages[0], crouch(duration=2))
        self.assertEqual(sitting_plan().stages[0].action, crouch().action)
        self.assertEqual(len(plan.stages), 4)
        self.assertEqual(plan.final_pose.get('root_pitch'), -90)
        self.assertEqual(plan.final_pose.get('left_thigh_elevation'), 0)
        self.assertEqual({c.part for c in plan.stages[2].contacts}, {'pelvis', 'left_hand', 'right_hand'})

    def test_common_movement_interface_carries_start_and_end_state(self):
        from avatar_app.pose import update_pose
        before = update_pose(None, {'head_yaw': 25})
        segment = construct_movement(before, AvatarMeasurements(1.8, .85), {'right_arm': 'up'}, 1)
        self.assertEqual(segment.starting_state, before)
        self.assertEqual(segment.ending_state.get('head_yaw'), 25)
        self.assertEqual(segment.ending_state.get('right_arm_elevation'), 180)

    def test_composer_carries_end_state_and_blends_disjoint_overlap(self):
        a = movement('a', 'Reach', {'right_arm': 'up'}, 2)
        b = movement('b', 'Turn head', {'head': 'left:40'}, 2, start=1)
        plan = validate_action(ActionPlan((a, b)))
        values = sample_controls(plan, 2)
        self.assertEqual(values['right_arm_elevation'], 180)
        self.assertEqual(values['head_yaw'], 20)
        self.assertEqual(plan.duration, 3)

    def test_airborne_flag_is_discrete_and_does_not_wait_until_final_frame(self):
        plan = validate_action(ActionPlan((movement('rise', 'Float upward',
            {'pelvis_drop': -.2, 'grounding': 0}, 1),)))
        self.assertEqual(sample_controls(plan, .1)['grounding'], 0)

    def test_overlapping_control_ownership_is_rejected(self):
        with self.assertRaises(PlanError):
            validate_action(ActionPlan((movement('a', 'Reach', {'right_arm': 'up'}, 2),
                movement('b', 'Lower', {'right_arm': 'down'}, 2, start=1))))

    def test_patch_changes_only_named_stage_and_preserves_timing_contacts(self):
        before = lying_down_plan()
        after = patch_stages(before, [{'id': 'lower', 'targets': {'head_yaw': 20}}])
        self.assertEqual(after.stages[0], before.stages[0])
        self.assertEqual(after.stages[3], before.stages[3])
        self.assertEqual(after.stages[2].contacts, before.stages[2].contacts)
        self.assertEqual(after.duration, before.duration)
        self.assertEqual(dict(after.stages[2].targets)['head_yaw'], 20)

    def test_slowing_preserves_geometry_and_scales_overlap(self):
        before = validate_action(ActionPlan((movement('a', 'Reach', {'right_arm': 'up'}, 1),
            movement('b', 'Look', {'head': 'left:30'}, 1, start=.5))))
        after = scale_timing(before, 2)
        self.assertEqual(after.duration, before.duration * 2)
        self.assertEqual(after.stages[1].start, 1)
        self.assertEqual(after.stages[0].targets, before.stages[0].targets)

    def test_unresolved_object_is_rejected(self):
        stage = replace(crouch(), contacts=(ContactConstraint('pelvis', 'chair'),))
        with self.assertRaises(PlanError):
            validate_action(ActionPlan((stage,)))

    def test_invalid_intervals_targets_and_revisions(self):
        good = crouch()
        for stage in (replace(good, duration=True), replace(good, duration=float('nan')),
                      replace(good, start=-1), replace(good, targets=(('python', 1),)),
                      replace(good, contacts=(ContactConstraint('left_foot', start=.7, end=.2),)),
                      replace(good, completion=('physical_balance',))):
            with self.subTest(stage=stage), self.assertRaises(PlanError):
                validate_action(ActionPlan((stage,)))

    def test_ai_can_describe_unlisted_creative_sequence(self):
        plan, _ = decode_action(reply('action', [
            {'id': 'open', 'action': 'Reach like a conductor', 'targets': {'right_arm': 'up'}, 'duration': 1},
            {'id': 'look', 'action': 'Look over shoulder', 'targets': {'head': 'left:60'}, 'duration': 1}]))
        self.assertEqual(len(plan.stages), 2)
        self.assertEqual(plan.final_pose.get('head_yaw'), 60)

    def test_new_motion_begins_from_current_pose(self):
        from avatar_app.pose import update_pose
        before = update_pose(None, {'head_yaw': 25})
        plan, _ = decode_action(reply('action', [
            {'id': 'reach', 'action': 'Reach', 'targets': {'right_arm': 'up'}, 'duration': 1}]), before)
        self.assertEqual(plan.initial.get('head_yaw'), 25)
        self.assertEqual(plan.final_pose.get('head_yaw'), 25)

    def test_ai_patch_and_timing_preserve_existing_sequence(self):
        before = lying_down_plan()
        after, _ = decode_action(reply('edit', [{'id': 'lower', 'targets': {'head': 'left:30'}}]), before)
        self.assertEqual(after.stages[0], before.stages[0])
        slow, _ = decode_action(reply('timing', factor=1.2), after)
        self.assertAlmostEqual(slow.duration, after.duration * 1.2)

    def test_malformed_or_ambiguous_results_cannot_replace_action(self):
        before = lying_down_plan()
        for raw in ('{}', reply('edit', [{'id': 'nonexistent', 'targets': {'head': 'left'}}]),
                    reply('pose_edit', changes={'head': 'left'}), reply('clarify', changes={'head': 'left'}),
                    reply('action', [{'id': 'a', 'targets': {'head': 'left'}, 'duration': 100}])):
            with self.subTest(raw=raw), self.assertRaises(PlanError):
                decode_action(raw, before)

    def test_neutral_remains_offline_and_model_gets_current_stages(self):
        class Model:
            def complete(self, messages, schema):
                self.payload = json.loads(messages[-1]['content'])
                return reply('timing', factor=1.1)
        model = Model()
        plan, _ = interpret_action('neutral pose', model=model)
        self.assertEqual(plan.values, ())
        before = lying_down_plan()
        after, _ = interpret_action('Do it more slowly.', before, model)
        self.assertEqual(model.payload['current_action']['stages'][0]['id'], 'crouch')
        self.assertAlmostEqual(after.duration, before.duration * 1.1)


if __name__ == '__main__':
    unittest.main()
