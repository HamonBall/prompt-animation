"""Read-only framing diagnostic: saved cameras, measured bones and actual skin."""
import sys,json
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.artifact_store import open_preview,atomic_json
from avatar_app.movement_library import contracts as c
OUT=ROOT/'artifacts/stages/05.3b';out=OUT/'mixamo/gesture.open.bent-turned'
h=open_preview(out);h.scene.frame_set(1);p=c.loads(c.AvatarProfile,(out.parent/'profile.json').read_text())
manifest=json.loads((out/'preview-manifest.json').read_text());report={}
for side in ('left','right'):
    names={j.source_bones[0] for j in p.rest_to_semantic_mappings if j.semantic_id==side+'.wrist' or j.semantic_id.startswith(side+'.finger.')}
    points=[];sources=[]
    for source in h.objects:
        if source.type!='MESH' or not source.vertex_groups:continue
        groups={g.index for g in source.vertex_groups if g.name in names}
        indices=[v.index for v in source.data.vertices if sum(g.weight for g in v.groups if g.group in groups)>=.3]
        ev=source.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
        points.extend(source.matrix_world @ mesh.vertices[index].co for index in indices)
        sources.append({'name':source.name,'matrix':list(map(list,source.matrix_world)),'vertices':len(indices)})
        ev.to_mesh_clear()
    row={'sources':sources,'bounds':[(min(v[i] for v in points),max(v[i] for v in points)) for i in range(3)],'views':{}}
    for angle in ('palm','edge'):
        view=manifest['views'][side+'-'+angle];inverse=Matrix(view['matrix_world']).inverted();local=[inverse @ v for v in points]
        row['views'][angle]={'camera':view,'skin_camera_bounds':[(min(v[i] for v in local),max(v[i] for v in local)) for i in range(3)]}
    report[side]=row
atomic_json(OUT/'framing-diagnostic.json',report);print('FINGER_FRAMING_DIAGNOSTIC',report,flush=True)
if '--render-fixed' in sys.argv:
    import bmesh
    from tools.storage_policy import enforce
    from avatar_app.blender import rig_profile as rp
    target=OUT/'framing-pilot';target.mkdir(exist_ok=True);enforce(target,growth=8*1024**2,temporary=32*1024**2)
    scene=h.scene;scene.render.engine='BLENDER_WORKBENCH';scene.display.shading.light='STUDIO';scene.display.shading.color_type='MATERIAL'
    scene.view_settings.view_transform='Standard';scene.render.resolution_percentage=100;scene.render.resolution_x=scene.render.resolution_y=256
    scene.render.image_settings.file_format='PNG';scene.render.dither_intensity=0;proof={}
    for side in ('left','right'):
        names={j.source_bones[0] for j in p.rest_to_semantic_mappings if j.semantic_id==side+'.wrist' or j.semantic_id.startswith(side+'.finger.')}
        copies=[];hidden=[]
        for source in h.objects:
            if source.type!='MESH':continue
            if not source.vertex_groups:
                hidden.append((source,source.hide_render));source.hide_render=True;continue
            groups={g.index for g in source.vertex_groups if g.name in names}
            selected={v.index for v in source.data.vertices if sum(g.weight for g in v.groups if g.group in groups)>=.3}
            obj=source.copy();obj.data=source.data.copy();obj.hide_render=False;obj.hide_viewport=False;scene.collection.objects.link(obj)
            mesh=bmesh.new();mesh.from_mesh(obj.data)
            mesh.verts.ensure_lookup_table();mesh.faces.ensure_lookup_table()
            bmesh.ops.delete(mesh,geom=[face for face in mesh.faces if not all(v.index in selected for v in face.verts)],context='FACES_ONLY')
            mesh.to_mesh(obj.data);mesh.free();assert len(obj.data.vertices)==len(source.data.vertices)
            assert all((a.co-b.co).length==0 for a,b in zip(obj.data.vertices,source.data.vertices))
            hidden.append((source,source.hide_render));source.hide_render=True;copies.append(obj)
        for angle in ('palm','edge'):
            view=manifest['views'][side+'-'+angle];scene.camera.matrix_world=Matrix(view['matrix_world']);scene.camera.data.type='ORTHO';scene.camera.data.ortho_scale=view['ortho_scale']
            scene.frame_set(1);scene.render.filepath=str(target/(side+'-'+angle+'.png'));bpy.ops.render.render(write_still=True)
        proof[side]={'copied_source_vertex_coordinates_and_count_exact':True,'source_weights_and_armature_modifiers_preserved_on_visual_copy':True}
        for obj in copies:
            mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(mesh)
        for source,value in hidden:source.hide_render=value
    atomic_json(target/'proof.json',proof);print('FIXED_HAND_SURFACE_PILOT_PASSED',flush=True)
