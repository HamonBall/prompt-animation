"""Reliable movement routes complement open-ended AI; they never limit pose names."""
from dataclasses import replace
import re
from ..motion import ActionPlan, scale_timing
from ..models import PlanError
from .movements import lying_down_plan, sitting_plan, floor_sitting_plan
from .presets import preset_plan


def common_route(text, current=None, surfaces=()):
    lowered = text.lower().strip().rstrip('.!')
    # Entire-request matches avoid swallowing creative modifiers, named stages,
    # explicit unusual routes, stomach poses, or unrelated body-part changes.
    lying = re.fullmatch(r'(?:please )?(?:lie|lay) (?:down(?: on (?:the )?(?:ground|floor))?|(?:flat )?on (?:your |the )?back)(?: slowly)?', lowered)
    sitting = re.fullmatch(r'(?:please )?sit(?: down)?(?: on (?:the |a |your )?(?:chair|seat))?(?: slowly)?', lowered)
    floor_sitting = re.fullmatch(r'(?:please )?sit(?: down)? on (?:the )?(?:ground|floor)(?: slowly)?', lowered)
    simple = lowered.removeprefix('please ').removesuffix(' slowly')
    gait = re.fullmatch(r'(walk|walking|run|running)(?: forward)?(?: (2|4) steps)?', simple)
    wave = re.fullmatch(r'(?:wave|waving)(?: hello|(?: with)? (?:your )?(left|right) (?:hand|arm))?', simple)
    if lying:
        plan = lying_down_plan()
    elif simple in ('lie', 'lying', 'lying down'):
        plan = preset_plan('lie')
    elif simple in ('jump', 'jumping', 'jump once', 'jump up'):
        plan = preset_plan('jump')
    elif gait:
        plan = preset_plan('run' if gait[1] in ('run', 'running') else 'walk', steps=int(gait[2] or 4))
    elif wave:
        plan = preset_plan('wave', side=wave[1] or 'right')
    elif floor_sitting:
        plan = floor_sitting_plan()
    elif sitting:
        seat = next((s for s in surfaces if s.name == 'seat'), None)
        if seat is None:
            raise PlanError('Enable the preview seat before asking to sit on a chair.')
        plan = sitting_plan(seat.height, seat)
    else:
        return None
    if lowered.endswith(' slowly'):
        plan = scale_timing(plan, 1.25)
    return replace(plan, revision=current.revision + 1 if current else 0)


def check_route_destination(plan, text):
    """Semantic guard on recognized destinations, including generated unfamiliar routes."""
    lowered = text.lower()
    endpoint = plan.final_pose if isinstance(plan, ActionPlan) else plan
    if re.search(r'\b(?:lie|lying|lay)\s+(?:down|flat|on\s+(?:your\s+|the\s+)?back)\b', lowered) and not re.search(r'\b(?:stomach|side|front)\b', lowered):
        if abs(endpoint.get('root_pitch') + 90) > 15:
            raise PlanError('The proposed route does not reach the requested lying pose. Try a simpler description.')
        if isinstance(plan, ActionPlan) and not any(c.surface == 'floor' and c.part in ('pelvis', 'back')
                                                    for stage in plan.stages for c in stage.contacts):
            raise PlanError('The proposed lying route needs explicit pelvis/back floor support.')
        # Sitting and lowering stages need explicit pelvic support, not an
        # unchecked whole-body rotation repaired after the animation is built.
        for stage in plan.stages if isinstance(plan, ActionPlan) else ():
            if re.search(r'\b(?:sit|sitting|lower|lowering)\b', stage.id+' '+stage.action) and not any(
                    c.part in ('pelvis', 'back') for c in stage.contacts):
                raise PlanError('The proposed floor route omits pelvic/back support. Try a simpler description.')
    return plan
