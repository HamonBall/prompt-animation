# Stage 06 logical recipe resolution v1

Implemented 2026-11-19. This is a logical planning contract;
composed native execution and its validation remain Stage 07.

`composer.compose_recipe(recipe, entry_state, profile, surfaces, catalog)` returns
the existing immutable `ResolvedRecipe`. Inputs pass registry/snapshot validation
and must match the measured revision. The composer calls trusted plain-data
builders; it never imports Blender, samples a predicted exit as measured state,
changes a scene or invokes a model.

Relations retain v1 spellings: `after` means then, `parallel` means while with an
offset, and `after_event` references an actual authored landmark. Negative offsets
allow overlap, but no instance can precede the operation origin. Independent
instances start at that origin. Schedule order is start time then lexical instance
ID, independent of dictionary order. Bounds include repetitions, tracks, contacts
and the 60-second timeline. Cycles/missing IDs/multiple start constraints reject.

`new` starts at local zero from the supplied current state. `edit` resolves the
complete caller-supplied candidate timeline at local zero and leaves unrelated
instance data intact; it does not apply a patch or replace an existing result.
`append` starts at `entry_state.captured_time_s`, which the caller must obtain from
the measured existing end. All three operations require matching base revision.

## Optional serialized extension

`ResolvedRecipe.resolution_v1` is an optional `RecipeResolutionV1` containing
per-instance `RecipeEntryBindingV1` records, explanations and the mandatory
rebuild-at-activation requirement. Absent extensions retain exact legacy encoding.
Generated schemas and compatibility fixtures live in movement_contracts/v1.

Every future activation binds to one common solved frame snapshot, including
overlapping/event-driven instances. The predecessor list records earlier starters;
it does not license target interpolation as a measured pose. The existing
`ParameterBinding(source='measured_exit', parameter_name='entry_state')` is emitted
only when the dependency has ended. Actual input parameters remain separately
bound with their original values and explicit-parameter provenance.

Builders currently provide timing/topology descriptors using the supplied measured
snapshot. Stage 07 must rebuild future fragments at measured activation, checking
entry requirements, surfaces, limits, duration, landmarks and ownership/contact
topology before candidate publication. Changed topology or incompatible entry must
reject and roll back. No transition is fabricated. Routes that cannot produce a
valid planning descriptor from this snapshot fail closed; broader symbolic route
planning is not claimed by this implementation.

## Ownership and support

Claims use actual fragment controls plus endpoint supporting chains, not parameter
names or a bilateral definition's broad potential ownership. Explicit movements
remain hard. Only `arm.swing` instances without clause links are optional gait
decoration; any explicit hard-goal ownership makes them hard. Hard/contact claims
outrank optional swing, with interval/chain explanations. Equal optional claims use
lexical instance ID. Incompatible hard owners report IDs and physical chain.

Passive primitive entry-contact holds persist until an authored support route
activates. Passive successors inherit unreleased terminal contacts across gaps.
Compatible exact
contacts or continuous fixed holds merge provenance; conflicting targets/surfaces
or ramps reject. Authored support changes remain authoritative. This does not prove
dynamic balance or arbitrary object interaction. Optional style requests remain
scoped in the recipe and cannot override resolved hard ownership or contacts.

Fixtures under `tests/fixtures/recipe_schedules/v1` cover both profiles with
sequential, parallel, hard-conflict, duplicate-contact and cyclic recipes.
`tests/publish_recipe_schedules.py --write` regenerates them; without `--write` it
verifies exact deterministic results. These fixtures are logical data, not baked
motion, and make no new native or visual acceptance claim.
