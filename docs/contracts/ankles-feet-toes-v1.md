# Ankle, foot and toe mechanics v1 — profile 8

Stage 05.5 uses the existing typed fragment and Blender baking transaction.
The builder is `feet.mechanics.v1`, definition version 1. The ranges below
are reviewed within the rig and entry limits recorded in the [Stage 05.5 receipt](../../to%20do/stages/receipts/05.5.md).

## Calibration and contacts

`calibrate_feet` extends a bound profile to version 8. Capture a fresh entry
after migration. The rig's rest skeleton and mesh remain the sources of
calibration. The existing sole is preserved. New heel and forefoot points use
the longitudinal extent of low, weighted foot geometry on the sole reference
plane. All three points are rigid ankle landmarks in metres, including on
rigs without a toe bone. They can be measured as world positions.

Free ankle flexion and tilt are signed swing/twist projections relative to
the shin. Flexion uses its existing calibrated axis. Tilt uses the mirrored
longitudinal component of the calibrated parent frame. Toe curl uses the
mapped toe's parent-relative flexion. Fine toe controls are available per side
only where mapped. Profile 8 retains the prior geometric knee, hip and hand
measurements. The existing sole path remains available to profiles 1–7.

Each fragment holds the captured opposite floor sole. Free local
articulation begins with an inactive selected sole and requires at least
55 mm measured clearance of its sole reference. Swing phases release the
selected sole before moving it. Landing uses an explicit acquisition
interval and captures the solved floor point at the start of that interval.
The acquired target remains fixed until its release. A final measured-entry
return reacquires the selected sole only if it was active at entry.

For a heel or forefoot pivot, the adapter computes the ankle position from
the captured world contact and the rotated rigid offset. It applies the
existing leg IK with the captured knee plane, and checks the solved contact
over the full phase. Position tracks and independently prescribed hip/knee
targets cannot compete with that IK target. A complete roll transitions
through heel, level sole and forefoot contacts at the authored phase
boundaries. No pelvis or rig-object translation is authored.

## Per-movement envelopes

Common parameters are side left/right, duration 1 s per transition (0.8–2 s),
and hold 0.2 s (0–0.5 s), aligned to 30 fps. Durations for landing and
contact switches include a minimum settling interval as needed. The default
return restores measured entry except placement, which acquires the
destination. Roll and tap always recover. Invalid reach, calibrated joint
bounds, conflicting support, missing anatomy and floor clearance reject.

| ID | Default and bounds | Frame, entry and ownership |
| --- | --- | --- |
| `ankle.flex` | +12°, −18 to +18° | Free mode changes ankle flexion relative to the shin. Pivot mode rotates about the captured heel for toes-up or forefoot for toes-down and may solve the selected thigh and shin. |
| `ankle.tilt` | +8°, −12 to +12° free, ±2° supported | Free mode changes the mirrored parent-relative ankle tilt. Supported mode rolls around the longitudinal foot axis at the captured heel. |
| `foot.place` | +.05 m, −.06 to +.09 m, .07 m clearance (.045–.13 m) | Forward in the entry pelvis frame or an explicit world sole target. Lift, travel, land and acquire. Owns the selected leg chain. |
| `foot.lift` | .07 m, .045–.13 m | World vertical lift from a captured selected floor sole. Owns the selected leg chain. |
| `foot.pivot` | +12°, −20 to +20° | Yaw about the captured heel by default, or forefoot. Owns the selected leg chain. |
| `heel.raise` | 12°, 3–18° | Foot-frame pitch around the captured forefoot. Owns the selected leg chain. |
| `toe.raise` | 10°, 3–15° | Foot-frame pitch around the captured heel. Owns the selected leg chain. |
| `foot.roll` | 9°, 3–15° | Heel support to level sole to forefoot, then measured-entry return. Owns the selected leg chain. |
| `foot.tap` | 0 m, −.06 to +.09 m, .07 m clearance (.045–.13 m) | Released lift, world floor acquisition, release and recovery. Target may be relative or an explicit world sole point. Owns the selected leg chain. |
| `toes.curl` | +15°, −12 to +24° | Parent-relative flexion on the mapped toe of a raised free foot. Owns that toe only. |

Supported envelopes are conditional on captured flat entry, reachable ankle
positions, joint bounds and measured floor clearance. The common motion,
contact, floor, speed and acceleration tolerances apply. Toe articulation
does not affect availability of rigid contacts. The scope is the authored
floor and foot references, with no terrain fitting, shoe deformation or
general contact transfer.
