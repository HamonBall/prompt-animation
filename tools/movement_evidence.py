"""Full-body frame evidence for the shared movement preview tests."""
import math
import json


def render(h,p,out,side=False,width=128):
    import bpy
    import numpy as np
    from mathutils import Vector
    from avatar_app.blender import rig_profile as rp
    from avatar_app.movement_library.compiler import value_error
    scene=h.scene;scene.frame_set(1)
    scene.render.engine='BLENDER_WORKBENCH';scene.display.shading.light='STUDIO';scene.display.shading.color_type='MATERIAL'
    scene.view_settings.view_transform='Standard';scene.render.resolution_percentage=100
    scene.render.resolution_x=width;scene.render.resolution_y=width;scene.render.image_settings.file_format='PNG'
    basis=rp.semantic_frame(h,p,'pelvis').to_3x3();focus=Vector((0,0,p.height_m*.52))
    scene.camera.data.type='ORTHO';scene.camera.data.ortho_scale=p.height_m*1.45
    scene.camera.location=focus+(basis.col[0] if side else basis.col[1])*4
    scene.camera.rotation_euler=(focus-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    count=scene.frame_end;columns=12;rows=math.ceil(count/columns)
    expected=json.loads((out/'result.json').read_text())['samples']
    controls={v.id:v for v in p.controls}
    sheet=np.zeros((rows*width,columns*width,4),dtype=np.float32);sheet[:,:,3]=1
    label='side' if side else 'front';frames=out/label;frames.mkdir(exist_ok=True)
    for previous in frames.glob('*.png'):
        if previous.stem.isdigit() and int(previous.stem)>count:previous.unlink()
    for index in range(count):
        scene.frame_set(index+1)
        for id in expected[index]['targets']:
            spec=controls[id]
            if spec.value_shape=='scalar':actual=rp.measure_joint_angle(h,p,id)
            else:
                frame=rp.semantic_frame(h,p,id.split('.')[0])
                actual=tuple(frame.translation if spec.value_shape=='vector' else frame.to_quaternion())
            saved=expected[index]['measured'][id];saved=tuple(saved) if isinstance(saved,list) else saved
            assert value_error(actual,saved,spec.value_shape)<.001,('Saved action playback',out,index+1,id)
        path=frames/f'{index+1:04d}.png';scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)
        image=bpy.data.images.load(str(path),check_existing=False);pixels=np.array(image.pixels[:]).reshape((width,width,4))
        x=index%columns*width;y=(rows-1-index//columns)*width;sheet[y:y+width,x:x+width]=pixels;bpy.data.images.remove(image)
    image=bpy.data.images.new(label,columns*width,rows*width,alpha=True);image.pixels.foreach_set(sheet.ravel());image.save_render(str(out/(label+'-sheet.png')),scene=scene);bpy.data.images.remove(image)
    scene.frame_set(1)
