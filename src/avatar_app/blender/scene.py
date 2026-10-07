import bpy
from mathutils import Vector


def prepare_preview(handle):
    scene = handle.scene
    scene.world = bpy.data.worlds.new('Avatar Studio World')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.12, 0.12, 0.12, 1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.6
    forward = (handle.rig.matrix_world.to_3x3() @ handle.forward).normalized()
    focus = Vector((0, 0, 0.95))
    camera_data = bpy.data.cameras.new('Avatar Camera')
    camera = bpy.data.objects.new('Avatar Camera', camera_data)
    scene.collection.objects.link(camera)
    camera.location = focus + forward * 4.5 + Vector((1.3, 0, 0.35))
    camera.rotation_euler = (focus - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.lens = 48
    scene.camera = camera
    handle.objects.append(camera)
    for name, offset, energy, size in (
        ('Key', Vector((2, -3, 4)), 650, 4),
        ('Fill', Vector((-3, 2, 3)), 450, 3),
    ):
        data = bpy.data.lights.new('Avatar ' + name, 'AREA')
        data.energy = energy
        data.shape = 'DISK'
        data.size = size
        obj = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(obj)
        handle.objects.append(obj)
        obj.location = offset
        obj.rotation_euler = (focus - offset).to_track_quat('-Z', 'Y').to_euler()
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 800
    scene.render.resolution_y = 800
    scene.render.resolution_percentage = 100
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                space.shading.type = 'MATERIAL'
                space.shading.use_scene_world = True
                space.shading.use_scene_lights = True
                space.region_3d.view_perspective = 'CAMERA'
                space.show_region_ui = True
