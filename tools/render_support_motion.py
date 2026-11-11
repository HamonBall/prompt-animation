"""Validate saved support playback and render complete front and side views."""
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]

from avatar_app.blender import rig_profile as rp
from avatar_app.blender.geometry import seat_penetration, skin_bounds, support_skin_height
from avatar_app.blender.support_mechanics import body_contact_point, support_part
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import value_error
from avatar_app.movement_library.support import BODY_ANCHORS, PALM_ANCHORS, sole_region_margin
from avatar_app.motion import Surface
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.lossless_evidence import encode_view, recover_evidence, retire_pngs
from tools.render_root_motion import render_view
from tools.support_evidence import FRAMING, VIEWS, case_path, numeric_valid, runtime


def verify(handle, profile, motion, result):
    controls = {item.id: item for item in profile.controls}
    bounds = []
    maxima = {'position_m': 0., 'angle_deg': 0., 'contact_m': 0., 'skin_gap_m': 0., 'surface_penetration_m': 0.}
    events = {event.anchor_id: event for event in motion.contact_events}
    surfaces = {surface.name: surface for surface in handle.surfaces}
    assert handle.scene.frame_end == result['frames'] == len(result['samples'])
    assert (handle.scene.render.fps, handle.scene.render.fps_base) == (motion.fps, 1)
    for frame, row in enumerate(result['samples'], 1):
        handle.scene.frame_set(frame)
        time = min(motion.duration_s, (frame - 1) / motion.fps)
        assert row['frame'] == frame and abs(row['time_s'] - time) < 1e-7 and not row['violations']
        state = rp.capture_motion_state(handle, profile, revision=motion.entry_snapshot.revision, captured_time_s=time)
        values = {item.control_id: item.value for item in state.measured_controls}
        assert values.keys() == row['measured'].keys()
        for key, value in values.items():
            spec = controls[key]
            saved = row['measured'][key]
            error = value_error(value, tuple(saved) if isinstance(saved, list) else saved, spec.value_shape)
            angular = spec.unit == 'degree' or spec.value_shape == 'quaternion'
            metric = 'angle_deg' if angular else 'position_m'
            maxima[metric] = max(maxima[metric], error)
            assert error < (.05 if angular else .001), (frame, key, error)
        held = {
            event.anchor_id: event.target_world_v1 for event in motion.contact_events
            if event.interval.start_s + event.acquire_s - 1e-9 <= time <= event.interval.end_s - event.release_s + 1e-9
        }
        active = ({key: value['position'] for key, value in row['active_support_anchors'].items()}
                  if 'active_support_anchors' in row else row['active_foot_anchors'])
        assert held.keys() == active.keys()
        for key, point in held.items():
            assert tuple(active[key]) == point
            surface = surfaces[events[key].surface_id]
            actual = body_contact_point(handle, profile, key, surface) if key in BODY_ANCHORS else values[key + '.position']
            error = math.dist(actual, point)
            assert error < .001
            maxima['contact_m'] = max(maxima['contact_m'], error)
            if key in PALM_ANCHORS + BODY_ANCHORS:
                gap = abs(support_skin_height(handle, support_part(key), surface) - surface.height)
                assert gap <= .025 and abs(gap - row['support_skin_gaps_m'][key]) < .001
                maxima['skin_gap_m'] = max(maxima['skin_gap_m'], gap)
        balance = row.get('geometric_balance')
        if balance:
            side = next(iter(held)).split('.')[0]
            other = 'left' if side == 'right' else 'right'
            margin = sole_region_margin(values['pelvis.position'], values[side + '.heel.position'],
                                        values[side + '.forefoot.position'])
            assert abs(margin - balance['margin_m']) < .001
            if balance['settled']:
                assert margin >= .005
            assert values[other + '.sole.position'][2] >= .02
        low, high = skin_bounds(handle)
        assert low.z >= -.003 and abs(low.z - row['floor_m']) < .001, (frame, low.z, row['floor_m'])
        bounds.extend((low, high))
        for surface in handle.surfaces:
            if surface.size:
                penetration = seat_penetration(handle, surface)
                assert penetration <= .003, (frame, surface.name, penetration)
                maxima['surface_penetration_m'] = max(maxima['surface_penetration_m'], penetration)
    handle.scene.frame_set(1)
    return [[operation(point[i] for point in bounds) for i in range(3)] for operation in (min, max)], maxima


def main(key):
    out = case_path(key)
    result = numeric_valid(out)
    renderer = store.digest(Path(__file__))
    with store.producer_lease(out):
        recover_evidence(out)
        manifest, _, baked = validate_manifest(out)
        assert not manifest['views']
        motion_hash = store.digest(baked)
        profile = c.loads(c.AvatarProfile, (out / 'profile.json').read_text(encoding='utf-8'))
        motion = c.loads(c.ExecutableMotion, (out / 'executable.json').read_text(encoding='utf-8'))
        handle = store.open_preview(out)
        floor = handle.scene.objects.get('Preview floor')
        assert floor is not None and floor.type == 'MESH' and not floor.modifiers
        handle.objects.remove(floor)
        handle.environment.append(floor)
        handle.surfaces = tuple(Surface(**value) for value in result['stage_05_6b']['surfaces'])
        for surface in handle.surfaces:
            if surface.size:
                pad = handle.scene.objects.get('Support pad')
                assert pad is not None and pad.type == 'MESH'
                assert math.dist(pad.matrix_world.translation[:2], surface.center) < 1e-5
                assert math.dist(pad.dimensions[:2], surface.size) < 1e-5
                assert abs(pad.matrix_world.translation.z + pad.dimensions.z / 2 - surface.height) < 1e-5
                handle.objects.remove(pad)
                handle.environment.append(pad)
        bounds, maxima = verify(handle, profile, motion, result)
        store.atomic_json(out / 'support-playback.json', {
            'passed': True, 'frames': result['frames'], 'maxima': maxima, 'motion_sha256': motion_hash,
            'result_sha256': store.digest(out / 'result.json'), 'renderer_sha256': renderer,
            'runtime': runtime(), 'framing_sha256': store.digest(FRAMING),
        })
        views = {}
        plans = []
        for label in VIEWS:
            view = render_view(handle, profile, out, label, bounds, view_basis=rp._character_basis(handle))
            media, plan = encode_view(out, label, manifest['expected_frames'], fps=manifest['fps'],
                                      fps_base=manifest['fps_base'])
            view.update(media=media, sheet_sha256=store.digest(out / (label + '-sheet.png')))
            views[label] = view
            plans.append(plan)
            store.write_manifest(out, handle.scene, views=views, complete=False)
        store.write_manifest(out, handle.scene, views=views, complete=True)
        retire_pngs(out, plans)
        assert store.digest(baked) == motion_hash and store.digest(Path(__file__)) == renderer
    print('SUPPORT_RENDER_PASSED', out.parent.name, out.name, maxima, flush=True)


if __name__ == '__main__':
    main(sys.argv[sys.argv.index('--') + 1])
