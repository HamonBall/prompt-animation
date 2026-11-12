# Movement evidence storage

Routine evidence uses schema-v2 portable bundles through `tools/artifact_store.py`.
The interactive app still exposes only its prompt interface. Migration results and
actual storage accounting are recorded in `to do/stages/receipts/storage-v2.md`.

## Bundle layout and identity

```
artifacts/assets/<content-hash>/avatar.blend
artifacts/assets/<content-hash>/asset.json
artifacts/stages/<stage>/<rig>/<case>/motion.blend
artifacts/stages/<stage>/<rig>/<case>/preview-manifest.json
artifacts/stages/<stage>/<rig>/<case>/result.json
```

An immutable asset contains the saved static mesh, weights, UVs, normals, rest rig,
materials and packed resources. Identity derives from actual saved content, never
an FBX filename or today's movement builder. Cases share only matching content.
Motion files contain baked actions without meshes, armatures, materials or images.
The manifest preserves active action/slot mappings, object and bone transforms,
custom properties, parenting, visibility, cameras/lights, world/view state,
frame range, current frame/subframe, fps and fps_base. Unsupported constraints,
drivers, NLA, shape keys, vertex colors and unreviewed content fail closed.

Manifest schema 2 has `bundle_root`, `asset` (relative path, SHA256, content hash),
`motion` (relative path and SHA256), `state`, `bindings`, `inputs`, `profile`,
`measurements`, `entry`, `views`, `expected_frames`, timing, `original_scene`,
`verification`, `visual_evidence` and `complete`. Profile and measurement references
are hashed. Paths are confined to the portable artifact root; symlinks, junctions,
missing resources, changed hashes and undeclared libraries are rejected.
Schema-v1 packed canonical scenes and the historical visual-scene fallback remain
readable through `open_preview`. Callers must use that loader rather than opening
`motion.blend` as a standalone scene.

Supported visual representations are `png_sequence` and verified `ffv1_mkv`:
every inclusive frame, declared views and contact sheets. `none_required` identifies
a case with no declared render requirement; it does not claim visual completion.
The original storage-v2 migration retained its PNG sequences. Stage 05.2 also
supports lossless video without changing coverage, resolution or timing.
Front/side view records contain
camera matrices, projection, lens, ortho scale and resolution. Historical CLI
cases can declare explicit `frames_dir` and `sheet` paths.

Each FFV1 view declares a content-addressed MKV path, file SHA256, inclusive frame
list, dimensions, fps/fps_base and the decoded float-RGBA pixel SHA256 for every
frame. Blender's bundled FFV1 encoder writes the movie; an independent decode must
match every original PNG before publication. The sheet remains available for
inspection. No lossy codec or sparse-frame substitution is accepted.

`complete: true` requires all declared frames and sheets. Routine resume additionally
checks inputs, profile, implementation identity and bundle hashes. Read-only
inspection may accept independently verified migrated historical evidence despite
a newer producer implementation; routine rendering must invalidate that resume.
A case named `default` describes parameters; its entry can be authored non-neutral.

## Commands

From `C:/work11`:

```powershell
$artifactPython = 'C:/Program Files/Blender Foundation/Blender 5.1/5.1/python/bin/python.exe'
$artifactBlender = 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe'
& $artifactPython tools/storage_v2.py --operation inventory
& $artifactPython tools/compact_stage_artifacts.py --operation retire-history # dry run
& $artifactPython tools/compact_stage_artifacts.py --operation retire-history --apply
& $artifactPython tools/compact_stage_artifacts.py --operation migrate --apply
& $artifactPython tools/storage_v2.py --operation compact-diagnostics --apply
& $artifactPython tools/storage_v2.py --operation check
& $artifactPython tools/inspect_stage_artifacts.py
& $artifactBlender --python tools/load_artifact.py -- --case artifacts/stages/05.1b/demo/torso.wave.default
# Decode a verified stage-05.2 view into explicit owned scratch when needed:
& $artifactBlender --background --python tools/load_artifact.py -- --case artifacts/stages/05.2/demo/arm.raise.default --extract-view front --frames-output artifacts/maintenance/storage-v2/.scratch/extracted-front
# Explicit owned temporary packed export; inspect then remove after use:
& $artifactBlender --background --python tools/load_artifact.py -- --case artifacts/stages/05.1b/demo/torso.wave.default --export artifacts/maintenance/storage-v2/.scratch/export.blend --temporary
```

`--case stages/05.1b/demo/torso.wave.default` limits maintenance to one case.
Dry-run is default. `--legacy-duplicates` exposes the old duplicate-only test
implementation; it is not the obsolete-history retirement operation.
The loader also accepts an old canonical `preview.blend` path and resolves its
verified manifest mapping. Retired `.blend1` actions are explicitly obsolete
history, without an equivalence claim. Historical receipts remain unchanged.

## Transactions, verification and retention

One resumable journal lives under `artifacts/maintenance/storage-v2/`. Each source
is hash checked against accepted numeric/profile evidence, reopened in Blender,
compared at every frame for bone/object matrices, and independently reopened from
its candidate bundle. Geometry, rest rig, resources, exact curves, slot, timing and
saved state must match. Representative decoded render pixels are compared at
entry, midpoint and exit. Matrix tolerance is at most 1e-5; existing numeric
thresholds are unchanged. No AI call or movement reconstruction occurs.

Candidates and manifests use atomic replacement. A small transaction record keeps
the previous motion until manifest publication; recovery either restores that
motion or finishes committed retirement. The accepted full scene is deleted only
after durable bundle publication and a journal record. Changed inputs, active
leases and unsupported cases retain the original and report the precise cause.
Obsolete-history retirement verifies each current canonical once and journals each
backup's path, bytes, hash and original retained reason before deletion.

Lossless media uses one bounded `media-build.json` and `media-retirement.json` per
case. The build record durably names a verified candidate before its atomic
rename. A retry reconciles either side of that rename and reuses verified movies
for unchanged source PNGs. After the complete hashed manifest is durable, cleanup
retires only enumerated unchanged numbered PNGs and superseded owned movies.
Recovery also handles a stop between manifest publication and creation of the
cleanup record. Unknown owners, path escapes, changed hashes and corrupt pending
files fail closed. A repeated successful case retains one movie per required view,
not another run directory. Temporary encode/decode output is confined to owned
`.scratch` and cleaned after verification.

`tests/blender_lossless_evidence.py` exercises complete two-view conversion,
every decoded frame, injected rename failure, pre-publication reuse,
post-publication recovery, interrupted retirement, extraction and repeated-run
media counts. Pure transaction tests cover both rename states, stale source,
corrupt output and path confinement. `tools/review_shoulders_arms_visuals.py`
prepares labelled review pages from the complete retained contact sheets; preparing
a page does not mark a movement visually reviewed.

Stage 05.2's render-only path performs the measured full-batch preflight once,
then retains actual allocation/commit budget checks for every case and view.
Rendering validates saved action playback but does not rewrite the baked motion
or shared asset. Only view/media metadata is published; the original saved scene
state remains available alongside the explicit front/side camera records.

Budgets in `docs/artifact-retention-policy.md` are enforced at measured batch
preflight, before render expansion, and at actual case commit. Shared assets,
maintenance, exports, global scratch and free space are counted. A reducing
migration may temporarily exceed retained limits, while its scratch limit remains
512 MiB. Routine writes may not bypass retained limits. Successful tests use
owned scratch and clean it; failure pins require a signature, owner, reason and
review trigger. Audits overwrite one compact report. Old verbose pose dumps are
replaced in place by fingerprints and compact assertions, retaining their original
hash/byte identity and existing diagnostic links. New stage receipts must include
storage compliance and retained/temporary accounting.
