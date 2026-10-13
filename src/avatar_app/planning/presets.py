"""Internal animation foundations for prompt planning; no user-facing catalog."""
from dataclasses import replace
from ..models import PlanError
from ..motion import ActionPlan, ContactConstraint, validate_action
from .movements import movement, lying_down_plan


PRESETS = (
    ('jump', 'Jumping', 'Crouch, jump with both feet airborne, land and recover'),
    ('walk', 'Walking', 'Four forward steps with alternating planted feet, then stop'),
    ('lie', 'Lying down', 'Crouch, sit on the floor and lower onto the back'),
    ('run', 'Running', 'Four forward strides with flight phases, then stop'),
    ('wave', 'Waving', 'Raise the right hand, wave three times and lower it'),
)

BASE_PARAMETERS = {'jump': {}, 'walk': {'steps': [2, 4]}, 'lie': {},
                   'run': {'steps': [2, 4]},
                   'wave': {'side': ['left', 'right'], 'waves': [1, 2, 3, 4]}}


def motion_foundations():
    """Compact mechanics for the local planner, without regenerating body targets."""
    return [{'name': name, 'purpose': purpose, 'parameters': BASE_PARAMETERS[name]}
            for name, _, purpose in PRESETS]


def motion_foundation(selection, current=None):
    if not isinstance(selection, dict) or not isinstance(selection.get('name'), str):
        raise PlanError('Invalid animation foundation.')
    name = selection['name']
    if name not in BASE_PARAMETERS or not set(selection) <= {'name', *BASE_PARAMETERS[name]}:
        raise PlanError('Invalid animation foundation parameters.')
    return preset_plan(name, current, **{k: v for k, v in selection.items() if k != 'name'})


def foot_target(side, forward=0, height=0):
    return {side+'_foot_target_side': 0, side+'_foot_target_forward': forward,
            side+'_foot_target_height': height}


def planted(*sides, start=0):
    return tuple(ContactConstraint(side+'_foot', start=start) for side in sides)


def jump_plan():
    feet = {**foot_target('left'), **foot_target('right')}
    return validate_action(ActionPlan((
        movement('prepare', 'Crouch before jumping',
                 {**feet, 'pelvis_drop': .12, 'torso': 'forward:12',
                  'left_arm': 'backward:10', 'right_arm': 'backward:10'}, 1.0,
                 planted('left', 'right')),
        movement('takeoff', 'Extend legs and rise into the air',
                 {**foot_target('left', height=.14), **foot_target('right', height=.14),
                  'pelvis_drop': -.10, 'torso': 'forward:0', 'grounding': 0,
                  'left_arm': 'forward:15', 'right_arm': 'forward:15'}, .3),
        movement('land', 'Land with softened knees',
                 {**feet, 'pelvis_drop': .12, 'left_arm': 'forward:15',
                  'right_arm': 'forward:15'}, .3, planted('left', 'right', start=.95)),
        movement('recover', 'Return to standing',
                 {'pelvis_drop': 0, 'grounding': 1,
                  'left_arm': 'out:8', 'right_arm': 'out:8'}, 1.0, planted('left', 'right')),
    ), description='Jump once and land with both feet supported'))


def gait_plan(running=False, steps=4):
    if type(steps) is not int or steps not in (2, 4):
        raise PlanError('This step sequence supports two or four steps.')
    stride = .17 if running else .13
    phase = .45 if running else .6
    depth = .07 if running else .08
    stages = [movement('prepare', 'Prepare to run' if running else 'Prepare to walk',
        {**foot_target('left'), **foot_target('right'), 'pelvis_drop': depth,
         'torso': 'forward:10' if running else 'forward:5', 'grounding': 0}, 1.0,
        planted('left', 'right'))]
    positions = {'left': 0, 'right': 0}
    for index in range(steps):
        side = 'left' if index % 2 == 0 else 'right'
        other = 'right' if side == 'left' else 'left'
        end = (index+1)*stride
        arms = {side+'_arm': 'backward:20', other+'_arm': 'forward:25',
                side+'_forearm': 'forward:65' if running else 'backward:10',
                other+'_forearm': 'forward:85' if running else 'forward:35'}
        if running:
            targets = {**foot_target(side, end, .10),
                       **foot_target(other, positions[other], .08),
                       'pelvis_forward': end-stride/2, 'pelvis_drop': -.015, **arms}
            stages.append(movement(f'flight_{index+1}', 'Stride with both feet airborne', targets, phase))
            targets = {**foot_target(side, end), **foot_target(other, positions[other], .08),
                       'pelvis_forward': end, 'pelvis_drop': depth, **arms}
            stages.append(movement(f'land_{index+1}', 'Catch stride on '+side+' foot', targets, phase,
                                   planted(side, start=.95)))
        else:
            targets = {**foot_target(side, end-stride/2, .045),
                       **foot_target(other, positions[other]),
                       'pelvis_forward': end-stride/2,
                       'pelvis_side': .035 if other == 'right' else -.035, **arms}
            stages.append(movement(f'swing_{index+1}', 'Swing '+side+' foot forward', targets, phase,
                                   planted(other)))
            targets = {**foot_target(side, end), 'pelvis_forward': end,
                       'pelvis_side': .035 if side == 'right' else -.035, **arms}
            stages.append(movement(f'plant_{index+1}', 'Place '+side+' foot on the floor', targets, phase,
                                   planted(other)))
        positions[side] = end
    # Bring the trailing foot alongside the last support before straightening.
    trailing, support = ('left', 'right') if steps % 2 == 0 else ('right', 'left')
    end = steps*stride
    stages.extend((
        movement('close_swing', 'Bring trailing foot alongside',
                 {**foot_target(trailing, end, .045), **foot_target(support, end),
                  'pelvis_forward': end, 'pelvis_drop': depth,
                  'pelvis_side': 0,
                  'left_arm': 'out:8', 'right_arm': 'out:8',
                  'left_forearm': 'out:8', 'right_forearm': 'out:8'}, .8, planted(support)),
        movement('close_plant', 'Place both feet together',
                 foot_target(trailing, end), .6, planted(support)),
        movement('stop', 'Finish standing with both feet planted',
                 {'pelvis_drop': 0, 'torso': 'forward:0', 'grounding': 1}, 1.0,
                 planted('left', 'right')),
    ))
    return validate_action(ActionPlan(tuple(stages), description=f'{"Run" if running else "Walk"} {steps} forward steps and stop'))


def wave_plan(side='right', waves=3):
    if side not in ('left', 'right') or type(waves) is not int or not 1 <= waves <= 4:
        raise PlanError('Wave with a left/right hand, one to four times.')
    stages = [movement('raise', 'Raise '+side+' hand to greet',
                       {side+'_arm': 'out:65', side+'_forearm': 'out:150'}, 1.5, planted('left','right'))]
    for index in range(waves*2):
        angle = 175 if index % 2 == 0 else 150
        stages.append(movement(f'wave_{index+1}', 'Wave '+side+' hand',
            {side+'_forearm': 'out:'+str(angle), side+'_hand_roll': 15 if index % 2 == 0 else -15},
            .65, planted('left','right')))
    stages.append(movement('lower', 'Lower '+side+' hand',
        {side+'_arm': 'out:8', side+'_forearm': 'out:8', side+'_hand_roll': 0}, 1.5, planted('left','right')))
    return validate_action(ActionPlan(tuple(stages), description=f'Wave {side} hand {waves} times'))


def preset_plan(name, current=None, **options):
    factories = {'jump': jump_plan, 'walk': gait_plan, 'lie': lying_down_plan,
                 'run': lambda **kw: gait_plan(running=True, **kw), 'wave': wave_plan}
    if name not in factories:
        raise PlanError('Invalid animation foundation.')
    plan = factories[name](**options)
    return replace(plan, revision=current.revision+1 if current else 0)
