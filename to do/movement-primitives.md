# General prompt-to-motion through reusable movement primitives

## Objective

Change prompt interpretation so users can request **any kind of pose or motion in ordinary language** and the application translates that request into a sequence of reusable, lower-level body movements. The system must not depend on a growing list of recognized animation names such as “sit,” “lie down,” “walk,” or “dance.” A phrase such as “fly like the fish swims” should enter the same planning path as familiar requests, even if the result is an approximate human-body interpretation.

The existing movement library is the starting point for the reusable motions. Expand and organize it as a library of **composable movement primitives**, not as a catalog of one-off animations keyed to exact user phrases. Preserve the existing Blender executor, plan validation, support/contact handling, and preview workflow unless implementation evidence requires a focused change.

## Product behavior

1. The user enters a natural-language request. It can describe a familiar action, an unusual action, a metaphor, a style, or a combination.
2. The interpreter extracts the intended outcome, body emphasis, direction, speed, style, and any sequence or loop requirement. It may use local AI and available context to understand unfamiliar wording; interpretation must not require an exact phrase match.
3. The planner expresses that interpretation as a small, structured sequence of available movement primitives with parameters and timing. The planner does not invent Blender commands, raw rig transforms, or unsupported control names.
4. The motion system composes the sequence, resolves its constraints and contacts, and produces one preview result. It changes only what the user's request calls for; follow-up prompts preserve unrelated parts of the current result.
5. If the request exceeds the available primitives or is ambiguous, explain the uncertainty in plain language and offer to attempt an approximate result with the available capabilities. Do not silently turn an unknown request into a different familiar animation.

## Key design rule

Separate **what the user means** from **how the body executes it**:

- Prompt interpretation identifies intent and descriptive qualities. It can use semantic knowledge to interpret phrases such as “move like a fish swimming through the air.”
- The movement library supplies verified, reusable mechanics: body undulation, alternating limb motion, arm sweep, torso lean, weight shift, step, crouch, reach, lower, rise, and supported contact, for example.
- The planner composes and parameterizes those mechanics into temporal beats. A “fish-like” request might be interpreted as a human imitating swimming, with flowing torso undulation and sweeping arms. It should not be forced to match a `swim` preset or rejected because no exact `fish` animation exists.
- The executor maps semantic movement targets to the current rig and applies the existing interpolation, contact, and validation behavior.

The library should encode **capabilities and coordinated movement patterns**, not the names of every action a user might type. A primitive can have a human-readable label for debugging or suggestions, but prompt matching must not select animation behavior solely by comparing the request against a fixed phrase list.

## Suggested planning contract

Keep the boundary between language interpretation and Blender execution explicit. The model should return a compact, validated plan along these lines (field names are illustrative; align them with the current data models before implementation):

```json
{
  "intent": "imitate a fish swimming through the air",
  "beats": [
    {
      "primitive": "body_undulation",
      "parameters": {"amplitude": "subtle", "direction": "forward"},
      "duration": 1.5
    },
    {
      "primitive": "alternating_arm_sweep",
      "parameters": {"range": "medium", "flow": "smooth"},
      "duration": 2.0
    }
  ],
  "style": ["playful", "fluid"],
  "loop": false,
  "uncertainties": ["A humanoid can imitate the motion, but cannot reproduce fish anatomy."]
}
```

This is an example of intent-to-primitives mapping, not a required exact schema. Reuse or evolve `ActionPlan`, `MotionStage`, and current validation rather than introducing a parallel plan format without need. Primitive IDs must resolve through an application-owned registry; validate parameter ranges, durations, sequencing, and supported controls before Blender receives a plan.

## Existing code to build on

- `src/avatar_app/planning/movements.py` already contains movement construction helpers and reference routes. Evolve its reusable helpers into the primitive library; keep task-sized reference routes where they are useful for verification.
- `src/avatar_app/planning/routes.py` currently recognizes a narrow set of complete requests. Keep narrowly safe, deterministic shortcuts only when they are an optimization over the general planning path. They must not define the product's supported vocabulary or block creative modifiers and unusual prompts.
- `src/avatar_app/planning/action_interpreter.py` should interpret general requests into stages that reference available primitives, validate the result, and preserve the current “change only what was asked” behavior.
- `src/avatar_app/motion.py` and `src/avatar_app/blender/motion.py` remain the plan and execution boundaries. Primitive composition should reuse their timing, contacts, interpolation, review, rollback, and experimental-attempt behavior.
- `src/avatar_app/main.py` should continue to present a simple prompt, progress, result, and correction flow. Internal primitive names need not be exposed to casual users; show them only where a concise explanation or suggestion helps.

Before changing structure, inspect the current types and call paths. Prefer extending the existing movement and action-plan abstractions over creating a second planner, another prompt-specific route table, or a generic framework with no current use.

## Interpretation and fallback rules

- Treat metaphors and novel combinations as valid requests to interpret, not as invalid vocabulary.
- Distinguish a requested **goal** (what the motion should communicate) from **style** (how it should feel) and **constraints** (duration, direction, contacts, loop, or body parts).
- Use known movement primitives to approximate an unfamiliar goal. State a meaningful limitation when the human avatar cannot literally perform the described action.
- Do not fabricate an exact semantic understanding when context is weak. Preserve the request's wording in the plan summary, identify the uncertain mapping, and offer the experimental attempt path already present in the UI.
- A follow-up like “make the arms wider” should adjust the arm movement while retaining the underlying sequence, timing, style, and other body targets unless the user asks to change them.
- If no loop is requested, produce a one-time motion. If a loop is requested, represent loop intent explicitly and validate continuity; do not make every generated preview repeat.
- Suggestions should help the user refine the result (for example, “more arm-driven,” “more fluid,” or “slower”) without replacing their original request.

## Primitive-library design

Start with a small set of verified building blocks that can combine across many intents. Each primitive should define its semantic purpose, supported body controls, tunable parameters, default timing/easing, required contacts or support, and validation expectations. Include primitives for upper-body motion, lower-body motion, coordinated whole-body motion, transitions, and contact/support as the current rig and executor can actually handle.

Keep capabilities composable: “walk like a robot,” “dance like a puppet,” and “swim through the air” can share stepping, limb alternation, joint stiffness or looseness, torso motion, and style parameters. They should not each require a separately hardcoded complete animation. Add a named higher-level pattern only when it captures a reusable coordination or timing rule that cannot be represented cleanly by composing existing primitives.

Do not treat a primitive as a guarantee that every combination will look good. The planner must account for support, reach, collisions, and transitions, and report when a requested combination is experimental or beyond current execution capabilities.

## Performance and interpretation quality

The structured planner should ask the model to choose and parameterize a small number of known primitives, rather than authoring a long list of detailed raw body targets from scratch. This should reduce output size and make plans easier to validate, while keeping open-ended language understanding. It does **not** by itself guarantee faster Blender baking; profile interpretation, motion construction, geometry checks, and any repair rebake separately.

Keep the local model as the default planning option. Any external context assistance must remain optional and must not turn ordinary prompt interpretation into a separate user-operated web-search step. Never rely on a remote service to supply executable movement mechanics; the local library and validator remain authoritative.

## Acceptance examples

The implementation is not complete merely because these exact strings are special-cased. Use them as diverse tests of a general interpretation and composition path:

- “Fly like the fish swims.” Interpret an understandable human imitation, such as fluid torso movement and sweeping arms, and explain any relevant limitation.
- “Move like a T-rex.” Produce a recognizable compact-arm posture and coordinated movement, not a generic backward fall.
- “Sit on the chair, then wave.” Compose a supported seat transition with a separate arm action; do not lose chair contact when waving.
- “Dance like a puppet.” Combine a dance-like sequence with deliberately articulated, puppet-like style; avoid mapping only to one fixed dance clip.
- “Make it more fluid.” Adjust continuity or motion quality while preserving the requested action and its unrelated targets.
- An unfamiliar metaphor should still create a plan or a clear, honest limitation/experimental option; it must not fail only because its action noun is absent from a route regex.

Verify the tests at three levels: planner tests prove diverse wording maps to valid primitive sequences without prompt-specific route matches; primitive tests prove parameter bounds and declared contacts/support are respected; Blender checks inspect representative composed motions visually and verify existing validation/rollback behavior. Record interpretation time and bake time separately on both the supplied avatar and a second rig if available.

## Out of scope

- Replacing Blender or the current animation executor.
- Adding body scanning, avatar reconstruction, or changing avatar structure.
- Hardcoding a separate complete animation for every user phrase.
- Claiming arbitrary motion is supported just because arbitrary text can be parsed.
- Requiring web search, paid AI, or new developer costs for the basic prompt flow.
- Building a large polished preset gallery before the reusable movement system works. User-visible examples can be added later; the first priority is an internal library that makes open-ended prompts more predictable.

