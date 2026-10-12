# Make natural-language requests the core interaction

The intended users are casual people who bring an existing Mixamo-rigged FBX avatar or try a supplied character. The product should interpret requests for unusual poses and motion rather than rely primarily on a larger preset library: creative expression is the chosen priority despite the additional difficulty of translating language into body movement.

Body scanning and character preparation happen before this workflow. Requests animate the existing body without changing its structure or appearance. The initial scope includes transitions from a starting pose into a requested pose and repeating motion such as walking or dancing; static pose generation alone does not meet the goal.

The AI should interpret a request, show a preview, and accept natural-language corrections. Follow-up prompts preserve the action, style, timing, and unrelated details while permitting connected body adjustments necessary to implement the correction. It should ask a clarifying question only when ambiguity would produce substantially different results. Ease of use determines the interface; Blender is acceptable but is not a requirement for the user-facing experience.

The user-facing target is an easy-to-understand application that opens to prompts and animation results. Each request produces one result; users refine an unsatisfactory result with another prompt, following the interaction style of AI image generation. Early animation results may be imperfect. Geometric scenery appears only when requested; otherwise the result animates the avatar alone.

The opening demonstration should show one play-through of one animation and receive little emphasis; users come to animate their own avatar. A T-rex-like pose transition was selected as the initial preview example. Transitions and requested loops remain intended capabilities, but multiple demonstrations are not required.

The application initially shows a supplied try-out avatar and lets the user subsequently load their own FBX.

Local AI is preferred for interpreting animation prompts with modest computing resources, but interpretation should use internet context in the background. Users should not need to perform separate web searches. Gemini or another online service may assist; the provider remains undecided. Initial online assistance uses free access only and stops when that allowance is exhausted. This is a hybrid direction rather than an offline-only requirement.

When online context is unavailable, continue using available data, explain the limitation, and offer an attempt. The developer should not bear ongoing computing or service costs. Computation runs on the end user's device without developer-operated inference servers; the user confirmed this interpretation.

The user proposed decomposing a prompt into instructions for limbs and body parts, such as wrist height and elbow direction, then animating from those instructions. This approach needs feasibility validation, including how coordinated movement, balance, foot contact, and timing are produced.

When a request exceeds the supported movement range, explain the limitation and offer an explicit option to attempt an experimental result with unpredictable quality.

Generation may take one to two minutes if visible progress shows that processing is underway, for example through a loading indicator. Hardware feasibility has not yet been verified.

The immediate milestone only needs visible animation results; recording is not required. The eventual application should offer video-file saving. FBX export is a likely later need, not yet a committed first-release requirement. The execution method and precise supported request range remain undecided.
