"""Isolated Blender worker for historical scene inspection, never motion rebuilding."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from tools.artifact_store import atomic_json, save_standalone as save_scene, digest


def rounded(value):
    return round(float(value), 6)


def matrix(value):
    return [rounded(v) for row in value for v in row]


def hashed(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def action_signature(action, slot):
    if action is None:
        return None
    curves = []
    for layer in action.layers:
        for strip in layer.strips:
            if strip.type != 'KEYFRAME':
                raise RuntimeError('Unsupported historical action strip')
            bag = strip.channelbag(slot)
            if bag:
                for curve in bag.fcurves:
                    curves.append([curve.data_path, curve.array_index, curve.extrapolation,
                                   [[list(p.co), p.interpolation, p.handle_left_type, list(p.handle_left),
                                     p.handle_right_type, list(p.handle_right)] for p in curve.keyframe_points],
                                   [(m.type, str(m)) for m in curve.modifiers]])
    # Empty/unsupported legacy animations are retained rather than guessed equivalent.
    if not curves:
        raise RuntimeError('No inspectable action curves')
    return {'curves_sha256': hashed(sorted(curves, key=lambda v: (v[0], v[1]))),
            'range': list(action.frame_range), 'slot_type': slot.target_id_type,
            'curve_count': len(curves)}


def signature():
    scene = bpy.context.scene
    rigs = [o for o in scene.objects if o.type == 'ARMATURE']
    if len(rigs) != 1:
        raise RuntimeError(f'Expected one active-scene rig, found {len(rigs)}')
    rig = rigs[0]
    ad = rig.animation_data
    if not ad or not ad.action or not ad.action_slot:
        raise RuntimeError('Missing action/slot')
    if ad.nla_tracks or rig.constraints:
        raise RuntimeError('Unsupported NLA/rig constraints; retain original')
    materials = []
    geometry = []
    exact_geometry=[]
    used_materials={m for obj in scene.objects if obj.type=='MESH' for m in obj.data.materials if m}
    used_images=set()
    material_map={}
    material_names={}
    for material in sorted(used_materials,key=lambda m:m.name):
        nodes = []
        links = []
        if material.use_nodes:
            for node in material.node_tree.nodes:
                if getattr(node,'image',None): used_images.add(node.image)
                inputs = []
                for socket in node.inputs:
                    if hasattr(socket, 'default_value'):
                        v = socket.default_value
                        try: v = list(v)
                        except TypeError: pass
                        inputs.append([socket.identifier, v])
                nodes.append([node.name, node.bl_idname, inputs,
                              getattr(getattr(node, 'image', None), 'name', None),
                              {key:getattr(node,key) for key in ('interpolation','extension','projection',
                               'projection_blend','uv_map','layer_name','blend_type','operation') if hasattr(node,key)}])
            links = [[l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier]
                     for l in material.node_tree.links]
        content=[list(material.diffuse_color),nodes,links]
        identity=hashed(content)
        material_map[material]=identity
        material_names[material.name]=identity
        materials.append(identity)
    for obj in scene.objects:
        if obj.type == 'MESH':
            mesh = obj.data
            if mesh.shape_keys or mesh.color_attributes:
                raise RuntimeError('Unreviewed shape-key/vertex-color content; retain original')
            normals=[tuple(rounded(v) for v in n.vector) for n in mesh.corner_normals] if mesh.has_custom_normals else []
            uv_layers=[(layer.name,[tuple(rounded(v) for v in uv.uv) for uv in layer.data])
                       for layer in mesh.uv_layers]
            faces=[]
            for p in mesh.polygons:
                faces.append([list(p.vertices),p.material_index,p.use_smooth,
                              [[name,[uv[i] for i in p.loop_indices]] for name,uv in uv_layers],
                              [normals[i] for i in p.loop_indices] if normals else []])
            geometry.append({'name': obj.name, 'vertices': hashed([list(v.co) for v in mesh.vertices]),
                             # Blender's sphere operator can emit the same oriented
                             # faces in a different order. Preserve winding, material
                             # assignment and smoothing while comparing the face set.
                             'polygons': hashed(sorted(faces)),
                             'weights': hashed([[(g.group, g.weight) for g in v.groups] for v in mesh.vertices]),
                             'groups': [g.name for g in obj.vertex_groups],
                             'matrix': matrix(obj.matrix_world), 'parent_type': obj.parent_type,
                             'modifiers': [(m.type, getattr(m, 'object', None).name if getattr(m, 'object', None) else None)
                                           for m in obj.modifiers],
                             'materials': [material_map[m] if m else None for m in mesh.materials]})
            exact_faces=[]
            raw_uv=[(layer.name,[tuple(uv.uv) for uv in layer.data]) for layer in mesh.uv_layers]
            raw_normals=[tuple(n.vector) for n in mesh.corner_normals] if mesh.has_custom_normals else []
            for face in mesh.polygons:
                exact_faces.append([list(face.vertices),face.material_index,face.use_smooth,
                    [[name,[uv[i] for i in face.loop_indices]] for name,uv in raw_uv],
                    [raw_normals[i] for i in face.loop_indices] if raw_normals else []])
            modifiers=[{key:getattr(m,key) for key in ('type','show_viewport','show_render',
                'use_vertex_groups','use_bone_envelopes','use_deform_preserve_volume') if hasattr(m,key)} for m in obj.modifiers]
            exact_geometry.append({**{k:v for k,v in geometry[-1].items() if k not in ('matrix','polygons')},
                                   'polygons':hashed(sorted(exact_faces)),'modifier_settings':modifiers,
                                   'parent':obj.parent.name if obj.parent else None})
    images = []
    for im in sorted(used_images,key=lambda im:im.name):
        if im.type in ('RENDER_RESULT', 'COMPOSITING') or im.source in ('VIEWER', 'GENERATED'):
            continue
        packed = im.packed_file
        if not packed:
            # Existing external content is hashed, then pack_all embeds it in the candidate.
            file = Path(bpy.path.abspath(im.filepath))
            if not file.is_file():
                raise RuntimeError('Missing image resource: ' + im.filepath)
            sha = digest(file)
        else:
            sha = hashlib.sha256(packed.data).hexdigest()
        images.append([im.name, list(im.size), sha, im.colorspace_settings.name, im.alpha_mode])
    rest = [[b.name, b.parent.name if b.parent else None, matrix(b.matrix_local), b.length] for b in rig.data.bones]
    exact_rest=[[b.name,b.parent.name if b.parent else None,[list(row) for row in b.matrix_local],b.length,
                 b.use_deform,b.use_connect,b.inherit_scale,b.use_inherit_rotation,b.use_local_location] for b in rig.data.bones]
    original = scene.frame_current
    frames = sorted(set([scene.frame_start, scene.frame_end] + [round(scene.frame_start +
                     (scene.frame_end-scene.frame_start)*i/8) for i in range(9)]))
    poses = {}
    for frame in frames:
        scene.frame_set(frame)
        poses[str(frame)] = {'rig_matrix': matrix(rig.matrix_world),
                             'bones': [[b.name, matrix(b.matrix), list(b.head), list(b.tail)] for b in rig.pose.bones]}
    scene.frame_set(original)
    cameras = []
    for obj in scene.objects:
        if obj.type == 'CAMERA':
            cameras.append({'name': obj.name, 'matrix': matrix(obj.matrix_world), 'type': obj.data.type,
                            'lens': obj.data.lens, 'ortho_scale': obj.data.ortho_scale,
                            'clip_start': obj.data.clip_start, 'clip_end': obj.data.clip_end})
    return {'rig': rig.name, 'action': action_signature(ad.action, ad.action_slot),
            'timing': [scene.frame_start, scene.frame_end, scene.render.fps, scene.render.fps_base],
            'rest': hashed(rest), 'geometry': hashed(sorted(geometry, key=lambda v: v['name'])),
            'materials': hashed(sorted(materials)), 'material_names':material_names, 'images': images, 'poses': poses,
            'asset_exact':hashed({'geometry':sorted(exact_geometry,key=lambda x:x['name']),
                                  'rest':exact_rest,'materials':sorted(materials),'images':images}),
            'cameras': cameras, 'current_frame': original,
            'active_action_name': ad.action.name, 'slot_identifier': ad.action_slot.identifier}


def equivalence(a, b):
    # Names differ when a render process appended an existing action; the actual
    # slot binding, every curve and sampled solved matrices must still agree.
    keys = ('rig', 'action', 'timing', 'rest', 'geometry', 'materials', 'images')
    for key in keys:
        if a[key] != b[key]:
            raise RuntimeError('Distinct historical content: ' + key)
    maximum = 0
    def compare(x, y):
        nonlocal maximum
        if isinstance(x, dict):
            if x.keys() != y.keys(): raise RuntimeError('Pose keys differ')
            for key in x: compare(x[key], y[key])
        elif isinstance(x, list):
            if len(x) != len(y): raise RuntimeError('Pose dimensions differ')
            for v, w in zip(x, y): compare(v, w)
        elif isinstance(x, (float, int)):
            maximum = max(maximum, abs(x-y))
        elif x != y:
            raise RuntimeError('Pose identity differs')
    compare(a['poses'], b['poses'])
    if maximum > .00001:
        raise RuntimeError(f'Distinct measured playback: {maximum}')
    return maximum


def verify_saved_measurements(directory):
    """Compare historical numeric evidence to the opened action, without a builder."""
    result_file = directory / 'result.json'
    if not result_file.exists():
        raise RuntimeError('No numeric evidence to establish historical equivalence')
    result = json.loads(result_file.read_text(encoding='utf-8'))
    profile_path = directory / 'profile.json'
    if not profile_path.exists(): profile_path = directory.parent / 'profile.json'
    if not profile_path.exists():
        raise RuntimeError('No stored profile')
    from avatar_app.movement_library import contracts as c
    from avatar_app.blender import rig_profile as rp
    from avatar_app.blender.avatar import AvatarHandle, map_mixamo_bones
    from avatar_app.movement_library.compiler import value_error
    from mathutils import Vector
    profile = c.loads(c.AvatarProfile, profile_path.read_text(encoding='utf-8'))
    rig = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    mapped = map_mixamo_bones(rig)
    # Measurement consumes profile frames/rest data; no posing or execution occurs.
    up = (rig.matrix_world.inverted().to_3x3() @ Vector((0,0,1))).normalized()
    right = (mapped['RightArm'].bone.head_local-mapped['LeftArm'].bone.head_local).normalized()
    forward = up.cross(right).normalized()
    height = (mapped['Head'].bone.tail_local-mapped['LeftFoot'].bone.head_local).dot(up)
    h = AvatarHandle(bpy.context.scene, rig, mapped, height, up, forward, right, [])
    specs = {s.id: s for s in profile.controls}
    samples = result['samples']
    maximum = 0
    for index in sorted(set([0, len(samples)-1] + [round((len(samples)-1)*i/8) for i in range(9)])):
        sample = samples[index]
        h.scene.frame_set(sample['frame'])
        measured = rp.capture_motion_state(h, profile, revision=1)
        for v in measured.measured_controls:
            expected = sample['measured'][v.control_id]
            if isinstance(expected, list): expected = tuple(expected)
            maximum = max(maximum, value_error(v.value, expected, specs[v.control_id].value_shape))
    if maximum > .001:
        raise RuntimeError(f'Saved numeric evidence mismatch: {maximum}')
    return maximum


def inspect(path, directory):
    started = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False)
    elapsed = time.perf_counter() - started
    sig = signature()
    current = bpy.context.scene.frame_current
    error = verify_saved_measurements(directory)
    bpy.context.scene.frame_set(current)
    return sig, error, elapsed


def prepare(job):
    directory = Path(job['directory'])
    base = Path(job['source'])
    signatures = {}
    source_sig,source_error,source_elapsed=inspect(base,directory)
    signatures[str(base)]={'signature':source_sig,'numeric_error':source_error,'load_seconds':source_elapsed}
    for path in job['originals']:
        if path==str(base): continue
        try:
            started=time.perf_counter()
            bpy.ops.wm.open_mainfile(filepath=path,load_ui=False)
            elapsed=time.perf_counter()-started
            sig=signature()
            record={'signature':sig,'load_seconds':elapsed}
            try:
                equivalence(source_sig,sig)
                # Exact curves, rest geometry and sampled solved bone transforms
                # already establish the same measured motion. Measure the source
                # against JSON once; the independent verifier measures the saved
                # candidate again. Distinct actions are retained without trying to
                # interpret them as this case's current numeric result.
                record.update(numeric_error=source_error,numeric_comparison='equal_curves_and_solved_transforms')
            except RuntimeError:
                pass
            signatures[path]=record
        except Exception as exc:
            signatures[path] = {'error': str(exc)}
    if 'error' in signatures[str(base)]:
        raise RuntimeError('Canonical source validation failed: ' + signatures[str(base)]['error'])
    original = signatures[str(base)]['signature']
    retire = []
    cameras = []
    retained = []
    for path, record in signatures.items():
        if 'error' in record:
            retained.append({'path': path, 'reason': record['error']})
            continue
        try:
            equivalence(original, record['signature'])
            retire.append(path)
            for camera in record['signature']['cameras']:
                if camera not in cameras: cameras.append(camera)
        except Exception as exc:
            retained.append({'path': path, 'reason': str(exc)})
    bpy.ops.wm.open_mainfile(filepath=str(base), load_ui=False)
    scene = bpy.context.scene
    from mathutils import Matrix
    for index, camera in enumerate(cameras):
        # Preserve every distinct view explicitly; no second scene copy is needed.
        if camera in original['cameras']: continue
        data = bpy.data.cameras.new('Historical evidence view')
        obj = bpy.data.objects.new('Historical evidence view ' + str(index), data)
        scene.collection.objects.link(obj)
        obj.matrix_world = Matrix([camera['matrix'][i:i+4] for i in range(0,16,4)])
        for key in ('type', 'lens', 'ortho_scale', 'clip_start', 'clip_end'):
            setattr(data, key, camera[key])
    scene['artifact_historical_views'] = json.dumps(cameras)
    # Do not move the source's current frame or re-bake any action.
    stats = save_scene(job['candidate'])
    return {'source_signature': original, 'originals': signatures, 'retire': retire,
            'retained': retained, 'preserved_cameras': cameras, 'save': stats}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--mode', choices=('prepare','verify'), required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    job = json.loads(args.job.read_text(encoding='utf-8'))
    try:
        if args.mode == 'prepare':
            value = prepare(job)
        else:
            prepared = json.loads(Path(job['prepared']).read_text(encoding='utf-8'))
            sig, error, elapsed = inspect(Path(job['candidate']), Path(job['directory']))
            residual = equivalence(prepared['source_signature'], sig)
            # Every historical view must be represented by a camera in the candidate.
            for camera in prepared['preserved_cameras']:
                assert any(all(camera[k] == v[k] for k in camera if k != 'name') for v in sig['cameras'])
            assert sig['current_frame'] == prepared['source_signature']['current_frame']
            assert sig['active_action_name'] == prepared['source_signature']['active_action_name']
            assert sig['slot_identifier'] == prepared['source_signature']['slot_identifier']
            for im in bpy.data.images:
                if im.source == 'FILE': assert im.packed_file, ('External image', im.name)
            assert not bpy.data.libraries, 'External linked Blender library'
            value = {'numeric_error': error, 'pose_residual': residual, 'load_seconds': elapsed,
                     'action': sig['active_action_name'], 'slot': sig['slot_identifier'], 'timing': sig['timing']}
        atomic_json(args.report, {'passed': True, **value})
    except Exception as exc:
        atomic_json(args.report, {'passed': False, 'error': str(exc)})
        raise


if __name__ == '__main__': main()
