# Required contract: one fragment bridge, composer and compiler

This resolves the early-execution dependency. Library movements must run before the general recipe composer exists. They share one representation, sampler and Blender executor.

## Stage 04: one authored fragment

Input is one validated MovementInstance, its measured entry snapshot, AvatarProfile and resolved surfaces. Its builder returns a MotionFragment containing bounded typed tracks, authored phases and contact events. A single fragment may coordinate several joints; 'single' means one declared movement/pattern result, not one bone.

Stage 04 implements prepare_fragment() and sample_motion(), then adapts the existing build_action_frames execution loop to accept ExecutableMotion alongside legacy ActionPlan. Reuse its rig application, contact solving, measurement, progress, rollback and result review. Do not create another keyframing loop or bypass review with a developer-only bone mutation path.

Initially support hold/transition descriptors; later body stages add shared bounded line/arc/circle or phase descriptors when their advertised movement requires them. The bridge does not parse user intent, schedule independent movement instances, select entry transitions or arbitrate conflicting owners.

Existing ActionPlan keeps its 12-stage validation limit. The fragment adapter uses the shared track/contact/frame budgets and does not disguise sampled frames as thousands of MotionStage objects. This narrowly scoped typed-track adapter is implemented in 04, not postponed to 07.

The bridge's developer harness takes explicit ID/version, parameters, rig, entry fixture and output directory. It writes actual sampled measurements and a full-motion preview. No AI call is needed. A fixture may set a known parent pose to test one primitive; this is not a general composition engine.

## Stages 05.*: library content and shared operators

Builders may call lower-level tested helpers and return one fragment with a declared internal timeline. They may not invent independent graph formats, renderer loops, priority systems or per-family samplers. For a simple lower/rise, the authored support phases are part of that movement's builder.

Patterns can transform/repeat explicit compatible fragments into one bounded fragment. Preserve provenance and nested instance counts. Before stage 06, an overlap operator accepts only pre-resolved compatible ownership and rejects a conflict; it does not decide which independent user goal to sacrifice. Test seams/phase through the same bridge.

A family needing an unimplemented curve/control must add the narrow versioned extension, measurement and tests in its assigned stage. A need for general graph scheduling is recorded for 06 rather than implemented privately.

## Stage 06: logical recipe resolution

Input is multiple validated instances and relations. Output is a ResolvedRecipe with schedule, chain ownership, support decisions, selected existing transitions and provenance. This layer is plain data.

Examples such as walk+wave can be expressed using existing body.step and stroke patterns even before legacy foundation migration in 08. Tests must not depend on an unimplemented recipe.wave factory. No Blender mutation occurs here.

Some entry values cannot be solved until preceding motion executes. Record a runtime entry binding to the preceding measured exit; do not fabricate a solved pose during logical planning.

## Stage 07: compile recipes through the bridge

Compile the resolved graph to the same ExecutableMotion and sample_motion() contract from 04. Prepare indexes/bindings and merge compatible tracks; do not introduce a second typed plan/sampler. Adapt legacy ActionPlan evaluation through that contract with regression checks.

At an activation boundary, capture the measured solved state once into the per-run execution cursor. Sequential and parallel transitions use the same frame-boundary snapshot; the result must not depend on iteration order. Sample goals, solve constraints, measure the achieved state and retain that state for the next frame/boundary.

A failed segment does not commit its output or silently seed later segments. Candidate rollback covers the whole generated result. Saved recipe targets and measured end states remain distinct.

## Required evidence

04 publishes a valid single-fragment fixture, invalid/over-budget fixtures, legacy equivalence and cancellation results. Every 05.* stage identifies the exact curve/control extension it used. 06 supplies deterministic schedule/conflict fixtures. 07 runs the same fragment fixtures through a one-instance recipe and compares results, then validates multi-instance/loop behavior. Equivalent sampling must remain within the guide's tolerances.
