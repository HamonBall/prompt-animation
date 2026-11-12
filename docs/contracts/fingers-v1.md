# Optional hand gestures and finger detail v1

Stage 05.3b adds `hand.gesture` and `finger.curl_spread`, definition version 1.
`with_fingers_v1(profile)` opts into profile **6**, retaining profile-5 controls
and semantics. Capture a fresh measured entry. Profiles 1–5 remain unchanged;
changing a snapshot's version number is not migration. The Blender adapter uses
the existing fragment compiler, sampler, baking transaction, review and rollback.

## Anatomy and calibration

Only existing wrist-parented three-joint thumb/index/middle/ring/pinky chains
are eligible. The distal joints must be consecutive children. The calibrated
bind palm normal and each rest segment direction define positive curl toward the
palm. Positive base-joint spread points toward the thumb side. These are axes in
the declared parent semantic frame, not assumed bone-local X/Y/Z axes.

Controls are `<side>.finger.<digit>.<1|2|3>.curl` and
`<side>.finger.<digit>.1.spread`, degrees relative to the calibrated rest pose.
Measurements are actual parent-relative quaternion swing/twist projections.
Curl and spread projections are solved together while preserving the unrequested
axial tangent component. Parents are applied before children at every sample.
The same geometric control meaning applies with root yaw or a bent parent.

Calibration bounds allow curl -10..100 degrees (thumb -10..75), spread -25..25
(thumb -20..20). Movement targets are deliberately narrower: curl 0..90 at each
joint (thumb 0..65); base spread -20..20 (thumb -15..15). The calibration margins
allow existing mild extension and numerical residuals without clamping actual
measurements. A sample outside a configured calibration limit fails.

Per-digit `detail.<side>.finger.<digit>.mapped_three_joint` identifies exact
existing chain mapping. Non-thumb digits advertise calibrated curl/spread;
thumbs explicitly advertise `approximate_thumb_hinge`. Thumb opposition,
abduction and anatomical grasp coordination are not implemented. Gesture shapes
are authored approximate presets, not a claim of anatomical or contact accuracy.
Any additional terminal bones follow their existing parent; they are not new
independently calibrated controls. Skeleton, rest transforms, weights and source
topology are preserved.

## Movement parameters and ownership

Both IDs use `side=left|right|both` (default left), `duration_s=1.5` (1.5..3),
`hold_s=.1` (0..1), and `return_policy=return_to_entry|preserve_end` (default
return_to_entry). Duration describes each transition, followed by hold and an
optional equally long recovery. Times round upward to 30 fps intervals. Default
execution has 94 inclusive samples over 3.1 seconds.

`hand.gesture` selects `gesture=open|relaxed|fist|point`, default relaxed. It owns
only all calibrated selected-hand digits. Open uses zero curl, relaxed .18 of
each digit's movement maximum, fist .72, and point keeps the index straight with
the other digits at .72. All use zero base spread. Entry and recovery interpolate
smoothly from/to measured entry; an authored open–fist–point validation fixture
uses the same tracks and sampler without adding a general composer.

`finger.curl_spread` offers `selection=all|four_fingers|thumb|index|middle|ring|pinky`
(default all), normalized `curl=.25` (0..1), and `spread_deg=0` (-20..20).
Normalized curl scales the three configured movement maxima for each selected
digit. Nullable `<digit>_curl` and `<digit>_spread_deg` override group settings.
An override naming an unselected digit rejects. With thumb selected, the thumb's
effective spread must be within -15..15; group requests beyond it require a
valid thumb override or `four_fingers`. Schema ranges are conditional on the
selected digit's calibrated movement bounds. No side is inferred from names.

Palm orientation, wrist, forearm, upper arm, other fingers and body trajectories
are independent. The builder emits no supporting arm tracks. Authored compatible
parent/finger fragments can share the existing bridge; this stage supplies no
recipe scheduling or ownership arbitration.

## Capability, review and evidence

Missing selected chains fail **MISSING_CAPABILITY** with exact digit IDs and an
`omitted_detail` ID before scene mutation. A caller can preserve independently
accepted major arm motion and record that error as omitted detail. A partial rig
may request its supported digits. No fingers are added to simulate capability.

The local procedural avatar has no finger chains and is unavailable for both
IDs. The local imported Mixamo asset has all ten three-joint chains. Constructing
a catalog confers no review status; explicit `VerificationRecord` registrations
and the final stage receipt define the actually reviewed envelope.

Full-motion speed/acceleration review includes actual world rotations of all
mapped finger bones, including passive terminal children, using unchanged
360 degrees/s and 3,000 degrees/s² gates. Joint limits, tracking, unrequested
controls, contacts and root/body checks remain active. Detail images may isolate
existing evaluated hand faces to avoid neutral thigh occlusion; complete-mesh
front/side sequences are also retained. Isolation is presentation only, with no
source mesh/rest-rig change. No hand/object attachment, grasp solver, contact
physics, rig reconstruction, downloads or prompt interpretation is included.
