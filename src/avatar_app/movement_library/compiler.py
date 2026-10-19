"""Pure single-fragment preparation and hold/transition sampling (Stage 04).

No graph scheduler, rig handles, model calls or scene mutation belong here.
"""
from dataclasses import dataclass, field, replace
import math
from . import contracts as c
from .registry import (get_movement, validate_instance, validate_fragment,
                       validate_snapshot, validate_control_value)
from ..motion import Surface


def supporting_chains(control_ids):
    """Endpoint IK's narrowly declared supporting chains, in semantic IDs."""
    return tuple(sorted({side+'.'+part for id in control_ids if id in ('left.hand.position','right.hand.position')
                         for side in (id.split('.')[0],) for part in ('upper_arm','forearm')}))


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


@dataclass
class ExecutionCursor:
    """One run's activation state. Never share this object between runs/plans."""
    bindings: dict = field(default_factory=dict)
    last_time_s: float | None = None
    executable: object = None


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


def sample_motion(executable, time_s, measured_state, execution_cursor):
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
    pending={}
    # Resolve all activations from this same pre-application measured snapshot.
    for track in executable.tracks:
        if track.start_source=='measured_entry' and track.track_id not in cursor.bindings and track.interval.start_s<=time_s+1e-9:
            pending[track.track_id]=_measured(measured_state,c.ControlValue(track.control_id,track.unit,track.frame,0))
    bindings={**cursor.bindings,**pending}
    selected={}
    for track in sorted(executable.tracks,key=lambda t:(t.interval.start_s,t.track_id)):
        if time_s+1e-9<track.interval.start_s: continue
        start=track.curve.start_value if track.start_source=='explicit' else bindings[track.track_id]
        weight=min(1,max(0,(time_s-track.interval.start_s)/track.curve.duration_s))
        if track.curve.easing=='smooth': weight=weight*weight*(3-2*weight)
        value=start if track.curve.kind=='hold' else interpolate(start,track.curve.end_value,weight,track.value_shape)
        selected[track.control_id]=(c.ControlValue(track.control_id,track.unit,track.frame,value),track.source_instance_ids)
    contacts=tuple(e for e in executable.contact_events if e.interval.start_s<=time_s<=e.interval.end_s)
    goals=tuple(g for g in executable.goal_checks if g.interval.start_s-1e-9<=time_s<=g.interval.end_s+1e-9)
    sources=tuple(sorted({s for _,ids in selected.values() for s in ids}|{s for e in contacts for s in e.source_instance_ids}))
    frame=c.FrameTargets(time_s,tuple(v for v,_ in selected.values()),contacts,None,sources,goals,supporting_chains(selected))
    cursor.bindings.update(pending); cursor.last_time_s=time_s; cursor.executable=executable
    return frame
