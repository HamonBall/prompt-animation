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
