"""Bounded operations on authored fragments for the single-fragment bridge."""

from dataclasses import replace
from hashlib import sha256
import math

from . import contracts as c
from .compiler import build_fragment, instantiate_movement, prepare_fragment, supporting_chains, value_error
from .joints import catalog_for_profile
from .registry import register_movement, validate_control_value, validate_snapshot
from .spatial import inverse, multiply, rotate


STEP_PATTERN_BUILDER = 'patterns.steps.v1'


def register_step_pattern(catalog):
    step = catalog.definitions.get('body.step')
    if step is None:
        return
    parameters = tuple(replace(spec, name='lead') if spec.name == 'side' else spec
                       for spec in step.parameter_specs)
    count = c.ParameterSpec('count', 'integer', 'unitless', None, False, True, 2, 1, 4)
    register_movement(replace(
        step, id='pattern.steps', kind='pattern',
        description='Alternate one to four planted steps from captured floor soles',
        parameter_specs=(*parameters, count), builder_id=STEP_PATTERN_BUILDER,
        phase_events=(),
    ), catalog)


def build_step_pattern(instance, entry, profile, surfaces):
    parameters = {value.name: value.value for value in instance.parameters}
    lead = parameters.pop('lead')
    count = parameters.pop('count')
    fragment = step_pattern(lead, parameters, count,
                            fragment_id=instance.instance_id + '.fragment',
                            entry=entry, profile=profile, surfaces=surfaces)
    # The composed recipe sees one schedulable instance. Its generated child
    # IDs still distinguish step tracks, contact events, goals and landmarks.
    source = (instance.instance_id,)
    return replace(fragment, source_instance_ids=source,
                   tracks=tuple(replace(track, source_instance_ids=source) for track in fragment.tracks),
                   contact_events=tuple(replace(event, source_instance_ids=source)
                                        for event in fragment.contact_events),
                   goals=tuple(replace(goal, clause_id=instance.instance_id) for goal in fragment.goals))


def _duration(seconds):
    c.check_type(seconds, float, 'duration_s')
    if seconds < 1e-9:
        c.fail('INVALID_PARAMETER', 'Duration must be positive')
    if seconds > c.MAX_SECONDS or math.ceil(seconds * c.FPS) + 1 > c.MAX_SAMPLES:
        c.fail('RESOURCE_LIMIT', 'Duration exceeds the shared fragment budget')
    return seconds


def hold_fragment(fragment, duration_s, *, entry, profile):
    """Extend an authored fragment's terminal targets and still-held contacts."""
    prepare_fragment(fragment, entry, profile)
    duration = _duration(fragment.duration_s + _duration(duration_s))
    contacts = tuple(
        replace(event, interval=replace(event.interval, end_s=duration))
        if event.interval.end_s == fragment.duration_s and event.release_s == 0 else event
        for event in fragment.contact_events
    )
    goals = tuple(
        replace(goal, interval=replace(goal.interval, end_s=duration))
        if goal.interval.end_s == fragment.duration_s else goal
        for goal in fragment.goals
    )
    held = replace(fragment, duration_s=duration, contact_events=contacts, goals=goals)
    prepare_fragment(held, entry, profile)
    return held


def transition_fragment(targets, duration_s, *, instance_id, entry, profile):
    """Build a smooth transition to explicit targets in their measured frames."""
    duration = _duration(duration_s)
    c.check_type(instance_id, c.ID, 'instance_id')
    if type(targets) is not tuple or not targets:
        c.fail('INVALID_PARAMETER', 'Transition needs a tuple of explicit control targets')
    if len(targets) > c.MAX_TRACKS:
        c.fail('RESOURCE_LIMIT', 'Transition exceeds the shared track budget')
    validate_snapshot(entry, profile)
    for target in targets:
        validate_control_value(target, profile)
    c.distinct(targets, 'control_id')
    interval = c.TimeInterval(0, duration)
    source = (instance_id,)
    controls = {control.id: control for control in profile.controls}
    measured = {control.control_id: control for control in entry.measured_controls}
    tracks = []
    for index, target in enumerate(targets):
        start = measured.get(target.control_id)
        if start is None or (start.unit, start.frame) != (target.unit, target.frame):
            c.fail('ENTRY_MISMATCH', 'Transition target needs a measured entry in the same unit and frame',
                   control_id=target.control_id)
        control = controls[target.control_id]
        tracks.append(c.TrackSpec(f'transition.track.{index}', source, target.control_id, target.unit,
                                  target.frame, control.value_shape, control.dimensions,
                                  c.CurveSpec('transition', start.value, target.value, duration, 'smooth'),
                                  'explicit', interval))
    contacts = tuple(
        c.ContactEvent(f'transition.anchor.{index}', source, anchor.anchor_id, anchor.surface_id,
                       interval, 0, 0, 0)
        for index, anchor in enumerate(entry.contact_anchors) if anchor.anchor_id in entry.active_contacts
    )
    fragment = c.MotionFragment(instance_id, source, (), duration, tuple(tracks), contacts,
                                (c.PhaseLandmark('entry', 0), c.PhaseLandmark('arrival', duration)), (), ())
    prepare_fragment(fragment, entry, profile)
    return fragment


def overlap_fragments(first, second, *, fragment_id, entry, profile):
    """Run two authored fragments from the same entry with disjoint ownership."""
    return _overlap(first, second, (0, 0), fragment_id=fragment_id, entry=entry, profile=profile)


def synchronize_fragments(first, first_phase, second, second_phase, *, fragment_id, entry, profile):
    """Delay one authored fragment so two named landmarks occur together."""
    def phase_time(fragment, name):
        if type(fragment) is not c.MotionFragment:
            c.fail('INVALID_PARAMETER', 'Synchronization needs two authored fragments')
        c.check_type(name, c.ID, 'phase')
        for phase in fragment.phase_landmarks:
            if phase.name == name:
                return phase.time_s
        c.fail('UNKNOWN_ID', 'Synchronization phase is absent from its fragment', details={'phase': name})

    first_time, second_time = phase_time(first, first_phase), phase_time(second, second_phase)
    common = max(first_time, second_time)
    return _overlap(first, second, (common - first_time, common - second_time),
                    fragment_id=fragment_id, entry=entry, profile=profile)


def phase_offset_fragments(first, second, phase_cycles, *, fragment_id, entry, profile):
    """Offset finite fragments by a signed fraction of the second fragment's cycle."""
    c.check_type(phase_cycles, float, 'phase_cycles')
    if not -1 <= phase_cycles <= 1 or type(second) is not c.MotionFragment:
        c.fail('INVALID_PARAMETER', 'Phase offset needs a fragment and a fraction between -1 and 1')
    delay = phase_cycles * second.duration_s
    return _overlap(first, second, (max(0, -delay), max(0, delay)),
                    fragment_id=fragment_id, entry=entry, profile=profile)


def alternate_fragments(first, second, count, *, fragment_id, entry, profile):
    """Execute compatible fragments in turn for a finite number of pairs."""
    if type(first) is not c.MotionFragment:
        c.fail('INVALID_PARAMETER', 'Alternation needs two authored fragments')
    pair = _overlap(first, second, (0, first.duration_s), fragment_id=fragment_id, entry=entry, profile=profile)
    return repeat_fragment(pair, count, entry=entry, profile=profile)


def _opposite_side(id):
    parts = id.split('.')
    if parts[0] in ('left', 'right'):
        parts[0] = {'left': 'right', 'right': 'left'}[parts[0]]
    return '.'.join(parts)


def mirror_fragment(fragment, *, fragment_id, entry, profile):
    """Mirror calibrated scalar motion and support across the entry sagittal plane."""
    c.check_type(fragment_id, c.ID, 'fragment_id')
    if type(fragment) is not c.MotionFragment:
        c.fail('INVALID_PARAMETER', 'Mirror needs one authored fragment')
    validate_snapshot(entry, profile)
    origin, rotation = entry.root_transform.position, entry.root_transform.orientation
    limits = {limit.control_id: limit for limit in profile.joint_limits}
    captured = {anchor.anchor_id: anchor for anchor in entry.contact_anchors}

    def scalar(id, frame):
        limit = limits.get(id)
        if limit is None or limit.mirror_control_id is None:
            c.fail('MISSING_CAPABILITY', 'Control has no calibrated scalar mirror', control_id=id)
        if frame.startswith('joint:'):
            frame = 'joint:' + _opposite_side(frame.removeprefix('joint:'))
        return limit.mirror_control_id, frame, limit.mirror_sign

    def mirror_target(target):
        id, frame, sign = scalar(target.control_id, target.frame)
        return replace(target, control_id=id, frame=frame, value=target.value * sign)

    def mirror_track(track):
        if track.value_shape != 'scalar':
            c.fail('MISSING_CAPABILITY', 'Track needs a calibrated mirror for its spatial representation',
                   control_id=track.control_id)
        id, frame, sign = scalar(track.control_id, track.frame)
        curve = track.curve
        return replace(track, control_id=id, frame=frame, curve=replace(curve,
            start_value=None if curve.start_value is None else sign * curve.start_value,
            end_value=None if curve.end_value is None else sign * curve.end_value))

    def mirror_contact(event):
        id = _opposite_side(event.anchor_id)
        target = event.target_world_v1
        if target is not None:
            local = rotate(inverse(rotation), tuple(a - b for a, b in zip(target, origin)))
            offset = rotate(rotation, (-local[0], local[1], local[2]))
            target = tuple(a + b for a, b in zip(origin, offset))
            if event.interval.start_s == 0 and event.acquire_s == 0 and id in entry.active_contacts:
                anchor = captured[id]
                if anchor.frame == 'world' and value_error(target, anchor.position) <= 1e-5:
                    target = anchor.position
        return replace(event, anchor_id=id, target_world_v1=target)

    mirrored = replace(fragment, fragment_id=fragment_id,
        tracks=tuple(mirror_track(track) for track in fragment.tracks),
        contact_events=tuple(mirror_contact(event) for event in fragment.contact_events),
        entry_requirements=tuple(replace(item, target=mirror_target(item.target)) for item in fragment.entry_requirements),
        exit_expectations=tuple(replace(item, target=mirror_target(item.target)) for item in fragment.exit_expectations),
        goals=tuple(replace(item, target=mirror_target(item.target)) for item in fragment.goals))
    prepare_fragment(mirrored, entry, profile)
    return mirrored


def _overlap(first, second, offsets, *, fragment_id, entry, profile):
    c.check_type(fragment_id, c.ID, 'fragment_id')
    if type(first) is not c.MotionFragment or type(second) is not c.MotionFragment:
        c.fail('INVALID_PARAMETER', 'Overlap needs two authored fragments')
    c.distinct(first.source_instance_ids + second.source_instance_ids, None)
    duration = _duration(max(previous.duration_s + offset for previous, offset in zip((first, second), offsets)))
    for fragment in (first, second):
        prepare_fragment(fragment, entry, profile)
    chains = {control.id: control.chain for control in profile.controls}

    def owned(fragment):
        ids = {track.control_id for track in fragment.tracks}
        return {chains[id] for id in ids} | set(supporting_chains(ids))

    if owned(first) & owned(second):
        c.fail('CONSTRAINT_CONFLICT', 'Overlap needs disjoint chain ownership')

    def support(fragment, offset):
        # Both operands must agree on the complete schedule, including the shorter operand's hold.
        return {(
            event.anchor_id, event.surface_id,
            0 if event.interval.start_s == 0 and not event.acquire_s else event.interval.start_s + offset,
            duration if event.interval.end_s == fragment.duration_s and not event.release_s
            else event.interval.end_s + offset,
            event.acquire_s, event.release_s, event.clearance_m, event.target_world_v1,
        ): event for event in fragment.contact_events}

    left, right = support(first, offsets[0]), support(second, offsets[1])
    if left.keys() != right.keys():
        c.fail('CONSTRAINT_CONFLICT', 'Overlap operands must agree on the contact schedule')

    def tagged(kind, side, id):
        return f'{kind}.{sha256(f"{fragment_id}/{side}/{id}".encode()).hexdigest()}'

    fields = (
        ('tracks', 'track_id', c.MAX_TRACKS), ('phase_landmarks', 'name', c.MAX_INSTANCES),
        ('entry_requirements', 'requirement_id', 64), ('exit_expectations', 'requirement_id', 64),
        ('goals', 'goal_id', c.MAX_TRACKS), ('source_instance_ids', None, c.MAX_INSTANCES),
    )
    if (any(len(getattr(first, field)) + len(getattr(second, field)) > limit for field, _, limit in fields)
            or sum(len(fragment.tracks) + len(fragment.goals) for fragment in (first, second)) + len(left)
            > c.MAX_TRACKS + c.MAX_CONTACTS):
        c.fail('RESOURCE_LIMIT', 'Overlap exceeds the shared fragment budget')

    def shift_item(field, item, offset):
        if field in ('tracks', 'goals'):
            return replace(item, interval=_shift(item.interval, offset))
        if field == 'phase_landmarks':
            return replace(item, time_s=item.time_s + offset)
        return item

    merged = {}
    for field, key, _ in fields:
        if key is None:
            continue
        merged[field] = tuple(
            replace(shift_item(field, item, offsets[side]), **{key: tagged(field, side, getattr(item, key))})
            for side, fragment in enumerate((first, second)) for item in getattr(fragment, field)
        )
    contacts = tuple(
        replace(event, event_id=tagged('contact', 0, event.event_id),
                source_instance_ids=tuple(dict.fromkeys(event.source_instance_ids + right[key].source_instance_ids)),
                interval=c.TimeInterval(key[2], key[3]))
        for key, event in left.items()
    )
    merged = c.MotionFragment(fragment_id=fragment_id, duration_s=duration, contact_events=contacts,
                              source_instance_ids=first.source_instance_ids + second.source_instance_ids, **merged)
    prepare_fragment(merged, entry, profile)
    return merged


def _cycle_id(fragment_id, id, cycle):
    if cycle == 0:
        return id
    digest = sha256(f'{fragment_id}/{cycle}/{id}'.encode()).hexdigest()
    return f'repeat.{cycle}.{digest}'


def _shift(interval, offset):
    return c.TimeInterval(interval.start_s + offset, interval.end_s + offset)


def _budget(fragment, count):
    duration = fragment.duration_s * count
    sizes = (
        (len(fragment.source_instance_ids), c.MAX_INSTANCES),
        (len(fragment.tracks), c.MAX_TRACKS),
        (len(fragment.contact_events), c.MAX_CONTACTS),
        (len(fragment.phase_landmarks), c.MAX_INSTANCES),
        (len(fragment.goals), c.MAX_TRACKS),
        (len(fragment.tracks) + len(fragment.contact_events) + len(fragment.goals),
         c.MAX_TRACKS + c.MAX_CONTACTS),
    )
    if (duration > c.MAX_SECONDS or math.ceil(duration * c.FPS) + 1 > c.MAX_SAMPLES
            or any(size * count > limit for size, limit in sizes)):
        c.fail('RESOURCE_LIMIT', 'Expanded repeat exceeds the shared fragment budget')
    return duration


def _check_pose_seam(fragment, entry):
    measured = {value.control_id: value.value for value in entry.measured_controls}
    controls = {}
    for track in sorted(fragment.tracks, key=lambda track: track.interval.start_s):
        controls.setdefault(track.control_id, []).append(track)
        if track.curve.look_at_world_v1 is not None:
            c.fail('UNSUPPORTED_GOAL', 'A dynamic world aim has no authored repeat seam')
        if track.start_source == 'measured_entry' and track.interval.start_s != 0:
            c.fail('UNSUPPORTED_GOAL', 'Repeat requires explicit starts after time zero')
    for control_id, tracks in controls.items():
        first, last = tracks[0], tracks[-1]
        endpoint = last.curve.end_value
        if endpoint is None:
            endpoint = last.curve.start_value
        if endpoint is None:
            endpoint = measured[control_id]
        if value_error(endpoint, measured[control_id], last.value_shape) > 1e-5:
            c.fail('ENTRY_MISMATCH', 'Finite repeat requires a returning pose at the seam',
                   control_id=control_id)
        for track, touches_seam in ((first, first.interval.start_s == 0),
                                    (last, last.interval.end_s == fragment.duration_s)):
            curve = track.curve
            start = measured[control_id] if curve.start_value is None else curve.start_value
            if (touches_seam and curve.kind == 'transition' and curve.easing == 'linear'
                    and value_error(start, curve.end_value, track.value_shape) > 1e-5):
                c.fail('ENTRY_MISMATCH', 'Finite repeat requires a resting pose at the seam',
                       control_id=control_id)
    return measured


def _check_contact_seam(fragment, entry):
    starts = {event.anchor_id: event for event in fragment.contact_events
              if event.interval.start_s == 0}
    ends = {event.anchor_id: event for event in fragment.contact_events
            if event.interval.end_s == fragment.duration_s}
    held_at_start = {anchor for anchor, event in starts.items() if event.acquire_s == 0}
    held_at_end = {anchor for anchor, event in ends.items() if event.release_s == 0}
    if held_at_start != held_at_end or held_at_start != set(entry.active_contacts):
        c.fail('ENTRY_MISMATCH', 'Repeat seam changes the held support set')
    captured = {anchor.anchor_id: anchor for anchor in entry.contact_anchors}
    for anchor in sorted(held_at_start):
        first, last = starts[anchor], ends[anchor]
        if ((first.surface_id, first.clearance_m, first.target_world_v1)
                != (last.surface_id, last.clearance_m, last.target_world_v1)
                or first.surface_id != captured[anchor].surface_id
                or first.target_world_v1 is not None
                and (captured[anchor].frame != 'world'
                     or first.target_world_v1 != captured[anchor].position)
                or first is not last and first.target_world_v1 is None):
            c.fail('ENTRY_MISMATCH', 'Repeat seam requires the same verified support anchor',
                   details={'anchor_id': anchor})
    if (starts.keys() & ends.keys()) - held_at_start:
        c.fail('UNSUPPORTED_GOAL', 'Leave a gap between release and reacquisition at a repeat seam')
    return held_at_start


def repeat_fragment(fragment, count, *, entry, profile):
    """Implement timing.repeat for finite, returning fragments with resting seams."""
    if type(fragment) is not c.MotionFragment or type(count) is not int or count < 1:
        c.fail('INVALID_PARAMETER', 'Repeat requires an authored fragment and a positive integer count')
    if count > c.MAX_INSTANCES:
        c.fail('RESOURCE_LIMIT', 'Repeat count exceeds the shared instance budget')
    duration = _budget(fragment, count)
    prepare_fragment(fragment, entry, profile)
    if count == 1:
        return fragment
    measured = _check_pose_seam(fragment, entry)
    held = _check_contact_seam(fragment, entry)

    tracks, contacts, phases, goals = [], [], [], []
    sources = []
    held_ends = {}
    for cycle in range(count):
        offset = fragment.duration_s * cycle
        end = fragment.duration_s * (cycle + 1)

        def cycle_id(id):
            return _cycle_id(fragment.fragment_id, id, cycle)

        instance_ids = {id: cycle_id(id) for id in fragment.source_instance_ids}
        sources.extend(instance_ids.values())

        def provenance(ids):
            # Put the occurrence first for the bridge's runtime entry binding.
            return tuple(dict.fromkeys(tuple(instance_ids[id] for id in ids) + ids))

        def shift(interval):
            shifted = _shift(interval, offset)
            if interval.end_s == fragment.duration_s:
                return replace(shifted, end_s=end)
            return shifted

        for track in fragment.tracks:
            if cycle and track.start_source == 'measured_entry':
                curve = replace(track.curve, start_value=measured[track.control_id])
                track = replace(track, curve=curve, start_source='explicit')
            tracks.append(replace(track, track_id=cycle_id(track.track_id),
                                  interval=shift(track.interval),
                                  source_instance_ids=provenance(track.source_instance_ids)))
        seam_ends = {}
        for event in fragment.contact_events:
            shifted = replace(event, event_id=cycle_id(event.event_id),
                              interval=shift(event.interval),
                              source_instance_ids=provenance(event.source_instance_ids))
            anchor = event.anchor_id
            if event.interval.start_s == 0 and anchor in held_ends:
                index = held_ends[anchor]
                previous = contacts[index]
                contacts[index] = replace(previous, release_s=shifted.release_s,
                    interval=c.TimeInterval(previous.interval.start_s, shifted.interval.end_s),
                    source_instance_ids=tuple(dict.fromkeys(previous.source_instance_ids + shifted.source_instance_ids)))
            else:
                index = len(contacts)
                contacts.append(shifted)
            if event.interval.end_s == fragment.duration_s and anchor in held:
                seam_ends[anchor] = index
        held_ends = seam_ends
        phases.extend(replace(phase, name=cycle_id(phase.name),
                              time_s=end if phase.time_s == fragment.duration_s else phase.time_s + offset)
                      for phase in fragment.phase_landmarks)
        goals.extend(replace(goal, goal_id=cycle_id(goal.goal_id), interval=shift(goal.interval))
                     for goal in fragment.goals)

    repeated = replace(fragment, fragment_id=_cycle_id(fragment.fragment_id, fragment.fragment_id, count),
                       duration_s=duration, source_instance_ids=tuple(sources),
                       tracks=tuple(tracks), contact_events=tuple(contacts),
                       phase_landmarks=tuple(phases), goals=tuple(goals))
    prepare_fragment(repeated, entry, profile)
    return repeated


def _authored_fragment(definition_id, parameters, instance_id, entry, profile, surfaces):
    catalog = catalog_for_profile(profile)
    instance = instantiate_movement(definition_id, parameters, instance_id=instance_id,
                                    entry_state=entry, profile=profile, catalog=catalog)
    return build_fragment(instance, entry, profile, surfaces, catalog)


def step_pattern(lead, parameters, count, *, fragment_id, entry, profile, surfaces):
    """Alternate bounded planted steps, carrying each authored target into the next step."""
    if lead not in ('left', 'right') or type(parameters) is not dict or 'side' in parameters:
        c.fail('INVALID_PARAMETER', 'Step pattern needs a starting side and shared step parameters')
    if type(count) is not int or not 1 <= count <= 4:
        c.fail('INVALID_PARAMETER', 'Step pattern needs one to four steps')
    c.check_type(fragment_id, c.ID, 'fragment_id')
    order = (lead, 'right' if lead == 'left' else 'left')
    templates = {}
    for side in order[:min(count, 2)]:
        instance_id = 'step.' + sha256(f'{fragment_id}/{side}'.encode()).hexdigest()
        templates[side] = _authored_fragment('body.step', {**parameters, 'side': side}, instance_id,
                                             entry, profile, surfaces)
    first = templates[lead]
    cycle_frames = round(first.duration_s * c.FPS)
    duration = _duration(cycle_frames * count / c.FPS)
    if any(round(fragment.duration_s * c.FPS) != cycle_frames for fragment in templates.values()):
        c.fail('CONSTRAINT_CONFLICT', 'Step pattern templates need a common step duration')

    positions = {value.control_id: value.value for value in entry.measured_controls
                 if value.control_id.endswith('.position') and value.frame == 'world'}
    measured = positions.copy()
    anchors = {anchor.anchor_id: anchor.position for anchor in entry.contact_anchors
               if anchor.anchor_id in entry.active_contacts}
    feet = anchors.copy()
    tracks, goals, phases, sources = [], [], [], []
    contacts = {anchor_id: [] for anchor_id in anchors}
    for index in range(count):
        fragment = templates[order[index % 2]]
        original, = fragment.source_instance_ids
        source = _cycle_id(fragment_id, original, index + 1)
        sources.extend((original, source))
        provenance = (source, original)

        def time(seconds):
            return (index * cycle_frames + round(seconds * c.FPS)) / c.FPS

        def interval(span):
            return c.TimeInterval(time(span.start_s), time(span.end_s))

        def translated(point, start, stop):
            return tuple(a + (b - c0) for a, b, c0 in zip(point, stop, start))

        previous = positions.copy()
        swing_side = order[index % 2]

        def translated_track(point, key):
            origin = measured[key]
            position = translated(point, origin, previous[key])
            if index >= 2 and key == swing_side + '.foot.position':
                # Once this side has landed, start from its carried pose.
                # Later knots still use the template's floor-relative height.
                return (*position[:2], previous[key][2] if point == origin else point[2])
            return position

        for track in fragment.tracks:
            curve = track.curve
            key = track.control_id
            if key in previous:
                curve = replace(curve,
                    start_value=translated_track(curve.start_value, key),
                    end_value=translated_track(curve.end_value, key))
                positions[key] = curve.end_value
            tracks.append(replace(track, track_id=_cycle_id(fragment_id, track.track_id, index + 1),
                                  source_instance_ids=provenance, curve=curve, interval=interval(track.interval)))
        for goal in fragment.goals:
            target = goal.target
            key = target.control_id
            if key in previous:
                target = replace(target, value=translated_track(target.value, key))
            goals.append(replace(goal, goal_id=_cycle_id(fragment_id, goal.goal_id, index + 1),
                                 target=target, interval=interval(goal.interval)))
        phases.extend(replace(phase, name=f'step.{index + 1}.{phase.name}', time_s=time(phase.time_s))
                      for phase in fragment.phase_landmarks)

        for event in sorted(fragment.contact_events, key=lambda item: item.interval.start_s):
            key = event.anchor_id
            target = translated(event.target_world_v1, anchors[key], feet[key])
            if index >= 2 and event.interval.start_s > 0:
                target = (*target[:2], event.target_world_v1[2])
            shifted = replace(event, event_id=_cycle_id(fragment_id, event.event_id, index + 1),
                              source_instance_ids=provenance, interval=interval(event.interval),
                              target_world_v1=target)
            history = contacts[key]
            if event.interval.start_s == 0 and history:
                prior = history[-1]
                history[-1] = replace(prior, interval=c.TimeInterval(prior.interval.start_s, shifted.interval.end_s),
                                      release_s=event.release_s, source_instance_ids=tuple(dict.fromkeys(
                                          prior.source_instance_ids + provenance)))
            else:
                history.append(shifted)
            feet[key] = target

    fragment = c.MotionFragment(fragment_id, tuple(dict.fromkeys(sources)), first.entry_requirements,
                                duration, tuple(tracks), tuple(event for group in contacts.values() for event in group),
                                tuple(phases), (), tuple(goals))
    prepare_fragment(fragment, entry, profile)
    return fragment


def has_alternating_step_support(motion, controls):
    """Recognize the fixed-support envelope for the authored alternating step pattern."""
    soles = {'left.sole', 'right.sole'}
    tracks = {'pelvis.position', 'left.foot.position', 'left.foot.orientation',
              'right.foot.position', 'right.foot.orientation'}
    if set(motion.entry_snapshot.active_contacts) != soles or controls != tracks:
        return False
    events = motion.contact_events
    if any(event.anchor_id not in soles or event.surface_id != 'floor' or event.clearance_m
           or event.target_world_v1 is None for event in events):
        return False
    swings = []
    for anchor in soles:
        group = sorted((event for event in events if event.anchor_id == anchor), key=lambda event: event.interval.start_s)
        if (len(group) < 2 or group[0].interval.start_s != 0 or group[0].acquire_s
                or group[-1].interval.end_s != motion.duration_s or group[-1].release_s):
            return False
        for prior, following in zip(group, group[1:]):
            if not prior.release_s or not following.acquire_s or prior.interval.end_s >= following.interval.start_s:
                return False
            swings.append((prior.interval.end_s - prior.release_s,
                           following.interval.start_s + following.acquire_s, anchor))
    swings.sort()
    return 2 <= len(swings) <= 4 and all(
        earlier[1] <= later[0] + 1e-9 and earlier[2] != later[2]
        for earlier, later in zip(swings, swings[1:])
    )


def verify_translation_loop(motion, loop, profile, start, following, preceding, end, *, cycle_duration_s=None):
    """Check a baked cycle's measured seam before attaching translating loop metadata."""
    c.check_type(motion, c.ExecutableMotion, 'motion')
    c.check_type(loop, c.LoopSpec, 'loop')
    if value_error(loop.per_cycle_root_transform.orientation, (1, 0, 0, 0), 'quaternion') > 1e-6:
        c.fail('UNSUPPORTED_GOAL', 'This loop verifier supports translation only')
    for state in (start, following, preceding, end):
        validate_snapshot(state, profile)
        if (state.avatar_id, state.profile_version, state.revision) != (
            start.avatar_id, start.profile_version, start.revision
        ):
            c.fail('STALE_REVISION', 'Loop samples must come from one measured bake')
    duration = motion.duration_s if cycle_duration_s is None else cycle_duration_s
    if not (start.captured_time_s == 0 < following.captured_time_s <= preceding.captured_time_s
            < end.captured_time_s) or abs(end.captured_time_s - duration) > 1e-9:
        c.fail('INVALID_PARAMETER', 'Loop validation needs ordered seam and adjacent samples')
    if (following.captured_time_s > 1 / motion.fps + 1e-9
            or end.captured_time_s - preceding.captured_time_s > 1 / motion.fps + 1e-9):
        c.fail('INVALID_PARAMETER', 'Loop validation needs the frames adjacent to the seam')
    root_moves = any(track.control_id == 'object_root.position' for track in motion.tracks)
    delta = rotate(start.root_transform.orientation, loop.per_cycle_root_transform.position)

    def difference(a, b):
        return tuple(x - y for x, y in zip(a, b))

    def angular_velocity(a, b, elapsed, shape):
        if shape == 'scalar':
            return ((b - a) / elapsed,)
        rotation = multiply(b, inverse(a))
        if rotation[0] < 0:
            rotation = tuple(-x for x in rotation)
        axis = rotation[1:]
        length = math.sqrt(sum(x*x for x in axis))
        if length < 1e-12:
            return (0., 0., 0.)
        angle = math.degrees(2 * math.atan2(length, rotation[0]))
        return tuple(x * angle / (length * elapsed) for x in axis)

    states = [{value.control_id: value for value in snapshot.measured_controls}
              for snapshot in (start, following, preceding, end)]
    expected = motion.entry_snapshot
    if (start.avatar_id, start.profile_version, start.revision) != (
        expected.avatar_id, expected.profile_version, expected.revision
    ):
        c.fail('ENTRY_MISMATCH', 'Loop samples belong to a different motion entry')
    required = {control.id for control in profile.controls}
    if any(state.keys() != required for state in states):
        c.fail('ENTRY_MISMATCH', 'Loop samples need the full calibrated control set')
    pose = value_error(start.root_transform.orientation, end.root_transform.orientation, 'quaternion')
    endpoint = math.dist(start.root_transform.position, difference(end.root_transform.position, delta))
    velocity = linear_velocity = 0.
    for control in profile.controls:
        a, b, c0, d = (state[control.id] for state in states)
        if len({(value.unit, value.frame) for value in (a, b, c0, d)}) != 1:
            c.fail('ENTRY_MISMATCH', 'Measured loop control changed frame', control_id=control.id)
        dt = following.captured_time_s
        last_dt = end.captured_time_s - preceding.captured_time_s
        if control.unit == 'degree' or control.value_shape == 'quaternion':
            pose = max(pose, value_error(a.value, d.value, control.value_shape))
            velocity = max(velocity, math.dist(angular_velocity(a.value, b.value, dt, control.value_shape),
                                               angular_velocity(c0.value, d.value, last_dt, control.value_shape)))
        elif control.unit == 'metre' and control.value_shape == 'vector':
            compensate = a.frame == 'world' and (root_moves or control.id != 'object_root.position')
            target = difference(d.value, delta) if compensate else d.value
            endpoint = max(endpoint, math.dist(a.value, target))
            linear_velocity = max(linear_velocity,
                math.dist(tuple(v / dt for v in difference(b.value, a.value)),
                          tuple(v / last_dt for v in difference(d.value, c0.value))))
    if (set(start.active_contacts) != set(end.active_contacts)
            or (start.phase is None) != (end.phase is None)
            or start.phase is not None and abs((end.phase - start.phase + .5) % 1 - .5) > 1e-6):
        c.fail('ENTRY_MISMATCH', 'Measured loop seam changes the active contact set')
    start_anchors = {anchor.anchor_id: anchor for anchor in start.contact_anchors}
    end_anchors = {anchor.anchor_id: anchor for anchor in end.contact_anchors}
    for id in start.active_contacts:
        a, b = start_anchors[id], end_anchors[id]
        if a.surface_id != b.surface_id or a.frame != 'world' or b.frame != 'world':
            c.fail('ENTRY_MISMATCH', 'Loop seam changes a measured world support surface', details={'anchor_id': id})
        endpoint = max(endpoint, math.dist(a.position, difference(b.position, delta)))
    metrics = {'pose_deg': pose, 'endpoint_m': endpoint, 'angular_velocity_deg_s': velocity,
               'linear_velocity_m_s': linear_velocity}
    if (pose > loop.pose_tolerance_deg or endpoint > loop.endpoint_tolerance_m
            or velocity > loop.angular_velocity_tolerance_deg_s):
        c.fail('ENTRY_MISMATCH', 'Measured cycle does not close at the declared displacement', details=metrics)
    return replace(motion, loop=loop), metrics


def torso_pattern(mode, parameters, count, *, fragment_id, entry, profile, surfaces,
                  follow_through=None):
    """Repeat a supported sway or a phased spine wave from the measured stance."""
    definitions = {'sway': 'torso.sway', 'undulation': 'torso.wave'}
    if (type(mode) is not str or mode not in definitions or type(parameters) is not dict
            or set(parameters) - {'duration_s', 'hold_s', 'angle'}):
        c.fail('INVALID_PARAMETER', 'Torso pattern needs a supported mode and torso parameters')
    if follow_through is not None and (mode != 'undulation' or follow_through not in ('left', 'right', 'both')):
        c.fail('INVALID_PARAMETER', 'Limb follow-through needs an undulation and a calibrated side')
    c.check_type(fragment_id, c.ID, 'fragment_id')
    validate_snapshot(entry, profile)
    anchors = {anchor.anchor_id: anchor for anchor in entry.contact_anchors}
    if (set(entry.active_contacts) != {'left.sole', 'right.sole'}
            or any(anchors[id].surface_id != 'floor' for id in entry.active_contacts)):
        c.fail('ENTRY_MISMATCH', 'Torso pattern needs both captured floor soles')
    torso_id = 'torso.' + sha256(fragment_id.encode()).hexdigest()
    torso = _authored_fragment(definitions[mode], {**parameters, 'return_policy': 'return_to_entry'},
                               torso_id, entry, profile, surfaces)
    if follow_through is not None:
        arm_id = 'follow.' + sha256(fragment_id.encode()).hexdigest()
        arm = _authored_fragment('arm.swing', {'side': follow_through, 'angle': 5.,
            'duration_s': max(1., parameters.get('duration_s', 1.)), 'hold_s': 0.},
            arm_id, entry, profile, surfaces)
        delay = round(torso.duration_s * c.FPS / 4) / c.FPS
        torso = _overlap(torso, arm, (0, delay), fragment_id=fragment_id, entry=entry, profile=profile)
        # The torso moves during the delay. Keep each selected arm in its
        # authored world orientation until its swing starts, so activation
        # does not reset an arm that inherited the moving torso's rotation.
        prelude = tuple(
            replace(track, track_id=track.track_id + '.hold', interval=c.TimeInterval(0, delay),
                    curve=c.CurveSpec('hold', track.curve.start_value, track.curve.start_value, delay))
            for track in torso.tracks if track.interval.start_s == delay and arm_id in track.source_instance_ids
        )
        torso = replace(torso, tracks=prelude + torso.tracks)
    else:
        torso = replace(torso, fragment_id=fragment_id)
    return repeat_fragment(torso, count, entry=entry, profile=profile)


def stroke_pattern(mode, parameters, count, *, fragment_id, entry, profile, surfaces):
    """Repeat two calibrated arm strokes in phase or with a half-cycle offset."""
    if (mode not in ('synchronized', 'alternating') or type(parameters) is not dict
            or set(parameters) - {'duration_s', 'hold_s', 'amplitude_m'}):
        c.fail('INVALID_PARAMETER', 'Stroke pattern needs a supported mode and shared stroke parameters')
    c.check_type(fragment_id, c.ID, 'fragment_id')
    arms = []
    for side in ('left', 'right'):
        stable_id = 'stroke.' + sha256(f'{fragment_id}/{side}'.encode()).hexdigest()
        arm = _authored_fragment('arm.stroke', {**parameters, 'side': side, 'return_policy': 'return_to_entry'},
                                 stable_id, entry, profile, surfaces)
        # Hand IK near full extension needs a zero-acceleration entry and exit.
        tracks = tuple(replace(track, curve=replace(track.curve, easing='smootherstep'))
                       if track.curve.kind == 'transition' else track for track in arm.tracks)
        arms.append(replace(arm, tracks=tracks))
    kwargs = dict(fragment_id=fragment_id, entry=entry, profile=profile)
    if mode == 'synchronized':
        pair = synchronize_fragments(arms[0], 'sweep', arms[1], 'sweep', **kwargs)
    else:
        # Frame-align the half cycle so each shifted point goal is measurable.
        right = arms[1]
        delay = round(right.duration_s * c.FPS / 2) / c.FPS
        start = right.tracks[0]
        value = start.curve.start_value
        # Keep the endpoint solver engaged through the delayed stroke's entry hold.
        prelude = replace(start, track_id=start.track_id + '.hold', interval=c.TimeInterval(0, delay),
                          curve=c.CurveSpec('hold', value, value, delay))
        duration = _duration(right.duration_s + delay)
        right = replace(right, duration_s=duration,
                        tracks=(prelude, *(replace(track, interval=_shift(track.interval, delay)) for track in right.tracks)),
                        contact_events=tuple(replace(event, interval=c.TimeInterval(0, duration))
                                             for event in right.contact_events),
                        phase_landmarks=tuple(replace(phase, time_s=phase.time_s + delay)
                                              for phase in right.phase_landmarks),
                        goals=tuple(replace(goal, interval=_shift(goal.interval, delay)) for goal in right.goals))
        pair = overlap_fragments(arms[0], right, **kwargs)
    return repeat_fragment(pair, count, entry=entry, profile=profile)
