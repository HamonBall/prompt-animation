"""Fixed front and side views of the full validated Stage 05.6a trajectory."""
import math
from pathlib import Path
import sys
import time

import bpy
from mathutils import Vector
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]

from avatar_app.blender import rig_profile as rp
from avatar_app.movement_library import contracts as c
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.lossless_evidence import encode_view, recover_evidence, retire_pngs
from tools.root_motion_evidence import VIEWS, WIDTH, case_path, numeric_valid, runtime
from tools.root_motion_playback import verify
from tools.storage_policy import enforce


def render_view(handle, profile, out, label, bounds, *, view_basis=None):
    scene = handle.scene
    scene.frame_set(1)
    body = view_basis if view_basis is not None else rp.semantic_frame(handle, profile, 'pelvis').to_3x3()
    direction = (body.col[1] if label == 'front' else body.col[0]).copy()
    direction.z = 0
    direction.normalize()
    low, high = map(Vector, bounds)
    low.z = min(low.z, 0)
    center = (low + high) / 2
    camera = scene.camera
    camera.location = center + direction * 6 + Vector((0, 0, .85))
    camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = (high - low).length * 1.15
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'MATERIAL'
    scene.view_settings.view_transform = 'Standard'
    scene.render.dither_intensity = 0
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = scene.render.resolution_y = WIDTH
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.compression = 100
    columns = 8
    count = scene.frame_end
    rows = math.ceil(count / columns)
    pixels_per_cell = WIDTH ** 2
    enforce(out, growth=(count + columns * rows) * pixels_per_cell * 8 + 65536,
            temporary=columns * rows * pixels_per_cell * 8 + 65536)
    sheet = np.zeros((rows * WIDTH, columns * WIDTH, 4), dtype=np.float32)
    sheet[:, :, 3] = 1
    folder = out / label
    folder.mkdir(exist_ok=False)
    for index in range(count):
        scene.frame_set(index + 1)
        path = folder / f'{index + 1:04d}.png'
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(str(path), check_existing=False)
        try:
            x = index % columns * WIDTH
            y = (rows - 1 - index // columns) * WIDTH
            sheet[y:y + WIDTH, x:x + WIDTH] = np.array(image.pixels[:]).reshape(WIDTH, WIDTH, 4)
        finally:
            bpy.data.images.remove(image)
    image = bpy.data.images.new(label, columns * WIDTH, rows * WIDTH, alpha=True)
    try:
        image.pixels.foreach_set(sheet.ravel())
        image.save_render(str(out / (label + '-sheet.png')), scene=scene)
    finally:
        bpy.data.images.remove(image)
    scene.frame_set(1)
    return store.camera_record(scene)


def main(key):
    out = case_path(key)
    result = numeric_valid(out)
    renderer = store.digest(Path(__file__))
    with store.producer_lease(out):
        recover_evidence(out)
        manifest, _, motion = validate_manifest(out)
        assert not manifest['views']
        before = (store.digest(motion), motion.stat().st_mtime_ns)
        profile = c.loads(c.AvatarProfile, (out / 'profile.json').read_text(encoding='utf-8'))
        handle = store.open_preview(out)
        # The bundle loader lists every scene object on the handle. Restore
        # the fixture's original split so skin bounds exclude the floor mesh.
        floor = handle.scene.objects.get('Preview floor')
        assert floor is not None and floor.type == 'MESH' and not floor.modifiers
        handle.objects.remove(floor)
        handle.environment.append(floor)
        started = time.perf_counter()
        playback = verify(handle, profile, out, result)
        playback['runtime'] = runtime()
        store.atomic_json(out / 'saved-playback-review.json', playback)
        playback_s = time.perf_counter() - started
        views = {}
        plans = []
        timings = {}
        for label in VIEWS:
            started = time.perf_counter()
            view = render_view(handle, profile, out, label, playback['swept_bounds'])
            media, plan = encode_view(out, label, manifest['expected_frames'],
                                      fps=manifest['fps'], fps_base=manifest['fps_base'])
            view.update(media=media, renderer_sha256=renderer, framing='fixed full avatar sweep and floor',
                        sheet_sha256=store.digest(out / (label + '-sheet.png')))
            views[label] = view
            plans.append(plan)
            timings[label] = time.perf_counter() - started
            store.write_manifest(out, handle.scene, views=views, complete=False)
        store.write_manifest(out, handle.scene, views=views, complete=True)
        retire_pngs(out, plans)
        assert before == (store.digest(motion), motion.stat().st_mtime_ns)
        assert renderer == store.digest(Path(__file__))
        store.atomic_json(out / 'render-timing.json', {
            'saved_playback_s': playback_s, 'seconds_by_view': timings,
            'rendered_frames': len(VIEWS) * len(manifest['expected_frames']),
        })
        enforce(out)
    print('ROOT_RENDER_PASSED', out.parent.name, out.name, playback['maxima'], flush=True)


if __name__ == '__main__':
    main(sys.argv[sys.argv.index('--') + 1])
