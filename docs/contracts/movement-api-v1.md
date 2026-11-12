# Implemented movement API v1

Stage 02 handoff, 2026-10-14. `SCHEMA_VERSION = 1`. The authoritative definitions are
`src/avatar_app/movement_library/contracts.py`; contextual validation and trusted
registration are in `registry.py`. This is immutable authoring and execution **data**.
The production `registry.CATALOG` now contains the five [Stage 05.1a head/neck IDs](head-neck-v1.md). The synthetic `test.*` definitions
exist only in tests and prove data validation, not motion or anatomical calibration.

## Implemented entry points

These signatures show the accepted types and return values; the Python implementations
perform runtime checks. The three primary registry functions are also exported from
`avatar_app.movement_library`.

```python
Catalog(builders: dict[str, Callable] | None = None)
catalog.definitions                 # read-only mapping: definition_id -> MovementDefinition
catalog.reviews                     # read-only mapping: (definition_id, definition_version,
                                    #                     avatar_id, profile_version) -> VerificationRecord
catalog.builder(builder_id: str) -> Callable
catalog.register_review(record: VerificationRecord, profile: AvatarProfile) -> VerificationRecord
register_movement(definition: MovementDefinition, catalog: Catalog) -> MovementDefinition
get_movement(id: str, version: int, catalog: Catalog) -> MovementDefinition
validate_instance(instance: MovementInstance, profile: AvatarProfile, catalog: Catalog) -> MovementInstance
validate_control_value(value: ControlValue, profile: AvatarProfile) -> ControlValue
validate_recipe(recipe: MotionRecipe, profile: AvatarProfile, catalog: Catalog) -> MotionRecipe
validate_patch(patch: RecipePatch, recipe: MotionRecipe, profile: AvatarProfile, catalog: Catalog) -> RecipePatch
validate_snapshot(snapshot: MotionStateSnapshot, profile: AvatarProfile) -> MotionStateSnapshot
validate_fragment(fragment: MotionFragment, profile: AvatarProfile, *, resolved_surface_ids=()) -> MotionFragment
parameter_schema(definition: MovementDefinition) -> dict
```

`Catalog` copies the supplied application-owned callable bindings. Registration rejects
duplicate definition IDs, including attempts to register another version under an existing
ID. A new version requires a new catalog snapshot. Lookup requires the exact version;
there is no implicit latest-version fallback. Registration and validation never call a
builder. A serialized builder ID cannot import code, evaluate an expression, or create a
scene. Failed registration and review validation leave their catalog mappings unchanged.

`validate_instance` checks required capabilities, owned chains, support anchors, parameters,
frames, linked controls and the profile's joint limits. It returns a new immutable instance
with resolved parameters in name order. `validate_recipe` applies this resolution to
instances and styles and checks declared source landmarks. These functions do not schedule
relations or decide whether the requested motion can physically achieve a goal.

`validate_patch` validates the narrow parameter changes against the existing instances,
recipe revision and lock IDs. It returns the envelope without applying it. Semantic goal
preservation, recomposition and application belong to Stage 11.

Codec functions, available from `contracts`:

```python
to_dict(record: Record) -> dict
from_dict(record_type: type[Record], data: dict) -> Record
dumps(record: Record) -> str
loads(record_type: type[Record], text: str) -> Record
json_schema(record_type: type[Record]) -> dict  # generated JSON Schema Draft 2020-12
```

## Common types and persistence

Every record is a frozen dataclass. Python constructors require tuples, not mutable lists,
for collections and coordinates. JSON arrays decode into new tuples, so editing the input
object after decoding cannot alter a saved record. `dataclasses.replace` creates a new,
validated record. Blender handles, callables and arbitrary Python objects are not values.

Every record, including nested records, has keyword-only `schema_version=1`. Canonical
saved objects include **all original fields**, including Python defaults and nulls. The
explicitly versioned optional [look_at_world_v1 curve extension](head-neck-v1.md) is omitted
when unused, preserving original v1 records. Decoding rejects other
missing fields, unknown fields, duplicate JSON keys and unsupported versions. Numeric
versions/revisions are nonnegative integers; booleans are rejected. There is no migration
in v1. A future extension must use an explicit version/migration instead of silently
changing the meaning of a saved curve, frame, unit or definition.

`dumps` sorts object keys, uses compact separators, emits UTF-8-compatible text and forbids
NaN/Infinity. Array order is preserved because instance, relation and provenance order can
matter. Repeated serialization of the same record is identical; validated instances and
styles sort their parameters and explicit parameter names. Constructors and the decoder
reject nonfinite numbers, numeric booleans, incomplete vectors and malformed quaternions.

The common types are:

| Type | Meaning |
| --- | --- |
| `ID` | ASCII `[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}`; stable record/control/provenance identifier |
| `Text` | Nonempty UTF-8-compatible string, at most 2,000 characters |
| `Number` | Finite float or integer, excluding booleans |
| `Value` | `Number` or immutable numeric tuple of 1–16 components |
| `ParameterData` | `Value`, string, boolean or null; a ParameterSpec further restricts its meaning |
| `Vector3` | Exactly three finite numbers |
| `Quaternion` | Exactly four numbers `[w,x,y,z]`, normalized within `1e-6` in squared norm |
| `Seconds` | Finite number in `[0,60]`; duration-bearing curves/fragments/executables must be positive |
| `TimeInterval` | Start/end seconds with `end_s >= start_s`; track/contact intervals must have positive duration |

The frame enum is `world`, `entry_body`, `current_root`, `current_torso`, `current_pelvis`,
`joint:<semantic_id>`, or `surface:<surface_id>`. Joint/surface suffixes use ASCII letters,
digits, underscore, dot or hyphen, starting with a letter/digit, up to 96 characters.
Unknown frame syntax fails immediately; a syntactically valid frame must also be available
in the profile/control. `entry_body` is the fixed body frame measured at motion entry;
the `current_*` frames follow their measured segment. Stage 03 supplies actual frame and
anatomical calibration; Stage 04 supplies frame conversion during execution.

Units are `degree`, `metre`, `avatar_height`, `second`, `unitless`,
`degree_per_second`, `metre_per_second`, `avatar_height_per_second`.
Positions/translations use explicit coordinates; rotations use degrees or dimensionless
active quaternions. Snapshot velocity units must equal the control's unit plus
`_per_second`, with matching frame and shape. A missing measured velocity or phase remains
null and is never invented as zero. Quaternion velocity is not represented by v1.

## Exact record fields

Each row lists every field other than the common `schema_version`. Exact types, literal
enums, lengths and field bounds are generated in
`tests/fixtures/movement_contracts/v1/schemas/<RecordName>.json`. The Python contracts
also enforce semantic cross-field rules that JSON Schema alone cannot express.

| Record | Fields |
| --- | --- |
| ParameterSpec | name, type, unit, frame, required, has_default, default, minimum, maximum, enum_values, dimensions, capability, nullable, control_id |
| ParameterValue | name, value |
| ControlSpec | id, unit, value_shape, dimensions, frames, chain, capability |
| ControlValue | control_id, unit, frame, value |
| TimeInterval | start_s, end_s |
| Transform | position, orientation, frame, unit |
| JointMapping | semantic_id, parent_id, source_bones, rest_to_semantic |
| LengthSpec | id, value_m |
| Landmark | id, joint_id, position, frame, unit |
| JointLimit | control_id, minimum, maximum, zero, positive_axis, mirror_control_id, mirror_sign, measurement_method, preferred_minimum, preferred_maximum |
| Provenance | method, source_revision, evidence, recorded_at |
| AvatarProfile | avatar_id, version, height_m, canonical_frames, rest_to_semantic_mappings, lengths, landmarks, joint_limits, controls, capabilities, calibration_provenance |
| ContactAnchor | anchor_id, surface_id, position, frame, unit |
| MotionStateSnapshot | avatar_id, profile_version, revision, captured_time_s, root_transform, measured_controls, contact_anchors, active_contacts, velocities, phase |
| StateRequirement | requirement_id, target, tolerance |
| SupportRequirement | anchor_id, surface_id, mode |
| MovementDefinition | id, version, kind, description, parameter_specs, required_capabilities, entry_conditions, owned_chains, contact_requirements, exit_expectations, builder_id, semantic_tags, phase_events, return_policy, named_neutral |
| MovementInstance | instance_id, definition_id, definition_version, parameters, clause_ids, explicit_parameters |
| VerificationRecord | definition_id, definition_version, avatar_id, profile_version, parameter_envelope, evidence, measured_maxima, status |
| CurveSpec | kind, start_value, end_value, duration_s, easing |
| TrackSpec | track_id, source_instance_ids, control_id, unit, frame, value_shape, dimensions, curve, start_source, interval |
| ContactEvent | event_id, source_instance_ids, anchor_id, surface_id, interval, acquire_s, release_s, clearance_m |
| PhaseLandmark | name, time_s |
| GoalSpec | goal_id, clause_id, target, interval, tolerance, locked |
| MotionFragment | fragment_id, source_instance_ids, entry_requirements, duration_s, tracks, contact_events, phase_landmarks, exit_expectations, goals |
| Relation | relation_id, kind, source_instance_id, target_instance_id, offset_s, source_event |
| StyleRequest | style_id, definition_version, parameters, target_instance_ids, clause_ids, explicit_parameters |
| LoopSpec | repetitions, per_cycle_root_transform, pose_tolerance_deg, endpoint_tolerance_m, angular_velocity_tolerance_deg_s |
| ClauseCoverage | clause_id, source_clause, status, source_instance_ids, explanation |
| MotionRecipe | recipe_id, avatar_id, profile_version, base_revision, operation, instances, relations, hard_goals, optional_styles, loop, clause_coverage |
| InstancePatch | instance_id, parameters |
| RecipePatch | recipe_id, base_revision, instance_changes, locked_goal_ids |
| ScheduledInstance | instance_id, interval |
| ChainOwnership | chain_id, source_instance_ids, interval |
| ParameterBinding | instance_id, parameter_name, source, value, predecessor_id |
| SourceMapEntry | output_id, source_instance_ids, clause_ids |
| ResolvedRecipe | recipe, scheduled_instances, ownership, transitions, merged_contacts, parameter_bindings, source_map |
| RuntimeEntryBinding | track_id, source_instance_id, activation_s, predecessor_id |
| ExecutableMotion | entry_snapshot, duration_s, fps, tracks, contact_events, runtime_entry_bindings, source_map, loop, goal_checks |
| FrameTargets | time_s, controls, active_contacts, root_target, source_instance_ids, expected_goals, permitted_supporting_changes |

Python constructor defaults, all explicitly saved by the codec:

| Record | Defaults |
| --- | --- |
| ParameterSpec | minimum/maximum/dimensions/capability/control_id=None; enum_values=(); nullable=False |
| JointLimit | preferred_minimum=None; preferred_maximum=None |
| MotionStateSnapshot | velocities=None; phase=None |
| MovementDefinition | phase_events=(); return_policy='preserve_end'; named_neutral=None |
| MovementInstance, StyleRequest | explicit_parameters=None |
| CurveSpec | easing='linear' |
| GoalSpec | locked=True |
| Relation | source_event=None |
| ClauseCoverage | explanation=None |

All other fields must be supplied. The codec requires the above defaults to be present
in serialized input as well. Constructors do not fill omitted parameters: only
`validate_instance`/`validate_recipe` do that from the registered ParameterSpecs.

## Parameters, calibration and review envelopes

Parameter type is `number`, `integer`, `boolean`, `string`, `enum`, `vector` or `quaternion`.
Numeric bounds are inclusive and apply to vector components. Spatial parameters require
a frame and a fixed dimension; quaternion dimension is four. Scalar parameters cannot
declare dimensions. Enum choices must be nonempty and unique. `minimum <= maximum`.
`has_default=False` requires `default=None`; `has_default=True` validates the default just
like an explicit value. Nullable parameters permit null only when `nullable=True`.

Missing required parameters without defaults fail. Omitted optional parameters without
defaults stay omitted, preserving the future measured entry control. Explicit zero stays
zero. `explicit_parameters=None` identifies an unresolved authored instance/style;
validation captures its supplied names and keeps that provenance on subsequent validation
and serialization. Defaulted values are not marked explicit. A control-linked parameter
also declares `control_id` and frame; validation checks its units, shape and calibrated
joint limits. No raw Blender bone names come from the model.

Profile controls carry named semantic IDs, shape (`scalar`, `vector`, `quaternion`), fixed
dimensions, allowed frames, chain and capability. Scalar dimension is one; quaternion
dimension is four with `unitless` units. Joint limits apply to scalar controls, require a
normalized positive axis, bounded zero and optional paired preferred limits. Parent
references must exist and the semantic hierarchy must be acyclic. `source_bones` contains
bounded names from a trusted rig adapter, including names with spaces; these are plain
data, not IDs executable by the registry. The synthetic profile is not calibration of
the procedural or imported avatar.

Verification records are separate from definitions and keyed by definition ID/version,
avatar ID and profile version. Status is `reviewed_for_envelope`, `experimental` or
`unavailable_on_rig`. Evidence is required. Envelopes can narrow numeric ranges or enum
choices but cannot redefine units, defaults, frames, type or capability. A reviewed
envelope must specify every parameter. This metadata does not produce motion evidence;
later movement stages must supply actual measurements and review before advertising it.

## Curves, contacts, recipes and execution data

Curve kind is `hold` or `transition`, with positive `duration_s`, `start_value`, `end_value`
and easing `linear` or `smooth`. A transition requires an explicit end. A hold's end is
null or equal to its start. Track `start_source` is `explicit` exactly when its start
value is present; otherwise it is `measured_entry`. A measured hold has both values null.
This preserves the value actually measured at activation instead of fabricating neutral.
Track shape and interval duration must agree with its curve.

The handoff meaning of `smooth` is cubic smoothstep `3u²-2u³`; scalar/vector interpolation
uses the eased fraction and quaternion transitions use normalized shortest-arc spherical
interpolation. Sampling is Stage 04 work. Root trajectories may use future registered
root controls with these typed tracks; additional curve kinds/trajectory payloads require
a versioned extension and are not executable placeholders in v1.

Contact events have stable IDs, source instance IDs, an anchor, resolved surface ID,
interval and nonnegative acquisition/release durations whose sum fits the positive
interval. Clearance is 0–0.2 metre. `validate_fragment` requires contact anchors available
on the profile and surfaces explicitly listed as resolved. It performs no lookup or scene
mutation. Snapshot active contacts must have captured anchors. Snapshot/root frame targets
are world-framed. Requirements and goals have explicit targets and nonnegative tolerance
in the target's unit.

Definition kind is `joint/limb/body/pattern/operator/style/recipe/clip`. Return policy is
`preserve_end/return_to_entry/return_to_named_neutral`; the last requires `named_neutral`,
and other policies forbid it. This is declared data for the future builder, not an
automatic reset. `phase_events` lists allowed `after_event` source names.

Recipe operation is `new/edit/append`. Relations are `after` (source end), `parallel`
(source start), or `after_event` (declared source landmark). Offsets are bounded to
[-60,60] seconds. Unconstrained roots will start at zero when Stage 06 schedules them.
Unknown source/target instances, self-dependency, cycles, duplicate IDs and multiple
start constraints for one target fail here. Only `after_event` has a non-null source event.
Parallel dependencies do not themselves prove disjoint control ownership; resolution is
Stage 06 work.

Clause coverage status is `fulfilled/approximated/unsupported`; the latter two require
an explanation. Fulfilled coverage requires source IDs. Clause and goal references must
exist. A `fulfilled` claim from serialized authoring data is not semantic or physical
verification. Later planners and solved-motion checks must establish actual fulfillment.
Styles reference exact definition versions, a scope of instance IDs, parameters and
clauses. Goal locks and explicit parameter markers survive serialization.

Resolved schedules cover every original/transition instance; transition IDs cannot reuse
original IDs. Ownership/contact intervals fit the resolved schedule; each overlapping
chain has one explicit ownership decision, potentially naming several cooperating sources.
Bindings use `explicit` or `measured_exit`; a measured-exit binding carries a predecessor
ID and null value. Source maps carry stable output, instance and clause IDs.

Executable records require exactly one runtime binding for each measured-entry track,
matching that track's source and activation time. All intervals/goals fit the duration;
conflicting simultaneous tracks/contacts and invalid source-map references fail. V1
defines these records but does not prepare, sample, compile, execute or measure them.
FrameTargets contains one frame's data; active contacts must include its sample time.
Future execution cursors must bind actual measured state without mutating these records.

LoopSpec declares finite repetitions and a per-cycle root transform in `entry_body`.
Initial seam tolerance maxima are 3 degrees, 0.01 metre and 10 degrees/second. Declared
tolerances do not certify a seam; motion/contact/root-displacement checks belong to later
stages. The executable duration describes the complete bounded timeline, including any
compiled repetitions.

## Bounds and errors

Shared bounds: 60 seconds, 30 fps, at most 1,801 samples, 128 expanded instances, 256 tracks,
256 contacts, 64 parameters per movement, 16 styles and 1,000,000 bytes of input JSON.
Each transform translation and each world/surface position in metres lies within a
20-metre radius. A quaternion or vector has fixed dimensions; other `Value` tuples are
limited to 16 components. Profile limits are 256 joint mappings/lengths/landmarks and
1,024 controls/joint limits/capabilities/frames. Additional collection limits are emitted
by each generated schema. Existing ActionPlan remains a separate representation with its
12-stage limit and unchanged behavior. No legacy adapter is required at this stage.

`MotionContractError` subclasses `PlanError` and has `code`, message (`str(error)`),
optional `instance_id`/`control_id`, and `details`. `to_dict()` emits those five fields.
Instance parameter errors include the parameter name and instance ID. Syntax/type
validation takes place before any scene work; catalog validation does not import bpy.

| Code | Use |
| --- | --- |
| UNKNOWN_ID | Missing definition, semantic control, relation source, landmark, patch target or binding reference |
| VERSION_MISMATCH | Unsupported schema version or differing definition/profile version; explicit migration required |
| INVALID_PARAMETER | Wrong type/enum/frame/units, nonfinite value, bounds, coordinates, quaternion or malformed field meaning |
| MISSING_CAPABILITY | Missing capability, owned chain or support anchor |
| ENTRY_MISMATCH | Wrong avatar identity, missing captured contact or inconsistent runtime entry binding |
| CONSTRAINT_CONFLICT | Duplicate IDs, dependency cycles, ambiguous starts or overlapping control/contact/chain ownership |
| UNRESOLVED_SURFACE | Fragment contact surface has not resolved |
| RESOURCE_LIMIT | Collection/JSON/sample/instance-expansion/position budget exceeded |
| STALE_REVISION | Patch base revision differs from the current recipe |
| INVALID_SCHEMA | Malformed JSON, unknown/missing fields, duplicate JSON keys or invalid serialized structure |
| UNSUPPORTED_GOAL | Reserved structured planner rejection, distinct from malformed data; no planner is implemented here |

Field-level range rejection uses INVALID_PARAMETER; collection/expansion/workspace budgets
use RESOURCE_LIMIT. JSON NaN/Infinity tokens fail as INVALID_SCHEMA. A valid JSON numeric
literal that overflows to infinity still fails numeric validation. Constructor unknown
keyword arguments follow normal Python TypeError; untrusted data uses the strict codec.

## Executable fixtures and next consumers

Generate with the local Python runtime and `PYTHONPATH=src`:

```powershell
& $stagePython tests/movement_contract_fixtures.py
& $stagePython -m unittest discover -s tests -p 'test_movement_contracts.py' -v
```

The generator authors test data as Python records and derives every schema from their
annotations/ParameterSpecs. The tests compare all generated files with the saved handoff,
load and validate every valid/invalid fixture, and verify deterministic round trips.

- `tests/fixtures/movement_contracts/v1/manifest.json`: 15 valid and 20 invalid cases.
- `valid/sequential-recipe.json`: two stable instances, an `after` relation, explicit
  angle zero, a measured goal with its lock and source clauses.
- `valid/parallel-recipe.json`: separate head/hand controls and a 0.25-second parallel offset.
- `valid/narrow-patch.json`: changes only `turn.2.angle`, references revision 7 and locks `goal.1`.
- Other valid files cover the synthetic profile/definitions, snapshot, fragment, review
  envelope, resolved/executable/frame data and a versioned style/finite loop.
- Invalid cases include unknown IDs/parameters, numeric booleans, bad types/ranges,
  unknown/unavailable frames, missing coordinates, duplicate instances/parameters,
  incompatible schema/definition/profile versions, stale patches and nonfinite JSON.
- `schemas/`: 40 record schemas and 3 test-definition parameter schemas.

The nonfinite fixture deliberately contains invalid JSON `NaN` to exercise parser rejection.
These fixtures are executable validation inputs, not Blender animations or production moves.

Initial contract additions resolving the proposed handoff are: recipe avatar/profile
identity; profile controls/height; ParameterSpec dimensions/nullability/control linkage;
definition phase/return policy; instance/style explicit-parameter provenance and style
definition version; finite LoopSpec; typed patch/binding/source records; common schema
versions on every record. This is the first implemented v1: there are no saved older
library recipes to migrate. Existing callers continue to use pose.py/motion.py.

Stage 03 has published actual rig calibration as AvatarProfile data. Stage 04 has now
implemented `instantiate_movement`, `build_fragment`, `prepare_fragment` and `sample_motion`;
see [the execution handoff](fragment-execution-v1.md) for the tested bridge and exact APIs.
Stage 06 supplies scheduling/ownership resolution, Stage 07 compilation, and Stage 11
patch application. They must consume these records and fixtures, extending versions
explicitly if a necessary change alters serialized semantics. No following stage was
implemented as part of Stage 02.
