# Stage 16 — Add selected existing clips as library movements

Status: planned (optional extension). Dependencies: [15](15-scene-builder.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Reuse suitable explicitly available recorded clips or segments as additional library resources while retaining procedural editability and provenance.

**Permitted changes:** Existing clips.py/blender/clips.py, clip-backed registry entry adapter, local catalog metadata and tests.

## Execution

1. Extend the explicit local clip metadata with reviewed entry/exit states, trimmed interval, phase landmarks, contact intervals, affected chains and permitted adaptation parameters.
2. Register a clip-backed entry only when its actual motion and source are inspected. Preserve source/provenance and distribution information; local availability does not imply permission to bundle.
3. Retarget through the existing Mixamo path, then adapt timing/placement and declared free channels through the same recipe/compiler/constraint interfaces.
4. Support blending from a procedural movement into/out of a clip and a compatible head/hand overlay. A baked clip may lock channels; expose those limits rather than promising arbitrary edits.
5. If no suitable clip exists locally, finish the adapter/tests with an explicitly authored synthetic test fixture and mark real-content catalog expansion pending. Do not relabel unrelated dance clips to fill an action gap.

## Required outputs and handoff

Publish a clip-entry fixture with provenance, root handling, phases, contacts, locked/free channels and retargeting envelope using [the library API](contracts/01-library-api.md). Demonstrate that overlays cannot overwrite locked support channels. Separate adapter completion from real-content review; synthetic fixtures cannot count as reviewed external catalog content.

## Testing

- Run existing clip regressions plus trim/retime/transition and overlay cases on two rigs. Verify root continuity, contacts and source-instance provenance.
- Test missing file/provenance, incompatible source rig, unavailable edit channel and cancellation restoration.
- Inspect a real locally available clip if suitable and record exactly which clip was reviewed; synthetic tests are not evidence of real-content quality.

## Validation / completion gate

Clip entries use the same contracts and review path as procedural movements. Adapter validation and real-content coverage are reported separately. Unavailable content does not block the already completed procedural pipeline.

Write the stage-16 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No unrequested downloads, bundled personal FBX assets, guessed animation tags, new retargeting framework or unrestricted blending over locked contact channels. This is an optional extension; stage 17 does not require real clip assets.

