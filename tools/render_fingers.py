"""Read-only saved-action views, shared rendering and verified lossless storage."""
import sys,json,time,shutil
from pathlib import Path
import bpy
from mathutils import Vector,Quaternion
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.movement_library import contracts as c
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.storage_policy import enforce
from tools.movement_evidence import render
from tools.lossless_evidence import encode_view,retire_pngs,recover_evidence
OUT=ROOT/'artifacts/stages/05.3b';name=sys.argv[sys.argv.index('--case')+1];out=OUT/'mixamo'/name


def isolated_surface(h,p,side):
    """Display only existing weighted hand faces, using evaluated source vertices.

    Source geometry, weights, rig and saved action are never modified. Full-body
    views retain the complete mesh. This removes neutral thigh occlusion only.
    """
    names={j.source_bones[0] for j in p.rest_to_semantic_mappings if j.semantic_id==side+'.wrist' or j.semantic_id.startswith(side+'.finger.')}
    displays=[];hidden=[]
    for source in h.objects:
        if source.type!='MESH':continue
        hidden.append((source,source.hide_render));source.hide_render=True
        if not source.vertex_groups:continue  # Floor can occlude below-floor hand cameras.
        groups={g.index for g in source.vertex_groups if g.name in names}
        selected={v.index for v in source.data.vertices if sum(g.weight for g in v.groups if g.group in groups)>=.3}
        faces=[tuple(face.vertices) for face in source.data.polygons if all(index in selected for index in face.vertices)]
        if not faces:continue
        indices=sorted({index for face in faces for index in face});lookup={index:i for i,index in enumerate(indices)}
        mesh=bpy.data.meshes.new('Evidence existing '+side+' hand faces')
        mesh.from_pydata([source.data.vertices[index].co for index in indices],[],[tuple(lookup[index] for index in face) for face in faces])
        for face in mesh.polygons:face.use_smooth=True
        obj=bpy.data.objects.new(mesh.name,mesh);h.scene.collection.objects.link(obj);obj.matrix_world=source.matrix_world
        for material in source.data.materials:mesh.materials.append(material)
        displays.append((source,obj,indices))
    assert displays,'Hand surface has no existing weighted faces'
    def update():
        graph=bpy.context.evaluated_depsgraph_get()
        for source,obj,indices in displays:
            evaluated=source.evaluated_get(graph);mesh=evaluated.to_mesh()
            try:obj.data.vertices.foreach_set('co',[value for index in indices for value in mesh.vertices[index].co])
            finally:evaluated.to_mesh_clear()
            obj.data.update()
    def cleanup():
        for source,obj,indices in displays:
            mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(mesh)
        for source,previous in hidden:source.hide_render=previous
    return update,cleanup


def visible_frames(folder,frames):
    """Reject empty/occluded detail images; generation alone is not review."""
    import numpy as np
    minimum_contrast=minimum_std=float('inf');minimum_pixels=10**9
    for frame in frames:
        image=bpy.data.images.load(str(folder/(str(frame).zfill(4)+'.png')),check_existing=False)
        try:
            pixels=np.array(image.pixels[:]).reshape((-1,4));luma=pixels[:,:3].mean(axis=1)
            contrast=float(luma.max()-luma.min());std=float(luma.std());foreground=int((luma>float(np.median(luma))+.05).sum())
            assert contrast>.08 and std>.005 and foreground>=32,('Hand view empty or occluded',folder,frame,contrast,std,foreground)
            minimum_contrast=min(minimum_contrast,contrast);minimum_std=min(minimum_std,std);minimum_pixels=min(minimum_pixels,foreground)
        finally:bpy.data.images.remove(image)
    return {'passed':True,'frames':len(frames),'minimum_luminance_contrast':minimum_contrast,
            'minimum_luminance_std':minimum_std,'minimum_foreground_pixels':minimum_pixels}


with store.producer_lease(out):
    recover_evidence(out);manifest,asset,motion=validate_manifest(out)
    assert manifest['inputs']==store.input_identity(out),'Stale numeric evidence'
    result=json.loads((out/'result.json').read_text());p=c.loads(c.AvatarProfile,(out.parent/'profile.json').read_text())
    before=(store.digest(motion),motion.stat().st_mtime_ns);h=store.open_preview(out)
    entry=c.loads(c.MotionStateSnapshot,(out/'entry.json').read_text());basis=Quaternion(entry.root_transform.orientation).to_matrix()
    instance=c.loads(c.MovementInstance,(out/'instance.json').read_text());params={x.name:x.value for x in instance.parameters}
    sides=('left','right') if params['side']=='both' else (params['side'],)
    views=dict(manifest['views']);timings={};plans=[]
    for label in ('front','side',*(side+'-'+angle for side in sides for angle in ('palm','edge'))):
        started=time.perf_counter();detail=label not in ('front','side');side_view=label=='side'
        if manifest.get('complete') and store.files_complete(out,manifest) and label in views:
            if not detail or views[label].get('renderer_sha256')==store.digest(Path(__file__)):continue
        scratch=out/'.scratch'/'camera';scratch.mkdir(parents=True,exist_ok=True)
        shutil.copy2(out/'result.json',scratch/'result.json')
        if detail:
            side,angle=label.split('-');values={x.control_id:x.value for x in entry.measured_controls}
            update_surface,cleanup_surface=isolated_surface(h,p,side)
            wrist=Vector(values[side+'.hand.position']);q=Quaternion(values[side+'.hand.orientation'])
            forward=q @ Vector((0,1,0));normal=q @ Vector((0,0,1));radial=forward.cross(normal).normalized()
            points=[Vector(sample['finger_tips'][side+'.finger.'+digit+'.3']) for sample in result['samples']
                    for digit in ('thumb','index','middle','ring','pinky')]
            center=(sum(points,Vector())/len(points)+wrist)/2
            scale=max((point-center).length for point in [wrist,*points])*2.6
            direction=(normal+radial*.35+forward*.2).normalized() if angle=='palm' else (radial+normal*.3+forward*.2).normalized()
            def observe(scene,*unused):
                if scene!=h.scene:return
                scene.camera.data.ortho_scale=scale
                scene.camera.location=center+direction*4
                scene.camera.rotation_euler=(center-scene.camera.location).to_track_quat('-Z','Y').to_euler()
                update_surface()
            bpy.app.handlers.frame_change_post.append(observe)
        try:record=render(h,p,scratch,side_view,width=192 if detail else 128)
        finally:
            if detail:
                bpy.app.handlers.frame_change_post.remove(observe);cleanup_surface()
        source='side' if side_view else 'front';destination=out/label
        if detail:record['visibility_check']=visible_frames(scratch/source,manifest['expected_frames'])
        if destination.exists():assert not any(destination.iterdir());destination.rmdir()
        (scratch/source).rename(destination);(scratch/(source+'-sheet.png')).replace(out/(label+'-sheet.png'))
        (scratch/'result.json').unlink();scratch.rmdir()
        media,plan=encode_view(out,label,manifest['expected_frames'],fps=manifest['fps'],fps_base=manifest['fps_base'])
        record.update(media=media,renderer_sha256=store.digest(Path(__file__)),framing='isolated existing deformed weighted hand faces; environment hidden; all five fingertip trajectories' if detail else 'full body')
        views[label]=record;plans.append(plan);timings[label]=time.perf_counter()-started
    h.scene.frame_set(1);store.write_manifest(out,h.scene,views=views,complete=True);retire_pngs(out,plans)
    assert before==(store.digest(motion),motion.stat().st_mtime_ns)
    store.atomic_json(out/'render-timing.json',{'seconds_by_view':timings,'rendered_frames':len(views)*len(manifest['expected_frames'])})
    enforce(out);print('FINGERS_RENDER_PASSED',name,timings,flush=True)
