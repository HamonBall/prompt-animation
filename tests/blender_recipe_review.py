"""Reopen a saved Stage 07 bake, verify playback, and render both views."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]

from avatar_app.blender import rig_profile as rp
from avatar_app.blender.geometry import skin_bounds
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import value_error
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.lossless_evidence import encode_view, recover_evidence, retire_pngs
from tools.render_root_motion import render_view
from tools.storage_policy import ARTIFACTS, confined


def main(key):
    out = confined(ARTIFACTS / 'stages/07' / key, ARTIFACTS / 'stages/07')
    with store.producer_lease(out):
        recover_evidence(out)
        manifest, _, baked = validate_manifest(out)
        assert not manifest['views']
        identity = store.digest(baked)
        result = json.loads((out / 'result.json').read_text(encoding='utf-8'))
        assert result['review']['passed'] and manifest['inputs'] == store.input_identity(out)
        profile = c.loads(c.AvatarProfile, (out / 'profile.json').read_text(encoding='utf-8'))
        motion = c.loads(c.ExecutableMotion, (out / 'executable.json').read_text(encoding='utf-8'))
        handle = store.open_preview(out)
        floor = handle.scene.objects.get('Preview floor')
        if floor is not None and floor in handle.objects:
            handle.objects.remove(floor)
            handle.environment.append(floor)
        assert handle.scene.frame_end == len(result['samples'])
        bounds, metric = [], {'angular': 0., 'position': 0.}
        controls = {control.id: control for control in profile.controls}
        for frame, row in enumerate(result['samples'], 1):
            handle.scene.frame_set(frame)
            state = rp.capture_motion_state(handle, profile, revision=motion.entry_snapshot.revision)
            for actual in state.measured_controls:
                control = controls[actual.control_id]
                expected = row['measured'][actual.control_id]
                error = value_error(actual.value, tuple(expected) if isinstance(expected, list) else expected,
                                    control.value_shape)
                angular = control.unit != 'metre'
                assert error < (.05 if angular else .001), (frame, control.id, error)
                kind = 'angular' if angular else 'position'
                metric[kind] = max(metric[kind], error)
            bounds.extend(skin_bounds(handle))
        hull = [[operation(point[i] for point in bounds) for i in range(3)] for operation in (min, max)]
        views, retirement = {}, []
        for label in ('front', 'side'):
            camera = render_view(handle, profile, out, label, hull)
            media, plan = encode_view(out, label, manifest['expected_frames'], fps=manifest['fps'],
                                      fps_base=manifest['fps_base'])
            views[label] = dict(camera, media=media, sheet_sha256=store.digest(out / (label + '-sheet.png')))
            retirement.append(plan)
            store.write_manifest(out, handle.scene, views=views, complete=False)
        store.write_manifest(out, handle.scene, views=views, complete=True)
        retire_pngs(out, retirement)
        assert store.digest(baked) == identity
        store.atomic_json(out / 'playback.json', {'motion_sha256': identity, 'maxima': metric,
                          'frames': len(result['samples']), 'result_sha256': store.digest(out / 'result.json'),
                          'renderer_sha256': store.digest(Path(__file__))})
    print('STAGE07_PLAYBACK_AND_RENDER_PASSED', key, metric, flush=True)


if __name__ == '__main__':
    main(sys.argv[sys.argv.index('--') + 1])
