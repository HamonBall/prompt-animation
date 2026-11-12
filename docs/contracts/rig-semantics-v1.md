# Implemented rig semantics v1

Stage 03 handoff, 2026-10-19. Calibration version **1**, AvatarProfile schema **1**.
Implementation: `src/avatar_app/blender/rig_profile.py`. Plain records and serialization
remain the [Stage 02 movement API](movement-api-v1.md); no record/schema was changed.
Generated real profiles: `tests/fixtures/rig_profiles/demo.json` and `mixamo.json`.

## Scope and exact API

Supported rigs are the existing procedural avatar and the existing core Mixamo mapping.
Calibration reads the rest skeleton and existing weighted mesh; measurement reads solved
pose-bone matrices after dependency-graph updates. Neither operation creates bones,
changes mesh/materials/rest data, zeroes the current pose, creates an action or applies a
movement. Stage 05.1a supplies the [head/neck catalog and opt-in head-aim profile v2 extension](head-neck-v1.md); default calibration remains v1.

```python
inspect_capabilities(handle) -> CapabilityInspection
calibrate_joint_frames(handle, *, avatar_id=None,
                       source_revision='unversioned', recorded_at) -> AvatarProfile
semantic_frame(handle, profile, joint_id) -> mathutils.Matrix  # world, metres, current anatomical frame
measure_joint_angle(handle, profile, control_id) -> float     # degrees
measure_endpoint(handle, profile, endpoint_id) -> tuple[float, float, float]
measure_orientation(handle, profile, endpoint_id) -> tuple[float, float, float, float]
measure_bend_plane(handle, profile, limb_id) -> tuple[float, float, float]
capture_motion_state(handle, profile, *, revision, captured_time_s=None,
                     contact_anchors=(), active_contacts=()) -> MotionStateSnapshot
```

`CapabilityInspection` is frozen plain data with `mapped_bones`, `available`,
`missing_optional` tuples. Bone mappings are `(Mixamo_name, actual_bone_name)` pairs.
It detects neck, Spine1/2, per-side clavicle/toe, individual complete three-bone finger
chains and named arm/forearm/thigh/shin twist bones. It does not infer an optional bone
by moving a required neighbour. Discovery uses `avatar.map_mixamo_bones(rig)`; the legacy
AvatarHandle.bones mapping stays restricted to its original core plus Spine1/2/Neck, so
clip retargeting does not silently start animating the newly discovered optional bones.

The built-in rig has an explicit `avatar_reference='procedural-demo-v1'` metadata tag.
This selects its documented palm convention even if Blender renames another instance.
Imported rigs require actual thumb/index/pinky landmarks for the palm reference. Optional
anatomy capabilities begin `anatomy.*`, palm references begin `reference.*`, and calibrated
measurement capabilities begin `measure.*`. These do not advertise movement builders.

## Units, axes, frames and transforms

World coordinates are metres. Angles are degrees; time is seconds. Character axes are
**+X right, +Y forward, +Z up**, derived from the existing import's anatomical right/up
vectors through the full rig hierarchy transform and orthogonalized. A root turn changes
the current frames, not the meaning of flexion or palm-up. Source bone axes are not
assumed to match character axes. Positive uniform effective rig scale is supported;
negative-handed/nonuniform transforms fail with MISSING_CAPABILITY.

Each semantic joint has a calibrated anatomical frame: character-oriented axes at its
bind origin, carried by that bone's measured deformation. With bind/world rotations B0
and B and bind character basis C, its current rotation is `B * inverse(B0) * C`.
This keeps the imported bind rotations, asymmetric wrists and parent inheritance explicit.
No global bone Euler angles are used as anatomical measurements.

`JointMapping.rest_to_semantic` maps normalized metre-space bone-local coordinates into
the **parent's calibrated bind-semantic frame**. Position is the child's origin offset
from the mapped parent's bind origin; orientation is `inverse(C) * B0`. Root mapping uses
`entry_body` at the bind pelvis origin. The profile length `rig.unit` is metres per rig
unit, so consumers must convert raw source coordinates before using this transform.
Segment lengths are measured in world metres, not copied from FBX centimetre coordinates.

Profile frame IDs include world, entry_body, current_root/current_torso/current_pelvis
and `joint:<semantic_id>` for every mapped joint. Joint-relative scalar controls name
their **parent** joint frame in ControlSpec.frames. Per-joint mapping, source name, parent,
unit, positive axis, range, mirror and measurement are persisted in each profile.
Quaternions are active normalized `[w,x,y,z]`; q and -q describe the same orientation.

For the Stage 04 frame adapter, world is identity; entry_body is the captured entry
root transform held fixed; current_root/current_pelvis use semantic_frame(..., 'pelvis');
current_torso uses the uppermost available spine frame (spine.upper, then spine.mid,
then torso). A joint frame uses its exact semantic ID. Surface frames require later
resolved-surface data and are not advertised by these profiles. The torso scalar control
belongs to the first Spine joint; it is distinct from the upper-torso frame alias.

`semantic_frame` returns a read-only measured transform; no frame object is added to the
scene. Current frames are recomputed from measured pose. `entry_body` remains fixed by
the entry snapshot when an executor is added in Stage 04; this module does not retain
mutable execution cursors or reinterpret an old world target as a parent-following one.

## Scalar controls and software envelopes

Ranges below are versioned **engineering software bounds**, tested as rotations, not
collision-free movement envelopes or biological limits. Preferred range is the
intersection of the software range with [-30,30] degrees. Unspecified targets preserve
measured state; calibration supplies no default movement or automatic neutral reset.

| Control family | Zero / positive direction | Software min/max (degrees) | Parent frame |
| --- | --- | --- | --- |
| head.yaw; torso.yaw; spine.mid/upper.yaw; neck.yaw | Bind-relative zero; positive toward character left, +Z axis | -80 / 80 | Actual mapped parent |
| corresponding .pitch | Bind-relative zero; positive forward, -X axis | -60 / 60 | Actual mapped parent |
| corresponding .roll | Bind-relative zero; positive toward character right, +Y axis | -45 / 45 | Actual mapped parent |
| left/right.elbow.flexion | Straight=0; lower arm bends forward relative to upper arm | -10 / 145 | joint:left/right.upper_arm |
| left/right.knee.flexion | Straight=0; lower leg bends backward relative to thigh | -10 / 150 | joint:left/right.thigh |
| left/right.hip.flexion | Calibrated bind-relative zero; thigh forward, +X axis | -90 / 120 | Actual mapped parent (pelvis on tested rigs) |
| left/right.forearm.twist | Bind-relative zero; positive supination convention, separate from wrist bend | -180 / 180 | joint:left/right.upper_arm |
| left/right.wrist.flexion | Calibrated bind-relative zero; positive toward palm | -70 / 70 | Actual mapped wrist parent (forearm on tested rigs) |
| left/right.wrist.deviation | Calibrated bind-relative zero; positive toward thumb | -30 / 30 | Actual mapped wrist parent |
| left/right.ankle.flexion | Calibrated bind-relative zero; positive toes upward, +X axis | -50 / 45 | joint:left/right.shin |
| left/right.toe.flexion, if present | Bind-relative zero; positive upward, +X axis | -40 / 60 | Actual mapped toe parent (ankle on tested rig) |

Head/torso/spine/neck mirror to themselves: yaw and roll change sign, pitch preserves sign.
Paired limb controls map left to right and preserve the semantic sign. The actual axis
vectors are calibrated separately for each side; reflecting an imported bone's raw Euler
values is not the mirror rule. If a required counterpart/reference is missing, the
corresponding optional control is absent or its mirror reference is null.

Elbow/knee flexion is independently measured by projecting actual upper/lower bone
directions onto the calibrated hinge plane and using signed atan2 of their cross/dot
products. Its zero is **straight**, so an imported bind pose can have nonzero flexion.
Mixamo bind elbows measure about 7.12/7.15 degrees, rather than fabricated zero.
The positive elbow axis is upper-arm direction crossed with projected character forward;
the knee uses thigh direction crossed with projected character backward.

Other scalar controls measure the signed axial part of the actual calibrated
parent-relative rotation delta, using swing/twist decomposition about their declared axis.
The observed parent rotation is removed before comparing against the child's bind mapping.
This is a scalar projection of a rotation, not a new Euler ordering. Combined multi-axis
authoring must account for that decomposition; Stage 03 does not supply an inverse solver.
An exactly orthogonal 180-degree swing with undefined twist fails ENTRY_MISMATCH.

Forearm positive twist axis is the bind forearm direction on the right and its negative
on the left. Wrist flexion axis is palm longitudinal crossed with outward palm normal;
deviation axis is longitudinal crossed with radial/thumb direction. These axes are stored
in the parent semantic frame and follow a turned/bent parent. Bind-relative wrist zero
preserves the imported wrist bend; it does not force bone matrices to identity or call
the bind pose anatomically straight.

## Direction, position, palm/sole and pole measurements

These are different semantic quantities from a hinge angle:

| Control/helper | Representation and meaning |
| --- | --- |
| left/right.upper_arm/forearm/thigh/shin.direction | Unit vector of the actual segment in world frame; no Euler or hinge reinterpretation |
| left/right.hand/foot.direction | Unit vector along the endpoint bone in world frame |
| left/right.hand/foot.position | Actual bone-head endpoint position, world metres; distinct from its requested target |
| left/right.hand/foot.orientation | World quaternion; local +Y is longitudinal, +Z is outward palm/sole normal, +X completes the right-handed frame |
| measure_endpoint(..., 'left/right.sole') | Current world position of the calibrated sole anchor |
| measure_bend_plane(..., 'left/right.forearm/shin') | Unit world pole direction, with deterministic near-straight fallback |
| root.position / root.orientation | Measured pelvis-root origin and anatomical orientation in world frame |

Palm longitudinal direction uses the wrist to index/pinky midpoint; radial direction
points from pinky toward index, projected off the longitudinal direction. Left/right
cross-product signs resolve the outward palm normal. The procedural avatar uses its
explicit longitudinal/facing convention; it has no individual finger capability.
Andrejs lacks thumb/pinky landmarks: palm orientation and wrist flexion/deviation are
unavailable there. Its existing hand bones are not evidence of a measured palm plane.

Sole normals use the calibrated standing support reference, not the sloped ankle-to-toe
bone as a flat shoe sole. The anchor is the mean of the lowest 3 mm of existing vertices
weighted at least 0.25 to that foot. Sole forward is the foot direction projected onto
the calibrated standing plane. These references follow measured foot deformation and
are not a new skin-collision solver or an estimate of ground contact from target values.

Reference directions are stored as named Landmark offsets: palm.forward/radial/normal
and sole.forward/normal have 0.05-metre length in the named joint frame. Normalize their
vectors when using them as directions. Sole anchors store their actual joint-relative
offset. Character right/forward/up use 0.1-metre reference offsets. Finger mappings/tip
landmarks record existing rest geometry but do not expose finger animation controls.

Preferred elbow and knee poles are respectively character backward and forward in the
upper arm/thigh frame, stored at 0.25 avatar-height distance. Geometric plane measurement
is ill-conditioned near straight, especially with asymmetric bind offsets. Below 0.5
degree projected flexion, the parent-relative calibrated pole is used. From 0.5 to 5
degrees it smoothly blends to the measured plane, oriented into the calibrated hemisphere.
At 5 degrees and above it uses that measured plane. This avoids flips without pretending
that a perfectly straight limb has a uniquely measured bend plane. No mutable history
or arbitrary lateral hinge angle is invented.

## State, compatibility and errors

capture_motion_state updates the view layer and records the solved root, every available
control, avatar/profile version and caller revision. Time defaults to
`(frame_current + frame_subframe - frame_start) / (fps/fps_base)`, in seconds. Captured
contacts/anchors must be explicitly passed as typed data. Empty contact tuples assert
no contacts; proximity to a floor does not imply a planted foot. Unknown velocities and
phase are **null**. Measurements are never replaced with requested targets or clamped.
Context validation rejects a measured state outside the profile's software envelope.

The legacy runtime carries whole-body root travel and local pelvis adjustments on the
same Hips bone. The snapshot records this measured carrier once; it does not fabricate
a separate pelvis translation or count it twice. Separating future authored root travel
from local pelvis coordination requires adapter work in the owning later stages.

Existing control mappings and gaps:

- head/torso yaw/pitch/roll are related to the existing controls, but legacy torso rotation
  is distributed over several spine bones. Per-segment measurements are not a direct
  copy of that aggregate target.
- arm/forearm/thigh/shin elevation and azimuth remain segment-direction controls. They
  cannot be relabelled elbow/knee flexion. New joint-relative authoring needs an adapter.
- hand_roll/pitch/yaw remain legacy rotations in the legacy root frame. Wrist flexion,
  radial deviation and forearm supination need the new calibrated axes; they are not
  aliases for those fields.
- Existing hand targets use avatar-height offsets from the pelvis/root; foot targets
  use neutral floor anchors. Convert requested frames explicitly before comparing with
  the new world-metre measured endpoints. Legacy AvatarHandle.height is unchanged:
  its world reference height is handle.height times the `rig.unit` LengthSpec value. New avatar_height
  values use profile.height_m (actual bind-mesh extent). These references are different;
  legacy target migration must preserve the original normalization factor.
- Optional neck/spine/clavicle/toe/finger/twist mappings describe actual anatomy only.
  Clavicle/finger/twist-bone authoring, twist distribution, shoulder motions and general
  arbitrary-rig inference are not implemented by this stage.

Binding uses a SHA-256 fingerprint of rest bone names/transforms and effective rig scale.
A wrong skeleton/changed scale fails ENTRY_MISMATCH and requires explicit recalibration.
Rigid object translation/rotation remains measurable. Unsupported calibration versions
fail VERSION_MISMATCH. Missing palm/axis/skin reference fails MISSING_CAPABILITY; unknown
IDs, invalid values and snapshots use the Stage 02 structured errors. Version/revision
booleans remain invalid. Changing axes, zero, sign, units, range, mirror or reference
meaning requires a new calibration/profile version and rerunning the affected evidence.

## Fixtures and verification

The Blender harness generates both real profiles and numeric/visual evidence:

```powershell
& $stageBlender --background --factory-startup --python-exit-code 1 --python tests/blender_rig_profile.py -- --render
& $stagePython -m unittest discover -s tests -p 'test_rig_profile_fixtures.py' -v
```

`tests/fixtures/rig_profiles/manifest.json` identifies the two schema-v1 profiles,
calibration version, source revision/working-tree context and tolerances. Demo has
48 measured controls; Mixamo has 53, with different measured segment proportions.
Every scalar axis is tested at its min, max, -5, 0 and +20 degrees with neutral,
90-degree root turn and bent-parent fixtures. Wrists also use horizontal/overhead arms.
Measurement tolerance is **0.1 degree**, rigid endpoint tolerance **0.0001 metre**.
The harness also verifies geometric flexion signs, mirrored semantic values, near-straight
pole continuity, orientation quaternion sign equivalence, explicit contacts, null unknown
state, scale invalidation, and exact rest/mesh/material/scale preservation.

Palm-up checks measure the actual palm normal before/after a 90-degree root turn, with
the shared **3-degree** orientation goal tolerance. Imported bind wrists receive an
explicit static corrective wrist fixture when pure forearm twist leaves a residual;
this distinguishes wrist bending from supination and does not add a movement builder.
Applying a known static test pose is not execution of a library animation.

Evidence under `artifacts/stages/03/` includes profile-review.json, both captured snapshots,
calibration-review.log, and demo/mixamo axes and turned-palm-up PNGs. The four images were
inspected: red X/green Y/blue Z frames follow the turned body, yellow palm normals point
up, and magenta leaders start at the actual wrist/sole landmarks. Axis drawings are offset
0.13 metre toward bind-forward for visibility. Landmark crosses are offset 0.18 metre
bind-forward and 0.03 metre up, with leaders to their measured positions, so interior
wrist/undersole points remain visible without changing the mesh.
Both mesh silhouettes/proportions remain intact; diagnostic Workbench shading uses material
colours rather than a texture review. Material slots are independently checked unchanged. Full-motion review
is not claimed for these static calibration fixtures. Stage 04 now supplies the
[single-fragment execution bridge](fragment-execution-v1.md), using these calibrated
frames and independent measurements.

## Stage 05.1b opt-in pelvis measurement extension

`movement_library.torso_pelvis.with_pelvis_v1` extends the head-aim profile to
calibration version 3 without altering version-1/2 controls or fixtures.
`pelvis.position/orientation` measure the Hips bone semantic frame;
`object_root.position/orientation` measure the actual armature object. The legacy
`root.*` names and snapshot `root_transform` retain their Hips-frame meaning for
compatibility. Whole-avatar root travel must migrate that naming explicitly in
Stage 05.6a. See [spine/pelvis v1](spine-pelvis-v1.md) for units, coordinate frames,
support requirements, schemas and the reviewed rig envelope. Torso-only builders
also work with head-aim version 2; pelvis builders explicitly require version 3.

