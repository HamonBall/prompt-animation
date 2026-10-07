"""Small explicit vocabulary for the feasibility spike; this is not an AI model."""
import re
from ..models import MotionPlan, PlanPatch, PlanError
from .validation import apply_patch, validate_plan


class UnknownPrompt(PlanError):
    """The exact vocabulary did not match; AI may interpret this wording."""


def interpret(text: str, current: MotionPlan | None = None) -> MotionPlan:
    text = text.strip().lower().rstrip('.!')
    # Full matching deliberately rejects extra actions and negated instructions.
    initial = re.fullmatch(
        r'(?:(?:make|move|turn)(?: me| the avatar)? (?:into )?|a )?'
        r'(?:t[ -]?rex|tyrannosaurus)(?:[ -]like)?(?: pose| transition)?'
        r'(?: (?:in|over) (\d+(?:\.\d+)?) seconds?)?', text)
    if initial:
        result = MotionPlan(duration=float(initial.group(1) or 2),
                            revision=current.revision + 1 if current else 0)
        validate_plan(result)
        return result
    if current is None:
        raise UnknownPrompt('Start with “T-rex pose” or “T-rex pose in 3 seconds”. '
                        'Walking, dancing, and arbitrary motions are not implemented yet.')
    edits = {
        'crouch lower': ('crouch', current.crouch + 0.03),
        'crouch less': ('crouch', current.crouch - 0.03),
        'stand taller': ('crouch', current.crouch - 0.03),
        'raise arms': ('arm_lift', current.arm_lift + 0.1),
        'raise the arms': ('arm_lift', current.arm_lift + 0.1),
        'lower arms': ('arm_lift', current.arm_lift - 0.1),
        'lower the arms': ('arm_lift', current.arm_lift - 0.1),
        'slower': ('duration', current.duration + 0.5),
        'faster': ('duration', current.duration - 0.5),
    }
    if text not in edits:
        raise UnknownPrompt('Available corrections: crouch lower, crouch less, stand taller, '
                        'raise arms, lower arms, slower, faster. '
                        'An experimental arbitrary-motion engine is not available yet.')
    return apply_patch(current, PlanPatch(current.revision, (edits[text],)))
