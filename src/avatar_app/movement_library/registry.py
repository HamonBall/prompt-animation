"""Trusted catalog authoring and pure validation, without builder execution."""
from dataclasses import replace
from types import MappingProxyType
from .contracts import (AvatarProfile, ControlValue, MovementDefinition,
    MovementInstance, MotionFragment, MotionRecipe, MotionStateSnapshot, ParameterValue,
    RecipePatch, VerificationRecord, MotionContractError, fail, check_type, ID,
    validate_parameter, validate_shape)


class Catalog:
    def __init__(self, builders=None):
        self._builders = dict(builders or {})
        for id, builder in self._builders.items():
            check_type(id, ID, 'builder_id')
            if not callable(builder): fail('INVALID_PARAMETER', 'Trusted builder bindings must be callable')
        self._definitions = {}
        self._reviews = {}

    @property
    def definitions(self): return MappingProxyType(self._definitions)

    @property
    def reviews(self): return MappingProxyType(self._reviews)

    def builder(self, builder_id):
        if builder_id not in self._builders: fail('UNKNOWN_ID', 'Builder ID has no application-owned implementation')
        return self._builders[builder_id]

    def register_review(self, record, profile):
        if type(record) is not VerificationRecord: fail('INVALID_PARAMETER', 'Expected a verification record')
        _profile(profile)
        definition = get_movement(record.definition_id,record.definition_version,self)
        _profile_identity(record.avatar_id,record.profile_version,profile)
        specs = {p.name:p for p in definition.parameter_specs}
        if record.status == 'reviewed_for_envelope' and {p.name for p in record.parameter_envelope} != set(specs):
            fail('INVALID_PARAMETER', 'A reviewed envelope must bound every movement parameter')
        for envelope in record.parameter_envelope:
            source = specs.get(envelope.name)
            if source is None: fail('UNKNOWN_ID', 'Review names an unknown parameter')
            if replace(envelope,minimum=source.minimum,maximum=source.maximum,enum_values=source.enum_values) != source:
                fail('INVALID_PARAMETER', 'A reviewed envelope cannot redefine parameter meaning/defaults')
            if source.minimum is not None and (envelope.minimum is None or envelope.minimum < source.minimum):
                fail('INVALID_PARAMETER', 'Reviewed range exceeds definition bounds')
            if source.maximum is not None and (envelope.maximum is None or envelope.maximum > source.maximum):
                fail('INVALID_PARAMETER', 'Reviewed range exceeds definition bounds')
            if not set(envelope.enum_values) <= set(source.enum_values):
                fail('INVALID_PARAMETER', 'Reviewed choices exceed definition choices')
        key = (record.definition_id,record.definition_version,record.avatar_id,record.profile_version)
        if key in self._reviews: fail('CONSTRAINT_CONFLICT', 'Review key already exists')
        self._reviews[key] = record
        return record


# No movement/capability is advertised merely because its record/schema exists.
CATALOG = Catalog()


def _catalog(catalog):
    if type(catalog) is not Catalog: fail('INVALID_PARAMETER', 'Expected a trusted movement catalog')


def _profile(profile):
    if type(profile) is not AvatarProfile: fail('INVALID_PARAMETER', 'Expected an immutable avatar profile')


def _profile_identity(avatar_id, version, profile):
    if avatar_id != profile.avatar_id:
        fail('ENTRY_MISMATCH', 'Data belongs to a different avatar', details={'expected':profile.avatar_id,'actual':avatar_id})
    if version != profile.version:
        fail('VERSION_MISMATCH', 'Avatar profile version differs; recalibrate or migrate explicitly',
             details={'expected':profile.version,'actual':version})


def register_movement(definition, catalog):
    _catalog(catalog)
    if type(definition) is not MovementDefinition: fail('INVALID_PARAMETER', 'Expected a movement definition')
    if definition.id in catalog._definitions:
        fail('CONSTRAINT_CONFLICT', 'Movement ID is already registered; replace only in a new versioned catalog')
    catalog.builder(definition.builder_id)
    catalog._definitions[definition.id] = definition
    return definition


def get_movement(id, version, catalog):
    _catalog(catalog)
    check_type(id,ID,'definition_id')
    if type(version) is not int or version < 0: fail('INVALID_PARAMETER', 'Definition version must be a nonnegative integer')
    definition = catalog._definitions.get(id)
    if definition is None: fail('UNKNOWN_ID', 'Movement ID is not registered', details={'definition_id':id})
    if definition.version != version:
        fail('VERSION_MISMATCH', 'Movement version differs; migrate explicitly',
             details={'definition_id':id,'expected':definition.version,'actual':version})
    return definition


def validate_control_value(value, profile):
    _profile(profile)
    if type(value) is not ControlValue: fail('INVALID_PARAMETER', 'Expected a framed control value')
    control = next((c for c in profile.controls if c.id == value.control_id),None)
    if control is None: fail('UNKNOWN_ID', 'Semantic control is unavailable', control_id=value.control_id)
    if value.unit != control.unit or value.frame not in control.frames:
        fail('INVALID_PARAMETER', 'Control unit/frame differs from the profile', control_id=value.control_id)
    validate_shape(control.value_shape,control.dimensions,value.value)
    limit = next((l for l in profile.joint_limits if l.control_id == value.control_id),None)
    if limit is not None and not limit.minimum <= value.value <= limit.maximum:
        fail('INVALID_PARAMETER', 'Control value exceeds this profile’s joint limits', control_id=value.control_id)
    return value


def validate_instance(instance, profile, catalog):
    _profile(profile); _catalog(catalog)
    if type(instance) is not MovementInstance: fail('INVALID_PARAMETER', 'Expected a movement instance')
    definition = get_movement(instance.definition_id,instance.definition_version,catalog)
    missing = set(definition.required_capabilities)-set(profile.capabilities)
    if missing:
        fail('MISSING_CAPABILITY', 'Avatar lacks required movement capabilities',
             instance_id=instance.instance_id,details={'missing':sorted(missing)})
    chains = {c.chain for c in profile.controls}
    if not set(definition.owned_chains) <= chains:
        fail('MISSING_CAPABILITY', 'Avatar lacks a declared owned chain',instance_id=instance.instance_id)
    provided = {p.name:p.value for p in instance.parameters}
    specs = {p.name:p for p in definition.parameter_specs}
    unknown = set(provided)-set(specs)
    if unknown: fail('INVALID_PARAMETER', 'Unknown movement parameters',instance_id=instance.instance_id,details={'parameters':sorted(unknown)})
    explicit = tuple(sorted(provided)) if instance.explicit_parameters is None else instance.explicit_parameters
    resolved = {}
    for name, spec in specs.items():
        if name in provided: value = provided[name]
        elif spec.has_default: value = spec.default
        elif spec.required: fail('INVALID_PARAMETER', 'Missing required parameter',instance_id=instance.instance_id,details={'parameter':name})
        else: continue
        try:
            validate_parameter(spec,value)
            if value is not None:
                if spec.capability is not None and spec.capability not in profile.capabilities:
                    fail('MISSING_CAPABILITY', 'Parameter requires an unavailable capability', details={'capability':spec.capability})
                if spec.frame is not None and spec.frame not in profile.canonical_frames:
                    fail('INVALID_PARAMETER', 'Parameter frame is not available in this profile')
                if spec.control_id is not None:
                    validate_control_value(ControlValue(spec.control_id,spec.unit,spec.frame,value),profile)
            resolved[name] = value
        except MotionContractError as exc:
            raise MotionContractError(exc.code,str(exc),instance_id=instance.instance_id,
                                      control_id=exc.control_id,details={**exc.details,'parameter':name}) from exc
    for condition in (*definition.entry_conditions,*definition.exit_expectations):
        validate_control_value(condition.target,profile)
    anchors = {landmark.id for landmark in profile.landmarks}
    if any(c.anchor_id not in anchors for c in definition.contact_requirements):
        fail('MISSING_CAPABILITY', 'Required support anchor is unavailable',instance_id=instance.instance_id)
    return replace(instance,parameters=tuple(ParameterValue(name,value) for name,value in sorted(resolved.items())),
                   explicit_parameters=tuple(sorted(explicit)))


def validate_recipe(recipe, profile, catalog):
    _profile(profile); _catalog(catalog)
    if type(recipe) is not MotionRecipe: fail('INVALID_PARAMETER', 'Expected a motion recipe')
    _profile_identity(recipe.avatar_id,recipe.profile_version,profile)
    instances = tuple(validate_instance(i,profile,catalog) for i in recipe.instances)
    by_id = {i.instance_id:i for i in instances}
    for relation in recipe.relations:
        if relation.kind == 'after_event':
            source = by_id[relation.source_instance_id]
            definition = get_movement(source.definition_id,source.definition_version,catalog)
            if relation.source_event not in definition.phase_events:
                fail('UNKNOWN_ID', 'Relation names an undeclared source landmark',instance_id=source.instance_id)
    for goal in recipe.hard_goals: validate_control_value(goal.target,profile)
    styles = []
    for style in recipe.optional_styles:
        definition = get_movement(style.style_id,style.definition_version,catalog)
        if definition.kind != 'style': fail('INVALID_PARAMETER', 'Style request must reference a style definition')
        resolved = validate_instance(MovementInstance(style.style_id,style.style_id,definition.version,
                                          style.parameters,style.clause_ids,style.explicit_parameters),profile,catalog)
        styles.append(replace(style,parameters=resolved.parameters,explicit_parameters=resolved.explicit_parameters))
    return replace(recipe,instances=instances,optional_styles=tuple(styles))


def validate_patch(patch, recipe, profile, catalog):
    """Validate a narrow envelope; applying/recompiling it belongs to Stage 11."""
    if type(patch) is not RecipePatch or type(recipe) is not MotionRecipe:
        fail('INVALID_PARAMETER', 'Expected typed recipe and patch')
    if patch.recipe_id != recipe.recipe_id: fail('UNKNOWN_ID', 'Patch belongs to a different recipe')
    if patch.base_revision != recipe.base_revision:
        fail('STALE_REVISION', 'Patch belongs to an older result', details={'expected':recipe.base_revision,'actual':patch.base_revision})
    validate_recipe(recipe,profile,catalog)
    instances = {i.instance_id:i for i in recipe.instances}
    if not set(patch.locked_goal_ids) <= {g.goal_id for g in recipe.hard_goals}:
        fail('UNKNOWN_ID', 'Patch locks an unknown goal')
    for change in patch.instance_changes:
        if change.instance_id not in instances: fail('UNKNOWN_ID', 'Patch references an unknown instance')
        original = instances[change.instance_id]
        values = {p.name:p.value for p in original.parameters}
        values.update({p.name:p.value for p in change.parameters})
        validate_instance(replace(original,parameters=tuple(ParameterValue(k,v) for k,v in sorted(values.items())),
                                  explicit_parameters=None),profile,catalog)
    return patch


def validate_snapshot(snapshot, profile):
    _profile(profile)
    if type(snapshot) is not MotionStateSnapshot: fail('INVALID_PARAMETER', 'Expected a measured snapshot')
    _profile_identity(snapshot.avatar_id,snapshot.profile_version,profile)
    for value in snapshot.measured_controls: validate_control_value(value,profile)
    anchors = {l.id for l in profile.landmarks}
    for anchor in snapshot.contact_anchors:
        if anchor.anchor_id not in anchors: fail('MISSING_CAPABILITY', 'Measured support anchor is unavailable')
        if anchor.frame not in profile.canonical_frames: fail('INVALID_PARAMETER', 'Measured anchor uses an unavailable frame')
    for value in snapshot.velocities or ():
        control = next((c for c in profile.controls if c.id == value.control_id),None)
        if control is None: fail('UNKNOWN_ID', 'Velocity control is unavailable',control_id=value.control_id)
        if value.unit != control.unit+'_per_second' or value.frame not in control.frames:
            fail('INVALID_PARAMETER', 'Velocity needs the control’s derivative unit and frame',control_id=value.control_id)
        validate_shape(control.value_shape,control.dimensions,value.value)
    return snapshot


def validate_fragment(fragment, profile, *, resolved_surface_ids=()):
    """Check authored data only; does not sample, solve or construct an animation."""
    _profile(profile)
    if type(fragment) is not MotionFragment: fail('INVALID_PARAMETER', 'Expected a motion fragment')
    for track in fragment.tracks:
        control = next((c for c in profile.controls if c.id == track.control_id),None)
        if control is None: fail('UNKNOWN_ID', 'Track control is unavailable',control_id=track.control_id)
        if (track.value_shape,track.dimensions) != (control.value_shape,control.dimensions):
            fail('INVALID_PARAMETER', 'Track shape differs from registered control',control_id=track.control_id)
        for value in (track.curve.start_value,track.curve.end_value):
            # Even a measured-entry hold with no explicit values needs its units/frame checked.
            if track.unit != control.unit or track.frame not in control.frames:
                fail('INVALID_PARAMETER', 'Track units/frame differ from profile',control_id=track.control_id)
            if value is not None: validate_control_value(ControlValue(track.control_id,track.unit,track.frame,value),profile)
    for condition in (*fragment.entry_requirements,*fragment.exit_expectations): validate_control_value(condition.target,profile)
    for goal in fragment.goals: validate_control_value(goal.target,profile)
    anchors = {l.id for l in profile.landmarks}
    for event in fragment.contact_events:
        if event.anchor_id not in anchors: fail('MISSING_CAPABILITY', 'Contact anchor is unavailable')
        if event.surface_id not in resolved_surface_ids:
            fail('UNRESOLVED_SURFACE', 'Contact surface must resolve before execution',details={'surface_id':event.surface_id})
    return fragment


def parameter_schema(definition):
    """Planner-friendly parameter object schema generated from ParameterSpecs."""
    if type(definition) is not MovementDefinition: fail('INVALID_PARAMETER', 'Expected a movement definition')
    properties = {}
    for spec in definition.parameter_specs:
        kind = spec.type
        if kind in ('vector','quaternion'):
            value = {'type':'array','items':{'type':'number'},'minItems':spec.dimensions,'maxItems':spec.dimensions}
            bounds = value['items']
        elif kind == 'enum': value = {'type':'string','enum':list(spec.enum_values)}; bounds = value
        else: value = {'type':{'number':'number','integer':'integer','boolean':'boolean','string':'string'}[kind]}; bounds = value
        if kind in ('number','integer','vector','quaternion'):
            if spec.minimum is not None: bounds['minimum'] = spec.minimum
            if spec.maximum is not None: bounds['maximum'] = spec.maximum
        if kind == 'string': value.update(minLength=1,maxLength=2000)
        if spec.nullable: value = {'anyOf':[value,{'type':'null'}]}
        value.update({'x-unit':spec.unit,'x-frame':spec.frame,'x-capability':spec.capability,'x-control-id':spec.control_id})
        if spec.has_default: value['default'] = list(spec.default) if type(spec.default) is tuple else spec.default
        properties[spec.name] = value
    return {'type':'object','additionalProperties':False,'properties':properties,
            'required':[p.name for p in definition.parameter_specs if p.required and not p.has_default]}
