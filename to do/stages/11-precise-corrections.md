# Stage 11 — Preserve intent through narrow follow-up edits

Status: planned. Dependencies: [10](10-ai-planner.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Make corrections modify the intended movement instances while preserving unrelated targets, timing, travel, contacts and appearance.

**Permitted changes:** Recipe patch contract/compiler mapping, action_interpreter edit decoding, session state in main.py, focused patch/integration tests.

## Execution

1. Retain source recipe, compiled mapping, measured result and base revision. Patch by stable movement-instance/parameter IDs; do not regenerate the whole recipe from prose for an isolated edit.
2. Support body-part/phase targeting: wrists only, knees higher, elbow direction, slower whole motion and gesture only during the second step.
3. Resolve dependency effects through the existing composer. Bound supporting changes and identify a material adjustment; leave incompatible hard-goal edits uncommitted.
4. Distinguish edit-in-place from append at the measured ending state. Preserve translated root/support anchors and reject stale revisions or changed avatars.
5. Initially recompile the entire corrected recipe for correctness. Partial rebuild is an optional measured optimization in stage 17.

## Required outputs and handoff

Publish patch fixtures with base revision, edit/append operation, instance IDs, permitted parameter/temporal changes and preserved locks. Only registered paths are writable; patches cannot modify scene/compiler internals. Compare at matched times and separate declared supporting adjustments from unrelated drift. Use [the API](contracts/01-library-api.md) and 07's source map; keep the original recipe on failure.

## Testing

- Create tests/test_recipe_edits.py and Blender edit cases for each named edit over walk+wave, airborne strokes and a supported seated gesture.
- Assert exact preservation of unrelated recipe fields and measured trajectory preservation within shared numerical tolerances at matched times.
- Test contradictory locks, translated endpoints, append versus edit, stale inference and cancel/failure restoration.

## Validation / completion gate

A wrist-only correction leaves arm paths, travel, timing and unrelated contacts intact unless an explicitly reported dependency requires adjustment. All scoped edits have source-ID evidence, revision checks and measured comparisons.

Write the stage-11 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No replacing a correction with a new complete preset, silent phase reset or broad supporting movement without explanation. Do not claim partial rebuild is implemented if the complete recipe is rebuilt correctly.

