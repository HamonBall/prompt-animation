# Stage 03 — Map and calibrate anatomical joints

Status: **complete** (2026-10-19). See [receipt](receipts/03.md) and [implemented rig semantics v1](../../docs/contracts/rig-semantics-v1.md). Dependencies: [02](02-library-contracts.md).

Read [00-START-HERE.md](00-START-HERE.md) and completed prerequisite receipts before execution. Its budgets, numeric tolerances, regression rules and receipt format apply here. Implement only this document.

## Plan

Establish meaningful anatomical axes before defining a large moveset. A knee bend must mean thigh-relative flexion, and a wrist bend must follow the forearm when the avatar turns.

**Permitted changes:** New blender/rig_profile.py; focused changes to blender/avatar.py, pose.py and measured-state capture; rig-profile tests. Read shared solver locations from the stage-01 receipt.

## Execution

1. Implement inspect_capabilities(), calibrate_joint_frames() and capture_motion_state(). Reuse current core Mixamo mapping; detect optional neck, spine segments, clavicles, toes, fingers and twist bones without adding bones.
2. Record rest transforms, segment lengths, palm/finger and sole directions, preferred elbow/knee bend planes, character forward/up/right and per-joint local frames. Store software limits and tolerances explicitly in the profile, with provenance/calibration version.
3. Define flexion/extension, deviation, pronation/supination, limb direction and endpoint target as different semantic quantities. Document mapping to existing controls and flag quantities requiring new adapter support.
4. Implement or expose measurement helpers for achieved joint angles, endpoint position and palm/sole orientation. Capture current root transform, contacts/anchors and revision. Mark unavailable phase/velocity explicitly rather than inventing zero as known data.
5. Verify mirror mapping in neutral, turned and bent configurations. Preserve imported mesh, materials, rest skeleton and overall scale behavior.

## Required outputs and handoff

Follow [rig semantics](contracts/02-rig-semantics.md). Publish `docs/contracts/rig-semantics-v1.md` and two calibrated profiles under `tests/fixtures/rig_profiles/`. For each advertised control record zero, sign, parent frame, unit, min/max, mirror rule and independent measurement. Include turned-parent evidence and optional-capability results. Later authors consume these definitions instead of guessing another rotation convention.

## Testing

- Create tests/blender_rig_profile.py with demo and one imported rig of different proportions. Inspect known 0/positive/negative rotations and compare measured local angles against applied rotations.
- Test missing optional bones, asymmetric bind orientations, nearly straight elbow/knee configurations and character yaw of 90 degrees.
- Check core import/pose regression tests. Save axis/landmark inspection images and numeric profile summaries.

## Validation / completion gate

Joint-frame tests meet declared tolerances on both rigs. Palm-up and knee/elbow flexion have consistent semantic meaning after a root turn. Missing optional anatomy is represented as a capability gap. Do not mark two-rig validation complete if only one rig was available.

Write the stage-03 receipt with commands, measured results and inspected artifacts. Update this stage's index status only after its required gates pass.

## Restraints and exclusions

No finger/shoulder animation authoring, general arbitrary-rig support or anatomy changes. Do not substitute global bone Euler rotation for calibrated local flexion. Do not treat legacy shin_elevation as knee angle or hand_roll as every kind of wrist motion. Preserve existing supported rig behavior.

