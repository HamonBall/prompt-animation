"""Immutable v1 authoring/execution data; no rig execution or language planning."""
from dataclasses import dataclass, fields, is_dataclass
from functools import lru_cache
import json
import math
import re
import types
from typing import Annotated, Literal, Union, get_args, get_origin, get_type_hints
from ..models import PlanError

SCHEMA_VERSION = 1
MAX_SECONDS = 60
FPS = 30
MAX_SAMPLES = 1801
MAX_INSTANCES = 128
MAX_TRACKS = 256
MAX_CONTACTS = 256
MAX_PARAMETERS = 64
MAX_JSON_BYTES = 1_000_000
ERROR_CODES = ('UNKNOWN_ID', 'VERSION_MISMATCH', 'INVALID_PARAMETER', 'MISSING_CAPABILITY',
               'ENTRY_MISMATCH', 'CONSTRAINT_CONFLICT', 'UNRESOLVED_SURFACE', 'RESOURCE_LIMIT',
               'STALE_REVISION', 'INVALID_SCHEMA', 'UNSUPPORTED_GOAL')


class MotionContractError(PlanError):
    def __init__(self, code, message, *, instance_id=None, control_id=None, details=None):
        if code not in ERROR_CODES:
            raise ValueError('Unknown motion error code')
        super().__init__(message)
        self.code, self.instance_id, self.control_id = code, instance_id, control_id
        self.details = dict(details or {})

    def to_dict(self):
        return {'code':self.code, 'message':str(self), 'instance_id':self.instance_id,
                'control_id':self.control_id, 'details':self.details}


def fail(code, message, **context):
    raise MotionContractError(code, message, **context)


@dataclass(frozen=True)
class Rule:
    minimum: float | None = None
    maximum: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None


ID_PATTERN = r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}'
FRAME_PATTERN = r'(world|entry_body|current_root|current_torso|current_pelvis|joint:[A-Za-z0-9][A-Za-z0-9_.-]{0,95}|surface:[A-Za-z0-9][A-Za-z0-9_.-]{0,95})'
ID = Annotated[str, Rule(pattern=ID_PATTERN)]
Frame = Annotated[str, Rule(pattern=FRAME_PATTERN)]
Text = Annotated[str, Rule(min_length=1, max_length=2000)]
Version = Annotated[int, Rule(minimum=0)]
Seconds = Annotated[float, Rule(minimum=0, maximum=MAX_SECONDS)]
Number = float | int
Vector3 = tuple[Number, Number, Number]
Quaternion = tuple[Number, Number, Number, Number]
Value = Number | Annotated[tuple[Number, ...], Rule(min_length=1, max_length=16)]
ParameterData = Value | str | bool | None
Unit = Literal['degree', 'metre', 'avatar_height', 'second', 'unitless',
               'degree_per_second', 'metre_per_second', 'avatar_height_per_second']
IDs = Annotated[tuple[ID, ...], Rule(max_length=MAX_INSTANCES)]


@lru_cache(maxsize=None)
def hints(record_type):
    return get_type_hints(record_type, include_extras=True)


def check_type(value, annotation, path):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        for rule in args[1:]:
            if rule.max_length is not None and type(value) in (tuple,str) and len(value) > rule.max_length:
                fail('RESOURCE_LIMIT', f'{path} exceeds its size budget', details={'field':path})
        check_type(value, args[0], path)
        for rule in args[1:]:
            if rule.minimum is not None and value < rule.minimum or rule.maximum is not None and value > rule.maximum:
                fail('INVALID_PARAMETER', f'{path} is outside its declared bounds', details={'field':path})
            if rule.min_length is not None and len(value) < rule.min_length:
                fail('INVALID_PARAMETER', f'{path} is incomplete', details={'field':path})
            if rule.max_length is not None and len(value) > rule.max_length:
                fail('RESOURCE_LIMIT', f'{path} exceeds its size budget', details={'field':path})
            if rule.pattern is not None and re.fullmatch(rule.pattern, value) is None:
                fail('INVALID_PARAMETER', f'{path} has an unknown identifier or frame format', details={'field':path})
    elif origin in (Union, types.UnionType):
        errors = []
        for candidate in args:
            try:
                check_type(value, candidate, path)
                return
            except MotionContractError as exc:
                errors.append(exc)
        for exc in errors:
            if exc.code in ('RESOURCE_LIMIT', 'VERSION_MISMATCH'): raise exc
        fail('INVALID_PARAMETER', f'{path} has an invalid type/value', details={'field':path})
    elif origin is Literal:
        if not any(type(value) is type(option) and value == option for option in args):
            fail('VERSION_MISMATCH' if path.endswith('.schema_version') else 'INVALID_PARAMETER',
                 f'{path} has an unsupported value', details={'field':path, 'allowed':list(args)})
    elif origin is tuple:
        if type(value) is not tuple:
            fail('INVALID_PARAMETER', f'{path} must be an immutable tuple', details={'field':path})
        if len(args) == 2 and args[1] is Ellipsis:
            for i, item in enumerate(value): check_type(item, args[0], f'{path}[{i}]')
        else:
            if len(value) != len(args): fail('INVALID_PARAMETER', f'{path} needs {len(args)} coordinates')
            for i, (item, kind) in enumerate(zip(value, args)): check_type(item, kind, f'{path}[{i}]')
    elif annotation is float:
        if type(value) not in (float, int) or type(value) is float and not math.isfinite(value):
            fail('INVALID_PARAMETER', f'{path} must be a finite number')
    elif annotation is int:
        if type(value) is not int: fail('INVALID_PARAMETER', f'{path} must be an integer, not a boolean')
    elif annotation is type(None):
        if value is not None: fail('INVALID_PARAMETER', f'{path} must be null')
    elif is_dataclass(annotation):
        if type(value) is not annotation: fail('INVALID_PARAMETER', f'{path} needs {annotation.__name__}')
    elif type(value) is not annotation:
        fail('INVALID_PARAMETER', f'{path} has an invalid type')
    elif annotation is str:
        try: value.encode('utf-8')
        except UnicodeEncodeError: fail('INVALID_PARAMETER', f'{path} must be valid UTF-8 text')


def distinct(values, field='id'):
    keys = [getattr(item, field) if field is not None else item for item in values]
    if len(set(keys)) != len(keys): fail('CONSTRAINT_CONFLICT', f'Duplicate {field or "identifier"}')


def quaternion(value):
    if abs(sum(component*component for component in value)-1) > 1e-6:
        fail('INVALID_PARAMETER', 'Orientation must be a normalized [w,x,y,z] quaternion')


def position_budget(value, frame, unit):
    if unit == 'metre' and (frame == 'world' or frame is not None and frame.startswith('surface:')):
        if sum(v*v for v in value) > 20**2:
            fail('RESOURCE_LIMIT', 'Position exceeds the 20 metre workspace')


@dataclass(frozen=True, kw_only=True)
class Record:
    schema_version: Literal[1] = SCHEMA_VERSION

    def __post_init__(self):
        for field in fields(self):
            check_type(getattr(self, field.name), hints(type(self))[field.name], type(self).__name__+'.'+field.name)
        self._validate()

    def _validate(self): pass


@dataclass(frozen=True)
class ParameterSpec(Record):
    name: ID
    type: Literal['number', 'integer', 'boolean', 'string', 'enum', 'vector', 'quaternion']
    unit: Unit
    frame: Frame | None
    required: bool
    has_default: bool
    default: ParameterData
    minimum: Number | None = None
    maximum: Number | None = None
    enum_values: tuple[str, ...] = ()
    dimensions: Annotated[int, Rule(minimum=1, maximum=16)] | None = None
    capability: ID | None = None
    nullable: bool = False
    control_id: ID | None = None

    def _validate(self):
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            fail('INVALID_PARAMETER', 'Parameter bounds are reversed')
        if self.type in ('vector','quaternion') and self.frame is None:
            fail('INVALID_PARAMETER', 'Spatial parameters require a declared frame')
        if self.control_id is not None and self.frame is None:
            fail('INVALID_PARAMETER', 'A control-linked parameter requires its frame')
        if self.type == 'vector' and self.dimensions is None or self.type == 'quaternion' and self.dimensions != 4:
            fail('INVALID_PARAMETER', 'Spatial parameters require their fixed dimension')
        if self.type not in ('vector','quaternion') and self.dimensions is not None:
            fail('INVALID_PARAMETER', 'Scalar parameters cannot declare vector dimensions')
        if self.type == 'enum' and not self.enum_values or self.type != 'enum' and self.enum_values:
            fail('INVALID_PARAMETER', 'Enum choices must belong to an enum parameter')
        distinct(self.enum_values, None)
        if not self.has_default and self.default is not None:
            fail('INVALID_PARAMETER', 'A value is not a default unless has_default is true')
        if self.has_default: validate_parameter(self, self.default)


def validate_parameter(spec, value):
    if value is None:
        if not spec.nullable: fail('INVALID_PARAMETER', f'{spec.name} does not allow null')
        return
    kind = spec.type
    if kind == 'number': check_type(value, float, spec.name)
    elif kind == 'integer': check_type(value, int, spec.name)
    elif kind == 'boolean': check_type(value, bool, spec.name)
    elif kind in ('string','enum'):
        check_type(value, str, spec.name)
        if not 1 <= len(value) <= 2000: fail('INVALID_PARAMETER', f'Invalid string parameter {spec.name}')
        if kind == 'enum' and value not in spec.enum_values: fail('INVALID_PARAMETER', f'Unknown choice for {spec.name}')
    else:
        check_type(value, tuple[Number, ...], spec.name)
        if len(value) != spec.dimensions: fail('INVALID_PARAMETER', f'{spec.name} needs {spec.dimensions} coordinates')
        if kind == 'quaternion': quaternion(value)
        if kind == 'vector' and spec.dimensions == 3: position_budget(value,spec.frame,spec.unit)
    numbers = value if type(value) is tuple else (value,)
    if kind in ('number','integer','vector','quaternion'):
        if any(spec.minimum is not None and n < spec.minimum or spec.maximum is not None and n > spec.maximum for n in numbers):
            fail('INVALID_PARAMETER', f'{spec.name} is outside its declared range')


@dataclass(frozen=True)
class ParameterValue(Record):
    name: ID
    value: ParameterData


@dataclass(frozen=True)
class ControlSpec(Record):
    id: ID
    unit: Unit
    value_shape: Literal['scalar', 'vector', 'quaternion']
    dimensions: Annotated[int, Rule(minimum=1, maximum=16)]
    frames: Annotated[tuple[Frame, ...], Rule(min_length=1, max_length=64)]
    chain: ID
    capability: ID

    def _validate(self):
        distinct(self.frames, None)
        if self.value_shape == 'scalar' and self.dimensions != 1 or self.value_shape == 'quaternion' and self.dimensions != 4:
            fail('INVALID_PARAMETER', 'Control shape and dimension disagree')
        if self.value_shape == 'quaternion' and self.unit != 'unitless':
            fail('INVALID_PARAMETER', 'Quaternions are dimensionless')


@dataclass(frozen=True)
class ControlValue(Record):
    control_id: ID
    unit: Unit
    frame: Frame
    value: Value

    def _validate(self):
        if type(self.value) is tuple and len(self.value) == 3:
            position_budget(self.value,self.frame,self.unit)


@dataclass(frozen=True)
class TimeInterval(Record):
    start_s: Seconds
    end_s: Seconds

    def _validate(self):
        if self.end_s < self.start_s: fail('INVALID_PARAMETER', 'Time interval is reversed')


@dataclass(frozen=True)
class Transform(Record):
    position: Vector3
    orientation: Quaternion
    frame: Frame
    unit: Literal['metre']

    def _validate(self):
        quaternion(self.orientation)
        if sum(v*v for v in self.position) > 20**2:
            fail('RESOURCE_LIMIT', 'Transform position exceeds the 20 metre workspace')


@dataclass(frozen=True)
class JointMapping(Record):
    semantic_id: ID
    parent_id: ID | None
    source_bones: Annotated[tuple[Text, ...], Rule(min_length=1, max_length=16)]
    rest_to_semantic: Transform

    def _validate(self): distinct(self.source_bones, None)


@dataclass(frozen=True)
class LengthSpec(Record):
    id: ID
    value_m: Annotated[float, Rule(minimum=1e-9, maximum=20)]


@dataclass(frozen=True)
class Landmark(Record):
    id: ID
    joint_id: ID
    position: Vector3
    frame: Frame
    unit: Literal['metre', 'avatar_height']

    def _validate(self): position_budget(self.position,self.frame,self.unit)


@dataclass(frozen=True)
class JointLimit(Record):
    control_id: ID
    minimum: Number
    maximum: Number
    zero: Number
    positive_axis: Vector3
    mirror_control_id: ID | None
    mirror_sign: Literal[-1, 1]
    measurement_method: Text
    preferred_minimum: Number | None = None
    preferred_maximum: Number | None = None

    def _validate(self):
        if not self.minimum <= self.zero <= self.maximum:
            fail('INVALID_PARAMETER', 'Joint zero must be within its software limits')
        if abs(sum(v*v for v in self.positive_axis)-1) > 1e-6:
            fail('INVALID_PARAMETER', 'Joint axis must be normalized')
        if (self.preferred_minimum is None) != (self.preferred_maximum is None):
            fail('INVALID_PARAMETER', 'Preferred range needs both bounds')
        if self.preferred_minimum is not None and not self.minimum <= self.preferred_minimum <= self.preferred_maximum <= self.maximum:
            fail('INVALID_PARAMETER', 'Preferred range must lie inside software limits')


@dataclass(frozen=True)
class Provenance(Record):
    method: Text
    source_revision: Text
    evidence: Annotated[tuple[Text, ...], Rule(min_length=1, max_length=64)]
    recorded_at: Text


@dataclass(frozen=True)
class AvatarProfile(Record):
    avatar_id: ID
    version: Version
    height_m: Annotated[float, Rule(minimum=1e-9, maximum=20)]
    canonical_frames: Annotated[tuple[Frame, ...], Rule(min_length=1, max_length=1024)]
    rest_to_semantic_mappings: Annotated[tuple[JointMapping, ...], Rule(max_length=256)]
    lengths: Annotated[tuple[LengthSpec, ...], Rule(max_length=256)]
    landmarks: Annotated[tuple[Landmark, ...], Rule(max_length=256)]
    joint_limits: Annotated[tuple[JointLimit, ...], Rule(max_length=1024)]
    controls: Annotated[tuple[ControlSpec, ...], Rule(max_length=1024)]
    capabilities: Annotated[tuple[ID, ...], Rule(max_length=1024)]
    calibration_provenance: Provenance

    def _validate(self):
        for values in (self.canonical_frames,self.capabilities): distinct(values, None)
        for values, name in ((self.rest_to_semantic_mappings,'semantic_id'), (self.lengths,'id'),
                             (self.landmarks,'id'),(self.joint_limits,'control_id'),(self.controls,'id')):
            distinct(values, name)
        joints = {j.semantic_id for j in self.rest_to_semantic_mappings}
        controls = {c.id:c for c in self.controls}
        for frame in self.canonical_frames:
            if frame.startswith('joint:') and frame[6:] not in joints:
                fail('INVALID_PARAMETER', 'Joint frame has no semantic mapping')
        for joint in self.rest_to_semantic_mappings:
            if joint.parent_id is not None and joint.parent_id not in joints:
                fail('UNKNOWN_ID', 'Joint parent has no semantic mapping')
            if joint.rest_to_semantic.frame not in self.canonical_frames:
                fail('INVALID_PARAMETER', 'Mapping uses an unavailable frame')
        parents = {j.semantic_id:j.parent_id for j in self.rest_to_semantic_mappings}
        for joint_id in parents:
            seen, current = set(), joint_id
            while current is not None:
                if current in seen: fail('CONSTRAINT_CONFLICT', 'Semantic joint hierarchy contains a cycle')
                seen.add(current)
                current = parents[current]
        for landmark in self.landmarks:
            if landmark.joint_id not in joints or landmark.frame not in self.canonical_frames:
                fail('UNKNOWN_ID', 'Landmark joint/frame is unavailable')
        for control in self.controls:
            if not set(control.frames) <= set(self.canonical_frames):
                fail('INVALID_PARAMETER', 'Control uses an unavailable frame', control_id=control.id)
            if control.capability not in self.capabilities:
                fail('MISSING_CAPABILITY', 'Control capability is unavailable', control_id=control.id)
        for limit in self.joint_limits:
            if limit.control_id not in controls or controls[limit.control_id].value_shape != 'scalar':
                fail('UNKNOWN_ID', 'Joint limit must reference a scalar control')
            if limit.mirror_control_id is not None and limit.mirror_control_id not in controls:
                fail('UNKNOWN_ID', 'Mirror control is unavailable')


@dataclass(frozen=True)
class ContactAnchor(Record):
    anchor_id: ID
    surface_id: ID
    position: Vector3
    frame: Frame
    unit: Literal['metre']

    def _validate(self): position_budget(self.position,self.frame,self.unit)


@dataclass(frozen=True)
class MotionStateSnapshot(Record):
    avatar_id: ID
    profile_version: Version
    revision: Version
    captured_time_s: Annotated[float, Rule(minimum=0)]
    root_transform: Transform
    measured_controls: Annotated[tuple[ControlValue, ...], Rule(max_length=1024)]
    contact_anchors: Annotated[tuple[ContactAnchor, ...], Rule(max_length=MAX_CONTACTS)]
    active_contacts: IDs
    velocities: Annotated[tuple[ControlValue, ...], Rule(max_length=1024)] | None = None
    phase: Annotated[float, Rule(minimum=0, maximum=1)] | None = None

    def _validate(self):
        if self.root_transform.frame != 'world': fail('INVALID_PARAMETER', 'Root snapshot must be world-framed')
        distinct(self.measured_controls, 'control_id')
        distinct(self.contact_anchors, 'anchor_id')
        distinct(self.active_contacts, None)
        if not set(self.active_contacts) <= {a.anchor_id for a in self.contact_anchors}:
            fail('ENTRY_MISMATCH', 'An active contact needs a captured anchor')
        if self.velocities is not None: distinct(self.velocities, 'control_id')


@dataclass(frozen=True)
class StateRequirement(Record):
    requirement_id: ID
    target: ControlValue
    tolerance: Annotated[float, Rule(minimum=0)]


@dataclass(frozen=True)
class SupportRequirement(Record):
    anchor_id: ID
    surface_id: ID
    mode: Literal['available', 'active', 'inactive']


@dataclass(frozen=True)
class MovementDefinition(Record):
    id: ID
    version: Version
    kind: Literal['joint', 'limb', 'body', 'pattern', 'operator', 'style', 'recipe', 'clip']
    description: Text
    parameter_specs: Annotated[tuple[ParameterSpec, ...], Rule(max_length=MAX_PARAMETERS)]
    required_capabilities: IDs
    entry_conditions: Annotated[tuple[StateRequirement, ...], Rule(max_length=64)]
    owned_chains: IDs
    contact_requirements: Annotated[tuple[SupportRequirement, ...], Rule(max_length=64)]
    exit_expectations: Annotated[tuple[StateRequirement, ...], Rule(max_length=64)]
    builder_id: ID
    semantic_tags: IDs
    phase_events: IDs = ()
    return_policy: Literal['preserve_end', 'return_to_entry', 'return_to_named_neutral'] = 'preserve_end'
    named_neutral: ID | None = None

    def _validate(self):
        distinct(self.parameter_specs, 'name')
        for values in (self.required_capabilities,self.owned_chains,self.semantic_tags,self.phase_events): distinct(values,None)
        for values in (self.entry_conditions,self.exit_expectations): distinct(values,'requirement_id')
        if (self.return_policy == 'return_to_named_neutral') != (self.named_neutral is not None):
            fail('INVALID_PARAMETER', 'Named-neutral policy requires a named neutral')


@dataclass(frozen=True)
class MovementInstance(Record):
    instance_id: ID
    definition_id: ID
    definition_version: Version
    parameters: Annotated[tuple[ParameterValue, ...], Rule(max_length=MAX_PARAMETERS)]
    clause_ids: IDs
    explicit_parameters: IDs | None = None

    def _validate(self):
        distinct(self.parameters,'name')
        distinct(self.clause_ids,None)
        if self.explicit_parameters is not None:
            distinct(self.explicit_parameters,None)
            if not set(self.explicit_parameters) <= {p.name for p in self.parameters}:
                fail('INVALID_PARAMETER', 'Explicit parameter names must have values')


@dataclass(frozen=True)
class VerificationRecord(Record):
    definition_id: ID
    definition_version: Version
    avatar_id: ID
    profile_version: Version
    parameter_envelope: Annotated[tuple[ParameterSpec, ...], Rule(max_length=MAX_PARAMETERS)]
    evidence: Annotated[tuple[Text, ...], Rule(min_length=1, max_length=64)]
    measured_maxima: tuple[ParameterValue, ...]
    status: Literal['reviewed_for_envelope', 'experimental', 'unavailable_on_rig']

    def _validate(self):
        distinct(self.parameter_envelope,'name')
        distinct(self.measured_maxima,'name')


@dataclass(frozen=True)
class CurveSpec(Record):
    kind: Literal['hold', 'transition']
    start_value: Value | None
    end_value: Value | None
    duration_s: Annotated[float, Rule(minimum=1e-9, maximum=MAX_SECONDS)]
    easing: Literal['linear', 'smooth'] = 'linear'

    def _validate(self):
        if self.kind == 'transition' and self.end_value is None:
            fail('INVALID_PARAMETER', 'A transition requires an explicit destination')
        if self.kind == 'hold' and self.end_value is not None and self.end_value != self.start_value:
            fail('INVALID_PARAMETER', 'A hold cannot change its value')


@dataclass(frozen=True)
class TrackSpec(Record):
    track_id: ID
    source_instance_ids: Annotated[IDs, Rule(min_length=1)]
    control_id: ID
    unit: Unit
    frame: Frame
    value_shape: Literal['scalar', 'vector', 'quaternion']
    dimensions: Annotated[int, Rule(minimum=1, maximum=16)]
    curve: CurveSpec
    start_source: Literal['explicit', 'measured_entry']
    interval: TimeInterval

    def _validate(self):
        distinct(self.source_instance_ids,None)
        if self.value_shape == 'scalar' and self.dimensions != 1 or self.value_shape == 'quaternion' and self.dimensions != 4:
            fail('INVALID_PARAMETER', 'Track shape and dimension disagree')
        if self.value_shape == 'quaternion' and self.unit != 'unitless':
            fail('INVALID_PARAMETER', 'Quaternion tracks are dimensionless')
        if abs(self.interval.end_s-self.interval.start_s-self.curve.duration_s) > 1e-9:
            fail('INVALID_PARAMETER', 'Track interval and curve duration disagree')
        if (self.start_source == 'explicit') != (self.curve.start_value is not None):
            fail('INVALID_PARAMETER', 'Start value must match explicit/measured-entry policy')
        for value in (self.curve.start_value,self.curve.end_value):
            if value is not None: validate_shape(self.value_shape,self.dimensions,value)


def validate_shape(shape, dimensions, value):
    if shape == 'scalar':
        if dimensions != 1: fail('INVALID_PARAMETER', 'Scalar shape has dimension one')
        check_type(value,float,'value')
    else:
        check_type(value,tuple[Number,...],'value')
        if len(value) != dimensions: fail('INVALID_PARAMETER', 'Missing vector coordinates')
        if shape == 'quaternion':
            if dimensions != 4: fail('INVALID_PARAMETER', 'Quaternion shape has dimension four')
            quaternion(value)


@dataclass(frozen=True)
class ContactEvent(Record):
    event_id: ID
    source_instance_ids: Annotated[IDs, Rule(min_length=1)]
    anchor_id: ID
    surface_id: ID
    interval: TimeInterval
    acquire_s: Seconds
    release_s: Seconds
    clearance_m: Annotated[float, Rule(minimum=0, maximum=.2)]

    def _validate(self):
        distinct(self.source_instance_ids,None)
        duration = self.interval.end_s-self.interval.start_s
        if duration <= 0 or self.acquire_s+self.release_s > duration:
            fail('INVALID_PARAMETER', 'Contact interval must fit its acquisition/release ramps')


@dataclass(frozen=True)
class PhaseLandmark(Record):
    name: ID
    time_s: Seconds


@dataclass(frozen=True)
class GoalSpec(Record):
    goal_id: ID
    clause_id: ID
    target: ControlValue
    interval: TimeInterval
    tolerance: Annotated[float, Rule(minimum=0)]
    locked: bool = True


@dataclass(frozen=True)
class MotionFragment(Record):
    fragment_id: ID
    source_instance_ids: Annotated[IDs, Rule(min_length=1)]
    entry_requirements: Annotated[tuple[StateRequirement, ...], Rule(max_length=64)]
    duration_s: Annotated[float, Rule(minimum=1e-9, maximum=MAX_SECONDS)]
    tracks: Annotated[tuple[TrackSpec, ...], Rule(max_length=MAX_TRACKS)]
    contact_events: Annotated[tuple[ContactEvent, ...], Rule(max_length=MAX_CONTACTS)]
    phase_landmarks: Annotated[tuple[PhaseLandmark, ...], Rule(max_length=MAX_INSTANCES)]
    exit_expectations: Annotated[tuple[StateRequirement, ...], Rule(max_length=64)]
    goals: Annotated[tuple[GoalSpec, ...], Rule(max_length=MAX_TRACKS)]

    def _validate(self):
        distinct(self.source_instance_ids,None)
        distinct(self.tracks,'track_id'); distinct(self.contact_events,'event_id')
        distinct(self.phase_landmarks,'name'); distinct(self.goals,'goal_id')
        distinct(self.entry_requirements,'requirement_id'); distinct(self.exit_expectations,'requirement_id')
        for item in (*self.tracks,*self.contact_events):
            if item.interval.end_s > self.duration_s or not set(item.source_instance_ids) <= set(self.source_instance_ids):
                fail('INVALID_PARAMETER', 'Fragment interval/provenance is inconsistent')
        if any(p.time_s > self.duration_s for p in self.phase_landmarks) or any(g.interval.end_s > self.duration_s for g in self.goals):
            fail('INVALID_PARAMETER', 'Fragment phase/goal exceeds its duration')
        for index, first in enumerate(self.tracks):
            for second in self.tracks[index+1:]:
                if first.control_id == second.control_id and overlaps(first.interval,second.interval):
                    fail('CONSTRAINT_CONFLICT', 'Overlapping tracks own the same control', control_id=first.control_id)
        for index, first in enumerate(self.contact_events):
            for second in self.contact_events[index+1:]:
                if first.anchor_id == second.anchor_id and overlaps(first.interval,second.interval):
                    fail('CONSTRAINT_CONFLICT', 'Overlapping contacts own the same anchor')


def overlaps(a,b): return max(a.start_s,b.start_s) < min(a.end_s,b.end_s)


@dataclass(frozen=True)
class Relation(Record):
    relation_id: ID
    kind: Literal['after', 'parallel', 'after_event']
    source_instance_id: ID
    target_instance_id: ID
    offset_s: Annotated[float, Rule(minimum=-MAX_SECONDS, maximum=MAX_SECONDS)]
    source_event: ID | None = None

    def _validate(self):
        if self.source_instance_id == self.target_instance_id:
            fail('CONSTRAINT_CONFLICT', 'An instance cannot depend on itself')
        if (self.kind == 'after_event') != (self.source_event is not None):
            fail('INVALID_PARAMETER', 'Only after_event has a required source landmark')


@dataclass(frozen=True)
class StyleRequest(Record):
    style_id: ID
    definition_version: Version
    parameters: Annotated[tuple[ParameterValue, ...], Rule(max_length=MAX_PARAMETERS)]
    target_instance_ids: Annotated[IDs, Rule(min_length=1)]
    clause_ids: IDs
    explicit_parameters: IDs | None = None

    def _validate(self):
        distinct(self.parameters,'name'); distinct(self.target_instance_ids,None); distinct(self.clause_ids,None)
        if self.explicit_parameters is not None:
            distinct(self.explicit_parameters,None)
            if not set(self.explicit_parameters) <= {p.name for p in self.parameters}:
                fail('INVALID_PARAMETER', 'Explicit style parameters must have values')


@dataclass(frozen=True)
class LoopSpec(Record):
    repetitions: Annotated[int, Rule(minimum=1, maximum=MAX_INSTANCES)]
    per_cycle_root_transform: Transform
    pose_tolerance_deg: Annotated[float, Rule(minimum=0, maximum=3)]
    endpoint_tolerance_m: Annotated[float, Rule(minimum=0, maximum=.01)]
    angular_velocity_tolerance_deg_s: Annotated[float, Rule(minimum=0, maximum=10)]

    def _validate(self):
        if self.per_cycle_root_transform.frame != 'entry_body':
            fail('INVALID_PARAMETER', 'Per-cycle displacement must use the fixed entry-body frame')


@dataclass(frozen=True)
class ClauseCoverage(Record):
    clause_id: ID
    source_clause: Text
    status: Literal['fulfilled', 'approximated', 'unsupported']
    source_instance_ids: IDs
    explanation: Text | None = None

    def _validate(self):
        distinct(self.source_instance_ids,None)
        if self.status != 'fulfilled' and self.explanation is None:
            fail('INVALID_PARAMETER', 'Approximation/unsupported clauses need an explanation')
        if self.status == 'fulfilled' and not self.source_instance_ids:
            fail('INVALID_PARAMETER', 'Fulfilled coverage must identify its source instances')


@dataclass(frozen=True)
class MotionRecipe(Record):
    recipe_id: ID
    avatar_id: ID
    profile_version: Version
    base_revision: Version
    operation: Literal['new', 'edit', 'append']
    instances: Annotated[tuple[MovementInstance, ...], Rule(min_length=1, max_length=MAX_INSTANCES)]
    relations: Annotated[tuple[Relation, ...], Rule(max_length=MAX_INSTANCES)]
    hard_goals: Annotated[tuple[GoalSpec, ...], Rule(max_length=MAX_TRACKS)]
    optional_styles: Annotated[tuple[StyleRequest, ...], Rule(max_length=16)]
    loop: LoopSpec | None
    clause_coverage: Annotated[tuple[ClauseCoverage, ...], Rule(min_length=1, max_length=MAX_INSTANCES)]

    def _validate(self):
        distinct(self.instances,'instance_id'); distinct(self.relations,'relation_id')
        distinct(self.hard_goals,'goal_id'); distinct(self.clause_coverage,'clause_id')
        ids = {i.instance_id for i in self.instances}
        clauses = {c.clause_id for c in self.clause_coverage}
        incoming, graph = {}, {id:[] for id in ids}
        for relation in self.relations:
            if relation.source_instance_id not in ids or relation.target_instance_id not in ids:
                fail('UNKNOWN_ID', 'Relation references an unknown instance')
            if relation.target_instance_id in incoming:
                fail('CONSTRAINT_CONFLICT', 'An instance has ambiguous multiple start constraints')
            incoming[relation.target_instance_id] = relation
            graph[relation.source_instance_id].append(relation.target_instance_id)
        visiting, visited = set(), set()
        def visit(id):
            if id in visiting: fail('CONSTRAINT_CONFLICT', 'Recipe dependency cycle')
            if id in visited: return
            visiting.add(id)
            for target in graph[id]: visit(target)
            visiting.remove(id); visited.add(id)
        for id in ids: visit(id)
        for instance in self.instances:
            if not set(instance.clause_ids) <= clauses: fail('UNKNOWN_ID', 'Instance references an unknown clause')
        for clause in self.clause_coverage:
            if not set(clause.source_instance_ids) <= ids: fail('UNKNOWN_ID', 'Clause references an unknown instance')
        for goal in self.hard_goals:
            if goal.clause_id not in clauses: fail('UNKNOWN_ID', 'Goal references an unknown clause')
        for style in self.optional_styles:
            if not set(style.target_instance_ids) <= ids or not set(style.clause_ids) <= clauses:
                fail('UNKNOWN_ID', 'Style scope references an unknown instance/clause')
        if self.loop is not None and len(ids)*self.loop.repetitions > MAX_INSTANCES:
            fail('RESOURCE_LIMIT', 'Repeated instance expansion exceeds its budget')


@dataclass(frozen=True)
class InstancePatch(Record):
    instance_id: ID
    parameters: Annotated[tuple[ParameterValue, ...], Rule(max_length=MAX_PARAMETERS)]

    def _validate(self): distinct(self.parameters,'name')


@dataclass(frozen=True)
class RecipePatch(Record):
    recipe_id: ID
    base_revision: Version
    instance_changes: Annotated[tuple[InstancePatch, ...], Rule(min_length=1, max_length=MAX_INSTANCES)]
    locked_goal_ids: IDs

    def _validate(self): distinct(self.instance_changes,'instance_id'); distinct(self.locked_goal_ids,None)


@dataclass(frozen=True)
class ScheduledInstance(Record):
    instance_id: ID
    interval: TimeInterval


@dataclass(frozen=True)
class ChainOwnership(Record):
    chain_id: ID
    source_instance_ids: Annotated[IDs, Rule(min_length=1)]
    interval: TimeInterval

    def _validate(self): distinct(self.source_instance_ids,None)


@dataclass(frozen=True)
class ParameterBinding(Record):
    instance_id: ID
    parameter_name: ID
    source: Literal['explicit', 'measured_exit']
    value: ParameterData
    predecessor_id: ID | None = None

    def _validate(self):
        if self.source == 'measured_exit' and (self.predecessor_id is None or self.value is not None):
            fail('INVALID_PARAMETER', 'Measured-exit binding needs a predecessor, not a fabricated value')
        if self.source == 'explicit' and self.predecessor_id is not None:
            fail('INVALID_PARAMETER', 'Explicit binding cannot have a predecessor')


@dataclass(frozen=True)
class SourceMapEntry(Record):
    output_id: ID
    source_instance_ids: Annotated[IDs, Rule(min_length=1)]
    clause_ids: IDs

    def _validate(self): distinct(self.source_instance_ids,None); distinct(self.clause_ids,None)


@dataclass(frozen=True)
class ResolvedRecipe(Record):
    recipe: MotionRecipe
    scheduled_instances: Annotated[tuple[ScheduledInstance, ...], Rule(max_length=MAX_INSTANCES)]
    ownership: Annotated[tuple[ChainOwnership, ...], Rule(max_length=MAX_TRACKS)]
    transitions: Annotated[tuple[MovementInstance, ...], Rule(max_length=MAX_INSTANCES)]
    merged_contacts: Annotated[tuple[ContactEvent, ...], Rule(max_length=MAX_CONTACTS)]
    parameter_bindings: Annotated[tuple[ParameterBinding, ...], Rule(max_length=MAX_INSTANCES*MAX_PARAMETERS)]
    source_map: Annotated[tuple[SourceMapEntry, ...], Rule(max_length=MAX_TRACKS+MAX_CONTACTS)]

    def _validate(self):
        distinct(self.scheduled_instances,'instance_id'); distinct(self.transitions,'instance_id')
        distinct(self.source_map,'output_id')
        distinct((*self.recipe.instances,*self.transitions),'instance_id')
        distinct(self.merged_contacts,'event_id')
        ids = {i.instance_id for i in (*self.recipe.instances,*self.transitions)}
        if len(ids) > MAX_INSTANCES: fail('RESOURCE_LIMIT', 'Transition expansion exceeds instance budget')
        if {s.instance_id for s in self.scheduled_instances} != ids:
            fail('UNKNOWN_ID', 'Resolved schedule must cover every instance/transition')
        for entry in (*self.ownership,*self.merged_contacts,*self.source_map):
            if not set(entry.source_instance_ids) <= ids: fail('UNKNOWN_ID', 'Resolved provenance references unknown instances')
        clauses = {c.clause_id for c in self.recipe.clause_coverage}
        for entry in self.source_map:
            if not set(entry.clause_ids) <= clauses: fail('UNKNOWN_ID', 'Source map references unknown clauses')
        for transition in self.transitions:
            if not set(transition.clause_ids) <= clauses: fail('UNKNOWN_ID', 'Transition references unknown clauses')
        duration = max(s.interval.end_s for s in self.scheduled_instances)
        if any(e.interval.end_s > duration for e in (*self.ownership,*self.merged_contacts)):
            fail('INVALID_PARAMETER', 'Resolved ownership/contact exceeds scheduled duration')
        distinct(tuple((b.instance_id,b.parameter_name) for b in self.parameter_bindings),None)
        for binding in self.parameter_bindings:
            if binding.instance_id not in ids or binding.predecessor_id is not None and binding.predecessor_id not in ids:
                fail('UNKNOWN_ID', 'Parameter binding references an unknown instance')
        for index, first in enumerate(self.ownership):
            for second in self.ownership[index+1:]:
                if first.chain_id == second.chain_id and overlaps(first.interval,second.interval):
                    fail('CONSTRAINT_CONFLICT', 'Overlapping chain ownership must be one explicit decision')


@dataclass(frozen=True)
class RuntimeEntryBinding(Record):
    track_id: ID
    source_instance_id: ID
    activation_s: Seconds
    predecessor_id: ID | None


@dataclass(frozen=True)
class ExecutableMotion(Record):
    entry_snapshot: MotionStateSnapshot
    duration_s: Annotated[float, Rule(minimum=1e-9, maximum=MAX_SECONDS)]
    fps: Literal[30]
    tracks: Annotated[tuple[TrackSpec, ...], Rule(max_length=MAX_TRACKS)]
    contact_events: Annotated[tuple[ContactEvent, ...], Rule(max_length=MAX_CONTACTS)]
    runtime_entry_bindings: Annotated[tuple[RuntimeEntryBinding, ...], Rule(max_length=MAX_TRACKS)]
    source_map: Annotated[tuple[SourceMapEntry, ...], Rule(max_length=MAX_TRACKS+MAX_CONTACTS)]
    loop: LoopSpec | None
    goal_checks: Annotated[tuple[GoalSpec, ...], Rule(max_length=MAX_TRACKS)]

    def _validate(self):
        distinct(self.tracks,'track_id'); distinct(self.contact_events,'event_id'); distinct(self.source_map,'output_id')
        if math.ceil(self.duration_s*self.fps)+1 > MAX_SAMPLES: fail('RESOURCE_LIMIT', 'Sample budget exceeded')
        for item in (*self.tracks,*self.contact_events):
            if item.interval.end_s > self.duration_s: fail('INVALID_PARAMETER', 'Executable interval exceeds duration')
        track_ids = {t.track_id for t in self.tracks}
        by_track = {t.track_id:t for t in self.tracks}
        distinct(self.goal_checks,'goal_id')
        if any(g.interval.end_s > self.duration_s for g in self.goal_checks):
            fail('INVALID_PARAMETER', 'Executable goal exceeds duration')
        distinct(self.runtime_entry_bindings,'track_id')
        if any(b.track_id not in track_ids or b.activation_s > self.duration_s for b in self.runtime_entry_bindings):
            fail('UNKNOWN_ID', 'Entry binding references an unavailable track/time')
        required = {t.track_id for t in self.tracks if t.start_source == 'measured_entry'}
        if {b.track_id for b in self.runtime_entry_bindings} != required:
            fail('ENTRY_MISMATCH', 'Every measured-entry track needs exactly one runtime binding')
        for binding in self.runtime_entry_bindings:
            track = by_track[binding.track_id]
            if binding.source_instance_id not in track.source_instance_ids or binding.activation_s != track.interval.start_s:
                fail('ENTRY_MISMATCH', 'Runtime binding must match its track source and activation')
        outputs = track_ids | {e.event_id for e in self.contact_events} | {g.goal_id for g in self.goal_checks}
        sources = {s for t in (*self.tracks,*self.contact_events) for s in t.source_instance_ids}
        if len(sources) > MAX_INSTANCES: fail('RESOURCE_LIMIT', 'Executable provenance exceeds instance budget')
        for entry in self.source_map:
            if entry.output_id not in outputs or not set(entry.source_instance_ids) <= sources:
                fail('UNKNOWN_ID', 'Executable source map references an unknown output/instance')
        if any(b.predecessor_id is not None and b.predecessor_id not in sources for b in self.runtime_entry_bindings):
            fail('UNKNOWN_ID', 'Runtime entry predecessor is unavailable')
        for index, first in enumerate(self.tracks):
            for second in self.tracks[index+1:]:
                if first.control_id == second.control_id and overlaps(first.interval,second.interval):
                    fail('CONSTRAINT_CONFLICT', 'Executable tracks overlap on a control',control_id=first.control_id)
        for index, first in enumerate(self.contact_events):
            for second in self.contact_events[index+1:]:
                if first.anchor_id == second.anchor_id and overlaps(first.interval,second.interval):
                    fail('CONSTRAINT_CONFLICT', 'Executable contacts overlap on an anchor')


@dataclass(frozen=True)
class FrameTargets(Record):
    time_s: Seconds
    controls: Annotated[tuple[ControlValue, ...], Rule(max_length=MAX_TRACKS)]
    active_contacts: Annotated[tuple[ContactEvent, ...], Rule(max_length=MAX_CONTACTS)]
    root_target: Transform | None
    source_instance_ids: IDs
    expected_goals: Annotated[tuple[GoalSpec, ...], Rule(max_length=MAX_TRACKS)]
    permitted_supporting_changes: IDs

    def _validate(self):
        distinct(self.controls,'control_id'); distinct(self.active_contacts,'event_id')
        distinct(self.source_instance_ids,None); distinct(self.expected_goals,'goal_id')
        distinct(self.permitted_supporting_changes,None)
        if self.root_target is not None and self.root_target.frame != 'world':
            fail('INVALID_PARAMETER', 'Sampled root target must be world-framed')
        for event in self.active_contacts:
            if not event.interval.start_s <= self.time_s <= event.interval.end_s:
                fail('INVALID_PARAMETER', 'Sampled active contact is outside its interval')


RECORD_TYPES = {name:value for name,value in tuple(globals().items())
                if isinstance(value,type) and issubclass(value,Record) and value is not Record}


def to_dict(record):
    if type(record) not in RECORD_TYPES.values(): fail('INVALID_SCHEMA', 'Unknown record type')
    def encode(value):
        if isinstance(value,Record): return {f.name:encode(getattr(value,f.name)) for f in fields(value)}
        if type(value) is tuple: return [encode(item) for item in value]
        return value
    return encode(record)


def from_dict(record_type, data):
    if record_type not in RECORD_TYPES.values(): fail('INVALID_SCHEMA', 'Unknown record type')
    def decode(annotation, value):
        origin, args = get_origin(annotation), get_args(annotation)
        if origin is Annotated:
            for rule in args[1:]:
                if rule.max_length is not None and type(value) in (list,str) and len(value) > rule.max_length:
                    fail('RESOURCE_LIMIT', 'Serialized collection exceeds its size budget')
            return decode(args[0],value)
        if origin in (Union,types.UnionType):
            errors = []
            for candidate in args:
                try:
                    decoded = decode(candidate,value)
                    check_type(decoded,candidate,'decoded')
                    return decoded
                except MotionContractError as exc: errors.append(exc)
            for exc in errors:
                if exc.code in ('RESOURCE_LIMIT','VERSION_MISMATCH'): raise exc
            fail('INVALID_SCHEMA', 'Serialized value has an invalid type')
        if origin is tuple:
            if type(value) is not list: fail('INVALID_SCHEMA', 'Serialized tuples must be arrays')
            if len(args) == 2 and args[1] is Ellipsis: return tuple(decode(args[0],item) for item in value)
            if len(value) != len(args): fail('INVALID_SCHEMA', 'Missing serialized coordinates')
            return tuple(decode(kind,item) for kind,item in zip(args,value))
        if is_dataclass(annotation) and issubclass(annotation,Record): return from_dict(annotation,value)
        check_type(value,annotation,'decoded')
        return value
    if type(data) is not dict: fail('INVALID_SCHEMA', 'A record must be a JSON object')
    names = {f.name for f in fields(record_type)}
    if set(data)-names: fail('INVALID_SCHEMA', 'Unknown serialized fields', details={'fields':sorted(set(data)-names)})
    if 'schema_version' not in data: fail('VERSION_MISMATCH', 'Saved records require an explicit schema version')
    if type(data['schema_version']) is not int or data['schema_version'] != SCHEMA_VERSION:
        fail('VERSION_MISMATCH', 'Unsupported schema version; migrate explicitly')
    if names-set(data): fail('INVALID_SCHEMA', 'Canonical saved records require every field, with null for unknown optional information',
                            details={'missing':sorted(names-set(data))})
    try:
        return record_type(**{name:decode(hints(record_type)[name],value) for name,value in data.items()})
    except TypeError as exc:
        fail('INVALID_SCHEMA', f'Incomplete {record_type.__name__} record', details={'cause':str(exc)})


def dumps(record):
    return json.dumps(to_dict(record),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def loads(record_type, text):
    if type(text) is not str: fail('INVALID_SCHEMA', 'Serialized contract must be text')
    try: size = len(text.encode('utf-8'))
    except UnicodeEncodeError: fail('INVALID_SCHEMA', 'Serialized contract must be valid UTF-8 text')
    if size > MAX_JSON_BYTES:
        fail('RESOURCE_LIMIT', 'Serialized contract exceeds its byte budget')
    def pairs(items):
        result = {}
        for key,value in items:
            if key in result: fail('INVALID_SCHEMA', 'Duplicate JSON field', details={'field':key})
            result[key] = value
        return result
    try:
        data = json.loads(text,object_pairs_hook=pairs,
            parse_constant=lambda value: fail('INVALID_SCHEMA','Nonfinite JSON number'))
    except (ValueError,RecursionError) as exc:
        if isinstance(exc,MotionContractError): raise
        fail('INVALID_SCHEMA', 'Malformed contract JSON')
    return from_dict(record_type,data)


def json_schema(record_type):
    """Generate structural Draft 2020-12 schema from the same record annotations."""
    if record_type not in RECORD_TYPES.values(): fail('INVALID_SCHEMA', 'Unknown record type')
    definitions = {}
    def schema(annotation):
        origin,args = get_origin(annotation),get_args(annotation)
        if origin is Annotated:
            result = schema(args[0])
            for rule in args[1:]:
                for source,target in (('minimum','minimum'),('maximum','maximum'),('pattern','pattern')):
                    if getattr(rule,source) is not None: result[target] = getattr(rule,source)
                for source,target in (('min_length','minItems' if get_origin(args[0]) is tuple else 'minLength'),
                                      ('max_length','maxItems' if get_origin(args[0]) is tuple else 'maxLength')):
                    if getattr(rule,source) is not None: result[target] = getattr(rule,source)
            return result
        if origin in (Union,types.UnionType): return {'anyOf':[schema(a) for a in args]}
        if origin is Literal: return {'enum':list(args)}
        if origin is tuple:
            if len(args) == 2 and args[1] is Ellipsis: return {'type':'array','items':schema(args[0])}
            return {'type':'array','prefixItems':[schema(a) for a in args], 'items':False,
                    'minItems':len(args),'maxItems':len(args)}
        if is_dataclass(annotation) and issubclass(annotation,Record):
            name = annotation.__name__
            if name not in definitions:
                definitions[name] = {}
                definitions[name] = {'type':'object','additionalProperties':False,
                    'properties':{f.name:schema(hints(annotation)[f.name]) for f in fields(annotation)},
                    'required':[f.name for f in fields(annotation)]}
            return {'$ref':'#/$defs/'+name}
        return {'type':{float:'number',int:'integer',bool:'boolean',str:'string',type(None):'null'}[annotation]}
    reference = schema(record_type)
    return {'$schema':'https://json-schema.org/draft/2020-12/schema',
            '$id':f'urn:avatar-animation:movement:v1:{record_type.__name__}', **reference, '$defs':definitions}
