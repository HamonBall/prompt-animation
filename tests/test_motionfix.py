import unittest
import json
from email.message import Message
from unittest.mock import patch
from avatar_app.motion import ActionPlan, Surface, sample_controls
from avatar_app.planning.movements import movement, lying_down_plan
from avatar_app.planning.action_interpreter import interpret_action, lying_example, decode_action
from avatar_app.planning.routes import check_route_destination
from avatar_app.planning.reference import PageText, load_reference
from avatar_app.models import PlanError


class MotionFixTests(unittest.TestCase):
    def test_shared_boundary_has_continuous_nonzero_velocity(self):
        plan = ActionPlan((movement('a', 'Lean', {'torso': 'forward:20'}, 1),
                           movement('b', 'Continue', {'torso': 'forward:40'}, 1)))
        h = .0001
        f = lambda t: sample_controls(plan, t)['torso_pitch']
        left, right = (f(1)-f(1-h))/h, (f(1+h)-f(1))/h
        self.assertGreater(left, 10)
        self.assertAlmostEqual(left, right, delta=.02)
        self.assertTrue(all(0 <= f(i/100) <= 40 for i in range(201)))

    def test_direction_reversal_stops_without_overshoot(self):
        plan = ActionPlan((movement('a', 'Lean', {'torso': 'forward:20'}, 1),
                           movement('b', 'Return', {'torso': 'forward:0'}, 1)))
        self.assertTrue(all(0 <= sample_controls(plan, i/100)['torso_pitch'] <= 20 for i in range(201)))

    def test_common_routes_do_not_require_local_model_and_have_support(self):
        with patch('avatar_app.planning.action_interpreter.get_model', side_effect=AssertionError('Slow inference')):
            plan, _ = interpret_action('Lie down on the floor.')
            self.assertTrue(any(c.part == 'pelvis' for c in plan.stages[1].contacts))
            self.assertTrue(any(c.part == 'back' for c in plan.stages[-1].contacts))
            seat = Surface('seat', .45, (0, -.38), (.6, .6))
            sitting, _ = interpret_action('Sit on the chair.', surfaces=(Surface(), seat))
            self.assertEqual(sitting.surfaces[1], seat)

    def test_missing_seat_and_wrong_destination_are_rejected(self):
        with self.assertRaises(PlanError):
            interpret_action('Sit on a chair.')
        bad = ActionPlan((movement('stand', 'Stand', {'torso': 'forward:0'}, 1),))
        with self.assertRaises(PlanError):
            check_route_destination(bad, 'Lie down through a crouch.')

    def test_try_anyway_can_approximate_an_unresolved_prop(self):
        class FakeModel:
            def complete(self, messages, schema):
                self.payload = json.loads(messages[-1]['content'])
                return json.dumps({'kind':'pose', 'stages':[], 'changes':{'torso':'forward:10'},
                    'contact':None, 'factor':None, 'message':'Approximate sitting without the chair.'})
        model = FakeModel()
        plan, _ = interpret_action('Sit on a chair.', model=model, approximate=True)
        self.assertTrue(model.payload['experimental_approximation'])
        self.assertEqual(plan.get('torso_pitch'), 10)

    def test_reference_example_uses_the_checked_route(self):
        plan, _ = decode_action(lying_example())
        self.assertEqual(plan.stages, lying_down_plan().stages)

    def test_semantic_guard_checks_static_destination_and_does_not_match_lay_a_hand(self):
        from avatar_app.pose import PosePlan
        with self.assertRaises(PlanError):
            check_route_destination(PosePlan(), 'Lie flat on your back.')
        check_route_destination(PosePlan(), 'Lay your hand on your chest.')

    def test_reference_markup_is_data_and_private_network_is_rejected(self):
        parser = PageText()
        parser.feed('<script>secret()</script><style>body{}</style><p>A kneeling posture.</p>')
        self.assertEqual(''.join(parser.parts), 'A kneeling posture.')
        for url in ('file:///C:/file', 'http://example.com', 'https://u:p@example.com'):
            with self.subTest(url=url), self.assertRaises(PlanError):
                load_reference(url)
        with patch('socket.getaddrinfo', return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(PlanError):
                load_reference('https://example.com')

    def test_public_reference_reads_bounded_text_and_keeps_its_source(self):
        class Response:
            headers = Message()
            headers['Content-Type'] = 'text/html; charset=utf-8'
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                self.limit = limit
                return b'<script>ignore</script><p>Hands rest beside the hips.</p>'
        response = Response()
        from unittest.mock import Mock
        opener = Mock()
        opener.open.return_value = response
        with patch('socket.getaddrinfo', return_value=[(2,1,6,'',('93.184.216.34',443))]), \
             patch('urllib.request.build_opener', return_value=opener):
            reference = load_reference('https://example.com/pose')
        self.assertEqual(reference, {'url':'https://example.com/pose', 'text':'Hands rest beside the hips.'})
        self.assertEqual(response.limit, 200001)
        self.assertEqual(opener.open.call_args.args[0].get_method(), 'GET')
