# Avatar Animation prototype

A first working slice of the prompt-driven avatar application. It imports a
Mixamo-rigged FBX into a separate Blender scene, preserves its materials, and
constructs a T-rex-like pose transition with planted feet. Follow-up commands
change only the selected plan parameter.

## Run

With Blender 5.1 installed, run from PowerShell:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --python C:\work11\launch_avatar.py
```

The local Andrejs FBX loads as the try-out avatar and generates one transition.
In the 3D View press **N**, select the **Avatar** sidebar tab, and click **Play
once**. Choose another Mixamo FBX with the file field and **Load avatar**.
Switching avatars starts a fresh session. Existing Blender scenes are preserved.
The supplied personal assets are used locally, not bundled for distribution.

Try `T-rex pose`, `T-rex pose in 3 seconds`, then `crouch lower`, `crouch less`,
`stand taller`, `raise arms`, `lower arms`, `slower`, or `faster`.
Each correction preserves unrelated plan fields. Unsupported requests and
out-of-range edits produce an explanation and keep the last successful result.

## Current limits

This feasibility prototype uses an explicit rules-based prompt vocabulary.
Local AI, internet context, arbitrary motion, walking/dancing loops, export,
undo controls, cancellation, and asynchronous generation are not implemented.
Generation runs on Blender's main thread and may briefly block the interface;
its progress counter tracks actual sampled frames. Arm posture is procedural,
not a trained animation model. Visual quality requires further review.
Rig mapping currently requires the main Mixamo bone names and an upright
humanoid rest pose, which is oriented upright from the skeleton on import.
A different naming convention needs a mapping adapter.
The architectural proposal in `docs/application-structure.md` remains the
longer-term direction; the initial UI is deliberately Blender-hosted.

## Verify

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python C:\work11\tests\blender_smoke.py
```

This runs pure planning checks and imports both original FBX files. It checks
correction preservation, leg contact, material preservation, invalid-plan
rejection, finite bone transforms, and isolation from the original scene.
It also renders `artifacts/trex-preview.png` for visual review. Pass
`-- --no-render` after the script argument to skip rendering on subsequent checks.

On this workspace's Blender 5.1 installation, both supplied rigs passed the
import, transition, and crouch-correction checks in approximately 8–9 seconds
per rig, excluding rendering. The corrected avatar rendered upright with bent
arms and a crouch. This measures the procedural slice only, not AI inference
or general motion generation.
