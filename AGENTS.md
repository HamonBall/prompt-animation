# Project instructions

## Context continuity — every session

Read `docs/context-continuity-policy.md` and `to do/CURRENT-WORK.md` at the start of project work and after context loss/compaction when the active state is unclear. Follow them for every stage and maintenance task without waiting for a reminder. Keep the current-work pointer and the assigned task's handoff current at meaningful checkpoints. A saved plan is not authorization to start it. Do not repeat completed work merely because a chat is new.

## Generated artifacts and storage

Before running tests, renders, benchmarks, preview generation, migration or maintenance that writes artifacts, read `docs/artifact-retention-policy.md` and follow it. It applies throughout this repository, including numbered movement stages and one-off diagnostics.

- Inspect existing outputs and active writers; estimate growth before large runs.
- Use the shared artifact writer and the supported bundle format. Do not create repeated packed avatar scenes, automatic Blender backups or unbounded timestamped run copies.
- Use the implemented storage-v2 bundles and checks; read its receipt for supported representations and measured limits.
- Preserve accepted motion, required numeric/visual evidence and all user/source assets. Retire only verified generated history within the assigned scope.
- Count shared assets, maintenance, exports and temporary files. Complete budget checks, owned-scratch cleanup and before/after storage accounting before reporting a stage complete.
- Never meet a storage target by weakening tests, moving files outside the accounting scope or deleting unrelated data.

Stage-specific instructions and receipts remain under `to do/stages/`. The storage implementation assignment is `to do/storage-reduction-and-retention-plan.md`.

## Validation efficiency

Before selecting validation commands, read `docs/validation-efficiency-policy.md`. It applies to every stage and maintenance task, not just movement-library work.

- Use targeted unit/contract checks and small demanding smoke sets during development. Run complete required coverage when the component is stable and at its completion gate.
- Pass numeric/functional checks before bulk rendering. Generate accepted visuals from validated saved motion; use extra views only for an identified review need.
- Reuse evidence only through valid dependency/input/runtime/output identity checks. Changes to shared mechanics invalidate affected consumers. Never bypass source validation or call reused results newly executed.
- Preserve proven native-process isolation; benchmark worker batching and concurrency before changing them. Do not blindly repeat crashes or full suites.
- Measure phase timings, estimate expensive batches, respect storage budgets and report executed/reused/not-run checks. After checks pass, rerun only when changes, failures or unresolved concerns justify it.
- Keep all required final cases, rigs, tolerances, full-motion and UI/model checks. Efficiency changes must not weaken completion gates.

## Long-running evidence jobs

Use `tools/evidence_job.py` and the contract in `docs/contracts/evidence-jobs.md` for long renders/validation pipelines. Build a bounded plan around existing strict producers/validators; let local code supervise render, encode, verify, publish and budget checks. Use single-case adapters when a legacy driver has a human-review window.

- Launch once. Do not repeatedly tail logs, query processes, scan folders or ask the model whether to keep waiting.
- Prefer completion events when the host supports them. Otherwise use managed `start` in a persistent tool session, report the session/job location and end the turn when independent work is exhausted. Resume on user input. Keep the tool session alive; this host may kill detached descendants when their launcher exits. Do not claim that background work automatically wakes this chat.
- For short foreground jobs, reuse the returned tool session and longest permitted wait. After one bounded wait still reports running, hand back control instead of starting an agent polling loop.
- Read the compact terminal report once. Inspect detailed logs only for an actionable failure; perform actual required visual inspection using the generated index/pages.
- A `needs_review` result is a real human/agent inspection boundary. Never fabricate review records or bypass retention gates to keep the worker busy. Preserve the existing paused-stage boundary unless the user resumes that stage.

## README freeze during development

Do not edit, regenerate or revert `README.md` during ordinary implementation, stage completion or maintenance. Defer README work until the user explicitly requests a README update or lifts this freeze. Existing README changes must remain intact.

Keep implementation contracts, project policies, stage documents and completion receipts current. Record deferred README changes briefly in the relevant receipt. This rule overrides older plans that include README updates; deferring that portion does not block an otherwise completed stage. Do not repeatedly ask permission to edit README while the freeze is active.


## Current work checkpoint

Stage 05.6c is complete as of 2026-11-12 in the working tree based on `d2f2e74`. Read `to do/stages/receipts/05.6c.md` and `to do/stages/handoffs/RESUME-05.6c.md` for the verified checkpoint. Stage 05.7a awaits explicit assignment. Preserve current changes and frozen README.md. Store numbered-stage handoffs in `to do/stages/handoffs/RESUME-<stage>.md`.

## Maintenance and future handoffs

Read `to do/validation-storage-handoff-maintenance.md` when assigned audit/storage maintenance. It is a separate assignment, not permission to start another movement stage. Its future-stage rules also apply at subsequent completion gates.

- Keep this checkpoint, the stage index and the latest handoff consistent. Historical receipts remain historical.
- Project instructions, policies, contracts, stage plans and handoffs must be eligible for Git tracking. Check their Git status; a clean tracked diff does not establish that ignored instructions are preserved. Do not commit or stage changes unless requested.
- Follow the transition coverage requirements in `docs/validation-efficiency-policy.md`; prepared-pose contact tests do not prove arbitrary entry transitions or dynamic balance.
