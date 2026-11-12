# Shoulder and upper-arm movements v1

Implementation: `movement_library/limbs.py`, shared pure chord helpers in
`curves.py`, optional shoulder/upper-arm control adapter in `blender/primitive.py`.
Validation status and reviewed envelopes belong to the stage 05.2 receipt; catalog
registration alone grants no rig review.

## Profile and compatibility

`with_shoulders_v1(profile)` explicitly extends calibration v1/v2/v3 to profile
version 4, retaining all existing controls. Record schema and definition versions
remain 1. Existing profiles stay valid for their existing movements. New arm
orientation controls require the extension. No topology or rest-bone changes occur.

Both sides gain `<side>.upper_arm.orientation`, a world quaternion representing
the current calibrated anatomical upper-arm frame. Its measurement reads the
solved bone against its actual rest frame. Applying it rotates the existing upper
arm while retaining child local pose, including captured elbow bend. Absolute
quaternion destinations avoid accumulated twist at circle closure.

A mapped clavicle additionally gains `<side>.clavicle.elevation`, `.protraction`
and `.twist`: signed parent-frame swing/twist angles in degrees, software limits
-12..12. Positive elevation raises either shoulder; positive protraction brings it
forward. Canonical axes are +X right, +Y forward, +Z up. Elevation axes are +Y left
and -Y right; protraction axes are -Z left and +Z right; twist axes are -X left and
+X right. Existing calibrated parent/rest transforms resolve imported bone axes.
Missing anatomy yields MISSING_CAPABILITY for the requested side, with no fake
shoulder movement or added bones. The procedural demo lacks clavicles; Mixamo
provides positive shoulder coverage. A missing opposite clavicle does not disable
the available side.

## Movement parameters and mechanics

All IDs have side left/right/both, duration_s (per transition, default 1.5, 1..3),
hold_s (default .1, 0..1), and return_policy return_to_entry/default or preserve_end.
Timing rounds upward to 30fps boundaries. Bilateral angle or world-target overrides
are independent. Inactive-side overrides and ambiguous target forms are rejected.
The authored bent/turned fixture is distinct from a neutral entry.

| ID | Mechanic and additional envelope |
| --- | --- |
| shoulder.shrug | Parent-relative clavicle elevation, angle default 4 degrees, -10..10. |
| shoulder.reach | Parent-relative clavicle protraction/retraction, angle 4, -10..10; attached arm follows with its captured elbow bend. |
| shoulder.roll | One entry-tangent lifted elevation/protraction orbit, amplitude 4 degrees, -8..8, 32 chords. Elevation ranges from entry to abs(angle); protraction ranges +/-abs(angle)/2. The sign reverses traversal; neutral shoulders never dip below their captured entry. |
| arm.raise | Absolute upper-arm rotation about entry-body or world forward/side-plane axis. Angle default 20 degrees, -30..150; endpoint/body-clearance restrictions still apply. |
| arm.sweep | Horizontal upper-arm sweep; angle 20 degrees, -70..110; side signs mirror across the body. |
| arm.swing | One forward/backward or side oscillation; angle 20 degrees, -70..70. |
| arm.circle | One entry-tangent outward upper-arm orientation orbit, angular radius 12 degrees, -20..20; the sign selects traversal direction. The maximum outward excursion is twice the radius, with exact captured-frame recovery. |
| arm.fold | Finite approach to an explicit world hand target or a chest-relative default (.08 avatar heights to its own side, .20 forward, .06 below the shoulder centre), hold/fold, recovery. Coordinated elbow ownership. The lateral approach margin keeps a neutral arm clear of the chest during the path. |
| arm.reach | Existing two-bone arm IK to a world target or entry-relative bounded displacement. distance_m default .02, -.08...08; forward/side plane and declared axes. Default target includes a small radial withdrawal to avoid forcing straight arms past reach. |
| arm.stroke | Finite approach, sweep and recovery through world endpoint targets. amplitude_m default .08, 0...16; coordinated elbow ownership. Default approach reserves the full sweep excursion on the selected side so bilateral paths remain separate. |

Angle movements expose nullable left_angle/right_angle overrides within the same
bounds. Endpoint movements expose nullable world target/left_target/right_target
vectors, each within +/-20m. A shared target cannot describe two different hands;
bilateral absolute requests require separate targets. Unreachable endpoints fail
before execution and at every solved sample. No unrequested torso/root movement
is permitted. Software parameter bounds are conditional on captured reach and body
clearance; the receipt must distinguish measured envelopes and rejected entries.

For `arm.stroke`, amplitude_m controls the lateral sweep in the declared frame.
The sweep also moves .025 avatar heights backward and downward; zero lateral
amplitude retains that finite back/down stroke and the independent approach.

Large inward sweeps have an explicit entry restriction. The 110-degree cross-body
and bilateral maximum cases use `entry-cross-body-clearance.json`: both upper arms
start at shoulder height with bent elbows and downward forearms. The original
lowered bent-arm entry penetrates Mixamo's chest approximation at that angle and
is retained as a rejection/rollback test. The movement does not secretly lift an
arm, straighten an elbow or move the torso to make an unsafe request fit. A caller
must supply a compatible prepared entry or request the preparation separately.

## Curves and review

Shared `line` and `arc` helpers provide deterministic 1..64 chord expansion,
finite bounded positions and orthogonal arc bases. A full circle closes exactly.
Builders emit existing hold/transition records, not a second sampler, pose-name
handler or recipe composer. Orbit chords use linear interpolation. Shoulder-roll and arm-circle phases are smoothly eased at their endpoints. Arm-circle tangent axes are projected from the captured segment, actual shoulder-to-shoulder outward direction and preferred entry-body/world forward reference. Overhead arms therefore fan away from the head rather than inward. Parallel references use the next fixed world axis deterministically. Approach/recovery use the shared smooth timing. All tracks, frames, contacts and goals retain the shared
budgets and original numeric review thresholds.

Endpoint paths use the existing IK and continuously measured elbow pole. Narrow
arm rotations preserve elbow flexion; reach/fold/stroke explicitly own supporting
upper-arm, forearm and wrist chains. Both feet and unrelated body state retain
captured contacts and existing transaction/rollback behavior.

A documented geometric approximation checks sampled upper/lower-arm segments
against a torso capsule and head sphere. Eight samples per segment use chest plus
arm radius .093 avatar heights and head plus arm radius .083 heights. The chest
capsule runs from 35% of pelvis-to-upper-spine to the upper-spine origin. Penetration
over 3mm rejects the result; this is not full skin collision certification. Opposite-arm segments are checked as capsules with combined radius .036 avatar heights, using exact segment distance. Every sample records minimum clearance and elbow poles. A pole hemisphere flip over one
frame is rejected. Normal 3-degree/10mm tracking, .5-degree/2mm unrelated-change,
360deg/s and 3000deg/sĀ² limits are unchanged.

Evidence uses schema-v2 saved motion and shared assets. Full-motion rendering must
open the saved bundle and compare actual playback to numeric targets. The stage
receipt and ledger record each ID separately, including missing-clavicle results,
invalid paths, both rigs, complete frame coverage, visual observations and storage
accounting. No UI presets, AI changes, fingers or later movement stages are added.

## Read-only measurement batching

Each synchronous `capture_motion_state` validates the current rig fingerprint and
profile once after dependency update. Nested measurements reuse that binding only
inside the read-only call; its context resets on return or exception. Nothing is
cached across frames, scene mutations or public measurement calls. Demo/Mixamo
snapshots matched the uncached path exactly, and changed rig scale still failed
both capture and direct endpoint measurement.
