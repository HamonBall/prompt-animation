"""Deterministic plain-data recipe scheduling; no scene or model access.

Fragment descriptors supply timing, never a prediction of a solved future pose.
This module's lower-level scheduling functions also support independent contract
validation before the entry/contact/ownership resolution gate.
"""
from dataclasses import replace

from . import contracts as c
from .registry import validate_recipe, validate_snapshot
from .compiler import build_fragment, supporting_chains, value_error


def resolve_entry_state(recipe, entry_state, profile):
    """Check the measured base and retain operation semantics without resetting it.

    New and edit schedules use local time zero. Append schedules start at the
    caller-supplied measured end time. The caller must provide the measured end,
    not an authored target; revision equality prevents stale edits/appends.
    """
    validate_snapshot(entry_state, profile)
    if (recipe.avatar_id, recipe.profile_version) != (profile.avatar_id, profile.version):
        c.fail('ENTRY_MISMATCH', 'Recipe and measured entry belong to different profiles')
    if recipe.base_revision != entry_state.revision:
        c.fail('STALE_REVISION', 'Recipe must use the measured entry revision',
               details={'expected': entry_state.revision, 'actual': recipe.base_revision})
    return entry_state


def schedule_instances(recipe, fragments, *, origin_s=0):
    """Resolve after/parallel/event offsets with lexical tie-breaking.

    ``fragments`` is a mapping from instance ID to validated MotionFragment.
    It must cover precisely the recipe, retaining each instance's provenance.
    Negative offsets express overlap but may not schedule before the origin.
    """
    if type(recipe) is not c.MotionRecipe or type(fragments) is not dict:
        c.fail('INVALID_PARAMETER', 'Expected a typed recipe and fragment mapping')
    c.check_type(origin_s, c.Seconds, 'origin_s')
    ids = {instance.instance_id for instance in recipe.instances}
    if set(fragments) != ids:
        c.fail('UNKNOWN_ID', 'Timing descriptors must cover exactly the recipe instances',
               details={'missing': sorted(ids - set(fragments)),
                        'extra': sorted(set(fragments) - ids)})
    for id, fragment in fragments.items():
        if type(fragment) is not c.MotionFragment or fragment.source_instance_ids != (id,):
            c.fail('INVALID_PARAMETER', 'Timing descriptor has incorrect instance provenance', instance_id=id)
    incoming = {relation.target_instance_id: relation for relation in recipe.relations}
    intervals = {}

    def resolve(id):
        if id in intervals:
            return intervals[id]
        relation = incoming.get(id)
        start = origin_s
        if relation is not None:
            source = resolve(relation.source_instance_id)
            if relation.kind == 'after':
                start = source.end_s
            elif relation.kind == 'parallel':
                start = source.start_s
            else:
                landmarks = {phase.name: phase.time_s
                             for phase in fragments[relation.source_instance_id].phase_landmarks}
                if relation.source_event not in landmarks:
                    c.fail('UNKNOWN_ID', 'Source fragment did not supply the declared event',
                           instance_id=relation.source_instance_id,
                           details={'event': relation.source_event, 'relation': relation.relation_id})
                start = source.start_s + landmarks[relation.source_event]
            start += relation.offset_s
        end = start + fragments[id].duration_s
        if start < origin_s:
            c.fail('CONSTRAINT_CONFLICT', 'Dependency schedules an instance before the operation origin',
                   instance_id=id, details={'start_s': start, 'origin_s': origin_s})
        if end > c.MAX_SECONDS:
            c.fail('RESOURCE_LIMIT', 'Resolved schedule exceeds the timeline budget', instance_id=id)
        intervals[id] = c.TimeInterval(start, end)
        return intervals[id]

    for id in sorted(ids):
        resolve(id)
    duration = max(interval.end_s for interval in intervals.values()) - origin_s
    repetitions = recipe.loop.repetitions if recipe.loop is not None else 1
    if origin_s + duration * repetitions > c.MAX_SECONDS:
        c.fail('RESOURCE_LIMIT', 'Repeated schedule exceeds the timeline budget')
    if sum(len(fragment.tracks) for fragment in fragments.values()) * repetitions > c.MAX_TRACKS:
        c.fail('RESOURCE_LIMIT', 'Recipe track expansion exceeds its budget')
    if sum(len(fragment.contact_events) for fragment in fragments.values()) * repetitions > c.MAX_CONTACTS:
        c.fail('RESOURCE_LIMIT', 'Recipe contact expansion exceeds its budget')
    return tuple(c.ScheduledInstance(id, interval) for id, interval in
                 sorted(intervals.items(), key=lambda item: (item[1].start_s, item[0])))


def build_transitions(recipe, schedule):
    """Bind future activation to the measured boundary, never to a target pose.

    A predecessor is a provenance dependency, not permission to sample its target
    as the entry. For overlap/event activation Stage 07 must capture the shared
    solved frame at activation, while ``after`` uses the solved end plus any gap.
    No movement is synthesized to bridge an unsupported entry.
    """
    intervals = {item.instance_id: item.interval for item in schedule}
    relations = {relation.target_instance_id: relation for relation in recipe.relations}
    bindings = []
    for instance in sorted(recipe.instances, key=lambda item: item.instance_id):
        for parameter in instance.parameters:
            bindings.append(c.ParameterBinding(instance.instance_id, parameter.name, 'explicit', parameter.value))
        relation = relations.get(instance.instance_id)
        if relation is not None:
            source = intervals[relation.source_instance_id]
            target = intervals[instance.instance_id]
            # The existing measured_exit contract cannot describe a mid-motion
            # shared-frame binding. Do not mislabel overlap as a solved exit.
            if target.start_s >= source.end_s:
                bindings.append(c.ParameterBinding(instance.instance_id, 'entry_state',
                                                   'measured_exit', None, relation.source_instance_id))
    return (), tuple(bindings)


def validate_composition_inputs(recipe, entry_state, profile, catalog):
    """Shared validation boundary for logical composition, without builder calls."""
    recipe = validate_recipe(recipe, profile, catalog)
    resolve_entry_state(recipe, entry_state, profile)
    return recipe


def _shift(interval, offset):
    return c.TimeInterval(interval.start_s + offset, interval.end_s + offset)


def _conflict(message, ids, chain):
    c.fail('CONSTRAINT_CONFLICT', message, details={'instance_ids': sorted(ids), 'chain': chain})


def _track_chains(track, profile):
    control = next(control for control in profile.controls if control.id == track.control_id)
    return {control.chain, *supporting_chains((track.control_id,))}


def _anchor_chains(anchor):
    side, _, part = anchor.partition('.')
    if side in ('left', 'right'):
        if part in ('sole', 'heel', 'toe', 'knee', 'knee.support'):
            return {side + '.' + name for name in ('thigh', 'shin', 'ankle')}
        if part == 'palm':
            return {side + '.' + name for name in ('upper_arm', 'forearm', 'wrist')}
    return {'pelvis'}


def merge_contacts(recipe, schedule, fragments, profile, entry_state):
    """Merge identical fixed contacts; preserve ramps and reject ambiguity.

    A support-neutral successor inherits terminal unreleased contacts. A
    successor with its own authored contact schedule owns acquisition/release.
    The compiler rebinds inherited anchors to the measured activation state.
    """
    events = []
    authored = []
    for item in schedule:
        fragment = fragments[item.instance_id]
        if any(event.target_world_v1 is not None or event.acquire_s or event.release_s
               or any(_anchor_chains(event.anchor_id) & _track_chains(track, profile)
                      for track in fragment.tracks)
               for event in fragment.contact_events):
            authored.append(item)

    authored_ids = {item.instance_id for item in authored}
    entry_anchors = {(anchor.anchor_id, anchor.surface_id): anchor.position
                     for anchor in entry_state.contact_anchors if anchor.frame == 'world'}
    by_id = {item.instance_id: item for item in schedule}
    incoming = {relation.target_instance_id: relation for relation in recipe.relations}
    for item in schedule:
        id = item.instance_id
        own = [replace(event, interval=_shift(event.interval, item.interval.start_s))
               for event in fragments[id].contact_events]
        if id in authored_ids or not authored:
            events.extend(own)
            continue

        # Retain entry contacts before a support route starts, defer to active
        # routes, and inherit their terminal holds through subsequent gaps.
        start, end = item.interval.start_s, item.interval.end_s
        relation = incoming.get(id)
        if relation is not None and relation.kind == 'after' and relation.offset_s > 0:
            start = by_id[relation.source_instance_id].interval.end_s
        boundaries = sorted({start, end, *(time for route in authored
                            for time in (route.interval.start_s, route.interval.end_s)
                            if start < time < end)})
        for segment, (left, right) in enumerate(zip(boundaries, boundaries[1:])):
            if any(route.interval.start_s <= left < route.interval.end_s for route in authored):
                continue
            completed = [route for route in authored if route.interval.end_s <= left]
            if completed:
                latest = max(route.interval.end_s for route in completed)
                inherited = [event for route in completed if route.interval.end_s == latest
                             for event in fragments[route.instance_id].contact_events
                             if event.interval.end_s == fragments[route.instance_id].duration_s
                             and event.release_s == 0]
            else:
                inherited = [replace(event, target_world_v1=entry_anchors.get((event.anchor_id, event.surface_id)))
                             for event in own]
            for index, event in enumerate(inherited):
                events.append(replace(event, event_id=f'contact.{len(events)}.{segment}.{index}',
                                      source_instance_ids=(id,), interval=c.TimeInterval(left, right),
                                      acquire_s=0, release_s=0))
    merged = []
    for event in sorted(events, key=lambda event: (event.anchor_id, event.interval.start_s, event.event_id)):
        previous = next((old for old in reversed(merged)
                         if old.anchor_id == event.anchor_id and old.interval.end_s >= event.interval.start_s), None)
        if previous is None:
            merged.append(event)
            continue
        identity = (previous.surface_id, previous.target_world_v1, previous.clearance_m)
        same = identity == (event.surface_id, event.target_world_v1, event.clearance_m)
        exact = previous.interval == event.interval and (previous.acquire_s, previous.release_s) == (event.acquire_s, event.release_s)
        steady = (previous.release_s == event.acquire_s == 0
                  and event.interval.start_s >= previous.interval.start_s + previous.acquire_s
                  and (event.release_s == 0 or previous.interval.end_s <= event.interval.end_s - event.release_s
                       or previous.interval.end_s == event.interval.start_s))
        if same and (exact or steady):
            merged.remove(previous)
            end = max(previous.interval.end_s, event.interval.end_s)
            merged.append(replace(previous,
                                  source_instance_ids=tuple(sorted(set(previous.source_instance_ids + event.source_instance_ids))),
                                  interval=c.TimeInterval(previous.interval.start_s, end),
                                  release_s=event.release_s if event.interval.end_s >= previous.interval.end_s else previous.release_s))
        elif c.contact_overlap(previous, event):
            _conflict('Incompatible contact targets or ramps', previous.source_instance_ids + event.source_instance_ids, event.anchor_id)
        else:
            merged.append(event)
    return tuple(sorted(merged, key=lambda event: (event.interval.start_s, event.anchor_id, event.event_id)))


def resolve_ownership(recipe, schedule, fragments, contacts, profile):
    """Arbitrate physical chains, including endpoint IK and support chains.

    Only unclaimed arm.swing instances are optional gait decoration. Explicit
    clauses, all other movements and hard goals remain hard. A contact can
    suppress optional swing but never silently replace an explicit goal.
    """
    instances = {instance.instance_id: instance for instance in recipe.instances}
    intervals = {item.instance_id: item.interval for item in schedule}
    claims = []
    explanations = []
    optional = {id for id, instance in instances.items()
                if instance.definition_id == 'arm.swing' and not instance.clause_ids}
    for id, fragment in fragments.items():
        for track in fragment.tracks:
            for chain in _track_chains(track, profile):
                claims.append((chain, _shift(track.interval, intervals[id].start_s), id, id in optional, False))
    for event in contacts:
        for chain in _anchor_chains(event.anchor_id):
            for id in event.source_instance_ids:
                start = max(event.interval.start_s, intervals[id].start_s)
                end = min(event.interval.end_s, intervals[id].end_s)
                if end > start:
                    claims.append((chain, c.TimeInterval(start, end), id, False, True))
    controls = {control.id: control for control in profile.controls}
    for index, goal in enumerate(recipe.hard_goals):
        owners = next(clause.source_instance_ids for clause in recipe.clause_coverage if clause.clause_id == goal.clause_id)
        if not owners:
            c.fail('UNSUPPORTED_GOAL', 'A hard goal must map to a selected instance', control_id=goal.target.control_id)
        for other in recipe.hard_goals[index + 1:]:
            shared = max(goal.interval.start_s, other.interval.start_s) <= min(goal.interval.end_s, other.interval.end_s)
            if shared and goal.target.control_id == other.target.control_id:
                if goal.target.frame != other.target.frame or value_error(goal.target.value, other.target.value, controls[goal.target.control_id].value_shape) > goal.tolerance + other.tolerance:
                    _conflict('Mutually incompatible hard goals', owners + next(clause.source_instance_ids for clause in recipe.clause_coverage if clause.clause_id == other.clause_id), controls[goal.target.control_id].chain)
        for owner in owners:
            optional.discard(owner)
            if goal.interval.start_s < intervals[owner].start_s or goal.interval.end_s > intervals[owner].end_s:
                c.fail('UNSUPPORTED_GOAL', 'Hard goal lies outside its owning instance', instance_id=owner)
            if not any(track.control_id == goal.target.control_id for track in fragments[owner].tracks):
                c.fail('UNSUPPORTED_GOAL', 'Selected instance has no track for the explicit goal',
                       instance_id=owner, control_id=goal.target.control_id)
            for chain in {controls[goal.target.control_id].chain, *supporting_chains((goal.target.control_id,))}:
                if goal.interval.end_s > goal.interval.start_s:
                    claims.append((chain, goal.interval, owner, False, False))
    # Optional status is finalized after explicit hard-goal owners are known.
    claims = [(chain, interval, id, id in optional and not contact, contact)
              for chain, interval, id, _, contact in claims]
    ownership = []
    for chain in sorted({claim[0] for claim in claims}):
        selected = [claim for claim in claims if claim[0] == chain]
        boundaries = sorted({time for _, interval, *_ in selected for time in (interval.start_s, interval.end_s)})
        for start, end in zip(boundaries, boundaries[1:]):
            active = [claim for claim in selected if claim[1].start_s < end and claim[1].end_s > start]
            if not active:
                continue
            hard = {claim[2] for claim in active if not claim[3]}
            moving = {claim[2] for claim in active if not claim[3] and not claim[4]}
            supports = {claim[2] for claim in active if claim[4]}
            # Multiple compatible contacts can share a chain, but a different
            # movement cannot drive that constrained chain without a solver.
            if len(moving) > 1 or moving and supports and not moving <= supports:
                _conflict('Overlapping hard physical-chain owners', hard, chain)
            winners = hard or {min(claim[2] for claim in active)}
            suppressed = {claim[2] for claim in active} - winners
            if suppressed:
                explanations.append(f'{chain} [{start:g}, {end:g}]: optional {", ".join(sorted(suppressed))} yields to {", ".join(sorted(winners))}.')
            decision = c.ChainOwnership(chain, tuple(sorted(winners)), c.TimeInterval(start, end))
            if ownership and ownership[-1].chain_id == chain and ownership[-1].source_instance_ids == decision.source_instance_ids and ownership[-1].interval.end_s == start:
                ownership[-1] = replace(ownership[-1], interval=c.TimeInterval(ownership[-1].interval.start_s, end))
            else:
                ownership.append(decision)
    return tuple(ownership), tuple(dict.fromkeys(explanations))


def compose_recipe(recipe, entry_state, profile, surfaces, catalog):
    """Resolve a bounded logical recipe; execution remains Stage 07.

    Trusted builders provide planning descriptors against the actual supplied
    snapshot. Future descriptors must be rebuilt against measured activation;
    their timing/ownership/contact topology must match or execution must reject
    the candidate transaction. No target pose is used as a measured entry.
    """
    recipe = validate_composition_inputs(recipe, entry_state, profile, catalog)
    fragments = {instance.instance_id: build_fragment(instance, entry_state, profile, surfaces, catalog)
                 for instance in recipe.instances}
    origin = entry_state.captured_time_s if recipe.operation == 'append' else 0
    schedule = schedule_instances(recipe, fragments, origin_s=origin)
    contacts = merge_contacts(recipe, schedule, fragments, profile, entry_state)
    ownership, explanations = resolve_ownership(recipe, schedule, fragments, contacts, profile)
    transitions, parameters = build_transitions(recipe, schedule)
    runtime = tuple(c.RecipeEntryBindingV1(item.instance_id, item.interval.start_s,
                                          'snapshot' if item.interval.start_s == origin else 'measured_activation',
                                          tuple(sorted(other.instance_id for other in schedule
                                                       if other.instance_id != item.instance_id and other.interval.start_s < item.interval.start_s)))
                    for item in schedule)
    explanations += (f'Operation {recipe.operation}; timeline origin {origin:g} seconds; preserve the supplied measured state.',
                     'Future entries use one shared solved activation snapshot; rebuild and revalidate descriptors before execution.',)
    if recipe.optional_styles:
        explanations += ('Optional styles remain scoped requests; compiler must preserve resolved hard ownership and contact schedules.',)
    sources = tuple(c.SourceMapEntry(instance.instance_id, (instance.instance_id,), instance.clause_ids)
                    for instance in sorted(recipe.instances, key=lambda item: item.instance_id))
    return c.ResolvedRecipe(recipe, schedule, ownership, transitions, contacts, parameters, sources,
                            c.RecipeResolutionV1(runtime, explanations))
