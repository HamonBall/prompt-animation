# Quiet evidence runner maintenance

Status: complete for the shared supervisor, pipeline builder and tested pilot,
2026-11-04. This is maintenance for Sol's future runs, not movement-stage work.
Stage 05.4 remains paused with its existing storage/accounting gates pending;
05.5 was not started. Existing uncommitted stage changes were preserved.

## Delivered

- `tools/evidence_job.py`: ordered trusted-argv jobs, mandatory preflight/numeric/
  verification/storage phases, bounded per-command deadlines, optional progress
  timeout, process-tree ownership/cancellation, compressed capped logs, one
  classified retry only after successful recovery, compact reports and resumable
  managed sessions. No AI/model API calls occur inside this supervisor.
- `tools/evidence_pipeline.py`: universal adapter builder for existing strict
  per-case checks/producers, numeric-first rendering, saved-motion verification,
  indexed original-resolution sheets/movie links and an actual-review gate.
  Missing safe-to-create output is distinct from stale/invalid evidence. The
  generated commands pin the pipeline configuration hash.
- `tests/test_evidence_job.py`: 15 focused checks, including actual native child
  processes and descendant termination. `tests/evidence_job_smoke.py` supplies a
  small real-Blender pipeline example using the existing shared writer and codec.
- The existing `tools/run_hips_knees_render.py` no longer sleeps indefinitely at
  its review/retention window: it exits 75 with a review request. Only this
  supervision branch was changed; no leg mechanics or stage output was changed.
- `AGENTS.md`, the validation policy and shared stage guide require quiet jobs and
  prohibit repeated agent-side polling. Exact commands/contracts are in
  `docs/contracts/evidence-jobs.md`. README remains frozen and unchanged.

No universal job can infer all future validators or human-review criteria.
Each future task supplies its existing validator/producer argument arrays in the
documented configuration. The runner does not replace their provenance checks,
weaken their numeric gates or fabricate visual approval.

## Verified behavior

Final focused command:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.1/5.1/python/bin/python.exe' -m unittest discover -s tests -p test_evidence_job.py -v
```

All 15 tests passed. They exercise quiet/capped output, numeric-failure short
circuit, review exit instead of waiting, deadline and idle timeout, cancellation,
Windows descendant termination, one classified recovery/retry, retry exhaustion,
fresh validation on resume, shell/phase rejection, stale configuration rejection,
render reuse versus invalid-output rejection, restart status and managed launch.
Initial test setup hit Windows sandbox temporary-directory permissions; fixtures
were moved to explicitly owned workspace scratch and cleaned after each test.

The real pilot ran one default-avatar head-look through the existing producer,
25 frames in each of two 64px views. The first run rendered, encoded, verified
decoded media and published review pages, then returned `needs_review` in
76.435 seconds. Recorded phases: preflight 4.163 s, numeric generation 31.165 s,
render/encode/publication 33.052 s, verification .484 s and review/index 4.258 s.
It did not wait for an invented visual approval.

Both complete sheets were actually inspected: the body remains visible without
clipping/missing cells. This small-view pilot validates orchestration; it makes
no new claim about movement accuracy or reviewed anatomical envelopes. The
approval pins its manifest hash and is stored separately.

A first detached-launch experiment was stopped by the execution host when its
launcher exited. The implemented `start` therefore keeps a silent guardian in
the persistent tool session. The corrected managed-session resume completed in
21.084 seconds, reported one reused case, performed no native render, and passed
the final configured review/storage gates. All 17 pilot payload files retained
identical hashes, sizes and mtimes. Per-step times include validation overhead;
this is not a claimed Blender speedup or host token-cost benchmark.

The supervisor makes zero model calls and emits a launch acknowledgement plus a
terminal summary in managed-start mode. CLI report/wait/cancel calls are counted
separately. No automatic Codex wake-up facility is claimed: keep the managed tool
session alive, use a completion event if supported, otherwise hand back its
session/report location and resume when the user returns. Never keep the model
active solely to check progress.

## Evidence and storage

Evidence: `artifacts/maintenance/evidence-runner/`, including the runnable
`pipeline.json`, `plan.json`, `job/report.json`, `review/review-index.json`,
`review-approval.json`, `pilot-before.json` and `verification.json`.

Final measured pilot payload: 398,389 bytes / 17 files. Runner maintenance
directory at verification: 416,820 bytes / 35 files, before adding the small
verification record itself. Whole artifact inventory: 2,736,677,889 bytes /
63,321 files. Shared assets remain 64,209,506 bytes; no additional avatar asset
was introduced. Owned temporary bytes zero; active writer leases zero. Accepted
stage outputs were neither regenerated nor retired.

The pre-task handover inventory was provisional, so its difference is not
represented as a precise isolated maintenance-growth measurement. This task's
retained output is reported directly above, and unchanged pilot payload is
verified by hashes. Generated Python caches outside artifacts are small tool/test
caches, not an alternative evidence store. No new data dependency or download.

README SHA-256 remains
`57dd7de96640eb40e5a6ac4541edc6c8e1784e693ead5ee970754be8238059ab`.
`git diff --check` passed. No full historical matrix or paused-stage completion
command was rerun. Existing stage-specific numeric/media evidence remains under
its original provenance and review records.
