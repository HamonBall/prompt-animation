"""Authored whole-avatar trajectories through the typed fragment bridge."""
from dataclasses import replace
import math

from . import contracts as c
from .joints import _contacts, _enum, _fragment, _number, _seconds, _values
from .spatial import angle_rotation, inverse, multiply, rotate

POSITION = 'object_root.position'
ORIENTATION = 'object_root.orientation'
CONTROLS = frozenset((POSITION, ORIENTATION))
IDS = ('root.travel', 'root.turn', 'root.orient', 'root.hover')
RELEASE_S = 6 / c.FPS


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def _subtract(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _scale(vector, weight):
    return tuple(value * weight for value in vector)


def _path_segments(duration, sample):
    """Author exact path samples with linear interpolation between frame keys."""
    count = round(duration * c.FPS)
    points = [sample((i / count) ** 2 * (3 - 2 * i / count)) for i in range(count + 1)]
    return [(i / c.FPS, (i + 1) / c.FPS, a, b, None)
            for i, (a, b) in enumerate(zip(points, points[1:]))]


def _travel(params, basis, origin, duration):
    heading = math.radians(params['heading_deg'])
    along = (math.sin(heading), math.cos(heading), 0)
    across = (-along[1], along[0], 0)
    distance = params['distance_m']
    if params['path'] == 'line':
        delta = rotate(basis, _scale(along, distance))
        return [(0, duration, origin, _add(origin, delta), None)]
    sweep = math.radians(params['arc_deg'])
    if abs(params['arc_deg']) < 15:
        c.fail('INVALID_PARAMETER', 'A circular arc requires a sweep of at least 15 degrees')
    radius = distance / (2 * math.sin(sweep / 2))

    def sample(weight):
        theta = sweep * (weight - .5)
        local = _add(_scale(along, radius * (math.sin(theta) + math.sin(sweep / 2))),
                     _scale(across, radius * (math.cos(sweep / 2) - math.cos(theta))))
        return _add(origin, rotate(basis, local))

    return _path_segments(duration, sample)


def build(instance, entry, profile, surfaces):
    params = {item.name: item.value for item in instance.parameters}
    values = _values(entry)
    origin, orientation = values[POSITION], values[ORIENTATION]
    basis = entry.root_transform.orientation if params.get('frame') == 'entry_body' else (1, 0, 0, 0)
    duration = _seconds(params['duration_s'])
    move = instance.definition_id
    mode = params.get('mode', 'airborne')
    support = set(entry.active_contacts)
    if mode == 'airborne' and support:
        c.fail('CONSTRAINT_CONFLICT', 'Airborne root motion requires released entry contacts')
    if mode == 'grounded_pivot' and (len(support) != 1 or next(iter(support)) not in ('left.sole', 'right.sole')):
        c.fail('CONSTRAINT_CONFLICT', 'A grounded turn needs exactly one captured sole and a free opposite foot')
    if mode == 'takeoff' and support != {'left.sole', 'right.sole'}:
        c.fail('ENTRY_MISMATCH', 'Hover takeoff needs both captured floor soles')
    if support and not any(surface.name == 'floor' for surface in surfaces):
        c.fail('UNRESOLVED_SURFACE', 'Supported root motion needs the resolved floor')
    for anchor in entry.contact_anchors:
        if anchor.anchor_id in support and (anchor.surface_id != 'floor' or anchor.frame != 'world'
                                            or abs(anchor.position[2]) > .003):
            c.fail('ENTRY_MISMATCH', 'Root motion requires captured world floor anchors')
    if mode == 'airborne' and min(values[side + '.sole.position'][2] for side in ('left', 'right')) < .02:
        c.fail('ENTRY_MISMATCH', 'Airborne motion needs at least 20 mm of measured sole clearance')

    if move == 'root.travel':
        positions = _travel(params, basis, origin, duration)
        rotations = [(0, duration, orientation, orientation, None)]
    elif move == 'root.hover':
        delay = RELEASE_S if mode == 'takeoff' else 0
        target = (origin[0], origin[1], params['elevation_m'])
        if mode == 'takeoff' and target[2] <= origin[2]:
            c.fail('INVALID_PARAMETER', 'Hover takeoff must increase the object root elevation')
        hold = _seconds(params['hold_s'])
        end = delay + duration
        positions = [(delay, end, origin, target, None), (end, end + hold, target, target, None)]
        if delay:
            positions.insert(0, (0, delay, origin, origin, None))
        duration = round((end + hold) * c.FPS) / c.FPS
        rotations = [(0, duration, orientation, orientation, None)]
    else:
        angle = params['angle_deg']
        pivot = entry.root_transform.position
        if mode == 'grounded_pivot':
            if abs(angle) > 20:
                c.fail('INVALID_PARAMETER', 'Grounded pivot is limited to 20 degrees')
            anchor_id = next(iter(support))
            pivot = next(anchor.position for anchor in entry.contact_anchors if anchor.anchor_id == anchor_id)
            other = 'right' if anchor_id == 'left.sole' else 'left'
            if values[other + '.sole.position'][2] < .02:
                c.fail('ENTRY_MISMATCH', 'Grounded pivot needs a raised opposite foot')
        axis = params.get('axis', 'yaw')
        delta = multiply(multiply(basis, angle_rotation(**{axis: angle})), inverse(basis))
        rotations = [(0, duration, orientation, multiply(delta, orientation), None)]

        def position(weight):
            rotation = multiply(multiply(basis, angle_rotation(**{axis: angle * weight})), inverse(basis))
            return _add(pivot, rotate(rotation, _subtract(origin, pivot)))

        positions = _path_segments(duration, position)
    contacts = _contacts(instance, entry, duration)
    if mode == 'takeoff':
        contacts = tuple(replace(event, interval=c.TimeInterval(0, RELEASE_S), release_s=RELEASE_S)
                         for event in contacts)
    fragment = _fragment(instance, entry, profile, {POSITION: positions, ORIENTATION: rotations},
                         duration, (c.PhaseLandmark('end', duration),))
    if len(positions) > 4:
        fragment = replace(fragment, tracks=tuple(
            replace(track, curve=replace(track.curve, easing='linear')) if track.control_id == POSITION else track
            for track in fragment.tracks))
    return replace(fragment, contact_events=contacts)


BUILDER_ID = 'root.trajectory.v1'


def register_root(catalog, profile):
    from .registry import register_movement

    capabilities = tuple('measure.' + key for key in sorted(CONTROLS))
    if profile.version != 8 or not set(capabilities) <= set(profile.capabilities):
        return catalog
    duration = _number('duration_s', 'second', 2, 1.5, 3.5)
    frame = _enum('frame', 'entry_body', ('world', 'entry_body'))
    parameters = {
        'root.travel': (frame, _enum('path', 'line', ('line', 'arc')),
                        _number('distance_m', 'metre', 1, .1, 2),
                        _number('heading_deg', 'degree', 0, -180, 180),
                        _number('arc_deg', 'degree', 60, -90, 90)),
        'root.turn': (_enum('mode', 'airborne', ('airborne', 'grounded_pivot')),
                      _number('angle_deg', 'degree', 45, -120, 120)),
        'root.orient': (frame, _enum('axis', 'pitch', ('pitch', 'roll')),
                        _number('angle_deg', 'degree', 45, -90, 90)),
        'root.hover': (_enum('mode', 'takeoff', ('takeoff', 'airborne')),
                       _number('elevation_m', 'metre', .8, .2, 2.5),
                       _number('hold_s', 'second', .5, .2, 1.5)),
    }
    for move, specs in parameters.items():
        register_movement(c.MovementDefinition(
            move, 1, 'body', f'Whole-avatar {move} with explicit entry support', (duration, *specs),
            capabilities, (), ('pelvis',), (), (), BUILDER_ID, ('root_trajectory',), ('end',), 'preserve_end',
        ), catalog)
    return catalog
