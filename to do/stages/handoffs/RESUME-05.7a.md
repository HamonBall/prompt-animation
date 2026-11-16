# Handoff — Stage 05.7a timing, repetition and coordination patterns

Updated 2026-11-16 in the working tree based on `30b3083`. Status complete.
Assignment [05.7a](../05.7a-timing-patterns.md), authorized 2026-11-15.
Stage 05.7b, general recipe composition and separate maintenance await assignment.

## Done

- Implemented the eight timing transforms and five pattern families through
  one typed fragment. The [contract](../../../docs/contracts/fragment-execution-v1.md#stage-057a-timing-and-finite-repeat)
  describes the current bounds, quintic easing and translation-only loop proof.
- First managed evidence batch finished with four reviewed storage-v2 cases.
  Both rigs passed alternating strokes and two-step translating cycles and
  continued from the measured exit. The [receipt](../receipts/05.7a.md)
  records measured residuals, visual observations and passed storage checks.
- The baseline runner verified all 26 cases and produced 52 views. All are
  now visually approved, covering measured baseline cases for every stage ID
  on Demo and Mixamo. The [receipt](../receipts/05.7a.md#baseline-review)
  records the visual observations, maxima and passed storage gate.
- Published 58 reviewed fixtures in `tests/fixtures/timing_patterns/v1/`,
  including two current-source replacements for the unilateral arm variants.
  The manifest references 117 content-addressed typed records.
- Fixed upper-arm activation during undulation by holding each selected world
  orientation through the torso lead-in. The earlier 20° both-arm pilot had
  snapped the left arm at activation. The fixed 335-frame Demo case passed.
  `tests/timing_baseline_compatibility.py` reconstructs and verifies the exact
  predecessor source identity and all outputs. It proved 28 approved cases are
  unaffected. The two original arm follow-through cases require replacement.

## Stop boundary

Stage 05.7b awaits explicit assignment. The stage changes are in the working
tree for the user's commit. README updates remain deferred.

## Validation and jobs

- Body pilots completed, including Mixamo sway, undulation and right-led
  traveling steps. Full unit discovery ran 289 tests with 12 skips and
  pre/post storage passed. Report `artifacts/maintenance/jobs/stage-05.7a-body-pilots/report.json`.
- `stage-05.7a-operator-pilots` passed all four Mixamo turned-crouch cases
  and failed at Demo turned-crouch mirror. The test reflected an explicit
  asymmetric start. Its corrected native pilot asserts that rejection,
  then mirrors the destination with a measured-entry binding. Demo passed
  all 31 frames with 0.0000072° maximum sample error.
- Stroke and torso parameter corners authored on both profiles. Step
  corners authored on two prepared crouched fixtures (one 60 mm step and
  four 160 mm steps). Demo's neutral straight-leg entry rejected the same
  low-clearance target at the leg-reach check. The focused pattern/contract
  suite passed 50 tests in 9.771 s.
- `stage-05.7a-baseline-evidence` passed seven operator/pose checks and all
  26 bakes, independent replays and media checks. Its report records the
  original review stop at 3,537.782 s. The 25 pending approvals are now
  in `artifacts/stages/05.7a/visual-review.json` with no new bake or render.
- The baseline storage check passed directly at 3,718,644,914 retained bytes
  after scratch cleanup, with zero temporary bytes.
- `stage-05.7a-range-evidence` passed the baseline identity check, full unit
  discovery (295 tests with 12 skips) and three upper numeric bakes. It
  stopped before rendering at Mixamo's four 160 mm steps. The alternate
  lead crossed the unchanged 3 mm floor threshold (3.113 mm). Investigation
  found the original sole-height correction accumulated on later swings.
  The repaired original Mixamo case passed all 385 frames with 1.5562 mm
  penetration. A focused regression checks both repeated landings.
- The split-corner recovery was cancelled after its two-step maximum-stride
  bake passed. The full original corner now passes, so the separate probes
  are superseded. Six source-bound predecessor directories were preserved
  and hash-journaled in `artifacts/stages/05.7a/floor-fix-predecessor-journal.json`.
- The baseline identity check validated 28 approvals after the two localized
  fixes. The two unilateral arm variants passed replacement visual review.
- `stage-05.7a-range-current-source` ran 296 unit tests with 12 skips
  in 143.630 s and passed 28 of 30 numeric bakes. Both unilateral waves
  failed the harness's 3° single-segment assertion. A 5° wave distributes
  that angle across the spine. A separate adapter checks each segment's
  authored peak and return, preserving the original harness for the other
  28 cases. Both replacement pilots passed all 111 frames.
- The replacement adapter now enters through Blender's native script path
  and returns to Blender for its normal shutdown. The two final saved
  bundles both passed the strict numeric validator after correcting those
  integration failures.
- The range runner passed 30 bakes and nine affected native regressions,
  rendered and verified 60 views and stopped at its review gate. Report
  `artifacts/maintenance/jobs/stage-05.7a-range-completion/report.json`.
  All 30 cases have now passed actual full-motion review and their approvals
  are recorded in the stage's `visual-review.json`. Review scratch was removed.
- `stage-05.7a-final-storage` passed review recheck, publication, retirement
  and strict storage audit. Its [receipt](../receipts/05.7a.md#publication-and-storage-closure)
  records 1,184 verified bundles, zero final temporary bytes and zero
  active writer leases. No managed stage job remains active.
