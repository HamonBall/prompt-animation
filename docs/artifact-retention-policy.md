# Project artifact retention and storage policy

Effective requirements: 2026-10-26. Applies to all generated artifacts in this project: movement stages, developer previews, regressions, maintenance, benchmarks, diagnostics, temporary renders and explicit exports. It does not authorize deleting user files, source assets or unrelated data.

Pair these storage rules with [the project-wide validation efficiency policy](validation-efficiency-policy.md): targeted development runs, correctness before bulk rendering, verified evidence reuse and measured worker/encoding costs. Storage efficiency and validation efficiency both preserve required final coverage.

Implementation status: shared schema-v2 bundles, measured preflight, commit checks and
verified cleanup are implemented. See [the storage-v2 receipt](../to%20do/stages/receipts/storage-v2.md)
for actual accounting and tests. Future evidence must use this format and budgets.

## Required storage model

- Store each immutable avatar/rig/resource version once in `artifacts/assets/<content-hash>/`. References are relative, hash-verified and confined to the portable bundle. No workstation-only absolute dependencies.
- Each test case retains exact baked motion, binding/state, metadata, numeric results and required visual evidence. A recipe/prompt is useful provenance, not a substitute for the saved action.
- Normal output is a small motion file plus a versioned manifest referencing the shared asset. Packed standalone scenes are explicit exports only, outside the routine case layout; remove owned temporary exports after validation.
- No automatic Blender backup files, duplicate `visual-preview.blend`, copied asset set per stage or whole-successful-run archives. Changing global user save preferences permanently is prohibited.
- Preserve semantic/visual test coverage. Storage optimization must not weaken tolerances, reduce required rig/case coverage, fake inspected evidence or discard unique accepted motion before verification.

## Retention classes

| Class | Retention rule |
| --- | --- |
| User FBX/media, models, source, configuration, Git data | Never subject to generated-artifact cleanup. |
| Shared assets | One immutable copy per referenced content version. Delete only after a complete manifest/reference scan finds zero references and no writer lease. |
| Accepted case | Keep the current accepted baked motion, profile/source/input identity, measurements, required views/full-motion media and compact receipt. Replace only after the successor passes. |
| Superseded successful case or historical backup | Retire after accepted replacement verification and a durable path/hash journal. Different historical motion does not automatically require permanent retention. Preserve explicitly selected unresolved-failure examples. |
| Failure reproduction | One latest minimal reproduction per distinct unresolved failure signature, with owner/reason and review-on-resolution marker. No entire repeated run directories. |
| Scratch, save candidates, copy-based integration tests | One active run; clean owned successful outputs after validation. After interruption, resume or reconcile owned leftovers before generating new copies. |
| Audit/maintenance evidence | Keep small summaries, hashes, assertions and actual failure diagnostics. Reuse/resume one operation journal; do not serialize full unchanged assets repeatedly. |
| Visual evidence | Retain full required motion coverage as PNGs or a validated lossless sequence/video representation plus selected sheets. Compression must preserve decoded frames and timing; never silently replace evidence with a few snapshots. |

## Initial budgets and enforcement

Units below are binary MiB/GiB. These are storage limits, not claims about existing enforcement or automatic permission to delete evidence.

| Scope | Limit |
| --- | --- |
| All retained generated artifacts, including assets/maintenance/exports | 4 GiB after migration; initial cleanup must reach the assignment's stricter 3 GiB gate. |
| Each new numbered stage | Warn at 256 MiB; hard limit 512 MiB excluding the shared assets counted globally. |
| Existing 05.1b visual/numeric evidence | Explicit grandfathered limit 1 GiB after migration; existing PNG coverage can remain. Other stages receive no inherited exception. |
| Shared asset store | 512 MiB total initially; no duplicate payload to avoid this count. |
| Per-case motion plus manifest, excluding measurements/media | Warn at 2 MiB; hard limit 8 MiB. Investigate unexpectedly embedded resources first. |
| All maintenance/audit retained output | 256 MiB after migration; stream/compress or deduplicate verbose validation records while retaining journal/proof. |
| Unresolved-failure reproductions | At most five per stage, 128 MiB combined, included in stage/global budgets. Minimize cases before requesting more space. |
| Active temporary write footprint | 512 MiB global, separately reported in addition to retained totals; reserve free space before allocation. |
| Explicit standalone exports | At most two active owned exports, 256 MiB combined, included globally; never overwrite/delete user-designated deliverables to enforce this. |

Measure retained and temporary bytes, expected final growth and filesystem free space before a large run. Enforce at individual writes as well as batch preflight; do not trust estimates alone. Unexpected limit breaches stop further artifact allocation while keeping accepted evidence intact. Test execution without new large artifacts may continue when valid for the assigned checks.

When a mandatory case cannot fit, first remove owned stale scratch, retire verified obsolete history and improve representation. Do not drop required tests, prune unresolved evidence automatically, or silently raise limits. A necessary budget exception must be explicit in the user's assignment or approved with exact extra bytes, reason, scope and review/expiry condition; it is not a routine approval step for work within the budgets.

## Cleanup and failure rules

Use dry-run inventories and explicit apply commands. An assignment explicitly requiring cleanup includes applying its reviewed, validated manifest; do not stop at a dry run and claim success. Restrict deletion to enumerated generated outputs within resolved authorized roots. Reject symlinks/junctions/path escapes, stale hashes and active producers. Verify the final path before recursive operations; use a single filesystem API/shell end-to-end.

Commit verified replacements and their journal before retiring originals. Failure before commit preserves originals; interruption after commit resumes pending retirement safely. Backup-only or unexplained unique cases remain pending until resolved. Do not fabricate equivalence between distinct actions.

Account for the entire artifact tree and explicitly report any generated output outside it. Moving files to another directory, Recycle Bin, local archive or uncounted asset cache does not count as disk space reclaimed. Never accumulate a complete migration backup on the same disk. Filesystem free-space change is corroborating evidence; concurrent system writes must be distinguished from artifact byte totals.

## Required completion evidence

Every future stage/maintenance receipt includes retained bytes before/after by class, peak temporary bytes, shared-asset additions, retired history, retained failures, applicable limits/exceptions and actual budget-check commands. Repeating unchanged accepted cases must not increase scene/asset counts or retain another full run. Repeated audits must not append full identical snapshots indefinitely.

Large evidence output is complete only after this accounting and cleanup, in addition to all movement quality gates. Existing historical receipts are not retroactively edited; migration journals resolve relocated artifacts.

## Capacity planning for subsequent stages

Before each expensive batch, report current global retained bytes, remaining bytes under 4 GiB, estimated retained additions including new shared assets, and temporary reservation separately. If projected retained usage reaches 90% of the global limit, prepare a concrete compaction/retirement inventory before expanding the batch. This is a planning trigger, not a raised hard limit or permission to delete evidence.

Prefer supported lossless representation of older frame sequences and verified superseded generated history. Preserve all required frames, timing, measurements, reviews and source assets. Complete replacement verification and reference updates before retiring originals. Report actual reclaimed bytes; an estimate or dry run is not a cleanup result. Record measured temporary peak when tooling supports it; otherwise explicitly report unavailable and retain the reservation bound.
