import json
import unittest
from avatar_app.models import PlanError
from avatar_app.pose import PosePlan, update_pose, validate_pose
from avatar_app.planning.pose_interpreter import decode_pose_response, interpret_pose, canonical_controls


def response(changes, kind='pose', contact=None):
    return json.dumps({'kind': kind, 'changes': changes, 'contact': contact, 'message': 'Requested posture'})


class PoseTests(unittest.TestCase):
    def test_semantic_directions_own_the_axis_conventions(self):
        plan, _ = decode_pose_response(response({'torso': 'forward:65', 'head': 'left:30',
                                                 'left_arm': 'up', 'right_arm': 'down'}), None)
        self.assertEqual(plan.get('torso_pitch'), 65)
        self.assertEqual(plan.get('head_yaw'), 30)
        self.assertEqual(plan.get('left_arm_elevation'), 180)
        self.assertEqual(plan.get('right_arm_elevation'), 0)

    def test_semantic_knee_bend_is_not_a_straight_kick(self):
        plan, _ = decode_pose_response(response({'right_thigh': 'forward', 'right_shin': 'down'}), None)
        self.assertEqual(plan.get('right_thigh_elevation'), 90)
        self.assertEqual(plan.get('right_thigh_azimuth'), 90)
        self.assertEqual(plan.get('right_shin_elevation'), 0)

    def test_contradictory_semantic_and_numeric_controls_rejected(self):
        with self.assertRaises(PlanError):
            canonical_controls({'torso': 'forward:65', 'torso_pitch': -65})

    def test_standard_body_part_aliases(self):
        controls = canonical_controls({'left_leg': 'down', 'right_knee': 'forward', 'right_lower_leg': 'down'})
        self.assertEqual(controls['left_thigh_elevation'], 0)
        self.assertEqual(controls['right_thigh_elevation'], 90)
        self.assertEqual(controls['right_shin_elevation'], 0)

    def test_lateral_directions_respect_character_left_and_right(self):
        controls = canonical_controls({'left_arm': 'right', 'right_thigh': 'right'})
        self.assertEqual(controls['left_arm_azimuth'], 180)
        self.assertEqual(controls['right_thigh_azimuth'], 0)

    def test_asymmetric_pose_is_representable(self):
        plan, _ = decode_pose_response(response({'right_arm_elevation': 90,
                                                 'right_forearm_elevation': 170}), None)
        self.assertEqual(plan.get('right_arm_elevation'), 90)
        self.assertEqual(plan.get('left_arm_elevation'), 0)

    def test_new_pose_resets_previous_unrelated_controls(self):
        before = update_pose(None, {'right_arm_elevation': 170, 'pelvis_drop': 0.2}, 'left')
        after, _ = decode_pose_response(response({'torso_pitch': 60}), before)
        self.assertEqual(after.get('right_arm_elevation'), 0)
        self.assertEqual(after.get('pelvis_drop'), 0)
        self.assertEqual(after.contact, 'auto')
        self.assertEqual(after.revision, before.revision + 1)

    def test_narrow_edit_preserves_every_unrelated_control(self):
        before = update_pose(None, {'right_arm_elevation': 90, 'duration': 3,
                                   'left_thigh_elevation': 80, 'left_shin_elevation': 0}, 'right')
        after, _ = decode_pose_response(response({'head_yaw': 45}, 'edit'), before)
        for key, value in before.values:
            self.assertEqual(after.get(key), value)
        self.assertEqual(after.contact, 'right')
        self.assertEqual(after.get('head_yaw'), 45)

    def test_rejects_invalid_controls_and_json(self):
        for raw in ('{}', '[]', 'not json', response({'left_arm_elevation': 200}),
                    response({'head_yaw': True}), response({'root_pitch': float('nan')}),
                    response({'python': 1}), response({}, 'edit'),
                    response({}, 'pose', 'arbitrary'),
                    '{"kind":"pose","kind":"edit","changes":{},"contact":null,"message":"x"}'):
            with self.subTest(raw=raw), self.assertRaises(PlanError):
                decode_pose_response(raw, None)

    def test_neutral_pose_needs_no_model(self):
        class NoModel:
            def complete(self, *args):
                raise AssertionError('Neutral pose must not require inference')
        plan, _ = interpret_pose('neutral pose', model=NoModel())
        self.assertEqual(plan.values, ())

    def test_human_pose_names_are_not_whitelisted(self):
        class Model:
            def complete(self, messages, schema):
                self.messages = messages
                return response({'left_arm_elevation': 135, 'torso_roll': 15})
        model = Model()
        plan, _ = interpret_pose('Pose as a conductor reaching toward a violinist.', model=model)
        self.assertEqual(plan.get('left_arm_elevation'), 135)
        self.assertIn('conductor', model.messages[-1]['content'])

    def test_rejected_request_cannot_mutate_pose(self):
        before = update_pose(None, {'head_yaw': 30})
        with self.assertRaises(PlanError):
            decode_pose_response(response({'head_yaw': 0}, 'unsupported'), before)
        self.assertEqual(before.get('head_yaw'), 30)

    def test_release_hand_target_without_resetting_other_controls(self):
        targets = {'right_hand_target_side': .08, 'right_hand_target_forward': .09,
                   'right_hand_target_height': .4}
        before = update_pose(None, {**targets, 'head_yaw': 30})
        after = update_pose(before, {**{name: None for name in targets}, 'right_arm_elevation': 180})
        self.assertEqual(after.get('head_yaw'), 30)
        self.assertFalse(any('hand_target' in name for name, _ in after.values))

    def test_incomplete_wrist_target_is_rejected(self):
        with self.assertRaises(PlanError):
            update_pose(None, {'right_hand_target_height': .4})

    def test_relaxed_arm_constraint_does_not_trust_incorrect_model_angles(self):
        class Model:
            def complete(self, *args):
                return response({'left_arm_elevation': 90, 'right_arm_elevation': 90,
                                 'torso_pitch': 60})
        plan, _ = interpret_pose('Bow with arms relaxed.', model=Model())
        self.assertEqual(plan.get('left_arm_elevation'), 0)
        self.assertEqual(plan.get('right_arm_elevation'), 0)
        self.assertEqual(plan.get('torso_pitch'), 60)

    def test_standing_constraint_rejects_accidental_inversion_and_floating_support(self):
        class Model:
            def complete(self, *args):
                return response({'root': 'backward:90', 'pelvis_drop': -.3,
                                 'left_leg': 'right', 'right_thigh': 'forward',
                                 'right_shin': 'down'}, contact='left')
        plan, _ = interpret_pose('Stand on your left leg and raise the right knee.', model=Model())
        self.assertEqual(plan.get('root_pitch'), 0)
        self.assertEqual(plan.get('pelvis_drop'), 0)
        self.assertEqual(plan.get('left_thigh_elevation'), 0)
        self.assertEqual(plan.get('right_thigh_elevation'), 90)


if __name__ == '__main__':
    unittest.main()
