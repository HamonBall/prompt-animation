# Proposed file and function structure

Status: target architecture with an initial feasibility slice implemented. Product requirements are recorded in avatar-animation-brief.md. The current code uses a Blender-hosted sidebar, immutable motion plans, narrow plan patches, Mixamo import, and a procedural transition builder. It does not yet implement all modules and boundaries described below.

## Organizing principle

Use one local Python application with separate responsibilities for the interface, application workflow, prompt planning, motion construction, and Blender integration. Start from the existing Python/Blender work rather than selecting a new stack before testing motion feasibility.

The AI produces a structured motion plan, not Python code or direct Blender commands. The motion engine turns the checked plan into movement. Blender imports the avatar and applies the resulting motion. Neither the local interpreter nor online context providers need access to Blender's scene objects.

## Proposed tree

```text
work11/
  pyproject.toml
  src/
    avatar_app/
      __init__.py
      main.py
      config.py
      models.py
      session.py
      workflow.py
      ui/
        window.py
      planning/
        context.py
        interpreter.py
        validation.py
      motion/
        builder.py
        constraints.py
      blender/
        client.py
        worker.py
        avatar.py
        animation.py
        scene.py
  assets/
    demo/
  tests/
    test_plan_edits.py
    test_plan_validation.py
    test_context_fallback.py
    blender/
      test_avatar_motion.py
  tools/
    diagnose_fbx.py
  examples/
    blender_hiphop_stage.py
  docs/
    avatar-animation-brief.md
    application-structure.md
    adr/
  CONTEXT.md
```

This is the intended destination, not a request to create empty folders now. Move existing scripts only when extracting reusable behavior. Preserve original FBX inputs; do not turn all personal assets into bundled demo content. The default demo asset still needs selection and distribution checks. Generated previews and local caches belong in per-user application storage, not source folders. Export modules can be added when export enters scope.

## Shared data contracts

Keep a few plain typed records in models.py initially. Split them only when their size warrants it.

| Record | Contents and purpose |
| --- | --- |
| AvatarProfile | Avatar identifier, source file reference, normalized measurements, semantic body-part mapping, rest transforms, supported controls. No bpy objects cross this boundary. |
| MotionPlan | Duration, frame rate, transition or loop, body targets over time, movement pattern, style, root motion, contact constraints, and optional explicit scenery request. |
| PlanPatch | The paths and values a follow-up changes, its base revision, and which targets must remain preserved. |
| ContextResult | Retrieved information, source URLs, availability, and warnings. Missing internet is an ordinary outcome. |
| ValidationReport | Invalid fields, unsupported controls, quality limitations, and whether an experimental attempt is available. |
| MotionClip | Sampled semantic joint transforms, root transforms, timestamps, and contact information. Independent of Blender object names. |
| PreviewResult | Backend preview handle, revision identifier, playback range, and warnings. The handle format depends on the viewport integration decision. |
| ProgressEvent | Job identifier, processing stage, optional measured progress, and user-readable status. |

Use normalized body coordinates and documented units for planning: for example, wrist height relative to avatar height. The backend resolves those instructions through the imported rig's rest transforms. A named elbow direction must not be assumed to equal the same local bone rotation on every avatar.

## Files and entry points

These signatures describe responsibilities; implementation details and exact types may change during the feasibility spike.

| File | Main functions | Responsibility |
| --- | --- | --- |
| main.py | main() | Construct dependencies and open the application. No work occurs merely by importing a module. |
| config.py | load_settings() | Local paths, model/provider choices, timeouts, and free-only policy. Avoid hardcoded C:\\work11 paths. |
| session.py | start_session(), snapshot(), commit_revision(), restore_revision() | Keep avatar identity, current plan, previous successful result, and revision history. |
| workflow.py | load_avatar(path), submit_prompt(text, experimental=False), cancel_job(job_id) | Coordinate the full workflow and publish progress. The UI calls this layer rather than individual AI or Blender functions. |
| ui/window.py | create_window(workflow), show_progress(event), show_result(result), show_limitations(report) | Prompt entry, avatar loading, preview controls, errors, and experimental-attempt action. No motion logic. |
| planning/context.py | retrieve_context(prompt, prior_context), build_context_query(prompt) | Obtain internet context internally, cache useful data, and return available information when services fail or free access runs out. Provider-specific code can be split later. |
| planning/interpreter.py | create_plan(prompt, context, avatar), propose_edit(prompt, current_plan, context) | Translate language into a plan or a narrow patch. Hide local model and optional online assistance behind the same callable boundary. |
| planning/validation.py | validate_plan(plan, avatar), apply_patch(plan, patch), validate_edit(before, after, patch) | Check schema, units, supported controls, revision consistency, and preservation of unrelated plan fields. |
| motion/builder.py | build_clip(plan, avatar) | Compose poses, transitions, timing, and repeating movement into a sampled clip. Its supported movement repertoire grows with verified capabilities. |
| motion/constraints.py | solve_contacts(clip, avatar), check_motion(clip, avatar) | Coordinate supporting adjustments, joint limits, ground contact, and loop continuity. This is a substantive feasibility task, not a completed generic solver. |
| blender/client.py | start_backend(), request(command), cancel(job_id), close_backend() | Manage the local Blender process and structured messages. This is the app-side boundary; it does not import bpy. |
| blender/worker.py | dispatch(command) | Run supported backend operations inside Blender and return serializable results. Queue Blender scene changes on its main thread. |
| blender/avatar.py | import_avatar(path), inspect_rig(handle), build_profile(handle) | Import FBX, identify the rig and body parts, normalize measurements, and preserve original appearance. |
| blender/animation.py | apply_clip(handle, clip), prepare_preview(handle, revision), discard_candidate(revision) | Resolve semantic motion onto the imported rig, keyframe it, and prepare playback without replacing the last good result prematurely. |
| blender/scene.py | create_preview_scene(), set_requested_scenery(spec), frame_avatar(handle) | Camera and lighting, optional geometric scenery, and isolation from unrelated Blender scenes. |

Avoid a generic utils.py: keep a helper beside the behavior that needs it. Do not create an abstraction for every function. The important replaceable boundaries are prompt interpretation, internet context, and the preview backend.

## Request flow

```text
User prompt + current session snapshot
  -> retrieve available internet context
  -> create plan OR propose patch to the existing plan
  -> validate plan and supported capabilities
  -> if needed, explain limitation and await experimental-attempt choice
  -> construct coordinated motion
  -> apply and inspect candidate in Blender
  -> prepare preview
  -> commit successful revision and display it
```

Loading an avatar is a separate workflow. It produces an AvatarProfile before motion is planned. The supplied avatar uses the same import and inspection path as a user's FBX. Switching avatars starts a fresh animation session initially; cross-avatar reuse can be designed later.

The application stays responsive while context retrieval and inference run. Use one active generation job initially. Cancellation and stale job identifiers prevent late results from replacing a newer session. Do not mutate the visible animation incrementally while generation is incomplete. Keep the last successful result if a candidate fails, and release candidate data afterward.

## Corrections must be narrow at the plan level

For an existing balancing pose, "turn only the head to the left" should patch the head direction while preserving arm and leg targets, pelvis position, and timing. The motion solver may make connected supporting adjustments when a correction requires them; the plan must preserve unrelated targets.

Rebuilding affected motion from a patched plan is acceptable; asking the AI to regenerate the entire plan without preservation checks is not. Record why an extra body adjustment was required when it materially changes the result. An impossible edit should produce a clear limitation, not silently discard earlier requests.

An experimental attempt can broaden supported movement combinations, but it still requires a well-formed plan and executable controls. It cannot make a missing animation mechanism exist.

## Using the existing scripts

Candidate behavior to extract from blender_hiphop_stage.py includes FBX import, collection management, camera/light construction, and playback setup. Review each helper during extraction rather than copying the script wholesale. Its current global scene clearing, unconditional material replacements, hardcoded character scales, stage construction, and automatic main() call do not match the new application's default behavior.

diagnose_fbx.py remains a developer tool. Its scene-clearing behavior should run in a disposable Blender scene or process. It must not be called against a user's active preview.

## Decisions deliberately left open

- UI toolkit and preview integration. A standalone window needs a viable way to display interactive animation. A Blender process alone does not provide an embeddable viewport. Test a simplified Blender-hosted interface against a separate window plus preview bridge before committing to either. Repeated full video renders are not a substitute for a responsive live preview.
- Local model, online provider, and credential setup. Free allowances and no developer hosting bill are constraints, not proof that a convenient provider is available.
- Procedural movement vocabulary and solver capability. Validate the T-rex transition and a follow-up correction before claiming general prompt-to-motion support. Later test loop coordination.
- Exact message transport and preview representation. They must support progress, cancellation, and serializable results without leaking bpy objects into the app.

## Verification boundaries

Meaningful initial checks cover narrow edit preservation, malformed or unsupported plans, context failure/quota fallback, and stale-result rejection. Blender integration checks use the supplied rig and a second rig with different naming or proportions, inspecting mapping, preservation of appearance, motion application, and final playback range. Visual review remains necessary for deformation, foot contact, transition quality, and loop continuity.

Do not promise one-to-two-minute performance for AI-driven generation until the full flow has been measured on the target hardware. The initial procedural slice has planning and Blender integration tests; those checks do not establish general motion-generation feasibility.
