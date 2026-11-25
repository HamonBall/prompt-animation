# Handoff — Stage 08 foundation migration

Updated: 2026-11-25. HEAD: `2fd0eff`. Status: active, partial.
Assignment: [Stage 08](../08-migrate-foundations.md).
Latest detailed evidence: [partial receipt](../receipts/08.md).
Stop boundary: Stage 09 needs a separate assignment.

## Done

- All seven named foundations have development recipe candidates. The
  user approved shared catalog/compiler and Blender request adapter work.
- Jump: both rigs match 2.6 s and 15 airborne samples. Upper arm excursion
  is 20° versus about 21–22° in the presets. Landing anchors passed.
- Walk: two and four steps match preset distance and duration on the
  tested rigs. Demo and Mixamo saved arm-swing bakes passed playback and
  front/side visual review at their recorded source.
- Run: two and four strides passed on both rigs from neutral. The recipe
  preserves flight, alternating single-sole landings and a two-sole finish.
  Turned Demo two-stride and Mixamo four-stride cases matched neutral preset
  duration, travel and ending stance width.
- Wave: the forearm follows explicit directions from the measured entry.
  Angular speed carries across continuous arcs and stops at reversals.
  Peak full-playback palm error is 2.39° on slow Demo and 6.78° on Mixamo.
  The turned Mixamo slow wave passed all 260 frames and rollback checks.
  Both saved cases passed front/side visual inspection and storage.
- The public neutral-standing wave now uses the recipe on Demo and Mixamo.
  Exact commands and unmodified model selections share a validated request.
  The 208-frame previews took 6.901 s on Demo and 15.316 s on Mixamo.
  Creative edits, timing corrections, and unsupported entries keep their
  existing paths. The native UI regression passed.
- A second Mixamo rehearsal took 14.351 s. The saved result reopened and
  playback matched at frames 1, 66 and 208. The visual checkpoint compared
  source, opening stance, raised shoulder and recovery at 720 px. See
  `artifacts/stages/08/mixamo/public-wave-first-preview/`.
- Local Mixamo has both palm references and packed textures. Local Andrejs
  imports and still waves through the previous preview, but lacks palms
  required by the measured wave. Neither is confirmed as a current studio
  delivery. Participant observation remains pending.
- Floor sit and lie: both neutral rigs passed a single 254-frame measured
  sit-to-back transaction. Reducing pelvis setback cleared the neutral
  Mixamo ankle limit. The separate five-second floor sit now passes all
  151 samples on both neutral rigs, releases both soles after seating, and
  finishes with pelvis support and a 15° bend in each knee. The candidate
  shifts the pelvis 611–625 mm, versus 66–68 mm in the preset.
- Run: the opt-in arm and torso candidate passed two neutral Demo strides
  and four turned Mixamo strides. Both reached the requested 65°/85° elbow
  bends, used 10° of distributed torso lean and recovered to the measured
  stance. Upper-arm rotation still differs from the preset.
- Chair: both rigs matched the 45 cm preset's 4.5 s duration and elbow
  bend within 0.47°. Demo matched pelvis placement and Mixamo was within
  2.362 mm. The 35 cm Demo and 55 cm Mixamo public prompts passed with
  the measured seated endpoint available to the follow-up editor.

## Remaining, in order

1. Confirm representative studio delivery and participant availability.
   Carry their evidence separately from the completed local rehearsal.
2. Extend public recipe routing beyond the initial wave and chair as parity
   passes. Preserve correction context, creative changes, approximate mode,
   and independent clips.
3. Resolve the floor-sit descent's pelvis travel and Mixamo's ending foot
   height, then add a measured replant from pelvis-only seating before
   sit-to-back. Complete walk elbow/torso and run upper-arm parity.
4. Complete current-source saved playback and full-motion visual review,
   required regressions, and final storage accounting. Retire duplicated
   legacy mechanics only when the corresponding cutover gates pass.

## Validation and workspace

- The 53-test foundation, coordinated-body, preset and recipe-composition
  suite passed in 16.924 s. Regenerated the two sequential fixtures for
  the previously changed standing-to-floor contact targets.
  The 18 compiler and spine/pelvis tests passed. Demo's live prompt suite
  passed public routing and airborne cancellation. The public 55 cm
  Mixamo chair check passed all 136 samples.
- `stage-08-jump-visual` completed, reusing both reopened bakes and both
  front/side view pairs. All 79 frames per rig were inspected from both views.
  The report records 4,166,937,920 retained bytes, within the existing cap,
  and zero temporary reservation. Retired 1,434,177 bytes of verified pilots.
  Review and retirement records are in `artifacts/stages/08/`. Public jump
  routing and its entry and follow-up checks remain open.

- The focused suite passed 46 tests in 13.691 s before chair centering,
  followed by 24 foundation/body tests in 7.336 s with the centering fix.
  The completed run
  matrix passed verification and storage; see
  `artifacts/maintenance/jobs/stage-08-run-pilots/report.json`.
- The walk review is hash-bound in
  `artifacts/stages/08/walk-visual-review.json`. Later shared edits changed
  source identity; this is evidence for the recorded source, not a fresh pass.
- `stage-08-wave-visual` completed with two verified bundles reused in
  closure. The review and media links are in `artifacts/stages/08/wave-review/`.
  The final managed report recorded 4,011,960,730 retained bytes and zero
  reserved temporary bytes. Use the
  current closure plan for these saved cases. Do not use the old raw
  Blender save steps to resume an existing bundle.
- `stage-08-chair-visual` completed with two reviewed cases and passed
  storage. Later public routing and forward forearm aim changed source
  identity. The incomplete Demo pilot was retired with a hash journal.
  Accounting then recorded 4,152,569,144 retained bytes and zero scratch.
- `stage-08-chair-refresh-visual` completed. Both 136-frame cases passed
  saved playback and front/side visual inspection. Closure reused both
  bakes and reported 4,161,717,954 retained bytes and zero temporary
  reservation. The previous chair case directories remain available
  and total 9,141,380 bytes excluding shared assets.
- The UI/adapter and direct-save guard changed the producer identity for
  earlier visual bundles. Preserve those results at their recorded source.
  First-preview storage passed at 4,079,296,671 retained bytes, zero
  temporary bytes, and no active writers. README remains frozen.
- Required source, docs, tests and handoff are Git-eligible. Preserve the
  unstaged and untracked changes. No commit or staging is requested.
