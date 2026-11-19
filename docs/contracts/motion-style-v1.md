# Local motion styles v1 — Stage 05.7b

Stage 05.7b is complete in the reviewed envelopes recorded in its receipt.
Other authorable anatomy and parameter combinations retain experimental status.
Use `movement_library.styles.apply_style` on one authored `MotionFragment` with
an explicit tuple of control IDs. This is not a general recipe composer.

## Definitions and priority

All styles use finite intensity 0–1, default 0.5. Zero returns the original
fragment. Invalid IDs, unavailable controls, nonfinite values and boolean
intensities reject. Entries still pass the normal fragment validator.

| ID | Transformation at intensity 1 | Restrictions |
| --- | --- | --- |
| style.fluid | Seventh-order smoothstep, zero endpoint velocity/acceleration/jerk | Explicit fixed path; blend continuously from original easing |
| style.robotic | Initial hold of 20% of each selected transition, then quintic easing | Free head angles/elbow flexion; sole contacts only |
| style.heavy | Quintic easing of squared normalized time | Slower preparation and later effort; no mass simulation |
| style.playful | Quintic easing of `1 - (1 - t)^2` | Earlier excursion and gradual recovery; no random jitter |
| style.exaggerated | 1.25 times optional intermediate excursion from entry | Returning scalar upper-body channel; explicit amplitude permission |
| style.tired | 0.75 times optional intermediate excursion from entry | Same restrictions as exaggerated |

Fluid, heavy and playful linearly blend the original eased progress with the
styled progress using intensity. They preserve the geometric path, duration,
track boundaries, endpoints, contact schedule and unrelated tracks. Endpoint
smoothness guarantees apply at full intensity; a partial blend retains the
corresponding contribution from the source easing. Smoothness is not global speed.
Normal measured speed/acceleration and geometry checks remain mandatory.

Amplitude changes require `amplitude_unlocked=True`: this declares intermediate
authored waypoints optional, not permission to override locked goals. Entry and
return stay fixed; any selected locked non-entry goal rejects. Supported channels
are head/torso angles and elbow flexion, with only sole contacts. Nonreturning
paths, contact-driving channels and quaternion extrapolation reject. Further
stroke, torso and step compatibility passed the scoped stage matrix.

All transforms reject overlapping intermediate locked goals and delayed measured
bindings. Style stacking rejects; use the original source for a replacement.
The ordinary bridge retains capability, continuity, ownership and range checks.
Authoring success does not certify a solved motion or a reviewed rig envelope.

## Serialized extension and narrow edits

`CurveSpec.style_timing` is an optional additive v1 extension, like existing
world-look and contact-target fields. It contains a versioned `StyleTimingV1`
record for fluid/heavy/playful. Absent/null means the original sampler exactly;
serialization omits a null extension, preserving old serialized curve identity.
Other missing fields, unknown styles and unsupported extension versions reject.
Generated schemas remain derived from the Python records.

`StyledFragment` stores the result, original fragment/instance IDs, canonical
source SHA256, style ID, intensity, selected controls and amplitude permission.
`restyle` verifies the supplied original source hash and replaces only this
application's intensity. It cannot silently restyle a changed source.
The style registry is exposed through the profile catalog with experimental tags;
direct standalone style building rejects because a style needs a source fragment.

The evidence adapter stores `style.json` and `source-fragment.json` alongside
the normal typed records and binds their hashes into the hashed result. Saved
motion is independently replayed before rendering. Acceptance requires actual
inspection of both full-motion views and the existing storage-v2 closure gates.
