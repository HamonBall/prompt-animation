# Handoff — Stage 05.6c coordinated body movements

Updated 2026-11-12. Status complete in the working tree based on `d2f2e74`.
Assignment [05.6c coordinated body movements](../05.6c-coordinated-body-moves.md).
The user will commit. Stage 05.7a and the separate maintenance assignment
await explicit assignment.

## Delivered

- Seven profile-8 coordinated movement IDs through the typed fragment and
  fixed-support execution bridge. The [receipt](../receipts/05.6c.md)
  records the per-ID entry states, bounds, review results and exclusions.
- Demo and Mixamo hands-and-knees crawl from prepared quadruped support.
  Reviewed 60 mm per cycle and verified two consecutive cycles on both rigs.
  The hands-and-feet route remains available from prepared palms and soles.
  Its revised 40 mm and 100 mm cases show controlled lifts and replants
  with a stiff gait. Standing-to-crawl and prompt composition remain outside
  this stage.
- Published 48 reviewed cases, 28 typed fixture examples and 5,417 motion
  samples in `tests/fixtures/coordinated_body_moves/v1/manifest.json`.

## Validation

- Current-source batch passed 261 unit tests with 12 skips and nine native
  regressions. The initial boundary lookup failure stopped that batch
  before rendering. The repaired group-aware lookup passed three routing
  tests, a native pilot and the other 17 boundary comparisons.
- All four revised hands-and-feet bakes passed numeric checks, independent
  playback and visual review in both views. Both hands-and-knees bundles
  also passed playback and visual review in both views.
- Final publication refreshed 24 baseline comparisons under the current
  validator and verified the 18 boundary proofs. It reused the reviewed
  media for those 42 cases and verified the six current crawl bundles
  directly. Earlier baseline proofs were preserved.
- The final publication report at
  `artifacts/maintenance/jobs/stage-05.6c-current-publication/report.json`
  completed in 1,545.574 s. The audit verified 1,123 bundles with zero
  errors and zero temporary bytes. Artifact-root accounting increased
  from 3,311,536,859 to 3,614,555,146 bytes. See
  `artifacts/stages/05.6c/completion-accounting.json`.

## Workspace

- Receipt, movement coverage, stage index and current-work pointer record
  closure. Implementation and evidence fixtures are ready for the user's
  commit. README changes remain deferred.
