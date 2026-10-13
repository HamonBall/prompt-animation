# Avatar Animation prototype

A local application for turning natural-language descriptions into body poses and staged motion
on a Mixamo-rigged FBX avatar. General AI planning and internal movement foundations
share the same anatomical controls and animation review. The interpreter decomposes
requests into independent anatomical controls; Blender builds a transition
from the avatar's rest stance to the resulting pose or through an ordered action plan.

## Run

With Blender 5.1 installed, run from PowerShell:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --python C:\work11\launch_avatar.py
```

The local Andrejs FBX loads when available. A fresh checkout instead generates an
original stylized rigged avatar from code, so no personal FBX is required to try it.
Open **Avatar settings**, clear the FBX field and load again to use this built-in character.
In the 3D View press **N**, select the **Avatar** sidebar tab, describe a pose,
and click **Generate / refine**, then **Play once**. Choose another Mixamo FBX
under the collapsed **Avatar settings** panel with the file field and **Load avatar**.
The main interface shows the prompt, generation/playback controls, and result status.
Movement foundations and their stage mechanics stay internal.
Switching avatars starts a fresh session. Existing Blender scenes are preserved.
The supplied personal assets are used locally, not bundled for distribution.

The preview floor is 5 × 5 metres. Editing and playback use Solid shading with
avatar textures and studio lighting to keep the viewport responsive. Switch to
Material Preview when checking scene lighting; final renders still use Eevee.
The viewport grid is hidden so the visible ground stops at the floor edges.
The preview includes a visible floor and an optional seat. In **Avatar settings**, enable **Preview seat**
and set its height before requesting chair interaction.
A successful floor-only support route clears the preview seat for space behind
the avatar; enable it again for the next chair request.

## Internal movement foundations

Enter a request in the prompt. Ready animations help the planner construct the
result automatically; there is no preset selector or separate preset command.
The internal library contains these finite, standing-start mechanics:

| Foundation | Movement |
| --- | --- |
| Jumping | Crouch, take off with both feet airborne, land and recover. |
| Walking | Four forward steps with alternating planted feet, then stop. |
| Lying down | Crouch, sit on the floor and lower onto the back. |
| Running | Four forward strides with flight phases, then stop. |
| Waving | Raise the right hand, wave three times and lower it. |

The same routes recognize simple prompts such as `jump`, `walking`, `lie down`,
`run forward`, and `wave`. `walk 2 steps` and `run 2 steps` choose shorter routes;
`wave with your left hand` mirrors the gesture. Add `slowly` to slow a route.
For descriptive requests, the local AI can select a foundation and add body
adjustments, parameters or timing while preserving unrelated mechanics and contacts.
Follow-up corrections edit the existing result. Unfamiliar actions and combinations
continue through the general planner; the library does not define the supported vocabulary.
These are finite procedural moves; continuous locomotion loops are still pending.

Foot paths use three coordinates (`left/right_foot_target_side/forward/height`)
relative to each foot's neutral floor anchor, normalized by avatar height.
Side/forward offsets range from -.8 to .8; height ranges from 0 to .35. Leg IK
reaches these targets while stance contacts hold the supporting foot in place.
Airborne stages preserve clearance with `grounding=0`. The measured ending foot
anchors are retained for follow-up edits after walking or running.

`tests/blender_presets.py` verifies actual flight, floor support, forward travel,
follow-up anchor preservation and motion review. For example:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python-exit-code 1 --python C:\work11\tests\blender_presets.py -- demo jump walk run wave lie --render
```

Use `andrejs` or `mixamo` instead of `demo` for the local imported avatars. Reports
and renders go to `artifacts/presets/`. `tests/blender_preset_ui.py` checks the prompt-only
panel, automatic foundation reuse/adaptation and cancellation during takeoff.
`tests/blender_foundation_live.py` checks a descriptive request with the actual
local model, then builds and reviews its adapted animation. It records interpretation
and construction times separately in `artifacts/foundation-live.json`.

Describe a whole-body pose or an individual adjustment. For example:

- `Reach straight up with both arms.`
- `Salute with your right hand, leaving the left arm relaxed.`
- `Sit as if on a chair, with knees bent.`
- `Bow deeply from the waist.`
- `Stand on your left leg and bring the right knee to hip height.`
- `Lie flat on your back with arms out to the sides.`
- `Turn only your head to the left; keep everything else unchanged.`
- `Lie down on the ground, crouching and sitting before lowering your torso.`
- `Make the lowering stage slower; keep the earlier stages unchanged.`
- `Do the entire motion more slowly.`

## Staged motion

The first implementation of `docs/ideas/motion-planning-approaches.md` adds
`ActionPlan`, `MotionStage`, resolved surfaces, and timed contact constraints.
The AI can generate arbitrary sequences, patch existing stages by ID, or scale
timing while retaining body targets. Static posing remains available.
Targets carry forward; stages controlling different joints can overlap using
absolute start times. Contradictory ownership and unresolved objects are rejected.
Adjacent targets share monotone Hermite tangents, carrying velocity through a
continuing movement rather than easing every stage to a stop. Direction reversals
still decelerate. Contact acquisition/release uses smooth ramps and elbow continuity.

The executor starts each movement from the actual preceding solved state,
including joint changes made by contact IK. Feet attach at their current
positions. Wrist supports acquire and release gradually; pelvis/back supports
coordinate body placement. Free stages settle onto the floor. Pelvis/back
anchor height adapts to the evaluated skin as the body turns;
this is approximate contact placement, not a physical balance simulation.
Surfaces represent a floor and bounded horizontal seats, not arbitrary collision meshes.
The body, supporting hand regions and seat are checked using evaluated skin vertices;
rotated bounding-box corners are not used as skin measurements.

Before committing a staged candidate, every sampled frame is checked for finite
transforms, angular speed (360°/s maximum), angular acceleration (3000°/s²),
root jumps, planted-contact drift, and floor/seat penetration. Completion compares
the measured joint orientation and wrist/foot/pelvis coordinates with requested targets;
it does not compare planned numbers with copies of themselves. Skin contact gaps
are measured separately from bone anchor positions. One
bounded floor-repair rebuild is allowed, with before/after measurements. Other
failures keep the previous action, pose, frame range, and camera. Reports identify
the affected frames, joints, and stages. Loop-boundary checks remain pending because
looping motions are not implemented.

`planning/movements.py` supplies a parameterized coordinated crouch reused by
reference sitting and lying-down routes. These references test the general executor;
they are not a prompt whitelist. Simple `Lie down on the floor`, `Sit on the ground`, and `Sit on a chair`
requests use these checked routes without model inference. Creative requests still
use the general AI planner; recognized lying destinations are checked for endpoint
orientation and explicit support. The visible seat's actual center, footprint and
height are passed to planning. Successful motion records its measured ending pose
for the next request, including adjustments made by contacts and grounding.

Run the hand-authored route, rollback checks, and two seat-height checks:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python C:\work11\tests\blender_motion.py -- --render
```

Stage renders and the direct-versus-staged timeline comparison are written to
`artifacts/motion/`. Add `--mixamo` to test the second avatar. Run
`tools/benchmark_actions.py` with Blender's Python to compare actual local AI
planning with the reference. Larger plans can be slow and may fail validation;
the procedural reference and model interpretation are tested separately.
`tests/blender_generated_action.py` applies that recorded real-model reply to
the rig and checks its destination, without repeating inference.
`tests/blender_initial_motion.py` checks that a crouched starting posture is retained.

## Local animation clips

`clips.py` adds an explicit JSON catalog with action tags, starting/ending posture,
source rig, provenance, trim interval, and planted-foot metadata. The experimental
Blender adapter maps Mixamo joints between different avatars, trims and retimes
clips, adjusts a pelvis destination, and reviews the resulting segment before
commit. It is currently a separate CLI path; automatic AI clip selection, partial
contact intervals, and mixing recorded clips into procedural stages are pending.
No sitting clip has been supplied, so the sitting-clip example is not claimed as
verified. The existing personal dance assets are not relabeled as sitting motion.

A catalog entry looks like:

```json
[
  {"id":"owned-sit", "path":"sit.fbx", "tags":["sit"],
   "starting_state":"standing", "ending_state":"seated",
   "source_rig":"Mixamo", "provenance":"Your asset provenance",
   "start_frame":1, "end_frame":80, "planted_feet":["left","right"]}
]
```

Use `tools/retarget_clip.py` in Blender with `-- --catalog PATH --clip owned-sit`
and optional `--duration SECONDS --pelvis-height METRES`. The source FBX must
contain one animation take. Adapted output and its report go to `artifacts/clips/`.
`tests/blender_clips.py` checks trim, retiming and retargeting on the supplied
local dance clip, preserving the avatar's materials.

New whole-body poses reset previous controls; follow-up edits preserve controls
that the patch does not touch. There is no whitelist of pose names. The plan
supports independent upper/lower arms, thighs/shins, pelvis offsets, torso and
head angles, whole-body orientation, hand/foot orientation, and explicit wrist/foot
positions. Wrist targets use a two-segment arm solver for hand-on-body poses.
The AI can use anatomical directions such as `forward`, `up`, and `left`;
the application translates those into the rig's coordinate conventions.
The backend supports optional planted feet and floor correction for free poses.
Free poses settle onto the floor by default; an explicit `grounding=0` control
allows intentionally airborne poses while still correcting floor penetration.
It frames the camera around both endpoints of the transition.

The status text describes the actual checked values. Invalid model replies,
unreachable targets, and failed builds keep the previous successful animation.
Use `neutral pose` to reset without needing model inference.

## Local AI setup

The workspace is configured for **Qwen3 4B Q4_K_M** with a portable CPU-only
llama.cpp runtime. Both were downloaded and verified during development. To
recreate this setup from PowerShell:

```powershell
& C:\work11\tools\setup_local_ai.ps1
```

The script downloads approximately 2.5 GB of model weights plus the runtime
into the ignored `.runtime` directory, checking the published SHA-256 hashes.
It installs no global service. After setup, prompts run entirely locally with
no API key or service charge. Without an optional web reference, generation makes
no external request. The application starts a hidden
model process on demand, bound to loopback with a random port and per-process
access token, and stops its owned process on normal exit.

Restart the prototype to load updated Python code. A missing model or failed
inference explains the problem and keeps the existing result. Neutral reset
remains available without the model.
AI interpretation runs in a worker while Blender stays responsive. **Cancel
request** or **Esc** discards that request's result; inference already running
may finish in the background. There is no invented percentage during inference.
Model replies stream as they are generated, so a slow CPU request can continue
past five minutes while the server responds. Stalled connections and server
errors report their cause. The planner omits the full lying example from general
requests to reduce input processing; checked floor routes remain available.
Motion construction still runs on Blender's main thread and tracks sampled
frames, yielding between them so the UI can redraw and cancel. Canceling during
construction rolls back the partial action. Inference reports real phases and
elapsed time with a cyclic activity indicator, never an invented completion percentage.
Switching scenes or changing the current revision rejects stale results.

After a rejected request, **Try anyway (experimental)** asks for an approximation.
An explicitly requested experimental preview can fail quality checks; the interface
labels it and offers **Restore reviewed result**. Unknown controls, nonfinite data,
out-of-range values and unreachable IK targets still cannot be applied.

**Use web reference**, under **Avatar settings**, is off by default. Supply a public HTTPS HTML/plain-text URL
to add readable page text and its source URL to the local planner. Only that URL
is fetched; the prompt and avatar are not sent to the website. Redirects, private
addresses, credential-bearing URLs and large/non-text responses are rejected.
Page text is quoted data, never executable code or instructions overriding validation.

## Current limits

The model returns structured pose data, never executable Blender/Python code.
Controls, numeric limits, complete wrist/foot targets, and foot reach are checked.
This is an approximate procedural pose system: broad pose representation does
not establish that almost every prompt already works well. Interpretation,
joint realism, skin deformation, self-contact, and balance need further work.
Precise fingers, facial expression, general object interaction, physics, internet
search, walking/dancing loops, general export, and undo controls are not implemented.
Staged procedural actions are supported; repeating motion cycles are still pending.
Rig mapping currently requires the main Mixamo bone names and an upright
humanoid rest pose, which is oriented upright from the skeleton on import.
A different naming convention needs a mapping adapter.
The architectural proposal in `docs/application-structure.md` remains the
longer-term direction; the initial UI is deliberately Blender-hosted.

## Verify

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python C:\work11\tests\blender_poses.py -- --render
```

This verifies six unrelated poses on the root-level demo avatar: overhead
reach, salute, seated posture, bow, one-leg balance, and lying on the back.
It checks selected endpoint positions, materials, finite transforms, and bone
scale. Renders are written to `artifacts/poses/`. Omit `-- --render` to skip
rendering. Model-generated poses require separate visual review.

To check the interpreter without importing an avatar:

```powershell
$env:PYTHONPATH = 'C:\work11\src'
& 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe' -m unittest discover -s C:\work11\tests -p 'test_*.py' -v
& 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe' C:\work11\tools\benchmark_poses.py
```

The benchmark uses actual local inference across varied pose descriptions and
writes `artifacts/pose-benchmark.json`. `tests/blender_ai_ui.py` exercises
Blender's commit, cancellation, and failure-recovery boundary without opening
anything in `problems/`. `tests/blender_ai_live.py` checks an actual local model
request through to a new Blender action using the root-level demo avatar.
Full-body plans can take longer than simple edits on this CPU. These tests are
small feasibility samples, not proof of unrestricted pose generation.

`tests/blender_motionfix.py` checks the source-free avatar, visible surfaces,
measured target failures, stricter speed checks, experimental preview, generator
cancellation and the real preview seat. Its renders are in `artifacts/motionfix/`.
Project Markdown files (briefs, decisions, ideas and task notes) are now trackable;
personal media, model downloads, generated output and `problems/` remain ignored.

Runtime API: [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).
Model: [official Qwen3 4B GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF).

The earlier limited interpreter and tests remain as historical feasibility
code; the application now uses `planning/action_interpreter.py`, `motion.py`,
and `blender/motion.py`, with `pose.py` and `blender/pose.py` for static poses.
Original personal assets and the `problems/` folder are not
modified by this work.
