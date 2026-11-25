# Stage 08 — Migrate existing animations to library recipes

Status: active, partial. See the [partial receipt](receipts/08.md) and
[handoff](handoffs/RESUME-08.md). Dependencies: [07](07-animation-compiler.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Make current jump/walk/lie/run/wave and supported floor/seat routes reuse the new library. Retire duplicate mechanics only after equivalent active behavior is demonstrated.

**Permitted changes:** planning/presets.py, planning/movements.py, routes.py adapters, movement_library/recipes.py, related tests/docs. The user also approved changes to the shared movement catalog and compiler, including the shared pattern bindings, and to the Blender request adapter as needed for this migration.

## Execution

1. Implement each existing foundation as a recipe of registry entries and shared patterns. Preserve documented parameters, finite repetitions and baseline contact/flight behavior.
2. Keep existing public entry points as thin adapters while callers migrate. Route exact-command optimizations through the same recipe/compiler path used by composed requests.
3. Declare standing-only preconditions honestly. Use available compatible transition routes for other starting states; do not overwrite a user's measured pose with the foundation's neutral initial state.
4. Remove duplicated raw target/solver mechanics after references and meaningful tests move to the recipe path. Keep regression fixtures for the previous behavior.
5. Update README to describe internal reusable mechanics and supported parameters, retaining the prompt-first UI.

## Required outputs and handoff

Complete all stage-08 rows in [the coverage ledger](movement-coverage.md), including floor/seat recipes. Record public parameter compatibility and any intentional measured difference. Exact shortcuts call the same registry/compiler. Remove duplicated mechanics only after replacement IDs and regression evidence are recorded; wrappers must not retain hidden duplicate solvers.

## Testing

- Rerun current foundation unit tests and Blender presets for demo/imported rigs. Compare root travel, support/flight intervals, landing, seat/floor contact and ending anchors.
- Check left-hand waving, slower timing, repeated gait and non-neutral entry behavior. Test creative wording still reaches general interpretation.
- Verify a correction to an existing result does not silently become a fresh foundation.

## Studio delivery and first playback

Identify one permitted studio delivery and record its provenance, file type, available joints, texture dependencies and launch steps. Determine whether the studio supplies a compatible FBX or the older custom rig. Andrejs is a useful local candidate with a missing palm reference. Confirm representativeness before treating it as a customer delivery. For an incompatible delivery, record the missing anatomy and compare a studio-prepared companion asset with a limited adapter as a separate decision. Continue migration on the supported rigs.

Use an eligible foundation for the first public playback. Record the operator, actual bake backend, time to first preview and whether the saved result plays. Compare the face, silhouette, clothing, raised shoulder and feet to the source at normal viewing size. Include correction context, cancellation, stale results and bake rollback. Repair the obsolete build_transition/build_action mocks in the UI regression at this boundary. Keep all existing parity and two-rig gates.

Offer an early studio-assisted observation when a participant and approved asset are available. Record recognition, the change they ask for, assistance and whether they choose another action. Carry missing customer evidence forward explicitly. An operator rehearsal can establish mechanics only. Keep source assets local and preserve the current README freeze.

## Validation / completion gate

Existing documented routes execute through the registry/compiler and pass their relevant regressions. No duplicate maintained movement implementation remains for migrated routes. Any intentional output difference has a measured and visually reviewed explanation.

Write the stage-08 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No expansion of the prompt whitelist, removal of useful clip support or sacrificing current capabilities to simplify migration. Do not retain two independently evolving sources of motion mechanics.

