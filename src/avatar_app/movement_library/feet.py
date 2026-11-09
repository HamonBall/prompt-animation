"""Finite ankle and foot movements over captured floor contacts, profile 8."""
from dataclasses import replace

from . import contracts as c
from .curves import axis_rotation
from .joints import _enum, _fragment, _number, _path, _seconds
from .legs import reachable
from .spatial import multiply, rotate


MARKER = 'foot_v1:rigid_heel_forefoot_contacts'
IDS = ('ankle.flex', 'ankle.tilt', 'foot.place', 'foot.lift', 'foot.pivot',
       'heel.raise', 'toe.raise', 'foot.roll', 'foot.tap', 'toes.curl')
POINTS = ('sole', 'heel', 'forefoot')
RAMP = 6 / c.FPS
ANGLES = {
    'ankle.flex': (-18, 18, 12), 'ankle.tilt': (-12, 12, 8),
    'foot.pivot': (-20, 20, 12), 'heel.raise': (3, 18, 12),
    'toe.raise': (3, 15, 10), 'foot.roll': (3, 15, 9), 'toes.curl': (-12, 24, 15),
}


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def _offset(point, z):
    return point[0], point[1], point[2] + z


def _contact(instance, anchor, start, end, *, acquire=0, release=0):
    return c.ContactEvent(
        f'{instance.instance_id}.{anchor}.{round(start * c.FPS)}',
        (instance.instance_id,), anchor, 'floor',
        c.TimeInterval(start, end), acquire, release, 0,
    )


def _local_motion(instance, profile, side, values, parameters):
    suffix = {'ankle.flex': 'ankle.flexion', 'ankle.tilt': 'ankle.tilt',
              'toes.curl': 'toe.flexion'}[instance.definition_id]
    key = f'{side}.{suffix}'
    if key not in values:
        c.fail('MISSING_CAPABILITY', 'Selected foot articulation is unavailable', control_id=key)
    if values[f'{side}.sole.position'][2] < .055:
        c.fail('ENTRY_MISMATCH', 'Free ankle or toe articulation requires a raised entry', control_id=key)
    target = values[key] + parameters['angle']
    limit = next(limit for limit in profile.joint_limits if limit.control_id == key)
    if not limit.minimum <= target <= limit.maximum:
        c.fail('INVALID_PARAMETER', 'Requested articulation exceeds the calibrated limit', control_id=key)
    return key, target


def build(instance, entry, profile, surfaces):
    if profile.version != 8 or MARKER not in profile.calibration_provenance.evidence:
        c.fail('MISSING_CAPABILITY', 'Foot mechanics require calibrated profile 8')
    p = {item.name: item.value for item in instance.parameters}
    values = {item.control_id: item.value for item in entry.measured_controls}
    anchors = {item.anchor_id: item for item in entry.contact_anchors}
    side = p['side']
    opposite = 'right' if side == 'left' else 'left'
    selected = f'{side}.sole'
    support = f'{opposite}.sole'
    if support not in entry.active_contacts or set(entry.active_contacts) - {support, selected}:
        c.fail('ENTRY_MISMATCH', 'This movement requires the opposite captured floor sole and an optional selected sole')
    if any(anchors[key].surface_id != 'floor' or anchors[key].frame != 'world'
           for key in entry.active_contacts):
        c.fail('ENTRY_MISMATCH', 'Foot support needs world-framed floor anchors')
    duration = _seconds(p['duration_s'])
    hold = _seconds(p['hold_s'])
    policy = p['return_policy']
    move = instance.definition_id
    planted = selected in entry.active_contacts
    delay = RAMP if planted else 0
    contact_specs = []
    key = f'{side}.foot.position'

    if move == 'toes.curl' or (move.startswith('ankle.') and p['support'] == 'free'):
        if planted:
            c.fail('CONSTRAINT_CONFLICT', 'Free ankle and toe articulation requires an already released foot')
        key, target = _local_motion(instance, profile, side, values, p)
        segments, end = _path(values[key], [target], duration, hold, policy)
    elif move in ('foot.place', 'foot.lift', 'foot.tap'):
        if not planted and move != 'foot.place':
            c.fail('ENTRY_MISMATCH', 'Lift and tap require a captured selected sole at entry')
        initial = values[key]
        sole = values[f'{side}.sole.position']
        lift = p['clearance_m']
        raised = _offset(initial, lift)
        if move == 'foot.lift':
            points = [raised]
        else:
            target = p.get('target')
            if target is not None and 'distance_m' in instance.explicit_parameters:
                c.fail('INVALID_PARAMETER', 'Use a world sole target or a relative distance', control_id=key)
            if target is None:
                heading = rotate(entry.root_transform.orientation, (0, p['distance_m'], 0))
                target = sole[0] + heading[0], sole[1] + heading[1], anchors[selected].position[2] if planted else 0
            if abs(target[2]) > .003:
                c.fail('INVALID_PARAMETER', 'Placement target must be a world floor sole point', control_id=key)
            landing = tuple(a + b - current for a, b, current in zip(initial, target, sole))
            points = [raised, _offset(landing, lift), landing]
            if move == 'foot.tap' or policy == 'return_to_entry':
                points += [landing, _offset(landing, lift), raised]
        for point in points:
            reachable(values, profile, side, point)
        if move != 'foot.lift':
            hold = max(hold, RAMP)
        segments, end = _path(initial, points, duration, hold, policy, delay=delay)
        if move != 'foot.lift':
            arrival = delay + 3 * duration + 2 * hold
            departure = end if len(points) == 3 else arrival + hold + duration + hold
            contact_specs.append((selected, arrival, departure, RAMP, 0 if len(points) == 3 else RAMP))
    else:
        if not planted:
            c.fail('ENTRY_MISMATCH', 'A supported pivot requires a flat captured selected sole')
        key = f'{side}.foot.orientation'
        initial = values[key]
        angle = p['angle']

        def orient(axis, amount):
            return multiply(axis_rotation(rotate(initial, axis), amount), initial)

        if move == 'foot.roll':
            if policy != 'return_to_entry':
                c.fail('INVALID_PARAMETER', 'A full foot roll ends on the measured sole')
            hold = max(hold, 1 / c.FPS)
            points = [orient((-1, 0, 0), angle), initial, orient((-1, 0, 0), -angle)]
            segments, end = _path(initial, points, duration, hold, policy, delay=delay)
            level = delay + 2 * duration + hold
            contact_specs.extend(((f'{side}.heel', delay, level, 0, 0),
                                  (selected, level, level + hold, 0, 0),
                                  (f'{side}.forefoot', level + hold, end, 0, 0)))
        else:
            if move == 'foot.pivot':
                point = p['anchor']
                rotation = orient((0, 0, -1), angle)
            elif move == 'ankle.tilt':
                if abs(angle) > 2:
                    c.fail('INVALID_PARAMETER', 'Heel-supported tilt is limited to two degrees')
                point = 'heel'
                rotation = orient((0, 1, 0), angle * (1 if side == 'left' else -1))
            else:
                pitch = -angle if move == 'heel.raise' else angle
                point = 'forefoot' if pitch < 0 else 'heel'
                rotation = orient((-1, 0, 0), pitch)
            segments, end = _path(initial, [rotation], duration, hold, policy, delay=delay)
            contact_specs.append((f'{side}.{point}', delay, end, 0, 0))
        for anchor, *_ in contact_specs:
            if anchor not in anchors or anchors[anchor].surface_id != 'floor' or anchors[anchor].frame != 'world':
                c.fail('ENTRY_MISMATCH', 'Capture the selected floor reference before a supported movement',
                       details={'anchor_id': anchor})

    restore = planted and policy == 'return_to_entry'
    if restore:
        previous = end
        end += RAMP
        segments.append((previous, end, segments[-1][3], segments[-1][3], None))
        contact_specs.append((selected, previous, end, RAMP, 0))
    if planted:
        contact_specs.append((selected, 0, delay, 0, RAMP))
    contact_specs.append((support, 0, end, 0, 0))

    # Author phase and contact boundaries on the same sample grid.
    def aligned(time):
        return round(time * c.FPS) / c.FPS

    end = aligned(end)
    contacts = tuple(_contact(instance, anchor, aligned(start), aligned(stop),
                              acquire=min(acquire, aligned(stop) - aligned(start)),
                              release=min(release, aligned(stop) - aligned(start) - acquire)
                              if release and acquire else min(release, aligned(stop) - aligned(start)))
                     for anchor, start, stop, acquire, release in contact_specs)
    segments = [(aligned(start), aligned(stop), a, b, aim) for start, stop, a, b, aim in segments]
    paths = {key: segments}
    if key.endswith('.foot.position'):
        orientation = f'{side}.foot.orientation'
        paths[orientation] = [(0, end, values[orientation], values[orientation], None)]
    fragment = _fragment(instance, entry, profile, paths, end, (
        c.PhaseLandmark('release', 0), c.PhaseLandmark('action', aligned(delay + duration)),
        c.PhaseLandmark('end', end),
    ))
    return replace(fragment, contact_events=contacts)


BUILDERS = {'feet.mechanics.v1': build}


def register_feet(catalog, profile):
    if profile.version != 8 or MARKER not in profile.calibration_provenance.evidence:
        return catalog
    from .registry import register_movement

    for move in IDS:
        suffix = '.toe.flexion'
        sides = tuple(side for side in ('left', 'right')
                      if move != 'toes.curl' or any(item.id == side + suffix for item in profile.controls))
        if not sides:
            continue
        default_return = 'preserve_end' if move == 'foot.place' else 'return_to_entry'
        policies = ('return_to_entry',) if move in ('foot.roll', 'foot.tap') else ('return_to_entry', 'preserve_end')
        params = (
            _enum('side', sides[0], sides), _number('duration_s', 'second', 1, .8, 2),
            _number('hold_s', 'second', .2, 0, .5), _enum('return_policy', default_return, policies),
        )
        if move in ANGLES:
            lo, hi, default = ANGLES[move]
            params += (_number('angle', 'degree', default, lo, hi),)
        if move.startswith('ankle.'):
            params += (_enum('support', 'free', ('free', 'pivot')),)
        if move == 'foot.pivot':
            params += (_enum('anchor', 'heel', ('heel', 'forefoot')),)
        if move in ('foot.lift', 'foot.place', 'foot.tap'):
            params += (_number('clearance_m', 'metre', .07, .045, .13),)
        if move in ('foot.place', 'foot.tap'):
            params += (_number('distance_m', 'metre', .05 if move == 'foot.place' else 0, -.06, .09),
                       c.ParameterSpec('target', 'vector', 'metre', 'world', False, True,
                                       None, -20, 20, dimensions=3, nullable=True))
        parts = ('toe',) if move == 'toes.curl' else ('thigh', 'shin', 'ankle')
        chains = tuple(f'{side}.{part}' for side in sides for part in parts)
        register_movement(c.MovementDefinition(
            move, 1, 'limb', f'Finite {move} with explicit foot support',
            params, (), (), chains, (), (), 'feet.mechanics.v1',
            ('foot_mechanics',), ('release', 'action', 'end'), default_return,
        ), catalog)
    return catalog
