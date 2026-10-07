from pathlib import Path
import sys
import bpy
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.animation import build_transition
from avatar_app.blender.scene import prepare_preview
from avatar_app.models import MotionPlan
h = import_avatar(str(Path(__file__).resolve().parents[1] / 'Hip Hop Andrejs.fbx'))
prepare_preview(h)
print('METRICS', h.height, h.up[:], h.forward[:], h.rig.matrix_world)
for phase in ('rest', 'end'):
    if phase == 'end':
        build_transition(h, MotionPlan(crouch=0.11))
        h.scene.frame_set(h.scene.frame_end)
    for name in ('Hips', 'Head', 'LeftFoot', 'LeftHand'):
        print(phase, name, (h.rig.matrix_world @ h.bones[name].head)[:])
    graph = bpy.context.evaluated_depsgraph_get()
    points = [obj.matrix_world @ Vector(c) for obj in h.objects if obj.type == 'MESH'
              for c in obj.evaluated_get(graph).bound_box]
    print(phase, 'bounds', [min(p[i] for p in points) for i in range(3)],
          [max(p[i] for p in points) for i in range(3)])
print('CAMERA', h.scene.camera.location[:], h.scene.camera.rotation_euler[:])
