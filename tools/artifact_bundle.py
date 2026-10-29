"""Schema-v2 portable assets + exact baked actions. No builder/model invocation."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import uuid

from tools.storage_policy import ARTIFACTS,MiB,confined,enforce,active_writer


def root_for(directory,root=None):
    directory=Path(os.path.abspath(directory))
    if root is not None:return confined(directory,Path(os.path.abspath(root))),Path(os.path.abspath(root))
    for p in (directory,*directory.parents):
        if p.name=='artifacts':return confined(directory,p),p
    raise ValueError('An explicit artifact bundle root is required')


def json_value(value):
    if hasattr(value,'to_dict'):value=value.to_dict()
    if isinstance(value,dict):return {k:json_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)) or hasattr(value,'to_list'):return [json_value(v) for v in value]
    if value is None or isinstance(value,(bool,str,int,float)):return value
    raise RuntimeError('Unsupported custom state: '+type(value).__name__)


def properties(owner):
    return {k:json_value(owner[k]) for k in owner.keys()}


def transform(owner):
    return {k:json_value(tuple(getattr(owner,k)) if k!='rotation_mode' else owner.rotation_mode)
            for k in ('location','rotation_mode','rotation_quaternion','rotation_euler','rotation_axis_angle','scale')}


def check_supported():
    import bpy
    scene=bpy.context.scene
    if bpy.data.libraries:
        _,bundle_root=root_for(Path(bpy.data.filepath).parent)
        validate_libraries(bundle_root)
    if scene.animation_data:raise RuntimeError('Unsupported animated scene state')
    for obj in scene.objects:
        if obj.constraints or obj.rigid_body or (obj.animation_data and (obj.animation_data.drivers or obj.animation_data.nla_tracks)):
            raise RuntimeError('Unsupported object constraints/drivers/NLA: '+obj.name)
        if obj.type not in ('MESH','ARMATURE','EMPTY','CAMERA','LIGHT'):
            raise RuntimeError('Unsupported object type: '+obj.name)
        if obj.type=='ARMATURE':
            if any(b.constraints for b in obj.pose.bones):raise RuntimeError('Unsupported pose constraints')
        if obj.type=='MESH' and any(m.type!='ARMATURE' for m in obj.modifiers):
            raise RuntimeError('Unsupported mesh modifier')
    for data in (*bpy.data.materials,*bpy.data.worlds,*bpy.data.meshes):
        if getattr(data,'animation_data',None):raise RuntimeError('Unsupported non-object animation: '+data.name)
        if getattr(data,'node_tree',None) and data.node_tree.animation_data:
            raise RuntimeError('Unsupported animated shader state: '+data.name)


def validate_libraries(root):
    import bpy
    from tools.artifact_store import digest
    for library in bpy.data.libraries:
        path=confined(Path(bpy.path.abspath(library.filepath)),root)
        if path.name=='avatar.blend' and path.parent.parent==root/'assets':
            metadata=json.loads((path.parent/'asset.json').read_text(encoding='utf-8'))
            if digest(path)!=metadata['sha256']:raise RuntimeError('Linked asset hash mismatch')
        elif path.name in ('motion.blend','motion.pending.blend'):
            pending=path.parent/'preview-manifest.pending.json'
            _,asset,motion=validate_manifest(path.parent,root=root,manifest_path=pending if pending.exists() else None)
            if motion!=path:raise RuntimeError('Undeclared motion library reference')
        else:raise RuntimeError('Library is outside the bounded asset/motion store: '+str(path))


def capture_state():
    import bpy
    scene=bpy.context.scene;objects={};bindings=[];actions=set()
    for obj in scene.objects:
        value={'type':obj.type,'parent':obj.parent.name if obj.parent else None,
               'parent_type':obj.parent_type,'parent_bone':obj.parent_bone,
               'matrix_parent_inverse':[list(row) for row in obj.matrix_parent_inverse],
               'transform':transform(obj),'properties':properties(obj),
               'visibility':{'hide_render':obj.hide_render,'hide_viewport':obj.hide_viewport,'hide_set':obj.hide_get(),'color':list(obj.color)}}
        if obj.type=='ARMATURE':
            value['bones']={b.name:{'transform':transform(b),'properties':properties(b)} for b in obj.pose.bones}
        if obj.type=='CAMERA':
            value['data']={k:getattr(obj.data,k) for k in ('type','lens','ortho_scale','clip_start','clip_end','shift_x','shift_y','sensor_width','sensor_height','sensor_fit')}
        if obj.type=='LIGHT':
            value['data']={k:json_value(tuple(getattr(obj.data,k)) if k=='color' else getattr(obj.data,k))
                           for k in ('type','energy','color','shape','size','size_y','shadow_soft_size','spot_size','spot_blend','use_shadow') if hasattr(obj.data,k)}
        ad=obj.animation_data
        if ad and ad.action:
            if not ad.action_slot:raise RuntimeError('Missing bound action slot')
            actions.add(ad.action)
            bindings.append({'rig':obj.name,'action':ad.action.name,'slot':ad.action_slot.identifier,
                             'action_blend_type':ad.action_blend_type,'action_extrapolation':ad.action_extrapolation,
                             'action_influence':ad.action_influence})
        objects[obj.name]=value
    if not bindings:raise RuntimeError('No accepted baked action')
    shading=scene.display.shading
    world=None
    if scene.world:
        world={'color':list(scene.world.color),'use_nodes':scene.world.use_nodes,'properties':properties(scene.world),'nodes':{}}
        if scene.world.use_nodes:
            for node in scene.world.node_tree.nodes:
                if getattr(node,'image',None):raise RuntimeError('Unsupported animated/view environment texture')
                world['nodes'][node.name]={'type':node.bl_idname,'inputs':{s.identifier:json_value(list(s.default_value) if hasattr(s.default_value,'__iter__') else s.default_value)
                    for s in node.inputs if hasattr(s,'default_value')}}
    return {'objects':objects,'bindings':bindings,'scene_properties':properties(scene),'world':world,
            'frame_start':scene.frame_start,'frame_end':scene.frame_end,'current_frame':scene.frame_current,
            'subframe':scene.frame_subframe,'fps':scene.render.fps,'fps_base':scene.render.fps_base,
            'camera':scene.camera.name if scene.camera else None,'engine':scene.render.engine,
            'resolution':[scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage],
            'view_transform':scene.view_settings.view_transform,
            'shading':{k:getattr(shading,k) for k in ('light','color_type','show_shadows','show_cavity')}},actions


def static_identity(signature):
    from tools.blender_artifact_worker import hashed
    # Object/camera/pose transforms are restored by the case, not static identity.
    # Geometry signatures include actual UVs/custom normals, weights/materials.
    value={'exact_content_sha256':signature['asset_exact']}
    return signature['asset_exact'],value


def write_library(path,blocks):
    import bpy
    from tools.artifact_store import atomic_replace
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name('.candidate-'+uuid.uuid4().hex+'.blend')
    previous=bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version=0
        bpy.data.libraries.write(str(temporary),set(blocks),fake_user=True,compress=True,path_remap='RELATIVE_ALL')
        if not temporary.is_file() or temporary.stat().st_size<32:raise RuntimeError('Empty library write')
        with bpy.data.libraries.load(str(temporary)) as (source,target):
            if not source.actions and not source.scenes:raise RuntimeError('Invalid saved library')
        with temporary.open('r+b') as stream:os.fsync(stream.fileno())
        atomic_replace(temporary,path)
    finally:
        bpy.context.preferences.filepaths.save_version=previous
        temporary.unlink(missing_ok=True)


def write_bundle(directory,*,root=None,migration=False,original_scene=None,source_signature=None,authorization=None):
    import bpy
    from tools.artifact_store import digest,atomic_json,input_identity
    from tools.blender_artifact_worker import signature
    directory,root=root_for(directory,root)
    if active_writer(directory,root,authorization):raise RuntimeError('Active case writer')
    recover_bundle(directory,root=root,authorization=authorization)
    check_supported()
    state,actions=capture_state()
    before=source_signature or signature();asset_id,static=static_identity(before)
    asset=root/'assets'/asset_id/'avatar.blend';asset_meta=asset.with_name('asset.json')
    # Reserve the measured packed source footprint, bounded independently of RAM.
    packed=sum(len(im.packed_file.data) for im in bpy.data.images if im.packed_file)
    reserve=packed+64*MiB
    budget_root=ARTIFACTS if directory.is_relative_to(ARTIFACTS) else root
    enforce(directory,growth=reserve if not asset.exists() else 8*MiB,temporary=reserve,root=budget_root,migration=migration)
    if asset.exists():
        metadata=json.loads(asset_meta.read_text(encoding='utf-8'))
        if metadata['identity']!=static or metadata['sha256']!=digest(asset):raise RuntimeError('Shared asset hash mismatch')
    else:
        # Remove animation and normalize the rig pose only in this disposable
        # in-memory snapshot. The original files are untouched.
        bpy.ops.file.pack_all()
        for obj in bpy.context.scene.objects:
            obj.animation_data_clear()
            if obj.type=='ARMATURE':
                for bone in obj.pose.bones:bone.matrix_basis.identity()
        scene=bpy.context.scene
        scene.camera=None
        for obj in list(scene.objects):
            if obj.type in ('CAMERA','LIGHT'):
                for collection in list(obj.users_collection):collection.objects.unlink(obj)
        bpy.context.view_layer.update()
        write_library(asset,[bpy.context.scene])
        atomic_json(asset_meta,{'schema_version':2,'asset_id':asset_id,'identity':static,'sha256':digest(asset)})
        # Restore original binding/state before saving exact action libraries.
        restore_state(state,{action.name:action for action in actions})
    if sum(p.stat().st_size for p in (root/'assets').rglob('*') if p.is_file())>512*MiB:
        raise RuntimeError('Shared asset store exceeds 512 MiB')
    motion=directory/'motion.pending.blend'
    directory.mkdir(parents=True,exist_ok=True)
    write_library(motion,actions)
    with bpy.data.libraries.load(str(motion)) as (source,target):
        if source.meshes or source.images or source.armatures or source.materials:
            raise RuntimeError('Motion file unexpectedly embeds avatar data')
    if motion.stat().st_size>8*MiB:raise RuntimeError('Per-case motion budget exceeded')
    old={}
    manifest=directory/'preview-manifest.json'
    if manifest.is_file():old=json.loads(manifest.read_text(encoding='utf-8'))
    value={**old,'schema_version':2,'bundle_root':os.path.relpath(root,directory).replace('\\','/'),
           'asset':{'path':os.path.relpath(asset,directory).replace('\\','/'),'sha256':digest(asset),'content_hash':asset_id},
           'motion':{'path':'motion.pending.blend','sha256':digest(motion)},'state':state,
           'bindings':state['bindings'],'inputs':input_identity(directory),
           'frame_start':state['frame_start'],'frame_end':state['frame_end'],'current_frame':state['current_frame'],
           'fps':state['fps'],'fps_base':state['fps_base'],'complete':False,
           'expected_frames':list(range(state['frame_start'],state['frame_end']+1)),
           'views':old.get('views',{}),'entry':old.get('entry',{}),
           'original_scene':original_scene or old.get('original_scene'),
           'measurements':{'path':'result.json','sha256':digest(directory/'result.json') if (directory/'result.json').exists() else None}}
    profile=directory/'profile.json'
    if not profile.exists():profile=directory.parent/'profile.json'
    if profile.exists():
        record=json.loads(profile.read_text(encoding='utf-8'))
        value['profile']={'path':os.path.relpath(profile,directory).replace('\\','/'),'sha256':digest(profile),
                          'version':record.get('version'),'schema_version':record.get('schema_version')}
    value.pop('scene',None);value.pop('scene_sha256',None)
    if not migration:
        value.pop('verification',None)
        value['original_scene']={'kind':'generated_baked_motion','action_sha256':before['action']['curves_sha256']}
    enforce(directory,growth=0,case_bytes=motion.stat().st_size+len(json.dumps(value)),root=budget_root,migration=migration)
    atomic_json(directory/'preview-manifest.pending.json',value)
    if not migration:value=commit_bundle(directory)
    return value,before


def restore_state(state,actions):
    import bpy
    from mathutils import Matrix
    scene=bpy.context.scene
    for name,value in state['objects'].items():
        if scene.objects.get(name):continue
        if value['type'] not in ('CAMERA','LIGHT','EMPTY'):
            raise RuntimeError('Asset object mapping mismatch: '+name)
        obj=bpy.data.objects.get(name)
        if obj is None:
            data=bpy.data.cameras.new(name) if value['type']=='CAMERA' else (
                 bpy.data.lights.new(name,value['data']['type']) if value['type']=='LIGHT' else None)
            obj=bpy.data.objects.new(name,data)
        scene.collection.objects.link(obj)
    def set_transform(owner,value):
        owner.rotation_mode=value['rotation_mode']
        for key in ('location','rotation_quaternion','rotation_euler','rotation_axis_angle','scale'):setattr(owner,key,value[key])
    for name,value in state['objects'].items():
        obj=scene.objects.get(name)
        if obj is None or obj.type!=value['type']:raise RuntimeError('Asset object mapping mismatch: '+name)
        parent=scene.objects.get(value['parent']) if value['parent'] else None
        obj.parent=parent;obj.parent_type=value['parent_type'];obj.parent_bone=value['parent_bone']
        obj.matrix_parent_inverse=Matrix(value['matrix_parent_inverse'])
        set_transform(obj,value['transform'])
        for key,v in value.get('visibility',{}).items():
            if key=='hide_set':obj.hide_set(v)
            else:setattr(obj,key,v)
        for key in list(obj.keys()):del obj[key]
        for key,v in value['properties'].items():obj[key]=v
        if 'data' in value:
            for key,v in value['data'].items():setattr(obj.data,key,v)
        if 'bones' in value:
            for key,b in value['bones'].items():
                bone=obj.pose.bones.get(key)
                if bone is None:raise RuntimeError('Rest rig version mismatch')
                set_transform(bone,b['transform'])
                for prop in list(bone.keys()):del bone[prop]
                for prop,v in b['properties'].items():bone[prop]=v
        obj.animation_data_clear()
    for binding in state['bindings']:
        obj=scene.objects[binding['rig']];action=actions.get(binding['action'])
        if action is None:raise RuntimeError('Missing saved action: '+binding['action'])
        slot=next((s for s in action.slots if s.identifier==binding['slot']),None)
        if slot is None:raise RuntimeError('Changed/missing saved action slot')
        ad=obj.animation_data_create();ad.action=action;ad.action_slot=slot
        for key in ('action_blend_type','action_extrapolation','action_influence'):setattr(ad,key,binding[key])
    scene.frame_start=state['frame_start'];scene.frame_end=state['frame_end'];scene.render.fps=state['fps'];scene.render.fps_base=state['fps_base']
    scene.camera=scene.objects.get(state['camera']);scene.render.engine=state['engine']
    scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage=state['resolution']
    scene.view_settings.view_transform=state['view_transform']
    world=state.get('world')
    if world is not None:
        if scene.world is None:raise RuntimeError('Asset world mapping missing')
        scene.world.color=world['color'];scene.world.use_nodes=world['use_nodes']
        for key in list(scene.world.keys()):del scene.world[key]
        for key,v in world['properties'].items():scene.world[key]=v
        if world['use_nodes']:
            if set(world['nodes'])!={n.name for n in scene.world.node_tree.nodes}:raise RuntimeError('Unsupported different world node topology')
            for name,value in world['nodes'].items():
                node=scene.world.node_tree.nodes[name]
                if node.bl_idname!=value['type']:raise RuntimeError('Different world shader type')
                for socket in node.inputs:
                    if socket.identifier in value['inputs']:socket.default_value=value['inputs'][socket.identifier]
    for key,v in state['shading'].items():setattr(scene.display.shading,key,v)
    for key in list(scene.keys()):del scene[key]
    for key,v in state['scene_properties'].items():scene[key]=v
    scene.frame_set(state['current_frame'],subframe=state['subframe'])
    bpy.context.view_layer.update()


def validate_manifest(directory,*,root=None,manifest_path=None):
    from tools.artifact_store import digest
    directory,root=root_for(directory,root)
    if manifest_path is None:recover_bundle(directory,root=root)
    m=json.loads((manifest_path or directory/'preview-manifest.json').read_text(encoding='utf-8'))
    if m['schema_version']!=2:raise ValueError('Not a v2 bundle')
    if (directory/m['bundle_root']).resolve()!=root:raise ValueError('Bundle root escape')
    asset=confined(directory/m['asset']['path'],root);motion=confined(directory/m['motion']['path'],root)
    if asset.parent.parent!=root/'assets' or asset.name!='avatar.blend' or asset.parent.name!=m['asset']['content_hash']:
        raise ValueError('Invalid asset reference')
    if motion.parent!=directory or motion.name not in ('motion.blend','motion.pending.blend','motion.previous.blend'):raise ValueError('Motion reference escapes case')
    if digest(asset)!=m['asset']['sha256'] or digest(motion)!=m['motion']['sha256']:raise RuntimeError('Bundle content hash mismatch')
    metadata=json.loads(asset.with_name('asset.json').read_text(encoding='utf-8'))
    if metadata['sha256']!=m['asset']['sha256']:raise RuntimeError('Asset metadata mismatch')
    for reference in (m.get('profile'),m.get('measurements')):
        if reference and reference.get('sha256'):
            dependency=confined(directory/reference['path'],root)
            if digest(dependency)!=reference['sha256']:raise RuntimeError('Evidence/profile hash mismatch')
    return m,asset,motion


def recover_bundle(directory,*,root=None,authorization=None):
    """Reconcile a process death between file and manifest publication.

    The published manifest is the commit record. Before it changes restore the
    previous motion; after it changes finish retiring the previous motion.
    """
    from tools.artifact_store import digest,atomic_replace,atomic_json
    directory,root=root_for(directory,root)
    transaction=directory/'bundle-transaction.json'
    if not transaction.exists():return
    if active_writer(directory,root,authorization):raise RuntimeError('Active interrupted bundle writer')
    record=json.loads(transaction.read_text(encoding='utf-8'))
    if record.get('owner')!='artifact-bundle-v2':raise RuntimeError('Unknown bundle transaction')
    target=directory/'motion.blend';previous=directory/'motion.previous.blend'
    manifest=directory/'preview-manifest.json';pending=directory/'preview-manifest.pending.json'
    current=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else None
    committed=bool(current and current.get('motion',{}).get('sha256')==record['new_sha256'] and
                   target.exists() and digest(target)==record['new_sha256'])
    if previous.exists() and digest(previous)!=record['previous_sha256']:
        raise RuntimeError('Interrupted previous motion changed')
    if committed:
        previous.unlink(missing_ok=True);pending.unlink(missing_ok=True)
    else:
        if target.exists() and digest(target) not in (record['new_sha256'],record['previous_sha256']):
            raise RuntimeError('Interrupted target changed')
        if previous.exists():atomic_replace(previous,target)
        elif record['previous_sha256'] and (not target.exists() or digest(target)!=record['previous_sha256']):
            raise RuntimeError('Previous motion missing during recovery')
        elif not record['previous_sha256']:target.unlink(missing_ok=True)
        if record['old_manifest'] is not None:atomic_json(manifest,record['old_manifest'])
        else:manifest.unlink(missing_ok=True)
    transaction.unlink()


def commit_bundle(directory):
    """Publish a validated candidate; recoverable old motion spans both renames."""
    from tools.artifact_store import atomic_json,atomic_replace,digest
    directory=Path(directory);pending=directory/'preview-manifest.pending.json'
    validate_manifest(directory,manifest_path=pending)
    m=json.loads(pending.read_text(encoding='utf-8'));candidate=directory/m['motion']['path']
    if candidate.name!='motion.pending.blend' or digest(candidate)!=m['motion']['sha256']:
        raise RuntimeError('Pending motion changed before commit')
    target=directory/'motion.blend';previous=directory/'motion.previous.blend';manifest=directory/'preview-manifest.json'
    old=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else None
    transaction={'owner':'artifact-bundle-v2','old_manifest':old,'new_sha256':m['motion']['sha256'],
                 'previous_sha256':digest(target) if target.exists() else None}
    atomic_json(directory/'bundle-transaction.json',transaction)
    if target.exists():atomic_replace(target,previous)
    try:
        atomic_replace(candidate,target);m['motion']['path']='motion.blend'
        atomic_json(manifest,m)
    except Exception:
        if previous.exists():atomic_replace(previous,target)
        if old is not None:atomic_json(manifest,old)
        raise
    if previous.exists():
        if digest(previous)!=transaction['previous_sha256']:raise RuntimeError('Previous motion unexpectedly changed')
        previous.unlink()
    pending.unlink(missing_ok=True);(directory/'bundle-transaction.json').unlink(missing_ok=True)
    return m


def open_bundle(directory,*,root=None,manifest_path=None):
    import bpy
    m,asset,motion=validate_manifest(directory,root=root,manifest_path=manifest_path)
    bpy.ops.wm.open_mainfile(filepath=str(asset),load_ui=False,use_scripts=False)
    with bpy.data.libraries.load(str(motion),link=False) as (source,target):
        if source.meshes or source.images or source.armatures:raise RuntimeError('Motion contains repeated asset payload')
        target.actions=list(source.actions)
    actions={a.name:a for a in target.actions}
    restore_state(m['state'],actions)
    return m


def trajectory(path,*,expected=None):
    """Streaming every-frame bone/object comparison, bounded scratch, no JSON dumps."""
    import bpy
    import math
    from array import array
    scene=bpy.context.scene;objects=sorted(scene.objects,key=lambda x:x.name)
    rigs=[o for o in objects if o.type=='ARMATURE']
    names=[o.name for o in objects]+[r.name+'/'+b.name for r in rigs for b in r.pose.bones]
    current,sub=scene.frame_current,scene.frame_subframe;maximum=0;count=0
    with gzip.open(path,'rb' if expected else 'wb',compresslevel=3) as stream:
        if expected:
            size=struct.unpack('<I',stream.read(4))[0];header=json.loads(stream.read(size))
            if header!={'names':names,'range':[scene.frame_start,scene.frame_end]}:raise RuntimeError('Motion sample layout mismatch')
        else:
            header=json.dumps({'names':names,'range':[scene.frame_start,scene.frame_end]}).encode()
            stream.write(struct.pack('<I',len(header)));stream.write(header)
        for frame in range(scene.frame_start,scene.frame_end+1):
            scene.frame_set(frame)
            values=array('f',[float(v) for o in objects for row in o.matrix_world for v in row]+[
                float(v) for r in rigs for b in r.pose.bones for row in b.matrix for v in row])
            if not all(math.isfinite(v) for v in values):raise RuntimeError('Nonfinite saved motion at frame '+str(frame))
            if expected:
                old=array('f');data=stream.read(len(values)*4)
                if len(data)!=len(values)*4:raise RuntimeError('Truncated stored trajectory')
                old.frombytes(data);maximum=max(maximum,max(abs(a-b) for a,b in zip(old,values)))
            else:stream.write(values.tobytes())
            count+=1
        if expected and stream.read(1):raise RuntimeError('Extra trajectory samples')
    scene.frame_set(current,subframe=sub)
    if maximum>1e-5:raise RuntimeError('Full playback mismatch: '+str(maximum))
    return {'frames':count,'max_matrix_error':maximum}
