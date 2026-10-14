"""Validation/preservation assertions migrated to the active pose/action path."""
import json
import unittest
from dataclasses import asdict
from avatar_app.models import PlanError
from avatar_app.motion import serialize_action
from avatar_app.pose import update_pose
from avatar_app.planning.action_interpreter import decode_action, interpret_action
from avatar_app.planning.presets import preset_plan
from avatar_app.planning.routes import common_route


def response(kind, *, stages=(), changes=None, factor=None, message='Test interpretation'):
    return json.dumps({'kind':kind, 'base':None, 'stages':list(stages),
                      'changes':changes or {}, 'contact':None, 'factor':factor, 'message':message})


class Model:
    def __init__(self, raw): self.raw = raw
    def complete(self, messages, schema):
        self.messages = messages
        return self.raw


class ActionValidationTests(unittest.TestCase):
    def test_creation_and_multifield_patch_preserve_unrelated_data(self):
        created, _ = decode_action(response('action', stages=[
            {'id':'reach', 'targets':{'left_arm':'up'}, 'duration':2}]))
        self.assertEqual(created.revision, 0)
        before = preset_plan('jump')
        snapshot = asdict(before)
        after, _ = decode_action(response('edit', stages=[
            {'id':'takeoff', 'targets':{'head':'left:25'}, 'duration':.6}]), before)
        self.assertEqual(after.revision, before.revision+1)
        self.assertEqual(after.stages[0], before.stages[0])
        self.assertEqual(after.stages[2:], before.stages[2:])
        self.assertEqual(after.stages[1].contacts, before.stages[1].contacts)
        self.assertEqual(dict(after.stages[1].targets)['head_yaw'], 25)
        self.assertEqual(after.stages[1].duration, .6)
        self.assertEqual(asdict(before), snapshot)

    def test_request_and_current_action_are_quoted_data(self):
        before = preset_plan('jump')
        text = 'Look left, keeping the jump. "Quoted text"\nReturn no executable code.'
        model = Model(response('edit', stages=[{'id':'prepare', 'targets':{'head':'left:15'}}]))
        interpret_action(text, before, model=model)
        payload = json.loads(model.messages[-1]['content'])
        self.assertEqual(payload['request'], text)
        self.assertEqual(payload['current_action'], json.loads(json.dumps(serialize_action(before))))
        self.assertEqual(model.messages[-1]['role'], 'user')

    def test_malformed_duplicate_nonfinite_or_wrong_type_replies_are_rejected(self):
        before = preset_plan('jump')
        snapshot = asdict(before)
        valid = response('edit', stages=[{'id':'prepare', 'targets':{'head_yaw':20}}])
        bad = ['not JSON', '[]', '{}', valid.replace('"head_yaw": 20', '"head_yaw": 20, "head_yaw": 30'),
               valid.replace('"kind": "edit"', '"kind": "edit", "kind": "edit"'),
               response('edit', stages=[{'id':'prepare', 'targets':{'python':1}}])]
        for value in (True, '20', float('nan'), float('inf'), 999):
            bad.append(response('edit', stages=[{'id':'prepare', 'targets':{'head_yaw':value}}]))
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(PlanError): decode_action(raw, before)
        self.assertEqual(asdict(before), snapshot)

    def test_rejected_requests_and_invalid_stage_patches_keep_the_original(self):
        before = preset_plan('jump')
        snapshot = asdict(before)
        for kind in ('clarify', 'unsupported'):
            with self.assertRaisesRegex(PlanError, 'Test interpretation'):
                decode_action(response(kind), before)
            with self.assertRaises(PlanError):
                decode_action(response(kind, changes={'head_yaw':20}), before)
        for rows in ([{'id':'missing', 'targets':{'head':'left'}}],
                     [{'id':'prepare', 'targets':{'head':'left'}}, {'id':'prepare', 'targets':{}}],
                     [{'id':'prepare', 'targets':{}, 'duration':0}],
                     [{'id':'prepare', 'targets':{}, 'duration':20}]):
            with self.subTest(rows=rows), self.assertRaises(PlanError):
                decode_action(response('edit', stages=rows), before)
        with self.assertRaises(PlanError):
            decode_action(response('edit', stages=[{'id':'prepare', 'targets':{'head':'left'}}]))
        self.assertIsNone(common_route('Do not jump.'))
        with self.assertRaises(PlanError):
            interpret_action('Do not jump.', before, model=Model(response('clarify')))
        self.assertEqual(asdict(before), snapshot)

    def test_timing_edit_preserves_geometry_contacts_and_contact_ramp_fractions(self):
        before = preset_plan('lie')
        after, _ = decode_action(response('timing', factor=1.2), before)
        self.assertEqual(after.initial, before.initial)
        self.assertAlmostEqual(after.duration, before.duration*1.2)
        for a, b in zip(before.stages, after.stages):
            self.assertEqual(a.targets, b.targets)
            for c, d in zip(a.contacts, b.contacts):
                self.assertEqual((c.part,c.surface,c.start,c.end,c.position), (d.part,d.surface,d.start,d.end,d.position))
                self.assertAlmostEqual(c.acquire/a.duration, d.acquire/b.duration)
                self.assertAlmostEqual(c.release/a.duration, d.release/b.duration)

    def test_static_pose_summary_uses_checked_values(self):
        before = update_pose(None, {'head_yaw':15, 'torso_pitch':25})
        model = Model(response('pose_edit', changes={'head':'left:30'}, message='Misleading model prose'))
        after, summary = interpret_action('Turn only your head to the left.', before, model=model)
        self.assertEqual(after.get('torso_pitch'), before.get('torso_pitch'))
        self.assertEqual(before.get('head_yaw'), 15)
        self.assertIn('head yaw 30', summary)
        self.assertNotIn('Misleading', summary)

    def test_inference_errors_and_truncation_do_not_mutate_source_plan(self):
        before = preset_plan('wave')
        snapshot = asdict(before)
        model = Model('{"kind":"edit"')
        with self.assertRaises(PlanError):
            interpret_action('Greet like a conductor.', before, model=model)
        class Unavailable:
            def complete(self, *args): raise PlanError('Local inference unavailable')
        with self.assertRaisesRegex(PlanError, 'unavailable'):
            interpret_action('Greet like a conductor.', before, model=Unavailable())
        self.assertEqual(asdict(before), snapshot)
