# Sol assignment — validation cost, storage capacity and reliable handoffs

Status: ready for implementation. Documentation/checkpoint corrections are applied;
audit optimization and storage reclamation below are not yet implemented by this assignment.
This is maintenance, not Stage 05.6c. Do not begin another numbered stage.

## 0. Read and establish the baseline

Read AGENTS.md, docs/artifact-retention-policy.md,
docs/validation-efficiency-policy.md, docs/contracts/evidence-jobs.md,
docs/contracts/artifact-storage.md, the storage-v2 receipt and the 05.6b
receipt/handoff under to do/stages/. Inspect current Git changes and preserve them.
Do not edit README.md, avatar data, accepted motions, animation solvers or tolerances.

Recorded 05.6b baseline (historical, refresh before writes): 1,063 bundles;
3,314,920,461 conservative retained bytes under a 4 GiB limit; 859.661 s for
the global audit. The implementation is committed as d2f2e74. Stage 05.6c
still requires explicit assignment.

Inventory active writers and retained classes once. Identify the exact audit
entry path in tools/storage_v2.py, tools/artifact_bundle.py and their shared
helpers before editing. Use existing reports for baseline timing; do not run
another full audit merely to recreate that number.

## 1. Reduce audit cost without reducing audit coverage

### Plan and execution

1. Instrument compact phase timings, bytes actually hashed, unique shared assets
   and repeated asset validations. Use one bounded representative subset containing
   multiple bundles sharing an asset, multiple assets and the supported bundle/media
   representations. State its selection; do not benchmark all historical renders.
2. Locate the dominant cost. If repeated shared-asset hashing is material, add an
   explicit per-audit verification context so a referenced immutable asset is
   content-verified once within that protected read-only audit. Verify every
   bundle's manifest, references and unique payload independently. Never reuse
   a bundle pass just because its asset passed.
3. Establish exclusive mutation protection using the existing lease protocol.
   Inspect whether every supported writer honors it. Detect conflicting writers,
   path escapes and changes during verification; fail closed. If immutability
   cannot be established, keep the strict path instead of trusting mtime/size.
4. Preserve an uncached strict reference mode. Do not add a persistent cross-run
   cache, change native-process isolation, or rewrite the artifact format here.
   If hashing is not dominant, report the measured bottleneck and implement only
   an equivalent bounded improvement in that audit path.
5. Keep a single compact terminal report: scope, pass/error counts, phase times,
   bytes hashed, reuse counts and storage totals. No per-file chatter in the chat.

### Testing

Compare optimized and strict results on the same small fixture set. Include valid
shared references, a corrupted unique payload, a corrupted shared asset affecting
multiple references, missing files, invalid manifest/reference, path escape,
conflicting writer and mutation between two references. Include replacement with
the same size and restored mtime: metadata alone must not establish integrity.
Use owned small fixtures; never corrupt accepted production evidence for a test.
Repeat the audit and verify no unbounded output or new scene/asset copies.

### Validation gate

Both paths must identify the same valid/invalid cases and budgets. Where safe reuse
is implemented, measured shared bytes hashed must scale with unique shared assets,
not reference count. Compare elapsed time on the identical subset; adopt the change
only with a measured benefit and equal integrity. Do not promise a fixed speedup.
Run one full final global audit after stable changes and any approved cleanup;
do not repeat it without a relevant change or failure. Use the managed job runner.

## 2. Recover capacity and bound future growth

### Plan and execution

1. Produce a small inventory of reclaimable generated data, with paths, category,
   current bytes, replacement bytes, references and verification needed. Prioritize
   older PNG sequences eligible for the existing lossless representation, verified
   superseded outputs and owned stale scratch. Count shared assets and outside-tree
   generated files. Do not infer that a shared asset is redundant from its filename.
2. Target at least 512 MiB of actual net reclamation if eligible data permits it.
   This is a planning target, not authority to discard unique accepted evidence.
   If less is safely reclaimable, recover the eligible amount and report the exact
   shortfall and reason. Do not claim this target has already been achieved.
3. Use existing supported migration/encoding and retirement tools. Inspect their
   reference-update and verification behavior first. Stream small bounded batches;
   keep peak temporary usage within 512 MiB and total retained usage within 4 GiB.
   No whole-tree backup or rerendering of accepted animations.
4. Verify decoded pixels, all frame indices and timing for lossless replacements.
   Preserve baked motion, measurements and review provenance. Update manifests and
   review references through supported migration rules; never forge a new visual
   inspection. Commit replacement files and the retirement journal atomically
   before deleting enumerated originals. This means filesystem publication, not
   making a Git commit.
5. Apply verified cleanup within artifacts after checking resolved paths and active
   writers. Preserve user assets, unique accepted cases and unrelated files. Resume
   an interrupted journal rather than creating another complete migration copy.

### Testing and validation

First exercise one representative replacement and an interruption/recovery case
using small owned fixtures. Prove corrupt/truncated media and stale deletion hashes
block retirement. Then apply the bounded production inventory. Finish with before/
after bytes by class, net reclaimed bytes, shared additions, temporary peak or
explicitly unavailable, zero owned scratch/leases, and the full audit from task 1.
Do not run separate duplicate global audits for each subtask.

## 3. Keep instructions available and checkpoints consistent

The current documentation patch updates AGENTS.md and stages/handoffs/RESUME-05.6b.md and adds
narrow Markdown exceptions to .gitignore for AGENTS.md, docs/ and to do/.
Verify git check-ignore -v and git status --untracked-files=all for these paths.
Check that source media, artifacts, local models and unrelated Markdown remain
under their intended ignore rules. Do not force-add everything, stage, or commit.

At future closure, update the current checkpoint, stage index and latest handoff
together. Preserve historical receipts. List required untracked documentation for
the user's next commit; never describe it as committed until Git confirms it.

## 4. Future animation checks — apply only when that stage is assigned

Use section 7 of docs/validation-efficiency-policy.md as the mandatory rule.
05.6c verifies finite authored routes and solved-exit continuation. Stage 06 checks
generic recipe scheduling and ownership; Stage 07 checks composed native playback.
Do not build the generic composer in maintenance or secretly inside 05.6c.

For each supported route, record supported entries and use at least two distinct
valid states where permitted. Include transformed/non-neutral entry, actual exit
fed into the next operation, fixed-world contacts, clearance and an unrelated
head/hand intention. Test rejection and rollback for incompatible continuation.
Do not reset to a neutral fixture to make a test pass. Use both required rigs and
the existing tolerances. Review the resulting full motion, not endpoints alone.
State restrictions: horizontal surfaces and geometric balance do not establish
arbitrary-object support or physically stable dynamic motion.

## 5. Delivery and stop boundary

Write one concise maintenance receipt under to do/stages/receipts/ containing
changed files, actual commands, executed/reused/not-run checks, measured audit
comparison, corruption/race test results, reclaimed bytes and remaining capacity.
Record deferred README work only if relevant. Document any unachieved target.
Leave changes unstaged and do not start 05.6c.

For long jobs launch tools/evidence_job.py once in a persistent tool session.
Keep logs local. After the permitted bounded wait, hand back the session/report
location when independent work is exhausted. Resume on user input or supported
completion notification. No repeated status calls, log tails or directory scans.
An actual needs_review result requires inspection; no fabricated review records.
