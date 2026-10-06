"""
FBX Diagnostic Script
Run in Blender (Text Editor → Run Script) to compare the two FBX files.
"""
import bpy
import mathutils
import os

FILES = {
    "Mixamo":  (r"C:\work11\Hip Hop Mixamo.fbx",  1.0),
    "Andrejs": (r"C:\work11\Hip Hop Andrejs.fbx", 100.0),
}

def clear():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

def get_view3d_override():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return {'window': window, 'screen': window.screen,
                                'area': area, 'region': region}
    return {}

def analyse(label, path, scale):
    print(f"\n{'='*60}")
    print(f"  {label}  |  scale={scale}  |  {os.path.basename(path)}")
    print(f"{'='*60}")

    clear()
    before = set(bpy.data.objects.keys())

    override = get_view3d_override()
    with bpy.context.temp_override(**override):
        bpy.ops.import_scene.fbx(
            filepath=path,
            use_anim=True,
            global_scale=scale,
            use_image_search=True,
            automatic_bone_orientation=True,
        )

    new_objs = [bpy.data.objects[n] for n in set(bpy.data.objects.keys()) - before]

    for obj in sorted(new_objs, key=lambda o: o.name):
        print(f"\n  OBJ: '{obj.name}'")
        print(f"    type          : {obj.type}")
        print(f"    location      : {obj.location[:]}")
        print(f"    scale         : {obj.scale[:]}")
        print(f"    rotation_mode : {obj.rotation_mode}")
        print(f"    rotation_euler: {[round(r,4) for r in obj.rotation_euler]}")
        print(f"    parent        : {obj.parent.name if obj.parent else 'None'}")

        if obj.type == 'MESH':
            mesh = obj.data
            print(f"    vertices      : {len(mesh.vertices)}")
            print(f"    polygons      : {len(mesh.polygons)}")
            print(f"    material slots: {len(obj.material_slots)}")
            for i, slot in enumerate(obj.material_slots):
                mat = slot.material
                print(f"      slot {i}: '{mat.name if mat else 'NONE'}'", end="")
                if mat:
                    print(f"  diffuse={[round(c,3) for c in mat.diffuse_color]}", end="")
                    if mat.use_nodes:
                        bsdf = mat.node_tree.nodes.get("Principled BSDF")
                        if bsdf:
                            bc = bsdf.inputs["Base Color"].default_value
                            print(f"  BSDF_base={[round(c,3) for c in bc]}", end="")
                print()

            # Check normals: sample up to 5 polygon normals (calc_normals removed in 4.x)
            print(f"    sample normals (first 5 polys):")
            for i, poly in enumerate(mesh.polygons[:5]):
                n = poly.normal
                print(f"      poly {i}: normal={[round(v,3) for v in n]}")

            # Check if normals face roughly outward (dot with centroid > 0)
            outward = sum(1 for p in mesh.polygons if p.normal.dot(p.center) > 0)
            total   = len(mesh.polygons)
            pct     = (100 * outward // total) if total else 0
            print(f"    normals facing outward: {outward}/{total} ({pct}%)")

        if obj.type == 'ARMATURE':
            arm = obj.data
            print(f"    bones         : {len(arm.bones)}")
            print(f"    pose bones    : {len(obj.pose.bones)}")

for label, (path, scale) in FILES.items():
    analyse(label, path, scale)

print("\n=== Diagnosis complete ===")
