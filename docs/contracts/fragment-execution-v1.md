# Implemented single-fragment execution v1

Stage 04 handoff, 2026-10-19. Uses the unchanged schema-v1 records from
[movement-api-v1](movement-api-v1.md) and calibration-v1 frames from
[rig-semantics-v1](rig-semantics-v1.md). Stage 05.1a now registers [five head/neck movements](head-neck-v1.md), with an explicit world-aim curve/profile extension.
This bridge is the shared execution path for later body-region builders and compilers.

## Implemented boundary

Pure functions live in `avatar_app.movement_library.compiler`, with no bpy/model import:

```python
instantiate_movement(id, parameters, *, instance_id, profile, entry_state, catalog) -> MovementInstance
build_fragment(instance, entry_state, profile, surfaces, catalog) -> MotionFragment
prepare_fragment(fragment, entry_state, profile) -> ExecutableMotion
sample_motion(executable, time_s, measured_state, execution_cursor) -> FrameTargets
ExecutionCursor()  # one mutable cursor per run, not serialized or shared
```

`instantiate_movement` takes a parameter dictionary, converts JSON spatial arrays into
immutable tuples, validates defaults/types/capabilities and checks the actual measured
entry conditions/support requirements. The catalog pins one exact version per ID; callers
requiring a persisted version call `get_movement(id, version, catalog)` first. No latest
version fallback or raw bone-name input is accepted.

`build_fragment` calls the application's trusted builder with
`(instance, entry_state, profile, surfaces)`. Builders are pure data authors, returning a
MotionFragment. Resolved surfaces are immutable legacy `Surface` records; the existing
floor is world height zero. The bridge validates provenance, owned chains, entry state,
frames, units, shape and budgets. Definition/fragment exit requirements become measured
end goals. A hand endpoint builder must explicitly own the wrist, forearm and upper-arm
chains. Serializing a builder ID never imports or evaluates executable user text.

`prepare_fragment` validates the fragment and entry, detects discontinuous explicit
starts, prepares source maps and runtime bindings, and keeps the entry snapshot immutable.
An active entry contact needs an explicit continuation/release interval at time zero.
Dropping it from the authored data cannot silently release support. A goal interval must
contain an execution sample (including the exact capped final sample); otherwise it fails
UNSUPPORTED_GOAL with a timing requirement, rather than being silently marked successful.

There is no graph scheduling, owner arbitration, movement selection, style/pattern
generation, loop expansion or general recipe compilation in this module. Stages 06/07
will consume the same ExecutableMotion/FrameTargets representation and sampler.

## Stage 05.7a timing and finite repeat

`patterns.repeat_fragment(fragment, count, entry=entry, profile=profile)`
implements the initial `timing.repeat` transform. Pass an authored fragment
and an explicit integer count. Count 1 returns the validated input. Counts
up to 128 are subject to the tighter expanded instance, duration, sample,
track, contact, phase, goal and source-map limits before copies are made.

For multiple copies the authored controls must return to the measured
entry at rest. The original unit and frame of each control are preserved.
The held support set must match at the seam, and its anchors must remain in
place. Consecutive held contact events are joined across the seam so the
executor keeps the anchor. Time is measured in seconds. The total duration
is the original duration times the requested count.

Later copies retain original instance IDs in track and contact provenance
alongside deterministic occurrence IDs. Phase landmarks and goals move with
each copy. The result is prepared through the same single-fragment bridge
and has finite playback with empty loop metadata. This first version covers
zero net root displacement and resting seams.

- `hold_fragment` appends a bounded time interval to the terminal targets,
  terminal goals and contacts still held at the end. `transition_fragment`
  builds a smooth curve from measured entry controls to explicit targets in
  the same semantic frame while continuing the captured contacts.
- Overlap accepts disjoint owned chains with a shared contact schedule.
  Synchronization aligns named landmarks by delaying one operand. Finite
  phase offsets use a signed fraction of the second fragment's duration.
  Positive offsets delay the second operand. Alternation schedules one
  compatible pair in turn and optionally applies finite repeat to the pair.
- The initial mirror supports calibrated scalar controls and mirrored
  side-specific anchors. Explicit world anchors reflect through the entry
  body's sagittal plane. Other track representations require calibration
  and evidence before support is added.
- Bilateral strokes reuse the calibrated `arm.stroke` path on each arm.
  The alternating form rounds its half-cycle phase to a frame and holds
  the delayed endpoint at its measured entry before the stroke. The shared
  `smootherstep` curve adds a quintic ramp with zero endpoint acceleration.
- `torso_pattern` reuses the calibrated supported sway and spine-wave paths.
  Both start with two captured floor soles and return to the entry pose.
  Undulation can add a phased 5° swing for the selected arm or both arms.
- `step_pattern` authors one to four alternating floor steps from two captured
  soles using the calibrated `body.step` parameters. Each swing carries the
  authoring foot frame and anchor forward by one stride. The body advances
  half a stride per step. The bridge only admits the multi-step schedule when
  the release/acquisition windows alternate and at least one sole stays held.
- `verify_translation_loop` attaches `LoopSpec` after checking the baked
  cycle's measured root, pose, support anchors and angular velocities at the
  seam. Translation uses the fixed entry-body frame. Passing a finite step
  fragment to the ordinary bridge still gives finite playback. Loop checks
  currently cover translation with unchanged heading.

The [05.7a receipt](../../to%20do/stages/receipts/05.7a.md) records the
measured seam, native checks and saved-motion visual evidence.

| Stage ID | Arguments and authored bounds | Entry, ownership and exit |
| --- | --- | --- |
| `timing.hold` | Explicit positive duration with total motion limited to 60 s | Extends the first fragment's terminal targets, goals and contacts. Inherits its frames and chains. |
| `timing.transition` | Explicit framed targets and duration from 1 ns to 60 s | Each target starts at the measured value in the same unit and frame. Owns the target's chain and requires normal numeric checks. Ends at the requested targets. |
| `timing.repeat` | Explicit count 1–128 subject to the expanded budgets | For multiple copies, the input returns to the measured stance at rest with matching support. Ownership and frames come from the input. |
| `timing.alternate` | Two explicit compatible fragments and pair count subject to repeat budgets | The second starts after the first. Foot support continues across the pair. Additional pairs require a returning seam. |
| `timing.mirror` | One fragment with calibrated scalar mirror rules | Reflects its scalar tracks and goal targets and changes side-specific contact IDs. Explicit world anchors reflect in the entry sagittal plane. An incompatible explicit start fails preparation. |
| `timing.synchronize` | One named landmark per operand | Delays one compatible operand to align both landmarks. Preserves the independently authored frames and exit states. |
| `timing.phase_offset` | Signed offset from −1 to +1 second-operand cycles | Positive values delay the second operand. Its phase is authored against the shared entry and the complete support schedule must match. |
| `timing.overlap` | Two explicit fragments and a common entry | Requires disjoint owned chains and compatible support. Each fragment retains its authored duration and endpoint. |
| `pattern.steps` | Lead left or right, count 1–4, phase 0.7–1.4 s with default 0.8 s, distance 60–160 mm with default 100 mm, clearance 40–90 mm with default 60 mm | Profile-8 floor soles. Owns pelvis and the swinging leg's foot position and orientation during each step. Uses world targets and leaves the stance translated. |
| `pattern.strokes_synchronized` and `pattern.strokes_alternating` | Phase 1–3 s with default 1.5 s, hold 0–1 s with default 0.1 s, stroke amplitude 0–160 mm with default 80 mm. Count is explicit and bounded by expansion. | Both arms approach and recover at measured world wrist endpoints. Owns upper arm, forearm and wrist on each side. Alternating mode offsets the right arm by half a cycle rounded to the frame grid. |
| `pattern.sway` and `pattern.undulation` | Angle −20° to +20° with default 10°, phase 0.8–3 s with default 1 s, hold 0–1 s with default 0.1 s. Count is explicit. Undulation accepts optional left, right or both arms with a 5° swing. | Both floor soles start held. Uses calibrated torso or spine controls and a fixed world head aim. Follow-through adds upper-arm ownership. Returns to measured entry. |

Authored bounds are checked before execution. The reviewed rig and entry
envelopes are recorded in the Stage 05.7a receipt. All cases still pass through
the same contact, joint, speed, acceleration and preservation gates.

## Sampling and entry binding

Curves use the hold/transition descriptor. Linear easing uses `u`, smooth easing
uses `3u²-2u³`, and Stage 05.7a adds quintic smootherstep `6u⁵-15u⁴+10u³`
to the shared sampler and schema-v1 easing enum. Scalars and vectors interpolate
their values. Quaternions use normalized shortest-arc slerp and treat q and -q
as equivalent rotations.

Start a fresh cursor at time zero, call chronologically at intervals no larger than
1/30 second, and pass the previous solved MotionStateSnapshot. The cursor rejects a
different executable, revision/rig/profile, rewind or skipped boundary. Replaying a
baked Blender action does not call the sampler; restarting sampling needs a new cursor.
The initial state remains measured data, including explicit zero; no neutral reset occurs.

All newly activated measured-entry tracks bind from the **same supplied pre-application
snapshot** before any track is applied. Bindings are captured once and remain in the
per-run cursor. A non-frame-aligned activation binds on the first execution frame at or
after that logical time. Authored explicit contiguous starts must agree with the prior
authored endpoint; an explicit initial reset is rejected. Tracks hold their final target
through a following gap; the latest starting track for a control owns a shared boundary.

The shared executor uses `ceil(duration_s * 30) + 1` inclusive frames and caps the last
logical sample to duration_s. The baked duration can therefore include less than one
frame of endpoint quantization. Whole fragments remain bounded to 60 seconds, 1,801
samples, 256 tracks, 256 contact intervals and 128 source instances. Legacy ActionPlan
keeps its separate 12-stage limit.

FrameTargets carries typed targets, active contact events, measurable goals, source IDs
and permitted supporting chains. Hand-position targets declare forearm/upper-arm support
changes explicitly; unrelated chains remain locked. The frame carries no arbitrary
scene handles, executable expressions or serialized mutable cursor.

## Blender application and transaction

The existing entry points in `avatar_app.blender.motion` now accept either plan type:

```python
build_action_frames(handle, plan, progress=lambda fraction: None,
                    allow_experimental=False, *, profile=None)  # yielding transaction
build_action(handle, plan, progress=lambda fraction: None,
             allow_experimental=False, *, profile=None) -> dict
```

For ExecutableMotion the actual calibrated profile is required. The adapter in
`blender/primitive.py` performs read-only preflight before opening a candidate action:
profile binding, supplied-vs-current state, supported controls/surfaces, reachable hand
targets and support anchors. An incompatible entry returns ENTRY_MISMATCH and the
required measured/declared values; it does not reset the rig to make the input fit.

`bake_candidate_frames` retains **one frame loop and one keyframe-insertion block**.
The typed branch samples/applies/measures through FragmentAdapter.step; the legacy branch
retains its existing posing/contact behavior. Both use capture_sample, review_samples,
linear keys, progress yields and build_action_frames' commit/rollback transaction.
Typed execution does not expand frames into fake MotionStages or add another bake loop.

The initial application envelope is:

- Calibrated head/neck/torso/spine scalar controls. A chain's three swing/twist projections
  are solved together, preserving untargeted angular components. It uses actual calibrated
  parent frames and bind offsets, not global bone Euler values.
- World hand-position targets through the existing position_hand IK. An already bent
  measured elbow supplies its pole; the calibrated fallback handles a nearly straight
  chain. Reach is checked before candidate creation and during solving.
- Existing floor sole support, with explicit acquisition/release ramps and captured
  anchors, reusing the existing contact solver when correction is needed. Supported
  floor contacts have zero surface clearance.

Other calibrated quantities remain measurable but reject execution with MISSING_CAPABILITY
until their owning body-region stage adds a tested application adapter. Root travel,
general leg/foot targets, wrist/finger gestures, other surfaces and support-transfer
authoring are not implied by the sampler's scalar/vector/quaternion support. Extend this
shared adapter in the owning stage; do not introduce a private family executor.

Every frame is independently measured after application/solving. The shared floor/contact,
speed and acceleration gates remain 3 mm, 25 mm, 360 degrees/second and 3,000 degrees/
second-squared. Typed tracking goals use at most 3 degrees/10 mm, with stricter authored
goal tolerances retained. Unrelated joints/orientations are limited to 0.5 degree and
endpoints to 2 mm. Actual trajectories, source IDs, contact errors and goal violations
are recorded in the returned samples. A symbolic goal alone is never a success result.

Generator close, callback cancellation, solver failure, failed review and entry rejection
keep the previous action/slot, pose, modes, timeline, FPS/base/subframe and camera.
Typed results are not automatically repaired by shifting the root, which could violate
entry fidelity or unrelated targets. `allow_experimental` retains the legacy explicit
developer option; an unsuccessful candidate stays labelled experimental, never reviewed.

The typed result dictionary contains frames/action/review/before_repair/repaired/
experimental, a serialized **ending_state**, measured **samples**, and **source_map**.
Legacy results keep their existing ending_pose shape and caller behavior. No user-facing
UI or AI path was changed in this stage.

## Developer harness and durable fixtures

`tools/preview_movement.py` accepts explicit `--id`, `--version`, `--parameters` JSON
or `--parameters-file`, `--rig` (`demo`, `mixamo` or a supported FBX path), `--entry`,
`--output-dir`, optional `--render`, and explicit `--test-catalog`.
Production head/neck IDs use the profile-scoped catalog; test IDs require that flag. Test definitions are
application-owned functions in tests/primitive_fixtures.py, not user-visible presets.

Entry setup files use a developer-only versioned object with exactly
`schema_version:1`, `controls` (validated legacy pose controls) and `contact`. They set
a known fixture pose, after which the harness captures actual measured state/sole anchors.
They are not another motion graph or instructions interpreted as code. The saved library
entry itself is a schema-v1 MotionStateSnapshot, distinct from the static fixture setup.

PowerShell example, from C:/work11 (parameter file avoids native-shell JSON quoting):

```powershell
$stageBlender = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'
'{"angle":15,"duration_s":1.2}' | Set-Content artifacts/stages/04/cli-parameters.json
& $stageBlender --background --factory-startup --python-exit-code 1 `
  --python tools/preview_movement.py -- `
  --id test.head_transition --version 1 `
  --parameters-file artifacts/stages/04/cli-parameters.json --rig demo `
  --entry tests/fixtures/movement_fragments/v1/entry-bent-turned.json `
  --output-dir C:/work11/artifacts/stages/04/cli-preview --test-catalog --render
```

The output has profile/entry/instance/fragment/executable JSON, result.json with every
measured frame, and preview.blend with the real keyframed action. With --render it also
contains every numbered PNG under `front/` and `side/`, plus `front-sheet.png`
and `side-sheet.png` (left-to-right, top-to-bottom, all frames). New outputs use one
compressed scene and `preview-manifest.json` for entry labels, views and completion;
see [artifact storage](artifact-storage.md). Historical `frames/`, overview and
contact-sheet outputs remain preserved. Open preview.blend in Blender and play the
timeline to inspect motion directly. These are local diagnostic artifacts, not a new
user export UI.

`tests/fixtures/movement_fragments/v1/` contains generated schema-v1 data examples for
instance/fragment/executable/entry snapshot, neutral and bent/turned setup fixtures,
invalid number/frame and over-budget cases, and a manifest with bounds and baseline
revision. The pure sampling entry is test data; actual rig-measured entries live with
the Blender execution outputs. Regenerate with `PYTHONPATH=src` and
`python tests/primitive_fixtures.py`; no JSON schema is maintained separately.

`tests/test_primitive_execution.py` verifies pure imports, defaults/zero, entry rejection,
continuity, actual activation bindings, deterministic simultaneous activation, cursor
isolation, quaternion interpolation, bounds, contact continuation and goal sample coverage.
`tests/blender_primitive_execution.py` verifies demo/Mixamo neutral and bent/turned
execution, frame-by-frame playback, cancellation/failure preservation, reachable/unreachable
endpoints and legacy equivalence. It loads the pre-adapter legacy source from the Git
revision pinned in the fixture manifest; retain that history or provide that baseline
when reproducing the comparison. No AI/model call is required.

Stages 05–07 consume these boundaries. Add reviewed movement content in its assigned
stage, use prepare_fragment/sample_motion, and pass ExecutableMotion through this same
transaction. No general compose_recipe/compile_recipe was added here, and no Stage 05
movement catalog is advertised by the test-only preview.

## Stage 05.1b body-content extension

Stage 05.7b adds the optional [local style timing v1](motion-style-v1.md) curve
extension and source-bound style records. Absent extensions preserve legacy
serialized curves and sampled behavior; style evidence remains experimental
until its native and visual gates pass.

The production catalog now contains five head/neck and nine spine/pelvis IDs.
`--test-catalog` still selects only the isolated Stage 04 fixtures. Production
body IDs use the same `prepare_fragment`, sampler, adapter and transactional
baking loop. Torso movement uses calibrated spine angles plus an independent
world head-orientation hold. Pelvis movement explicitly opts into calibration
version 3 and applies the Hips bone transform while solving both planted legs;
the actual armature object root stays fixed. Reach rejection, captured knee-pole
continuity and identity preservation are part of this existing adapter.

The developer preview uses a full-body camera for body IDs and resolves its
output directory before passing paths to Blender's renderer. Version-1/2 data,
legacy action callers, rollback, cancellation and source maps retain their prior
meaning. No generic recipe composer or multi-instance compiler is introduced.
See [spine/pelvis v1](spine-pelvis-v1.md) and the Stage 05.1b receipt for the tested
envelopes and scoped review records.
