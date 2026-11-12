# Neutral pose and artifact storage maintenance

Status: **complete**. Started 2026-10-23; completed 2026-10-26 after an
interruption. Baseline: `7871747` (spine and pelvis). Changes remain uncommitted.
No `problems/` content, stage 05.2/05.3a, imported asset, rest skeleton, pose
omission rule, `.gitignore`, persistent Blender preference or dependency changed.

## Package 1 — neutral workflow: passed

`tests/blender_neutral_workflow.py` exercised the actual application operator and
state/history path on the demo, `Hip Hop Andrejs.fbx` and `Hip Hop Mixamo.fbx`.
Fresh and repeated loads display the final neutral frame with a valid action and
slot and a fresh history. An explicit neutral request after asymmetric controls
clears the prior goals. Reset remains an animation: its displayed first frame is
the prior pose; playback ends neutrally. Explicit zero elevation and wrist pitch
still override defaults. No startup/reset defect was reproduced, so application
posing code was retained.

The default camera/frame was inspected in the live Blender UI on 2026-10-23:
demo neutral at frame 61/61, relaxed symmetric arms, both feet visible. The UI
inspection used the computer-use skill. `neutral/ui-state.json` records the app
state; `neutral/demo-app-default-camera.png` records the matching camera render.

`tests/blender_movement_arm_preservation.py` checked complete baked playback of
all five head/neck and five implemented torso IDs from the bent/turned fixture,
on demo and Mixamo. It measures local arm angles and head-movement hand positions
or torso-movement hand positions relative to the existing arm parent. The original
fixture and ordinary movement preservation semantics remain unchanged.

Entry fixture, actual entry kind, parameters, initial/current frame and explicit
default-parameter labels are recorded by new manifests/reports. The maintenance
audit appends corresponding labels for historical cases without renaming them.

Evidence: `artifacts/maintenance/neutral-artifacts/neutral/` and `preservation/`.
Maximum final neutral direction error was **0.018334 degrees** (limit 0.1).
Across complete head/torso playback, maximum unrelated arm drift was
**0.000229 degrees** and hand endpoint drift **0.000003499 m**, within the
unchanged 0.5-degree/0.002-m limits.

## Package 2 — demo joint appearance: passed for inspected diagnostic poses

Inspected `demo.py`, complete rigid weights and armature modifiers, the actual
continuous elbow/wrist bone endpoints, and front/side/three-quarter renders of
neutral, bent/turned, bilateral 30-degree and 90-degree elbow diagnostics.
Segment seams are visible; no unintended open joint gap, reversed surface or
disconnected bone was reproduced. No mesh or solver modification was indicated.
The same unchanged geometry therefore applies before and after this maintenance.
Diagnostic images are named `neutral/demo-*-before-*.png`; geometry/rest/count
records are in `neutral/demo-geometry-before.json`. This is not verification of a
future full arm movement envelope.
The unchanged demo has **17 bones, 27 meshes and 2,322 vertices**. Both elbow and
wrist endpoint connections were checked within 0.000001 rig units.

## Package 3 — storage: passed, including verified historical compaction

Shared atomic compressed saves, packed-resource checks, preference restoration,
producer leases, canonical scene resolution and versioned completion manifests
are implemented. Routine second-scene writes were removed. Render-only passes
open stored scenes and preserve numeric results. Readers, review/publishing tools,
the legacy head-stage inspection script and additional evidence writers were
updated. The contract and exact commands are in `docs/contracts/artifact-storage.md`.

The initial stage inventory was 22.042 GiB: 520 `.blend`, 216 `.blend1`, 44,936 PNGs
and 1,559 JSON files. Scene compression was already enabled in the sampled old
files; duplicate embedded avatar resources were the dominant cost. The original
inventory is `inventory-before.json`. Final accounting is in `storage-summary.json`:

| Storage | Before | After | Net freed |
| --- | ---: | ---: | ---: |
| All artifacts, including new maintenance evidence | 22.05 GiB | 14.76 GiB | **7.30 GiB** |
| Existing stage evidence | 22.04 GiB | 14.07 GiB | **7.97 GiB** |

Stage scene counts fell from **520 to 267 `.blend`** files and **216 to 199
`.blend1`** files. All **44,936 original PNGs / 896,995,536 bytes** are preserved:
44,436 numbered frames, 458 sheets and 42 other images. All **1,559 original JSON
files / 174,228,555 bytes** remain; the additional 262 JSONs are migration maps.
Logs and historical receipts were preserved. Retained files within the assigned
roots are **195 `.blend1` backups**, classified as different actions or unable to
match current numeric evidence. Four further backups lie outside these roots and
were not compacted. Retention is intentional under the assignment, not an assertion
that those older motions equal current cases.

The compactor processed **262 case directories with zero validation failures** in
the completed migration. A second application reported every directory already
compacted, removed nothing further, and left every stage file's path/size/mtime
inventory unchanged (`idempotence-review.json`). The canonical-scene read-only
audit passed for **252 owned movement cases** and all **43,594 declared main-view
frames** (`evidence-audit.json`); other diagnostic images remain preserved too.
That audit also appends entry/default-parameter labels for the historical cases.

Compaction is dry-run by default, limited to the two assigned roots, and validates
stored motion without rebuilding it. Each case has original hashes and a migration
record; each candidate is reopened in a separate Blender process. Distinct camera
views are embedded before redundant scenes are retired. Different/unverified
actions and backups remain. Material-name aliases are compared by actual content.
Every subsequent run has a separate evidence directory; previous maps are retained.
Maximum fresh-reopen `value_error` was **0.000022492** in each control's declared
comparison units (verification gate 0.001); source/candidate sampled pose residual
was **0**. Across the same migrated cases, median compressed save time was
**0.161 s** and median fresh candidate load time **0.109 s**. A representative
Mixamo alias-copy check recorded **0.165 s source load / 0.146 s candidate load**,
**0.162 s save**, retiring **64,086,184 bytes**. These are local measurements,
not a promised compression or speed ratio; old scenes were already compressed.

## Commands and validation

All commands ran from `C:/work11`. Python:
`C:/Program Files/Blender Foundation/Blender 5.1/5.1/python/bin/python.exe`.
Blender: `C:/Program Files/Blender Foundation/Blender 5.1/blender.exe`, 5.1.0.
Blender checks use `--background --factory-startup --python-exit-code 1 --python`.

- `-m unittest discover -s tests -p 'test_*.py' -v`: 163 tests in the full run
  before the separately added playable-backup fixture, 158 passed,
  5 skipped (four separately run Blender integration cases and a Windows junction
  fixture whose creation returned Access denied). Reparse-metadata rejection and
  resolved-root escape tests passed. `unit-tests-final.log`.
- `tests/test_artifact_compaction_blender.py --blender-integration -v`: all four
  copy-based cases passed: identical scenes, distinct cameras, differing actions,
  corrupt file; reapplication performed no further removals. A fifth focused real
  playable-backup-only copy check also passed (`--blender-integration -k backup`).
  Logs: `compaction-integration-final.log`, `backup-only-integration.log`.
- A Mixamo copy with `Floor`/`Floor.001` material aliases passed fresh numeric,
  geometry/material/resource and playback verification while retiring its duplicate.
  `material-copy-validation/`.
- `tests/blender_neutral_workflow.py`: all three avatars passed. Commands and
  rendered diagnostic views are recorded in `neutral-workflow-final.log`. The final
  run explicitly resets from the application-owned ActionPlan path on every rig.
- `tests/blender_movement_arm_preservation.py`: all 20 rig/movement combinations
  passed. `preservation.log` and `preservation/review.json`.
- `tests/blender_movement_spine_pelvis.py -- --case torso.wave.default --output-dir
  artifacts/maintenance/neutral-artifacts/new-spine --render`: both rigs passed.
  Render-only reruns skipped an unchanged case, rerendered after removing one
  expected frame, and rejected stale fragment data. Numeric results remained
  byte-identical; the original test PNG was restored. `resume-review.json`.
- `tests/blender_movement_head_neck.py -- --case nod-default --output-dir
  artifacts/maintenance/neutral-artifacts/new-head --render`: both rigs passed.
  Final render-only passes use the saved rig/action and preserve result JSON hashes.
- `tests/blender_primitive_execution.py -- --output-dir
  artifacts/maintenance/neutral-artifacts/primitive-regression`: passed, including
  playback, endpoint checks, cancellation/failure rollback and legacy equivalence.
- `tools/preview_movement.py -- --id head.nod --version 1 --rig demo
  --parameters-file artifacts/maintenance/neutral-artifacts/cli-parameters.json
  --entry tests/fixtures/movement_fragments/v1/entry-bent-turned.json
  --output-dir artifacts/maintenance/neutral-artifacts/cli-final --render`: passed,
  49 frames, one canonical scene and front/side evidence.
- `tests/blender_artifact_store.py`: real repeat-save, injected replacement failure,
  preference restoration and fresh playback checks on demo and Mixamo.
- `tools/compact_stage_artifacts.py --jobs 2`, then `--apply --jobs 2`: migration
  completed, followed by a no-change `--apply --jobs 2` check. No whole-suite
  rendering was used for compression. Migration runs are under `compaction/runs/`;
  per-case `artifact-migration.json` files retain original hashes, prior maps,
  preserved camera views and verification paths.
- `tools/inspect_stage_artifacts.py`: all owned cases passed; every expected image
  is present, sampled headers are valid, and result hashes match historical visual
  markers. Fast directory enumeration is paired with unchanged global PNG byte
  totals rather than repeatedly decoding/reopening all historical images.
- `artifacts/maintenance/neutral-artifacts/summarize-storage.py`: before/after
  accounting and preservation assertions passed. `git diff --check` and changed
  Python AST parsing passed. The Windows junction fixture remains the one platform
  setup limitation; reparse rejection itself passed.

Blender logged thumbnail-cache access errors and small shutdown allocation reports
on some background runs; the actual tested scene/image writes and process exit
results determine the checks above.

## Handoff and limits

All three maintenance packages are complete within their stated scope. No neutral
or demo mesh defect was reproduced, so their existing implementation was retained.
Distinct/unverified historical backups remain available; deleting them would exceed
the evidence-preservation rule. No future arm ranges or stages 05.2/05.3a are claimed.

## Changed paths

- Shared storage, compaction worker/command and read-only historical evidence audit:
  `tools/artifact_store.py`, `tools/blender_artifact_worker.py`,
  `tools/compact_stage_artifacts.py`, `tools/inspect_stage_artifacts.py`.
- Producers/readers: `tools/preview_movement.py`, `tools/movement_evidence.py`,
  `tools/review_spine_pelvis_visuals.py`, `tools/publish_spine_pelvis_fixtures.py`,
  `tools/retarget_clip.py`; the head/neck, spine/pelvis, primitive-execution and
  spine/pelvis boundary Blender harnesses. The local historical head-stage
  `inspect-evidence.py` resolves canonical scenes with a historical fallback.
- Tests: `tests/test_artifact_store.py`, `tests/test_artifact_compaction_blender.py`,
  `tests/blender_artifact_store.py`, `tests/blender_neutral_workflow.py`,
  `tests/blender_movement_arm_preservation.py`.
- Documentation: README, the new artifact-storage contract, relevant existing
  local execution/body contracts and this receipt. Existing Markdown ignore rules
  remain in effect; generated evidence remains local.
