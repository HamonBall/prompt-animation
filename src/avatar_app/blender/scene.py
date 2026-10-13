import bpy
import math
from mathutils import Vector
from ..motion import Surface
from .geometry import rest_foot_rear


PREVIEW_FLOOR_SIZE = 5.0


def surface_material(name, color):
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    material.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = color
    return material


def resolve_seat(handle, height=.45, enabled=True):
    """Create a real preview surface and return its plain-data constraint bounds."""
    for obj in list(handle.environment):
        if obj.get('avatar_seat'):
            handle.environment.remove(obj)
            bpy.data.objects.remove(obj, do_unlink=True)
    if not enabled:
        handle.surfaces = (Surface(),)
        return handle.surfaces
    forward = (handle.rig.matrix_world.to_3x3() @ handle.forward).normalized()
    origin = handle.rig.matrix_world @ handle.bones['Hips'].bone.head_local
    foot_back = min(((handle.rig.matrix_world @ handle.bones[side+'Foot'].bone.head_local)-origin).dot(forward)
                    for side in ('Left', 'Right'))
    shoe_back = rest_foot_rear(handle, origin, forward)
    if not math.isfinite(shoe_back):
        shoe_back = foot_back - .10
    forward_extent = .30*abs(forward.x) + .225*abs(forward.y)
    distance = max(.32, -shoe_back + forward_extent + .035)
    center = origin - forward * distance
    bpy.ops.mesh.primitive_cube_add(size=1, location=(center.x, center.y, height - .025))
    seat = bpy.context.object
    seat.name = 'Preview seat'
    seat.scale = (.60, .45, .05)
    seat['avatar_seat'] = True
    seat.data.materials.append(surface_material('Seat', (.25, .31, .36, 1)))
    handle.environment.append(seat)
    # Legs make the surface read as a chair rather than a floating platform.
    for dx, dy in ((-.24,-.18), (-.24,.18), (.24,-.18), (.24,.18)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(center.x+dx, center.y+dy, height/2))
        leg = bpy.context.object
        leg.name = 'Seat leg'
        leg.scale = (.035, .035, height)
        leg['avatar_seat'] = True
        leg.data.materials.append(seat.data.materials[0])
        handle.environment.append(leg)
    handle.surfaces = (Surface(), Surface('seat', height, (center.x, center.y), (.60, .45)))
    return handle.surfaces


def prepare_preview(handle):
    scene = handle.scene
    scene.world = bpy.data.worlds.new('Avatar Studio World')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.12, 0.12, 0.12, 1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.6
    bpy.ops.mesh.primitive_plane_add(size=PREVIEW_FLOOR_SIZE, location=(0, 0, -.002))
    floor = bpy.context.object
    floor.name = 'Preview floor'
    floor.data.materials.append(surface_material('Floor', (.10, .13, .16, 1)))
    handle.environment.append(floor)
    handle.surfaces = (Surface(),)
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
                # Workbench displays the avatar textures without continuously
                # running Eevee lighting and shadows while editing or playing.
                space.shading.type = 'SOLID'
                space.shading.color_type = 'TEXTURE'
                space.shading.light = 'STUDIO'
                space.shading.use_scene_world = True
                space.shading.use_scene_lights = True
                space.overlay.show_floor = False
                space.overlay.show_axis_x = False
                space.overlay.show_axis_y = False
                space.region_3d.view_perspective = 'CAMERA'
                space.show_region_ui = True
