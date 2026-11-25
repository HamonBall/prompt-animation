# GPT-6.2 Sol plan for a scan customer's first animation

Integrated into the numbered stages on 2026-11-24 for the local Blender avatar application in `C:\work11`. This document supplies product context and ownership. Stage 08 is active. Later stages require explicit assignment.

## Product and starting state

The owner clarified the commercial goal. The application promotes the existing service that scans people and delivers rigged personal avatars. A customer should recognize themselves, enjoy directing a short movement, and understand who made the avatar. Someone seeing the result should be able to discover the service if the customer chooses to show it. The [product brief](../docs/avatar-animation-brief.md) supplies the interaction and local-compute constraints. Broad free-text control remains part of the vision. First prove the trip from an actual delivery to a convincing personal result.

The review examined HEAD `2fd0eff` plus uncommitted Stage 08 changes. Recover current state from [AGENTS.md](../AGENTS.md), the [context policy](../docs/context-continuity-policy.md), [current pointer](CURRENT-WORK.md), and [Stage 08 handoff](stages/handoffs/RESUME-08.md). Preserve existing edits and the README freeze. Verify which findings still apply. Read the [validation](../docs/validation-efficiency-policy.md) and [retention](../docs/artifact-retention-policy.md) policies before running checks that produce artifacts. Use the managed evidence-job contract for long native jobs.

The [interpreter](../src/avatar_app/planning/action_interpreter.py) first handles neutral and exact commands. Open-ended requests use the local model and a structured decoder. The [UI](../src/avatar_app/main.py) interprets on a worker, bakes on Blender's thread, then commits the result. Both the direct and model-selected foundation paths could still produce legacy plans at review time. The [recipe adapter](../src/avatar_app/blender/requests.py) separately accepts a measured, bound foundation. Stage 08 owns parity and migration of these paths. Its saved wave playback and two-rig visual reviews are useful precedents. Check their recorded source identities before reuse.

## Decision on C:\armature

Treat the prior service as the source of the main product asset. Its [batch pipeline](C:/armature/process_all_avatars.bat) reduces topcode-marked OBJ scans, builds and skins a custom skeleton, then partially rotates limb chains toward a reference scan. Reports record 15 successful reductions, 15 skeletons with 19 bones and zero unweighted vertices, and 210 per-bone pose-match rows. These assets supply real variation in proportions and visible deformation cases. The [prior status review](C:/armature/statusReview.docx) identifies armpit weighting as unresolved.

Establish what customers receive today. The inspected batch writes rigged Blender scenes and static OBJs. The [current importer](../src/avatar_app/blender/avatar.py) expects one Mixamo-style armature in an FBX, including hips and head bones absent from the [old rig definition](C:/armature/scripts/skeleton.py). The [reducer](C:/armature/scripts/reduce_obj_faces.py) also disables UV export on its modern OBJ path. Determine whether the studio uses those outputs or a separate textured and rigged delivery. A format conversion alone cannot supply missing anatomy.

The [Stage 01 receipt](stages/receipts/01.md) records a 61-frame Mixamo dance retargeted onto the supplied Andrejs FBX. The [rig-profile harness](../tests/blender_rig_profile.py) also uses Andrejs as a missing-palm-reference case. Verify its provenance before treating it as representative. Choose motions supported by the actual delivery and preserve original meshes, weights, and authored pose.

## Delivery across the existing stages

The numbered specifications own implementation and checks. Use the [active handoff](stages/handoffs/RESUME-08.md) for the next executable task. Stages retain their existing dependencies and assignment boundaries.

| Stage | Responsibility |
| --- | --- |
| [08](stages/08-migrate-foundations.md) | Studio delivery and first playback |
| [09](stages/09-capability-retrieval.md) | Options supported by the customer rig |
| [10](stages/10-ai-planner.md) | Customer wording and offline fallback |
| [11](stages/11-precise-corrections.md) | The customer's first intentional change |
| [14](stages/14-object-interaction.md) | Chair recovery through the visible UI |
| [16](stages/16-clip-library.md) | Optional studio demonstration clip |
| [17](stages/17-performance.md) | Time to first playback and cancel-to-retry |
| [18](stages/18-acceptance.md) | Customer and prospective-customer observations |

Stages 12, 13 and 13.1 already own chair resolution, construction and collision respectively. Stage 14 brings these together through the visible workflow. Stage 15 already owns scene presentation. Keep the neutral preview focused on the person. Stage 19 remains an optional context-cache extension. Basic missing-reference recovery belongs in Stage 10 so the core workflow can pass acceptance independently. Stage 16 also remains optional.

Record ordinary workflow probes as development evidence, including an exact action, a paraphrase, a correction, a chair request and an unsupported request. Reserve the Stage 18 held-out set for acceptance. Record customer observations separately from developer rehearsals.

## Evidence and handoff

The original review executed 37 passing tests from `test_presets`, `test_motionfix` and `test_foundation_recipes`. The wording and intent probes exercised planner code. The deliberately wrong model selection says nothing about its frequency during live inference. Prior stage receipts document native evidence at their recorded revisions. No new live-model trial, playback inspection or user study was performed for this plan.

Report baseline and post-change results by prompt and rig. Keep four judgments distinct: requested meaning, successful bake, visual quality, and time to a usable result. For corrections, list what should change and what should remain observable in the clip. An evaluator should be able to see a failure even when the application says “Ready to play.” Record actual fresh, reused, failed and pending checks with paths and evidence identities. Update the assigned handoff when implementing. Any unfinished route parity or stage acceptance remains with its owning stage.
