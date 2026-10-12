# Five approaches to better avatar motion

## 1. AI-generated stages

Translate a prompt into a sequence of actions rather than a single destination pose. Each stage describes body targets, duration, supporting contacts, and the condition for moving to the next stage.

For example, "lie down on the ground" could become: bend knees → crouch → sit on the ground → lower the torso with hand support → extend the legs and settle. The planner chooses a plausible route unless the user specifies one.

**Work to continue:** Introduce an `ActionPlan` containing ordered `MotionStage` records. Each record includes an action, affected body parts, targets, timing, contacts, and completion conditions. Separate prompt interpretation from stage execution. Follow-up prompts patch the relevant stages while preserving unrelated targets and timing.

**Starting task:** Write a hand-authored lying-down plan and execute its stages before connecting the AI planner. Then compare the model's generated plan against that example.

## 2. Reusable movement building blocks

Create parameterized movements such as shifting weight, lowering the pelvis, bending the torso, reaching, and extending the legs. Each movement operates on body targets over time and can participate in different action plans.

For sitting, combine a backward hip shift, coordinated knee bending, forward torso lean, and a final upright adjustment. Allow stages to overlap: the knees can start bending while the hips move backward.

**Work to continue:** Give each movement a common interface accepting the starting state, avatar measurements, targets, duration, and contact constraints. Return a motion segment and its ending state. Add a composer that schedules segments, blends overlapping contributions, and carries the ending state into the next stage.

**Starting task:** Implement a coordinated crouch from an upright stance, then reuse it as the first stage of both sitting and lying down.

## 3. Adapt existing animation clips

Use recorded animation as the basis for an action or an individual stage. Select a clip by its movement and starting posture, retarget it to the avatar, and adjust its speed, reach, posture, or destination to match the prompt.

For "sit on a low chair," adapt a sitting clip to the seat height and position. A follow-up such as "do it more slowly" changes timing while retaining the movement sequence.

**Work to continue:** Build a clip catalog with action tags, starting and ending states, duration, contact intervals, source rig, and asset provenance. Add semantic rig mapping, retargeting, clip trimming, time adjustment, and transitions between clips and generated segments.

**Starting task:** Retarget one sitting clip onto the try-out avatar, then adapt its hip destination to two different seat heights.

## 4. Contact-driven planning

Describe which body parts contact which surfaces throughout an action. Contacts have an activation interval, a target position or surface, and rules for attachment and release.

For sitting, both feet remain planted while the pelvis approaches the seat; seat contact begins when the body reaches it. For lying down, support can transfer from feet to hands and pelvis, then to the back.

**Work to continue:** Add `ContactConstraint` records to motion stages. Resolve floor and object geometry into reachable targets, use inverse kinematics to coordinate joints, and schedule contact activation and release. Object-dependent actions need a resolved object before planning: whether to create, select, or approximate a missing chair remains a product decision.

**Starting task:** Execute a sitting plan against a simple seat surface, checking foot drift, seat penetration, and pelvis-to-seat distance through the transition.

## 5. Generate-and-review

Inspect a candidate animation before presenting it. Evaluate the whole timeline for abrupt joint changes, foot sliding during planted intervals, surface penetration, unreachable targets, and discontinuities between stages or at loop boundaries.

Produce a structured report identifying the affected frames, body parts, and constraints. Use that report to adjust the relevant targets, timing, or contact schedule, then rebuild the affected motion.

**Work to continue:** Implement deterministic motion checks first. Add a bounded repair pass that applies targeted changes and measures whether the reported error decreases. Keep the previous successful result until the candidate passes checks or the user accepts an experimental preview.

**Starting task:** Compare the current direct pose transition with a staged lying-down transition. Record joint-angle changes, planted-foot displacement, and floor penetration, and visually review both animations.

## Combined direction

Use AI-generated stages to describe the action, reusable movements or adapted clips to construct it, contact constraints to coordinate support, and a review pass before committing the preview. Begin with one hand-authored staged action so motion execution can be evaluated independently of AI interpretation.
