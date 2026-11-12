# Stage 17 — Measure and optimize the complete pipeline

Status: planned. Dependencies: [15](15-scene-builder.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Reduce prompt-to-preview latency and UI stalls using measurements of the library-based pipeline. Preserve motion and semantic quality.

**Permitted changes:** Benchmark tooling, profiled hot paths in retrieval/compiler/rig/geometry/keyframing and cache contracts; focused performance regression checks.

## Execution

1. Record model startup, prompt processing/generation, retrieval, composition, rig sampling, geometry extraction, key insertion, review/repair and playback separately. Record cold/warm runs, hardware, avatar size, motion length and retry/cache counts.
2. Use a fixed routine/compound/aerial/object/edit suite and compare equivalent outputs against stage 01/current migration baselines. Report median and slow cases, not only a best run.
3. Optimize demonstrated costs: catalog/recipe summaries, schedule preparation, redundant dependency updates, repeated geometry work, unchanged channel keys or bulk key insertion. Reuse existing caches before adding another.
4. Cache recipes separately from rig-specific bakes. Keys include rig/profile, entry state, surfaces, parameters, timing, library/compiler version and quality mode. Add cache invalidation tests.
5. Preserve per-frame yielding and measure worst-frame/preview frame time. Implement partial edit rebuild only if dependency boundaries, downstream state and blend margins can be verified.

## Required outputs and handoff

Report phase and worst-frame/UI timings with actual rig, recipe/profile/library versions and quality policy. Compare equivalent outputs including [object collision](contracts/04-object-contact-collision.md). Include cache invalidation fixtures, cold/warm sample counts and measured quality equivalence. Performance results cannot substitute for missing movement coverage.

## Testing

- Run at least five warm samples per routine benchmark and one documented cold-model sample; keep original logs and units. Repeat only after a measured code change.
- Compare solved trajectories, contacts, semantic goals and visual results before/after each optimization. Test invalidation for avatar, state, surface and parameter changes.
- Measure cancellation latency, allocation growth across repeated requests and actual playback responsiveness.

## Validation / completion gate

Report measurable improvements or a justified retained baseline with remaining bottlenecks. Equivalent motions preserve tolerances and normal review. Aim for the user's 60–120-second ordinary-prompt window, but report real measured results and unresolved misses.

Write the stage-17 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No quality-threshold loosening, silently reduced motion/detail, unbounded caches or skipped final collision review to improve timings. No claim that a fast preset alone proves fast arbitrary interpretation.

