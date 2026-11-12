# Storage reduction and retention ā€” Sol implementation handoff

Status: complete, 2026-10-26; see [the receipt](stages/receipts/storage-v2.md). Implement this maintenance assignment before adding stage 05.2 evidence. Writing tooling or a dry-run report alone does not complete it: execute verified cleanup and meet the storage gates below.

Read [the project retention policy](../docs/artifact-retention-policy.md), [the stage guide](stages/00-START-HERE.md), [the implemented v1 storage contract](../docs/contracts/artifact-storage.md), and [the previous maintenance receipt](stages/receipts/maintenance-neutral-artifacts.md). Preserve the existing uncommitted maintenance implementation. This assignment supersedes the old requirement to retain every different historical backup and to embed the avatar in every case. It preserves accepted motion and validation evidence.

## 1. Freeze the inventory and agree on accounting through code

### Plan and execution

- Inventory all of `C:/work11/artifacts`, including maintenance, scratch, hidden files and future shared assets. Record bytes, file counts, hashes for deletion candidates, classification and active-writer status. Capture filesystem free space separately. Do not count files moved elsewhere on the same disk as freed storage.
- Inspection baseline: stages 14.072 GiB, maintenance about 0.675 GiB; 05.1b alone 11.307 GiB. Its 195 `.blend1` backups total 5.041 GiB. All have adjacent canonical scenes and completed migration records. Recheck these facts, hashes and current status rather than trusting this snapshot.
- Two main Mixamo collections have 127 canonical scenes totaling 7.587 GiB. A representative approximately 61 MiB scene contains approximately 59 MiB of packed textures. The existing files are already compressed; do not spend this assignment experimenting with ZIP compression of unchanged full scenes.
- Store a small inventory and deletion/migration journal under `artifacts/maintenance/storage-v2/`. Use one resumable run, not a fresh full evidence tree on every retry. Identify any selected unresolved failure reproductions before retiring history.

### Testing and validation

Inventory totals must reconcile by extension, stage and artifact class. Detect changing input, active producer leases, path escape, symlinks/junctions and insufficient free space. Do not terminate another running task. Migrate inactive independent cases where possible; leave active cases explicitly pending.

## 2. Reclaim obsolete backup space first

### Plan and execution

- Extend the existing maintenance command with a distinct obsolete-history retirement operation, not a claim that these files are equivalent duplicates. Default invocation remains dry-run; this assignment requires running its explicit apply mode after validation.
- For each of the 195 backups, verify the current canonical hash against its migration record and verify that current accepted evidence resolves to that scene. Fresh-process reopen/playback verification must precede retirement for each affected canonical case; reuse one verified case result for multiple backups in that case.
- Record the backup's original path, size, hash and retained reason. If it contains a specifically needed unresolved-failure reproduction, extract and retain that motion as a small case in package 3. Otherwise retire it as obsolete history even when its action differs from the accepted action. Do not rerun the old duplicate-only compactor and stop at `already_compacted`.
- Remove only manifest-enumerated, unchanged files after rechecking resolved paths and hashes. Use one filesystem implementation end-to-end; no wildcard recursive shell deletion. Do not send gigabytes to the same disk's Recycle Bin or retain a second full local archive.

### Testing and validation

Use copies to test a valid historical backup, changed canonical, backup-only case, active writer, path escape and interrupted/resumed retirement. A backup-only or unverifiable case is retained and reported. Current canonical scenes, original results, PNGs, sheets and historical receipts remain intact. Target at least 4.9 GiB net recovery from this package; exceptions require exact paths, bytes and reasons, not a general preservation claim.

## 3. Replace repeated full scenes with shared assets and exact baked motion

### Plan and execution

Use a portable bundle contained within `artifacts`, with this initial layout:

```text
artifacts/assets/<asset-content-hash>/avatar.blend
artifacts/stages/<stage>/<rig>/<case>/motion.blend
artifacts/stages/<stage>/<rig>/<case>/preview-manifest.json
artifacts/stages/<stage>/<rig>/<case>/result.json
```

- The immutable asset stores the actual mesh, rest rig, materials and packed resources once per distinct supported asset version. The case stores its baked action(s), slot/binding data, pose/object state needed for playback, timing, views and profile identity. Preserve all required state; do not assume copying one action alone is sufficient.
- Derive assets and motions from the existing saved scenes, not today's FBX, current movement builder or model. Asset hashes cover the actual static geometry, weights, UVs, normals, rest transforms, materials and resource content. Exclude case-specific action/camera/pose state from static identity; serialize it with the case. Verify equality before deduplicating. Distinct rig/asset versions must not be merged merely because filenames match.
- Write a schema-v2 manifest with relative asset/motion paths, their hashes, original scene identity, rig/action/slot mapping, frame range/fps, measured evidence references, view settings, source/profile versions, entry metadata and typed render-completion information. Preserve v1 reader compatibility.
- Add a loader/exporter that assembles the stored asset and baked motion for playback, rendering and inspection. It must not invoke AI or rebuild movement from a recipe. Loading from a relocated bundle must work without the original source FBX or an absolute workstation path. Standalone packed scenes remain an explicit temporary export option.
- Update `tools/artifact_store.py`, preview/test producers, render-resume logic, the compactor, evidence audit, visual reviewers and fixture publishers. Discover other readers before changing paths. The current linked-library rejection must be replaced by a bounded bundle-reference validation rule, not simply removed.
- Extract a pilot demo and Mixamo case first. Then migrate every eligible accepted scene in 05.1a/05.1b and the repeated generated regression/maintenance scenes needed to reach the overall target. Reuse validated static assets across stages; do not duplicate the asset store for each stage.
- Fresh-process validate each migrated case before committing its v2 manifest. Compare active slot, timing, complete sampled bone/object motion and relevant geometry/material/resource state against the original. Use the existing validated motion comparison gates or stricter; never increase tolerances to pass migration. Check representative rendered views on each distinct asset version and motion boundary cases. Preserve existing visual evidence throughout migration.
- Atomically commit the durable manifest and asset/motion files before deleting that case's original full scene. Keep a compact append-only journal mapping old paths/hashes to new locations. Update readers of historical references; do not rewrite old receipts to pretend their paths never changed.

### Testing and validation

Test fresh playback, relocatable bundles, shared-asset hash mismatch, missing asset, different rig version, changed action/slot, saved custom state, failure before/after manifest commit and repeat application. Unsupported constraints/drivers/custom content must fail closed for that case and retain its original. Reopening must reproduce the saved motion independently of newer source code. Case motion files must not contain copies of avatar meshes/textures.

Migrate incrementally with one worker initially, temporary data no more than 512 MiB, and measured space preflight. Remove verified source scenes as each case commits; do not accumulate a full second archive and delete it only at the end. Shared-asset garbage collection is allowed only after a complete reference scan and writer exclusion.

## 4. Enforce budgets and bounded retention for every producer

### Plan and execution

- Implement the budgets and retention classes in [the policy](../docs/artifact-retention-policy.md) through the shared writer and a machine-readable inventory/check command. Cover maintenance, tests and developer previews, not only numbered stage output.
- Budget checks run before batch expansion and at case commit. Estimate using a measured representative case, expected case/view/frame counts and existing output. Report exact over-budget categories. A configuration value or printed warning with no enforcement is insufficient.
- Preserve one current accepted record per case/input signature. Changed implementations invalidate resume; unchanged verified evidence may be reused. Do not accumulate timestamped copies of all successful runs. Pin selected failure reproductions by issue/signature with reason and expiry/review trigger.
- Retain required full-motion visual evidence. Do not cut test cases or frame coverage to meet storage limits. For future image-heavy runs, a lossless temporal container can replace frame PNGs only after verifying decoded frame count/order/timing and pixel hashes. Keep selected sheets; teach manifests/readers the declared representation. Use available encoders; otherwise retain PNGs and report the budget constraint. Current PNGs need not be converted to achieve this migration.
- Remove successful owned scratch/copy-test files after validation, retaining compact assertions/hashes/log summaries. Do not retain thousands of repeated mesh/texture dumps in maintenance reports; keep deduplicated fingerprints and failure diagnostics.
- Publish schema-v2 commands and the supported representations in `docs/contracts/artifact-storage.md`. Update tests, README and stage evidence examples. Existing receipts remain historical. Future stage receipts must include storage compliance.

### Testing and validation

Test within-budget and over-budget writes, estimates versus actual bytes, no backups, interrupted runs, cleanup ownership, asset references, failure retention and no-growth repeat runs. Check a head and a torso case on both rigs using the real writers, including render resume. Do not rerender all historical motion just to prove storage reduction. Run affected existing regressions and the read-only evidence audit through the v2 resolver.

## Completion gates ā€” actual disk recovery required

1. Entire `C:/work11/artifacts` is at most **3.0 GiB** after cleanup, counting shared assets, migration evidence, diagnostics and remaining originals; net reduction is at least **11 GiB** against the approximately 14.75 GiB inventory. If the inventory has materially changed, report a fresh baseline and reconcile it; do not shrink the accounting scope or count unrelated manual deletions.
2. All accepted cases still resolve to playable saved motion with their numeric and full-motion visual evidence. Every retained original has an explicit unsupported-content or required-history reason and measured bytes. All eligible cases are actually migrated, not only a sample.
3. New routine writes embed no repeated avatar assets; no generated `.blend1` files or routine standalone scenes appear. Asset hashes and source-bundle portability checks pass.
4. Reapplying migration/retirement removes nothing further. Repeating identical test cases creates no new permanent scene/resource copies. Audit-only runs do not create growing full-data snapshots.
5. The steady-state budgets, preflight checks, receipt accounting and producer/reader changes are implemented and exercised. No lowered quality gates, deleted unique source assets, hidden archives, hardlink/reflink accounting tricks or altered historical success claims.

Write `to do/stages/receipts/storage-v2.md` with before/after bytes, net reclaimed disk space, file counts, migrated/retired/retained inventory, fresh-reopen results, regression commands and budget tests. If any gate fails, report partial with exact remaining bytes and cause. Do not label the assignment complete merely because the new architecture exists. Stop before implementing another movement stage.
