# Implementation plan: a broad, composable movement preset library

Date: 2026-10-14

Storage requirements updated 2026-10-26: all implementation stages and maintenance follow [the project artifact-retention policy](../docs/artifact-retention-policy.md). Complete [storage-v2 migration](storage-reduction-and-retention-plan.md) before further large stage-05 evidence generation. Retain exact baked motion and full required validation coverage while sharing immutable avatar assets and bounding generated history.

Status: proposed implementation plan, based on the conversation, project briefs, TODO notes, current source, tests, and saved reports. This document does not claim the proposed capabilities are implemented or newly tested.

Execution is now split into [numbered, independently assignable work packages](stages/00-START-HERE.md), with [required interface contracts](stages/contracts/01-library-api.md), [execution boundaries](stages/contracts/03-execution-boundaries.md) and a [per-movement coverage ledger](stages/movement-coverage.md). Use those documents for implementation order, permitted changes, tests and completion gates. This document remains the design reference. Begin with dependency-verified cleanup, then build the library before integrating the AI and scene systems.

## 1. The direction to implement

Build a large internal library of reliable, parameterized movements covering individual joints, limbs, coordinated body actions, and transitions. Use those movements to construct animations from freely written prompts. Natural-language input remains the main user interaction.

Here, **preset** means a reusable piece of movement with known mechanics and adjustable parameters. Examples include bending a knee, pointing an elbow outward, rotating a palm upward, moving a wrist along an arc, shifting support onto one foot, or coordinating alternating arm strokes. Complete actions such as walking and waving are reusable compositions of these smaller pieces.

The desired pipeline is:

> User prompt + current animation → understand intent → find suitable movement presets → compose and parameterize them → resolve body coordination and contacts → generate and review the animation → show one result → accept a narrow correction.

The purpose of building many presets is to improve the range and quality of combinations the application can execute. A growing list of recognized prompt phrases does not achieve this. New combinations must work without adding a dedicated handler for each sentence, animal reference, action name, or metaphor.

“Fly like the fish swims” is a useful example. It contains both an airborne movement request and a swimming-inspired style. The application should be able to combine root travel, body orientation, flowing torso motion, and coordinated limb strokes. It must preserve the airborne part rather than silently return a standing arm gesture. The avatar keeps its existing humanoid structure; adding fish anatomy is unnecessary.

## 2. Context and decisions carried forward

The intended users are casual non-programmers. They start with the supplied avatar and can later import their prepared, rigged FBX. Scanning and rigging happen before this application. Game and video use are possible later applications.

Preserve these product decisions:

- Produce actual animation, including transitions into poses. Support repeating motion when requested; a finite movement can contain repeated strokes without becoming an endless loop.
- Show one result and accept corrections such as “only bend the wrists more.” Preserve unrelated motion, timing, direction, and appearance.
- Start from the current measured state when continuing a movement. A new generation from the beginning of an existing timeline and an appended movement are different operations.
- Keep avatar structure, proportions, and materials. Detect optional bones instead of adding them to the user's skeleton.
- Keep the interface simple: prompt, progress, preview, correction, and an explained experimental attempt when appropriate.
- Add scenery only when requested or required by an explicit object interaction. A request for flight does not automatically request water, clouds, wings, or a new scene.
- Prefer modest local computation. Avoid developer-operated inference servers and recurring developer costs.
- Internet context can help interpret unfamiliar references in the background. Continue using available local information if it is unavailable. Context is descriptive input; executable mechanics come from the library and solver.
- The user accepts roughly one to two minutes with honest progress. Reducing this is desirable; it is a measured target rather than a promise.
- Visible results are the immediate deliverable. Video saving and possible FBX export follow after the motion system is useful.

This plan develops [movement-primitives.md](movement-primitives.md) into an implementation roadmap. It supersedes the older emphasis on proving sitting and lying as the main development milestones. Those actions remain valuable regression cases alongside a much broader set.

The older ADR's preference for prompt-driven interaction still applies. Its wording about avoiding reliance on a larger preset library should be read in light of the user's current direction: the internal library is now the principal execution resource, while users continue to express goals freely in prompts.

## 3. Current implementation: reuse and gaps

| Area | Verified in the current source | Work required |
| --- | --- | --- |
| Ready motions | planning/presets.py exposes jump, walk, lie, run, and wave; walking/running are finite two- or four-step sequences | Extract their reusable phases and support combinations, varied parameters, and more starting states |
| Shared movements | planning/movements.py has movement(), construct_movement(), crouch(), and floor/seat routes | Turn this beginning into a discoverable, versioned library with consistent contracts |
| AI planning | action_interpreter.py supports selecting one foundation with extra controls, writing stages, or patching stages | Select multiple compatible movements, schedule them, and express anatomical intent compactly |
| Anatomical controls | pose.py has upper/lower segment directions, hand/foot orientation, root/torso/head rotation, pelvis offsets, wrist/foot targets | Add explicit joint-relative intent and calibration; direction of a shin is not a knee bend angle |
| Rig mapping | avatar.py maps core Mixamo bones and optionally Spine1, Spine2, Neck | Map shoulders, toes, fingers, and twist bones when present; declare capabilities per avatar |
| Timing/composition | ActionPlan and MotionStage support sequencing and overlap of different controls, with a 12-stage and 60-second bound | Support larger composed recipes, reusable curves, ownership of complete joint chains, and synchronized cycles |
| Constraints | Foot/hand IK, scheduled floor/seat contacts, evaluated-skin checks, motion review, bounded repair | Generalize joint bend planes, support transitions, collision handling, and aerial modes as needed |
| Editing | Stable stage IDs, target patches, measured ending poses, rollback | Preserve recipe-level intent and primitive-instance IDs so edits remain precise after compilation |
| Playback/UI | Prompt-first UI, one-shot playback, streamed model progress, cancelable frame construction | Preserve these behaviors and distinguish requested loop content from preview playback policy |
| Performance | Solid viewport shading, skin/bounds caching, skipped identity rotations, frame-by-frame UI yielding already exist | Measure remaining costs rather than reimplementing those fixes |
| Imported clips | clips.py and blender/clips.py support an explicit catalog and Mixamo retargeting | Reuse selected clips or segments as optional library content with clear provenance and contact metadata |
| Internet context | reference.py fetches a supplied public URL when enabled | Automatic contextual retrieval remains a separate integration task |

Important constraints visible in the code:

1. Foundation adaptation currently copies the same extra controls into every stage. This cannot represent “look left only during the second step” or “start waving after takeoff” without a richer composition.
2. The current foundation schema enumerates five choices. Expanding that enum to hundreds of full actions would make prompts larger and still leave combinations unresolved.
3. Overlap validation checks matching control names. Two operations can use different names and still fight over the same physical chain, such as a wrist target and an elbow angle.
4. Contacts currently cover feet, hands, pelvis, and back on horizontal floor/seat surfaces. Knee support, wall contact, grasping, and general object interaction require additional mechanisms.
5. The current hand/foot orientation controls and limb elevation/azimuth values do not form a full anatomical joint model. The new library must not claim wrist flexion, forearm twist, and elbow orientation are already independent calibrated controls.
6. Measured state includes solved pose controls, but a general composer also needs contact anchors, trajectory phase, velocities where relevant, and active motion ownership.
7. A saved real-model foundation run records about 92.26 seconds of interpretation and 8.37 seconds of construction. It is one historical sample, with model startup potentially included in interpretation, not a current benchmark average. Reusing a complete motion alone has not established fast interpretation.

## 4. Library structure: four levels

| Level | Contents | Example | Who constructs it |
| --- | --- | --- | --- |
| Joint motion | An anatomical degree of freedom or an endpoint/orientation target with a curve | Bend left elbow; tilt right wrist; turn head | Deterministic library and rig adapter |
| Coordinated movement | Several joints and support rules working together | Reach, step, squat, weight transfer, arm stroke | Deterministic movement builder |
| Motion pattern | Repeated or phased coordination across movements | Alternating steps, torso wave, symmetrical strokes, sway | Pattern composer |
| Action recipe | A reusable arrangement of movements/patterns for an intended action | Walk and greet; jump and turn; lower to a seat | Authored recipe or validated AI composition |

Every level must be usable in a larger composition. A wrist motion can accompany walking; an arm stroke can accompany airborne travel; a torso pattern can modify several locomotion recipes.

The local AI should usually select coordinated movements or patterns and specify a few explicit joint details. The compiler expands their mechanics. A prompt that explicitly mentions a knee, elbow, or wrist may select the corresponding joint primitive directly.

Use parameterized families rather than one file for every combination of side, angle, direction, and speed. Build a broad catalog across the families below, then add reviewed variants. Catalog size is a planning measure; acceptance depends on tested coverage and motion quality.

## 5. Movement catalog to build

The IDs below are proposed names, not existing executable controls. Each family needs a builder or validated curve implementation before it is advertised to the planner. Left/right, direction, amplitude, timing, and style are usually parameters rather than duplicate implementations.

### 5.1 Head, neck, spine, and pelvis

| Family | Movement and important parameters | Coordination requirements |
| --- | --- | --- |
| head.look | Look toward a character-relative direction or target; angle, hold, return | State whether the target is relative to the torso or fixed in the world |
| head.nod | Pitch down/up; amplitude, cycles, phase | Keep neck and torso motion separate |
| head.shake | Turn side to side; amplitude, cycles | Preserve requested torso direction |
| head.tilt | Ear toward shoulder; side and amount | Avoid silently twisting the whole body |
| neck.lead | Neck begins a gesture before the head settles | Require a mapped neck; otherwise use a declared head-only approximation |
| torso.lean | Forward/backward/side lean with entry and recovery | Account for the support state and intended center shift |
| torso.twist | Rotate upper body relative to pelvis | Distribute motion across available spine bones |
| torso.curl | Progressively flex/unflex spine | Preserve head targets unless the recipe includes head follow-through |
| torso.wave | Traveling bend through spine; plane, amplitude, phase delay | Multi-bone curve; one-bone rigs use a simpler declared version |
| torso.sway | Periodic side/forward movement | Synchronize with pelvis and planted feet |
| pelvis.shift | Move pelvis sideways/forward/backward relative to support | Maintain reachable legs and specified anchors |
| pelvis.raise_lower | Change height; amount, duration, easing | Coordinate hip, knee, and ankle adjustments in supported motion |
| pelvis.tilt_turn | Pelvic orientation relative to root/body | Add calibrated pelvic orientation rather than rotating the entire avatar |
| pelvis.circle | Circular/elliptical motion; size, plane, direction | Reuse shift curves and support solver |

### 5.2 Shoulders and upper arms

| Family | Movement and parameters | Coordination requirements |
| --- | --- | --- |
| shoulder.shrug | Raise/lower one or both shoulders | Optional clavicle/shoulder bones; report capability |
| shoulder.reach | Protract/retract shoulder during a reach | Keep arm length and torso adjustment explicit |
| shoulder.roll | Smooth shoulder cycle | Joint-aware limits and phase |
| arm.raise | Raise/lower arm in forward, side, or intermediate plane | Preserve or explicitly change elbow bend |
| arm.sweep | Sweep across/outward/backward through a specified arc | Check chest/head clearance |
| arm.swing | Pendulum-like movement; amplitude and phase | Pair with gait or leave independent |
| arm.circle | Circular endpoint path; radius, plane, cycles | Resolve elbow continuously; avoid flips near a straight arm |
| arm.fold | Bring upper arms close to torso or across chest | Bilateral collision and ordering matter |
| arm.reach | Reach hand toward a point, direction, or body landmark | Solve shoulder/elbow chain with reach and bend-plane constraints |
| arm.stroke | Sweep, recover, repeat; path and recovery parameters | Reusable in swimming, flying, dancing, and expressive gestures |

### 5.3 Elbows, forearms, wrists, and hands

| Family | Movement and parameters | Coordination requirements |
| --- | --- | --- |
| elbow.flex | Bend/extend relative to upper arm; target bend and duration | Hinge angle is distinct from forearm elevation |
| elbow.orient | Point elbow forward/outward/downward around a wrist target | Expose stable bend-plane/pole intent; wrist position remains constrained |
| forearm.twist | Turn palm up/down through forearm pronation/supination | Map available twist bones or distribute along the forearm; keep wrist bend separate |
| wrist.flex | Bend palm toward/away from forearm | Calibrated wrist-local axes |
| wrist.deviate | Tilt hand toward thumb/little-finger side | Correct handedness on both sides |
| wrist.circle | Combine flexion and deviation in a controlled cycle | Preserve hand attachment and forearm twist |
| hand.orient | Face palm toward a direction/target; orient fingers along another axis | Resolve a full orientation without confusing it with hand position |
| hand.trace | Move wrist on a line, arc, circle, or authored curve | Arm IK resolves supporting joints; specify reference frame |
| hand.hold | Hold wrist position/orientation while other body parts move | Distinguish a free-space target from contact with a surface |
| hand.gesture | Open hand, fist, point, relaxed curl | Optional finger mapping; preserve the requested major arm motion on rigs without fingers |
| finger.curl_spread | Per-finger or grouped curl/spread | Later coverage; require appropriate bones and preserve topology |

Include asymmetric versions: one wrist flexed while the other stays straight, one palm upward while the other faces outward, and differing elbow directions. These are core prompt capabilities, not rare exceptions.

### 5.4 Hips, thighs, and knees

| Family | Movement and parameters | Coordination requirements |
| --- | --- | --- |
| hip.lift | Bring thigh forward/backward; height or angle | Specify supporting leg and pelvis response |
| hip.open_close | Move thigh out/in relative to pelvis | Avoid unintended root translation |
| hip.rotate | Turn thigh inward/outward | Coordinate knee and foot direction within configured ranges |
| leg.extend | Extend an unweighted leg toward a direction | Knee extension and foot orientation are separate |
| leg.swing | Swing leg through an arc | Release support first and preserve clearance |
| knee.flex | Bend/straighten knee relative to thigh | Stable hinge direction; no accidental sideways folding |
| knee.lift | Raise knee as a coordinated hip/knee action | Foot target and support response are part of the builder |
| knee.orient | Set the leg bend plane for a reachable foot target | Do not implement this as arbitrary lateral knee rotation |
| knee.pulse | Small repeated supported bend | Coordinate pelvis/ankles and timing |
| leg.cross | Cross or uncross legs | Use explicit clearance and starting-state requirements |
| leg.fold | Fold leg toward body or behind | Require reachable geometry and explicit support/airborne mode |
| leg.kick | Prepare, extend, recover | Reuse lift/extend primitives with anticipation and planted-support rules |

Kneeling is a coordinated floor interaction and requires knee-contact support. It is not complete when the knees merely look bent near the floor.

### 5.5 Ankles, feet, and toes

| Family | Movement and parameters | Coordination requirements |
| --- | --- | --- |
| ankle.flex | Point foot or draw toes upward | Ankle-relative angle; preserve orientation inherited from the leg |
| ankle.tilt | Tilt foot inward/outward within configured ranges | Restrict according to planted/free state |
| foot.place | Move foot to a floor destination | Swing clearance, orientation, and contact acquisition |
| foot.lift | Raise a free foot while holding another support | Preserve the supporting anchor |
| foot.pivot | Turn around a heel/toe/sole anchor | Reposition support geometry without sliding the whole foot |
| heel.raise | Lift heel with forefoot support | Requires distinct sole/toe support locations |
| toe.raise | Lift forefoot with heel support | Requires heel anchor |
| foot.roll | Heel-to-sole-to-toe progression | Useful in walking and landing; contact transitions need timing |
| foot.tap | Lift/contact a small distance with repetitions | Separate tapping foot from weight-bearing support |
| toes.curl | Optional toe articulation | Use mapped toe bones when present |

### 5.6 Root travel, support, and coordinated body movement

| Family | Movement and parameters | Coordination requirements |
| --- | --- | --- |
| root.travel | Translate along a line or curve; distance, height, heading | Separate world travel from local pelvis motion and stable support anchors |
| root.turn | Turn body; angle and turn path | Use stepping/pivoting when grounded; free orientation when airborne |
| root.orient | Tilt body into a desired overall orientation | Preserve independent limb targets and collision rules |
| root.hover | Maintain requested elevation, with optional controlled bobbing | Explicit stylized airborne mode; no automatic floor settling |
| support.transfer | Transfer load/contact ownership between supports | Reach the new support before releasing the old one for grounded motion |
| support.acquire_release | Attach/detach hand, foot, pelvis, back, or supported future anchor | Controlled contact ramps and resolved surfaces |
| body.lower_rise | Lower/rise through coordinated legs and torso | Reuse pelvis, knee, ankle, and support primitives |
| body.step | One step with swing and stance phases | Starting anchors and ending anchors are part of its result |
| body.lunge | Shift into and out of a directional stance | Leg reach, support width, and torso placement |
| body.takeoff_land | Preparation, takeoff, flight, landing, recovery | Allow flight; avoid floor snapping and premature contact |
| body.balance | Maintain a support-consistent pose while moving free limbs | Initially a geometric support approximation, with explicit boundaries |
| body.floor_transfer | Transition between upright, seated, side, or back support | Reuse contact transitions; add routes as capabilities become available |
| body.kneel_rise | Transfer between feet and knee support | Depends on new knee contacts and skin-clearance checks |
| body.crawl | Alternate hands/knees or hands/feet | Depends on support and limb-phase mechanisms, not just four limb swings |

### 5.7 Patterns and style operators

Build shared timeline operators: hold, transition, repeat a finite number of times, alternate left/right, mirror, synchronize, phase-offset, overlap, and blend in/out. These operate on movement instances and must preserve their contact rules.

Add reusable patterns: alternating steps, synchronized strokes, alternating strokes, torso undulation with limb follow-through, side-to-side sway, hop sequences, turn sequences, arm-leg opposition, and gesture phrases with preparation/action/recovery.

Represent style as controlled changes to curves and coordination:

- Smooth/fluid: continuous velocity, rounded paths, delayed follow-through where appropriate.
- Robotic/staccato: deliberate pauses and sharper timing within validated motion limits.
- Heavy: longer preparation and recovery, smaller or slower changes, visible weight transfer.
- Light/playful: smaller support dwell, modest bounce, quicker recovery where the mechanism permits it.
- Exaggerated: increase relevant amplitudes within limits; retain requested contacts and goals.
- Tired: reduced amplitude, slower transitions, changed torso posture where compatible.

Style operators must have declared scope and bounds. “Fluid” should not change path direction; “robotic” should not disable contact validation; “bigger arms” should not automatically increase leg motion.

## 6. Joint semantics and rig calibration

This is a prerequisite for a useful limb library. Do not populate hundreds of presets on top of inconsistent joint axes.

Build an AvatarProfile from the existing importer containing:

- Core and optional bone mapping, rest transforms, segment lengths, body landmarks, and measured avatar scale.
- Anatomical forward/up/right frames and each joint's local bend/twist axes.
- Elbow and knee preferred bend planes with continuity information near straight-limb configurations.
- Wrist/ankle neutral orientation; palm normal and finger-forward direction; sole orientation and contact offsets.
- Available capabilities: clavicles, segmented spine, neck, fingers, toes, twist bones, and supported contact anchors.
- Configured per-joint ranges and quality tolerances, versioned with the rig adapter. These are animation configuration, not universal human limits.

Document units at every boundary. Use seconds for timing, degrees for semantic joint angles, and explicit world metres or avatar-relative distances for positions. Include the reference frame in each target: world, root/body, torso, pelvis, a limb's parent, or a resolved support surface. Never infer the frame from an ambiguous field name.

Preserve existing control conventions through an adapter while migrating. New knee flexion must be compiled from thigh-relative bending; it must not alias directly to shin_elevation. New wrist flexion must follow the forearm's orientation when the whole body turns. Forearm twist and wrist bend are distinct operations.

Mirroring is anatomical: exchange sides and reflect the appropriate directions, trajectories, orientations, and contact anchors. Validate it after a body turn and in non-neutral poses. Do not negate every number indiscriminately.

Extend measured-state capture alongside new controls. A plan cannot validate joint-relative elbow bend using only its requested target value; inspect the solved rig and compare in the same frame and units.

## 7. Contracts for library entries and movement instances

Use typed Python records initially, with deterministic JSON serialization for saved recipes and diagnostics. A data file should describe parameters and curves, never execute arbitrary code. Export an authoring format later if needed; avoid maintaining duplicate Python and JSON definitions as separate authorities.

Each library entry needs:

| Field | Purpose |
| --- | --- |
| Stable ID and version | Reproducible selection, saved recipes, and cache invalidation |
| Level, description, semantic tags | Retrieval and planner understanding |
| Builder kind | Joint curve, coordinated procedural motion, pattern, or reviewed clip segment |
| Parameter schema | Types, units, frames, defaults, allowed ranges, side selection |
| Required capabilities | Bones, joint controls, supported surfaces, IK and contact features |
| Entry conditions | Compatible posture, supports, reach, orientation, and previous movement state |
| Controls/chains owned | Targets the movement sets and body chains it may need to solve |
| Contact obligations | Required, acquired, maintained, and released supports |
| Timing/phase behavior | Duration, internal landmarks, repeats, phase compatibility, entry/exit ramps |
| Composition rules | Valid overlays, soft preferences, exclusions, and allowed supporting adjustments |
| Exit state contract | Expected pose/support/phase/velocity properties to pass to the next movement |
| Verification record | Rigs, parameter envelope, measured checks, visual approval, version |
| Provenance | Author/source and distribution permission when using an external clip |

A MovementInstance references an entry by ID/version and supplies parameters, a stable instance ID, placement in the timeline, and the user-request clauses it satisfies. Retain those clause links through compilation so corrections and diagnostics can identify the right movement.

A MotionRecipe contains movement instances, ordering/overlap dependencies, shared parameters, loop policy, explicit constraints, and style operators. It is the compact authoring representation above ActionPlan, not a replacement Blender executor.

A MotionStateSnapshot contains the measured pose, root transform, support anchors, active contacts, avatar profile version, current revision, and available trajectory phase/velocity information. Capture it at the correct edit or append boundary.

## 8. Prompt interpretation and library retrieval

### Step A: identify the request's meaning and edit scope

Extract action goals, referenced body parts, spatial relationships, style, temporal order, simultaneous actions, duration/repetition, airborne/grounded intent, and object requirements. Mark which constraints were explicit and which were defaults.

Classify whether the user requests a new motion, a correction to an existing motion, or an appended action. Use the current conversation and recipe. Ask a concise clarification only when the ambiguity would materially change the result; otherwise use a visible reasonable interpretation.

### Step B: retrieve relevant capabilities

Keep the catalog broad without placing every preset definition in every model prompt. Retrieve short descriptions by body family, semantic purpose, current support state, and available rig capabilities. Include coordination helpers such as support transfer when an apparently local request needs them.

Start with deterministic metadata search and compact family summaries. If a metaphor cannot be matched reliably, let the model explain its motion qualities and select families; then retrieve the corresponding entries. A retrieval miss triggers broader family search or an explained limitation, not forced selection of the nearest familiar complete animation.

Prefer a single model call for routine requests. A bounded second call is reasonable when the first identifies a missing family or needs a specific correction. Record why it was needed and include its time in the total budget. Do not add an open-ended model/tool loop.

### Step C: select and compose

The AI returns library IDs, parameters, temporal relationships, intended support mode, and unresolved uncertainty. The application supplies schema/defaults, expands recipes, computes body mechanics, and validates the result. The AI should not calculate every bone keyframe or regenerate contacts already defined by a reviewed movement.

Include a generic set of joint/endpoint primitives so an unusual goal can be expressed even without a high-level named pattern. A finite executable vocabulary is appropriate; a finite list of accepted user intents is not.

Example interpretation: “Walk forward, wave with your left hand, and look right.”

- Use a stepping pattern for locomotion and foot contacts.
- Give the left-arm gesture ownership of the left arm during its interval, replacing only the gait's optional arm swing on that side.
- Schedule head orientation concurrently, preserving right arm motion and the gait's root path.
- Blend the left arm into and out of the gesture; retain continuous foot support and end anchors.

### Step D: check semantic coverage before building

Every explicit clause must be accounted for as fulfilled, approximated with an explanation, or unsupported. Store this in diagnostics and show only useful summaries in the casual UI. Valid JSON and passing geometry checks alone do not prove that the avatar performs the requested motion.

For “wrists at chest height, elbows pointing forward,” check wrist positions relative to the torso, elbow bend-plane direction, and palm orientation separately. Do not consider a vaguely raised-arm pose sufficient.

### Internet context

Keep the current optional reference path while designing automatic retrieval separately. Use context to resolve unfamiliar references and movement descriptions; cache concise useful descriptions with sources. Avoid mandatory network requests for simple joint edits or known library capabilities. No service/provider selection or free-access assumption is required to implement this local movement library.

## 9. Composition rules that prevent broken animations

### Starting state and transitions

Every builder receives actual entry state. A movement authored from standing must declare that precondition. If the avatar is seated, the composer either inserts an appropriate transition or uses a seated-compatible version; it must not reset silently to standing.

Pass the solved exit state forward, including contacts and root displacement. Match position and velocity where motion should continue. Add intentional holds where the request calls for them. Do not force every internal stage to stop and restart.

### Simultaneous movements and ownership

Resolve ownership at the physical-chain level as well as the control-name level. Give contacts and explicit hard targets precedence over optional style preferences. Treat mutually impossible explicit constraints as a conflict requiring an explained adjustment or experimental attempt.

Examples:

- A planted hand cannot also trace a free-space circle during the same interval; release contact or reject that combination.
- A wrist endpoint and elbow direction can cooperate through an IK pole preference. A fixed wrist, fixed shoulder, and incompatible exact elbow angle cannot all be satisfied.
- Walking plus waving can share a body because the gesture replaces optional arm swing; walking plus a full-body pose that fixes both feet in place needs temporal sequencing or an explained interpretation.
- A wrist-only correction may require a small supporting forearm adjustment. Bound it, preserve unrelated body goals, and explain a material change.

Use one contact schedule shared by the composed motion. Merge compatible contact requests; never duplicate competing owners for the same support anchor.

### Supported and airborne motion

Represent grounded, supported-on-object, transitional flight, and sustained stylized airborne motion explicitly. Ground contacts are active only when appropriate. Floor collision checks still apply to airborne motion, but automatic settling must not pull an intentional flight path to the ground.

Root travel should have its own trajectory; pelvis offsets describe local body coordination. This avoids treating long travel or flight height as an increasingly large pelvis correction against original foot anchors. Retain compatibility with current foot offsets through the compiler.

For grounded movements, start with geometric support reasoning and explicit transfer paths. Add a simple support-region/body-center check with a clearly defined approximation. Dynamic balance is a separate capability; do not label a kinematic check a full physics simulation.

### Curves, phase, and loops

Provide a shared sampler for bounded curves, oscillations, phase offsets, holds, and entry/exit ramps. Preserve shortest-path orientation continuity where applicable and unwrap intended multi-turn rotation explicitly. Do not average arbitrary Euler angles to blend rotations.

The current 12-stage limit will be exceeded by ordinary composed patterns. Keep a compact logical recipe and introduce explicit compiled resource limits based on duration, frame count, active channels, and contact events. Do not remove limits blindly or ask the model to emit hundreds of expanded stages.

Stage 04 adds bounded MotionFragment/ExecutableMotion tracks and a shared sampler to the existing executor for individual movements. Stages 05 add content/curves; 06 resolves recipes; 07 compiles them into that same representation. Keep legacy ActionPlan compatibility through an adapter and its existing stage limit; do not introduce a second independently maintained typed plan. Prepare schedules, control ownership, and curve adjacency once rather than repeatedly rediscovering them per frame.

For requested loops, match local pose, motion phase, velocities, and contact state at the boundary. A traveling walk loop can have a declared root displacement per cycle; its global start and end positions need not be identical. Preview one cycle by default while retaining loop metadata for later playback/export.

## 10. Corrections and recipe preservation

Keep the source recipe, compiled plan, measured result, and mapping from instance IDs to generated stages/tracks. Correct the recipe by stable IDs, then rebuild its affected dependency region. Preserve locked targets, timing, phase, path, and unrelated instances.

Examples of required behavior:

- “Only bend the wrists inward”: edit wrist flexion/deviation with clear anatomical meaning; preserve arm paths, torso motion, and travel.
- “Make the knees higher”: adjust knee-lift/step clearance and necessary supporting mechanics; preserve the walking direction and requested arm gesture.
- “Keep the elbows closer to the body”: change elbow-plane preferences and check reach; retain hand goals where compatible.
- “Same movement, slower”: scale duration and contact ramps coherently; preserve ordering and spatial paths.
- “Wave only on the second step”: target the relevant gait phase instead of copying an arm adjustment across the entire plan.
- “Now turn left”: use session context to distinguish an appended turn from an edit to the previous travel path; preserve the resulting position instead of restarting at the origin.

Do not use text similarity alone to decide that a correction is a fresh action. Maintain base-revision checks so late inference or a stale edit cannot replace a newer result.

## 11. Building and reviewing each preset

Use a repeatable authoring workflow:

1. Define the movement's purpose, parameter schema, required controls, starting states, and contact obligations.
2. Implement one deterministic builder using the existing solver and calibrated semantic controls.
3. Exercise typical values and representative boundaries, both sides, and at least one non-neutral entry pose.
4. Inspect rendered motion over time from useful angles. A single endpoint screenshot is insufficient for smoothness, support transfer, and joint flips.
5. Measure solved joint values, contact drift, floor/object penetration, speed/acceleration, and transition continuity.
6. Validate the movement on the built-in avatar and an imported rig with different proportions; expand the supported envelope only after review.
7. Mark the entry as reviewed for that envelope, experimental, or unavailable for a given avatar. Expose the correct status to retrieval.
8. Add at least one composition with an unrelated body motion and one narrow correction before treating the entry as generally reusable.

Use authored procedural movements for precise joint/endpoint control. Reuse suitable recorded clip segments for complex coordination when their source and distribution rights are known. Record start/end state, phase landmarks, supported parameter ranges, contact intervals, and retargeting requirements. Preserve the existing explicit clip catalog; do not guess that a personal dance asset contains a different action.

The initial catalog can cover roughly 60–90 movement families across the tables above, delivered in batches. Mirrored versions, amplitude settings, and speed settings can create many usable variations, but should not inflate the count of independently verified mechanics. Maintain a coverage sheet listing family, implemented parameters, supported rigs, combinations tested, and quality status.

## 12. Proposed files and functions

Keep motion.py as the existing plan module. Do not create an avatar_app/motion/ directory alongside it. Introduce the library package when the first extraction is implemented; avoid scaffolding empty modules for later phases.

| File | Main responsibilities and proposed entry points |
| --- | --- |
| src/avatar_app/movement_library/contracts.py | MovementDefinition, MovementInstance, MotionRecipe, MotionStateSnapshot, parameter and capability records |
| src/avatar_app/movement_library/registry.py | register_movement(), get_movement(), list_capabilities(), validate_instance(); authoritative catalog metadata |
| src/avatar_app/movement_library/joints.py | Builders for calibrated head, elbow, knee, wrist, ankle, and other joint motions |
| src/avatar_app/movement_library/limbs.py | Reach, trace, sweep, stroke, leg swing, and other coordinated limb builders |
| src/avatar_app/movement_library/support.py | Support transfer and acquire/release builders; requirements expressed as plain data |
| src/avatar_app/movement_library/patterns.py | Alternation, mirroring, repetition, phase relationships, undulation, gait patterns |
| src/avatar_app/movement_library/recipes.py | Ready composed actions and migration of existing foundation recipes |
| src/avatar_app/movement_library/composer.py | resolve_entry_state(), resolve_ownership(), schedule_instances(), build_transitions(), compose_recipe() |
| src/avatar_app/movement_library/compiler.py | compile_recipe() to the shared ExecutableMotion, preserving source-instance mapping and resource limits |
| src/avatar_app/planning/retrieval.py | Retrieve compact relevant capability descriptions and report retrieval misses |
| src/avatar_app/planning/action_interpreter.py | Interpret intent, select/compose library instances, decode validated responses, and propose scoped recipe edits |
| src/avatar_app/planning/presets.py | Temporary compatibility adapter for existing foundation callers during migration |
| src/avatar_app/planning/movements.py | Reuse existing helpers; move behavior once into the appropriate library module and keep adapters where needed |
| src/avatar_app/planning/routes.py | Retain safe shortcuts through the same registry/compiler; no separate animation behavior for regex matches |
| src/avatar_app/pose.py | Validated canonical control extensions and legacy-control adapters |
| src/avatar_app/motion.py | ActionPlan compatibility, compiled tracks, shared bounded sampling, timing, patch validation |
| src/avatar_app/blender/rig_profile.py | inspect_capabilities(), calibrate_joint_frames(), capture_motion_state(); serializable outputs |
| src/avatar_app/blender/pose.py and blender/animation.py | Extend existing anatomical mapping and IK for new controls; reuse existing solvers |
| src/avatar_app/blender/motion.py | Execute compiled motion and measure the solved result; preserve yielding, rollback, and review |
| src/avatar_app/blender/geometry.py | Reuse geometry caching; add profiled contact/collision queries where required |
| tests/test_movement_library.py and related focused tests | Contracts, composition, retrieval, edit preservation, and malformed-input behavior |
| tests/blender_movement_library.py | Rig-based motion/transition checks and representative visual artifacts |
| tools/benchmark_movement_library.py | Separate interpretation, composition, construction, review, and playback measurements |

Suggested central interfaces:

- retrieve_movements(intent, avatar_profile, state) → compact catalog subset and missing capabilities.
- instantiate_movement(id, parameters, state, avatar_profile) → validated instance with requirements.
- compose_recipe(instances, relations, state, surfaces) → resolved recipe or explicit conflicts.
- compile_recipe(resolved, entry_state, profile) → ExecutableMotion with instance-to-output mapping; see the stage API contract for exact signatures.
- apply_recipe_patch(recipe, patch, base_revision) → validated revised recipe and affected dependency region.
- review_result(recipe, measured_samples) → geometry/motion checks plus measurable semantic-goal checks.

Keep the library and planning layers independent of bpy. Keep Blender scene writes in the current main-thread execution path. Do not duplicate rig solvers inside each preset builder.

## 13. Performance work

Measure before increasing library size or changing the solver. The important costs are model startup, prompt processing, token generation, retrieval/composition, per-frame rig evaluation, geometry extraction, key insertion, review/repair, and playback.

Priorities:

1. Give the model compact relevant capability summaries and current recipe summaries. Avoid serializing the full catalog and every expanded frame/stage into each prompt.
2. Make simple repeat/side/speed/angle variations library parameters. Do not regenerate raw target sequences for them.
3. Compile schedules and curve relationships once. Reuse the existing skin and bounds cache and count actual cache hits/misses.
4. Profile dependency-graph updates and key insertion. Consider bulk key construction and avoiding unchanged channels only after measuring the effect and confirming equivalent playback.
5. Use cheap kinematic/contact checks during construction, with detailed evaluated-skin review for the resulting candidate. Any sparse/coarse checks need an explicit strategy for catching fast collisions between samples; preserve full checks at contact transitions and final review requirements.
6. Cache semantic recipes separately from rig-specific baked output. Baked-cache keys need the rig/profile version, measured entry state, contacts/surfaces, motion parameters, library/compiler version, timing, and quality mode.
7. Rebuild only affected regions when a narrow edit permits it; include supporting chains, changed downstream state, and blend margins. Start with correct whole-plan recompilation if partial rebuilding is not yet trustworthy.
8. Preserve frame-by-frame cancellation. One unusually expensive frame can still delay the UI despite the existing time budget, so measure worst frame duration as well as overall time.

Measure cold and warm model runs separately. Record input/output token counts where available, hardware, model settings, rig/mesh size, motion length, and quality settings. Report medians and slow cases over a representative suite instead of quoting one fastest run.

Initial acceptance targets: no added inference call for a cached/exact deterministic request; no material construction regression for equivalent current motions; ordinary prompts aim to remain within the user's 60–120 second expectation on the target machine; visible progress and cancellation remain responsive. Set tighter numerical budgets after collecting the baseline. Optimize without loosening quality thresholds merely to claim speed.

## 14. Numbered execution stages

The [stage index](stages/00-START-HERE.md) replaces the previous broad phase sketch. Each linked work package has Plan, Execution, Testing, Validation and Restraints sections, explicit dependencies, required outputs and a completion receipt. Library stages must satisfy every assigned row in the coverage ledger. The linked contracts resolve API/coordinate and execution-boundary details; object collision has its own stage 13.1 before object interaction.

| Stages | Work |
| --- | --- |
| 01 | Audit dependencies, remove proven obsolete code, preserve live helpers and useful tests |
| 02–04 | Library contracts, rig calibration and a small executable primitive preview path |
| 05.1a–05.7b | Separate body-region, joint, support, pattern and style library assignments |
| 06–08 | Timeline-stage composer, animation compiler and migration of existing foundations |
| 09–11 | Capability retrieval, local AI recipe interpretation and precise follow-up edits |
| 12–15, including 13.1 | Object specifications, construction, complete-object collision review, interaction and physical scene assembly |
| 16 | Optional recorded-clip integration |
| 17–18 | Measured optimization and end-to-end acceptance |
| 19 | Optional bounded reference-context integration |

The composer and compiler precede AI integration so the interpreter has working capabilities to select. Temporal action stages and physical scene construction are separate systems. Use the dependency list in each numbered document; do not implement the entire roadmap when assigned one stage.

## 15. Acceptance suite and quality criteria

Maintain a reproducible suite across: isolated joints, coordinated limbs, supported transitions, locomotion, simultaneous actions, unusual metaphors, loops, edits, and unavailable capabilities. Use several paraphrases per intent and reserve some prompts/combinations from tuning so they test generalization.

| Request or scenario | Required evidence |
| --- | --- |
| “Raise the left knee and keep both palms facing upward.” | Appropriate one-leg support, measured knee lift, distinct palm orientation on both sides |
| “Keep wrists at chest level, elbows pointing forward.” | Correct torso-relative wrist heights and elbow planes without a whole-body preset |
| “Circle only the right wrist.” | Wrist-local motion while preserving the arm path and the rest of the animation |
| “Walk and wave with the left hand while looking right.” | Concurrent channels, gait contacts/root travel preserved, waving replaces only the relevant optional arm swing |
| “Fly like the fish swims.” | Airborne root path, fluid body/limb coordination, no invented anatomy or scenery, no floor snapping |
| “Move like a T-rex.” | Interpreted compact-arm posture, elbow/wrist details, and coordinated movement; recipe built from reusable pieces |
| “Dance like a puppet.” | Visible articulated timing/style, continuity and bounds appropriate to the effect |
| “Sit on the chair, then gesture with both hands.” | Resolved seat support survives the arm movement; starting pose and transitions are correct |
| “Crouch, reach sideways, then rise.” | Continuous, reachable whole-body coordination from actual entry state |
| “Turn around and then point forward.” | Correct distinction between character-relative and world-relative directions |
| “Loop the swimming motion.” | Phase/pose/velocity/contact continuity and appropriate declared root displacement |
| “Only make the wrists bend more.” | Identifiable wrist-instance patch; unrelated recipe parameters and measured motion preserved within tolerances |
| Same recipe on different proportions | Goal preserved through rig mapping/reach adjustment, with declared approximation if necessary |
| Rig without fingers/toes | Major requested movement remains valid; missing detail is identified rather than fabricated |
| Conflicting constraints or impossible reach | Specific conflict and useful adjustment/experimental option; previous result retained |
| Missing internet/local inference error/cancel | Explained fallback or failure, cancellation behavior, no stale result committed |

Validation has three distinct layers:

1. **Plan validity:** known IDs, parameter/frame/unit validation, declared capabilities, ownership, contact consistency, revision checks, bounded resource use.
2. **Executed motion quality:** measure actual rig angles/targets and skin/contact behavior, joint flips, sudden changes, loop seams, and transitions. Extend existing review rather than measuring requested values as if they were achieved.
3. **Semantic and visual quality:** inspect whether the motion expresses all important requested clauses, shows appropriate style, and looks coherent over time. A physically tidy wave is still the wrong answer to a flight request.

Retain current motion-review thresholds as the compatibility baseline: 3 mm floor/surface penetration, 25 mm contact error, 360 degrees/second joint speed, and 3000 degrees/second-squared angular acceleration. Define new joint/goal tolerances explicitly and measure them in calibrated frames. Any change to thresholds needs its own evidence; experimental status must remain visible.

Proposed release gates, to assess on a recorded fixed suite:

- Every advertised reviewed family passes its supported parameter and rig checks.
- At least 90% of routine supported prompts produce a usable first preview, with the sample count and scoring rubric reported. Treat this as a target, not a current result.
- Every failed or approximate request has a specific cause/omission recorded; unsupported input does not silently become another action.
- Narrow edits preserve unrelated recipe fields exactly and unrelated measured motion within declared numerical tolerances, except documented supporting adjustments.
- Existing foundation behavior, cancellation, previous-result restoration, and stale-revision rejection continue to pass their relevant checks.
- Performance reports separate interpretation, construction, review/repair, and playback and compare equivalent motions against Phase 0.

## 16. First implementation task

Assign [stage 01: dependency audit and cleanup](stages/01-cleanup.md) first. It records the baseline and removes only proven obsolete implementation paths after preserving their live helpers and meaningful test coverage. Then assign contracts, calibration and primitive execution individually before the body-region stages.

The library still targets a raised knee with independent palms, chest-height wrists with forward elbows, coordinated arm/torso motion and isolated wrist corrections. These are cross-family acceptance examples rather than permission to implement several unassigned stages at once.

## Context sources reviewed

- Conversation requirements and corrections through 2026-10-14.
- [Product brief](../docs/avatar-animation-brief.md), [architecture proposal](../docs/application-structure.md), [initial decision](../docs/adr/0001-prompt-driven-avatar-animation.md), and [domain context](../CONTEXT.md).
- [Five motion approaches](../docs/ideas/motion-planning-approaches.md), [motion fixes and implementation notes](motionfix.md), and [previous movement brief](movement-primitives.md).
- [Current README](../README.md), planning presets/routes/interpreter/movements, pose and motion data models, Blender rig/pose/motion/geometry code, clip catalog, model runtime, reference loading, and prompt UI.
- Existing preset/planning tests, Blender foundation/preset/performance checks, and the saved [foundation run](../artifacts/foundation-live.json). Historical documentation claims were checked against current source where they affected this plan. Tests and benchmarks were inspected, not rerun while writing this document.
