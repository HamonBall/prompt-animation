# Context continuity policy

Applies to Sol and all agents working in this repository, across stages,
maintenance, debugging and chat handoffs. This file contains standing rules;
task state belongs in the handoff, not an expanding conversation transcript.

## 1. Recover the current task before acting

1. Read AGENTS.md and to do/CURRENT-WORK.md. Follow the pointer to the active
   handoff, then read the assigned specification and only relevant contracts.
   Do not read every historical receipt or rescan the entire repository by default.
2. Apply the user's current request. A pending task, next-stage link or saved
   plan is not permission to execute it. Preserve explicit pauses and stop boundaries.
3. Inspect current Git HEAD/status and the specific files relevant to the next
   action. Preserve unrelated and uncommitted changes, including untracked documents.
   Never reset, stage or commit as part of recovering context unless requested.
4. Distinguish verified completion, partial work, queued work and unknown state.
   Treat receipts as evidence for their recorded revision, not automatic proof
   of current-source validity. Follow the validation policy for reuse.
5. If records disagree, compare dates, revisions, changed dependencies and actual
   output identities with narrow reads. Reconcile the live handoff; do not rewrite
   historical evidence. Ask only if an unresolved decision or authorization blocks
   progress. Do not make the user repeat information already available in files.

After compaction, recover only missing state. If the active handoff and constraints
are already present and unambiguous, continue without repeating startup exploration.

## 2. Maintain one current pointer and one task handoff

to do/CURRENT-WORK.md is a short index: current assignment/status, handoff path,
last completed stage and explicit next-stage boundary. Keep it under 40 lines.
Create and update numbered-stage handoffs in `to do/stages/handoffs/RESUME-<stage>.md`. For maintenance
use a named RESUME file alongside its assignment. Do not create competing summaries
for the same task. Full receipts and logs remain linked supporting evidence.

Target 60 lines or fewer for a live handoff. Preserve essential facts over that
soft limit, but move detailed chronology to the existing receipt. Rewrite obsolete
status in place; do not append endless timestamped copies. Use this structure:

```markdown
# Handoff — <task>
Updated: <date>; HEAD: <commit>; status: <active/paused/needs_review/complete>
Assignment: <spec path>; authorized scope: <one sentence>
Stop boundary: <what is explicitly not assigned>

## Done
- <verified outcome; files and evidence path; revision/identity when relevant>

## Remaining, in order
1. <next exact action and its completion condition>

## Decisions and constraints
- <reason for non-obvious choice; supported envelope; unresolved question>
- <failed approach and concrete reason not to repeat it, only if still relevant>

## Validation
- Executed: <commands, result, scope, report path>
- Reused: <evidence and identity basis>
- Failed/not run: <exact scope and reason; do not conflate these>

## Workspace and jobs
- Changed/untracked files: <owned paths; unrelated edits to preserve>
- Job: <none, or job ID, plan/report path, owner/session, last observed state>
- Storage: <last measured totals/reservation and evidence date, if applicable>
```

Never invent a commit, pass, review, active process or measurement to fill a field.
Use unknown/not checked when necessary. Store no secrets or full console dumps.

## 3. Update at meaningful checkpoints

Update the handoff after a stable implementation milestone, validation completion,
an important changed decision, launching a long job before handing control back,
or a pause/failure that changes the next action. Also update before a requested
chat handoff and before ending a turn with unfinished authorized work.

Do not rewrite it after every command, log line or routine question. Documentation
updates must not start expensive tests or renders. On completion synchronize the
current pointer, AGENTS checkpoint when changed, stage index and latest handoff;
keep historical receipts intact and README frozen.

## 4. Prevent repeated work and wasted context

- Start from the first unfinished action. Reinvestigate a completed item only for
  a relevant change, failed integrity check or specific unresolved concern.
- Read narrow source ranges and compact terminal reports. Keep verbose logs on
  disk; inspect failure excerpts only when they inform the next action.
- Preserve the distinction between implementation, numeric validation, render
  verification, actual visual review, publication and storage closure. Passing
  one does not imply the others passed.
- Before rerunning evidence, establish why existing evidence cannot be reused.
  Do not weaken identity checks or relabel reused checks as executed.
- Follow the managed evidence-job contract. Do not create duplicate jobs because
  the previous chat ended. A recorded session ID is a locator, not proof the
  process is alive or that another chat can control it. Check its report and
  supported ownership/lease state once; reconcile an uncertain owner before launch.
- Never fabricate visual review to resume a job. Record needs_review as a real
  remaining action. Keep supervisor sessions alive as required by the host.

## 5. Chat boundaries

Prefer a fresh chat for a newly assigned numbered stage or a separate substantial
maintenance task. Within a large task, use a stable milestone when useful. There
is no mandatory message count, duration or compaction count for restarting.

If repeated rediscovery, contradictory state or context recovery prevents progress,
save a verified handoff and recommend a fresh chat. Do not automatically abandon
work or create a chat. Do not switch away from an active native job without recording
ownership and a safe continuation procedure. A new chat should require only the
task assignment: the files provide the continuation context.

## 6. Portability check

At handoff/closure verify that required instructions and handoff files are not
ignored and identify untracked files needing inclusion in the user's commit.
Eligibility for tracking is not a commit. Do not force-add files or commit without
authorization. A fresh checkout needs the relevant committed documentation and
separately available source assets/evidence; never claim local artifacts transfer
automatically with a chat or Git commit.
