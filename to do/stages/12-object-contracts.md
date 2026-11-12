# Stage 12 — Define requested objects and semantic surfaces

Status: planned. Dependencies: [11](11-precise-corrections.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Represent simple requested props as bounded scene data with useful interaction anchors. Keep object description separate from Blender mesh creation and movement execution.

**Permitted changes:** New scene_contracts.py, plain-data object validation/resolution, narrow planner object-request schema, object contract tests.

## Execution

1. Define versioned ObjectSpec and ScenePatch with stable IDs, template/primitive type, dimensions, placement frame, orientation, material choice and explicit user-request provenance.
2. Support box, plane, sphere and cylinder primitives plus chair, stool, table and platform assemblies. Separate visible geometry, collision proxies, support surfaces and interaction landmarks.
3. Resolve new/existing object references from a scene snapshot. A chair interaction can create one simple chair when none is resolved, while an existing explicitly referenced chair is reused.
4. Expose horizontal top surfaces to the current contact solver; tag other geometry as visual/collision-only until its interaction capability exists.
5. Validate finite positive dimensions up to 10 m on applicable axes (planes omit thickness), positions within 20 m of scene origin, at most 64 generated meshes, 10,000 generated triangles and 16 generated materials per preview. Count existing generated props plus expanded assemblies before accepting a ScenePatch.

## Required outputs and handoff

Follow [object contracts](contracts/04-object-contact-collision.md). Publish `docs/contracts/scene-api-v1.md` and fixtures under `tests/fixtures/scene_contracts/v1/`. Include a chair with separate seat support and back/leg proxies. Geometry, support eligibility and collision-review capability are distinct. No collision-free claim is valid until 13.1 consumes and tests those proxies.

## Testing

- Create tests/test_scene_contracts.py for valid assemblies, duplicate IDs, unknown types, nonfinite data, bound failures and failed references.
- Test 'sit on a chair', 'use this chair', 'fly like a fish' and 'add a simple room': interaction requirements or explicit scene requests are retained; metaphor alone creates no water/fish geometry.
- Validate surface coordinates against analytic dimensions, including a rotated object with a horizontal top.

## Validation / completion gate

The same spec deterministically describes visible dimensions and support/interaction data. Unsupported surface capabilities are explicit. All resource limits are checked on expanded assemblies before any Blender mutation.

Write the stage-12 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No meshes created, arbitrary object code, external model downloads, detailed rooms, wall-climbing or physics. Do not overload the motion primitive registry with object-template IDs. Preserve the existing floor/seat workflow through an adapter.

