import math
from dataclasses import replace
from ..models import MotionPlan, PlanPatch, PlanError


LIMITS = {'duration': (0.5, 8.0), 'crouch': (0.0, 0.20), 'arm_lift': (-0.3, 0.5)}


def validate_plan(plan: MotionPlan) -> None:
    if plan.action != 'trex_transition' or plan.fps != 30:
        raise PlanError('This prototype supports a T-rex transition at 30 fps.')
    for name, (low, high) in LIMITS.items():
        value = getattr(plan, name)
        if not math.isfinite(value) or not low <= value <= high:
            raise PlanError(f'{name} must be between {low} and {high}.')


def apply_patch(plan: MotionPlan, patch: PlanPatch) -> MotionPlan:
    if patch.base_revision != plan.revision:
        raise PlanError('This correction belongs to an older result.')
    changes = dict(patch.changes)
    if not changes or len(changes) != len(patch.changes) or changes.keys() - LIMITS.keys():
        raise PlanError('Invalid correction fields.')
    result = replace(plan, **changes, revision=plan.revision + 1)
    validate_plan(result)
    return result
