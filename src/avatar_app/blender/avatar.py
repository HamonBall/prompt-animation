from dataclasses import dataclass
from pathlib import Path
import re
import bpy
from mathutils import Vector


REQUIRED = ('Hips', 'Spine', 'Head', 'LeftArm', 'LeftForeArm', 'LeftHand',
            'RightArm', 'RightForeArm', 'RightHand', 'LeftUpLeg', 'LeftLeg',
            'LeftFoot', 'RightUpLeg', 'RightLeg', 'RightFoot')


@dataclass
class AvatarHandle:
    scene: object
    rig: object
    bones: dict
    height: float
    up: Vector
    forward: Vector
    right: Vector
    objects: list


def import_avatar(path: str) -> AvatarHandle:
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != '.fbx':
        raise ValueError('Choose an existing Mixamo-rigged .fbx file.')
    previous = bpy.context.window.scene if bpy.context.window else bpy.context.scene
    scene = bpy.data.scenes.new('Avatar Preview')
    # Import operators use the current window's scene, including background mode.
    bpy.context.window.scene = scene
    before = set(bpy.data.objects)
    try:
        bpy.ops.import_scene.fbx(filepath=str(path), use_anim=False,
                                 use_image_search=True, automatic_bone_orientation=False)
        objects = list(set(bpy.data.objects) - before)
        rigs = [obj for obj in objects if obj.type == 'ARMATURE']
        if len(rigs) != 1:
            raise ValueError('Expected exactly one armature in the FBX.')
        rig = rigs[0]
        names = {}
        for bone in rig.pose.bones:
            key = re.sub(r'[^a-z0-9]', '', bone.name.lower().split(':')[-1])
            key = key.removeprefix('mixamorig')
            if key in names:
                raise ValueError(f'Ambiguous bone mapping: {key}')
            names[key] = bone
        missing = [name for name in REQUIRED if name.lower() not in names]
        if missing:
            raise ValueError('Unsupported rig; missing: ' + ', '.join(missing))
        bones = {name: names[name.lower()] for name in REQUIRED}
        for name in ('Spine1', 'Spine2', 'Neck'):
            if name.lower() in names:
                bones[name] = names[name.lower()]
        for obj in objects:
            obj.animation_data_clear()
        for bone in rig.pose.bones:
            bone.matrix_basis.identity()
        bpy.context.view_layer.update()
        # Normalize the whole imported hierarchy together; meshes and materials stay intact.
        root = bpy.data.objects.new('Avatar Scale', None)
        scene.collection.objects.link(root)
        for obj in objects:
            if obj.parent is None:
                world = obj.matrix_world.copy()
                obj.parent = root
                obj.matrix_world = world
        anatomical_up = (rig.matrix_world.to_3x3()
                         @ (bones['Head'].head - bones['Hips'].head)).normalized()
        root.rotation_mode = 'QUATERNION'
        root.rotation_quaternion = anatomical_up.rotation_difference(Vector((0, 0, 1)))
        bpy.context.view_layer.update()
        mesh_points = [obj.matrix_world @ Vector(corner) for obj in objects
                       if obj.type == 'MESH' for corner in obj.bound_box]
        if not mesh_points:
            raise ValueError('No avatar mesh was found.')
        low = min(p.z for p in mesh_points)
        high = max(p.z for p in mesh_points)
        if high - low < 1e-6:
            raise ValueError('The avatar has no measurable height.')
        factor = 1.8 / (high - low)
        root.scale = (factor,) * 3
        root.location.z = -low * factor
        bpy.context.view_layer.update()
        up = (rig.matrix_world.inverted().to_3x3() @ Vector((0, 0, 1))).normalized()
        right = (bones['RightArm'].head - bones['LeftArm'].head).normalized()
        forward = up.cross(right).normalized()
        height = (bones['Head'].tail - bones['LeftFoot'].head).dot(up)
        if height <= 0:
            raise ValueError('Cannot determine a humanoid standing height.')
        return AvatarHandle(scene, rig, bones, height, up, forward, right, objects + [root])
    except Exception:
        bpy.context.window.scene = previous
        for obj in list(set(bpy.data.objects) - before):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)
        raise


def discard_avatar(handle):
    for obj in handle.objects:
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.scenes.remove(handle.scene)
