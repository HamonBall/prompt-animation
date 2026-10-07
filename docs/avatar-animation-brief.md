# Prompt-driven avatar animation

## Purpose

Let casual non-programmers animate their existing rigged character with natural-language requests, including unusual motions beyond a conventional animation library. Game animation is a possible later use, not the primary audience.

## Agreed experience

- Open an easy-to-understand application with a supplied try-out avatar; allow loading a user's Mixamo-rigged FBX.
- Keep the opening demonstration brief: one play-through of one animation. The initial example is moving from a starting pose into a T-rex-like pose.
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

Translate requests into coordinated instructions for body parts, then produce motion from those instructions. For example, a T-rex-like walk combines arm posture, torso lean, alternating leg motion, and timing. Pose instructions alone do not establish a walking cycle: balance, foot contact, transitions, and coordination still need an executable motion system.

This is a proposed method, not a verified arbitrary-motion generator. Web context supplies information; it does not itself produce skeletal animation.

## Current project and next evidence

The original scripts build Blender scenes and play embedded FBX animation. The new feasibility slice adds a Blender sidebar, rules-based prompt interpretation, procedural T-rex transitions, and narrow corrections. It does not yet provide AI interpretation, general motion generation, internet context, or export workflows.

Read-only inspection found an Intel Core i5-6500, approximately 16 GB RAM, Intel HD Graphics 530 integrated graphics, and Blender 5.1. No local AI or animation-generation benchmark has been run. Performance within the requested waiting time remains unverified.

The next technical investigation should test one pose transition and one prompt-based correction, inspect deformation and coordinated movement, and measure latency and resource use. It should also establish a usable free internet-context source and the fallback behavior. These are feasibility checks, not additional opening demos or a guarantee of unrestricted animation support.

## Status

The user confirmed shared understanding of this product scope and authorized implementation. A first Blender-hosted feasibility prototype now imports either supplied FBX, normalizes its orientation and size, builds a T-rex-like pose transition, and accepts narrow rules-based corrections. It preserves imported materials and creates a separate preview scene. AI interpretation, internet context, motion loops, export, cancellation, and asynchronous generation remain unimplemented. See README.md for running and verification instructions.
