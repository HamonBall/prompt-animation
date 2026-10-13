"""Parameterized body-target movements, reusable in arbitrary timelines."""
from dataclasses import dataclass, replace
import math
from ..models import PlanError
from ..pose import PosePlan
from ..motion import ActionPlan, MotionStage, ContactConstraint, affected_part, validate_action
from .pose_interpreter import canonical_controls


@dataclass(frozen=True)
class AvatarMeasurements:
    height: float
    leg_length: float


@dataclass(frozen=True)
class MovementSegment:
    stage: MotionStage
    starting_state: PosePlan
    ending_state: PosePlan


def construct_movement(starting_state, measurements, targets, duration, contacts=(),
                       id='movement', action='Move body targets'):
    """Common movement interface; the rig executor resolves IK reach precisely."""
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
           for v in (measurements.height, measurements.leg_length)):
        raise PlanError('Avatar measurements must be positive finite lengths.')
    stage = movement(id, action, targets, duration, contacts)
    plan = validate_action(ActionPlan((stage,), initial=starting_state))
    return MovementSegment(stage, starting_state, plan.final_pose)


def movement(id, action, targets, duration=1.0, contacts=(), start=None):
    controls = canonical_controls(targets)
    parts = tuple(sorted({affected_part(key) for key in controls if affected_part(key)}))
    return MotionStage(id, action, parts, tuple(sorted(controls.items())), duration,
                       start, tuple(contacts))


def crouch(id='crouch', depth=.22, backward=.04, lean=25, duration=1.2):
    return movement(id, 'Lower hips with coordinated knee bending',
                    {'pelvis_drop': depth, 'pelvis_forward': -backward,
                     'torso': f'forward:{lean}'}, duration,
                    [ContactConstraint('left_foot'), ContactConstraint('right_foot')])


def lying_down_plan():
    """Reference route for executor verification, not a prompt-name whitelist."""
    pelvis = ContactConstraint('pelvis', clearance=.07, acquire=.8)
    hands = [ContactConstraint(side + '_hand', start=.35, end=.95,
                               position=(sign * .16, -.10), clearance=.025, acquire=1.5, release=1.0)
             for side, sign in (('left', -1), ('right', 1))]
    return validate_action(ActionPlan((
        crouch(duration=2.0),
        # The feet inherit the shin rotation; preserve their neutral ankle angle.
        movement('sit', 'Sit on the floor and extend legs',
                 {'torso': 'forward:0',
                  'left_thigh': 'forward:105', 'right_thigh': 'forward:105',
                  'left_shin': 'forward', 'right_shin': 'forward',
                  'left_arm': 'forward:20', 'right_arm': 'forward:20',
                  'left_forearm': 'forward:70', 'right_forearm': 'forward:70'}, 3.0,
                 [replace(pelvis, acquire=3.0)]),
        movement('lower', 'Lower torso with temporary hand support',
                 {'root': 'backward:65', 'left_thigh': 'forward:40',
                  'right_thigh': 'forward:40', 'left_shin': 'forward:25',
                  'right_shin': 'forward:25',
                  'left_arm': 'forward:25', 'right_arm': 'forward:25',
                  'left_forearm': 'forward:25', 'right_forearm': 'forward:25',
                  **{side+'_hand_target_'+axis: None for side in ('left','right')
                     for axis in ('side','forward','height')}}, 4.5, [pelvis, *hands]),
        movement('settle', 'Extend and settle onto back',
                 {'root': 'backward:90', 'left_thigh': 'down', 'right_thigh': 'down',
                  'left_shin': 'down', 'right_shin': 'down', 'left_arm': 'down',
                  'right_arm': 'down', 'left_forearm': 'down', 'right_forearm': 'down'}, 2.0,
                  [ContactConstraint('back', clearance=.055, acquire=2.0)]),
    ), description='Lie down through crouching, sitting and supported lowering'))


def sitting_plan(height=.45, surface=None):
    from ..motion import Surface
    return validate_action(ActionPlan((crouch(depth=.16, backward=.04, duration=2.0),
        movement('seat', 'Lower pelvis onto resolved seat',
                 {'torso': 'forward:0',
                  'left_arm': 'forward:20', 'right_arm': 'forward:20',
                  'left_forearm': 'forward:70', 'right_forearm': 'forward:70'}, 2.5,
                 [ContactConstraint('left_foot'), ContactConstraint('right_foot'),
                  ContactConstraint('pelvis', surface='seat', clearance=.06, acquire=2.5)])),
        surfaces=(Surface(), surface or Surface('seat', height)), description='Sit onto resolved seat surface'))


def floor_sitting_plan():
    """Acquire floor support through the same checked route used before lying."""
    route = lying_down_plan()
    return validate_action(replace(route, stages=route.stages[:2],
                                   description='Sit on the floor through a supported crouch'))
