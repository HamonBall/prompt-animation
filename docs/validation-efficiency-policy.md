# Project-wide validation efficiency policy

Effective 2026-10-30. Applies to every stage, feature, fix, refactor and maintenance task: movement libraries, composition, AI interpretation, objects, scenes, UI, exports and storage. Follow this policy together with [artifact retention](artifact-retention-policy.md) and the assigned task's completion gates.

These are execution rules for agents and contributors. Existing runners already provide some reuse and isolation; this document does not claim a new universal runner or dependency cache has been implemented. Reuse supported tools first. Add a narrow selector, timing record or cache test only when needed for the assigned work; do not turn a feature task into an unrelated validation-framework rewrite.

Update 2026-11-04: the universal process supervisor and pipeline builder are now implemented; see [quiet evidence jobs](contracts/evidence-jobs.md). They delegate cache validity to existing producers/validators. For long pipelines launch one bounded job in a persistent tool session, consume its terminal summary, and intervene only for failure or actual review. Do not burn agent turns on repeated progress queries. Use completion events if available; otherwise hand back control with the session/report location until the user resumes. Keep the managed session alive; there is no automatic Codex wake-up guarantee.

## 1. Select checks from the actual change

Before expensive work, identify changed behavior, shared dependencies, affected consumers, required checks and reusable evidence. Keep this in a short validation plan or the existing receipt, not a second large report tree.

| Work state | Required approach |
| --- | --- |
| Local edit | Run relevant unit/contract tests and affected cases. Documentation-only edits need link/consistency checks, not Blender runs. |
| Developing behavior | Use a small, demanding smoke set with a normal case, boundary, invalid/conflicting input and relevant preservation/rollback case. Exercise required rig/platform differences early. |
| Stable component or family | Run its complete required numeric/functional matrix and affected integration regressions. |
| Stage/task completion | Establish current coverage of all required cases, inspect required full-motion/UI evidence, run final required regressions and audit artifacts/storage. Valid reusable results count as reused, not newly executed. |

Smoke tests never substitute for the final matrix. Preserve test assertions, parameter/rig coverage, sampling rates, tolerances, required model/UI checks and visual review. Do not grow a Cartesian product of every parameter unnecessarily: map cases to distinct required behaviors and failures, while retaining every mandated boundary/baseline variant.

## 2. Gate expensive evidence on correctness

Before launching a changed batch driver or revalidator, run a non-Blender routing
check for every selected case ID and registry/group, command argument shape and
confined output path. Exercise each newly added dispatch branch, including invalid
groups and unknown IDs. Then run one representative native case from each changed
branch before the remaining batch. Unit tests of animation mechanics alone do not
validate job orchestration. After a deterministic harness failure, retain successful
evidence and build a targeted recovery plan with identity checks; do not blindly
repeat earlier successful bakes, regressions or renders.

Run cheap schema/unit checks before native execution, and numeric/functional checks before bulk rendering or other expensive evidence production. Fix failing required mechanics before mass-rendering the affected family. A small diagnostic render is allowed when it helps locate the failure; record it as diagnostic, not accepted evidence.

A stable independent group may proceed while another group is being repaired if it shares no changed dependency. Generate final visuals from validated saved motion; do not ask the AI or rebuild the movement merely to render it. Record the inspected motion/media identity.

Keep every view required by the task. Add detail views only for a stated visibility problem or validation question. Full-motion review means inspecting the motion, not repeatedly rendering unchanged frames. Reuse current validated visual evidence with its provenance.

## 3. Reuse evidence with correct invalidation

Use existing manifest/hash checks. A directory, filename, timestamp or old success receipt alone is not a cache hit. Relevant identity includes inputs/fixtures, asset and rig/profile versions, behavior-affecting source dependencies, runtime/configuration, validator version and output integrity. Model work also records model/runtime, prompt/schema and generation settings; cache reuse cannot replace a required fresh live-model trial.

Distinguish execution, validation and presentation dependencies:

- Behavior/solver changes invalidate affected execution and downstream evidence. Shared solver, frame, contact or compiler changes include affected consumers across families.
- Validator-only changes require revalidation. Existing raw measurements can be reused only if sufficient and trustworthy for the new check; otherwise execute again.
- Camera/render/encoding changes invalidate affected visual evidence, without regenerating unchanged accepted motion.
- Documentation-only changes normally invalidate neither numeric nor visual evidence.

Use dependency declarations only when verified complete. With uncertainty, conservatively rerun affected consumers. Never omit a shared dependency, edit recorded producer hashes, or introduce a blanket stale-source override to manufacture cache hits. Preserve existing narrow compatibility migrations and their negative tests.

If implementing finer caching, test unchanged reuse, relevant dependency/input changes, unrelated changes, missing/corrupt output and changed validation requirements. Reuse immutable shared-asset verification within a bounded read-only run; invalidate on mutation and retain final integrity checks rather than hashing the same asset for every frame.

## 4. Bound native workers and retries

Keep the proven process-isolation strategy. Previous Blender allocation/driver failures mean a long-lived worker is not automatically an optimization. Compare a small candidate batch against fresh-process results, checking state leakage, memory growth, cancellation and exit status before changing isolation.

Reuse an existing measured concurrency limit. For a new workload, start with one worker, measure it, then trial two within memory, CPU/GPU and temporary-storage limits. Do not multiply shards and internal render threads without checking combined load. Independent cases need separate leases and outputs.

Retry a failed unchanged command only to test a specific transient-failure hypothesis, retaining both results. Repeated failure requires diagnosis rather than another blind full-suite run. A native crash after output creation is still a failed process until explicit recovery/revalidation establishes usable evidence. Do not alter tests or suppress exit failures to improve throughput.

## 5. Measure costs before optimizing

For the first expensive batch of a task, use existing timings or a small representative pilot. Estimate case/view/frame counts, runtime, concurrency, retained growth and temporary peak before launching the full batch. Distinguish measured timings from estimates; stop expanding a batch whose observed costs violate the storage policy.

Record elapsed time for applicable phases: startup/asset load, planning/generation, execution/measurement, rendering, encoding/pixel verification and audit. Report cache hits/misses and rerun reasons. Measure the largest contributor first; do not promise a speedup without comparison on equivalent cases and hardware settings.

The current lightweight renderer and lossless media already reduce cost. Potential changes such as faster temporary PNG compression, direct encoding or small native-worker batches are benchmarks to evaluate, not mandatory implementations. Adopt them only if measured faster with unchanged decoded pixels/frame order/timing, correct failure recovery and bounded temporary storage. Do not repeatedly benchmark the whole suite or install new dependencies outside the assignment.

## 6. Finish without redundant reruns

At completion, run the task's mandated checks and affected regressions. Run full unit discovery at the existing shared-contract/compiler, cleanup and acceptance boundaries, or when impact warrants it. A local change does not automatically require every historical Blender matrix and visual set.

After a passing final run, repeat only checks affected by later changes, new failures or unresolved concerns. Preserve independent audits and no-growth checks where required, but do not regenerate accepted media to perform a read-only audit.

Every completion receipt reports executed versus reused versus not-run checks, affected scope and reuse justification, phase timings/estimates, cases/views/frames, worker settings, retry/failure outcomes and storage accounting. Missing measurement is labelled unavailable, never guessed. A successful optimization requires equal required coverage and correctness with measured time/resource improvement; otherwise retain the proven path. Do not mark a stage complete from smoke checks alone.

## 7. Transition coverage and truthful scope

For coordinated movement and composition work, map each declared route to its supported entry states, acquired/released contacts and measured exit. Test at least two distinct valid entry states per route where the contract permits them, including a non-neutral or translated/rotated state. A route with only one supported entry must state that restriction and reject incompatible entries. Do not silently reset to a prepared fixture.

Carry the actual solved exit into the next operation. Check pose/root continuity, contact overlap and release, surface clearance, preservation of an unrelated head or hand intention, and rollback on an incompatible continuation. Use existing stage tolerances and both required rigs. Add focused full-motion review for these transitions; do not multiply every parameter into an exhaustive cross-product.

Stage 05.6c uses finite authored routes through the existing fragment bridge. Generic scheduling belongs to 06 and composed native execution to 07. These requirements do not authorize implementing those later stages early. Geometric pelvis-over-foot support must not be labelled dynamic balance, and horizontal-surface coverage must not be labelled general object interaction.

## 8. Audit efficiency

Optimize measured bottlenecks using the bounded assignment in `to do/validation-storage-handoff-maintenance.md`. Keep the strict audit as a reference. Deduplicating immutable shared-asset reads inside one protected audit must preserve every bundle, manifest, path, content and budget check. Never substitute file size/mtime or a historical receipt for content integrity. A cross-run cache is a separate design requiring explicit invalidation tests; it is not part of that maintenance assignment.
