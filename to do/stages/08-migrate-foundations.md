# Stage 08 — Migrate existing animations to library recipes

Status: planned. Dependencies: [07](07-animation-compiler.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Make current jump/walk/lie/run/wave and supported floor/seat routes reuse the new library. Retire duplicate mechanics only after equivalent active behavior is demonstrated.

**Permitted changes:** planning/presets.py, planning/movements.py, routes.py adapters, movement_library/recipes.py, related tests/docs.

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

## Validation / completion gate

Existing documented routes execute through the registry/compiler and pass their relevant regressions. No duplicate maintained movement implementation remains for migrated routes. Any intentional output difference has a measured and visually reviewed explanation.

Write the stage-08 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No expansion of the prompt whitelist, removal of useful clip support or sacrificing current capabilities to simplify migration. Do not retain two independently evolving sources of motion mechanics.

