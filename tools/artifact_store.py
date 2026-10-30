"""Portable developer evidence: one atomic compressed scene and explicit completion.

No bpy import at module scope: inventory, manifests and resume checks run in Python.
"""
from contextlib import contextmanager
import atexit
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'preview-manifest.json'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic_replace(source, target):
    # Windows indexers/readers may briefly hold a file without delete sharing.
    # A bounded retry preserves atomic replacement and still fails safely.
    for attempt in range(6):
        try:
            os.replace(source,target)
            return
        except PermissionError:
            if attempt==5: raise
            time.sleep(.02 * 2**attempt)


def atomic_json(path, value, *, compact=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w',encoding='utf-8') as stream:
            stream.write(json.dumps(value,indent=None if compact else 2,
                                    separators=(',',':') if compact else None,allow_nan=False)+'\n')
            stream.flush();os.fsync(stream.fileno())
        atomic_replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def process_alive(pid):
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return kernel.GetLastError() == 5  # Access denied is not proof of death.
        code = ctypes.c_ulong()
        try:
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def producer_lease(directory):
    """Cooperating producers and migration share an exclusive directory lease."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    for parent in directory.parents:
        ancestor = parent / '.artifact-writer.lock'
        if ancestor.is_file():
            owner = json.loads(ancestor.read_text(encoding='utf-8'))
            if owner['pid'] != os.getpid() and process_alive(owner['pid']):
                raise RuntimeError(f'Active artifact writer: {ancestor}')
    lock = directory / '.artifact-writer.lock'
    token = {'pid': os.getpid(), 'token': uuid.uuid4().hex, 'started': time.time()}
    if lock.exists():
        previous = json.loads(lock.read_text(encoding='utf-8'))
        if process_alive(previous['pid']):
            raise RuntimeError(f'Active artifact writer: {lock} (PID {previous["pid"]})')
        # Only a proven dead owner can be reclaimed.
        if json.loads(lock.read_text(encoding='utf-8')) != previous:
            raise RuntimeError(f'Artifact lease changed: {lock}')
        lock.unlink()
    with lock.open('x', encoding='utf-8') as stream:
        json.dump(token, stream)
    try:
        yield token
    finally:
        if lock.exists() and json.loads(lock.read_text(encoding='utf-8')) == token:
            lock.unlink()


def hold_producer_lease(directory):
    lease = producer_lease(directory)
    lease.__enter__()
    atexit.register(lease.__exit__, None, None, None)


def save_standalone(path, *, bpy_module=None):
    """Save a self-contained compressed sibling, validate, then replace atomically.

    copy=True keeps Blender's working filename intact. Preferences are never saved.
    A failed save cannot damage the previous canonical file.
    """
    if bpy_module is None:
        import bpy as bpy_module
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.stem + '.' + uuid.uuid4().hex + '.blend')
    preferences = bpy_module.context.preferences.filepaths
    previous = preferences.save_version
    started = time.perf_counter()
    try:
        preferences.save_version = 0
        bpy_module.ops.file.pack_all()
        data = bpy_module.data
        if getattr(data, 'libraries', ()) and len(data.libraries):
            raise RuntimeError('Evidence must not depend on linked Blender libraries')
        for image in getattr(data, 'images', ()):
            if image.source in ('FILE', 'TILED') and not image.packed_file:
                raise RuntimeError('Image resource was not embedded: ' + image.name)
            if image.source in ('MOVIE', 'SEQUENCE'):
                raise RuntimeError('Unpacked temporal image resource: ' + image.name)
        for sound in getattr(data, 'sounds', ()):
            if not sound.packed_file:
                raise RuntimeError('Sound resource was not embedded: ' + sound.name)
        result = bpy_module.ops.wm.save_as_mainfile(filepath=str(temporary), compress=True, copy=True)
        if result != {'FINISHED'} or not temporary.is_file() or temporary.stat().st_size < 32:
            raise RuntimeError('Blender did not create a complete scene candidate')
        # Parse the saved library before replacing; migration additionally reopens it.
        with bpy_module.data.libraries.load(str(temporary)) as (source, target):
            if not source.scenes or not source.objects:
                raise RuntimeError('Saved evidence contains no scene/objects')
        atomic_replace(temporary, path)
    finally:
        preferences.save_version = previous
        temporary.unlink(missing_ok=True)
    return {'bytes': path.stat().st_size, 'save_seconds': time.perf_counter() - started}


def save_scene(path, *, bpy_module=None):
    """Routine writes are v2 bundles. Standalone output is an explicit export."""
    if bpy_module is not None:
        return save_standalone(path,bpy_module=bpy_module)  # legacy failure-injection adapter
    from tools.artifact_bundle import write_bundle
    value,_=write_bundle(Path(path).parent)
    return {'bytes':(Path(path).parent/value['motion']['path']).stat().st_size,'schema_version':2}


def scene_path(directory):
    directory = Path(directory)
    manifest=directory/MANIFEST
    if manifest.is_file():
        m=json.loads(manifest.read_text(encoding='utf-8'))
        if m.get('schema_version')==2:
            from tools.artifact_bundle import validate_manifest
            return validate_manifest(directory)[2]
    canonical = directory / 'preview.blend'
    if canonical.is_file():
        return canonical
    historical = directory / 'visual-preview.blend'
    if historical.is_file():
        return historical
    raise FileNotFoundError(canonical)


def resolve_historical(path):
    """Resolve historical canonical references without rewriting old receipts."""
    from tools.storage_policy import confined
    path=confined(path)
    if path.is_dir():return path
    if path.suffix=='.blend1':
        if path.exists():raise RuntimeError('Historical backup is retained; inspect it explicitly')
        raise RuntimeError('Obsolete history was retired; its action is not claimed equivalent to the accepted case')
    manifest=path.parent/MANIFEST
    if path.name=='preview.blend' and manifest.exists():
        value=json.loads(manifest.read_text(encoding='utf-8'))
        original=value.get('original_scene') or {}
        if value.get('schema_version')==2 and Path(original.get('path','')).resolve()==path:
            from tools.artifact_bundle import validate_manifest
            validate_manifest(path.parent);return path.parent
    if path.name=='visual-preview.blend' and manifest.exists():
        migration=path.parent/'artifact-migration.json'
        if migration.exists():
            old=json.loads(migration.read_text(encoding='utf-8'))
            value=json.loads(manifest.read_text(encoding='utf-8'))
            if (str(path) in old.get('retired',{}) and old.get('canonical_sha256')==
                    (value.get('original_scene') or {}).get('sha256')):
                from tools.artifact_bundle import validate_manifest
                validate_manifest(path.parent);return path.parent
    if path.exists() and path.suffix=='.blend':return path.parent
    raise FileNotFoundError('No verified historical canonical mapping: '+str(path))


def open_preview(directory):
    """Render the stored rig/action/resources, without rebuilding from today's FBX."""
    import bpy
    from mathutils import Vector
    from avatar_app.blender.avatar import AvatarHandle, map_mixamo_bones
    manifest=Path(directory)/MANIFEST
    if manifest.is_file() and json.loads(manifest.read_text(encoding='utf-8')).get('schema_version')==2:
        from tools.artifact_bundle import open_bundle
        open_bundle(directory)
    else:
        bpy.ops.wm.open_mainfile(filepath=str(scene_path(directory)), load_ui=False,use_scripts=False)
    rigs=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
    if len(rigs)!=1: raise RuntimeError('Evidence must contain exactly one active-scene rig')
    rig=rigs[0]
    ad=rig.animation_data
    if not ad or not ad.action or not ad.action_slot:
        raise RuntimeError('Stored evidence has no active action/slot')
    bones=map_mixamo_bones(rig)
    up=(rig.matrix_world.inverted().to_3x3() @ Vector((0,0,1))).normalized()
    right=(bones['RightArm'].bone.head_local-bones['LeftArm'].bone.head_local).normalized()
    forward=up.cross(right).normalized()
    height=(bones['Head'].bone.tail_local-bones['LeftFoot'].bone.head_local).dot(up)
    return AvatarHandle(bpy.context.scene,rig,bones,height,up,forward,right,list(bpy.context.scene.objects))


def input_identity(directory):
    directory = Path(directory)
    inputs = {}
    for name in ('result.json', 'entry.json', 'instance.json', 'fragment.json', 'executable.json'):
        path = directory / name
        if path.is_file():
            inputs[name] = digest(path)
    profile = directory / 'profile.json'
    if not profile.is_file():
        profile = directory.parent / 'profile.json'
    if profile.is_file():
        inputs['profile.json'] = digest(profile)
    source = directory / 'source.json'
    if not source.is_file(): source = directory.parent / 'source.json'
    if source.is_file(): inputs['source.json'] = digest(source)
    # Changed implementation must invalidate routine render resume as well.
    sources = sorted((ROOT / 'src/avatar_app').rglob('*.py')) + [
        ROOT / 'tools/artifact_store.py', ROOT / 'tools/movement_evidence.py',
        ROOT / 'tools/artifact_bundle.py',ROOT / 'tools/storage_policy.py',
        ROOT / 'tools/lossless_evidence.py',ROOT / 'tools/media_transaction.py',ROOT / 'tests/shoulders_arms_cases.py',
        ROOT / 'tools/preview_movement.py', ROOT / 'tests/blender_movement_head_neck.py',
        ROOT / 'tests/blender_movement_spine_pelvis.py',ROOT / 'tests/blender_movement_shoulders_arms.py',
        ROOT / 'tests/blender_primitive_execution.py',ROOT / 'tests/blender_spine_pelvis_boundaries.py',
        ROOT / 'tests/blender_movement_elbows_wrists_hands.py',ROOT / 'tests/elbows_wrists_hands_cases.py',
        ROOT / 'tools/retarget_clip.py',ROOT / 'tools/shoulders_arms_storage_preflight.py']
    inputs['producer_sha256'] = hashlib.sha256(''.join(digest(p) for p in sources).encode()).hexdigest()
    return inputs


def entry_metadata(fixture, parameters, scene):
    fixture = str(fixture) if fixture else 'implicit neutral PosePlan'
    return {'entry_fixture': fixture, 'entry_kind': 'neutral' if
            ('entry-neutral.json' in fixture or fixture == 'implicit neutral PosePlan') else 'authored_non_neutral',
            'movement_parameters': parameters, 'parameter_label': 'default parameters' if not parameters else 'explicit parameters',
            'initial_frame': scene.frame_start, 'current_frame': scene.frame_current}


def write_source_identity(directory, rig):
    source = ROOT / ('Hip Hop Mixamo.fbx' if rig == 'mixamo' else rig)
    value = {'kind': 'procedural-demo-v1'} if rig == 'demo' else {
        'kind': 'imported', 'path': str(source.resolve()), 'sha256': digest(source)}
    atomic_json(Path(directory) / 'source.json', value)


def camera_record(scene):
    camera = scene.camera
    return {'matrix_world': [list(row) for row in camera.matrix_world],
            'type': camera.data.type, 'lens': camera.data.lens, 'ortho_scale': camera.data.ortho_scale,
            'resolution': [scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage]}


def write_manifest(directory, scene, *, views=None, metadata=None, complete=False):
    directory = Path(directory)
    views = views or {}
    frames = list(range(scene.frame_start, scene.frame_end + 1))
    value = {'schema_version': 1, 'scene': 'preview.blend', 'inputs': input_identity(directory),
             'frame_start': scene.frame_start, 'frame_end': scene.frame_end,
             'current_frame': scene.frame_current, 'fps': scene.render.fps, 'fps_base': scene.render.fps_base,
             'views': views, 'expected_frames': frames, 'entry': metadata or {}, 'complete': False,
             'scene_sha256': digest(directory/'preview.blend') if (directory/'preview.blend').is_file() else None}
    value['bindings']=[{'rig':o.name,'action':o.animation_data.action.name,
                        'slot':o.animation_data.action_slot.identifier}
                       for o in getattr(scene,'objects',()) if o.type=='ARMATURE' and o.animation_data
                       and o.animation_data.action and o.animation_data.action_slot]
    existing=directory/MANIFEST
    if existing.is_file():
        previous=json.loads(existing.read_text(encoding='utf-8'))
        if previous.get('schema_version')==2:
            if metadata is None:value['entry']=previous.get('entry',{})
            for key in ('scene','scene_sha256'):value.pop(key,None)
            value={**previous,**value,'schema_version':2}
            representation='ffv1_mkv' if views and all('media' in v for v in views.values()) else 'png_sequence'
            value['visual_evidence']={'representation':representation,'views':list(views),'frames':frames,
                                      'fps':scene.render.fps,'fps_base':scene.render.fps_base,
                                      'result_sha256':value['inputs'].get('result.json'),'complete':complete}
    if complete:
        if not views or not files_complete(directory, value):
            raise RuntimeError(f'Cannot complete missing visual evidence: {directory}')
        value['complete'] = True
    atomic_json(directory / MANIFEST, value)
    if value['schema_version']==2:
        from tools.storage_policy import enforce
        enforce(directory,case_bytes=(directory/value['motion']['path']).stat().st_size+(directory/MANIFEST).stat().st_size)
    return value


def files_complete(directory, manifest):
    directory = Path(directory)
    scene=manifest.get('motion',{}).get('path',manifest.get('scene','preview.blend'))
    if not (directory / scene).is_file():
        return False
    for view in manifest['views']:
        details=manifest['views'][view] if isinstance(manifest['views'],dict) else {}
        folder=details.get('frames_dir',view);sheet=details.get('sheet',f'{view}-sheet.png')
        if 'media' in details:
            from tools.lossless_evidence import media_complete
            if not media_complete(directory,details['media'],manifest['expected_frames'],fps=manifest['fps'],fps_base=manifest['fps_base']):return False
            path=directory/sheet
            if not path.is_file() or path.stat().st_size<8:return False
            with path.open('rb') as stream:
                if stream.read(8)!=b'\x89PNG\r\n\x1a\n':return False
            continue
        for name in [sheet] + [f'{folder}/{frame:04d}.png' for frame in manifest['expected_frames']]:
            path = directory / name
            if not path.is_file() or path.stat().st_size < 8:
                return False
            with path.open('rb') as stream:
                if stream.read(8) != b'\x89PNG\r\n\x1a\n':
                    return False
    return True


def render_complete(directory, views, *, allow_legacy=False):
    directory = Path(directory)
    path = directory / MANIFEST
    try:
        if path.is_file():
            m = json.loads(path.read_text(encoding='utf-8'))
            if m.get('schema_version')==2:
                from tools.artifact_bundle import validate_manifest
                validate_manifest(directory)
                expected=input_identity(directory);actual=m['inputs']
                if allow_legacy and m.get('verification',{}).get('passed'):
                    expected={k:v for k,v in expected.items() if k!='producer_sha256'}
                    actual={k:v for k,v in actual.items() if k!='producer_sha256'}
                return bool(m['complete'] and set(m['views'])==set(views) and actual==expected
                            and files_complete(directory,m) and m['visual_evidence']['complete'])
            return (m['schema_version'] == 1 and m['complete'] and set(m['views']) == set(views)
                    and m['inputs'] == input_identity(directory) and files_complete(directory, m)
                    and m['scene_sha256'] == digest(directory/m['scene']))
        if allow_legacy:
            # Inspection can still consume old two-file evidence; never resume a producer with it.
            result = directory / 'result.json'
            marker = json.loads((directory / 'visual-source.json').read_text(encoding='utf-8'))
            count = json.loads(result.read_text(encoding='utf-8'))['frames']
            return (marker['result_sha256'] == digest(result) and files_complete(directory,
                    {'scene': scene_path(directory).name, 'views': views, 'expected_frames': list(range(1, count + 1))}))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        pass
    return False
