import json
import unittest
from unittest.mock import patch
from avatar_app.models import PlanError
from avatar_app.motion import sample_controls, validate_action, scale_timing
from avatar_app.pose import update_pose
from avatar_app.planning.presets import PRESETS, preset_plan, gait_plan, wave_plan
from avatar_app.planning.routes import common_route
from avatar_app.planning.action_interpreter import decode_action, interpret_action


def response(kind='adapt', base=None, stages=(), factor=None, changes=None):
    return json.dumps({'kind': kind, 'base': base, 'stages': list(stages),
                      'changes': changes or {}, 'contact': None, 'factor': factor,
                      'message': 'Requested movement'})


class PresetTests(unittest.TestCase):
    def test_all_presets_have_bounded_reviewable_timelines(self):
        for name, _, _ in PRESETS:
            with self.subTest(name=name):
                plan = validate_action(preset_plan(name))
                self.assertLessEqual(len(plan.stages), 12)
                self.assertLessEqual(plan.duration, 60)
                self.assertEqual(plan.final_pose.get('grounding', 1), 1)

    def test_simple_aliases_need_no_model(self):
        with patch('avatar_app.planning.action_interpreter.get_model', side_effect=AssertionError('AI called')):
            for text in ('jumping', 'Jump once.', 'walking', 'walk forward 2 steps slowly',
                         'lying', 'running', 'run 4 steps', 'waving', 'wave with your left hand'):
                with self.subTest(text=text):
                    plan, _ = interpret_action(text)
                    self.assertGreater(len(plan.stages), 1)

    def test_creative_modifiers_still_use_general_interpretation(self):
        for text in ('walk backward and wave', 'jump and turn your head', 'wave like a conductor'):
            self.assertIsNone(common_route(text))

    def test_model_can_adapt_an_internal_foundation_for_novel_wording(self):
        class Model:
            def complete(self, messages, schema):
                self.payload = json.loads(messages[-1]['content'])
                if 'base' not in schema['required']:
                    raise AssertionError('Runtime schema must require a foundation selection or null')
                return response(base={'name':'jump'},
                    changes={'head':'left:25'})
        model = Model()
        plan, explanation = interpret_action('Hop once while glancing over your left shoulder.', model=model)
        original = preset_plan('jump')
        self.assertEqual(model.payload['request'], 'Hop once while glancing over your left shoulder.')
        self.assertEqual({b['name'] for b in model.payload['motion_foundations']},
                         {'jump','walk','lie','run','wave'})
        for stage, before in zip(plan.stages, original.stages):
            self.assertEqual({k:v for k,v in stage.targets if k != 'head_yaw'}, dict(before.targets))
            self.assertEqual(stage.contacts, before.contacts)
            self.assertEqual(stage.duration, before.duration)
        self.assertEqual(plan.duration, original.duration)
        self.assertEqual(plan.final_pose.get('head_yaw'), 25)
        self.assertEqual(explanation, 'Requested movement')

    def test_adaptation_parameters_and_timing_keep_one_new_revision(self):
        before = preset_plan('walk')
        original = wave_plan('left', 2)
        plan, _ = decode_action(response(base={'name':'wave', 'side':'left', 'waves':2}, factor=1.25), before)
        self.assertEqual(len(plan.stages), len(original.stages))
        self.assertEqual(plan.revision, before.revision+1)
        self.assertAlmostEqual(plan.duration, original.duration*1.25)
        for a, b in zip(original.stages, plan.stages):
            self.assertEqual(a.targets, b.targets)
            self.assertEqual(a.contacts[0].part, b.contacts[0].part)
            self.assertAlmostEqual(a.contacts[0].acquire/a.duration, b.contacts[0].acquire/b.duration)

    def test_follow_up_edits_preserve_the_current_animation(self):
        before = preset_plan('run')
        class Model:
            def complete(self, messages, schema):
                self.payload = json.loads(messages[-1]['content'])
                self.message_size = sum(len(m['content']) for m in messages)
                return response('edit', stages=[{'id':'flight_1', 'targets':{'head':'right:15'}}])
        model = Model()
        after, _ = interpret_action('Turn the head a little during the first stride.', before, model)
        self.assertEqual(model.payload['current_action']['description'], before.description)
        self.assertLess(model.message_size, 22000)
        self.assertEqual(after.initial, before.initial)
        self.assertEqual(after.stages[0], before.stages[0])
        self.assertEqual(after.stages[2:], before.stages[2:])
        self.assertEqual(after.stages[1].contacts, before.stages[1].contacts)

    def test_foundations_do_not_restrict_unfamiliar_actions(self):
        class Model:
            def complete(self, messages, schema):
                return response('action', stages=[
                    {'id':'curl', 'targets':{'torso':'forward:20', 'right_arm':'across:60'}, 'duration':2},
                    {'id':'unfurl', 'targets':{'torso':'forward:0', 'right_arm':'up'}, 'duration':2}])
        plan, _ = interpret_action('Curl and unfurl like a fern.', model=Model())
        self.assertEqual([s.id for s in plan.stages], ['curl','unfurl'])

    def test_invalid_adaptations_cannot_replace_a_result(self):
        before = preset_plan('walk')
        bad = [response(base={'name':'unknown'}), response(base={'name':'run', 'waves':2}),
               response(base={'name':'wave', 'side':'both'}), response(base={'name':'walk', 'steps':True}),
               response(base={'name':'jump'}, factor=0), response(base=None),
               response(base={'name':'jump'}, stages=[{'id':'unknown', 'targets':{'head':'left'}}]),
               response(base={'name':'jump'}, changes={'left_arm':'wave:1'}),
               response('edit', base={'name':'jump'}, stages=[{'id':'prepare', 'targets':{'head':'left'}}])]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(PlanError):
                decode_action(raw, before)
        self.assertEqual(before, preset_plan('walk'))

    def test_gaits_progress_and_have_distinct_support_patterns(self):
        walk, run = gait_plan(), gait_plan(running=True)
        self.assertGreater(run.final_pose.get('pelvis_forward'), walk.final_pose.get('pelvis_forward'))
        self.assertLess(run.duration, walk.duration)
        self.assertTrue(all(stage.contacts for stage in walk.stages))
        self.assertTrue(any(not stage.contacts for stage in run.stages))
        self.assertTrue(any(c.start > 0 for s in run.stages for c in s.contacts))
        self.assertEqual(walk.final_pose.contact, 'both')
        self.assertEqual(run.final_pose.contact, 'both')

    def test_jump_preserves_airborne_height_without_auto_grounding(self):
        plan = preset_plan('jump')
        apex = sample_controls(plan, plan.stages[0].duration+plan.stages[1].duration)
        self.assertEqual(apex['grounding'], 0)
        self.assertGreater(apex['left_foot_target_height'], .1)
        self.assertLess(apex['pelvis_drop'], 0)
        self.assertEqual(plan.final_pose.contact, 'both')

    def test_mirroring_and_new_revision(self):
        left = wave_plan('left', 2)
        self.assertTrue(all(k.startswith('left_') for stage in left.stages for k, _ in stage.targets))
        before = update_pose(None, {'head_yaw':30})
        self.assertEqual(preset_plan('wave', before).revision, before.revision+1)

    def test_partial_or_invalid_foot_targets_are_rejected(self):
        for changes in ({'left_foot_target_height': .1},
                        {'left_foot_target_side':0, 'left_foot_target_forward':0, 'left_foot_target_height':-.1}):
            with self.assertRaises(PlanError): update_pose(None, changes)
        with self.assertRaises(PlanError): gait_plan(steps=6)
        with self.assertRaises(PlanError): wave_plan('right', 6)
        with self.assertRaises(PlanError): preset_plan('dance')

    def test_slower_presets_keep_support_ramps_at_the_same_fraction(self):
        original = preset_plan('lie')
        slower = scale_timing(original, 1.25)
        for before, after in zip(original.stages, slower.stages):
            for a, b in zip(before.contacts, after.contacts):
                self.assertAlmostEqual(a.acquire/before.duration, b.acquire/after.duration)
                self.assertAlmostEqual(a.release/before.duration, b.release/after.duration)
