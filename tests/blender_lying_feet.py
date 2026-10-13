"""Sitting and lying must keep the same neutral ankle angle as standing."""
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar_app.blender.avatar import import_avatar, discard_avatar
from avatar_app.blender.pose import target_pose, ground_pose
from avatar_app.blender.scene import prepare_preview
from avatar_app.pose import PosePlan
from avatar_app.planning.movements import floor_sitting_plan, lying_down_plan

original_scene = bpy.context.scene
for filename in ('Hip Hop Andrejs.fbx', 'Hip Hop Mixamo.fbx'):
    handle = import_avatar(str(ROOT / filename))
    target_pose(handle, PosePlan())
    rest = {side: (handle.bones[side + 'Leg'].matrix.to_quaternion().conjugated()
                   @ handle.bones[side + 'Foot'].matrix.to_quaternion())
            for side in ('Left', 'Right')}
    for plan in (floor_sitting_plan(), lying_down_plan()):
        target_pose(handle, plan.final_pose)
        for side in rest:
            ankle = (handle.bones[side + 'Leg'].matrix.to_quaternion().conjugated()
                     @ handle.bones[side + 'Foot'].matrix.to_quaternion())
            assert ankle.rotation_difference(rest[side]).angle < .01, (filename, side, plan.description)
        print('NEUTRAL_ANKLE_PRESERVED', filename, plan.description, flush=True)
    if '--render' in sys.argv and filename == 'Hip Hop Andrejs.fbx':
        prepare_preview(handle)
        ground_pose(handle)
        from mathutils import Vector
        camera = handle.scene.camera
        focus = handle.rig.matrix_world @ handle.bones['Hips'].head
        right = (handle.rig.matrix_world.to_3x3() @ handle.right).normalized()
        camera.location = focus + right * 3.5 + Vector((0, 0, .25))
        camera.rotation_euler = (focus - camera.location).to_track_quat('-Z', 'Y').to_euler()
        handle.scene.render.filepath = str(ROOT / 'artifacts' / 'motion' / 'lying-feet-fixed.png')
        bpy.ops.render.render(write_still=True)
    bpy.context.window.scene = original_scene
    discard_avatar(handle)
print('ALL_LYING_FOOT_CHECKS_PASSED', flush=True)
