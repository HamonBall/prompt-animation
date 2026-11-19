"""Pure fragment and recipe preparation for the shared motion sampler."""
from dataclasses import dataclass, field, replace
import math
from . import contracts as c
from .curves import ease_weight
from .registry import (get_movement, validate_instance, validate_fragment,
                       validate_snapshot, validate_control_value)
from ..motion import Surface
from .spatial import look_rotation


def supporting_chains(control_ids):
    """Endpoint IK's narrowly declared supporting chains, in semantic IDs."""
    control_ids=tuple(control_ids)
    legs={id.split('.')[0]+'.'+part for id in control_ids if id.endswith('.foot.position')
          for part in ('thigh','shin')}
    return tuple(sorted({side+'.'+part for id in control_ids if id.split('.')[0] in ('left','right') and '.hand.' in id and id.rsplit('.',1)[1] in ('position','orientation','torso_position','torso_orientation')
                         for side in (id.split('.')[0],) for part in (('upper_arm','forearm') if id.endswith('position') else ('forearm',))}|legs))


def check_goal_coverage(goals,duration_s,fps):
    for goal in goals:
        first=math.ceil(goal.interval.start_s*fps-1e-8)
        last=math.floor(goal.interval.end_s*fps+1e-8)
        if not (first<=last and first<math.ceil(duration_s*fps) or goal.interval.start_s<=duration_s<=goal.interval.end_s):
            c.fail('UNSUPPORTED_GOAL','Goal interval contains no execution sample; use a frame-aligned time or wider interval',
                   control_id=goal.target.control_id,details={'goal_id':goal.goal_id,'fps':fps})


def value_error(actual, target, shape='scalar'):
    if shape == 'quaternion':
        norm=math.sqrt(sum(a*a for a in actual)*sum(b*b for b in target))
        if norm==0: c.fail('INVALID_PARAMETER','Cannot compare zero quaternions')
        dot = abs(sum(a*b for a,b in zip(actual,target)))/norm
        return math.degrees(2*math.acos(min(1,max(0,dot))))
    if type(actual) is tuple and type(target) is tuple:
        return math.sqrt(sum((a-b)**2 for a,b in zip(actual,target)))
    return abs(actual-target)


def _measured(snapshot, target):
    value=next((v for v in snapshot.measured_controls if v.control_id==target.control_id),None)
    if value is None or (value.unit,value.frame)!=(target.unit,target.frame):
        c.fail('ENTRY_MISMATCH','A control needs a measured value in its declared frame',control_id=target.control_id)
    return value.value


def check_requirements(requirements, snapshot, profile):
    for requirement in requirements:
        control=next(v for v in profile.controls if v.id==requirement.target.control_id)
        actual=_measured(snapshot,requirement.target)
        error=value_error(actual,requirement.target.value,control.value_shape)
        if error>requirement.tolerance:
            c.fail('ENTRY_MISMATCH','Measured entry does not meet the declared requirement',
                   control_id=control.id,details={'requirement_id':requirement.requirement_id,
                       'measured':actual,'required':requirement.target.value,'tolerance':requirement.tolerance})


def _support_requirements(definition, entry, instance_id):
    anchors={a.anchor_id:a for a in entry.contact_anchors}
    for requirement in definition.contact_requirements:
        available=requirement.anchor_id in anchors and anchors[requirement.anchor_id].surface_id==requirement.surface_id
        active=requirement.anchor_id in entry.active_contacts
        if not available or requirement.mode=='active' and not active or requirement.mode=='inactive' and active:
            c.fail('ENTRY_MISMATCH','Entry support requirement is not met',instance_id=instance_id,
                   details={'anchor_id':requirement.anchor_id,'mode':requirement.mode})


def instantiate_movement(id, parameters, *, instance_id, profile, entry_state, catalog):
    validate_snapshot(entry_state,profile)
    definition=catalog.definitions.get(id)
    if definition is None: c.fail('UNKNOWN_ID','Movement is not registered',details={'definition_id':id})
    if type(parameters) is not dict: c.fail('INVALID_PARAMETER','Parameters must be a JSON object')
    if len(parameters)>c.MAX_PARAMETERS: c.fail('RESOURCE_LIMIT','Too many movement parameters')
    specs={p.name:p for p in definition.parameter_specs}
    values=[]
    for name,value in parameters.items():
        if name in specs and specs[name].type in ('vector','quaternion') and type(value) is list:
            if len(value)>16: c.fail('RESOURCE_LIMIT','Spatial parameter exceeds its dimension budget')
            value=tuple(value)
        values.append(c.ParameterValue(name,value))
    instance=validate_instance(c.MovementInstance(instance_id,id,definition.version,tuple(values),()),profile,catalog)
    check_requirements(definition.entry_conditions,entry_state,profile)
    _support_requirements(definition,entry_state,instance_id)
    return instance


def build_fragment(instance, entry_state, profile, surfaces, catalog):
    instance=validate_instance(instance,profile,catalog)
    validate_snapshot(entry_state,profile)
    definition=get_movement(instance.definition_id,instance.definition_version,catalog)
    check_requirements(definition.entry_conditions,entry_state,profile)
    _support_requirements(definition,entry_state,instance.instance_id)
    if type(surfaces) is not tuple or any(type(s) is not Surface for s in surfaces):
        c.fail('UNRESOLVED_SURFACE','Pass resolved immutable Surface records')
    names=tuple(s.name for s in surfaces)
    c.distinct(names,None)
    for surface in surfaces:
        c.check_type(surface.name,c.ID,'surface.name')
        c.check_type(surface.height,float,'surface.height')
        if abs(surface.height)>20: c.fail('RESOURCE_LIMIT','Surface exceeds the world budget')
        if surface.name=='floor' and surface.height!=0:
            c.fail('UNRESOLVED_SURFACE','The existing floor is at world height zero')
        if (surface.center is None)!=(surface.size is None):
            c.fail('INVALID_PARAMETER','A bounded surface requires both center and size')
        if surface.center is not None:
            c.check_type(surface.center,tuple[c.Number,c.Number],'surface.center')
            c.check_type(surface.size,tuple[c.Number,c.Number],'surface.size')
            if any(abs(v)>20 for v in surface.center) or any(not 0<v<=10 for v in surface.size):
                c.fail('RESOURCE_LIMIT','Surface dimensions exceed the shared budget')
    fragment=catalog.builder(definition.builder_id)(instance,entry_state,profile,surfaces)
    if type(fragment) is not c.MotionFragment: c.fail('INVALID_SCHEMA','Builder must return a MotionFragment')
    if fragment.source_instance_ids!=(instance.instance_id,):
        c.fail('UNKNOWN_ID','Single-fragment builder changed its source instance identity')
    validate_fragment(fragment,profile,resolved_surface_ids=names)
    controls={v.id:v for v in profile.controls}
    for track in fragment.tracks:
        if controls[track.control_id].chain not in definition.owned_chains:
            c.fail('CONSTRAINT_CONFLICT','Builder writes a chain it does not own',control_id=track.control_id)
    if not set(supporting_chains(t.control_id for t in fragment.tracks))<=set(definition.owned_chains):
        c.fail('CONSTRAINT_CONFLICT','Endpoint builder must declare the supporting arm chains it owns')
    requirements=definition.entry_conditions+fragment.entry_requirements
    check_requirements(requirements,entry_state,profile)
    goals=list(fragment.goals)
    for condition in (*definition.exit_expectations,*fragment.exit_expectations):
        goals.append(c.GoalSpec(condition.requirement_id,instance.instance_id,condition.target,
                               c.TimeInterval(fragment.duration_s,fragment.duration_s),condition.tolerance))
    return replace(fragment,entry_requirements=tuple({r.requirement_id:r for r in requirements}.values()),goals=tuple(goals))


def prepare_fragment(fragment, entry_state, profile):
    validate_snapshot(entry_state,profile)
    validate_fragment(fragment,profile,resolved_surface_ids=tuple(e.surface_id for e in fragment.contact_events))
    check_requirements(fragment.entry_requirements,entry_state,profile)
    check_goal_coverage(fragment.goals,fragment.duration_s,c.FPS)
    for anchor in entry_state.active_contacts:
        if not any(e.anchor_id==anchor and e.interval.start_s==0 for e in fragment.contact_events):
            c.fail('ENTRY_MISMATCH','An active entry contact needs an explicit continuation or release interval',details={'anchor_id':anchor})
    by_control={}
    bindings=[]
    sources=[]
    for track in sorted(fragment.tracks,key=lambda t:(t.interval.start_s,t.track_id)):
        previous=by_control.get(track.control_id)
        target=c.ControlValue(track.control_id,track.unit,track.frame,0)
        measured=_measured(entry_state,target)
        if previous is None and track.curve.kind=='hold' and track.curve.look_at_world_v1 is not None:
            position=_measured(entry_state,c.ControlValue('head.position','metre','world',0))
            aimed=look_rotation(position,track.curve.look_at_world_v1)
            if value_error(measured,aimed,'quaternion')>.05:
                c.fail('ENTRY_MISMATCH','Initial look-at hold would reset the measured orientation; author an approach transition',control_id=track.control_id)
        if track.start_source=='explicit':
            expected=measured if previous is None else previous.curve.end_value if previous.curve.end_value is not None else previous.curve.start_value
            if expected is not None and value_error(expected,track.curve.start_value,track.value_shape)>1e-5:
                c.fail('ENTRY_MISMATCH','Explicit track start would reset or jump the measured state',control_id=track.control_id)
        else:
            bindings.append(c.RuntimeEntryBinding(track.track_id,track.source_instance_ids[0],track.interval.start_s,None))
        by_control[track.control_id]=track
        clauses=tuple(sorted({g.clause_id for g in fragment.goals if g.target.control_id==track.control_id}))
        sources.append(c.SourceMapEntry(track.track_id,track.source_instance_ids,clauses))
    for event in fragment.contact_events:
        sources.append(c.SourceMapEntry(event.event_id,event.source_instance_ids,()))
    for goal in fragment.goals:
        sources.append(c.SourceMapEntry(goal.goal_id,fragment.source_instance_ids,(goal.clause_id,)))
    return c.ExecutableMotion(entry_state,fragment.duration_s,c.FPS,fragment.tracks,fragment.contact_events,
                              tuple(bindings),tuple(sources),None,fragment.goals)


def compile_recipe(resolved, entry_state, profile, *, surfaces=None, catalog=None):
    """Compile recipe instances sharing the captured activation snapshot."""
    from .composer import compose_recipe
    from .joints import catalog_for_profile

    if type(resolved) is not c.ResolvedRecipe:
        c.fail('INVALID_PARAMETER', 'Expected a resolved recipe')
    validate_snapshot(entry_state, profile)
    recipe = resolved.recipe
    if recipe.base_revision != entry_state.revision:
        c.fail('STALE_REVISION', 'Resolved recipe belongs to a different measured revision')
    if resolved.transitions or recipe.optional_styles:
        c.fail('UNSUPPORTED_GOAL', 'Transition insertion and recipe-level styles are unavailable')
    if surfaces is None:
        surfaces = (Surface(),)
    if catalog is None:
        catalog = catalog_for_profile(profile)
    expected = compose_recipe(recipe, entry_state, profile, surfaces, catalog)
    if resolved != expected:
        c.fail('ENTRY_MISMATCH', 'Resolved recipe no longer matches the measured entry and surfaces')
    if recipe.operation == 'append':
        origin = entry_state.captured_time_s
        def local(item):
            return replace(item, interval=c.TimeInterval(max(0, item.interval.start_s - origin),
                                                         item.interval.end_s - origin))
        local_recipe = replace(recipe, hard_goals=tuple(local(item) for item in recipe.hard_goals))
        # Keep serialized Stage 06 timestamps intact; only the execution view
        # uses local time. A saved activation refers to this local timeline.
        resolved = replace(resolved, recipe=local_recipe, resolution_v1=None,
                           scheduled_instances=tuple(local(item) for item in resolved.scheduled_instances),
                           ownership=tuple(local(item) for item in resolved.ownership),
                           merged_contacts=tuple(local(item) for item in resolved.merged_contacts))
        recipe = local_recipe
    if recipe.loop is not None and len(recipe.instances) != 1:
        c.fail('UNSUPPORTED_GOAL', 'Finite recipe loops currently require one returning authored instance')
    if len(recipe.instances) != 1:
        executable = _compile_schedule(resolved, entry_state, profile, surfaces, catalog)
        return replace(executable, recipe_surfaces_v1=recipe_surface_snapshot(surfaces))
    instance = recipe.instances[0]
    fragment = build_fragment(instance, entry_state, profile, surfaces, catalog)
    if recipe.loop is not None:
        from .patterns import repeat_fragment
        transform = recipe.loop.per_cycle_root_transform
        if transform.position != (0, 0, 0) or value_error(transform.orientation, (1, 0, 0, 0), 'quaternion') > 1e-6:
            c.fail('UNSUPPORTED_GOAL', 'Finite recipe loops currently require stationary seams')
        if abs(fragment.duration_s * c.FPS - round(fragment.duration_s * c.FPS)) > 1e-7:
            c.fail('UNSUPPORTED_GOAL', 'A loop seam must land on a sample boundary')
        fragment = repeat_fragment(replace(fragment, goals=fragment.goals + recipe.hard_goals),
                                   recipe.loop.repetitions, entry=entry_state, profile=profile)
    executable = prepare_fragment(fragment, entry_state, profile)
    goals = executable.goal_checks if recipe.loop else executable.goal_checks + recipe.hard_goals
    check_goal_coverage(goals, executable.duration_s, executable.fps)
    sources = tuple(replace(source, clause_ids=tuple(sorted(set(source.clause_ids + instance.clause_ids))))
                    for source in executable.source_map)
    sources += tuple(c.SourceMapEntry(goal.goal_id, (instance.instance_id,), (goal.clause_id,))
                     for goal in (() if recipe.loop else recipe.hard_goals))
    return replace(executable, goal_checks=goals, source_map=sources, loop=recipe.loop,
                   recipe_activation_v1=() if recipe.loop else None,
                   recipe_surfaces_v1=recipe_surface_snapshot(surfaces))


def recipe_surface_snapshot(surfaces):
    return tuple(c.RecipeSurfaceV1(item.name, item.height, item.center, item.size)
                 for item in sorted(surfaces, key=lambda surface: surface.name))


def _compile_schedule(resolved, entry_state, profile, surfaces, catalog):
    """Lay out tracks and retain descriptors for delayed measured activations."""
    instances = {item.instance_id: item for item in resolved.recipe.instances}
    controls = {item.id: item for item in profile.controls}
    ownership = {}
    for item in resolved.ownership:
        for id in item.source_instance_ids:
            ownership.setdefault((id, item.chain_id), []).append(item.interval)

    tracks, goals, activations = [], list(resolved.recipe.hard_goals), []
    goal_sources = {goal.goal_id: next(clause.source_instance_ids for clause in resolved.recipe.clause_coverage
                                     if clause.clause_id == goal.clause_id) for goal in goals}
    for scheduled in resolved.scheduled_instances:
        id = scheduled.instance_id
        fragment = build_fragment(instances[id], entry_state, profile, surfaces, catalog)
        start = scheduled.interval.start_s
        if start:
            if any(event.target_world_v1 is not None or event.acquire_s or event.release_s
                   for event in fragment.contact_events):
                c.fail('UNSUPPORTED_GOAL', 'Delayed authored support changes require runtime contact rebinding',
                       instance_id=id)
            activations.append(c.RecipeActivationV1(instances[id], fragment, start))
        accepted = set()
        for track in fragment.tracks:
            chains = {controls[track.control_id].chain, *supporting_chains((track.control_id,))}
            total = []
            for chain in chains:
                span = shift_interval(track.interval, start)
                intervals = ownership.get((id, chain), ())
                total.append(sum(max(0, min(span.end_s, item.end_s) - max(span.start_s, item.start_s))
                                 for item in intervals))
            if all(abs(amount - track.curve.duration_s) <= 1e-9 for amount in total):
                tracks.append(replace(track, interval=shift_interval(track.interval, start)))
                accepted.add(track.control_id)
            elif any(amount > 1e-9 for amount in total):
                c.fail('UNSUPPORTED_GOAL', 'Optional track ownership changes inside the track',
                       instance_id=id, control_id=track.control_id)
        for goal in fragment.goals:
            if goal.target.control_id in accepted or not any(
                    track.control_id == goal.target.control_id for track in fragment.tracks):
                goals.append(replace(goal, interval=shift_interval(goal.interval, start)))
                goal_sources[goal.goal_id] = (id,)

    contacts = resolved.merged_contacts
    duration = max(item.interval.end_s for item in resolved.scheduled_instances)
    contributing = tuple(sorted({id for item in (*tracks, *contacts) for id in item.source_instance_ids}))
    if not contributing:
        c.fail('UNSUPPORTED_GOAL', 'Resolved recipe has no tracks or contacts to execute')
    fragment = c.MotionFragment('recipe.schedule', contributing, (), duration,
                                tuple(tracks), contacts, (), (), tuple(goals))
    first_tracks = tuple(track for track in tracks if not any(
        activation.instance.instance_id in track.source_instance_ids for activation in activations))
    executable = prepare_fragment(replace(fragment, tracks=first_tracks, goals=()), entry_state, profile)
    sources = []
    for item in (*tracks, *contacts):
        clauses = {clause for id in item.source_instance_ids for clause in instances[id].clause_ids}
        sources.append(c.SourceMapEntry(getattr(item, 'track_id', None) or item.event_id,
                                        item.source_instance_ids, tuple(sorted(clauses))))
    sources.extend(c.SourceMapEntry(goal.goal_id, goal_sources[goal.goal_id], (goal.clause_id,))
                   for goal in goals)
    check_goal_coverage(goals, duration, c.FPS)
    bindings = tuple(c.RuntimeEntryBinding(track.track_id, track.source_instance_ids[0], track.interval.start_s, None)
                     for track in tracks if track.start_source == 'measured_entry')
    return replace(executable, tracks=tuple(tracks), goal_checks=tuple(goals), runtime_entry_bindings=bindings,
                   source_map=tuple(sources), recipe_activation_v1=tuple(activations))


def shift_interval(interval, offset):
    return c.TimeInterval(interval.start_s + offset, interval.end_s + offset)


def prepare_recipe_activation(instance, planned, measured, profile, surfaces, catalog, *, inherit_support=False):
    """Rebuild an activation from the solved state and enforce planned topology.

    Spatial values may follow the measured entry. Changes to track routing,
    landmarks or contact timing require a new schedule before baking can proceed.
    """
    if type(planned) is not c.MotionFragment or planned.source_instance_ids != (instance.instance_id,):
        c.fail('INVALID_PARAMETER', 'Activation descriptor belongs to another instance')
    actual = build_fragment(instance, measured, profile, surfaces, catalog)

    def topology(fragment):
        return (
            fragment.duration_s, fragment.phase_landmarks,
            tuple((track.track_id, track.control_id, track.frame, track.unit, track.interval,
                   track.start_source, track.curve.kind) for track in fragment.tracks),
            () if inherit_support else tuple(
                (event.anchor_id, event.surface_id, event.interval, event.acquire_s, event.release_s,
                 event.target_world_v1 is not None) for event in fragment.contact_events),
            tuple((goal.goal_id, goal.target.control_id, goal.target.frame, goal.interval)
                  for goal in fragment.goals),
        )

    if topology(actual) != topology(planned):
        c.fail('ENTRY_MISMATCH', 'Measured activation changed the planned fragment topology',
               instance_id=instance.instance_id)
    return prepare_fragment(actual, measured, profile)


@dataclass
class ExecutionCursor:
    """One run's activation state. Never share this object between runs/plans."""
    bindings: dict = field(default_factory=dict)
    last_time_s: float | None = None
    executable: object = None
    activation_ready: set = field(default_factory=set)
    activation_curves: dict = field(default_factory=dict)
    activation_goals: dict = field(default_factory=dict)
    defer_activation: bool = False


def activate_recipe_boundary(executable, time_s, measured, cursor, profile, surfaces, catalog):
    """Commit a group of same-frame descriptors only after every rebuild succeeds."""
    if abs(measured.captured_time_s - time_s) > 1e-8:
        c.fail('ENTRY_MISMATCH', 'Activation requires a solved snapshot from its boundary frame')
    pending = []
    for item in executable.recipe_activation_v1 or ():
        if item.instance.instance_id not in cursor.activation_ready and abs(item.time_s - time_s) <= 1e-8:
            motion = prepare_recipe_activation(item.instance, item.planned, measured, profile, surfaces,
                                               catalog, inherit_support=True)
            pending.append((item.instance.instance_id, motion))
    for id, motion in pending:
        cursor.activation_curves.update((track.track_id, track.curve) for track in motion.tracks)
        cursor.activation_goals.update((goal.goal_id, goal.target) for goal in motion.goal_checks)
        cursor.activation_ready.add(id)


def interpolate(start,end,weight,shape):
    if shape=='quaternion':
        dot=sum(a*b for a,b in zip(start,end))
        if dot<0: end=tuple(-x for x in end); dot=-dot
        dot=min(1,max(0,dot))
        if dot>.9995:
            value=tuple(a+(b-a)*weight for a,b in zip(start,end))
        else:
            angle=math.acos(dot); denominator=math.sin(angle)
            value=tuple((math.sin((1-weight)*angle)*a+math.sin(weight*angle)*b)/denominator for a,b in zip(start,end))
        length=math.sqrt(sum(v*v for v in value))
        return tuple(v/length for v in value)
    if type(start) is tuple: return tuple(a+(b-a)*weight for a,b in zip(start,end))
    return start+(end-start)*weight


@dataclass
class LegacySamplingCursor:
    starting: dict
    intervals: tuple
    baselines: dict = field(default_factory=dict)


def sample_legacy_frame(plan, time, starting, baselines, measured, *, intervals=None):
    """Start each newly activated movement from the actual preceding solved state."""
    from mathutils import Quaternion, Vector
    from ..motion import blend_control, control_default, schedule
    values = dict(starting)
    intervals = schedule(plan) if intervals is None else intervals
    for stage, start, end in sorted(intervals, key=lambda row: row[1]):
        if time < start - 1e-8:
            continue
        if stage.id not in baselines:
            baselines[stage.id] = dict(measured)
        source = baselines[stage.id]
        weight = min(1.0, max(0.0, (time - start) / stage.duration))
        weight = weight * weight * (3 - 2 * weight)
        for key, target in stage.targets:
            before = source.get(key, control_default(source, key))
            if target is None:
                if '_target_' in key or time >= end:
                    values.pop(key, None)
            elif key == 'grounding':
                values[key] = 0 if target == 0 else (target if time >= end else before)
            else:
                values[key] = blend_control(plan, stage, key, before, time)
        # Direction interpolation avoids sweeping a shin sideways when changing
        # from backward to forward through the azimuth wrap.
        for side, sign in (('left', -1), ('right', 1)):
            for part in ('arm', 'forearm', 'thigh', 'shin'):
                e, a = side+'_'+part+'_elevation', side+'_'+part+'_azimuth'
                targets = dict(stage.targets)
                if e not in targets or a not in targets or targets[e] is None or targets[a] is None:
                    continue
                se, sa = source.get(e, 0), source.get(a, 0)
                if abs(targets[a] - sa) < 45:
                    continue
                def vector(elev, az):
                    elev, az = math.radians(elev), math.radians(az)
                    return Vector((sign*math.sin(elev)*math.cos(az), math.sin(elev)*math.sin(az), -math.cos(elev)))
                first, last = vector(se, sa), vector(targets[e], targets[a])
                v = Quaternion().slerp(first.rotation_difference(last), weight) @ first
                values[e] = math.degrees(math.acos(max(-1, min(1, -v.z))))
                values[a] = math.degrees(math.atan2(v.y, sign*v.x))
    # IK may have changed an unowned leg or pelvis. Carry that ending state
    # when the next movement does not own it, rather than resetting to rest.
    owned = {k for s, start, end in intervals if start <= time <= end for k, _ in s.targets}
    explicit = set(starting) | {k for s, start, _ in intervals if start <= time
                               for k, _ in s.targets}
    for key in measured:
        implicit_lower = next((key.replace('_'+lower+'_', '_'+upper+'_')
                               for lower, upper in (('forearm', 'arm'), ('shin', 'thigh'))
                               if '_'+lower+'_' in key and key not in explicit), None)
        if implicit_lower in owned:
            values.pop(key, None)
            continue
        if key not in owned and (key.startswith('pelvis_') or any('_'+p+'_' in key for p in ('thigh','shin','arm','forearm'))):
            values[key] = measured[key]
    return values


def sample_motion(executable, time_s, measured_state, execution_cursor):
    from ..motion import ActionPlan
    if isinstance(executable, ActionPlan) and isinstance(execution_cursor, LegacySamplingCursor):
        return sample_legacy_frame(executable, time_s, execution_cursor.starting, execution_cursor.baselines,
                                   measured_state, intervals=execution_cursor.intervals)
    if type(executable) is not c.ExecutableMotion or type(execution_cursor) is not ExecutionCursor:
        c.fail('INVALID_PARAMETER','Expected executable motion and a per-run cursor')
    c.check_type(time_s,c.Seconds,'time_s')
    if time_s>executable.duration_s: c.fail('INVALID_PARAMETER','Sample time exceeds motion duration')
    cursor=execution_cursor
    if cursor.executable is not None and cursor.executable is not executable:
        c.fail('STALE_REVISION','A cursor cannot be reused for another executable')
    if type(measured_state) is not c.MotionStateSnapshot or (measured_state.avatar_id,measured_state.profile_version,measured_state.revision)!=(
            executable.entry_snapshot.avatar_id,executable.entry_snapshot.profile_version,executable.entry_snapshot.revision):
        c.fail('STALE_REVISION','Measured state belongs to another rig, profile or revision')
    if cursor.last_time_s is None and time_s!=0:
        c.fail('ENTRY_MISMATCH','Start a new sampling run at time zero')
    if cursor.last_time_s is not None and time_s<cursor.last_time_s:
        c.fail('STALE_REVISION','Sampling must be chronological; use a new cursor to restart')
    if cursor.last_time_s is not None and time_s-cursor.last_time_s>1/executable.fps+1e-7:
        c.fail('ENTRY_MISMATCH','Sampling skipped an execution boundary')
    blocked = set()
    blocked_goals = set()
    for item in executable.recipe_activation_v1 or ():
        id = item.instance.instance_id
        if id in cursor.activation_ready:
            continue
        if item.time_s <= time_s + 1e-9 and not (cursor.defer_activation and abs(item.time_s - time_s) <= 1e-9):
            c.fail('ENTRY_MISMATCH', 'Delayed tracks require their solved activation before sampling', instance_id=id)
        blocked.add(id)
        blocked_goals.update(goal.goal_id for goal in item.planned.goals)
    tracks = tuple(replace(track, curve=cursor.activation_curves[track.track_id])
                   if track.track_id in cursor.activation_curves else track
                   for track in executable.tracks if not blocked.intersection(track.source_instance_ids))
    pending={}
    # Resolve all activations from this same pre-application measured snapshot.
    for track in tracks:
        if track.start_source=='measured_entry' and track.track_id not in cursor.bindings and track.interval.start_s<=time_s+1e-9:
            pending[track.track_id]=_measured(measured_state,c.ControlValue(track.control_id,track.unit,track.frame,0))
    bindings={**cursor.bindings,**pending}
    selected={}
    for track in sorted(tracks,key=lambda t:(t.interval.start_s,t.track_id)):
        if time_s+1e-9<track.interval.start_s: continue
        start=track.curve.start_value if track.start_source=='explicit' else bindings[track.track_id]
        weight=min(1,max(0,(time_s-track.interval.start_s)/track.curve.duration_s))
        weight=ease_weight(weight,track.curve.easing,track.curve.style_timing)
        end=track.curve.end_value
        if track.curve.look_at_world_v1 is not None:
            position=_measured(measured_state,c.ControlValue('head.position','metre','world',0))
            end=look_rotation(position,track.curve.look_at_world_v1)
        value=(end if track.curve.look_at_world_v1 is not None else start) if track.curve.kind=='hold' else interpolate(start,end,weight,track.value_shape)
        selected[track.control_id]=(c.ControlValue(track.control_id,track.unit,track.frame,value),track.source_instance_ids)
    contacts=tuple(e for e in executable.contact_events if e.interval.start_s<=time_s<=e.interval.end_s)
    goals=tuple(replace(g, target=cursor.activation_goals[g.goal_id]) if g.goal_id in cursor.activation_goals else g
                for g in executable.goal_checks if g.goal_id not in blocked_goals
                and g.interval.start_s-1e-9<=time_s<=g.interval.end_s+1e-9)
    # World-point goals use the same versioned binding, then compare achieved rotation.
    aim=next((t for t in reversed(sorted(tracks,key=lambda t:(t.interval.start_s,t.track_id)))
              if t.control_id=='head.orientation' and t.interval.start_s<=time_s+1e-9),None)
    if aim is not None and aim.curve.look_at_world_v1 is not None:
        end=look_rotation(_measured(measured_state,c.ControlValue('head.position','metre','world',0)),aim.curve.look_at_world_v1)
        goals=tuple(replace(g,target=replace(g.target,value=end)) if g.target.control_id=='head.orientation' else g for g in goals)
    sources=tuple(sorted({s for _,ids in selected.values() for s in ids}|{s for e in contacts for s in e.source_instance_ids}))
    frame=c.FrameTargets(time_s,tuple(v for v,_ in selected.values()),contacts,None,sources,goals,supporting_chains(selected))
    cursor.bindings.update(pending); cursor.last_time_s=time_s; cursor.executable=executable
    return frame
