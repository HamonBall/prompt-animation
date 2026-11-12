"""Finite coordinated movements authored through the shared fragment bridge."""
from dataclasses import replace
import math

from . import contracts as c
from .joints import _enum, _fragment, _number, _path, _seconds, _values
from .legs import hip_position, reachable
from .root_motion import CONTROLS, ORIENTATION, POSITION, RELEASE_S
from .spatial import angle_rotation, inverse, multiply, normalize, rotate
from .support import PALM_ANCHORS, SOLE_ANCHORS, require_surface_point, schedule

BUILDER_ID = 'body.coordinated.v1'
LEG_CHAINS = tuple(f'{side}.{part}' for side in ('left', 'right')
                   for part in ('thigh', 'shin', 'ankle'))
ARM_CHAINS = tuple(f'{side}.{part}' for side in ('left', 'right')
                   for part in ('upper_arm', 'forearm', 'wrist'))
CRAWL_ANCHORS = (*PALM_ANCHORS, *SOLE_ANCHORS)
KNEE_CRAWL_ANCHORS = (*PALM_ANCHORS, 'left.knee.support', 'right.knee.support')
CRAWL_ENDPOINTS = tuple(f'{side}.{part}.{quantity}' for side in ('left', 'right')
                        for part in ('hand', 'foot') for quantity in ('position', 'orientation'))
KNEE_CRAWL_ENDPOINTS = ('left.hand.position', 'left.hand.orientation', 'right.hand.position',
                        'right.hand.orientation', 'left.knee.support.position', 'right.knee.support.position')


def build(instance, entry, profile, surfaces):
    """Author one bounded route from its measured support state."""
    move = instance.definition_id
    params = {item.name: item.value for item in instance.parameters}
    if move in ('body.floor_transfer', 'body.kneel_rise'):
        if params.get('route') == 'standing_to_seated':
            return build_standing_to_seated(instance, entry, profile, surfaces, params)
        if params.get('route') == 'seated_to_back':
            return build_seated_to_back(instance, entry, profile, surfaces, params)
        if params.get('route') == 'planted_to_knee':
            return build_planted_kneel(instance, entry, profile, surfaces, params)
        return build_body_contact(instance, entry, surfaces, params)
    if move == 'body.crawl':
        return build_crawl(instance, entry, profile, surfaces, params)

    anchors = floor_soles(entry, surfaces, SOLE_ANCHORS)
    if move == 'body.step':
        return build_step(instance, entry, profile, params, anchors)
    if move == 'body.takeoff_land':
        return build_takeoff_land(instance, entry, profile, params)
    origin = _values(entry)['pelvis.position']
    lowered = (*origin[:2], origin[2] - params['depth_m'])
    arrival = 'lowered'
    if move == 'body.lunge':
        lowered = lunge_target(entry, params, anchors, lowered)
        arrival = 'loaded'
    phase = _seconds(params['phase_s'])
    hold = _seconds(params['hold_s'])
    path, duration = _path(origin, [lowered], phase, hold, 'return_to_entry')
    fragment = _fragment(instance, entry, profile, {'pelvis.position': path}, duration,
                         (c.PhaseLandmark(arrival, phase), c.PhaseLandmark('end', duration)))
    return replace(fragment, goals=tuple(replace(goal, tolerance=.002) for goal in fragment.goals))


def floor_soles(entry, surfaces, required):
    if set(entry.active_contacts) != set(required):
        c.fail('ENTRY_MISMATCH', 'The route requires its declared floor sole contacts',
               details={'required': required, 'active': entry.active_contacts})
    anchors = {anchor.anchor_id: anchor for anchor in entry.contact_anchors if anchor.anchor_id in required}
    for anchor in anchors.values():
        if anchor.surface_id != 'floor':
            c.fail('ENTRY_MISMATCH', 'The route requires captured soles on the floor')
        require_surface_point(anchor, surfaces)
    return anchors


def build_body_contact(instance, entry, surfaces, params):
    kneel = instance.definition_id == 'body.kneel_rise'
    if kneel:
        side = params['side']
        required = tuple(sole for sole in SOLE_ANCHORS if sole != side + '.sole')
        anchor_id = side + '.knee.support'
    else:
        required = SOLE_ANCHORS
        anchor_id = 'pelvis.support'
    floor_soles(entry, surfaces, required)
    surface = next((item for item in surfaces if item.name == params['surface']), None)
    if surface is None:
        c.fail('UNRESOLVED_SURFACE', 'Body support surface is unavailable', details={'surface_id': params['surface']})
    values = _values(entry)
    point = values[anchor_id + '.position']
    if abs(point[2] - surface.height) > .16:
        c.fail('ENTRY_MISMATCH', 'The route requires a prepared entry near the support surface',
               details={'anchor_id': anchor_id, 'reference_height_m': point[2] - surface.height})
    target = c.ContactAnchor(anchor_id, surface.name, (*point[:2], surface.height), 'world', 'metre')
    phase = round(_seconds(params['phase_s']) * c.FPS)
    hold = round(_seconds(params['hold_s']) * c.FPS)
    duration, events = schedule(instance.instance_id, entry, surfaces, acquire=target,
                                release=(anchor_id,) if kneel else (), acquire_frames=phase,
                                hold_frames=hold, release_frames=phase if kneel else 0)
    return c.MotionFragment(instance.instance_id + '.fragment', (instance.instance_id,), (), duration, (), events,
                            (c.PhaseLandmark('supported', phase / c.FPS), c.PhaseLandmark('end', duration)), (), ())


def build_standing_to_seated(instance, entry, profile, surfaces, params):
    floor_soles(entry, surfaces, SOLE_ANCHORS)
    if params['surface'] != 'floor':
        c.fail('UNSUPPORTED_GOAL', 'Standing-to-seated uses the resolved floor')
    values = _values(entry)
    pelvis = values['pelvis.position']
    heading = horizontal_heading(entry)
    if pelvis[2] < .35 * profile.height_m:
        c.fail('ENTRY_MISMATCH', 'Standing-to-seated needs a standing or shallow crouched entry')
    lengths = {length.id: length.value_m for length in profile.lengths}
    leg_reach = min(lengths[side + '.thigh'] + lengths[side + '.shin'] for side in ('left', 'right'))
    setback = tuple(-.73 * leg_reach * component for component in heading)
    approach = (*(pelvis[i] + setback[i] for i in range(2)), .15 * profile.height_m)
    skin_reference = values['pelvis.support.position']
    orientation = values['pelvis.orientation']
    reclined = multiply(orientation, angle_rotation(pitch=-28))
    offset = rotate(multiply(reclined, inverse(orientation)), tuple(a - b for a, b in zip(skin_reference, pelvis)))
    target = c.ContactAnchor('pelvis.support', 'floor',
                             (*(approach[i] + offset[i] for i in range(2)), 0), 'world', 'metre')
    approach_frames = round(_seconds(params['approach_s']) * c.FPS)
    acquire_frames = round(_seconds(params['phase_s']) * c.FPS)
    hold_frames = round(_seconds(params['hold_s']) * c.FPS)
    arrival = approach_frames / c.FPS
    supported = (approach_frames + acquire_frames) / c.FPS
    end, events = schedule(instance.instance_id, entry, surfaces, acquire=target,
                           acquire_frames=acquire_frames, hold_frames=approach_frames + hold_frames)
    events = tuple(replace(event, interval=c.TimeInterval(arrival, end)) if event.anchor_id == target.anchor_id else event
                   for event in events)
    head = values['head.orientation']
    paths = {'pelvis.position': [(0, arrival, pelvis, approach, None)],
             'pelvis.orientation': [(0, arrival, orientation, reclined, None)],
             'head.orientation': [(0, arrival, head, head, None)]}
    fragment = _fragment(instance, entry, profile, paths, end,
                         (c.PhaseLandmark('approached', arrival), c.PhaseLandmark('supported', supported),
                          c.PhaseLandmark('end', end)))
    goals = tuple(replace(goal, tolerance=.002) if goal.target.unit == 'metre' else goal for goal in fragment.goals)
    return replace(fragment, contact_events=events, goals=goals)


def fixed_event(instance, anchor, start, end, *, acquire=0, release=0, suffix=''):
    return c.ContactEvent(instance.instance_id + '.' + anchor.anchor_id + suffix, (instance.instance_id,),
                          anchor.anchor_id, anchor.surface_id, c.TimeInterval(start, end), acquire, release, 0,
                          anchor.position)


def build_seated_to_back(instance, entry, profile, surfaces, params):
    anchors = floor_soles(entry, surfaces, (*SOLE_ANCHORS, 'pelvis.support'))
    if params['surface'] != 'floor':
        c.fail('UNSUPPORTED_GOAL', 'Seated-to-back uses the resolved floor')
    values = _values(entry)
    if 'back.support.position' not in values:
        c.fail('MISSING_CAPABILITY', 'Seated-to-back needs a calibrated back support reference')
    pelvis, orientation = values['pelvis.position'], values['pelvis.orientation']
    incline = math.degrees(math.asin(max(-1, min(1, rotate(orientation, (0, 1, 0))[2]))))
    if not 10 <= incline <= 45 or pelvis[2] > .20 * profile.height_m:
        c.fail('ENTRY_MISMATCH', 'Seated-to-back needs a low seated entry with a captured pelvis contact')
    reclined = multiply(orientation, angle_rotation(pitch=incline - 79))
    rotation = multiply(reclined, inverse(orientation))
    back = rotate(rotation, tuple(a - b for a, b in zip(values['back.support.position'], pelvis)))
    seat = rotate(rotation, tuple(a - b for a, b in zip(values['pelvis.support.position'], pelvis)))
    forward = rotate(orientation, (0, 1, 0))
    heading = normalize((*forward[:2], 0))
    shifted = tuple(pelvis[i] + .045 * heading[i] for i in range(2))
    # Allow extra clearance for the seated skin as it rotates away from the floor.
    target = (*shifted, max(pelvis[2], .055 - back[2], .085 - seat[2]))
    anchor = c.ContactAnchor('back.support', 'floor', (*(target[i] + back[i] for i in range(2)), 0), 'world', 'metre')
    require_surface_point(anchor, surfaces)
    approach = round(_seconds(params['approach_s']) * c.FPS)
    acquisition = round(_seconds(params['phase_s']) * c.FPS)
    hold = round(_seconds(params['hold_s']) * c.FPS)
    arrival = approach / c.FPS
    start = (approach + 1) / c.FPS
    end = (approach + 1 + acquisition + hold) / c.FPS
    contacts = tuple(fixed_event(instance, anchors[sole], 0, end) for sole in SOLE_ANCHORS)
    contacts += (fixed_event(instance, anchors['pelvis.support'], 0, RELEASE_S, release=RELEASE_S),
                 fixed_event(instance, anchor, start, end, acquire=acquisition / c.FPS))
    paths = {'pelvis.position': [(0, RELEASE_S, pelvis, pelvis, None), (RELEASE_S, arrival, pelvis, target, None)],
             'pelvis.orientation': [(0, RELEASE_S, orientation, orientation, None),
                                    (RELEASE_S, arrival, orientation, reclined, None)]}
    fragment = _fragment(instance, entry, profile, paths, end,
                         (c.PhaseLandmark('approached', arrival), c.PhaseLandmark('supported', start + acquisition / c.FPS),
                          c.PhaseLandmark('end', end)))
    return replace(fragment, contact_events=contacts)


def build_planted_kneel(instance, entry, profile, surfaces, params):
    anchors = floor_soles(entry, surfaces, SOLE_ANCHORS)
    if params['surface'] != 'floor':
        c.fail('UNSUPPORTED_GOAL', 'Planted-to-knee uses the resolved floor')
    side = params['side']
    sole = side + '.sole'
    stance = next(anchor for anchor in SOLE_ANCHORS if anchor != sole)
    values = _values(entry)
    pelvis = values['pelvis.position']
    lengths = {item.id: item.value_m for item in profile.lengths}
    thigh = lengths[side + '.thigh']
    hip = hip_position(values, profile, side)
    heading = horizontal_heading(entry)
    # Keep the planted shin closer to vertical when the free knee takes load.
    setback = .55 * thigh
    target = (*(pelvis[i] - setback * heading[i] for i in range(2)), thigh - (hip[2] - pelvis[2]) + .10)
    knee = c.ContactAnchor(side + '.knee.support', 'floor',
                           (*(hip[i] - setback * heading[i] for i in range(2)), 0), 'world', 'metre')
    require_surface_point(knee, surfaces)
    release = round(RELEASE_S * c.FPS)
    approach = round(_seconds(params['approach_s']) * c.FPS)
    phase = round(_seconds(params['phase_s']) * c.FPS)
    hold = round(_seconds(params['hold_s']) * c.FPS)
    raised = (release + round(.25 * approach)) / c.FPS
    tucked = (release + round(.50 * approach)) / c.FPS
    arrival = (release + approach) / c.FPS
    lift = (release + approach + 2 * phase + hold) / c.FPS
    recovered = (release + 2 * approach + 2 * phase + hold) / c.FPS
    end = (2 * release + 2 * approach + 2 * phase + hold) / c.FPS
    untucked = recovered - (tucked - RELEASE_S)
    unraised = recovered - (raised - RELEASE_S)
    hip_flexion = side + '.hip.flexion'
    knee_flexion = side + '.knee.flexion'
    paths = {}
    # Lift the foot and fold the shin before lowering the pelvis. The hip and
    # knee initially flex together to keep the toes from pitching into the floor.
    for key, raised_value, tucked_value, goal in (
        ('pelvis.position', pelvis, pelvis, target),
        (hip_flexion, min(65., values[hip_flexion] + 34.), 24., 0.),
        (knee_flexion, min(90., values[knee_flexion] + 34.), 85., 115.),
    ):
        origin = values[key]
        paths[key] = [(0, RELEASE_S, origin, origin, None), (RELEASE_S, raised, origin, raised_value, None),
                      (raised, tucked, raised_value, tucked_value, None), (tucked, arrival, tucked_value, goal, None),
                      (arrival, lift, goal, goal, None), (lift, untucked, goal, tucked_value, None),
                      (untucked, unraised, tucked_value, raised_value, None), (unraised, recovered, raised_value, origin, None)]
    contacts = (fixed_event(instance, anchors[stance], 0, end),
                fixed_event(instance, anchors[sole], 0, RELEASE_S, release=RELEASE_S),
                fixed_event(instance, knee, arrival, lift, acquire=phase / c.FPS, release=phase / c.FPS),
                fixed_event(instance, anchors[sole], recovered, end, acquire=RELEASE_S, suffix='.land'))
    fragment = _fragment(instance, entry, profile, paths, end,
                         (c.PhaseLandmark('supported', arrival + phase / c.FPS), c.PhaseLandmark('end', end)))
    return replace(fragment, contact_events=contacts)


def horizontal_heading(entry, *, minimum_projection=.9):
    forward = rotate(entry.root_transform.orientation, (0, 1, 0))
    horizontal = math.hypot(*forward[:2])
    if horizontal < minimum_projection:
        c.fail('ENTRY_MISMATCH', 'The entry forward direction has insufficient horizontal projection')
    return tuple(component / horizontal for component in forward[:2])


def lunge_target(entry, params, anchors, lowered):
    heading = horizontal_heading(entry)
    lead = params['lead'] + '.sole'
    rear = next(anchor for anchor in SOLE_ANCHORS if anchor != lead)
    span = sum((anchors[lead].position[i] - anchors[rear].position[i]) * heading[i] for i in range(2))
    if not .16 <= span <= .50:
        c.fail('ENTRY_MISMATCH', 'Lunge needs the selected lead sole 160–500 mm ahead of the rear sole',
               details={'lead': lead, 'forward_span_m': span})
    remaining = sum((anchors[lead].position[i] - lowered[i]) * heading[i] for i in range(2))
    if params['advance_m'] > remaining:
        c.fail('INVALID_PARAMETER', 'Lunge target would carry the pelvis past the lead sole')
    return (*(lowered[i] + heading[i] * params['advance_m'] for i in range(2)), lowered[2])


def landing(event, touchdown, end):
    return replace(event, event_id=event.event_id + '.landing', interval=c.TimeInterval(touchdown, end),
                   acquire_s=end - touchdown)


def build_step(instance, entry, profile, params, anchors):
    side = params['side']
    sole = side + '.sole'
    position = side + '.foot.position'
    orientation = side + '.foot.orientation'
    values = _values(entry)
    origin = values[position]
    heading = horizontal_heading(entry)
    distance = params['distance_m']
    target = (*(origin[i] + distance * heading[i] for i in range(2)), origin[2] - anchors[sole].position[2])
    apex = (*((origin[i] + target[i]) / 2 for i in range(2)), target[2] + params['clearance_m'])
    pelvis = values['pelvis.position']
    advance = (*(pelvis[i] + .5 * distance * heading[i] for i in range(2)), pelvis[2])
    for point, fraction in ((apex, .25), (target, .5)):
        shifted = dict(values)
        shifted[position] = (*(origin[i] + fraction * distance * heading[i] for i in range(2)), origin[2])
        reachable(shifted, profile, side, point)
    phase_frames = round(_seconds(params['phase_s']) * c.FPS)
    mid = (round(RELEASE_S * c.FPS) + phase_frames) / c.FPS
    touchdown = (round(RELEASE_S * c.FPS) + 2 * phase_frames) / c.FPS
    end = (round(touchdown * c.FPS) + round(RELEASE_S * c.FPS)) / c.FPS
    paths = {
        position: [(0, RELEASE_S, origin, origin, None), (RELEASE_S, mid, origin, apex, None),
                   (mid, touchdown, apex, target, None), (touchdown, end, target, target, None)],
        orientation: [(0, end, values[orientation], values[orientation], None)],
        'pelvis.position': [(0, RELEASE_S, pelvis, pelvis, None),
                            (RELEASE_S, touchdown, pelvis, advance, None)],
    }
    fragment = _fragment(instance, entry, profile, paths, end,
                         (c.PhaseLandmark('swing', mid), c.PhaseLandmark('touchdown', touchdown),
                          c.PhaseLandmark('end', end)))
    fixed = tuple(replace(event, target_world_v1=anchors[event.anchor_id].position)
                  for event in fragment.contact_events)
    step_event = next(event for event in fixed if event.anchor_id == sole)
    contacts = tuple(event for event in fixed if event.anchor_id != sole)
    old = anchors[sole].position
    landing_point = (*(old[i] + distance * heading[i] for i in range(2)), 0)
    return replace(fragment, contact_events=(*contacts,
        replace(step_event, interval=c.TimeInterval(0, RELEASE_S), release_s=RELEASE_S),
        replace(landing(step_event, touchdown, end), target_world_v1=landing_point)))


def build_takeoff_land(instance, entry, profile, params):
    values = _values(entry)
    origin = values[POSITION]
    apex = (*origin[:2], origin[2] + params['height_m'])
    rise_frames = round(_seconds(params['phase_s']) * c.FPS)
    release_frames = round(RELEASE_S * c.FPS)
    load_frames = 20
    launch_frames = load_frames + 16
    loaded = load_frames / c.FPS
    launch = launch_frames / c.FPS
    peak = (launch_frames + rise_frames) / c.FPS
    touchdown = (launch_frames + 2 * rise_frames) / c.FPS
    planted = (launch_frames + release_frames + 2 * rise_frames) / c.FPS
    recovery_frames = 20
    compressed = (round(planted * c.FPS) + recovery_frames) / c.FPS
    end = (round(planted * c.FPS) + 2 * recovery_frames) / c.FPS
    pelvis = values['pelvis.position']
    push_off = (*pelvis[:2], pelvis[2] - params['push_off_depth_m'])
    lifted = (*pelvis[:2], pelvis[2] + params['height_m'])
    cushion = (*pelvis[:2], pelvis[2] - params['recovery_depth_m'])
    paths = {
        POSITION: [(0, launch, origin, origin, None), (launch, peak, origin, apex, None),
                   (peak, touchdown, apex, origin, None), (touchdown, end, origin, origin, None)],
        ORIENTATION: [(0, end, values[ORIENTATION], values[ORIENTATION], None)],
        'pelvis.position': [(0, loaded, pelvis, push_off, None), (loaded, launch, push_off, pelvis, None),
                            (launch, peak, pelvis, lifted, None), (peak, touchdown, lifted, pelvis, None),
                            (touchdown, planted, pelvis, pelvis, None),
                            (planted, compressed, pelvis, cushion, None),
                            (compressed, end, cushion, pelvis, None)],
    }
    fragment = _fragment(instance, entry, profile, paths, end,
                         (c.PhaseLandmark('loaded', loaded), c.PhaseLandmark('liftoff', launch),
                          c.PhaseLandmark('apex', peak), c.PhaseLandmark('touchdown', touchdown),
                          c.PhaseLandmark('compressed', compressed), c.PhaseLandmark('end', end)))
    releases = tuple(replace(event, interval=c.TimeInterval(0, launch), release_s=RELEASE_S)
                     for event in fragment.contact_events)
    landings = tuple(replace(landing(event, touchdown, end), acquire_s=planted - touchdown)
                     for event in fragment.contact_events)
    goals = tuple(replace(goal, tolerance=.002) if goal.target.control_id == 'pelvis.position' else goal
                  for goal in fragment.goals)
    return replace(fragment, contact_events=(*releases, *landings), goals=goals)


def build_crawl(instance, entry, profile, surfaces, params):
    on_knees = params['support'] == 'hands_knees'
    required = KNEE_CRAWL_ANCHORS if on_knees else CRAWL_ANCHORS
    if set(entry.active_contacts) != set(required):
        c.fail('ENTRY_MISMATCH', 'Crawl needs both palms and the selected pair of lower-body contacts',
               details={'required': required, 'actual': entry.active_contacts})
    anchors = {anchor.anchor_id: anchor for anchor in entry.contact_anchors if anchor.anchor_id in required}
    if on_knees:
        orientation = entry.root_transform.orientation
        if rotate(orientation, (0, 1, 0))[2] > -.8:
            c.fail('ENTRY_MISMATCH', 'Hands-and-knees crawl needs a forward-inclined pelvis')
        forward = rotate(orientation, (0, 0, 1))
        heading = normalize((*forward[:2], 0.))[:2]
    else:
        heading = horizontal_heading(entry, minimum_projection=.3)
    values = _values(entry)
    distance = params['distance_m']
    clearance = params['clearance_m']
    swing_frames = round(_seconds(params['swing_s']) * c.FPS)
    ramp = 4
    ramp_s = ramp / c.FPS
    stride = 2 * ramp + swing_frames
    end = 4 * stride / c.FPS
    lead = params['lead']
    other = 'right' if lead == 'left' else 'left'
    support = '.knee.support' if on_knees else '.sole'
    order = (lead + '.palm', other + support, other + '.palm', lead + support)
    paths = {}
    contacts = []
    phases = []

    def translated(point):
        return (*(point[i] + distance * heading[i] for i in range(2)), point[2])

    for index, anchor_id in enumerate(order):
        anchor = anchors[anchor_id]
        surface = require_surface_point(anchor, surfaces)
        if (on_knees or anchor_id in SOLE_ANCHORS) and anchor.surface_id != 'floor':
            c.fail('ENTRY_MISMATCH', 'Crawl requires the selected contacts on the floor')
        start = (index * stride + ramp) / c.FPS
        apex = (index * stride + ramp + swing_frames // 2) / c.FPS
        touchdown = ((index + 1) * stride - ramp) / c.FPS
        landing_target = translated((*anchor.position[:2], surface.height))
        require_surface_point(replace(anchor, position=landing_target), surfaces)
        key = anchor_id.replace('.palm', '.hand').replace('.sole', '.foot')
        endpoint = values[key + '.position']
        target = tuple(value + after - before for value, before, after in zip(endpoint, anchor.position, landing_target))
        mid = tuple((a + b) / 2 for a, b in zip(endpoint, target))
        lifted = (*mid[:2], max(endpoint[2], target[2]) + clearance)
        paths[key + '.position'] = [(0, start, endpoint, endpoint, None),
                                    (start, apex, endpoint, lifted, None), (apex, touchdown, lifted, target, None)]
        if not key.endswith('.knee.support'):
            orientation = values[key + '.orientation']
            paths[key + '.orientation'] = [(0, end, orientation, orientation, None)]
        event_id = instance.instance_id + '.' + anchor_id
        contacts.append(c.ContactEvent(event_id, (instance.instance_id,), anchor_id, anchor.surface_id,
                                       c.TimeInterval(0, start), 0, ramp_s, 0, anchor.position))
        contacts.append(c.ContactEvent(event_id + '.land', (instance.instance_id,), anchor_id, anchor.surface_id,
                                       c.TimeInterval(touchdown, end), ramp_s, 0, 0, landing_target))
        phases.append(c.PhaseLandmark(anchor_id + '.touchdown', touchdown))

    pelvis = values['pelvis.position']
    lateral = (heading[1], -heading[0])
    shift = min(.018, .36 * distance) * (1 if lead == 'left' else -1)
    # Transfer across the supporting limbs as each swing passes its apex.
    # Use short chords so forward travel continues through the weight shifts.
    waypoints = [(0., pelvis)]
    for index in range(1, 24):
        frame = round(4 * stride * index / 24)
        phase = frame / (4 * stride)
        blend = math.sin(math.pi * phase)
        sway = math.sin(4 * math.pi * (phase + (.02 if on_knees else 0.)))
        forward = distance * phase * phase * (3 - 2 * phase)
        limb, offset = divmod(frame, stride)
        knee_lift = 0.
        if on_knees and limb % 2 and ramp <= offset <= ramp + swing_frames:
            knee_lift = .5 * clearance * math.sin(math.pi * (offset - ramp) / swing_frames) ** 2
        point = (*(pelvis[i] + heading[i] * forward + lateral[i] * shift * sway * blend for i in range(2)),
                 pelvis[2] + (knee_lift if on_knees else -.006 * sway * sway * blend))
        waypoints.append((frame / c.FPS, point))
    waypoints.append((end, translated(pelvis)))
    paths['pelvis.position'] = [(start, stop, a, b, None)
                               for (start, a), (stop, b) in zip(waypoints, waypoints[1:])]
    fragment = _fragment(instance, entry, profile, paths, end, (*phases, c.PhaseLandmark('end', end)))
    tracks = tuple(replace(track, curve=replace(track.curve, easing='linear'))
                   if track.control_id == 'pelvis.position' else track for track in fragment.tracks)
    return replace(fragment, tracks=tracks, contact_events=tuple(contacts))


def validate_crawl_support(events, duration):
    """Check fully held support between contact boundaries as well as at entry and exit."""
    held = tuple((event.anchor_id, event.interval.start_s + event.acquire_s,
                  event.interval.end_s - event.release_s) for event in events)
    boundaries = sorted({0, duration, *(time for _, start, end in held for time in (start, end))})
    probes = [(0, 4), (duration, 4), *(((a + b) / 2, 3) for a, b in zip(boundaries, boundaries[1:])
                                     if b - a > 1e-9)]
    for time, minimum in probes:
        if len({anchor for anchor, start, end in held if start - 1e-9 <= time <= end + 1e-9}) < minimum:
            c.fail('CONSTRAINT_CONFLICT', 'Crawl must keep three held contacts through each swing and four at its boundaries',
                   details={'time_s': time})


def has_step_support(entry, events, controls, duration):
    """Recognize the two-sole support envelope for a pelvis-and-foot track."""
    if set(entry.active_contacts) != set(SOLE_ANCHORS) or len(events) != 3:
        return False
    for stance in events:
        if (stance.anchor_id not in SOLE_ANCHORS or stance.acquire_s or stance.release_s
                or stance.interval != c.TimeInterval(0, duration)):
            continue
        swing = next(sole for sole in SOLE_ANCHORS if sole != stance.anchor_id)
        foot = swing.replace('.sole', '.foot')
        return (controls == {'pelvis.position', foot + '.position', foot + '.orientation'}
                and all(event.surface_id == 'floor' for event in events)
                and all(event.anchor_id == swing for event in events if event is not stance)
                and any(event.anchor_id == swing and event.interval.end_s == duration
                        and event.acquire_s and not event.release_s for event in events))
    return False


def grounded_root_windows(motion, controls):
    """Bound planted articulation to the original root before release and after landing."""
    if controls != {*CONTROLS, 'pelvis.position'} or set(motion.entry_snapshot.active_contacts) != set(SOLE_ANCHORS):
        return ()
    events = motion.contact_events
    if len(events) != 4 or any(event.target_world_v1 is not None or event.surface_id != 'floor' for event in events):
        return ()
    release = [event for event in events if event.interval.start_s == 0 and event.release_s and not event.acquire_s]
    landing_events = [event for event in events if event.interval.start_s > 0 and event.acquire_s
                      and not event.release_s and event.interval.end_s == motion.duration_s]
    if any({event.anchor_id for event in group} != set(SOLE_ANCHORS) for group in (release, landing_events)):
        return ()
    launch = min(event.interval.end_s for event in release)
    recovery = max(event.interval.start_s + event.acquire_s for event in landing_events)
    if launch >= min(event.interval.start_s for event in landing_events) or recovery >= motion.duration_s:
        return ()
    windows = (c.TimeInterval(0, launch), c.TimeInterval(recovery, motion.duration_s))
    values = _values(motion.entry_snapshot)
    for control in CONTROLS:
        tracks = sorted((track for track in motion.tracks if track.control_id == control),
                        key=lambda track: track.interval.start_s)
        for window in windows:
            active = [track for track in tracks if track.interval.start_s <= window.start_s + 1e-9]
            if not active:
                return ()
            remaining = [track for track in tracks if window.start_s + 1e-9 < track.interval.start_s < window.end_s]
            if any(track.curve.start_value != values[control] or track.curve.end_value != values[control]
                   for track in (active[-1], *remaining)):
                return ()
    root_paths = [track for track in motion.tracks if track.control_id == POSITION]
    for track in (item for item in motion.tracks if item.control_id == 'pelvis.position'):
        interval = track.interval
        if any(window.start_s - 1e-9 <= interval.start_s and interval.end_s <= window.end_s + 1e-9
               for window in windows):
            continue
        covering = [path for path in root_paths if path.interval.start_s <= interval.start_s
                    and path.interval.end_s >= interval.end_s]
        if len(covering) != 1:
            return ()
        path, = covering
        if path.curve.start_value != path.curve.end_value and (path.interval != interval or path.curve.easing != track.curve.easing):
            return ()
        for root_point, pelvis_point in ((path.curve.start_value, track.curve.start_value),
                                         (path.curve.end_value, track.curve.end_value)):
            if root_point is None or pelvis_point is None:
                return ()
            expected = tuple(pelvis + root - origin for pelvis, root, origin in zip(values['pelvis.position'], root_point, values[POSITION]))
            if math.dist(pelvis_point, expected) > 1e-7:
                return ()
    return windows


def has_seated_approach(motion, controls):
    """Recognize a tracked pelvis descent followed by a floor seat acquisition."""
    if (controls != {'pelvis.position', 'pelvis.orientation', 'head.orientation'}
            or len(motion.tracks) != 3 or len(motion.contact_events) != 3
            or set(motion.entry_snapshot.active_contacts) != set(SOLE_ANCHORS)):
        return False
    arrival = motion.tracks[0].interval.end_s
    if (any(track.interval != c.TimeInterval(0, arrival) for track in motion.tracks)
            or any(goal.interval.end_s > arrival for goal in motion.goal_checks)):
        return False
    contacts = {event.anchor_id: event for event in motion.contact_events}
    if set(contacts) != {*SOLE_ANCHORS, 'pelvis.support'}:
        return False
    if any(event.surface_id != 'floor' or event.interval.end_s != motion.duration_s or event.release_s
           for event in contacts.values()):
        return False
    seat = contacts['pelvis.support']
    return (seat.interval.start_s == arrival and seat.acquire_s > 0
            and all(contacts[sole].interval.start_s == 0 and not contacts[sole].acquire_s for sole in SOLE_ANCHORS))


def has_floor_body_transition(motion, controls):
    """Recognize the explicitly supported back and single-knee handoffs."""
    events = motion.contact_events
    if len(events) != 4 or any(event.surface_id != 'floor' or event.target_world_v1 is None for event in events):
        return False
    held = {event.anchor_id for event in events if event.interval == c.TimeInterval(0, motion.duration_s)
            and not event.acquire_s and not event.release_s}
    if held == set(SOLE_ANCHORS) and controls == {'pelvis.position', 'pelvis.orientation'}:
        seat = next((event for event in events if event.anchor_id == 'pelvis.support'), None)
        back = next((event for event in events if event.anchor_id == 'back.support'), None)
        return bool(seat and back and seat.interval.start_s == 0 and seat.release_s and not seat.acquire_s
                    and back.interval.start_s > seat.interval.end_s and back.interval.end_s == motion.duration_s
                    and back.acquire_s and not back.release_s)
    if len(held) != 1 or not held <= set(SOLE_ANCHORS):
        return False
    swing = next(sole for sole in SOLE_ANCHORS if sole not in held)
    side = swing.split('.')[0]
    if controls != {'pelvis.position', side + '.hip.flexion', side + '.knee.flexion'}:
        return False
    steps = sorted((event for event in events if event.anchor_id == swing), key=lambda event: event.interval.start_s)
    knee = next((event for event in events if event.anchor_id == side + '.knee.support'), None)
    if len(steps) != 2 or knee is None:
        return False
    release, landing_event = steps
    return bool(release.interval.start_s == 0 and release.release_s and not release.acquire_s
                and release.interval.end_s < knee.interval.start_s < knee.interval.end_s < landing_event.interval.start_s
                and knee.acquire_s and knee.release_s and landing_event.acquire_s and not landing_event.release_s
                and landing_event.interval.end_s == motion.duration_s)


def register_coordinated(catalog, profile):
    from .registry import register_movement

    capabilities = ('measure.pelvis.position', 'measure.left.sole.position', 'measure.right.sole.position')
    if profile.version != 8 or not set(capabilities) <= set(profile.capabilities):
        return
    common = (_number('phase_s', 'second', 1.2, .9, 2), _number('hold_s', 'second', .2, .1, .6))
    routes = (
        ('body.lower_rise', 'Lower and rise with two captured floor soles', 'lowered',
         (_number('depth_m', 'metre', .06, .03, .10),)),
        ('body.lunge', 'Load and recover a captured staggered floor stance', 'loaded',
         (_enum('lead', 'left', ('left', 'right')), _number('depth_m', 'metre', .06, .04, .10),
          _number('advance_m', 'metre', .06, .04, .10))),
    )
    for move, description, arrival, parameters in routes:
        register_movement(c.MovementDefinition(
            move, 1, 'body', description, parameters + common,
            capabilities, (), ('pelvis', *LEG_CHAINS), (), (), BUILDER_ID,
            ('horizontal_support',), (arrival, 'end'), 'return_to_entry',
        ), catalog)
    for move, description, markers, parameters, measures, chains in (
        ('body.step', 'Advance the pelvis and one foot while the stance sole remains fixed', ('swing', 'touchdown', 'end'),
         (_enum('side', 'left', ('left', 'right')), _number('distance_m', 'metre', .10, .06, .16),
          _number('clearance_m', 'metre', .06, .04, .09), _number('phase_s', 'second', .8, .7, 1.4)),
         tuple(f'{side}.foot.{part}' for side in ('left', 'right') for part in ('position', 'orientation')),
         ('pelvis', *LEG_CHAINS)),
        ('body.takeoff_land', 'Load, extend, fly and recover through both planted legs',
         ('loaded', 'liftoff', 'apex', 'touchdown', 'compressed', 'end'),
         (_number('height_m', 'metre', .20, .12, .35), _number('phase_s', 'second', .8, .7, 1.4),
          _number('push_off_depth_m', 'metre', .075, .04, .10), _number('recovery_depth_m', 'metre', .055, .03, .08)),
         tuple(sorted(CONTROLS)), ('pelvis', *LEG_CHAINS)),
    ):
        required = capabilities + tuple('measure.' + control for control in measures)
        if set(required) <= set(profile.capabilities):
            register_movement(c.MovementDefinition(
                move, 1, 'body', description, parameters, required, (), chains, (), (), BUILDER_ID,
                ('horizontal_support',), markers, 'preserve_end',
            ), catalog)
    surface = c.ParameterSpec('surface', 'string', 'unitless', None, False, True, 'floor')
    for move, description, anchors, return_policy in (
        ('body.floor_transfer', 'Lower a prepared two-sole stance onto pelvis support', ('pelvis.support',), 'preserve_end'),
        ('body.kneel_rise', 'Lower a prepared free knee onto support and rise', ('left.knee.support', 'right.knee.support'),
         'return_to_entry'),
    ):
        available = tuple(anchor for anchor in anchors if 'measure.' + anchor + '.position' in profile.capabilities)
        if available:
            sides = tuple(anchor.split('.')[0] for anchor in available) if move == 'body.kneel_rise' else ()
            floor_routes = ('prepared_seat', 'standing_to_seated')
            if 'measure.back.support.position' in profile.capabilities:
                floor_routes += ('seated_to_back',)
            parameters = ((_enum('side', sides[0], sides), _enum('route', 'prepared_knee', ('prepared_knee', 'planted_to_knee')))
                          if sides else (_enum('route', 'prepared_seat', floor_routes),))
            parameters += (_number('approach_s', 'second', 2.8, 2.2, 3.5),)
            route_caps = () if sides else ('measure.pelvis.orientation', 'measure.head.orientation')
            if not set(route_caps) <= set(profile.capabilities):
                continue
            register_movement(c.MovementDefinition(
                move, 1, 'body', description, parameters + (surface, *common),
                capabilities + route_caps + tuple('measure.' + anchor + '.position' for anchor in available), (),
                ('pelvis', *LEG_CHAINS, *(('head',) if not sides else ())), (), (), BUILDER_ID, ('horizontal_support',),
                ('supported', 'end'), return_policy,
            ), catalog)
    crawl_caps = capabilities + tuple('measure.' + key for key in (
        *CRAWL_ENDPOINTS, *(anchor + '.position' for anchor in PALM_ANCHORS)))
    if set(crawl_caps) <= set(profile.capabilities):
        knee_caps = {'measure.' + key for key in KNEE_CRAWL_ENDPOINTS}
        support_modes = ('hands_feet', 'hands_knees') if knee_caps <= set(profile.capabilities) else ('hands_feet',)
        register_movement(c.MovementDefinition(
            'body.crawl', 1, 'body', 'Advance from measured palms and soles or knees one limb at a time',
            (_enum('lead', 'left', ('left', 'right')), _number('distance_m', 'metre', .06, .04, .10),
             _number('clearance_m', 'metre', .04, .03, .06), _number('swing_s', 'second', .6, .5, .9),
             _enum('support', 'hands_feet', support_modes)),
            crawl_caps, (), ('pelvis', *ARM_CHAINS, *LEG_CHAINS), (), (), BUILDER_ID,
            ('horizontal_support',), ('end',), 'preserve_end',
        ), catalog)
