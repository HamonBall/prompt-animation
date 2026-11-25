"""Foundation recipes built against a caller-supplied measured entry."""

from dataclasses import replace
import math

from . import contracts as c
from .compiler import compile_recipe
from .composer import compose_recipe
from .curves import axis_rotation
from .joints import catalog_for_profile
from .legs import hip_position
from .spatial import multiply, rotate


def foundation_recipe(name, entry, profile, *, floor_sit_arms=False, steps=None,
                      side=None, waves=None, tempo=None, instance_id='foundation', compact_jump=False,
                      chair_descent=False, run_height_m=None, run_arms=False):
    """Build a candidate recipe from the measured floor entry.

    The coordinated builders validate the measured support and route geometry
    during composition. The recipe does not prepare or replace the entry pose.
    Floor sits may carry the legacy forward arm intent during descent.
    """
    if steps is not None and name not in ('walk', 'run'):
        c.fail('INVALID_PARAMETER', 'Step count applies only to finite gait recipes')
    if (run_height_m is not None or run_arms) and name != 'run':
        c.fail('INVALID_PARAMETER', 'Run height and arm swing apply only to the run recipe')

    if name != 'wave' and any(value is not None for value in (side, waves, tempo)):
        c.fail('INVALID_PARAMETER', 'Wave options apply only to the wave recipe')
    if compact_jump and name != 'jump':
        c.fail('INVALID_PARAMETER', 'Compact jump timing applies only to the jump recipe')
    if chair_descent and name != 'sit_seat':
        c.fail('INVALID_PARAMETER', 'Chair descent applies only to the resolved chair recipe')

    if name == 'wave':
        movement = 'arm.wave_gesture'
        parameters = tuple(c.ParameterValue(key, value) for key, value in
                           (('side', side), ('waves', waves), ('tempo', tempo)) if value is not None)
        goal = 'Wave with the selected hand and return to the measured stance'
    elif name in ('walk', 'run'):
        count = 4 if steps is None else steps
        if type(count) is not int or count not in (2, 4):
            c.fail('INVALID_PARAMETER', 'The gait foundation supports two or four steps')
        if name == 'walk':
            movement = 'pattern.steps'
            parameters = (c.ParameterValue('count', count), c.ParameterValue('distance_m', .06),
                          c.ParameterValue('clearance_m', .04))
            goal = f'Walk {count} alternating planted steps'
        else:
            movement = 'body.run_burst'
            parameters = (c.ParameterValue('steps', count),
                          c.ParameterValue('height_m', run_height_m if run_height_m is not None else profile.height_m))
            if run_arms:
                parameters += (c.ParameterValue('arms', 'counter_swing'),)
            goal = f'Run {count} airborne strides and close both feet'
    elif name == 'jump':
        movement = 'body.jump_once' if compact_jump else 'body.takeoff_land'
        parameters = ()
        goal = 'Jump once and return to both planted soles'
    elif name == 'sit_floor':
        movement = 'body.floor_transfer'
        parameters = (c.ParameterValue('route', 'standing_to_seated'),)
        goal = 'Lower from standing onto floor support'
    elif name == 'lie_back':
        movement = 'body.floor_transfer'
        parameters = (c.ParameterValue('route', 'seated_to_back'),)
        goal = 'Lower from measured floor seating onto back support'
    elif name == 'sit_extend':
        movement = 'body.floor_transfer'
        parameters = (c.ParameterValue('route', 'seated_extend'),)
        goal = 'Extend both legs after releasing the feet from a supported floor seat'
    elif name == 'sit_seat':
        movement = 'body.floor_transfer'
        route = 'standing_to_chair' if chair_descent else 'prepared_seat'
        parameters = (c.ParameterValue('route', route), c.ParameterValue('surface', 'seat'))
        if chair_descent:
            parameters += (c.ParameterValue('approach_s', 3.1),)
        goal = 'Acquire pelvis support on the resolved chair'
    else:
        c.fail('UNKNOWN_ID', 'No foundation recipe for this movement', details={'name': name})

    if floor_sit_arms and name != 'sit_floor':
        c.fail('INVALID_PARAMETER', 'Floor sit arm motion applies only to the floor sit recipe')

    instances = (c.MovementInstance(instance_id, movement, 1, parameters, ('request',)),)
    if compact_jump:
        instances += (c.MovementInstance('jump_arms', 'arm.jump_swing', 1, (), ('request',)),)
    if floor_sit_arms or chair_descent:
        arm_targets = (('raise', 'arm.raise', 20),)
        if floor_sit_arms:
            arm_targets += (('bend', 'elbow.flex', 70),)
        instances += tuple(
            c.MovementInstance(instance_id, arm_movement, 1, (
                c.ParameterValue('side', 'both'),
                c.ParameterValue('angle', angle),
                c.ParameterValue('duration_s', 2.),
                c.ParameterValue('hold_s', 0.),
                c.ParameterValue('return_policy', 'preserve_end'),
            ), ('request',))
            for instance_id, arm_movement, angle in arm_targets
        )
        if chair_descent:
            instances += (c.MovementInstance('forearms', 'forearm.aim', 1, (
                c.ParameterValue('angle', 70), c.ParameterValue('duration_s', 2.),
            ), ('request',)),)

    return c.MotionRecipe(
        recipe_id=f'recipe.{name}',
        avatar_id=profile.avatar_id,
        profile_version=profile.version,
        base_revision=entry.revision,
        operation='new',
        instances=instances,
        relations=(),
        hard_goals=(),
        optional_styles=(),
        loop=None,
        clause_coverage=(c.ClauseCoverage('request', goal, 'fulfilled',
                                          tuple(instance.instance_id for instance in instances)),),
    )


def _floor_segment_compiler(profile, surfaces):
    surfaces = tuple(surfaces)
    catalog = catalog_for_profile(profile)

    def compile_from(name, measured, *, timing=(), **options):
        recipe = foundation_recipe(name, measured, profile, instance_id=name, **options)
        if timing:
            body, *accessory = recipe.instances
            body = replace(body, parameters=(*body.parameters, *timing))
            recipe = replace(recipe, instances=(body, *accessory))
        resolved = compose_recipe(recipe, measured, profile, surfaces, catalog)
        return compile_recipe(resolved, measured, profile, surfaces=surfaces, catalog=catalog)

    return compile_from


def compile_lie_sequence(entry, profile, surfaces, *, floor_sit_arms=False):
    """Continue from floor seating or first acquire it from a supported stance."""
    compile_from = _floor_segment_compiler(profile, surfaces)

    def lie_from(measured):
        return compile_from('lie_back', measured)

    if 'pelvis.support' in entry.active_contacts:
        return lie_from(entry), ()
    return compile_from('sit_floor', entry, floor_sit_arms=floor_sit_arms), (lie_from,)


def compile_floor_sit_sequence(entry, profile, surfaces):
    """Lower onto the pelvis before releasing both soles and extending the legs."""
    compile_from = _floor_segment_compiler(profile, surfaces)

    def extend_from(measured):
        return compile_from('sit_extend', measured)

    # Reserve 1.6 s of the five-second preset for release, extension and hold.
    timing = (c.ParameterValue('approach_s', 2.3), c.ParameterValue('phase_s', .9))
    return compile_from('sit_floor', entry, floor_sit_arms=True, timing=timing), (extend_from,)


def walk_recovery_distance(entry, measured, profile, load_depth):
    """Recover toward the entry height within the new planted stance's reach."""
    values = {item.control_id: item.value for item in measured.measured_controls}
    start = next(item.value for item in entry.measured_controls if item.control_id == 'pelvis.position')
    up = rotate(measured.root_transform.orientation, (0, 0, 1))
    if up[2] < .9:
        c.fail('ENTRY_MISMATCH', 'Walk recovery requires an upright support frame')
    desired = (start[2] - values['pelvis.position'][2]) / up[2]
    lengths = {item.id: item.value_m for item in profile.lengths}
    rise = min(load_depth, desired)
    for side in ('left', 'right'):
        leg = tuple(a - b for a, b in zip(hip_position(values, profile, side), values[side + '.foot.position']))
        along = sum(a * b for a, b in zip(leg, up))
        transverse = sum((value - along * axis) ** 2 for value, axis in zip(leg, up))
        reach = lengths[side + '.thigh'] + lengths[side + '.shin']
        rise = min(rise, math.sqrt(max(0., reach ** 2 - transverse)) - along - .00005)
    if rise < 0 or (desired - rise) * up[2] >= .002:
        c.fail('ENTRY_MISMATCH', 'The landed stance cannot recover the original pelvis height',
               details={'requested_m': desired, 'reachable_m': rise})
    return rise


def compile_walk_sequence(entry, profile, surfaces, *, steps=None, preset_height_m=None, arm_motion=False):
    return _compile_gait_sequence('walk', entry, profile, surfaces, steps, preset_height_m, arm_motion)


def compile_run_sequence(entry, profile, surfaces, *, steps=None, preset_height_m, arm_motion=False):
    return _compile_gait_sequence('run', entry, profile, surfaces, steps, preset_height_m, arm_motion)


def _compile_gait_sequence(name, entry, profile, surfaces, steps, preset_height_m, arm_motion):
    """Prepare a bounded walk and bind its later phases from measured exits."""
    surfaces = tuple(surfaces)
    catalog = catalog_for_profile(profile)
    running = name == 'run'
    gait_recipe = foundation_recipe(name, entry, profile, steps=steps,
                                    run_height_m=preset_height_m if running else None,
                                    run_arms=running and arm_motion)
    preset_travel = preset_height_m is not None
    if preset_travel:
        c.check_type(preset_height_m, float, 'preset_height_m')
        if preset_height_m <= 0:
            c.fail('INVALID_PARAMETER', 'Walk preset height must be positive')
    # Keep the stance knee loaded without over-flexing the ankle at the
    # higher swing apex used by the preset-distance steps.
    load_depth = (.07 if running else .06) * preset_height_m if preset_travel else .04
    posture_id = 'pelvis.gait_load' if preset_travel else 'pelvis.raise_lower'
    if arm_motion and not preset_travel:
        c.fail('INVALID_PARAMETER', 'Gait arm timing requires the preset-distance sequence')
    initial = {value.control_id: value.value for value in entry.measured_controls} if arm_motion and not running else {}
    arm_axis = rotate(entry.root_transform.orientation, (1, 0, 0))

    def compile_from(recipe, measured):
        resolved = compose_recipe(recipe, measured, profile, surfaces, catalog)
        return compile_recipe(resolved, measured, profile, surfaces=surfaces, catalog=catalog)

    def segment(measured, instance_id, definition, parameters, goal, accessory=()):
        instance = c.MovementInstance(instance_id, definition, 1, parameters, ('request',))
        instances = (instance, *accessory)
        recipe = c.MotionRecipe(f'recipe.{name}_{instance_id}', profile.avatar_id, profile.version,
                                measured.revision, 'new', instances, (), (), (), None,
                                (c.ClauseCoverage('request', goal, 'fulfilled',
                                                  tuple(item.instance_id for item in instances)),))
        return compile_from(recipe, measured)

    def posture(measured, instance_id, distance, torso_pitch=0.):
        parameters = (
            c.ParameterValue('distance_m', distance),
            c.ParameterValue('duration_s', 1.),
            c.ParameterValue('hold_s', 0.),
            c.ParameterValue('return_policy', 'preserve_end'),
        )
        if torso_pitch:
            parameters += (c.ParameterValue('torso_pitch_deg', torso_pitch),)
        return segment(measured, instance_id, posture_id, parameters, 'Adjust posture over both planted soles')

    run_lean = 10. if running and arm_motion else 0.

    def step_from(measured):
        return compile_from(replace(gait_recipe, base_revision=measured.revision), measured)

    def recover_from(measured):
        return posture(measured, 'recover', walk_recovery_distance(entry, measured, profile, load_depth), -run_lean)

    def gait_step(index, count):
        closing = index == count
        stride = .13 * preset_height_m
        side = 'left' if index % 2 == 0 else 'right'
        parameters = (
            c.ParameterValue('side', side),
            c.ParameterValue('distance_m', stride if index == 0 or closing else 2 * stride),
            c.ParameterValue('pelvis_advance_m', 0. if closing else stride),
            c.ParameterValue('apex_progress', 1. if closing else .5 if index == 0 else .75),
            c.ParameterValue('clearance_m', .045 * preset_height_m),
            c.ParameterValue('phase_s', .5 if closing else .4),
        )
        accessories = ()
        if arm_motion:
            angles = (0., 0.) if closing else (-20., 25.) if side == 'left' else (25., -20.)
            orientations = []
            for arm_side, angle in zip(('left', 'right'), angles, strict=True):
                arm = initial.get(arm_side + '.upper_arm.orientation')
                if arm is None:
                    c.fail('MISSING_CAPABILITY', 'Walk arm swing needs measured upper arm orientation')
                orientations.append(c.ParameterValue(arm_side + '_orientation',
                                                     multiply(axis_rotation(arm_axis, angle), arm)))
            accessories = (c.MovementInstance(f'arms.{index + 1}', 'arm.orient', 1, (
                c.ParameterValue('duration_s', 1.4 if closing else 1.2), *orientations,
            ), ('request',)),)

        def bind(measured):
            return segment(measured, f'step.{index + 1}', 'body.gait_step', parameters,
                           'Close the trailing foot' if closing else f'Step forward with the {side} foot',
                           accessories)

        return bind

    if preset_travel and not running:
        count = next(value.value for value in gait_recipe.instances[0].parameters if value.name == 'count')
        gait = tuple(gait_step(index, count) for index in range(count + 1))
    else:
        gait = (step_from,)
    return posture(entry, 'load', -load_depth, run_lean), (*gait, recover_from)
