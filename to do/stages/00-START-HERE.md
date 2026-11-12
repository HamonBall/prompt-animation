# Numbered execution stages — start here

Stages 01–04, 05.1a, 05.1b, 05.2, 05.3a, optional 05.3b, 05.4, 05.5, 05.6a and 05.6b are complete. The [05.6b handoff](handoffs/RESUME-05.6b.md) records the current checkpoint. See the [05.6a receipt](receipts/05.6a.md) for root travel, turns, and airborne motion. See the [05.5 receipt](receipts/05.5.md) for ankle, foot and toe validation and storage. See the [05.4 receipt](receipts/05.4.md) for the hip, thigh and knee validation and storage results, and the [05.3b receipt](receipts/05.3b.md) for the optional finger work. See [Stage 01's receipt](receipts/01.md) for cleanup and the preserved pre-existing test issue, [Stage 02's receipt](receipts/02.md) for the data contracts, [Stage 03's receipt](receipts/03.md) for calibration, [Stage 04's receipt](receipts/04.md) for the execution bridge, and [Stage 05.1a's receipt](receipts/05.1a.md) for the five head/neck movements and two-rig previews.
Prepared: 2026-10-14.

Storage policy added 2026-10-26: every stage must read and follow [the project artifact-retention policy](../../docs/artifact-retention-policy.md). Complete [the storage-v2 maintenance assignment](../storage-reduction-and-retention-plan.md) before generating another large stage-05 evidence set. This maintenance requirement does not renumber movement stages or claim their implementation is complete.

## How to assign one stage to Sol

README freeze (2026-10-30): follow `AGENTS.md` and leave `README.md` unchanged until the user explicitly requests its update or lifts the freeze. Older stage/maintenance instructions to update README are deferred, not completion blockers. Keep contracts, policies and stage receipts current, noting any deferred README work in the receipt. Preserve existing README edits.

Give the implementer one stage file and this index. Use:

> Implement only stage [ID] in [its numbered document]. Read 00-START-HERE.md and the completed prerequisite receipts first. Follow that stage's Plan, Execution, Testing, Validation and Limits sections. Complete the permitted work and checks, write the stage receipt, then stop at the stage boundary. Report changed files, actual test results, artifacts and unresolved limits. Do not begin the next stage.

The stage document and shared rules below are the execution specification. The [extensive plan](../movement-library-implementation-plan.md) supplies design context; its old phase sketch is superseded by this sequence. Prefer current code and actual receipts over historical claims that a capability already exists.

Read the current source before changing it. Do not blindly reproduce a module that an earlier stage already supplied. If a named path changed, follow the recorded replacement. If a prerequisite is incomplete, identify the missing capability precisely and leave dependent work pending; do not silently implement several unassigned stages. Complete independent work within the assigned scope where possible.

Optional stages 05.3b (finger detail), 16 (recorded clips) and 19 (context integration) can be selected separately. Missing optional assets/providers must not block the procedural-body pipeline. They must remain marked pending until their own evidence exists.

## Execution order and files

Read top to bottom. Dependencies, not filename proximity, determine readiness. Each row is one independently assignable work package.

| Stage | Document | Requires | Status |
| --- | --- | --- | --- |
| 01 | [Audit and remove obsolete implementation paths](01-cleanup.md) | None | [Complete](receipts/01.md) |
| 02 | [Define the movement catalog and data contracts](02-library-contracts.md) | 01 | [Complete](receipts/02.md) |
| 03 | [Map and calibrate anatomical joints](03-rig-calibration.md) | 02 | [Complete](receipts/03.md) |
| 04 | [Execute and inspect one library movement](04-primitive-execution.md) | 03 | [Complete](receipts/04.md) |
| 05.1a | [Library 5.1 — head and neck](05.1a-head-neck.md) | 04 | [Complete](receipts/05.1a.md) |
| 05.1b | [Library 5.1 — spine and pelvis](05.1b-spine-pelvis.md) | 05.1a | [Complete](receipts/05.1b.md) |
| 05.2 | [Library 5.2 — shoulders and upper arms](05.2-shoulders-arms.md) | 05.1b | [Complete](receipts/05.2.md) |
| 05.3a | [Library 5.3 — elbows, forearms, wrists and hand targets](05.3a-elbows-wrists-hands.md) | 05.2 | [Complete](receipts/05.3a.md) |
| 05.3b (optional) | [Library 5.3 — optional hand gestures and finger detail](05.3b-fingers.md) | 05.3a | [Complete](receipts/05.3b.md) |
| 05.4 | [Library 5.4 — hips, thighs and knees](05.4-hips-knees.md) | 05.3a | [Complete](receipts/05.4.md) |
| 05.5 | [Library 5.5 — ankles, feet and toes](05.5-ankles-feet-toes.md) | 05.4 | [Complete](receipts/05.5.md) |
| 05.6a | [Library 5.6 — root travel, turning and airborne motion](05.6a-root-travel-flight.md) | 05.5 | [Complete](receipts/05.6a.md) |
| 05.6b | [Library 5.6 — support contacts and transfers](05.6b-support-transfers.md) | 05.6a | [Complete](receipts/05.6b.md) |
| 05.6c | [Library 5.6 — coordinated body movements](05.6c-coordinated-body-moves.md) | 05.6b | Complete ([receipt](receipts/05.6c.md)) |
| 05.7a | [Library 5.7 — timing, repetition and coordination patterns](05.7a-timing-patterns.md) | 05.6c | Planned |
| 05.7b | [Library 5.7 — bounded motion style](05.7b-style.md) | 05.7a | Planned |
| 06 | [Build action recipes and timeline stages](06-recipe-stage-builder.md) | 05.7b | Planned |
| 07 | [Compile and execute composed animation](07-animation-compiler.md) | 06 | Planned |
| 08 | [Migrate existing animations to library recipes](08-migrate-foundations.md) | 07 | Planned |
| 09 | [Retrieve the right movement capabilities](09-capability-retrieval.md) | 08 | Planned |
| 10 | [Interpret open-ended prompts into movement recipes](10-ai-planner.md) | 09 | Planned |
| 11 | [Preserve intent through narrow follow-up edits](11-precise-corrections.md) | 10 | Planned |
| 12 | [Define requested objects and semantic surfaces](12-object-contracts.md) | 11 | Planned |
| 13 | [Construct simple objects transactionally](13-object-builder.md) | 12 | Planned |
| 13.1 | [Review collisions against complete objects](13.1-object-collision.md) | 13 | Planned |
| 14 | [Connect movement goals to objects](14-object-interaction.md) | 13.1 | Planned |
| 15 | [Assemble requested preview scenes](15-scene-builder.md) | 14 | Planned |
| 16 (optional) | [Add selected existing clips as library movements](16-clip-library.md) | 15 | Planned |
| 17 | [Measure and optimize the complete pipeline](17-performance.md) | 15 | Planned |
| 18 | [Validate the staged product and document its capabilities](18-acceptance.md) | 17 | Planned |
| 19 (optional) | [Optional — bounded background reference context](19-context-cache.md) | 18 | Planned |

The movement catalog follows sections 5.1–5.7 of the extensive plan. Head/neck versus spine/pelvis, hand mechanics versus fingers, and root travel versus support versus coordinated body movement are split further to keep each assignment bounded.

The single-fragment execution bridge in 04 includes the shared typed-track adapter needed to verify the moveset. The timeline-stage composer (06) and multi-instance compiler (07) reuse it before AI integration. Object specifications (12), construction (13), complete-object collision review (13.1), interaction (14) and scene assembly (15) are separate assignments.

## Required reference contracts and handoffs

Read the relevant linked specification before implementing its stage:

| Reference | Owner and consumers |
| --- | --- |
| [Library API and serialized data](contracts/01-library-api.md) | 02 implements the initial contract; 04, 06–11 and 16 consume it |
| [Rig units, frames and anatomy](contracts/02-rig-semantics.md) | 03 publishes actual mappings/ranges; all movement stages consume them |
| [Bridge/composer/compiler boundaries](contracts/03-execution-boundaries.md) | 04 supplies one fragment path; 05 adds content; 06 resolves recipes; 07 compiles them |
| [Object support and collision](contracts/04-object-contact-collision.md) | 12 defines data; 13 builds it; 13.1 checks collisions; 14–15 integrate |
| [Per-ID coverage ledger](movement-coverage.md) | Every 05.* stage and 08 records individual movement results; 18 audits coverage |

These references are proposed implementation requirements. Stages 02/03/12 must publish exact implemented contracts and fixtures at the paths specified in their documents; later stages read those artifacts and receipts. No empty contract file or prose-only API promise completes a handoff. Approved versioned migration notes take precedence over outdated examples, but do not weaken product requirements or validation silently.

On starting a stage, verify its predecessor's source revision, contracts, fixture commands and capability coverage. If current code contradicts a receipt, record the actual discrepancy and resolve only the assigned scope. Do not rebuild the predecessor from memory or guess missing semantics.

## Terms that must remain distinct

- Movement preset: a parameterized joint/limb/body motion with entry conditions, owned chains and tested execution.
- Motion pattern: repetition, alternation or phase coordination over movements.
- Recipe: selected movement instances and their temporal relationships, plus user goals and constraints.
- Timeline/action stage builder: the composer that orders/overlaps movements (06).
- Animation constructor/compiler: the system that expands and executes the recipe as measured motion (07).
- Object builder: procedural creation of requested props and their surfaces (13).
- Scene/physical-stage builder: arrangement of requested props/background/camera/light (15).

Library IDs are a bounded executable vocabulary; user language remains open-ended. Metaphors must be decomposed into motion qualities and supported movements. Unknown wording must not silently become a familiar unrelated animation. “Fly like the fish swims” retains airborne travel; it does not merely wave arms while standing.

## Shared implementation limits

These apply to every numbered document:

1. Implement only its scope and necessary tests/adapters. No new service, dependency, paid model, model download, export feature or UI redesign unless that stage explicitly calls for it.
2. Preserve existing avatar topology, rest skeleton, materials and user-owned scene objects. No body scanning/reconstruction. Optional bones are detected, never added to simulate capability.
3. Keep library/planning data independent of bpy. Use the existing Blender executor and main-thread scene mutation path; retain progress, cancellation, stale-result checks and rollback.
4. Never execute model output as code. Validate IDs, types, units, frames, finite values, revision and capabilities before mutation.
5. Preserve requested goals and unrelated motion during corrections. Supporting changes must be bounded and material differences explained. Measured results, not desired targets, establish success.
6. Retain working behavior while replacing its implementation. Delete obsolete code only with dependency evidence and migrated useful tests; never delete tests merely to make a failure disappear.
7. No hardcoded solver branch for an acceptance sentence or animal/action name. Reusable semantic mappings and general library recipes are allowed.
8. Do not change shared contracts casually. Required narrow extensions must be versioned, update all affected consumers and add compatibility tests in the same stage. A change exceeding the assigned stage becomes an explicit follow-up.
9. Stage-specific exclusions are real boundaries. An unsupported future capability stays unavailable/experimental rather than being implemented by an inaccurate shortcut.
10. Preserve original data, runtime/model binaries, configuration and accepted evidence. Generated-artifact migration and obsolete-history retirement follow the project retention policy; user assets are never cleanup candidates.

## Initial resource bounds

These are explicit starting engineering limits, not measured speed guarantees.

- Animation: at most 60 seconds at the current 30 fps; at most 1,801 inclusive samples.
- New recipe: at most 128 movement instances, 256 compiled scalar/vector tracks and 256 contact activation intervals; reject over-budget expansion before allocation. A vector track's dimension is fixed by its registered schema.
- Keep legacy ActionPlan's 12-stage limit. Stage 04 adds the separately bounded typed single-fragment path; 07 compiles general recipes into that same representation. Never expand sampled frames into thousands of fake legacy stages.
- Root/object positions stay within 20 m of scene origin; applicable generated-object dimensions are positive and at most 10 m per axis. A plane has positive width/length and omits thickness; zero thickness is not treated as a volumetric dimension.
- Generated scene: at most 64 mesh objects, 10,000 triangles after assembly expansion, 16 generated materials, and three simple lights. Avatar geometry/materials are excluded from this generated-prop budget. Count the entire generated preview, including existing props, when validating an addition.
- Retrieval starts with at most 12 detailed capability entries plus compact family summaries. Keep the existing 2,000-character prompt limit, 22,000-character model-message guard, 8,192-token runtime context and current 1,800-token action output limit as baselines. Characters are not tokens: check actual prompt+schema+output headroom. Any measured necessary adjustment must remain bounded and documented.
- Model planning: one routine call, at most one explicit targeted retry; no autonomous indefinite retry/repair loop.
- Use per-definition/profile parameter ranges, not one universal anatomical range. Stage 03 must document those ranges before movement authors rely on them.

## Testing and numeric validation shared by movement stages

All stages follow [the project-wide validation efficiency policy](../../docs/validation-efficiency-policy.md). Use focused checks while developing, complete numeric/functional coverage on stable components, and required final visual/integration review. Reuse only current verified evidence; keep all existing coverage and numeric tolerances. The policy also applies to non-movement stages and maintenance.

[The coverage ledger](movement-coverage.md) is mandatory: complete each required ID and baseline variant, not only one representative animation per stage. An experimental or unimplemented required baseline keeps its owning stage partial. Optional anatomy is reviewed only for rigs that actually support it, with missing-capability tests elsewhere.

Every advertised reviewed movement needs: declared parameter-range tests, both sides where applicable, at least one non-neutral/turned entry state, missing-capability failure, an unrelated-target preservation check, numeric solved-motion measurements, and inspection over its full motion. Default tests use the procedural avatar and a differently proportioned imported rig. Missing optional bones require an explicit negative capability case on that rig and positive evidence on a capable rig; never claim the missing anatomy was animated. If a required rig/runtime is unavailable, record the gap and do not claim its gate passed.

Maintain current normal-review baselines: 3 mm maximum floor/surface penetration, 25 mm contact error, 360 degrees/second joint speed and 3,000 degrees/second-squared angular acceleration. Do not loosen them to make new moves pass.

Initial additional targets, measured in the declared frames:

- Requested joint/orientation residual: at most 3 degrees; endpoint residual: at most 10 mm.
- Unrelated measured-joint change during a narrow edit: at most 0.5 degree; unrelated endpoint change: at most 2 mm at matched times. Unrelated recipe fields must remain exactly equal.
- Loop seam after removing declared per-cycle root displacement: pose residual at most 3 degrees, endpoint residual at most 10 mm and angular-velocity difference at most 10 degrees/second. Contact identity/phase must agree; root transform accumulation must match the declaration.
- No invalid numbers, chain flips, undeclared support changes or discontinuous resets.
- Deliberate style pauses/reversals are permitted, but still obey the configured speed/acceleration and contact checks.

These new tolerances are initial acceptance targets, not claims about current capability. If calibration or an intended style cannot meet one, report the measured cause and leave that case incomplete/experimental; do not silently mark it reviewed. A physically valid preview can still fail semantic/visual validation.

## Commands and evidence

Long-running evidence must use [quiet evidence jobs](../../docs/contracts/evidence-jobs.md). Wrap the assigned stage's strict validators and single-case producers in a bounded plan; the local runner handles subprocess waits, logs, deadlines and classified recovery. Do not repeatedly poll Blender or read unchanged logs through the agent. `needs_review` ends the worker's waiting and supplies an index for actual inspection. A completed automated job does not itself complete a stage. Follow the `AGENTS.md` handoff rule when no host completion notification is available.

Choose commands using the validation policy rather than running every example after every edit. Before an expensive matrix/render batch, record affected scope, reusable evidence, estimated cases/views/frames and measured or estimated phase cost. Preserve proven process isolation and measured concurrency. Passing final checks are not repeated without a change, failure or unresolved concern.

Stage 01 records the actual local runtimes/commands. The current documented baseline is Blender 5.1. From C:/work11, after verifying the executable paths:

~~~powershell
$stagePython = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
$stageBlender = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
& $stagePython -m unittest discover -s tests -p 'test_*.py' -v
& $stageBlender --background --factory-startup --python-exit-code 1 --python tests/blender_presets.py -- demo jump walk run wave lie
~~~

Use focused unittest discovery patterns and the actual stage-specific Blender script for each assignment. For body-family documents 05.*, use `tests/test_movement_<slug>.py` and `tests/blender_movement_<slug>.py`, replacing the document filename's words after the stage number with underscores; for example, tests/test_movement_head_neck.py. Test filenames are files to create or adapt during implementation, not claims that they already exist. Run affected existing checks as well; use full unit discovery at cleanup, shared-contract/compiler migration and acceptance boundaries. A background render does not prove the interactive cancellation/playback UI works; test those flows in the appropriate UI harness.

Keep logs, numeric samples and videos/contact sheets under `artifacts/stages/<ID>/`. View the resulting evidence; creating a file is not visual review. Record tested rig, model, library/compiler versions and cold/warm state where relevant.

Storage is a completion gate for every stage. Reuse immutable avatar assets across cases and stages; preserve individual baked motions and required evidence through the supported manifest/loader. Do not save a complete packed avatar scene per variant. Follow the retention policy's stage/global/temporary budgets, preflight large runs, retire verified obsolete outputs and clean owned scratch. Required full-motion coverage remains unchanged. Until storage-v2 is implemented, avoid large runs that reproduce the legacy storage growth.

## Required completion receipt

Create `to do/stages/receipts/<ID>.md` only when implementing the assigned stage. It must contain:

- Status: complete, partial, or unable to validate, and the date/source revision or working-tree state.
- Implemented IDs/interfaces, supported parameter envelopes and changed/removed paths. Movement stages attach a separate evidence section for every owned ledger ID.
- Actual commands, exit results and relevant measured values; distinguish existing failures from new ones.
- Validation efficiency: checks executed/reused/not run, affected scope and reuse justification, phase timings or labelled estimates, case/view/frame counts, worker settings and retry outcomes. Record actual savings when changing the validation pipeline; retain complete required coverage.
- Artifact paths and full-motion visual-review observations.
- Each validation criterion marked passed, failed or not run, with evidence.
- Required contract/fixture paths, exact versioned API/schema changes and downstream consumer updates.
- Storage before/after by artifact class, shared-asset additions, peak temporary bytes, retired outputs, retained failures and actual budget-check results. Count maintenance and exports; do not hide growth outside the stage directory.
- Remaining limitations, unavailable optional capabilities and migration notes for the next stage.

Mark a stage complete only when its required gates pass, then update its document header and index row. For partial or unvalidated work, record that status in the receipt and leave the completion gate open. Do not fabricate test output, substitute a mocked AI test for a required real-model check, or treat registry metadata as implemented motion. Stop after the assigned stage's receipt; the user selects the next work package.

