# Prompt-driven avatar animation

## Purpose

Let casual non-programmers animate their existing rigged character with natural-language requests, including unusual motions beyond a conventional animation library. Game animation is a possible later use, not the primary audience.

## Agreed experience

- Open an easy-to-understand application with a supplied try-out avatar; allow loading a user's Mixamo-rigged FBX.
- Open with a neutral avatar ready for a freely written pose request. No single demonstration pose defines the product's capability or development scope.
- Accept freely written requests for actual animation: transitions into poses and repeating actions such as walking or dancing.
- Show one result, then accept follow-up prompts that edit it. Preserve the action, style, timing, and unrelated details, allowing connected body changes required by a correction.
- Preserve the avatar's body structure and appearance.
- Add simple geometric scenery only when requested; otherwise animate the avatar alone.
- Accept imperfect early results and generation times of one to two minutes, with visible processing progress. Progress must reflect actual processing; a percentage is appropriate only if measurable.
- Explain unsupported requests and offer an explicit experimental attempt with unpredictable results.
- Require only visible results for the immediate prototype. Add video saving eventually; FBX export is a possible later capability.

## Intelligence and cost constraints

Prefer lightweight local prompt interpretation, supported by internet context integrated into the workflow. Online AI assistance may help, but initial use must stay within free access; unavailable online context must not prevent an explained attempt using available data.

Avoid ongoing computing or service costs for the developer. Computation runs on the user's device without developer-operated inference servers. Exact distribution, online credentials, providers, quotas, and hardware requirements are not yet selected.

## Motion hypothesis to validate

Translate requests into coordinated instructions for body parts, then produce motion from those instructions. For example, a balancing pose combines independent arm directions, a raised knee, torso orientation, and a supporting leg. Pose instructions alone do not establish a walking cycle: balance, foot contact, transitions, and coordination still need an executable motion system.

This is a proposed method, not a verified arbitrary-motion generator. Web context supplies information; it does not itself produce skeletal animation.

## Current project and next evidence

The original scripts build Blender scenes and play embedded FBX animation. The application now uses local Qwen interpretation and a general anatomical pose contract for independent limbs, torso, head, pelvis, whole-body orientation, and wrist targets. The user explicitly redirected work away from the initial single-pose milestone toward broad natural-language pose coverage. Motion loops, internet context, export, and robust arbitrary-pose quality remain unverified or unimplemented.

Read-only inspection found an Intel Core i5-6500, approximately 16 GB RAM, Intel HD Graphics 530 integrated graphics, and Blender 5.1. No local AI or animation-generation benchmark has been run. Performance within the requested waiting time remains unverified.

Continue testing varied whole-body poses and narrow follow-up corrections, inspecting deformation, coordination, and latency. The scope is broad prompt-to-pose interpretation rather than optimizing one named pose. A usable free internet-context source and fallback behavior remain future work. These checks do not establish unrestricted animation support.

## Status

The user authorized implementation and clarified that broad prompt-to-pose coverage is the goal. The Blender-hosted prototype imports the supplied FBX, normalizes orientation and size, preserves materials, and builds pose transitions from general skeletal controls. Local AI interpretation runs in a worker; cancellation discards pending results. Narrow plan edits preserve unmodified fields. Pose coverage and visual quality still need continued validation. See README.md for running and verification instructions.
