# Stage 05.3a verified handoff

Status: **complete**, 2026-10-30. Stop here; 05.3b and subsequent stages have not
started. Preserve the uncommitted working tree based on
`1039187c965491a7021c7d5a127de9b82e0c8802`; no staging, commit or ignore-rule change
was performed. Required Markdown remains local under the existing ignore rule.

Read [the receipt](../receipts/05.3a.md) and
[the hand contract](../../../docs/contracts/elbows-wrists-hands-v1.md) for per-ID
ranges, frames, ownership, entry/return rules and actual reviewed rig envelopes.

## Delivered interface

Nine definition-v1 IDs: elbow.flex, elbow.orient, forearm.twist, wrist.flex,
wrist.deviate, wrist.circle, hand.orient, hand.trace and hand.hold. Opt into
calibrated profile 5 with `with_hands_v1` and capture a fresh entry. Profiles 1–4
retain their meanings; changing a snapshot version is not migration.

Versioned schemas, profiles, default example sets and 18 explicit rig review
records are in `tests/fixtures/elbows_wrists_hands/v1/`. Reviews register explicitly;
a constructed catalog does not automatically claim validation.

The endpoint/pole solver uses immutable entry arm bases after current parent
transforms. The source migration pins 130 unchanged FK/wrist/orientation cases to
their truthful original producer identity and regenerates 72 endpoint/pole cases.
Keep `endpoint-baseline-migration.json` and the narrow source-compatibility checks;
changing application sources requires fresh compatibility assessment or regeneration.

## Verified gates

- All 202 cases / 20,906 actual motion samples pass independent rebuild, tracking,
  physical review, isolation and loop checks on demo and Mixamo.
- Worst target error: 0.001433 degrees / 0.000002818 metres. Worst cycle pose seam:
  0.003101 degrees; velocity mismatch 1.803 degrees/s. Original limits unchanged.
- Both-rig hard-goal errors, cancellation/failed-review rollback, moving-torso
  holds, authored-arm preservation, legacy execution and exact cached/uncached
  measurement capture pass.
- Full unit discovery: 214 tests, 12 skips, passed (`all-unit-final.log`).
- All 540 lossless movies / 57,868 rendered frames pass saved-action playback and
  decoded-pixel checks. All 26 full-body and 10 detail review pages were actually
  inspected, with page/source-sheet hashes in `visual-review.json`.
- Published fixture rebuilds, the 202-case evidence audit and two no-growth
  repeats pass. The repeats preserve hashes/mtimes/counts for 958 payload files,
  206 motions (including 4 regressions), 540 movies and 3 shared avatars.
- Global storage check: 683 bundles, zero errors. Final preservation/accounting
  passes; all writers and the temporary monitor are stopped, owned scratch zero.

Evidence is under `artifacts/stages/05.3a/`; the independent media audit is
`artifacts/maintenance/storage-v2/hands-evidence-audit.json`.

## Storage closure

Whole artifact root: 1,620,651,664 bytes / 55,587 files before;
2,064,288,980 bytes / 58,979 files after. Stage artifacts: 443,250,593 bytes.
Conservative totals including hand fixtures and all local source caches:
446,304,402 stage bytes against 536,870,912; 2,067,342,789 global bytes against
4,294,967,296. Warning threshold crossed; no hard-limit exception.

All 55,585 predecessor files outside the two explicitly refreshed maintenance
reports (`current-inventory.json`, `budget-check.json`) preserve size/mtime.
Shared assets remain 64,209,506 bytes, additions zero. Only two superseded,
unreviewed demo development cases were retired: 14 files / 1,259,145 bytes, with
path/hash journals. Required motions, numeric/visual evidence and source assets
remain retained. Maximum case motion+manifest is 542,368 bytes; no stage packed
scene copies, .blend1 backups or unresolved failure pins remain.

Observed temporary peak: 12,465,682 bytes over 11,365 observations; final zero.
Observation was interrupted, including 09:28:29–09:50:48 and 11:10:39–11:24:24 UTC
on 2026-10-30, and expanded from scratch/pending to include provisional PNGs.
Do not call this a continuous maximum. Per-write guards remained enabled.
See `completion-accounting.json` for all classes and conservative outside-root bytes.

## Limits and retained diagnostics

Free-space goals remain conditional on reach, clearance, joint limits and hard
constraint compatibility. Undefined near-straight poles reject when hard and omit
when soft. Core forearm bones are reviewed; uncalibrated twist distribution,
fingers, surface attachment and a generic composer are outside scope.

One long-lived Mixamo detail process hit an Intel `ig9icd64.dll` shutdown access
violation after all case checks passed and the writer lease was released. Fresh
cache re-entry validated all 17 cases and exited cleanly, without regeneration.
Retain its raw log, re-entry log and `detail-shutdown-diagnostic.json`. The logged
sandbox crash report was absent after exit. No manual interactive-UI exercise is
claimed; cancellation/rollback were exercised in the native executor harness.

The user selects the next work package. Do not start it automatically.
