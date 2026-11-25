# Stage 07 recipe execution v1

Implemented and verified for the reviewed Stage 07 envelope. See the
[receipt](../../to%20do/stages/receipts/07.md) for case coverage and limitations.

`compile_recipe(resolved, entry_state, profile, *, surfaces=None, catalog=None)`
returns `ExecutableMotion`. Compilation revalidates the registry, revision,
surface inputs and resolved schedule. For append, the compiled timeline is local
to the supplied measured end. Applying the resulting segment to an existing
Blender action is a separate operation from compiling that segment.

The optional `recipe_activation_v1` extension contains each delayed instance,
its local start time and a planning descriptor. Omitted extensions retain their
existing v1 encoding. Delayed activation requires a frame boundary. The adapter
solves the preceding motion at that boundary, shares one measured snapshot among
starters, and checks the rebuilt control, phase and goal layout. It then samples
the new curves in the same frame. A rejected rebuild aborts the candidate action.
Delayed passive movements inherit scheduled support. Delayed authored support
changes currently reject before baking.

`recipe_surfaces_v1` records the resolved surface geometry. The adapter compares
that snapshot to the active scene before opening a candidate action. The sampler
uses the existing control and contact representation. Both legacy `ActionPlan`
and compiled recipes go through `sample_motion`. The legacy cursor preserves
its measured baseline, contact, and direction interpolation behavior, including
the 12-stage legacy limit. Recipe budget checks use the typed track representation.

For a stationary returning single-instance loop, the compiler expands finite
cycles with `repeat_fragment` and leaves `LoopSpec` on the executable. Blender
checks measured pose, endpoint, angular velocity and contacts at each seam before
publishing. Multiple-instance or translating recipe loops currently reject.
Partially suppressed tracks, recipe-level styles and inserted transitions remain
explicit capability limits. No per-instance style parameter is changed implicitly.

## Measured segment sequences

`build_action_frames` and `build_action` accept a tuple of application-owned
continuation builders for strict compiled motion. Each builder receives the
preceding segment's measured exit and returns a local `ExecutableMotion`
compiled against that exact snapshot. The baker checks the seam's pose and
planted anchors, preserves a single key at that frame, and reviews the full
candidate action before publishing. A rejected continuation or cancellation
restores the previous action and timeline.

Segments use a common sample rate and frame-aligned durations. The existing
motion sample budget applies to the whole candidate. This path supports pose
articulation. Object-root tracks, loops, and experimental fallback are outside
the sequence envelope. Segment diagnostics carry their index and global sample
time. This API does not change how a serialized recipe schedules delayed
support changes within an individual compiled segment.

The floor-sit candidate compiles leg extension from the exact measured seat.
Both captured soles release before the hip, knee, and ankle tracks move.
Pelvis support stays fixed through the extension and is the only active
support at the end. The seated-to-back continuation still requires measured
planted soles alongside pelvis support, so an extended seat needs a separate
replant transition before that continuation can run.

The run candidate can opt into counter-swing. The measured preparation
distributes the torso lean across available spine joints before the first
stride, and recovery reverses it. The burst alternates bilateral arm
tracks without changing the sole contact schedule. The option leaves
the finite stride count and playback duration intact.

## First public foundation preview

The Blender prompt operator can request a measured recipe for an exact wave
or an unmodified model-selected wave. Both forms carry the same validated
selection to the Blender-thread request adapter. The first public route
starts from the app's neutral standing result, requires calibrated palms
and planted soles, and accepts normal or slow timing. The bake uses strict
review. Existing preview paths handle modified model plans, corrections,
approximations and unsupported entries. The operator retains the stage
description and the returning standing pose for the existing editor.

An exact normal-speed chair request from the app's neutral standing result
uses the recipe with a resolved 35–55 cm seat. The Blender adapter calibrates
skin support and reviews a planted descent. It projects the measured seated
endpoint into the existing editor's pose controls inside the bake transaction.
The editor keeps the chair stages and the solved endpoint. Slow chair prompts,
unsupported heights and other entries still use their existing path.
