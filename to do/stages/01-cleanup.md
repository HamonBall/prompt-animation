# Stage 01 — Audit and remove obsolete implementation paths

Status: complete — 2026-10-14. Dependencies: None. Evidence: [Stage 01 receipt](receipts/01.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Remove confirmed redundant or obsolete code before building the library. Establish the current behavior and dependency graph first. Success means a smaller, understandable active implementation with the current prompt workflow preserved.

**Permitted changes:** Existing source, tests, tools and README entries proven to belong to retired paths; shared helper extraction only where needed to preserve active callers. Create a cleanup inventory and stage receipt.

## Execution

1. Inventory launcher/UI entry points, imports, Blender registration/string references, test fixtures, tools and documented commands. Classify each candidate as active, shared, obsolete, or retained reference, with evidence and a planned action.
2. Inspect the old T-rex-only path: planning/interpreter.py, planning/ai.py, planning/validation.py, MotionPlan/PlanPatch in models.py, and the old blender/animation.py build_transition(). These are candidates, not a deletion list. Current pose/motion/clip code imports aim() and solve_leg() from blender/animation.py; PlanError is used throughout the application.
3. Extract live helpers if necessary and update every active caller before deleting obsolete functions/modules. Preserve PlanError and the active general pose/action contracts. Migrate useful stale-revision, malformed-response, timing-preservation and rollback tests to their live equivalents; remove only tests whose sole purpose is retired behavior.
4. Review tools/check_preview.py, tools/benchmark_interpretation.py and legacy smoke tests together with their callers. Inspect root-level diagnostic/scene scripts; delete only proven redundant tracked source. Record intentionally retained standalone tools and their purpose.
5. Update broken documentation/commands and mark historical single-pose milestones as historical. Record each removed path, reason, remaining replacement, and migrated test coverage.

## Required outputs and handoff

Publish `docs/contracts/cleanup-map.md`: active entry points, removed symbols/paths, replacement helpers, migrated assertions and verified runtime commands. Record source revision and unrelated dirty files before editing. Stage 02 must be able to locate PlanError, active plan types and current IK without guessing. Record the baseline before removal; preserve pre-existing failure evidence.

## Testing

- Before editing, record unit-test discovery and a current demo prompt/generation/play-once smoke result. After editing rerun unit discovery and relevant Blender pose, preset, clip, cancellation and rollback checks affected by the import/helper changes.
- Search for removed symbols and filenames, then inspect every remaining hit. Import the active application modules inside Blender. Test a general pose, one compound/creative prompt path with a deterministic model response, and an existing foundation.
- Do not make obsolete tests pass by restoring the obsolete vocabulary restriction; retain the underlying preservation and validation assertions on the active path.

## Validation / completion gate

Receipt includes a before/after inventory, actual removed paths, helper dependency evidence and test results. No new broken imports, documented commands or active workflow regressions. Any pre-existing failure is identified separately from failures introduced here.

Write the stage-01 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No library implementation, AI redesign or unrelated refactor. No blanket deletion by filename, age, directory or failed-test status. Preserve personal FBX/media, model/runtime files, .git, user configuration, baseline artifacts and historical evidence. Verify resolved paths stay inside C:/work11 before any removal or move. Existing active pose transitions and clip support stay until a tested replacement exists.

