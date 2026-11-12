# Hip, thigh and knee mechanics v1 — profile 7

Stage 05.4 adds twelve finite movement definitions, version 1, builder
legs.mechanics.v1. The conditional envelopes below passed the numeric, visual
and storage gates on Demo and Mixamo on 2026-11-05. See the
[stage receipt](../../to%20do/stages/receipts/05.4.md).

## Versioned measurements and application

with_legs_v1 explicitly migrates a newly calibrated profile 1–6 to profile 7.
Profiles 1–6 keep their old meanings. Profile 7 inherits hand semantics; optional
profile-6 digit controls are retained only when supplied, without synthesizing
missing anatomy. Capture fresh measured entry; relabelling an old snapshot's
version is not migration.

Existing knee.flexion becomes the actual unsigned angle between thigh and shin
segments: straight 0, positive anatomical bend, software range 0–150 degrees.
It is not legacy shin elevation. Application uses the calibrated forward-bend
hinge, without hyperextension or arbitrary lateral hinging.

Each side has three independent parent-pelvis-frame hip swing/twist projections:
hip.flexion (existing, positive forward, -90–120 degrees), hip.abduction
(positive outward, -25–40), hip.rotation (positive external rotation, -60–60).
The calibrated semantic axes are +X, side-signed +Y, side-signed +Z respectively.
They are not imported bone-local Euler channels. All three projections are
solved together, preserving unspecified components.

knee.plane is a signed angle around the reachable hip-to-ankle axis, referenced
to current pelvis-forward projected perpendicular to that axis (pelvis-up
fallback near parallel). It is undefined below 3 degrees knee bend; measurement
reports 0 there and a requested plane edit requires at least 5 degrees entry
bend. Entry plane angle is carried around a changing endpoint axis; repeatedly
projecting the old knee position is not used to invent a lateral swing.

Foot position/orientation retain world-framed calibrated ankle-head and sole
orientation meanings. Hard endpoint IK conflicts with independent hard hip/knee
angle tracks. Optional foot orientation is applied after the leg solve and must
still satisfy calibrated ankle limits; it is never silently clamped. These
internal controls do not implement stage-05.5 ankle movement IDs.

## Support, ownership and timing

Free-leg IDs use side=left|right (default left); both-free flight is unsupported.
support=opposite_planted is required. The opposite captured sole must be active;
its original anchor stays held throughout. An initially planted selected sole
releases over .2 seconds while its pose holds, before any free movement. With
return_to_entry, its measured entry state is recovered before .2 seconds of
settling/re-acquisition. An initially inactive sole is not falsely acquired.
preserve_end leaves the selected sole inactive. No support surface is invented.

knee.pulse requires side=both, support=both_planted and both captured active floor
soles. It lowers the pelvis by a bounded world-vertical distance while preserving
anchors/orientations through existing planted-leg solving. This is local pelvis
coordination, not rig-object travel or a general support-transfer feature.

duration_s=1.5 (1.5–3) describes each transition; hold_s=.1 (0–1) follows each
authored point. return_policy=return_to_entry|preserve_end defaults to entry.
Times align to 30 fps. Movements declare release, preparation, action, recovery
and end landmarks. Kick/swing/cross/fold contain explicit finite internal phases;
there is no general composer, graph or new sampler.

Free motions own only the selected thigh/shin/ankle and its inherited foot, with
bounded supporting hip motion where listed below. Arms, hands, other leg and
pelvis/object root are preserved. Knee pulse owns pelvis and both leg chains;
its bounded inherited body displacement is declared, not an unrelated reset.

## Per-ID parameters and conditional envelopes

Angles are degrees. Spatial parameters use metres; h denotes calibrated avatar
height. FK motions keep the entry world sole orientation; incompatible poses
reject on joint, reach, floor or clearance checks.

| ID | Default /range | Authored action and support |
| --- | --- | --- |
| hip.lift | angle 40 /0–70 | Prepare hip 15, knee 35; reach absolute hip flexion angle with knee angle+25. |
| hip.open_close | angle +12 /-8–22 | Prepare hip 25, knee 50; change abduction by angle from entry, keeping prepared flexion. Negative closes, positive opens. |
| hip.rotate | angle +15 /-25–25 | Same prepared clearance; entry-relative external hip rotation by angle. |
| leg.extend | angle 15 /0–40 | Absolute knee flexion with captured hip components retained. Requires already-free raised bent entry: hip flexion >=20 and knee >=20. |
| leg.swing | distance_m .06 /0–.10; plane forward or side | Lift by entry-body (0,.035h,.13h), sweep center +/- distance and recover to lifted center. Sole pitches -10 degrees during the raised sweep to preserve ankle margin. Optional world target specifies center; side plane means outward/inward. |
| knee.flex | angle 60 /0–100 | Prepare hip 15/knee 30; achieve knee angle with declared supporting hip 12+angle/2 for floor clearance. Measures hinge relative to the raised thigh. |
| knee.lift | angle 55 /30–70 | Prepare hip 20/knee 45, then hip angle/knee angle+30; measured-entry recovery. |
| knee.orient | angle +20 /-35–35 | Entry-relative bend-plane offset with reachable captured ankle position and world sole orientation fixed. Requires entry bend >=5. |
| knee.pulse | depth_m .02 /.005–.05 | Both planted; bounded pelvis lower/rise. Upright/shallow crouch entry, knees <=70. preserve_end retains lower pose. |
| leg.cross | distance_m .18 /0–.20 | Lift first, then entry-foot offset (toward other side by distance,.18h,.16h), then lift/uncross/recover. preserve_end ends at crossing point. Optional explicit world target is conditional. |
| leg.fold | distance_m .06 /0–.10 | Lift, then foot back by distance and up .20h; sole pitches -25 degrees around entry-body +X at the fold, then unfolds. preserve_end retains fold. Optional world target is conditional. |
| leg.kick | angle 45 /30–60 | Prepare hip35/knee70, action hip angle/knee20, recover to preparation then entry. preserve_end retains prepared recovery pose. No ballistic or contact claim. |

Other hip components remain entry values unless explicitly listed. Extra world
targets exist only on swing/cross/fold. They must satisfy every sampled reach,
joint, floor, support and leg-clearance check, not just a coordinate schema.
Unusable entries reject explicitly instead of shifting to neutral. Default
upright/raised, turned and crouched envelopes are established by actual two-rig
evidence in the receipt, not by this table alone.

## Review and exclusions

Actual geometric leg points, hip/knee angles, sole drift, untouched controls,
root/object state, floor and opposite-leg capsules are measured. Native world
joint rotations feed the existing speed/acceleration reviewer. Limits remain
3 degrees tracking, .5 degree /2 mm unrelated change, 3 mm floor penetration,
25 mm support error, 360 degrees/s and 3,000 degrees/s². Capsule checks do not
replace full-motion skin/deformation/intersection review.

No bones, weights, rest transforms or source topology change. No kneeling,
crawling, knee-floor attachment, contact physics, airborne motion, new avatar
downloads, AI output execution or prompt/composition implementation is included.
