# Required contract: objects, support and collision

Stages 12–15 own this pipeline. Rendering an object, contacting its top and avoiding its entire volume are separate capabilities.

## Object records and identifiers

Stage 12 publishes the actual typed schemas and JSON fixtures in docs/contracts/scene-api-v1.md.

- ObjectSpec: schema_version, object_id, template/primitive kind, dimensions with units, transform and placement frame, material key, request clause IDs, assembly children and capability flags.
- SurfaceSpec: surface_id, object_id/version, world transform, bounded support region, normal, supported anchor kinds and contact capability.
- CollisionProxy: proxy_id, object_id/version, supported geometric type, dimensions/transform, local bounds and mapping to rendered geometry.
- SceneSnapshot/ScenePatch: base revision, existing object versions, add/update/remove operations and a candidate transaction ID. Only owned generated objects may be changed by ordinary scene patches.
- CollisionIssue: frame/time interval, avatar part, object/proxy IDs, kind, measured clearance/penetration where available, method and whether the finding is definite or conservative.

Keep IDs stable across updates and increment versions for geometry/transform changes. Catalog IDs for motions and objects occupy distinct namespaces.

## Support contract

Initial object support is limited to bounded horizontal upward-facing top surfaces. Object yaw is allowed; a tilted top is not silently treated as horizontal. A visually rendered wall does not provide wall-contact mechanics.

A chair has a seat support surface plus separate seat/back/leg geometry and collision proxies. A pelvis may touch the seat while an arm must still avoid the back. Object-dependent controls refer to the resolved surface/landmark, not a guessed chair height or the avatar's original origin.

Surfaces/proxies derive from the same transforms and dimensions as the mesh. A neutral editing floor is existing preview infrastructure; arbitrary extra props need explicit scene or interaction intent.

## Collision stages and minimum coverage

13 builds geometry, surfaces and proxies; it does not claim collision avoidance. New stage 13.1 consumes them and supplies a collision-review API. 14 binds object interaction to both support and collision review; 15 handles arrangement and camera framing.

Use broad-phase bounds/proxies to find candidates, then a documented narrow phase for supported geometry. Checking only whether avatar vertices are below the seat is insufficient. Required cases include thin chair legs/back panels, an avatar edge/triangle crossing an object with no avatar vertex inside, containment, and movement through a prop between sampled frames.

For static generated props, use evaluated-avatar mesh intersection/containment checks where needed, with reusable object acceleration data. Include a conservative swept body/limb proxy check between samples; refine uncertain intervals with bounded subdivision. Proxies are rejection/refinement evidence, not proof that an intersecting mesh is clear.

The minimum normal-preview contract is conservative: if the supported checker cannot classify clearance within its bound, return collision_uncertain and do not mark the candidate reviewed. This does not require a dynamics or automatic avoidance planner.

At an explicitly acquired support surface, allow only the configured contact tolerance for the intended part/region. Never ignore the entire supporting object. Other penetrations or unclassified intersections remain failures. Apply the guide's 3 mm penetration baseline when penetration is measured; a boolean intersection alone must not be reported as a measured depth.

## Collision API owned by 13.1

prepare_collision_scene(scene_snapshot) -> immutable object acceleration/proxy data.
review_object_collisions(evaluated_motion, collision_scene, policy) -> issues and measured coverage.
review_swept_interval(previous_sample, current_sample, collision_scene, policy) -> clear/collision/uncertain plus evidence.

Policy includes tolerances, maximum refinement depth (initially 4 bisections per flagged interval), candidate budget (initially 2,048 body-proxy/object-proxy pairs per interval), and supported geometry methods. Overflow returns uncertain/resource-limit, never clear. Profile these explicit initial bounds before tuning.

Object/geometry changes invalidate caches and motion bindings. Cancellation restores both candidate motion and candidate objects. Experimental acceptance can retain an explained quality failure, but cannot disable malformed-data, unreachable-target or resource checks.

## Out of scope

No rigid-body response, friction simulation, carrying/throwing, moving articulated props, wall support, full self-collision solver or arbitrary downloaded meshes. Self-collision quality remains a separate avatar review concern; passing prop collision does not establish it.
