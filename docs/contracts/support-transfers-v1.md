# Fixed support contacts and geometric balance v1

Stage 05.6b uses the existing single-fragment transaction. A contact
event with `target_world_v1` fixes a point in world metres on the
resolved horizontal surface named by `surface_id`. The field is optional
in serialized data. Omitting it selects the earlier contact behavior.
The stage still uses profile 8. The opt-in
`support_contacts_v1:weighted_skin_points` calibration adds palm,
pelvis, back, and knee landmarks and world position controls from the
rig's authored weighted mesh. A missing calibrated point excludes it
from the profile's supported anchor choices.

| Anchor | Contact measurement and solver |
| --- | --- |
| Sole, heel, forefoot | A rigid calibrated point in the ankle frame. Existing leg IK places the point with the entry foot orientation. Forefoot provides toe-end support on either rig. |
| Palm | A weighted hand-skin reference in the wrist frame. Arm IK positions it while the palm normal turns toward the plane. Held skin gap is measured independently. |
| Pelvis, back, knee | The calibrated point supplies world XY. Evaluated skin over the support region supplies the vertical contact measurement. Pelvis translation places the point. Held foot targets are then solved again, with at most two corrections for the effect of foot IK on skin height. |

The solver accepts one independent fixed foot point per leg. A knee
contact requires the same-side foot free. One pelvis-driven contact can
own the body at a time. Simultaneous palm and pelvis-driven contact
requires a compatible combined solver and currently rejects. Surface
penetration is checked separately from held point residual and skin
gap. A bounded surface uses its measured world XY region and elevation.
The floor has elevation zero.

`support.acquire_release` supports acquire, release and cycle. The
default cycle acquires, holds and releases the selected left sole.
`support.transfer` defaults to acquiring the left sole and releasing
the right sole. Its old support remains fully held through the new
contact's acquisition and hold. Acquisition and release default to
0.8 s with bounds of 0.5–2 s. Hold defaults to 0.2 s with bounds of
0.1–1 s. Phases are aligned to 30 fps. The target defaults to the
selected reference's entry XY at surface elevation. An explicit world
target must lie within the resolved surface region. Releasing the
last contact or acquiring from a contact-free entry requires explicit
airborne intent in acquire/release. A foot released during acquisition
of a body contact lifts 40 mm during its release ramp. The ending
snapshot records the fully held world anchors and surface identities.

`body.balance` is a slow approach over one captured floor sole. It
uses the pelvis projection as a body-center estimate. The rectangular
footprint proxy spans the measured heel and forefoot and has a
half-width of 15% of their horizontal separation. The endpoint needs
at least 5 mm inward margin, unchanged pelvis height, and no more
than 220 mm of horizontal shift. The other sole must stay at least
20 mm clear of the floor. Approach defaults to 1.5 s (1.2–3 s) and
hold to 0.5 s (0.2–1 s). The measured settled margin and free-sole
clearance are reported per frame. This is a geometric check for slow
support. It provides no dynamic balance guarantee.

The verified case sets, outstanding coverage, and source identities
are tracked in the [stage receipt](../../to%20do/stages/receipts/05.6b.md).
