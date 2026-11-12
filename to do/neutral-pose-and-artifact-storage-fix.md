# Fix plan — neutral pose, demo joint appearance and stage artifact storage

Status: implemented and verified, 2026-10-26. Prepared 2026-10-23. See the
[maintenance receipt](stages/receipts/maintenance-neutral-artifacts.md) for measured
results, actual storage savings and the deliberately retained historical backups.

Follow-up, 2026-10-26: [storage reduction and retention](storage-reduction-and-retention-plan.md) supersedes this completed plan's per-case self-contained-scene requirement and blanket retention of distinct backups. The earlier results remain historical; future generated evidence follows [the project policy](../docs/artifact-retention-policy.md).

## Assignment and boundaries

Implement the three work packages below in order, then write one completion receipt. Read [the stage guide](stages/00-START-HERE.md), current source and the latest stage receipts first. Preserve concurrent/uncommitted work. Do not start stages 05.2 or 05.3a as part of this assignment.

This is a focused maintenance task before further arm-library work. It covers default-state correctness, misleading test-preview presentation, visibly defective demo joint connections if reproduced, and repeated full-scene artifacts. It does not introduce arm presets, change AI interpretation, redesign the avatar or relax motion-validation thresholds.

## Established facts versus unresolved diagnosis

- A direct Blender check of `target_pose(handle, PosePlan())` on the procedural demo produced symmetric upper-arm, forearm and hand directions: 8 degrees outward from downward on both sides. That checks the posing function, not the full application load/reset workflow.
- `tests/fixtures/movement_fragments/v1/entry-bent-turned.json` deliberately specifies left upper-arm elevation 45 degrees, forearm elevation 80 degrees, forearm azimuth 60 degrees, root yaw 90 degrees and torso pitch 15 degrees. Preserve this fixture and its purpose.
- Stage 05.1b's `default` case means default movement parameters; most such cases start from a deliberately bent/crouched entry. It does not mean the application's default avatar pose.
- The screenshot's exact source scene/frame is unknown. Do not claim a confirmed startup defect or fix the photographed pose by resetting every test case.
- The demo is made from separate rigid mesh pieces. Segment boundaries are expected; open gaps, exposed interiors, severe overlaps or disconnected-looking joints require reproduction and inspection.
- At inspection, `05.1a/mixamo` was approximately 4.50 GiB: 74 `.blend` files for 37 cases. `05.1b/mixamo` was approximately 3.26 GiB: 48 `.blend` files and six `.blend1` backups. Individual scenes were about 61 MiB. The latter directory was growing, so these are observations, not a frozen inventory.

## 1. Verify and correct neutral startup/reset behavior

### Plan

Separate three states explicitly: anatomical bind/rest pose, application neutral pose, and the authored starting pose of a movement test. Determine whether the screenshot reflects the last category or an actual application regression.

### Execution

1. Trace `AVATAR_OT_load` in `src/avatar_app/main.py`, the exact `neutral pose` shortcut, action construction and final frame selection. Test through the same path used by the application, including its state/history bookkeeping. A direct `target_pose()` test alone is insufficient.
2. Reproduce fresh load, reset after an asymmetric animation, and repeated avatar loading. Check the final displayed frame, active action/slot, evaluated arm transforms and any stale state from the previous avatar. Record which operation changes either arm unexpectedly.
3. Fix only the reproduced source of incorrect neutral state. Neutral must explicitly reset old arm goals; ordinary head/spine movements must preserve their supplied arm state. Do not change global omission semantics or force neutral at the start/end of every generated movement.
4. Identify starting state clearly in developer previews and reports. Record `entry_fixture`, movement parameters, current/initial frame and `entry_kind` (`neutral` or `authored_non_neutral`). Label existing `default` cases as default movement parameters with their actual entry state; do not rename case IDs or break historical artifact paths.
5. If the full startup/reset path passes, record that result and retain the behavior. Complete the preview-labeling and regression coverage; do not invent a pose correction merely to produce a code change.

### Testing

- Extend `tests/blender_neutral_arms.py` or a focused companion to include the procedural demo and both existing supplied imported rigs. Exercise fresh load and reset after explicit asymmetric arm controls through the application path. An unavailable asset is a recorded validation gap.
- At the final neutral frame, upper-arm, forearm and hand direction must match the documented downward/outward 8-degree target on each side within 0.1 degree in the existing semantic axes. Wrist alignment must follow the solved forearm.
- Check default camera/frame display manually once in the UI. Verify explicit arm elevation zero and explicit wrist rotation still override defaults.
- Run one head movement and one implemented torso movement from the bent fixture; verify unchanged unrelated controls and measured preservation within the shared stage tolerances. Inspect complete playback, not only the first frame.

### Validation and restraints

Receipt distinguishes verified neutral behavior, any reproduced defect and its fix, and intentional non-neutral fixtures. No arm preset implementation, automatic symmetry during ordinary animation, rest-skeleton changes or edits to imported assets. This is not deferred to 05.2: that stage adds upper-arm motion, while 05.3a adds elbow/wrist mechanics.

## 2. Inspect and correct demo joint appearance

### Plan

Check whether the visible elbow/shoulder seams are ordinary segment boundaries, mesh placement defects or incorrect evaluated joint transforms. Repair only reproduced defects on the procedural demo.

### Execution

1. Inspect `src/avatar_app/blender/demo.py` mesh placement, local transforms, full-weight vertex groups and armature modifiers. Compare evaluated mesh placement with actual shoulder/elbow/wrist joint positions. Use front, side and three-quarter views without viewport relationship lines obscuring the result.
2. Inspect neutral, the existing bent fixture and a small set of directly authored elbow bends/arm directions. These are diagnostic poses through existing controls, not new movement-library entries.
3. If bones are continuous but rigid pieces leave unintended holes, adjust the existing demo pieces' placement, scale or normals only as required. Preserve skeleton, bone names/rest transforms, mesh topology, material assignments, object identity and existing calibration landmarks. Do not add subdivision or increase polygon counts to hide a transform defect.
4. If the defect comes from joint solving, identify the exact transform failure and fix it in the existing adapter with a focused regression. Do not compensate by distorting the demo meshes. If repair requires a larger solver change outside these boundaries, report that dependency and leave this package partial.

### Testing and validation

Capture matching before/after views for both arms in neutral and bent poses. Inspect for open gaps, reversed surfaces, abrupt offsets and severe overlap; retain the intentionally segmented appearance. Confirm skeleton transforms, endpoint measurements, object/vertex counts and imported-avatar behavior are unchanged by a visual-only fix. Rerun affected neutral and preservation checks if shared posing code changed.

Do not claim support across unimplemented future arm ranges. Record the inspected poses and any unresolved defect; screenshots alone do not prove a full movement envelope.

## 3. Reduce test artifact storage without losing evidence

### Plan

Save one compressed, self-contained Blender scene per case. Keep numeric evidence and required visual coverage. Update producers, render-resume logic and evidence readers together.

### Execution — future outputs first

1. Inventory sizes by case and extension, separating `.blend`, `.blend1`, JSON, frame PNGs and contact sheets. Identify active writers before touching existing output directories. Use a new maintenance evidence directory while another stage is running.
2. Add one shared artifact-writing helper used by `tools/preview_movement.py`, `tests/blender_movement_head_neck.py` and `tests/blender_movement_spine_pelvis.py`. Locate additional affected readers/writers with repository searches, including stage inspection scripts.
3. Canonical scene name is `preview.blend`. Save with Blender compression explicitly enabled. Disable save-version backups only around generated-artifact saving and restore the previous preference in `finally`; never persist a global user-preference change.
4. Write to a temporary sibling file, validate successful creation, then replace the canonical scene. A failed save must leave the previous valid artifact available. Remove only temporary files created by this operation after their ownership is verified.
5. Eliminate routine creation of `visual-preview.blend`. Store front/side camera settings and viewing instructions in a small manifest or the canonical scene. Reload/render from the canonical action. Keep one file containing the correct rig, active action/slot, frame range, current frame and required resources.
6. Replace `visual-preview.blend exists` completion checks with a versioned per-case manifest. Include source/profile/recipe identity, frame range, expected views/frame counts and completion status. Only mark rendering complete after the expected files exist. Missing frames or changed inputs must invalidate `--skip-rendered`; an interrupted run must resume safely.
7. Update inspection scripts and documentation to resolve the canonical scene. Readers must still understand historical two-file cases. A rendering pass must not silently overwrite the numerical result with a different action or pose.

### Execution — existing evidence compaction

Provide an explicit compaction command with dry-run as default and an `--apply` mode. Limit it to the two named stage directories; reject paths escaping their resolved roots, including link/junction traversal. Never operate on a directory with an active producer or changing inventory.

For each case, inventory and hash the original files, build a compressed canonical candidate, reopen it, and compare rig/action/slot, timing, entry/exit and sampled measured motion with the saved evidence. Preserve camera/view settings or genuinely distinct content before retiring a second scene. Different filenames or equal sizes do not prove equivalence. Do not load a historical case through newer builders and silently regenerate different motion.

Commit the validated canonical file and migration manifest before removing only the redundant files explicitly enumerated for that case. Classify `.blend1` separately: retain it if it is the only recoverable copy or contains unverified distinct content. Preserve JSON, render frames, sheets, logs and historical receipts; append a migration map rather than rewriting old completion claims. If verification fails, retain originals and report the case. Process cases incrementally and check temporary disk-space needs.

### Testing

- Use isolated temporary output directories for save, repeat-save, failed-save and resume tests. Confirm no second scene or `.blend1` appears and the original save preference is restored after success/failure.
- Reopen a demo and a Mixamo case in a fresh Blender process; inspect playback, action slot, frame range and materials. Compare measured motion against pre-change evidence within existing tolerances. Verify front/side render-resume behavior with deliberately missing frames and stale manifests.
- Test compaction on copies of representative historical cases before applying it to evidence: identical scenes, distinct viewing settings, differing actions, a corrupt file and a backup-only recoverable case. Repeated application must be safe and produce no further removals.
- Measure bytes before/after, file counts and save/load time for the same case set. Confirm required numeric and full-motion visual evidence remains available. Do not rerender the entire suite merely to measure file compression.

### Validation and restraints

Every newly generated case has at most one complete `.blend`, zero generated `.blend1` files and a truthful completion manifest. Successful existing-case compaction produces a per-file migration record and verified playable replacements. Report actual storage savings; do not promise an arbitrary compression ratio.

No asset decimation, source FBX removal, texture degradation, omitted validation cases, reduced required frame coverage, blanket folder deletion or external asset links that make evidence nonportable. Do not modify `.gitignore` or user Blender preferences permanently. Historical compaction remains pending if writers are active; the new-output improvements can still be completed independently.

## Completion receipt and handoff

Write `to do/stages/receipts/maintenance-neutral-artifacts.md` with a separate passed/partial/not-run status for each package, actual commands, changed paths, neutral/preservation measurements, inspected before/after views, storage inventory/savings, migration manifest and remaining dependencies. Store new evidence under `artifacts/maintenance/neutral-artifacts/`.

Run focused checks plus affected existing regressions; do not claim tests from historical receipts as newly run. Do not mark 05.2/05.3a complete or expand their scope. Stop after this maintenance handoff.
