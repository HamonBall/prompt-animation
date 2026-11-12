# Stage 06 — Build action recipes and timeline stages

Status: planned. Dependencies: [05.7b](05.7b-style.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Combine selected movements into a deterministic temporal recipe with entry/exit conditions, chain ownership, support scheduling and provenance.

**Permitted changes:** movement_library/composer.py and recipe relations/contracts; plain-data scheduling/conflict tests. This is the action-stage builder, not a scene builder.

## Execution

1. Implement resolve_entry_state(), resolve_ownership(), schedule_instances(), build_transitions() and compose_recipe(). Accept only validated registry instances, a snapshot and resolved surfaces.
2. Support 'then', 'while', start-after-event and overlap through explicit dependency relations; reject cycles, missing IDs and incompatible entry states.
3. Resolve physical-chain conflicts even when parameter names differ. Contacts and explicit hard goals outrank optional style or gait arm swing; mutually incompatible hard goals produce a specific conflict.
4. Merge compatible contacts into one schedule. A seated arm gesture must inherit seated support; walking plus waving replaces only optional swing on the chosen arm.
5. Specify whether an operation edits an existing timeline, appends from its measured end or starts a new motion from the current state. Preserve IDs and user-clause links; return a recipe plus explanations, without touching Blender.

## Required outputs and handoff

Use compose_recipe() from [the API](contracts/01-library-api.md) and the [execution boundary](contracts/03-execution-boundaries.md). Publish deterministic schedule/conflict fixtures under `tests/fixtures/recipe_schedules/`. Cover sequential, parallel, hard-goal conflict, duplicate contact and cycle cases. State tie-breaking and runtime entry bindings. Build walk/gesture tests from existing step/stroke fragments, not the legacy recipe migration scheduled for 08.

## Testing

- Create tests/test_recipe_composition.py for walk+wave+look, sequential seat+gesture, incompatible hand hold/path, duplicate contact ownership and graph cycles.
- Verify durations, event synchronization, explicit-goal priority, stable provenance and unchanged unrelated instances. Test non-neutral/translated entry snapshots.
- Use real registered definitions; mock only measured state where Blender is unnecessary.

## Validation / completion gate

Valid graphs yield deterministic bounded schedules with no unresolved ownership/contact conflict. Invalid graphs name the conflicting instances/chains. Every explicit clause remains mapped to an instance or a recorded unsupported/approximate result.

Write the stage-06 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No AI calls, Blender scene writes, arbitrary automatic action replacement or silent reset to standing. A missing transition is a reported capability gap, not permission to create a new movement in this stage. Physical stage/scenery construction is stage 15.

