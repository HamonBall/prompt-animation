import json
import unittest
from dataclasses import asdict
from unittest.mock import patch
from avatar_app.models import MotionPlan, PlanError
from avatar_app.planning.ai import decode_response, interpret_ai, interpret_request
from avatar_app.planning.local_model import LocalModel


def response(changes, kind='edit'):
    return json.dumps({'kind': kind, 'changes': changes, 'message': 'Test interpretation.'})


def change(field, value, operation='add'):
    return {'field': field, 'value': value, 'operation': operation}


class FakeModel:
    def __init__(self, raw):
        self.raw = raw
        self.messages = None

    def complete(self, messages, schema):
        self.messages = messages
        return self.raw


class AITests(unittest.TestCase):
    def test_relative_edits_preserve_other_fields(self):
        before = MotionPlan(duration=3, arm_lift=0.2, revision=7)
        after, _ = decode_response(response([change('crouch', 0.03)]), before)
        self.assertAlmostEqual(after.crouch, 0.11)
        self.assertEqual(after.duration, 3)
        self.assertEqual(after.arm_lift, 0.2)
        self.assertEqual(after.revision, 8)

    def test_multiple_edits_and_multiplication(self):
        result, _ = decode_response(response([change('duration', 2, 'multiply'),
                                              change('arm_lift', 0.1)]), MotionPlan())
        self.assertEqual(result.duration, 4)
        self.assertEqual(result.arm_lift, 0.1)
        self.assertEqual(result.crouch, 0.08)

    def test_rejects_bad_model_payloads(self):
        bad = ['not JSON', '[]', '{}', response([change('action', 1)]),
               response([change('duration', True)]), response([change('duration', '3')]),
               response([change('crouch', float('nan'))]),
               response([change('crouch', 0.03), change('crouch', 0.01)]),
               response([change('duration', 99, 'set')]),
               response([], kind='create'), response([], kind='edit'),
               '{"kind":"edit","kind":"edit","changes":[],"message":"bad"}']
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(PlanError):
                decode_response(raw, MotionPlan())

    def test_create_does_not_increment_revision(self):
        result, _ = decode_response(response([change('duration', 3, 'set')], 'create'), None)
        self.assertEqual(result.duration, 3)
        self.assertEqual(result.revision, 0)

    def test_unsupported_and_clarification_do_not_make_a_plan(self):
        for kind in ('unsupported', 'clarify'):
            with self.assertRaisesRegex(PlanError, 'Test interpretation'):
                decode_response(response([], kind), MotionPlan())

    def test_exact_commands_bypass_model(self):
        model = FakeModel('must not be used')
        after, source = interpret_request('crouch lower', MotionPlan(), model)
        self.assertAlmostEqual(after.crouch, 0.11)
        self.assertIsNone(model.messages)
        self.assertEqual(source, 'Direct command')

    def test_exact_command_boundaries_do_not_fall_back_to_ai(self):
        model = FakeModel('must not be used')
        with self.assertRaises(PlanError):
            interpret_request('crouch lower', MotionPlan(crouch=0.2), model)
        self.assertIsNone(model.messages)

    def test_current_plan_and_text_sent_as_data(self):
        model = FakeModel(response([change('arm_lift', 0.1)]))
        current = MotionPlan(revision=8)
        interpret_request('Could you raise both arms a little?', current, model)
        payload = json.loads(model.messages[-1]['content'])
        self.assertEqual(payload['current_plan'], asdict(current))
        self.assertEqual(payload['request'], 'Could you raise both arms a little?')

    def test_negation_never_becomes_positive_motion(self):
        model = FakeModel(response([change('crouch', 0.03)]))
        with self.assertRaises(PlanError):
            interpret_ai('Do not crouch lower.', MotionPlan(), model)
        self.assertIsNone(model.messages)

    def test_independent_preservation_check(self):
        for text in ('Keep the speed and arms the same, but crouch lower.',
                     'Crouch lower without changing the arm position.'):
            model = FakeModel(response([change('crouch', 0.03), change('arm_lift', 0.1)]))
            with self.subTest(text=text), self.assertRaisesRegex(PlanError, 'preserve'):
                interpret_ai(text, MotionPlan(), model)

    def test_explicit_duration_cannot_be_silently_misread(self):
        model = FakeModel(response([change('duration', 4, 'set')]))
        with self.assertRaisesRegex(PlanError, 'duration'):
            interpret_ai('Make it last twenty seconds.', MotionPlan(), model)

    def test_summary_comes_from_actual_values(self):
        model = FakeModel(response([change('crouch', 0.03)]))
        plan, summary = interpret_ai('Sink a little lower.', MotionPlan(), model)
        self.assertIn('11%', summary)
        self.assertNotIn('Test interpretation', summary)

    def test_missing_runtime_is_an_explained_failure(self):
        client = LocalModel()
        with patch('avatar_app.planning.local_model.MODEL') as model:
            model.is_file.return_value = False
            with self.assertRaisesRegex(PlanError, 'not installed'):
                client.start()
        client.close()

    def test_truncated_or_unavailable_inference(self):
        for result in ({'choices': [{'finish_reason': 'length'}]}, {}):
            client = LocalModel()
            with patch.object(client, 'start'), patch.object(client, '_request', return_value=result):
                with self.assertRaises(PlanError):
                    client.complete([], {})
            client.close()


if __name__ == '__main__':
    unittest.main()
