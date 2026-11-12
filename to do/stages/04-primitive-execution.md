# Stage 04 — Execute and inspect one library movement

Status: **complete** (2026-10-19). Evidence: [Stage 04 receipt](receipts/04.md). Dependencies: [03](03-rig-calibration.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Provide the smallest working route from a MovementInstance to a measured Blender result. This allows every body-region library stage to be built and tested before the AI or full composition system changes.

**Permitted changes:** movement_library/compiler.py and shared sampling, the minimal ExecutableMotion adapter in the existing executor, calibrated controls, tests and a developer preview harness.

## Execution

1. Implement instantiate_movement() and build_fragment() against the stage-02 contract. Validate the instance, then accept its measured entry snapshot, rig profile and resolved surfaces to produce a bounded MotionFragment with instance provenance.
2. Implement prepare_fragment() and sample_motion() over bounded typed tracks/contact events, initially hold/transition curves. Adapt the existing build_action_frames loop to accept ExecutableMotion alongside legacy ActionPlan. Reuse solving, independent measurement, review and rollback; no separate keyframing loop.
3. Extend rig application and measurement only for the calibrated semantic controls required by the library interface. Retain old controls through an adapter so existing poses/actions remain valid.
4. Create a developer command/harness that selects a library ID and parameters without a model call, executes one transition and writes samples plus a preview artifact.
5. Keep candidate/rollback/cancel behavior; begin at the measured supplied state. An incompatible entry state yields a precise requirement, not an automatic reset.

## Required outputs and handoff

Follow [execution boundaries](contracts/03-execution-boundaries.md) and [the API](contracts/01-library-api.md). Deliver `tools/preview_movement.py` and fixtures under `tests/fixtures/movement_fragments/v1/`. The harness takes explicit ID/version, parameter JSON, rig and entry fixture. Demonstrate neutral/non-neutral execution, independent measurement, source IDs and cancellation. Publish the sampler/adapter boundary reused by 05–07; no separate family executor.

## Testing

- Create tests/test_primitive_execution.py and tests/blender_primitive_execution.py. Use a test-only head or limb transition to check starting-state fidelity, hold/transition continuity, final measurement and source-instance mapping.
- Test invalid/unreachable targets, missing capability, cancellation and unchanged previous result. Inspect a bent starting pose and a turned avatar.
- Compare an equivalent legacy pose before/after the adapter change, including floor support and keyframed playback.

## Validation / completion gate

A single valid movement can be generated without AI and inspected over its full duration. Measured output meets shared tolerances, preserves unrelated targets, and starts from the supplied state. Legacy paths continue to work.

Write the stage-04 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No general recipe graph, pattern authoring, catalog-wide AI schema, objects or UI redesign. Keep legacy ActionPlan's 12-stage cap; new single fragments use shared track/frame/contact budgets. The typed fragment adapter belongs here; general multi-instance composition belongs to 06–07. Never declare an unexecuted symbolic target a successful movement.

