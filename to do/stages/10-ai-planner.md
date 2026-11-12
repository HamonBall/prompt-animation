# Stage 10 — Interpret open-ended prompts into movement recipes

Status: planned. Dependencies: [09](09-capability-retrieval.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Have the local AI select and parameterize multiple implemented movements, expressing meaning and temporal relationships rather than authoring raw joint choreography.

**Permitted changes:** planning/action_interpreter.py, registry-generated planner schemas, narrow local_model.py request shaping if required, planner and live-model tests.

## Execution

1. Return a versioned recipe selection with instance IDs, registry IDs/versions, validated parameters, sequence/parallel relations, explicit goals, support mode, style and clause coverage. Generate valid parameter choices from retrieved definitions.
2. Handle new motion versus correction versus append explicitly. Preserve user direction, body parts, airborne intent, repetition and scene requests. Record each explicit clause using the contract's fulfilled/approximated/unsupported statuses, with explanations where required.
3. Use low-level joint/endpoint combinations for unusual goals. Keep one model call for routine requests and allow at most one targeted retry for a schema/capability clarification; log its cause and latency.
4. Route validated recipes through the composer/compiler. Unknown IDs, malformed JSON, impossible hard constraints and resource overruns fail before scene mutation.
5. Retain exact shortcuts through the same compiled mechanics. Preserve existing streaming progress, model reuse, error reporting and previous-result behavior. Keep optional reference text untrusted.

## Required outputs and handoff

Generate schemas from [the implemented API](contracts/01-library-api.md). Save actual model input, chosen IDs, clause coverage, recipe, measured preview and phase timings. Run at least six live cases spanning knee/palm, wrist/elbow, compound action, unfamiliar metaphor, flight and narrow-correction intent decoding. Full correction application belongs to 11; here verify the proposed edit scope without inventing a second patch engine. Missing explicit goals are failures, not successful approximations without disclosure. Record every retry.

## Testing

- Create deterministic decoder/coverage tests, then run actual local-model prompts for joint intent, compound action, unusual metaphor and airborne swimming. Include paraphrases not used in prompt examples.
- Assert that 'fly like the fish swims' includes airborne root motion, and 'wrists at chest height, elbows forward' includes distinct endpoint/bend-plane goals.
- Test hallucinated IDs, missing clauses, malformed output, retrieval miss and missing optional anatomy. Record actual model input/output size, startup/inference times and retry count.

## Validation / completion gate

Supported examples produce executable recipes with every explicit clause accounted for; visually inspect actual previews. Mock-model tests alone do not complete this stage. Unknown requests yield useful approximation/conflict handling without silently replacing intent.

Write the stage-10 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

Keep current local model/runtime as baseline; no cloud dependency or phrase-specific solution handlers. Retain current input/output/context limits unless measured evidence justifies a documented bounded adjustment. Never run model-generated Python or Blender commands. Object requests may be recorded as unresolved requirements until stages 12–14.

