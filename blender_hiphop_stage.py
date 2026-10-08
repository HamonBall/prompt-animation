"""
Blender Hip-Hop Stage Setup Script
====================================
Run this inside Blender's Text Editor (open the file, then click "Run Script"),
or via command line:
    blender --python blender_hiphop_stage.py
"""

import bpy
import math
import os

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
FBX_PATH_1   = r"C:\work11\Hip Hop Mixamo.fbx"
FBX_SCALE_1  = 1.0     # Mixamo exports in metres

FBX_PATH_2   = r"C:\work11\Hip Hop Andrejs.fbx"
FBX_SCALE_2  = 100.0   # Andrejs export is in centimetres → scale up to match

# Where to place the two dancers on the stage (X, Y)
DANCER_1_POS = (-1.5, 0.0)
DANCER_2_POS = ( 1.5, 0.0)

# Animation playback speed multiplier (1 = normal, 3 = 3× faster, 5 = 5× faster)
ANIMATION_SPEED = 4

# Material colours for both dancers — override the dark FBX-embedded materials
DANCER1_COLOR = (0.75, 0.75, 0.80, 1.0)  # Mixamo  — silver
DANCER2_COLOR = (1.0,  0.78, 0.0,  1.0)  # Andrejs — gold
# ─────────────────────────────────────────────────────────────────────────────


# ── helpers ──────────────────────────────────────────────────────────────────

def clear_scene():
    """Remove everything from the default scene."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    # Remove orphan data
    for block in list(bpy.data.meshes):
        bpy.data.meshes.remove(block)
    for block in list(bpy.data.lights):
        bpy.data.lights.remove(block)
    for block in list(bpy.data.cameras):
        bpy.data.cameras.remove(block)


def make_material(name, color_rgba, roughness=0.8, metallic=0.0):
    """Create or reuse a simple principled-BSDF material."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color_rgba
    bsdf.inputs["Roughness"].default_value  = roughness
    bsdf.inputs["Metallic"].default_value   = metallic
    # Solid-view uses diffuse_color (Viewport Display), not the BSDF node
    mat.diffuse_color = color_rgba
    return mat


def assign_material(obj, mat):
    """Assign a material to an object, replacing any existing slots."""
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def add_object_to_collection(obj, col):
    if obj.name not in col.objects:
        col.objects.link(obj)
    if obj.name in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.unlink(obj)


# ── scene structure ──────────────────────────────────────────────────────────

def build_collections():
    scene_col = bpy.context.scene.collection
    stage_col   = bpy.data.collections.new("Stage")
    dancers_col = bpy.data.collections.new("Dancers")
    lights_col  = bpy.data.collections.new("Lights")
    scene_col.children.link(stage_col)
    scene_col.children.link(dancers_col)
    scene_col.children.link(lights_col)
    return stage_col, dancers_col, lights_col


# ── stage ────────────────────────────────────────────────────────────────────

def build_stage(stage_col):
    """
    Simple raised platform made from a flat box.
    Dimensions: 5 m wide  x  3 m deep  x  0.2 m tall
    Top surface sits at Z = 0 so dancers stand at ground level.
    """
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -0.1))
    stage = bpy.context.active_object
    stage.name = "Stage_Platform"
    stage.scale = (5.0, 1.5, 0.1)   # doubled width: 10 m wide x 3 m deep x 0.2 m tall
    bpy.ops.object.transform_apply(scale=True)

    mat = make_material("Stage_Floor",
                        color_rgba=(0.55, 0.02, 0.08, 1.0),   # deep red
                        roughness=0.6, metallic=0.15)
    assign_material(stage, mat)
    add_object_to_collection(stage, stage_col)

    # ── backdrop wall ──
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -1.6, 1.25))
    wall = bpy.context.active_object
    wall.name = "Stage_Backdrop"
    wall.scale = (5.0, 0.05, 1.25)   # same doubled width
    bpy.ops.object.transform_apply(scale=True)

    mat_wall = make_material("Stage_Backdrop_Mat",
                             color_rgba=(0.04, 0.01, 0.18, 1.0),   # deep purple
                             roughness=0.85)
    assign_material(wall, mat_wall)
    add_object_to_collection(wall, stage_col)

    # ── Hip-Hop text on the backdrop ──
    bpy.ops.object.text_add(location=(0.0, -1.55, 1.35))
    txt = bpy.context.active_object
    txt.name = "Backdrop_HipHop_Text"
    txt.data.body        = "HIP HOP"
    txt.data.align_x     = 'CENTER'
    txt.data.size        = 0.55
    txt.data.extrude     = 0.04          # slight 3-D depth
    txt.data.bevel_depth = 0.01          # rounded edges on letters
    txt.rotation_euler   = (math.radians(90), 0, 0)   # stand upright
    txt.scale.x          = -1.0    # flip X so the back face reads correctly from camera

    mat_txt = make_material("Text_Gold",
                            color_rgba=(1.0, 0.78, 0.0, 1.0),   # gold
                            roughness=0.15, metallic=0.95)
    # Add a subtle emission so letters glow even in dim light
    mat_txt.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value  = (1.0, 0.78, 0.0, 1.0)
    mat_txt.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 1.5
    txt.data.materials.append(mat_txt)
    add_object_to_collection(txt, stage_col)

    # ── floor under stage ──
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, -0.205))
    floor = bpy.context.active_object
    floor.name = "Floor"
    mat_floor = make_material("Floor_Mat",
                              color_rgba=(0.08, 0.08, 0.08, 1.0),
                              roughness=0.95)
    assign_material(floor, mat_floor)
    add_object_to_collection(floor, stage_col)

    return stage


# ── lights ───────────────────────────────────────────────────────────────────

def build_lights(lights_col):
    """Three-point lighting rig suited for a small stage."""

    def add_spot(name, location, energy, color=(1, 1, 1), angle_deg=40,
                 target=(0, 0, 0.8)):
        bpy.ops.object.light_add(type='SPOT', location=location)
        light_obj = bpy.context.active_object
        light_obj.name = name
        light = light_obj.data
        light.energy     = energy
        light.color      = color
        light.spot_size  = math.radians(angle_deg)
        light.spot_blend = 0.15
        light.shadow_soft_size = 0.3

        # Point toward target using a 'TRACK_TO' constraint
        constraint = light_obj.constraints.new('TRACK_TO')
        empty = bpy.data.objects.new(name + "_target", None)
        lights_col.objects.link(empty)          # go straight into Lights, not root
        empty.location = target
        constraint.target = empty
        constraint.track_axis = 'TRACK_NEGATIVE_Z'
        constraint.up_axis    = 'UP_Y'

        add_object_to_collection(light_obj, lights_col)
        return light_obj

    # Key light — front-left, warm, lowered to chest height for full-body coverage
    add_spot("Key_Light",
             location=(-3.0, 3.5, 2.0), energy=2000,
             color=(1.0, 0.95, 0.85), angle_deg=70,
             target=(0, 0, 1.0))

    # Fill light — front-right, cooler, symmetric to key
    add_spot("Fill_Light",
             location=( 3.0, 3.5, 2.0), energy=1200,
             color=(0.85, 0.90, 1.0), angle_deg=70,
             target=(0, 0, 1.0))

    # Front-centre light — straight-on at face/torso height, neutral white
    add_spot("Front_Light",
             location=(0.0, 4.0, 1.5), energy=800,
             color=(1.0, 1.0, 1.0), angle_deg=65,
             target=(0, 0, 1.0))

    # Rim / back light — cool blue, creates separation from backdrop
    add_spot("Rim_Light",
             location=(0.0, -3.5, 3.0), energy=600,
             color=(0.5, 0.6, 1.0), angle_deg=55,
             target=(0, 0, 1.2))

    # Ambient world — slightly raised so deep shadows aren't pitch black
    bpy.context.scene.world.use_nodes = True
    bg = bpy.context.scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value    = (0.02, 0.02, 0.04, 1)
    bg.inputs["Strength"].default_value = 0.5


# ── camera ───────────────────────────────────────────────────────────────────

def build_camera():
    bpy.ops.object.camera_add(location=(0, 6.5, 2.2))
    cam = bpy.context.active_object
    cam.name = "Stage_Camera"
    cam.rotation_euler = (math.radians(80), 0, math.radians(180))
    cam.data.lens = 35          # mild wide, good for stage
    bpy.context.scene.camera = cam
    return cam


# ── FBX import ───────────────────────────────────────────────────────────────

def get_view3d_override():
    """
    Find a VIEW_3D area and return a context override dict.
    bpy.ops.import_scene.fbx silently returns CANCELLED when the active area
    is TEXT_EDITOR, so we must redirect it to a 3D viewport.
    Falls back to any area if no VIEW_3D is open.
    """
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return {'window': window, 'screen': window.screen,
                                'area': area, 'region': region}
    # Fallback – use whatever area is available
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            for region in area.regions:
                if region.type == 'WINDOW':
                    return {'window': window, 'screen': window.screen,
                            'area': area, 'region': region}
    return {}


def ensure_fbx_addon():
    """Enable the FBX import/export addon if it is not already active."""
    addon = "io_scene_fbx"
    if addon not in bpy.context.preferences.addons:
        try:
            bpy.ops.preferences.addon_enable(module=addon)
            print(f"  [INFO] Enabled addon: {addon}")
        except Exception as e:
            print(f"  [ERROR] Could not enable FBX addon: {e}")

    if not hasattr(bpy.ops.import_scene, "fbx"):
        print("  [ERROR] bpy.ops.import_scene.fbx is still not available.")
        print("          In Blender → Edit → Preferences → Add-ons,")
        print("          search 'FBX' and enable 'Import-Export: FBX format'.")
        return False
    return True


def import_fbx(path, label, scale=1.0):
    """
    Import a single .fbx and return a list of all objects added by the import.
    'scale' is passed to global_scale (1.0 = metres export, 0.01 = cm export).
    """
    if not os.path.isfile(path):
        print(f"  [ERROR] File not found: {path}  — skipping '{label}'")
        return []

    if not ensure_fbx_addon():
        return []

    before = set(bpy.data.objects.keys())
    print(f"  Scene objects before import: {len(before)}")

    override = get_view3d_override()
    print(f"  Using context area: {override.get('area').type if override.get('area') else 'none'}")

    try:
        with bpy.context.temp_override(**override):
            result = bpy.ops.import_scene.fbx(
                filepath=path,
                use_anim=True,
                global_scale=scale,
                use_image_search=True,
                # Unused FBX metadata can contain unsupported Short properties.
                use_custom_props=False,
                automatic_bone_orientation=True,
            )
        print(f"  Operator result: {result}")
        if 'CANCELLED' in result:
            print("  [ERROR] Import was CANCELLED — check the file path and FBX addon.")
            return []
    except Exception as e:
        print(f"  [ERROR] Import operator raised an exception: {e}")
        return []

    after    = set(bpy.data.objects.keys())
    new_keys = after - before
    print(f"  Scene objects after import: {len(after)}  |  new: {len(new_keys)}")

    if not new_keys:
        print("  [WARNING] No new objects detected after import.")
        return []

    new_objs = [bpy.data.objects[n] for n in new_keys]

    # Rename root objects for easy identification in the outliner
    roots = [o for o in new_objs if o.parent is None]
    for i, root in enumerate(roots):
        root.name = f"{label}_root_{i}"
        print(f"  Root object: {root.name}  loc={root.location[:]}")

    return new_objs


def place_dancer(objects, x, y, stage_z=0.0):
    """
    Move all root objects to (x, y, stage_z) and rotate them to face the camera
    (camera is at +Y, so dancers must face +Y, i.e. rotate 180° around Z).
    """
    roots = [o for o in objects if o.parent is None]
    for root in roots:
        root.location.x = x
        root.location.y = y
        root.location.z = stage_z
        root.rotation_euler.z = math.pi   # turn to face the camera


def route_to_collection(objects, col):
    for obj in objects:
        # Unlink from every current collection first
        for c in list(obj.users_collection):
            try:
                c.objects.unlink(obj)
            except RuntimeError:
                pass  # already unlinked
        # Link into our target collection
        if obj.name not in col.objects:
            col.objects.link(obj)


def clear_custom_normals(objects):
    """
    Remove FBX-baked custom normals and recompute from geometry.
    Fixes the 'lit only from top' bug caused by normals stored in the
    pre-rotation (lying-flat) orientation before the armature's 90° X fix.
    """
    prev_active = bpy.context.view_layer.objects.active
    for obj in objects:
        if obj.type != 'MESH':
            continue
        if not obj.data.has_custom_normals:
            print(f"  '{obj.name}': no custom normals — skipping")
            continue
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
        bpy.ops.object.mode_set(mode='OBJECT')
        print(f"  '{obj.name}': custom normals cleared — recomputed from geometry")
    bpy.context.view_layer.objects.active = prev_active


def apply_material_to_meshes(objects, mat_name, color_rgba,
                              roughness=0.5, metallic=0.2):
    """Assign a solid material to every MESH object in the list."""
    mat = make_material(mat_name, color_rgba, roughness=roughness, metallic=metallic)
    print(f"  apply_material_to_meshes: {len(objects)} objects total")
    for obj in objects:
        print(f"    obj='{obj.name}'  type={obj.type}  mesh_slots={len(obj.material_slots) if obj.type=='MESH' else 'n/a'}")
        if obj.type == 'MESH':
            # Override every existing slot at the object level, then clear mesh-level slots
            for slot in obj.material_slots:
                slot.link     = 'OBJECT'
                slot.material = mat
            obj.data.materials.clear()
            obj.data.materials.append(mat)
            obj.color = color_rgba
            print(f"    → material '{mat_name}' applied, slots now: {len(obj.material_slots)}")


def set_viewport_color_to_material():
    """
    Switch every 3D Viewport to Material Preview with scene lights enabled.
    Uses bpy.context.screen.areas (current screen) for reliability when called
    from the Text Editor, plus iterates all windows as fallback.
    """
    def apply_to_space(space):
        space.shading.type             = 'MATERIAL'
        space.shading.use_scene_lights = True   # use our placed scene lights
        space.shading.use_scene_world  = True   # use our world ambient

    # Primary: current screen (reliable from Text Editor)
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    apply_to_space(space)

    # Fallback: all windows
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        apply_to_space(space)


# ── render settings (optional preview quality) ───────────────────────────────

def setup_render():
    scene = bpy.context.scene
    # Real-time renderer for smooth viewport playback. Blender 5.x exposes this
    # as BLENDER_EEVEE; some older scripts used BLENDER_EEVEE_NEXT.
    engines = {item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items}
    scene.render.engine = 'BLENDER_EEVEE' if 'BLENDER_EEVEE' in engines else 'BLENDER_WORKBENCH'

    if hasattr(scene, "eevee"):
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = 16   # fast preview quality
        if hasattr(scene.eevee, "use_gtao"):
            scene.eevee.use_gtao = True           # ambient occlusion
    scene.render.resolution_x         = 1920
    scene.render.resolution_y         = 1080
    scene.render.fps                  = 30
    scene.render.frame_map_old        = 100                        # Time Remapping:
    scene.render.frame_map_new        = int(100 / ANIMATION_SPEED) # SPEED× faster
    scene.frame_start = 1


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n=== Hip-Hop Stage Builder ===")

    clear_scene()
    stage_col, dancers_col, lights_col = build_collections()

    print("Building stage…")
    build_stage(stage_col)

    print("Setting up lights…")
    build_lights(lights_col)

    print("Placing camera…")
    build_camera()

    print("Setting up render…")
    setup_render()

    print(f"Importing dancer 1 (scale={FBX_SCALE_1}): {FBX_PATH_1}")
    d1_objs = import_fbx(FBX_PATH_1, "Dancer1", scale=FBX_SCALE_1)
    place_dancer(d1_objs, *DANCER_1_POS)
    apply_material_to_meshes(d1_objs, "Mixamo_Mat", DANCER1_COLOR)
    route_to_collection(d1_objs, dancers_col)

    print(f"Importing dancer 2 (scale={FBX_SCALE_2}): {FBX_PATH_2}")
    d2_objs = import_fbx(FBX_PATH_2, "Dancer2", scale=FBX_SCALE_2)
    clear_custom_normals(d2_objs)
    place_dancer(d2_objs, *DANCER_2_POS)
    apply_material_to_meshes(d2_objs, "Andrejs_Mat", DANCER2_COLOR)
    route_to_collection(d2_objs, dancers_col)

    # Switch solid-view colour mode so material colours are visible
    set_viewport_color_to_material()

    # Jump to frame 1 so the viewport shows the start pose
    bpy.context.scene.frame_set(1)

    print("=== Done! ===")
    print(f"  Dancer1 objects in scene: {len(d1_objs)}")
    print(f"  Dancer2 objects in scene: {len(d2_objs)}")
    print("  Press SPACE in the viewport to play the animation.")
    print("  Switch viewport shading to 'Rendered' (Z → Rendered) for full look.")
    print("  Press F12 to render the current frame.")


main()
