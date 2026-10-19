"""Original procedural try-out character; no downloaded or personal assets."""
import bpy
from mathutils import Vector
from .avatar import AvatarHandle


def create_demo_avatar():
    scene = bpy.data.scenes.new('Avatar Preview')
    bpy.context.window.scene = scene
    data = bpy.data.armatures.new('Demo Skeleton')
    rig = bpy.data.objects.new('Built-in Avatar', data)
    rig['avatar_reference'] = 'procedural-demo-v1'
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    specs = [('Hips', (0, 0, .98), (0, 0, 1.10), None),
             ('Spine', (0, 0, 1.10), (0, 0, 1.22), 'Hips'),
             ('Spine1', (0, 0, 1.22), (0, 0, 1.34), 'Spine'),
             ('Spine2', (0, 0, 1.34), (0, 0, 1.46), 'Spine1'),
             ('Head', (0, 0, 1.50), (0, 0, 1.73), 'Spine2')]
    for side, sign in (('Left', -1), ('Right', 1)):
        specs += [(side+'Arm', (sign*.18, 0, 1.42), (sign*.43, 0, 1.42), 'Spine2'),
                  (side+'ForeArm', (sign*.43, 0, 1.42), (sign*.68, 0, 1.42), side+'Arm'),
                  (side+'Hand', (sign*.68, 0, 1.42), (sign*.78, 0, 1.42), side+'ForeArm'),
                  (side+'UpLeg', (sign*.10, 0, .94), (sign*.10, 0, .51), 'Hips'),
                  (side+'Leg', (sign*.10, 0, .51), (sign*.10, 0, .08), side+'UpLeg'),
                  (side+'Foot', (sign*.10, 0, .08), (sign*.10, .18, .06), side+'Leg')]
    for name, head, tail, parent in specs:
        bone = data.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        if parent:
            bone.parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    objects = [rig]
    colors = {}
    for name, color in [('Body', (.15, .42, .65, 1)), ('Joints', (.08, .18, .25, 1)),
                        ('Face', (.72, .48, .28, 1)), ('Eyes', (.025, .035, .05, 1))]:
        material = bpy.data.materials.new('Demo ' + name)
        material.diffuse_color = color
        material.use_nodes = True
        material.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = color
        material.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = .65
        colors[name] = material
    def shape(name, bone_name, center, scale, color='Body', direction=None):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, location=center)
        obj = bpy.context.object
        obj.name = name
        obj.scale = scale
        if direction:
            obj.rotation_mode = 'QUATERNION'
            obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(direction.normalized())
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(colors[color])
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        group = obj.vertex_groups.new(name=bone_name)
        group.add(list(range(len(obj.data.vertices))), 1, 'REPLACE')
        modifier = obj.modifiers.new('Skeleton', 'ARMATURE')
        modifier.object = rig
        obj.parent = rig
        objects.append(obj)
    for name, head, tail, _ in specs:
        if name.startswith('Spine') or name == 'Hips':
            continue
        head, tail = Vector(head), Vector(tail)
        radius = .075 if 'Leg' in name else .047
        if name == 'Head':
            shape('Head', name, (0, 0, 1.62), (.14, .12, .17), 'Face')
        elif name.endswith('Foot'):
            shape(name, name, (head.x, .075, .045), (.07, .14, .045), 'Joints')
        else:
            shape(name, name, (head + tail) / 2, (radius, radius, (tail-head).length/2 + radius*.2),
                  direction=tail-head)
            shape(name+' joint', name, head, (radius,)*3, 'Joints')
    shape('Pelvis', 'Hips', (0, 0, .99), (.19, .12, .13))
    shape('Torso', 'Spine1', (0, 0, 1.27), (.20, .12, .23))
    for x in (-.05, .05):
        shape('Eye', 'Head', (x, .113, 1.65), (.018, .018, .022), 'Eyes')
    bpy.context.view_layer.update()
    bones = {name: rig.pose.bones[name] for name, *_ in specs}
    return AvatarHandle(scene, rig, bones, 1.65, Vector((0,0,1)), Vector((0,1,0)),
                        Vector((1,0,0)), objects)
