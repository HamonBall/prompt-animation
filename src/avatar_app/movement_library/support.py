"""Frame-aligned contact schedules for horizontal support."""
from dataclasses import replace
import math

from . import contracts as c
from .joints import _enum, _fragment, _number, _seconds, _values

SOLE_ANCHORS = ('left.sole', 'right.sole')
FOOT_ANCHORS = tuple(f'{side}.{point}' for side in ('left', 'right')
                     for point in ('sole', 'heel', 'forefoot'))
PALM_ANCHORS = ('left.palm', 'right.palm')
BODY_ANCHORS = ('pelvis.support', 'back.support', 'left.knee.support', 'right.knee.support')
BUILDER_ID = 'support.schedule.v1'


def require_surface_point(anchor, surfaces, *, clearance_m=0):
    """Check that a world anchor lies on its declared horizontal region."""
    if anchor.frame != 'world':
        c.fail('INVALID_PARAMETER', 'A fixed support target needs a world frame')
    surface = next((item for item in surfaces if item.name == anchor.surface_id), None)
    if surface is None:
        c.fail('UNRESOLVED_SURFACE', 'Support surface is unavailable', details={'surface_id': anchor.surface_id})
    x, y, z = anchor.position
    if abs(z - surface.height - clearance_m) > .003:
        c.fail('INVALID_PARAMETER', 'Support target lies outside its surface height tolerance',
               details={'anchor_id': anchor.anchor_id, 'height_m': surface.height, 'position': anchor.position})
    if surface.size and any(abs(point - center) > extent / 2 for point, center, extent in
                            zip((x, y), surface.center, surface.size)):
        c.fail('INVALID_PARAMETER', 'Support target lies outside the resolved surface region',
               details={'anchor_id': anchor.anchor_id, 'surface_id': anchor.surface_id})
    return surface


def validate_support_drivers(anchors):
    body = set(anchors) & set(BODY_ANCHORS)
    if len(body) > 1:
        c.fail('CONSTRAINT_CONFLICT', 'Only one pelvis-driven contact can own the body at a time')
    if body and set(anchors) & set(PALM_ANCHORS):
        c.fail('CONSTRAINT_CONFLICT', 'Combined palm and pelvis-driven support has no compatible solve yet')
    for anchor in body:
        if anchor.endswith('.knee.support') and any(
                foot in anchors for foot in FOOT_ANCHORS if foot.split('.')[0] == anchor.split('.')[0]):
            c.fail('CONSTRAINT_CONFLICT', 'A pelvis-driven knee contact needs a free foot on the same leg',
                   details={'anchor_id': anchor})


def schedule(instance_id, entry, surfaces, *, acquire=None, release=(), acquire_frames=0, hold_frames=1,
             release_frames=0, allow_airborne=False):
    """Build one contact schedule with an overlapping transfer and an explicit exit."""
    frames = (acquire_frames, hold_frames, release_frames)
    if (any(type(value) is not int or value < 0 for value in frames)
            or hold_frames < 1 or sum(frames) > c.FPS * c.MAX_SECONDS
            or bool(acquire) != bool(acquire_frames) or bool(release) != bool(release_frames)):
        c.fail('INVALID_PARAMETER', 'Support phases need bounded frame counts and matching contact ramps')
    active = set(entry.active_contacts)
    if len(set(release)) != len(release) or not set(release) <= active | ({acquire.anchor_id} if acquire else set()):
        c.fail('ENTRY_MISMATCH', 'Release requires an active or newly acquired contact')
    if acquire and acquire.anchor_id in active:
        c.fail('CONSTRAINT_CONFLICT', 'Release the current attachment before acquiring the same anchor again',
               details={'anchor_id': acquire.anchor_id})
    if acquire and acquire.anchor_id in FOOT_ANCHORS and any(
            anchor in active for anchor in FOOT_ANCHORS
            if anchor.split('.')[0] == acquire.anchor_id.split('.')[0]):
        c.fail('CONSTRAINT_CONFLICT', 'A single leg cannot acquire two independent fixed foot points',
               details={'anchor_id': acquire.anchor_id})
    remaining = active | ({acquire.anchor_id} if acquire else set())
    validate_support_drivers(remaining)
    if not remaining - set(release) and not allow_airborne:
        c.fail('CONSTRAINT_CONFLICT', 'Releasing the last contact requires an explicit airborne exit')
    if not active and not allow_airborne:
        c.fail('ENTRY_MISMATCH', 'A supported transfer needs an active entry contact')
    end = sum(frames) / c.FPS
    anchors = [anchor for anchor in entry.contact_anchors if anchor.anchor_id in active]
    if acquire:
        anchors.append(acquire)
    events = []
    for anchor in anchors:
        require_surface_point(anchor, surfaces)
        events.append(c.ContactEvent(
            f'{instance_id}.{anchor.anchor_id}', (instance_id,), anchor.anchor_id, anchor.surface_id,
            c.TimeInterval(0, end), acquire_frames / c.FPS if anchor is acquire else 0,
            release_frames / c.FPS if anchor.anchor_id in release else 0, 0,
            target_world_v1=anchor.position,
        ))
    return end, tuple(events)


def build(instance, entry, profile, surfaces):
    params = {value.name: value.value for value in instance.parameters}
    if instance.definition_id == 'body.balance':
        return build_balance(instance, entry, profile, surfaces, params)
    transfer = instance.definition_id == 'support.transfer'
    mode = 'transfer' if transfer else params['operation']
    anchor_id = params['anchor']
    target = None
    if mode != 'release':
        surface_id = params['surface']
        c.check_type(surface_id, c.ID, 'surface')
        surface = next((item for item in surfaces if item.name == surface_id), None)
        if surface is None:
            c.fail('UNRESOLVED_SURFACE', 'Support surface is unavailable', details={'surface_id': surface_id})
        measured = _values(entry).get(anchor_id + '.position')
        if measured is None:
            c.fail('MISSING_CAPABILITY', 'Support needs a measured anchor', details={'anchor_id': anchor_id})
        position = params['target'] if params['target'] is not None else (*measured[:2], surface.height)
        target = c.ContactAnchor(anchor_id, surface_id, position, 'world', 'metre')
    release = (params['from_anchor'],) if transfer else (anchor_id,) if mode in ('release', 'cycle') else ()
    frame_count = lambda key: round(params[key] * c.FPS)
    duration, events = schedule(
        instance.instance_id, entry, surfaces, acquire=target, release=release,
        acquire_frames=frame_count('acquire_s') if target else 0, hold_frames=frame_count('hold_s'),
        release_frames=frame_count('release_s') if release else 0,
        allow_airborne=False if transfer else params['allow_airborne'],
    )
    return c.MotionFragment(instance.instance_id + '.fragment', (instance.instance_id,), (), duration,
                            (), events, (c.PhaseLandmark('end', duration),), (), ())


def sole_region_margin(point, heel, forefoot):
    """Signed inward margin to a rectangular heel-to-forefoot footprint proxy."""
    dx, dy = (forefoot[i] - heel[i] for i in range(2))
    length = math.hypot(dx, dy)
    if length < .02:
        c.fail('ENTRY_MISMATCH', 'Balance requires a nondegenerate horizontal sole reference')
    x, y = (point[i] - heel[i] for i in range(2))
    along = (x * dx + y * dy) / length
    across = (y * dx - x * dy) / length
    return min(along, length - along, .15 * length - abs(across))


def build_balance(instance, entry, profile, surfaces, params):
    anchor_id = params['anchor']
    if entry.active_contacts != (anchor_id,):
        c.fail('ENTRY_MISMATCH', 'One-foot balance requires only the selected captured sole')
    anchor = next(item for item in entry.contact_anchors if item.anchor_id == anchor_id)
    if anchor.surface_id != 'floor':
        c.fail('UNSUPPORTED_GOAL', 'One-foot balance currently uses the resolved floor')
    measured = _values(entry)
    side = anchor_id.split('.')[0]
    other = 'right' if side == 'left' else 'left'
    heel, forefoot = (measured[f'{side}.{part}.position'] for part in ('heel', 'forefoot'))
    if measured[f'{other}.sole.position'][2] < .02:
        c.fail('ENTRY_MISMATCH', 'The free sole needs at least 20 mm of entry clearance')
    if max(abs(heel[2] - anchor.position[2]), abs(forefoot[2] - anchor.position[2])) > .003:
        c.fail('ENTRY_MISMATCH', 'One-foot balance requires a flat sole reference')
    origin = measured['pelvis.position']
    target = params['target'] if params['target'] is not None else (
        (heel[0] + forefoot[0]) / 2, (heel[1] + forefoot[1]) / 2, origin[2])
    if abs(target[2] - origin[2]) > 1e-6 or math.dist(target, origin) > .22:
        c.fail('INVALID_PARAMETER', 'Balance allows at most 220 mm of horizontal pelvis shift')
    if sole_region_margin(target, heel, forefoot) < .005:
        c.fail('INVALID_PARAMETER', 'The pelvis projection needs 5 mm of margin inside the sole proxy')
    settle = _seconds(params['duration_s'])
    duration, events = schedule(instance.instance_id, entry, surfaces,
                                hold_frames=round((settle + _seconds(params['hold_s'])) * c.FPS))
    fragment = _fragment(instance, entry, profile,
                         {'pelvis.position': [(0, settle, origin, target, None)]},
                         duration, (c.PhaseLandmark('settled', settle), c.PhaseLandmark('end', duration)))
    return replace(fragment, contact_events=events,
                   goals=tuple(replace(goal, tolerance=.002) for goal in fragment.goals))


def register_support(catalog, profile):
    from .registry import register_movement

    capabilities = tuple('measure.' + anchor + '.position' for anchor in FOOT_ANCHORS)
    if profile.version != 8 or not set(capabilities) <= set(profile.capabilities):
        return
    palms = tuple(anchor for anchor in PALM_ANCHORS if 'measure.' + anchor + '.position' in profile.capabilities)
    body = tuple(anchor for anchor in BODY_ANCHORS if 'measure.' + anchor + '.position' in profile.capabilities)
    available = FOOT_ANCHORS + palms + body
    common = (
        _enum('anchor', 'left.sole', available),
        c.ParameterSpec('surface', 'string', 'unitless', None, False, True, 'floor'),
        c.ParameterSpec('target', 'vector', 'metre', 'world', False, True, None, dimensions=3, nullable=True),
        _number('acquire_s', 'second', .8, .5, 2),
        _number('hold_s', 'second', .2, .1, 1),
        _number('release_s', 'second', .8, .5, 2),
    )
    modes = {
        'support.acquire_release': (_enum('operation', 'cycle', ('acquire', 'release', 'cycle')),
                                    c.ParameterSpec('allow_airborne', 'boolean', 'unitless', None, False, True, False)),
        'support.transfer': (_enum('from_anchor', 'right.sole', available),),
    }
    chains = tuple(f'{side}.{part}' for side in ('left', 'right') for part in ('thigh', 'shin', 'ankle'))
    arm_chains = tuple(f'{anchor.split(".")[0]}.{part}' for anchor in palms for part in ('upper_arm', 'forearm', 'wrist'))
    for move, extra in modes.items():
        register_movement(c.MovementDefinition(
            move, 1, 'body', 'Schedule a fixed foot point on a resolved horizontal surface',
            common + extra, capabilities, (), chains + arm_chains + (('pelvis',) if body else ()), (), (), BUILDER_ID,
            ('horizontal_support',), ('end',), 'preserve_end',
        ), catalog)
    balance_caps = ('measure.pelvis.position',)
    if set(balance_caps) <= set(profile.capabilities):
        register_movement(c.MovementDefinition(
            'body.balance', 1, 'body', 'Slow pelvis projection over a geometric one-sole footprint',
            (_enum('anchor', 'left.sole', SOLE_ANCHORS), common[2], _number('duration_s', 'second', 1.5, 1.2, 3),
             _number('hold_s', 'second', .5, .2, 1)),
            capabilities + balance_caps, (), ('pelvis', *chains), (), (), BUILDER_ID,
            ('geometric_balance',), ('settled', 'end'), 'preserve_end',
        ), catalog)
