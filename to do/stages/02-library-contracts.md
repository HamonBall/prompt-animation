# Stage 02 — Define the movement catalog and data contracts

Status: **complete** (2026-10-14). See [receipt](receipts/02.md) and [implemented API v1](../../docs/contracts/movement-api-v1.md). Dependencies: [01](01-cleanup.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Give every following stage one stable, Blender-independent contract. Separate movement definitions, instantiated movements, curves, recipes and measured entry state. Register capabilities only when their execution path exists.

**Permitted changes:** New src/avatar_app/movement_library/{__init__,contracts,registry}.py; focused contract tests; documentation of public types. Minimal adapters to existing plan types.

## Execution

1. Define immutable MovementDefinition, MovementInstance, MotionFragment, MotionRecipe, MotionStateSnapshot and AvatarProfile records. Definitions carry stable ID/version, required capabilities, parameters with units/frames/defaults/ranges, owned chains, contact requirements, entry/exit conditions. Store reviewed parameter envelopes separately by definition version, rig/profile and verification evidence.
2. Define named semantic controls and a typed curve descriptor: hold/transition plus start/end values, duration and explicit frame. Contact intervals and entry/exit requirements are plain data. Reserve root trajectories and later curve kinds through a versioned extension point; do not create placeholder executable capabilities.
3. Implement register_movement(), get_movement(), validate_instance() and deterministic serialization. Reject duplicate IDs, unknown parameters/IDs/frames, nonfinite values, booleans used as numbers and missing capabilities. Registry metadata supplies future planner schemas.
4. Define stable instance IDs, sequential/parallel dependency relations, requested clause IDs and source-instance mappings in MotionRecipe. No Blender objects or filesystem-loaded executable expressions may cross these contracts.
5. Record initial resource bounds from 00-START-HERE.md. Keep the existing ActionPlan representation compatible; the library contract does not itself remove its 12-stage limit.

## Required outputs and handoff

Follow [the v1 API contract](contracts/01-library-api.md). Publish `docs/contracts/movement-api-v1.md`, generated schemas and executable fixtures under `tests/fixtures/movement_contracts/v1/`. Record exact implemented signatures, fields, enum values, default resolution, errors and versions. Required fixtures: sequential recipe, parallel recipe, narrow patch, and invalid ID/type/frame/version/coordinate cases. This handoff is a completion gate, not deferred design.

## Testing

- Create tests/test_movement_contracts.py for invalid types, bounds, IDs, versions, immutable updates and deterministic serialization round-trips.
- Verify a registered test-only movement can be instantiated from a synthetic profile and rejects an incompatible profile. The test fixture must not appear in the production catalog.
- Confirm importing contracts/registry requires neither bpy nor local-model startup. Run existing pose/motion data-model tests.

## Validation / completion gate

One documented source of truth exists for parameter units, target frames, capabilities and ownership. A contract test round-trips a two-instance recipe without changing IDs, timing or constraints. All rejected cases fail before scene mutation.

Write the stage-02 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No movement catalog population, AI integration, new UI, networking or solver rewrite. Do not duplicate schemas in manually maintained JSON/YAML and Python. Keep motion.py as a module; do not also create avatar_app/motion/. Later schema changes must version and migrate this contract rather than silently reinterpreting saved data.

