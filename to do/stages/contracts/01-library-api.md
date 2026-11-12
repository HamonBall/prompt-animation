# Required contract: library API and serialized data

Applies to stages 02 onward. This is the proposed v1 implementation specification, not an existing API. Stage 02 owns its initial implementation and publishes the resolved signatures/schema in docs/contracts/movement-api-v1.md. Later stages must use that artifact and compatibility tests. A necessary departure must be recorded with affected consumers and migration; silently inventing a second representation is prohibited.

## Records and required fields

All IDs are nonempty stable strings; version/revision fields are nonnegative integers, with booleans rejected. Records are immutable plain data and serialize deterministically. Unknown fields, enum values, IDs and incompatible versions fail validation. Tuples serialize as arrays; missing optional information is null, not fabricated zero.

| Record | Required contract |
| --- | --- |
| ParameterSpec | name, type, unit, frame, required, has_default, default, numeric bounds or enum, and optional capability requirement. No undeclared implicit units/defaults. |
| MovementDefinition | id, version, kind, description, parameter_specs, required_capabilities, entry_conditions, owned_chains, contact_requirements, exit_expectations, builder_id, semantic_tags. Review status belongs to a separate rig/envelope-specific verification record. |
| MovementInstance | instance_id, definition_id, definition_version, parameters, clause_ids. User timing/style overrides are validated parameters or recipe relations, never untyped extra fields. |
| MotionStateSnapshot | avatar_id, profile_version, revision, captured_time_s, root_transform, measured_controls, contact_anchors, active_contacts, optional velocities/phase. Every measured quantity includes its declared frame/unit through the control schema. |
| AvatarProfile | avatar_id, version, canonical frames, rest-to-semantic mappings, lengths/landmarks, joint limits, capabilities and calibration provenance. No bpy handles. |
| TrackSpec | track_id, source_instance_ids, control_id, unit, frame, fixed value shape, bounded curve descriptor, start_source and interval. start_source is an explicit value or measured_entry; fragment times are relative to fragment start, compiled times to timeline start. A component cannot be written by unrelated simultaneous tracks. |
| ContactEvent | event_id, source_instance_ids, part/anchor_id, surface_id, interval, acquisition/release ramps and clearance. Surface IDs resolve before execution. |
| MotionFragment | fragment_id, source_instance_ids, entry_requirements, duration_s, tracks, contact_events, phase_landmarks, exit_expectations and measured-goal specifications. One explicit authored movement result; no unresolved recipe graph. |
| MotionRecipe | schema_version, recipe_id, base_revision, operation, instances, relations, hard_goals, optional_styles, loop, clause_coverage. Operation is new/edit/append; loop is null or an explicitly validated loop specification. |
| ResolvedRecipe | recipe plus scheduled instance intervals, chain ownership decisions, transitions, merged contacts, parameter bindings and source map. It may still contain runtime bindings to the actual measured entry of a future segment. |
| ExecutableMotion | schema_version, entry_snapshot, duration_s, fps, prepared tracks/contact events, runtime entry bindings, source map, loop metadata and goal checks. It is sampled by the existing executor, not a second Blender engine. |
| FrameTargets | canonical control targets, active contacts, root target, source IDs, expected measurable goals and permitted supporting changes for the current frame. |

Definition kind is joint/limb/body/pattern/operator/style/recipe/clip. builder_id selects application-owned functions from a trusted registry; serialized data cannot name arbitrary imports or execute expressions.

Relations have relation_id, kind, source_instance_id, target_instance_id, offset_s and optional source_event. For after, target starts after source ends; for parallel, target starts relative to source start; for after_event, the named declared source landmark controls timing. Unconstrained root instances start at zero; reject ambiguous multiple start constraints or cycles. Timing parameters remain bounded by the shared guide.

Goals record goal_id, source clause, target/control, reference frame, interval and tolerance. Clause coverage uses fulfilled/approximated/unsupported with an explanation for the latter two. A syntactically valid selection is not automatically fulfilled.

## Public entry points and owning stages

- 02: register_movement(definition, catalog), get_movement(id, version, catalog), validate_instance(instance, profile, catalog) -> MovementInstance.
- 04: instantiate_movement(id, parameters, *, instance_id, profile, entry_state, catalog) -> MovementInstance.
- 04: build_fragment(instance, entry_state, profile, surfaces, catalog) -> MotionFragment.
- 04: prepare_fragment(fragment, entry_state, profile) -> ExecutableMotion.
- 04: sample_motion(executable, time_s, measured_state, execution_cursor) -> FrameTargets. The per-run cursor stores activated entry bindings; never mutate shared definitions/caches.
- 06: compose_recipe(recipe, entry_state, profile, surfaces, catalog) -> ResolvedRecipe.
- 07: compile_recipe(resolved, entry_state, profile) -> ExecutableMotion.
- 11: apply_recipe_patch(recipe, patch, base_revision) -> revised recipe plus affected-instance set.

Validation returns validated data or raises MotionContractError, a PlanError subclass carrying code, message, instance_id/control_id when applicable, and structured details. Required codes: UNKNOWN_ID, VERSION_MISMATCH, INVALID_PARAMETER, MISSING_CAPABILITY, ENTRY_MISMATCH, CONSTRAINT_CONFLICT, UNRESOLVED_SURFACE, RESOURCE_LIMIT and STALE_REVISION. Distinguish UNSUPPORTED_GOAL from invalid schema at the planner boundary. Error paths must not mutate the scene.

No public function above accepts raw Blender bone names from the model. Rig-specific mapping is an adapter responsibility.

## Defaults, persistence and migration

Omitted controls preserve the entry state. Only ParameterSpec defaults may fill omitted parameters. Explicit zero is a value, not omission; null is allowed only by the field's declared meaning. Required position targets include every coordinate and a declared frame. Applying defaults must retain which goals the user explicitly supplied.

Save schema, definition and profile versions with recipes; persist source IDs and explicit locks. Reject an unsupported version with a useful migration message. A migration must preserve semantics or report changed meaning before replacing a result.

Stage 02 must deliver schema-generated JSON fixtures: a valid two-instance sequential recipe, a parallel recipe, a narrow patch envelope, and invalid cases covering duplicate IDs, missing coordinates, version mismatch and invalid numbers. Tests must load the fixtures, validate and round-trip them. The definition/serializer is authoritative; examples must be generated from it rather than become a manually divergent schema.

## Downstream completion handoff

Publish exact runtime signatures, resolved defaults and executable fixture paths in the stage-02 receipt. Stage 03 fills actual rig calibration values; stage 04 demonstrates execution of the contract; stage 07 adds general recipe compilation without replacing these records with an incompatible second family.
