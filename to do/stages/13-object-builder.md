# Stage 13 — Construct simple objects transactionally

Status: planned. Dependencies: [12](12-object-contracts.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Build the validated object specs into low-polygon preview props with matching interaction surfaces and reliable undo/rollback behavior.

**Permitted changes:** New blender/objects.py; existing scene.py/geometry.py adapters; object ownership, budgets and Blender tests.

## Execution

1. Implement build_objects(), update_objects() and discard_candidate_objects() for the validated types/assemblies. Use owned collections/tags and stable object IDs.
2. Use simple primitives without subdivision; bound cylinders/spheres to 16 radial segments and count final triangulated output against the shared object budget. Reuse the palette and enforce the 16-generated-material limit.
3. Compute support surfaces and collision proxies from the same transforms/dimensions used for visible geometry. Keep surface/top alignment measurable in world coordinates.
4. Make creation/update a transaction: invalid geometry, cancel or failure restores prior objects, materials references and surfaces without touching unrelated Blender scene content.
5. Adapt the preview-seat creation path to the shared object builder while retaining existing enable/height settings until later UI integration.

## Required outputs and handoff

Follow [object contracts](contracts/04-object-contact-collision.md). Return a candidate object handle plus plain-data surfaces/proxies; commit/discard are separate operations. Verify a rotated chair's support coordinates against its actual mesh. Publish proxy-to-mesh correspondence for 13.1. This stage proves construction, dimensions and rollback, not whole-object collision avoidance.

## Testing

- Create tests/blender_object_builder.py for chair/table/platform dimensions, transformed placement, polygon budgets, repeated updates and no duplicate materials/objects.
- Compare visible top vertices with returned surfaces; test cancel/failure rollback and preservation of a user-owned unrelated object.
- Run existing seat/floor and viewport performance regressions on supported shapes.

## Validation / completion gate

All supported props match their spec and resolved surfaces, stay within budgets and survive updates without leaks. Canceled/failed changes leave the previous scene usable. Avatar geometry/materials remain unchanged.

Write the stage-13 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No dense procedural furniture, scene-wide clear/delete, auto-decimation of the avatar, mesh-generation AI or paid asset services. Unsupported specs must fail before replacing existing props.

