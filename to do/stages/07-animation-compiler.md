# Stage 07 — Compile and execute composed animation

Status: planned. Dependencies: [06](06-recipe-stage-builder.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Turn the resolved recipe into one bounded executable animation while preserving the current Blender executor, review, cancellation and rollback.

**Permitted changes:** movement_library/compiler.py, motion.py typed compiled tracks/shared sampling, blender/motion.py integration, focused executor tests.

## Execution

1. Implement compile_recipe() returning the same ExecutableMotion introduced in 04. Compile scheduled tracks, runtime entry bindings and merged contacts. Adapt legacy stage evaluation into the shared sampler with regression evidence; do not create a competing typed plan.
2. Retain the 12-stage rule on legacy ActionPlan. New resolved recipes use the independently bounded fragment/track representation. Enforce duration/frame/instance/track/contact budgets before expansion or allocation.
3. Prepare schedules, adjacency and source-instance mappings once. At transitions use actual measured solved state and continuity information, not only the theoretical destination of the previous stage.
4. Apply canonical joint/root/endpoint targets through shared rig adapters. Retain root displacement, acquired anchors, loop metadata and per-instance measurements in the result.
5. Yield construction work through the current modal UI path. Preserve candidate isolation, transaction rollback, previous-result restoration and stale-revision/surface checks.

## Required outputs and handoff

Reuse [04's execution contract](contracts/03-execution-boundaries.md). Compare measured output of a one-instance recipe and its direct fragment. Include multi-instance runtime entry bindings and overflow cases for every shared budget. Document source mapping and legacy compatibility. The result uses one sampler and executor; the compiler cannot invent a second typed animation engine.

## Testing

- Create tests/test_motion_compiler.py and tests/blender_motion_compiler.py. Exercise a recipe exceeding 12 legacy stages, parallel arm/head movement over gait, translated starts, aerial strokes and a loop.
- Measure actual results, contacts and transitions. Inject cancellation, compiler/solver failure and changed surface/revision; verify complete restoration.
- Run existing pose/motion/foundation/clip regressions affected by the new sampler and compare equivalent trajectories.

## Validation / completion gate

The new recipe path builds a visible, reviewable animation with stable provenance and correct start/end state. Legacy results retain their checks. Resource overruns fail before scene mutation; candidate failure never commits partial work.

Write the stage-07 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No replacing Blender, independent second animation engine, removing validation budgets or loosening review thresholds. Do not merge object creation into the compiler; it consumes resolved surfaces. Performance tuning beyond evident duplicated preparation is stage 17.

