# Elbow, forearm, wrist and free-hand mechanics v1

Implementation: `movement_library/hands.py`, `blender/hand_mechanics.py`, and the
existing fragment compiler, sampler and transactional executor. Validation status
and actual rig envelopes belong to the stage-05.3a receipt and coverage ledger.
This contract does not confer review status merely by constructing a catalog.

`with_hands_v1(profile)` opts into calibration profile **5**. Profiles 1–4 and
their fixtures retain their meanings. Recalibrate and capture a fresh entry;
changing a snapshot's version number does not migrate its measurements.

## Controls and frames

Profile 5 measures elbow flexion as the unsigned angle between actual upper and
lower arm segments, with straight equal to zero, 0..145 degrees. The movement
offers 0..130 degrees. Its solver changes the lower arm about the actual hinge
plane, preserving the upper arm and measured forearm twist. It does not move the
upper arm to simulate a wrist or elbow hinge.

`<side>.elbow.plane` is a signed geometric pole angle about shoulder-to-wrist,
relative to root-backward projected perpendicular to that axis. Root-up is the
fallback reference near a parallel axis. Below 3 degrees of bend the plane is
undefined and measures the deterministic fallback zero. An explicit plane edit
requires at least 3 degrees of entry bend. The movement `elbow.orient` offsets
the measured angle by -45..45 degrees while holding the wrist position and palm
orientation. It owns the coordinated arm chain; it is not lateral elbow flexion.

Forearm twist uses the existing calibrated signed axial swing/twist measurement,
with positive supination convention. Its movement offers -179..179 degrees to
avoid the signed-angle branch at exactly 180 degrees. Actual selected forearm
rotation changes palm roll while retaining wrist flexion/deviation. Optional
twist bones are not synthesized or silently driven by an uncalibrated distribution.
The tested rigs use their mapped core forearm bone.

Wrist flexion is positive toward the palm (-60..60 degrees); deviation is positive
toward the thumb (-25..25 degrees), using the profile's anatomical axes on each
side. They are absolute measured angles relative to the forearm. The application
solves the calibrated swing/twist projections together, retaining the unrequested
component and axial wrist state. Neither moves the wrist endpoint or forearm.
`wrist.circle` traverses a smooth phase orbit tangent to the entry, with signed
radius -10..10 degrees: flexion excursion 0..2*radius, deviation +/-radius. Its
chords use the shared sampler and return exactly to entry.

Palm orientation quaternions map +Y to finger-forward and +Z to the palm normal.
`spatial.palm_rotation(finger_forward,palm_normal)` constructs that quaternion
from perpendicular direction goals, rejecting incompatible directions. This
describes the palm frame, without articulating fingers. `hand.orient` accepts
explicit quaternions or a bounded -150..150 degree roll about entry finger-forward.
The adapter allocates axial rotation to the forearm and applies the remaining
orientation at the wrist, checking actual calibrated joint limits and measured
palm orientation. Simultaneous independent hard wrist/forearm tracks and a hard
palm quaternion conflict explicitly; they are not silently prioritized.

World hand controls remain unchanged. Profile 5 adds
`<side>.hand.torso_position` and `torso_orientation`, measured in `current_torso`,
plus world `torso_frame.position/orientation` for explicit frame conversion.
Torso-relative tracks are transformed from the **current solved torso each
sample** and checked against actual local measurements. World holds remain world
fixed. Entry-body targets are explicitly converted once through the captured
pelvis/root snapshot; this retains the existing snapshot naming convention.

Endpoint/pole IK starts each sample from the captured arm-local entry basis,
after current parent transforms are applied. It does not accumulate pole/axial
parallel-transport drift from preceding samples. This makes a closed hand trace
return the supporting arm as well as the wrist. A simultaneous hard upper-arm
orientation and endpoint solve requires pre-resolved compatible ownership and
rejects at this single-fragment boundary.

The completion evidence records an explicit hash-pinned source-compatibility
migration for this endpoint-only correction. The 130 cases without endpoint/pole
tracks retain their original execution-producer identities and immutable motion;
their branch is unchanged. Affected cases must regenerate. Build/schema,
measurement, sampler and shared renderer sources remain unchanged, and all numeric,
saved-playback, visual and storage gates still apply.

## Common movement parameters

All nine IDs offer `side=left|right|both`, independent nullable left/right angle
or target overrides where appropriate, `duration_s=1.5` (1.5..3), `hold_s=.1`
(0..1), and `return_policy=return_to_entry|preserve_end`. Numeric angular controls
are absolute except the explicitly relative elbow-plane and palm-roll requests.
Default angles: elbow flex 45, elbow plane 20, forearm twist 45, wrist flex 20,
deviation 10, wrist-circle radius 5, and palm roll 30 degrees.

`duration_s` is a nominal transition/curve-phase duration, not total action time.
Approach, hold and optional recovery contribute separately. Cycle chords round
up to whole 30 fps frames: the default wrist circle uses 64 cycle frames plus
3 hold frames, while a default hand arc/circle also has approach and recovery
and totals 141 frame intervals. Use the compiled duration/manifest for playback.

`hand.trace` offers line, arc and circle through shared bounded curve support,
with signed `distance_m=.02` (-.04...04). Line is an exact local-forward offset
from the initial or explicit point. Arc/circle use tangent X/Z orbits, with
180/360-degree sweep; sign reverses traversal. An explicit approach precedes an
orbit and recovery follows it. Frame-aligned linear chords retain smooth orbital
phase without pausing at every vertex. Total duration and track budgets remain
those of the shared bridge.

`hand.hold` defaults to the measured wrist position/orientation. Both hold and
trace offer explicit world, entry-body or current-torso position and orientation
frames. Bilateral explicit targets require separate left/right values. No frame
is inferred from an unlabelled target. Software vector bounds remain +/-20 m,
subject to the shared workspace budget and actual arm reach at every sample.
A straight arm cannot trace further out of its reach; it must use a reachable
path or a prepared bent entry.

Explicit spatial parameters are frame-typed: `target` / `orientation` are world,
`entry_target` / `entry_orientation` are entry-body, and `torso_target` /
`torso_orientation` are current-torso. Side overrides prefix these names with
`left_` or `right_`. The frame selectors choose the captured default when no
explicit spatial value is supplied; an explicitly supplied selector must agree
with an explicit spatial parameter. Mixed target representations reject rather
than reinterpreting the parameter schema's frame.

Trace curve axes are entry-body forward and X/Z for world/entry-body point
requests, and current-torso forward and X/Z for torso-relative requests. The
point's coordinates and curve-axis convention remain distinct. Normal playback
and additional hand closeups use actual solved palm/finger reference axes.
Closeups fit the active hand trajectory and its 10 cm reference rays. Yellow is
the measured palm normal; cyan is measured finger-forward, drawn in front of
the mesh for readability. Unilateral cases have front/side hand angles;
bilateral cases use hand-front for the left hand and hand-side for the right.
The full-body paired views remain available for both arms and body support.

Nullable elbow-plane preferences can accompany hand targets, including independent
left/right values. Soft preference is omitted at an undefined straight-arm
plane; `plane_policy=hard` rejects that case. Once applicable, the selected pole
is solved with the hard endpoint and palm target; unsafe paths still fail review.
An optional hard `flexion_deg` must agree with the law-of-cosines bend implied by
the endpoint within the existing 3-degree gate, otherwise `CONSTRAINT_CONFLICT`.
Unreachable endpoints fail explicitly. The executor preserves the previous
animation on either failure.

The authored chest fixture and explicit torso-relative hand targets/poles express
chest-height wrists and forward elbows. There is no sentence-specific handler,
general recipe composer, surface attachment or finger gesture in this stage.

Schemas under `tests/fixtures/elbows_wrists_hands/v1/` are the authoritative
serialized defaults, units, bounds and example entries. Full-motion evidence,
numeric checks and any remaining limits are recorded in the stage receipt.
