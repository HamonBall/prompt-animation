# Spine and pelvis movement contract v1

Stage 05.1b adds nine definition-version-1 movements to the shared single-fragment
bridge. No planner, composer, preset selector or public UI is added. Parameter
schemas are generated from `movement_library/torso_pelvis.py`; measured examples
and the stage receipt supply the reviewed rig envelope.

## Coordinates and calibration compatibility

`with_pelvis_v1(profile)` is an explicit, nonmutating calibration-version-3
extension of head-aim version 2. It retains all old controls and adds:

| Control | Shape/unit/frame | Measurement/application |
| --- | --- | --- |
| pelvis.position | vector3/metre/world | Actual Hips bone head in world space; moving the Hips bone |
| pelvis.orientation | quaternion4/unitless/world | Current calibrated pelvis semantic frame; rotating the Hips bone |
| object_root.position | vector3/metre/world | Armature object translation; measurement only in this stage |
| object_root.orientation | quaternion4/unitless/world | Armature object rotation; measurement only in this stage |

The version-3 provenance marker is
`pelvis_v1:bone_world_transform_not_object_root`. Existing versions 1 and 2 retain
their serialization and behavior. Their historical `root.position`,
`root.orientation` and snapshot `root_transform` describe the calibrated Hips
frame. Those legacy aliases remain intact in version 3 for compiler entry-frame
compatibility; they are **not** the armature object root. New pelvis movements
never author tracks on those aliases or on `object_root`. Stage 05.6a must choose
explicit whole-avatar travel controls and migrate the aliases before advertising
root travel; it must not treat a pelvis shift as whole-avatar translation.

Torso angles use the existing calibrated parent-joint frames and signed
swing/twist controls: pitch forward, roll right, yaw left. Pelvis displacement is
authored along the **captured entry pelvis axes**, then stored as absolute world
positions. `forward`, `side`, `vertical` select +Y, +X, +Z of that captured frame;
negative distances reverse direction. Pelvis rotation is a relative quaternion
in the captured pelvis frame, stored as an absolute world orientation. It never
rotates the armature object. These fixed conventions are not selectable dynamic
frames. Arbitrary future root travel and support transfer are excluded.

## Definitions and parameter envelopes

All nine IDs take `duration_s` (seconds per transition, default 1, range .8–3),
`hold_s` (seconds at each waypoint, default .1, range 0–1), and `return_policy`
(`return_to_entry`, default, or `preserve_end`). Times round up to the next 30 fps
sample. Preserving a cycle's end still completes that cycle; no generic repeat or
timeline composer is involved.

| ID | Amplitude | Plane/default | Authored path |
| --- | --- | --- | --- |
| torso.lean | angle=10°, −20..20° | pitch or roll; pitch | Lowest calibrated spine segment bends then optionally returns |
| torso.twist | angle=10°, −20..20° | yaw | Lowest spine segment turns with pelvis fixed |
| torso.curl | angle=10°, −20..20° total | pitch | Equal share across available spine segments, then optional unfurl |
| torso.wave | angle=10°, −20..20° total | pitch | One bend/recovery pulse, lower/middle/upper activation staggered by 8 frames, recovery in the same order |
| torso.sway | angle=10°, −20..20° | pitch or roll; roll | Entry → positive amplitude → negative amplitude → optional entry |
| pelvis.shift | distance_m=.01, −.04...04 m | forward or side; side | Captured position → offset → optional entry |
| pelvis.raise_lower | distance_m=−.02, −.04...04 m | vertical | Supported lower/rise → optional entry |
| pelvis.tilt_turn | angle=5°, −10..10° | pitch, roll or yaw; yaw | Relative orientation → optional entry |
| pelvis.circle | distance_m=.01, −.04...04 m | side (entry horizontal plane) | Radial entry, 32 chord segments, radial exit; one closed cycle |

Circle v1 uses 32 linearly timed chords, with smooth radial entry/exit and optional
holds at orbit entry, orbit closure and recovered entry. Its maximum chord radial
error at a 4 cm radius is below .2 mm. It is not an analytic curve. A zero radius
or angle is an explicit identity. A negative radius starts on the opposite side;
it does not reverse the direction of traversal. `duration_s` is per transition,
except for circle chords, which each take a quarter of `duration_s`, rounded up
to a full sample. Its orbit takes about eight times `duration_s`, in addition to
radial entry/exit and holds. The largest circle stays below 34 seconds.
Wave recovery is part of the pulse, so `preserve_end` preserves its recovered
entry pose rather than truncating the wave at its bent peak.

One spine segment can curl and can perform an explicitly labelled
`single_spine_approximation` wave. It cannot produce traveling multi-segment
motion. No calibrated torso control is a missing capability, never an invented
bone. The profile-scoped catalog owns only actually calibrated spine chains.

## Entry, ownership and support

Every movement starts from actual measured controls and keeps the head's world
orientation through an explicit quaternion hold. Head compensation is owned.
The arms retain their joint pose and follow their torso parent; their moving
world positions are structural consequences, not fixed hand targets. World hand
locking and head follow-through are not parameters of this version.

Torso-only movement preserves the pelvis and armature object. Curl and wave own
the available spine controls. Lean, twist and sway author only the lowest spine
segment; the other spine angles remain locked to entry. The definitions reserve
available spine chains and head, while tracks determine actual execution
ownership. Captured floor contacts continue without support transfer.

Pelvis movements require **both captured sole anchors on the floor for the full
fragment**, with zero acquisition/release ramps. Hips changes cause supporting
thigh, shin and ankle changes through the existing two-segment leg/contact
solver. Foot head locations and foot orientations stay captured. The adapter
preserves each captured knee bend plane through a pelvis turn instead of using
the rig's original forward direction. Supporting changes and entry/exit states
are available in every sample and the final measured snapshot.

Reach is checked without mutation at authored waypoints and at every sampled
position/orientation. Incompatible shifts and depths fail; no foot dragging,
clamping, implicit standing pose or balance simulation is applied. A straight
leg cannot generally accept a positive vertical offset; callers must supply a
reachable entry. The reviewed pelvis fixture is an explicitly authored 9 cm
crouch with a 90° heading and asymmetric arm/head pose, on both demo and imported
Mixamo rigs. That fixture is test input, never an executor reset.

## Measurements and failure behavior

The existing transaction, sampler, main-thread baking, cancellation, keyframes,
floor review, contact review and rollback are reused. Meter-valued authored
waypoint goals use a 1 mm tolerance, joint/quaternion goals .1°. Normal shared
limits remain 3 mm floor penetration, 25 mm contact drift, 360°/s joint speed,
3000°/s² acceleration, 3° orientation residual and 10 mm endpoint residual.
Unrequested angular components stay within .5°. Profile measurements are actual
bone transforms, not copies of requested targets.

Focused commands are `tests/test_movement_spine_pelvis.py`,
`tests/blender_movement_spine_pelvis.py` (both rigs and parameter matrix), and
`tests/blender_spine_pelvis_boundaries.py` (real reach rejection, failed-review
rollback, cancellation and a disposable one-spine rig). The matrix's
`--render-only --skip-rendered` mode produces every frame in front and side views
and records a versioned manifest with input/scene hashes and expected frame files
so stale or incomplete visual files cannot be reused. It renders the stored rig
and action/slot directly. See [artifact storage](artifact-storage.md).
The developer CLI `tools/preview_movement.py` opts pelvis IDs into version 3 and
uses a full-body camera for body movements. User-visible controls remain the
prompt workflow. Measured JSON, numbered PNGs, contact sheets and playable Blend
files live under `artifacts/stages/05.1b/`.
