# Context continuity policy

Applies to Sol and all agents working in this repository, across stages,
maintenance, debugging and chat handoffs. This file contains standing rules;
task state belongs in the handoff, not an expanding conversation transcript.

## 1. Recover the current task before acting

1. Read AGENTS.md and to do/CURRENT-WORK.md. Text already supplied in the active
   context counts as read; fetch it again only for missing details or likely changes.
   For stage work, follow the active handoff; for a separate task, use the pointer
   to preserve the stage boundary and read only that task's specification/contracts.
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

These defaults apply to Sol and other agents. They limit avoidable context, not
the work required for correctness. Expand when needed for a concrete decision;
briefly state the reason rather than asking permission for ordinary investigation.

- Before retrieval, identify the missing fact and smallest likely source. Start
  with named files or directories: `rg --files <path>` for discovery, `rg -n`
  for symbols/headings, then a focused range. Use `rg -l` when only filenames
  are needed. Exclude artifacts, assets, logs and historical receipts from routine
  source searches; include them explicitly when the task needs their evidence.
- Default source excerpts to at most 120 lines per file and tool output to about
  2,000 tokens per call. These are local starting limits, not measured optimal
  settings. Read complete small files when useful and expand to full functions,
  callers or contracts when needed. Never infer missing content from truncation.
  After truncation, narrow the query or request the missing range; do not repeat
  the same oversized dump with a larger cap by default.
- Batch independent, bounded reads/searches into one call where supported.
  Keep dependent reads and mutations sequential. Do not batch whole documents
  merely to reduce call count. Parse large JSON/logs locally and return the fields,
  counts and failure excerpts needed for the decision, retaining the source path.
- Reuse facts and file ranges already in this chat. Reread only after an edit,
  possible concurrent change, missing context or a specific verification need.
  Do not reopen historical handoffs or broad memory/session logs for routine work.
  After compaction recover the missing next action and constraints, not all history.
- After two searches/reads that add no actionable information, change the query,
  inspect the direct caller/test, or state the precise blocker. Do not keep looping
  through the same files. Once evidence supports a fix, implement and validate it;
  expand exploration only for an unresolved risk or failed check.
- Use short plans for multi-step work and concise updates with new findings.
  Keep detailed logs on disk; do not restate the plan or narrate every command.
  Use existing runners for repetitive work. Do not spawn agents unless explicitly
  assigned; when authorized, give bounded scope and request findings/paths rather
  than duplicate repository exploration or full transcripts.
- Validation follows `validation-efficiency-policy.md`: targeted checks while
  developing, required full coverage at its gate, and no rerun after a pass without
  a relevant change/failure. Documentation-only work needs diff/link/consistency
  checks, not native renders or a new benchmark suite.

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
