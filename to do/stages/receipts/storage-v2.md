# Storage-v2 maintenance receipt

Status: **complete**, 2026-10-26; uncommitted working tree based on 7871747.
This completes the storage prerequisite before the new stage 05.2 evidence matrix.
Historical stage receipts and the previous maintenance receipt remain unchanged.

## Whole-root accounting

Frozen baseline: **15,846,188,473 bytes**, 50,295 files (14.757913 GiB).
Completion inventory: **1,291,747,369 bytes**, 52,967 files (1.203033 GiB).
Net reclaimed: **14,554,441,104 bytes / 13.554880 GiB**. The inventory includes
shared assets, diagnostics, scratch, exports, all maintenance and the first
11,793,873 bytes of stage 05.2 numeric outputs. No accounting scope was excluded.
The at-most-3-GiB and at-least-11-GiB gates both pass.

Filesystem free space rose from 50,444,791,808 to 63,399,866,368 bytes. This is
reported separately: concurrent filesystem activity means its difference is not
the artifact-recovery total. No archive, Recycle Bin, off-root move, hardlink or
reflink was used to claim recovery.

| Retention class | Before bytes | Completion bytes |
| --- | ---: | ---: |
| Historical backups | 5,541,986,908 | 0 |
| Standalone scenes outside maintenance | 8,494,183,297 | 0 |
| Shared assets including metadata | 0 | 64,209,506 |
| Case motions outside maintenance | 0 | 42,101,272 |
| Maintenance, including its retained case motions | 724,337,647 | 68,540,948 |
| Numeric/metadata outside maintenance | 175,410,029 | 206,624,962 |
| Original frame PNGs | 608,306,193 | 608,306,193 |
| Original sheets | 276,530,053 | 276,530,053 |
| Other original visuals | 18,364,736 | 18,364,736 |

Machine-readable accounting: `artifacts/maintenance/storage-v2/baseline.json`,
`baseline-files.json`, `backup-package-final.json`, `completion-accounting.json`,
`reopen-summary.json`, `budget-check.json` and the append-only `journal.jsonl`.
The first package alone reclaimed **5.005086 GiB net**, above its 4.9-GiB gate.
All 195 designated 05.1b backups were retired as obsolete history, with original
reasons, hashes and accepted-case verification. Six additional verified generated
backups were retired during other case migrations. Backup-only, changed-input,
pinned and active-writer cases are protected by the command and tests.

All **480 baseline scene/backup files** were retired: 279 full scenes and 201
backups. Of the full scenes, 277 were converted and independently verified; one
successful private integration bundle was subsequently cleaned and two owned
save-test copies were verified against retained accepted motion and removed.
There are **276 retained migrated accepted cases**, three shared asset versions,
and **zero retained originals or unresolved failure reproductions**. Required
numeric and visual evidence remains; 47,031 original PNG and stage numeric/profile
files match baseline size and modification identity exactly. Original stage
results, profiles, entries, instances, fragments and executables were not rewritten.

## Motion, resources and portability

Every migrated case was independently reopened before its original was removed.
Across 25,757 complete case frames, maximum bone/object matrix difference was
**0**; maximum saved numeric-control error was **0.000022491617**. Thresholds were
not relaxed. Action curves, active action/slot, timing, geometry, rest rig, weights,
UVs, normals, materials, resources and custom/object/pose/view state were checked.
No AI or movement reconstruction was used.

Decoded entry/midpoint/exit render pixels matched for representatives covering
all three distinct assets, including boundary cases. Two initially pending
boundary comparisons were retained until a fresh extraction/reopen comparison
passed; the originals were not removed on failure. Representative original/bundle
images were visually inspected. The Mixamo crouch, pose, resources and camera
agree without visible separation or missing geometry.

Both demo and Mixamo bundles passed fresh-process relocation without source FBX,
full-frame comparison, explicit temporary standalone export/reopen, custom-state
round-trip and changed-slot rejection. Different rig versions retain different
asset hashes. Missing assets, changed hashes, escaping references, constraints,
drivers and unsupported content fail closed. Motion libraries contain no repeated
meshes, armatures, materials or images.

Durable atomic files and a transaction record protect publication. Process-death
recovery restores the prior motion before commit or finishes retirement after
commit. The journal precedes source retirement. Relative references are confined;
legacy v1 scenes and historical canonical mappings remain readable. Retired
backup actions are not described as equivalent to accepted actions.

## Producers, readers, retention and tests

The shared writer, head/torso/primitive/boundary/CLI producers, compactor, evidence
audit, visual reviewers and fixture publishers use the bundle resolver. Explicit
standalone exports are bounded and separate from routine output. No Blender
backups are generated; user save preferences are restored. Schema and commands:
`docs/contracts/artifact-storage.md`.

Measured preflight enforces expected cases/views/frames and existing output;
render expansion reserves bounded output, and actual case commit rechecks totals.
The old maintenance dumps were reduced in place: **389 reports**, originally
370,563,662 bytes, now retain compact fingerprints/assertions and original hashes.
Owned integration/scratch copies and no-longer-needed trajectories were enumerated,
hash checked, journaled and cleaned. Diagnostic paths and old receipts remain useful.
Failure pins require owner, signature, reason and review trigger, with count/byte
limits. Audit outputs overwrite one fixed report rather than growing run trees.

Actual check: `tools/storage_v2.py --operation check` passed with no errors.
05.1b retains 915,467,005 bytes, within its explicit 1-GiB grandfathered limit;
maintenance is within 256 MiB and assets within 512 MiB. The temporary monitor's
observed peak was **31,618,206 bytes**; combined worker reservation was **320 MiB**
and every allocation enforced the 512-MiB global temporary bound. Monitoring began
after the initial pilot, so the observed value is not claimed as an exact peak
for the earlier unmonitored interval.

Commands actually exercised, using Blender 5.1 and its bundled Python:

- `tools/storage_v2.py --operation retire-history --apply`
- `tools/storage_v2.py --operation migrate --apply`, initially one worker, then
  a separately leased independent 05.1b worker after a combined-space preflight.
- `tools/storage_v2.py --operation compact-diagnostics --apply`
- `tests/test_storage_v2.py`: 9 tests passed.
- `tests/test_storage_v2_blender.py --blender-integration`: 6 tests passed,
  including interrupted retirement and failure before/after manifest commit.
- `tests/test_artifact_compaction_blender.py --blender-integration`: 5 passed.
- `tests/blender_bundle_portability.py`: both rigs passed.
- `tests/blender_artifact_store.py`: both rigs passed repeated/failing routine
  writes, saved preferences, full playback and owned old-copy retirement.
- Real `blender_movement_head_neck.py` nod and
  `blender_movement_spine_pelvis.py` torso-wave writers on both rigs, including
  saved-motion render resume. Repeating retained exactly three asset files, two
  head motions and two torso motions, with identical aggregate blend bytes and
  no backups (`writer-repeat-review.json`). Missing/stale resume cases also
  passed pure checks.
- `tools/inspect_stage_artifacts.py`: 37 head cases per rig and 89 body cases per
  rig audited, preserving all required frame coverage.
- Full unit discovery: **185 tests passed, 12 skipped**, including the initial
  stage 05.2 tests. Real Blender integrations above were run explicitly; native
  junction creation is unavailable here, while simulated reparse rejection passed.

No next movement stage was implemented as part of this maintenance assignment.
The user subsequently requested stage 05.2; its changes/evidence have their own
contract, tests and receipt. All changes remain available for user review/commit.
