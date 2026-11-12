# Stage 09 — Retrieve the right movement capabilities

Status: planned. Dependencies: [08](08-migrate-foundations.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Find a small useful capability set for a prompt without sending the entire catalog or restricting requests to exact action names.

**Permitted changes:** New planning/retrieval.py, compact registry descriptions and retrieval tests; no new model/provider.

## Execution

1. Index movement descriptions, body families, semantic tags, entry states and required capabilities. Start with deterministic metadata retrieval; include support/transition helpers needed by selected movements.
2. Return at most 12 detailed entries plus compact family summaries initially. Include relevant low-level joint/endpoint alternatives and preserve the original prompt and edit context.
3. Represent a miss explicitly. Provide one bounded broad-family expansion path, rather than mapping an unfamiliar metaphor automatically to the nearest whole-body action.
4. Filter unavailable rig features and distinguish reviewed versus experimental parameter envelopes. Optional fingers must not hide an otherwise usable arm movement.
5. Create a compact current-recipe summary retaining IDs, timing relations, explicit locks, root path and contacts; do not serialize expanded frame data into the planner context.

## Required outputs and handoff

Use [the API](contracts/01-library-api.md) and [coverage rules](movement-coverage.md). Deliver prompt/context-to-capability fixtures, mandatory helper expectations and explicit misses. Eligibility depends on rig, entry state AND reviewed parameter envelope. Record candidate-budget and expansion behavior. Include a miss that must not silently select an unrelated familiar action.

## Testing

- Create tests/test_movement_retrieval.py using varied descriptions/paraphrases for knees, wrists, palm orientation, compound gait/gesture and airborne swimming.
- Test a deliberately unknown metaphor, missing optional anatomy, non-neutral starting state and an edit to a specific instance. Verify relevant helpers survive filtering.
- Measure candidate count/context size against an expanded test catalog and confirm deterministic ordering.

## Validation / completion gate

Retrieval exposes usable primitives and support helpers for each supported test intent within the configured size bound. A miss remains a miss with a widening path; it is never silently treated as a successful different action.

Write the stage-09 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No new heavyweight embedding service, paid provider, fixed list of accepted user intents or downloading movement assets. Metadata matching is retrieval, not proof that the full prompt was understood.

