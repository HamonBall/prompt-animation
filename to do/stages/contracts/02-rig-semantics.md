# Required contract: units, frames and joint meaning

Stages 03–05 own implementation of these semantics. Stage 03 publishes docs/contracts/rig-semantics-v1.md with the actual per-joint mappings/ranges and calibrated fixtures. This document defines what must be resolved, not a claim that every current bone is calibrated.

## Coordinate and time conventions

- World distances use metres; time uses seconds; semantic angles use degrees. Avatar-relative distances use the explicit unit avatar_height and the calibrated positive height in metres.
- Canonical character axes: +X right, +Y forward, +Z up. Distinguish world axes from the character's current orientation. Conversion at the Blender boundary accounts for imported rig transforms and scale.
- Frame IDs: world, entry_body, current_root, current_torso, current_pelvis, joint:<semantic-id>, and surface:<resolved-id>. entry_body is fixed at the captured entry snapshot; current frames update with their named parent.
- A target must say whether it follows its parent or stays fixed in world/entry space. Parent changes cannot silently reinterpret a cached target.
- Orientation serialization uses normalized active quaternions [w,x,y,z], mapping local vectors into the named parent frame. Quaternion sign equivalents compare as the same rotation. Angles/curves remain human-readable semantic parameters; multi-turn intent includes an explicit unwrapped turn count.
- Root position/orientation describe whole-avatar travel. Pelvis shifts/tilts are local coordination on top of root motion. Neither may be counted twice in an endpoint transform.

## Semantic joint axes

Calibrate in the profile; do not assume imported local X/Y/Z match these names.

| Quantity | Meaning |
| --- | --- |
| elbow/knee flexion | Zero means calibrated straight; positive bends the anatomical hinge on either side. Preferred bend plane is a separate parameter. |
| wrist flexion | Positive bends toward the palm; negative toward the back of the hand, within the declared range. |
| wrist deviation | Positive toward the thumb, negative toward the little finger. Handedness must be resolved anatomically. |
| forearm twist | Positive supination/palm-up relative to its calibrated neutral, separate from wrist bending. |
| ankle flexion | Positive draws toes upward; negative points the foot. Inherited leg rotation remains separate. |
| hip flexion | Positive brings the thigh forward relative to the pelvis. Hip rotation/opening use separate calibrated axes. |
| head/torso yaw | Positive looks/turns toward character left; direction words are converted through the named frame. |
| head/torso pitch | Positive bends forward in the anatomical frame. |
| head/torso roll | Positive tilts toward character right. |
| elbow/knee plane | A pole direction around an endpoint chain, not arbitrary lateral hinge flexion. |

The profile must explicitly document unsupported quantities. It records zero pose, axes, mirror transformation, software min/max, preferred range, default interpretation and measurement method for every advertised control. A legacy elevation/azimuth remains a segment direction; it must not be relabeled as a joint-relative hinge angle.

## Defaults and tests

Unspecified joint targets preserve measured state. A movement's declared return policy is preserve_end, return_to_entry or return_to_named_neutral; there is no implicit reset at every stage. 'Neutral' identifies a documented semantic pose, not an assumption that all imported matrices should be zeroed.

For each calibrated axis: apply a known small positive and negative change where allowed, independently measure the result, then repeat with root yaw 90 degrees and a bent parent. Check unilateral/mirrored cases. Validate wrist flexion with the arm horizontal and overhead; validate knee flexion with the thigh raised. Joint mapping and measurement cannot both merely echo the requested control.

Capture pole continuity near straight limbs. Unknown velocities/phase remain null. Optional neck/finger/toe/clavicle absence is a missing capability; do not add bones or hide it by moving another joint.

Stage 03 exports two real rig-profile fixtures plus named-axis visual/numeric evidence. If optional anatomy exists on only one rig, identify that positive envelope and test explicit unavailability on the other; do not claim positive two-rig support for that feature.

## Change control

Changing a frame, zero pose, unit, sign, range or mirror rule changes the profile/control schema version. Record migrations and rerun affected movement measurements. Later stage authors consume these definitions and must not introduce their own side-dependent angle conventions.
