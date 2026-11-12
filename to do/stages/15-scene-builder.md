# Stage 15 — Assemble requested preview scenes

Status: planned. Dependencies: [14](14-object-interaction.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Implement the physical stage/scene builder separately from the temporal stage builder in stage 06. Assemble requested simple scenery, props, camera framing and lighting around the avatar.

**Permitted changes:** SceneSpec/ScenePatch orchestration, blender/scene.py composition/camera logic and main.py integration; scene workflow tests.

## Execution

1. Compose validated ObjectSpecs into a bounded SceneSpec with stable IDs and relations such as beside/behind/on. Resolve placement in an explicit world or avatar-relative frame.
2. Use the object builder for all new geometry. Support simple floor/background primitives and requested prop arrangements; preserve the shared 64-object/10,000-triangle budget.
3. Keep the current neutral preview floor as the default editing aid. Add decorative scene elements only when requested. Metaphors and animation style are not scenery requests.
4. Frame the whole requested motion path with a stable camera where possible. Use at most three simple lights and preserve Solid preview performance settings.
5. Allow scene-only changes and combined scene/motion candidates with revision/transaction handling. Preserve user-owned unrelated Blender objects and camera choices unless the requested operation explicitly changes them.

## Required outputs and handoff

Use [scene/collision contracts](contracts/04-object-contact-collision.md). Publish placement fixtures with explicit frames, expected bounds, framing and ownership. Keep default camera framing stable over the compiled path. Test scene-only versus combined transactions, and invalidate collision/motion bindings when objects move. Visual placement alone never certifies valid contact.

## Testing

- Create tests/blender_scene_builder.py for avatar-only flight, explicit geometric backdrop, chair+table placement, long-path framing and scene-only correction.
- Check generated-object IDs/budgets, light counts, material reuse, visible framing and rollback. Verify a scene change invalidates dependent stale motion.
- Review the UI flow and rendered previews without exposing internal primitive IDs to casual users.

## Validation / completion gate

Requested simple scenes assemble predictably and remain responsive. Avatar-only requests add no decorative objects. Scene and motion edits preserve unrelated content, and the camera includes the intended action.

Write the stage-15 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No general photorealistic world generation, procedural city/terrain, asset scraping, automatic physics or default decorative stage. Do not merge this with temporal scheduling or export work.

