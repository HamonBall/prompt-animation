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

## Sampling and entry binding

Curves use the existing hold/transition descriptor. Smooth easing is `3u²-2u³`; linear
easing uses u. Scalars/vectors interpolate their values and quaternions use normalized
shortest-arc slerp, treating q and -q as equivalent rotations. No new curve enum/schema
or per-family sampler was introduced.

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
