# Root travel and airborne motion v1

Stage 05.6a uses the single-fragment bridge with the existing profile-8
world controls `object_root.position` and `object_root.orientation`. Both
are sampled for the full fragment. Their meaning and the profile format
are unchanged. The legacy snapshot `root_transform` still describes the
semantic pelvis frame. Root fragments use that captured frame for
`entry_body` parameters and airborne rotation about the entry pelvis.
The Blender adapter applies and keys the armature object transform.
Parent-relative bone poses and local pelvis offsets are preserved.

| ID | Parameters and scope |
| --- | --- |
| `root.travel` | Released airborne entry. Line by default, or circular arc with signed sweep of 15° to 90° in magnitude. Chord length defaults to 1 m and ranges from 0.1 to 2 m. Heading defaults to 0° along +Y and ranges from −180° to 180°, positive toward +X. The path lies in the world or captured entry-body XY plane. |
| `root.turn` | World-Z yaw, default +45°, bounded to ±120° airborne. Grounded pivot is limited to ±20° about the one captured active sole. The opposite sole needs at least 20 mm of measured clearance. Two locked soles reject. |
| `root.orient` | Released airborne entry. Pitch or roll in the world or captured entry-body frame, default +45° pitch, bounded to ±90°. Rotation is about the captured pelvis point. |
| `root.hover` | Acquire an absolute armature-origin world elevation from 0.2 to 2.5 m, default 0.8 m. Hold for 0.2 to 1.5 s, default 0.5 s. Takeoff is the default and first releases both captured soles over 0.2 s. Airborne acquisition requires a released entry. |

Transitions default to 2 s and are bounded to 1.5–3.5 s, aligned to 30 fps.
Airborne entries require both sole references at least 20 mm above the
floor. A tilted trajectory must also clear the floor with its evaluated
skin. The exact authored circular positions and pivot positions are
sampled at each frame. The bounded bridge interpolates between adjacent
position keys. Orientation takes the shortest quaternion path across the
requested signed range. Root fragments preserve the solved endpoint. They
do not settle or insert a landing. The normal sampled motion limits and
20 m world budget apply.

The grounded pivot keeps the world sole point fixed while the foot and
body yaw around it. The adapter rejects motion that moves a locked sole.
Continuation uses the measured exit and the baked object pose at the
endpoint. Fixed floor anchors remain world-fixed. Released anchors are
absent from the solved exit, and a later floor acquisition requires a
fresh measured contact. The existing transaction restores the prior
object and bone pose, action and timeline on cancellation or failure.

This scope is restricted to rigid motion on a supported armature object.
An imported rig can retain its static normalization hierarchy. Its
effective parent frame must have positive uniform scale and orthogonal
axes. Root baking uses the rig's local location and quaternion channels
and preserves its authored scale. The profile binding accepts a matching
rotation-invariant scale hash when world-matrix decomposition rounds a
rotated scale differently.
Reviewed rig envelopes and measured evidence will be recorded in the
[stage receipt](../../to%20do/stages/receipts/05.6a.md).
