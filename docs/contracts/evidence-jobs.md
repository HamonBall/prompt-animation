# Quiet evidence jobs

Implemented 2026-11-04 in `tools/evidence_job.py` and `tools/evidence_pipeline.py`.
The supervisor uses ordinary local Python, with zero model/API calls. This does
not make Blender faster or eliminate tokens used for actual diagnosis/review.

## Agent execution rule

Launch one bounded job. Keep frame logs on disk. Do not repeatedly inspect PIDs,
tail logs, count files or reconstruct commands while it runs. Work on independent
authorized tasks, or hand back control. Use a host-provided completion event if
available; this runner does not invent a Codex wake-up API. Without a completion
event, use managed `start` in a persistent tool session, end the turn with the
session/job/report location, and read the result when the user resumes. Keep the
session alive: this host killed the detached-launch pilot when its launcher
exited. `start` therefore retains a silent guardian process until completion.
The worker does not itself wake the chat.

For short work, `run` prints exactly one compact terminal JSON report; use the
tool's existing session handle and longest permitted wait, not shell polling.
`wait --seconds 50` is a single bounded wait, not a command to repeat forever.
If it still reports running and no independent work remains, hand back control.
Progress inside the worker costs no model tokens. The report and CLI status-call
counter measure orchestration activity, not unavailable host token billing.

## Commands

From `C:/work11`, with Blender's bundled Python:

```powershell
$jobPython = 'C:/Program Files/Blender Foundation/Blender 5.1/5.1/python/bin/python.exe'
& $jobPython tools/evidence_pipeline.py build --config <pipeline.json> --plan <job-plan.json>
& $jobPython tools/evidence_job.py start --plan <job-plan.json> --job artifacts/maintenance/jobs/<job-id>
# Only on completion notification or a later user resume:
& $jobPython tools/evidence_job.py report --job artifacts/maintenance/jobs/<job-id>
# Explicit cancellation, if needed:
& $jobPython tools/evidence_job.py cancel --job artifacts/maintenance/jobs/<job-id>
```

`start` emits a launch acknowledgement and one terminal summary; it must be
launched through a tool that retains a running session, rather than a command
that kills unfinished children on return. For foreground automation without
the launch acknowledgement substitute `run` for `start`. Resume
uses the same command/plan/job directory. Existing producers revalidate their
source/runtime/output identities on every invocation; the supervisor never skips
a command just because an older job report says it passed. Its lock prevents
simultaneous owners. It will not reclaim a previous worker still reported alive.

## Windows progress window

Managed `start` opens the viewer automatically on Windows. An existing
window for the same jobs folder keeps following new jobs. Use `--no-viewer`
for a managed session that runs without a desktop window.

From the repository root, open the local viewer with:

```powershell
powershell.exe -NoProfile -STA -File .\tools\watch_evidence_jobs.ps1
```

The window refreshes every two seconds and follows the newest active job by
default. Select a job to keep it in view. It shows the current step, completed
numeric and render steps, elapsed time, and whether the job failed or needs
review. The progress bar advances at runner step boundaries. Use the review
folder button to find the generated inspection pages. `-JobsRoot` can point
to another directory containing job folders, and `-Snapshot` prints one JSON
view. The viewer reads reports directly and can be closed independently of
the managed runner session.

## Pipeline adapter contract

Developer-authored configuration has exactly these fields:

- `schema_version: 1`.
- `preflight_argv`: measured budget/runtime/writer checks.
- `numeric_gate_argv`: complete current numeric/functional validation for this
  bounded group; may execute a required missing numeric phase, using strict reuse.
- `cases`: 1–250 records with `id`, artifact `directory`, `check_argv`,
  `render_argv`, and a finite `timeout_s`. Use smaller batches where retention
  requires human review before more media fits the budget.
- `verify_argv`: independent saved-motion/media checks.
- `review_directory`: small generated review index/pages inside artifacts.
- `review_check_argv`: validate actual inspected-review records against current
  evidence; exit 75 when inspection/retention remains necessary, not a sleep loop.
- `storage_argv`: final required budget/accounting checks.

All commands are argument arrays with `shell=False`. These are trusted local
developer commands, never raw model output from the avatar application's prompt.
Use single-case producers inside each case, not a batch driver which waits for
human review. Case `check_argv` returns 0 for verified current reusable evidence,
10 only for missing output safe to generate, and any other code for invalid or
stale evidence needing reconciliation. The wrapper reruns this check after a
successful renderer. Never map all validation failures to 10.

Existing native rendering should include encoding, decoded-pixel verification,
atomic bundle publication and PNG retirement through the shared tools. Additional
pipeline verification remains independent. No schema/hash/tolerance checks are
disabled. A failed numeric gate prevents rendering; a failed producer cannot be
accepted just because it left media files behind.

`tests/evidence_job_smoke.py config` writes a runnable, tiny example pipeline
under `artifacts/maintenance/evidence-runner/`. It creates a demo head-look through
the real producer, then renders two 64px views, verifies lossless media, publishes
review pages and stops for real inspection. It is an integration pilot, not a
substitute for a stage's reviewed rig/range matrix.

## Supervision, recovery and reporting

Low-level plan schema is `{schema_version: 1, steps: [...]}`. Each step requires
`id`, `phase`, `argv`, `timeout_s`; phases are ordered preflight, numeric, render,
verify, review, storage. Preflight/numeric/verify/storage are mandatory; render
plans need review. Optional `case_id` identifies case summaries.

Every command has a hard deadline. Optional `idle_timeout_s` and `progress_paths`
detect stalls using output activity or declared progress-file timestamps. Idle
timeouts are disabled by default because a quiet encoder can be healthy. Choose
deadlines from measured workload plus margin; do not use a short silence timeout
as a guess about Blender progress.

Windows workers start suspended, are assigned to a kill-on-close Job Object,
then resume. POSIX workers get a process group. Timeout/cancellation terminates
owned descendants. On supervisor death the Windows job closes; on POSIX, inspect
recorded remaining worker identities before resuming. No unrelated process is
killed by a global process-name search.

Default retries: zero. An optional `retry` declares `exit_codes`, a classification
`reason` and `recovery_argv`. At most one retry follows successful recovery; both
attempts and recovery are recorded. Recovery must reconcile producer leases and
validate partial output. Native access violations are not silently classed as
transient. Exit 75 is never retried automatically.

Statuses: `completed`, `needs_review`, `failed`, `cancelled`, or `interrupted`.
Completed means the configured automated pipeline gates passed, not that the
entire project/stage is complete. Review indexes never claim actual inspection.
Pages embed the existing sheets at original resolution and link full-motion
movies. Selected-frame sheets are explicitly labelled; they cannot replace a
new full-motion inspection.

The terminal report contains case counts, phase elapsed times, storage check,
review index paths and at most a short failure excerpt. Per-step compressed logs
are bounded (8 MiB uncompressed per attempt, 32 MiB combined retained diagnostics);
excess output is drained without growing the conversation or file indefinitely.
Truncation is recorded. Reusing a job directory overwrites its latest attempt
logs/report; pin a needed failure reproduction under the retention policy before
rerunning. No timestamped full-run trees are created automatically.

`status-requests.json` counts CLI report/wait/cancel calls separately from the
worker report. Internal subprocess checks are local Python operations, not agent
turns. Actual token savings must be measured at the host; no claimed percentage
or continuous-memory guarantee is inferred from these counters.
