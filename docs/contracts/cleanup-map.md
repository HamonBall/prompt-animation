# Stage 01 cleanup map

Status: implemented and regression checked, 2026-10-14.
Baseline source: `81e4ee4cdd6e712c71fad25997f08675a4837e73`.
The implementation is an uncommitted working tree. `.gitignore` was already modified
before this stage and was not changed by this work. New stage documents and receipts
are locally ignored by its existing `*.md` rule; they remain available on disk.

## Active entry points and handoff

| Path | Classification and actual purpose |
| --- | --- |
| `launch_avatar.py` → `avatar_app.main.main()` | Active application entry; registers the Avatar operators and prompt/settings panels. |
| `main.py` | Active main-thread commit, prompt worker/modal builder, progress, cancellation, stale-result checks, load recovery and play-once flow. Its `build_transition()` is the **current PosePlan adapter** to `action_from_pose()`/`build_action()`, and remains active. |
| `planning/action_interpreter.py` | Active UI planner; decodes poses, complete staged actions, foundation adaptation, stage edits and timing changes. No executable model output. |
| `planning/pose_interpreter.py` | Shared anatomical conversion/static constraints and retained general-pose interpreter used by pose tooling. |
| `pose.py` | Blender-independent `PosePlan`, control limits, immutable updates and validation. |
| `motion.py` | Blender-independent `ActionPlan`, `MotionStage`, `ContactConstraint`, `Surface`, validation, sampling, stage patching and timing. The 12-stage/60-second limits remain unchanged. |
| `models.py` | Shared `PlanError(ValueError)`; retained at its original import path. |
| `planning/movements.py`, `presets.py`, `routes.py` | Active shared construction helpers, internal ready motions and conservative shortcuts. Retained for migration in Stage 08. |
| `planning/local_model.py`, `reference.py` | Active local inference and optional supplied-URL context; no changes to model, runtime, networking or configuration. |
| `blender/kinematics.py` | Shared `aim(bone, direction)` and `solve_leg(handle, side, target)`, extracted without changing either function body. |
| `blender/pose.py` | Active anatomical application, arm IK and static-pose transition builder. Imports both shared IK helpers from `kinematics`. |
| `blender/motion.py` | Active reviewed/yielding action executor and rollback. Imports `solve_leg` from `kinematics`. |
| `clips.py`, `blender/clips.py` | Active explicit clip catalog and retargeting; the Blender adapter imports `solve_leg` from `kinematics`. |
| `blender/avatar.py`, `demo.py`, `scene.py`, `geometry.py` | Active import/isolation, procedural avatar, preview environment, geometry caches and measured support queries. |

Stage 02 can locate the error type, existing plan types and IK at these paths.
No `movement_library` package, new contract version, movement ID, calibrated axis,
composer or compiler was implemented in Stage 01. Future stages must publish their
own contracts and evidence. Historical design prose using `MotionPlan`/`PlanPatch`
does not describe current importable classes.

`aim` and `solve_leg` operate on Blender pose-bone/armature-space vectors, using
the handle's existing axes and bone lengths. They return no data record and retain
their previous behavior, including reach failure. This extraction does not
establish the future calibrated anatomical semantics required by Stage 03.

## Dependency evidence and removals

Before deletion, source/test/tool searches showed the following complete dependency
island. The launcher/UI imported the general action planner, never this island.
The only live dependency crossing its boundary was the two IK functions in the
old animation module; all live consumers were migrated first.

| Removed path/symbol | Evidence and replacement |
| --- | --- |
| `planning/interpreter.py` | Restricted single-pose command matching; called only by the retired planner and legacy tests/smoke. General action/pose interpretation remains. |
| `planning/ai.py` | Single-pose schema/system prompt and decoder; callers were the legacy tests and `benchmark_interpretation.py`. Current `action_interpreter`/`pose_interpreter` remain. |
| `planning/validation.py` | Validated only the retired `MotionPlan`/`PlanPatch`; imported by that island and the old animation module. Current pose/action validators remain. |
| `MotionPlan`, `PlanPatch` in `models.py` | Their executable consumers belonged to that island. Removed the records and unused dataclass import; preserved `PlanError`. |
| `blender/animation.py` | Its `build_transition()` implemented the retired motion contract and had only legacy smoke/preview callers. Extracted `aim`/`solve_leg` to `blender/kinematics.py`; migrated pose, motion, clips and the identity-performance check. |
| `tools/check_preview.py` | Metrics around the retired transition only. General pose checks, the migrated smoke and prompt workflow supply active evidence. |
| `tools/benchmark_interpretation.py` | Benchmarked the retired three-field schema and rejected now-valid unilateral/general actions. Retained `benchmark_poses.py` and `benchmark_actions.py`. Prior benchmark artifacts were preserved. |
| `tests/test_ai.py`, `tests/test_planning.py` | All imports/fixtures used retired types. Useful checks were migrated or matched to existing active coverage below; retired vocabulary/relative-operation assertions were not kept. |

All eight file-removal paths were resolved and checked inside `C:/work11` before
removal. No recursive cleanup was performed. Source modules decreased from 26 to
23; `inventory.json` records the before/after lists and current import graph.
The two helper ASTs match exactly (`helper-equivalence.log`). Searching executable
source/tests/tools for the removed imports/types/tools leaves zero matches.
Remaining names in the stage specifications and historical architecture proposals
are reference prose; this map records the replacement paths.

## Tests and assertion migration

Baseline unit discovery passed 79 tests. Twenty tests were in the retired pair.
Fifty-nine existing tests remain, seven active-path validation tests were added,
and the missing-runtime test was transferred to `test_local_model.py`: **67 pass**.
Counts describe discovered methods, not the number of subcases or capabilities.

| Underlying legacy check | Active coverage after cleanup |
| --- | --- |
| Initial revision, multifield edits, source immutability | `test_action_validation.py::test_creation_and_multifield_patch_preserve_unrelated_data` and existing pose/motion revision tests. |
| Request/current result supplied as quoted data | `test_action_validation.py::test_request_and_current_action_are_quoted_data`. |
| Malformed/duplicate JSON, unknown controls, nonfinite values, booleans/strings as numbers | `test_action_validation.py::test_malformed_duplicate_nonfinite_or_wrong_type_replies_are_rejected`, existing pose/action validation tests. |
| Rejected requests, missing current plan, invalid/duplicate stage IDs, boundary duration and previous-result preservation | `test_action_validation.py::test_rejected_requests_and_invalid_stage_patches_keep_the_original`. Negated wording cannot take the positive exact route; a clarifying response applies no motion. |
| Timing preserves unrelated pose/contacts | `test_action_validation.py::test_timing_edit_preserves_geometry_contacts_and_contact_ramp_fractions`, existing motion/preset retiming tests. |
| Checked-data summary instead of misleading model prose | `test_action_validation.py::test_static_pose_summary_uses_checked_values`. This applies to the existing static-pose path, not a new general semantic verifier. |
| Failed/truncated inference preserves input | `test_action_validation.py::test_inference_errors_and_truncation_do_not_mutate_source_plan`, existing streamed-runtime tests. |
| Missing runtime | `test_local_model.py::test_missing_runtime_is_an_explained_failure`. |
| Stale result | Existing `blender_ai_ui.py` commit identity check and modal boundary checks; no obsolete patch record restored. |
| Import/material/scene preservation, invalid target and interrupted-build rollback | Migrated `blender_smoke.py`, existing general-pose, UI and airborne-cancellation tests. |
| Exact commands avoid inference | Existing neutral-pose and internal-foundation tests; no single-pose vocabulary restriction restored. |

The retired API's symmetric-only controls, three-field add/multiply operations and
single-pose-only rejection policy are not the current contracts. Its word-specific
preservation/timing guards were not transplanted into the general AI planner.
Current validated patches preserve untouched data; comprehensive free-language
clause and edit-intent verification remains assigned to Stages 10/11.

## Retained tools and references

`tools/benchmark_poses.py`, `benchmark_actions.py`, `inspect_rig.py`,
`retarget_clip.py` and `setup_local_ai.ps1` have active general-pose/action,
inspection, explicit-clip or runtime responsibilities and remain unchanged.
`diagnose_fbx.py` and `blender_hiphop_stage.py` are standalone, intentionally retained
diagnostic/scene references. Neither is imported by application startup. Their
scene-clearing/hardcoded asset/material behavior is for a disposable process,
not the active avatar preview; they were inspected but not executed here.

Personal FBX/media, runtime/model binaries, configuration, original Git state and
prior artifacts were not removed or modified. New evidence is under
`artifacts/stages/01`. Optional `--output-dir` flags in the preset/clip test
harnesses keep their reports separate from existing baseline reports.

## Verified local commands

Working directory: `C:/work11`. Blender 5.1.0; its Python is 3.13.9.

```powershell
$stagePython = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
$stageBlender = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'
$env:PYTHONPATH = 'C:\work11\src'
& $stagePython -m unittest discover -s tests -p 'test_*.py' -v
& $stageBlender --background --factory-startup --python-exit-code 1 --python tests/blender_smoke.py
& $stageBlender --background --factory-startup --python-exit-code 1 --python tests/blender_presets.py -- demo jump walk run wave lie --output-dir C:/work11/artifacts/stages/01/presets
& $stageBlender --background --factory-startup --python-exit-code 1 --python tests/blender_clips.py -- --output-dir C:/work11/artifacts/stages/01/clips
& $stageBlender --background --factory-startup --python-exit-code 1 --python tests/blender_ai_ui.py
& $stageBlender --background --factory-startup --python-exit-code 1 --python tests/blender_preset_ui.py
& $stageBlender --background --factory-startup --python-exit-code 1 --python tests/blender_preview_performance.py
& $stageBlender --factory-startup --python-exit-code 1 --python tests/blender_prompt_workflow.py -- after
```

The foreground workflow was launched with `Start-Process -WindowStyle Hidden`
and stdout/stderr redirects for both before/after checks. Its real event loop
verified worker/modal generation, actual screen animation, one-shot final-frame
stopping and cancellation restoration. It is not a mocked or background playback
check. All commands above exited 0.

`blender_poses.py -- --avatar 'Hip Hop Mixamo.fbx'` exited 0 with all six poses and
unreachable-wrist rollback. The Andrejs variant exited 1 at its static lying
bounding-box assertion; the pre-cleanup source snapshot reproduced exactly the
same failure. See the receipt for this preserved issue and measured evidence.

## Evidence and known limits

`artifacts/stages/01/workflow-equivalence.json` compares 208 matched frames of the
real prompt result: maximum world head/left-hand/left-foot coordinate difference
is **0 m**. This is the measured coordinate envelope checked, not a claim about
every possible animation. The original scene and previous motion/history survive
the UI cancellation case before and after extraction.

The rendered `visual/prompt-contact-sheet.png` was opened and inspected: five
sampled frames show the left-hand raise, alternate wave positions and return, with
planted feet and unchanged appearance. Full-motion numeric samples cover all 208
frames. A contact sheet alone does not certify every intermediate pose.

The retained Andrejs static lying test measures rotated local bounding-box corners
at **-0.009739291854202747 m**, although evaluated skin minimum is
**0.000000000191789723 m**. Both values are identical against baseline HEAD and
current source. The unchanged test still fails its 2 mm box assertion. This is a
pre-existing measurement-test issue; Stage 01 did not relax it or change the active
solver to satisfy it. Its later wrist rollback branch is not reached on that rig;
independent imported smoke and cancellation checks still pass on both rigs.

No real-model benchmark was rerun for this cleanup. Creative-path execution used
an explicit deterministic response, as specified by Stage 01. No new movement
library, joint semantics, loop capability, object interaction or AI behavior is
claimed. Stage 02 is the next work package, not part of this implementation.
