# Per-movement delivery and validation ledger

The Stage 05.1a and 05.1b rows are reviewed in the envelopes recorded in [the head/neck receipt](receipts/05.1a.md) and [the spine/pelvis receipt](receipts/05.1b.md). The ten Stage 05.2 rows are reviewed in the named entry envelopes recorded in [the shoulders/arms receipt](receipts/05.2.md); its motion and final storage gates pass. The nine Stage 05.3a rows are reviewed in the named demo/Mixamo envelopes recorded in [the hands receipt](receipts/05.3a.md), with motion and storage gates passed. Remaining rows are planned. Planned rows are required delivery IDs and minimum baseline variants, not existing registry entries or verified animations. Subsequent stages must not silently merge or drop rows.

The corresponding stage defines scope; the contracts define semantics and test rules. Registry code is authoritative for actual schemas/ranges. This ledger records coverage and evidence, not a duplicate executable definition.

## Complete a row, then complete its stage

For each ID create a section in the owning stage's receipt containing:

- Implemented ID/version and callable builder; supported rig capabilities; required entry state.
- Every parameter's actual type, default, unit/frame and allowed range, or a link to the authoritative generated schema.
- The advertised reviewed envelope versus broader experimental/schema limits.
- Measured entry/exit goals, contact obligations, owned/supporting chains, return policy and composition exclusions.
- Cases covering default, small/large, reviewed min/max, zero/identity where meaningful, both sides/directions, a turned/bent entry and invalid/out-of-range inputs.
- Actual unit, Blender, demo-rig, imported-rig and full-motion visual results. Optional anatomy must have positive coverage on a capable rig and explicit unavailability tests on a missing-feature rig.
- Example instance JSON, numeric report and preview paths; each baseline variant below needs evidence.

Record status as planned, implemented-unvalidated, reviewed-for-envelope, experimental, or unavailable-on-rig. Stage completion requires every required baseline ID/variant reviewed in its declared supported envelope and missing-capability handling checked. One successful animation cannot complete a multi-ID stage. A required unimplemented or experimental baseline keeps the stage partial. Optional 05.3b may be skipped as a whole; optional neck/clavicle/toe features remain accurately capability-scoped.

General composition is unavailable before 06: early preservation tests use an authored parent/limb fixture through the 04 bridge. Reuse the same fixture as a real composed recipe in 07/08. Never write a private family-specific composer just to satisfy a test.

## Required IDs

| Owning stage | ID | Minimum positive baseline | State |
| --- | --- | --- | --- |
| 05.1a | head.look | Torso-relative and world-target look in both directions | [Reviewed: torso ranges and explicit world-point fixture envelope](receipts/05.1a.md#headlook) |
| 05.1a | head.nod | One nod with hold and explicit return | [Reviewed for envelope on both rigs](receipts/05.1a.md#headnod) |
| 05.1a | head.shake | One side-to-side cycle | [Reviewed for envelope on both rigs](receipts/05.1a.md#headshake) |
| 05.1a | head.tilt | Left and right tilt without torso motion | [Reviewed for envelope on both rigs](receipts/05.1a.md#headtilt) |
| 05.1a | neck.lead | Neck-led head movement on capable rig;  explicit missing-neck result | [Reviewed on Mixamo; demo neck unavailable, labelled approximation reviewed](receipts/05.1a.md#necklead) |
| 05.1b | torso.lean | Forward/backward and side lean | [Reviewed for envelope on both rigs](receipts/05.1b.md#torsolean) |
| 05.1b | torso.twist | Upper-body turn with pelvis preserved | [Reviewed for envelope on both rigs](receipts/05.1b.md#torsotwist) |
| 05.1b | torso.curl | Curl/unfurl across available spine segments | [Reviewed for envelope on both rigs](receipts/05.1b.md#torsocurl) |
| 05.1b | torso.wave | One ordered spine wave or explicitly limited single-bone variant | [Reviewed for envelope on both rigs](receipts/05.1b.md#torsowave) |
| 05.1b | torso.sway | One supported side-to-side cycle | [Reviewed for envelope on both rigs](receipts/05.1b.md#torsosway) |
| 05.1b | pelvis.shift | Forward and side supported shifts | [Reviewed for envelope on both rigs](receipts/05.1b.md#pelvisshift) |
| 05.1b | pelvis.raise_lower | Supported lowering and rise from measured entry | [Reviewed for envelope on both rigs](receipts/05.1b.md#pelvisraise_lower) |
| 05.1b | pelvis.tilt_turn | Local pelvis orientation independent of root | [Reviewed for envelope on both rigs](receipts/05.1b.md#pelvistilt_turn) |
| 05.1b | pelvis.circle | One supported bounded circle | [Reviewed for envelope on both rigs](receipts/05.1b.md#pelviscircle) |
| 05.2 | shoulder.shrug | Unilateral and bilateral raise/lower on capable rig | [Reviewed for envelope on Mixamo; unavailable on demo](receipts/05.2.md) |
| 05.2 | shoulder.reach | Protract/retract with arm reach | [Reviewed for envelope on Mixamo; unavailable on demo](receipts/05.2.md) |
| 05.2 | shoulder.roll | One smooth shoulder cycle | [Reviewed for envelope on Mixamo; unavailable on demo](receipts/05.2.md) |
| 05.2 | arm.raise | Forward and side raise/lower | [Reviewed for envelope on demo and Mixamo](receipts/05.2.md) |
| 05.2 | arm.sweep | Outward and cross-body sweep with clearance | [Reviewed for envelope on demo and Mixamo](receipts/05.2.md) |
| 05.2 | arm.swing | One forward/backward swing | [Reviewed for envelope on demo and Mixamo](receipts/05.2.md) |
| 05.2 | arm.circle | One bounded arc cycle with stable elbow | [Reviewed for envelope on demo and Mixamo](receipts/05.2.md) |
| 05.2 | arm.fold | Fold/unfold near chest with clearance | [Reviewed for envelope on demo and Mixamo](receipts/05.2.md) |
| 05.2 | arm.reach | Reach a bounded endpoint from bent entry | [Reviewed for envelope on demo and Mixamo](receipts/05.2.md) |
| 05.2 | arm.stroke | Sweep and recover once | [Reviewed for envelope on demo and Mixamo](receipts/05.2.md) |
| 05.3a | elbow.flex | Bend/extend relative to upper arm | [Reviewed for envelope on demo and Mixamo](receipts/05.3a.md) |
| 05.3a | elbow.orient | Change pole while preserving wrist endpoint | [Reviewed for envelope on demo and Mixamo](receipts/05.3a.md) |
| 05.3a | forearm.twist | Palm-up/down independent of wrist bend | [Reviewed for envelope on demo and Mixamo](receipts/05.3a.md) |
| 05.3a | wrist.flex | Palm/back-of-hand direction with bent parent | [Reviewed for envelope on demo and Mixamo](receipts/05.3a.md) |
| 05.3a | wrist.deviate | Thumb/little-finger directions on both hands | [Reviewed for envelope on demo and Mixamo](receipts/05.3a.md) |
| 05.3a | wrist.circle | One local cycle with arm path preserved | [Reviewed for envelope on demo and Mixamo](receipts/05.3a.md) |
| 05.3a | hand.orient | Palm normal and finger-forward targets | [Reviewed for envelope on demo and Mixamo](receipts/05.3a.md) |
| 05.3a | hand.trace | Line, arc and shared circle | [Reviewed for envelope on demo and Mixamo](receipts/05.3a.md) |
| 05.3a | hand.hold | World-fixed and parent-relative free-space holds | [Reviewed for envelope on demo and Mixamo](receipts/05.3a.md) |
| 05.3b | hand.gesture | Open relaxed fist and point on fingered rig | [Reviewed for Mixamo envelope; demo unavailable; thumb approximate](receipts/05.3b.md) |
| 05.3b | finger.curl_spread | Group and individual finger curl/spread | [Reviewed for Mixamo envelope; demo unavailable; thumb approximate](receipts/05.3b.md) |
| 05.4 | hip.lift | Raise/lower thigh in the pelvis frame, 40° default, 0–70° | [Reviewed on Demo and Mixamo](receipts/05.4.md#per-id-numeric-envelope) |
| 05.4 | hip.open_close | Pelvis-relative out/in, +12° default, −8–22° | [Reviewed on Demo and Mixamo](receipts/05.4.md#per-id-numeric-envelope) |
| 05.4 | hip.rotate | Entry-relative external rotation, +15° default, −25–25° | [Reviewed on Demo and Mixamo](receipts/05.4.md#per-id-numeric-envelope) |
| 05.4 | leg.extend | Thigh-relative extension from bent free entry, 15° default, 0–40° | [Reviewed on Demo and Mixamo](receipts/05.4.md#per-id-numeric-envelope) |
| 05.4 | leg.swing | Forward/lateral clearance arc, .06 m default, 0–.10 m | [Reviewed on Demo and Mixamo](receipts/05.4.md#per-id-numeric-envelope) |
| 05.4 | knee.flex | Thigh-relative bend/extend, 60° default, 0–100° | [Reviewed on Demo and Mixamo](receipts/05.4.md#per-id-numeric-envelope) |
| 05.4 | knee.lift | Supported raised knee, 55° default, 30–70° | [Reviewed on Demo and Mixamo](receipts/05.4.md#per-id-numeric-envelope) |
| 05.4 | knee.orient | Bend-plane change with fixed reachable ankle, +20° default, −35–35° | [Reviewed on Demo and Mixamo](receipts/05.4.md#per-id-numeric-envelope) |
| 05.4 | knee.pulse | Two planted soles, pelvis dip .02 m default, .005–.05 m | [Reviewed on Demo and Mixamo](receipts/05.4.md#per-id-numeric-envelope) |
| 05.4 | leg.cross | Raised crossing and recovery, .18 m default, 0–.20 m | [Reviewed on Demo and Mixamo](receipts/05.4.md#per-id-numeric-envelope) |
| 05.4 | leg.fold | Raised backward fold, .06 m default, 0–.10 m | [Reviewed on Demo and Mixamo](receipts/05.4.md#per-id-numeric-envelope) |
| 05.4 | leg.kick | Preparation, extension and recovery, 45° default, 30–60° | [Reviewed on Demo and Mixamo](receipts/05.4.md#per-id-numeric-envelope) |
| 05.5 | ankle.flex | Toes-up/point with raised thigh | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.5.md) |
| 05.5 | ankle.tilt | Free and supported ankle tilt within declared envelopes | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.5.md) |
| 05.5 | foot.place | Clearance swing to destination and acquire | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.5.md) |
| 05.5 | foot.lift | Lift with opposite support preserved | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.5.md) |
| 05.5 | foot.pivot | One heel and one forefoot pivot | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.5.md) |
| 05.5 | heel.raise | Forefoot anchored heel raise and recovery | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.5.md) |
| 05.5 | toe.raise | Heel anchored forefoot raise and recovery | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.5.md) |
| 05.5 | foot.roll | Heel to sole to forefoot | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.5.md) |
| 05.5 | foot.tap | Two lift and tap cycles, then recovery | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.5.md) |
| 05.5 | toes.curl | Toe curl only on capable rig | Mixamo mapped toes, [reviewed](receipts/05.5.md). Unavailable on Demo. |
| 05.6a | root.travel | Bounded line and arc with explicit frame | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.6a.md) |
| 05.6a | root.turn | Airborne turn and compatible supported pivot | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.6a.md) |
| 05.6a | root.orient | Whole-body tilt independent of local pelvis | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.6a.md) |
| 05.6a | root.hover | Acquire/hold requested elevation without floor snap | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.6a.md) |
| 05.6b | support.acquire_release | Acquire hold release for each advertised anchor | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.6b.md) |
| 05.6b | support.transfer | Feet to hand/pelvis and foot to knee | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.6b.md) |
| 05.6b | body.balance | Slow one-foot geometric support case and invalid case | Demo and Mixamo, [reviewed within the profile-8 envelope](receipts/05.6b.md) |
| 05.6c | body.lower_rise | Supported lower/rise cycle | Neutral and turned crouched reviewed on both rigs. [Verified envelope](receipts/05.6c.md) |
| 05.6c | body.step | One left/right step retaining anchors | Both sides reviewed on both rigs. [Verified envelope](receipts/05.6c.md) |
| 05.6c | body.lunge | Enter/recover directional stance | Demo left lead and Mixamo right lead reviewed. [Verified envelope](receipts/05.6c.md) |
| 05.6c | body.takeoff_land | Prepare flight land recover | Planted push-off, flight and landing recovery reviewed on both rigs. [Verified envelope](receipts/05.6c.md) |
| 05.6c | body.floor_transfer | Upright to floor sitting and floor sitting to back | Floor sit and seated-to-back reviewed on both rigs. [Verified envelope](receipts/05.6c.md) |
| 05.6c | body.kneel_rise | Feet/knee support transition and return | Prepared free-knee and planted-foot entry reviewed on both rigs. [Verified envelope](receipts/05.6c.md) |
| 05.6c | body.crawl | One supported cycle with two palms and a measured pair of knees or soles | Reviewed hands-and-knees cycles at 60 mm on both rigs with two-cycle continuation. Reviewed prepared hands-and-feet cases at 40 mm and 100 mm. [Verified envelope](receipts/05.6c.md#bodycrawl) |
| 05.7a | timing.hold | Preserve state for bounded duration | Planned |
| 05.7a | timing.transition | Connect compatible explicit fragment states | Planned |
| 05.7a | timing.repeat | Finite one two and four cycles | Planned |
| 05.7a | timing.alternate | Left/right alternation with support preserved | Planned |
| 05.7a | timing.mirror | Reflect parameters paths and anchors anatomically | Planned |
| 05.7a | timing.synchronize | Align named phases | Planned |
| 05.7a | timing.phase_offset | Shift one fragment cycle relative to another | Planned |
| 05.7a | timing.overlap | Pre-resolved compatible fragments only | Planned |
| 05.7a | pattern.steps | Alternate finite steps | Planned |
| 05.7a | pattern.strokes_synchronized | Both arm strokes in phase | Planned |
| 05.7a | pattern.strokes_alternating | Opposed stroke phases | Planned |
| 05.7a | pattern.sway | Bounded supported sway | Planned |
| 05.7a | pattern.undulation | Torso phase progression with optional limb follow-through | Planned |
| 05.7b | style.fluid | Smoother paths/continuity with hard goals preserved | Planned |
| 05.7b | style.robotic | Bounded deliberate holds and articulated timing | Planned |
| 05.7b | style.heavy | Longer preparation/recovery within timing locks | Planned |
| 05.7b | style.playful | Controlled light bounce/quick recovery where compatible | Planned |
| 05.7b | style.exaggerated | Bounded amplitude change on selected channels | Planned |
| 05.7b | style.tired | Scoped reduced amplitude/tempo or posture | Planned |
| 08 | recipe.jump | Existing finite jump contract migrated | Planned |
| 08 | recipe.walk | Existing two/four-step supported travel migrated | Planned |
| 08 | recipe.lie_back | Existing supported lying route migrated | Planned |
| 08 | recipe.run | Existing finite strides/flight migrated | Planned |
| 08 | recipe.wave | Side/count/timing preserved | Planned |
| 08 | recipe.sit_floor | Existing floor-seat route migrated | Planned |
| 08 | recipe.sit_seat | Existing resolved-chair route migrated | Planned |

## Stage 05.2 handoff

All ten IDs are version 1 with profile version 4. The receipt's per-ID table
records defaults/ranges, inclusive default frame counts and owned articulation;
[the contract](../../docs/contracts/shoulders-arms-v1.md) records coordinate frames,
entry/return semantics, exact path defaults and the geometric clearance limits.
Authoritative parameter types/defaults/bounds and per-ID reviews are published in
`tests/fixtures/shoulders_arms/v1/<rig>/{schemas,reviews}.json`; supported default
entry/instance/fragment JSON examples are beside them. Per-case numeric results,
complete front/side motion and the inspection index are under
`artifacts/stages/05.2/`.

Arm rotations preserve entry elbow bend; fold/reach/stroke explicitly own the
selected upper arm, forearm and wrist. All IDs preserve unrequested body/root
state and captured contacts. Default return is `return_to_entry`; `preserve_end`
is explicit. Entries are bent-turned, shoulders-bent, neutral and overhead as
reviewed per case. Extreme inward sweeps require cross-body-clearance entry.
Shoulders require the actual selected clavicle, including one-sided availability;
all 33 absent-clavicle demo variants explicitly reject. Arbitrary world targets
remain subject to reach and clearance checks. No later-stage composer is implied.

## Aggregate reporting

Stage 05.3a adds nine reviewed IDs under opt-in profile 5, with 101 cases per
rig, actual per-frame measurements, complete front/side motion and selected hand
axis closeups. Defaults/ranges, coordinate frames, owned chains and return policy
are recorded separately per ID in its receipt and versioned schemas. Spatial goals
remain conditional on reach, joint limits, clearance and compatible hard goals;
near-straight poles follow the explicit hard/soft rules. These entries add no
finger gestures, surface attachment or generic composer. All motion, review,
regression, preservation and storage gates pass. Later rows remain planned.

A stage receipt lists each row separately, not only “all presets passed.” Report reviewed ID count, baseline-variant count, tested rigs and remaining experimental/unavailable variants. Stage 18 checks the ledger against the production registry and receipts: no missing required row, orphan advertised ID or unsupported rig/envelope claim.
