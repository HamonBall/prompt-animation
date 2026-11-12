# Stage 14 — Connect movement goals to objects

Status: planned. Dependencies: [13.1](13.1-object-collision.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Use actual resolved objects to parameterize existing movement primitives: seat support, reach destinations and hand support on horizontal surfaces.

**Permitted changes:** Object resolver, recipe/composer object bindings, contact target adapter and motion/object integration tests.

## Execution

1. Resolve referenced object IDs/landmarks before compiling motion. Bind 'sit on chair' to its seat surface and 'put hand on table' to a reachable top target.
2. Use measured dimensions/state for compatible parameters and approaches. Call 13.1's full-prop reviewer, including between-frame checks; contact success alone cannot clear a candidate. Do not substitute whole-avatar rotation/lowering for supported transitions.
3. Prepare object changes and motion as one candidate transaction. A failed/canceled motion must not leave a new prop committed unless the user requested it as an independent scene edit.
4. Maintain revision checks for object transform/dimensions. Recompute bindings if the object changes; never use stale seat coordinates.
5. Keep limitations specific: supported horizontal contact, unreachable goal, missing approach or unsupported interaction. Offer an existing experimental path where executable.

## Required outputs and handoff

Require full-prop review from [13.1](13.1-object-collision.md) alongside support binding. Add a fixture where seat contact is correct but the avatar hits the chair back/leg; normal generation must reject it. Apply [collision policy](contracts/04-object-contact-collision.md), including uncertain results and between-frame checks. Verify failed combined generation leaves neither a partial motion nor a new prop committed.

## Testing

- Create Blender cases for two seat heights, a repositioned chair, hand-on-table support plus head motion, and unreachable/obstructed targets.
- Measure foot/hand/seat contact and geometry alignment throughout approach and hold. Test a seated gesture preserves support.
- Inject object change, cancellation and solver failure to verify both scene and animation rollback.

## Validation / completion gate

Object-dependent actions use the resolved geometry and preserve it across subsequent gestures/corrections. No floating pelvis or passing candidate is justified by planned contact values alone. Scene/motion transaction checks pass.

Write the stage-14 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No grasping movable objects, carrying, throwing, articulated doors, wall contacts or rigid-body interaction. Visible primitive geometry is not proof that those mechanics exist. No automatic scenery unrelated to the request.

