import unittest
from dataclasses import asdict
from avatar_app.models import MotionPlan, PlanPatch, PlanError
from avatar_app.planning.interpreter import interpret
from avatar_app.planning.validation import apply_patch


class PlanningTests(unittest.TestCase):
    def test_correction_preserves_every_unrelated_field(self):
        before = interpret('T-rex pose in 3 seconds')
        after = interpret('crouch lower', before)
        self.assertGreater(after.crouch, before.crouch)
        for name, value in asdict(before).items():
            if name not in ('crouch', 'revision'):
                self.assertEqual(getattr(after, name), value)

    def test_rejects_stale_or_invalid_patch(self):
        for patch in (PlanPatch(9, (('crouch', 0.1),)),
                      PlanPatch(0, (('action', 1),)),
                      PlanPatch(0, (('crouch', float('nan')),)),
                      PlanPatch(0, (('duration', 0),))):
            with self.assertRaises(PlanError):
                apply_patch(MotionPlan(), patch)

    def test_rejects_unsupported_and_negated_actions(self):
        for prompt in ('walk like a T-rex', 'do not make a T-rex pose',
                       'T-rex pose and dance', 'dance'):
            with self.assertRaises(PlanError):
                interpret(prompt)

    def test_edits_need_an_existing_plan(self):
        with self.assertRaises(PlanError):
            interpret('crouch lower')

    def test_boundary_edit_keeps_original_plan(self):
        plan = MotionPlan(crouch=0.20)
        with self.assertRaises(PlanError):
            interpret('crouch lower', plan)
        self.assertEqual(plan.crouch, 0.20)

    def test_timing_edits_preserve_pose(self):
        plan = interpret('T-rex pose')
        after = interpret('slower', plan)
        self.assertEqual(after.duration, 2.5)
        self.assertEqual(after.crouch, plan.crouch)
        self.assertEqual(after.arm_lift, plan.arm_lift)


if __name__ == '__main__':
    unittest.main()
