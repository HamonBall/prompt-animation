# Stage 05.5 handoff

Status **complete, 2026-11-09**. The stage started at `81585f5` and was
validated in the uncommitted working tree. Read AGENTS.md, the
[specification](../05.5-ankles-feet-toes.md), [receipt](../receipts/05.5.md), and
[profile-8 contract](../../../docs/contracts/ankles-feet-toes-v1.md) before
resuming related work.

- Profile 8 adds rigid heel and forefoot anchors to the existing sole
  calibration. Capture a fresh entry after profile migration. Profiles 1–7
  keep the prior contact path. The supported foot mechanics use the existing
  leg IK and captured opposite sole. Fine toe curl needs a mapped toe and is
  unavailable on Demo.
- The current numeric and visual gates passed 123 cases and 13,227 samples
  on Demo and Mixamo. All 246 complete view sequences were reviewed. Native
  boundaries, profile compatibility, legacy floor/seat, and unit discovery
  passed. Published profile-8 fixtures under `tests/fixtures/ankles_feet_toes/v1/`
  include reviewed per-rig envelopes and the explicit missing-toe result.
- All 16 managed visual batches passed their storage checks. The final
  storage-v2 check validated 989 bundles. Conservative storage is
  363,714,762 stage bytes and 3,101,803,843 global bytes. Final temporary
  bytes and writer leases are zero.

Closure evidence lives in
`artifacts/maintenance/jobs/stage-05.5-closure/report.json`.
See `artifacts/stages/05.5/visual-review.json`,
`publication-summary.json`, and `completion-accounting.json` in the same
stage evidence directory. Reuse these verified outputs when their identities
match. The README freeze remains in force. Stage 05.6a awaits assignment.
