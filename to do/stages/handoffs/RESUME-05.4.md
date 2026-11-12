# Stage 05.4 handover

Status **complete, 2026-11-05**. Stage 05.5 remains planned and awaits assignment.

Read AGENTS.md, [the stage specification](../05.4-hips-knees.md), [the receipt](../receipts/05.4.md), [the contract](../../../docs/contracts/hips-knees-v1.md), and the artifact-retention and validation-efficiency policies before resuming. Preserve the working tree and frozen README. The stage began from clean commit 11682ba1cb96ecf063567a3c2723c6ab9bf5b0cf.

## Passed

- All twelve hip, thigh and knee movements are implemented in opt-in profile 7 through `legs.mechanics.v1`. Free-leg movements keep the captured opposite sole planted. Pulse holds both soles. The native boundary and prior-profile regression checks passed on Demo and Mixamo.
- The independent numeric and saved-playback audits each passed 156 cases and 24,680 samples. The 12 pulse cases ran fresh after the pelvis and leg rebase. The 144 free-leg executions are preserved under the recorded unreachable-branch proof.
- Both render drivers exited successfully at 78 cases each. All 156 cases were inspected in both views, with retention complete. The stage evidence audit passed for all 312 lossless movies and 49,360 frames. Default sheets remain complete and non-default sheets retain verified original-resolution phase cells.
- Published all 24 per-rig movement reviews and examples under `tests/fixtures/hips_knees/v1/`. Final unittest discovery found 232 tests, with 220 passed and 12 existing opt-in skips. The published fixture test ran.
- The two-pass resume check passed in 604.34 seconds. It verified 471 payloads and found no growth or identity change across the whole artifact inventory. The storage monitor is stopped at zero temporary bytes, with a sampled peak of 19,490,042 bytes. No artifact writer leases were found after the stop.

Primary evidence lives under `artifacts/stages/05.4/` in `validation-summary.json`, `saved-playback-summary.json`, `visual-review.json`, `final-unittest.log`, `resume-no-growth.json` and `temporary-monitor.json`. The stage audit is `artifacts/maintenance/storage-v2/hips-knees-evidence-audit.json`.

## Verified closure

The managed evidence job revalidated the accepted numeric and full-motion visual evidence, and the global storage-v2 check passed 866 bundles with no errors. Final accounting passed after the job released its lease. Stage 05.4 used 451,240,699 bytes against its 512 MiB cap, including fixtures and local code caches. The conservative global total was 2,740,792,019 bytes against 4 GiB. Final temporary bytes and writer leases were zero. All 312 lossless movies, 49,360 frames and the shared assets were preserved.

The closure plan and terminal report are `artifacts/maintenance/stage-05.4-closure-plan.json` and `artifacts/maintenance/jobs/stage-05.4-closure/report.json`. Final accounting is `artifacts/stages/05.4/completion-accounting.json`. The global check is `artifacts/maintenance/storage-v2/budget-check.json`. The [receipt](../receipts/05.4.md) records commands, measured results, retained failures and byte totals.

For future assigned evidence batches, use the [managed runner contract](../../../docs/contracts/evidence-jobs.md). Preserve the reviewed profile-7 leg envelopes, including captured support anchors, thigh-relative flexion and knee bend-plane semantics. Keep the README freeze in force.
