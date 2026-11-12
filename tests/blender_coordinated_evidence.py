"""Publish and independently replay coordinated motion before lossless rendering."""
from dataclasses import asdict
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.blender import rig_profile as rp
from avatar_app.blender.geometry import seat_penetration, skin_bounds, support_skin_height
from avatar_app.blender.motion import build_action, capture_sample, contact_ease, review_samples
from avatar_app.blender.support_mechanics import body_contact_point, calibrate_support, support_part
from avatar_app.motion import Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import value_error
from avatar_app.movement_library.root_motion import POSITION
from avatar_app.movement_library.support import BODY_ANCHORS, PALM_ANCHORS
from blender_movement_coordinated_body_moves import check_takeoff, setup_floor_sit, setup_lunge
from blender_movement_crawl import setup_crawl
from blender_movement_root_travel_flight import setup
from blender_support_body import body_fixture
from test_movement_support_transfers import compile_support
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.coordinated_evidence import CASES, FRAMING, HARNESS, NATIVE, VIEWS, case_path, numeric_valid, runtime
from tools.lossless_evidence import encode_view, recover_evidence, retire_pngs
from tools.preview_movement import capture_entry
from tools.render_root_motion import render_view


def make_entry(rig, spec):
    move, pose = spec['move'], spec['pose']
    parameters = dict(spec['parameters'])
    route = parameters.get('route')
    if move == 'body.lunge':
        handle, profile, entry = setup_lunge(rig, pose, parameters['lead'])
    elif move == 'body.crawl':
        handle, profile, entry = setup_crawl(rig, pose)
    elif route in ('standing_to_seated', 'seated_to_back'):
        handle, profile, entry = setup_floor_sit(rig, pose)
        if route == 'seated_to_back':
            approach = compile_support(profile, entry, move, {'route': 'standing_to_seated'}, handle.surfaces)
            solved = build_action(handle, approach, profile=profile)
            assert solved['review']['passed']
            handle.scene.frame_set(handle.scene.frame_end)
            entry = c.from_dict(c.MotionStateSnapshot, solved['ending_state'])
    elif route == 'planted_to_knee':
        handle, profile, _ = setup(rig, pose)
        profile = calibrate_support(handle, profile)
        entry = capture_entry(handle, profile)
    elif pose in ('pelvis', 'knee'):
        handle, profile, entry, surface, _ = body_fixture(rig, pose)
        parameters['surface'] = surface.name
    else:
        handle, profile, entry = setup(rig, pose)
    return handle, profile, entry, parameters


def bake(key):
    out = case_path(key)
    spec = CASES[key]
    producer = store.input_identity(out)['producer_sha256']
    harness = {name: store.digest(ROOT / name) for name in HARNESS}
    handle, profile, entry, parameters = make_entry(out.parent.name, spec)
    motion = compile_support(profile, entry, spec['move'], parameters, handle.surfaces)
    try:
        result = build_action(handle, motion, profile=profile)
    except c.PlanError as error:
        diagnostic = error.to_dict() if isinstance(error, c.MotionContractError) else str(error)
        print('COORDINATED_NUMERIC_FAILED', getattr(error, 'review', None) or diagnostic, flush=True)
        raise
    assert result['review']['passed'] and result['frames'] <= spec['max_frames']
    if spec['move'] == 'body.takeoff_land':
        check_takeoff(motion, result['samples'])
        assert result['review']['metrics']['contact_error_m'] < .001
    assert producer == store.input_identity(out)['producer_sha256']
    assert all(store.digest(ROOT / name) == digest for name, digest in harness.items())
    result['stage_05_6c'] = {'key': key, 'spec': spec, 'parameters': parameters, 'producer': producer,
                            'harness': harness, 'surfaces': [asdict(surface) for surface in handle.surfaces]}
    with store.producer_lease(out):
        for name, value in (('profile', profile), ('entry', entry), ('executable', motion)):
            store.atomic_json(out / (name + '.json'), c.to_dict(value))
        store.write_source_identity(out, out.parent.name)
        store.atomic_json(out / 'result.json', result, compact=True)
        handle.scene.frame_set(1)
        store.save_scene(out / 'preview.blend')
        store.write_manifest(out, handle.scene, metadata=store.entry_metadata('authored:' + spec['pose'], parameters,
                                                                                handle.scene), complete=False)
    print('COORDINATED_NUMERIC_PASSED', out.parent.name, out.name, result['frames'], flush=True)


def restore_surfaces(handle, result):
    floor = handle.scene.objects.get('Preview floor')
    assert floor is not None and floor.type == 'MESH' and not floor.modifiers
    handle.objects.remove(floor)
    handle.environment.append(floor)
    handle.surfaces = tuple(Surface(**value) for value in result['stage_05_6c']['surfaces'])
    for surface in handle.surfaces:
        if surface.size:
            pad, = (obj for obj in handle.objects if obj.type == 'MESH' and not obj.modifiers
                    and math.dist(obj.matrix_world.translation[:2], surface.center) < 1e-5
                    and math.dist(obj.dimensions[:2], surface.size) < 1e-5
                    and abs(obj.matrix_world.translation.z + obj.dimensions.z / 2 - surface.height) < 1e-5)
            handle.objects.remove(pad)
            handle.environment.append(pad)


def replay_contacts(handle, profile, motion, time, values, row, captured, surfaces):
    held = {}
    for event in motion.contact_events:
        if not event.interval.start_s <= time <= event.interval.end_s:
            continue
        key = event.anchor_id
        acquire = min(1, (time - event.interval.start_s) / event.acquire_s) if event.acquire_s else 1
        release = min(1, (event.interval.end_s - time) / event.release_s) if event.release_s else 1
        weight = min(acquire, release)
        if event.target_world_v1 is not None:
            if weight >= 1 - 1e-9:
                held[key] = (event.target_world_v1, surfaces[event.surface_id])
        else:
            if event.acquire_s and event.interval.start_s > 0:
                point = captured.setdefault(event.event_id, values[key + '.position'])
            else:
                point = captured[key]
            if contact_ease(weight) > 1e-8:
                held[key] = (point, surfaces[event.surface_id])
    actual = ({key: value['position'] for key, value in row['active_support_anchors'].items()}
              if 'active_support_anchors' in row else row['active_foot_anchors'])
    assert held.keys() == actual.keys(), (row['frame'], held.keys(), actual.keys())
    errors = {}
    for key, (point, surface) in held.items():
        assert math.dist(actual[key], point) < .001
        measured = body_contact_point(handle, profile, key, surface) if key in BODY_ANCHORS else values[key + '.position']
        errors[key] = math.dist(measured, point)
        assert errors[key] < .001, (row['frame'], key, errors[key])
        if key in PALM_ANCHORS + BODY_ANCHORS:
            gap = abs(support_skin_height(handle, support_part(key), surface) - surface.height)
            assert gap <= .025 and abs(gap - row['support_skin_gaps_m'][key]) < .001
            errors[key] = max(errors[key], gap)
    return errors


def verify_playback(handle, profile, motion, result):
    scene = handle.scene
    assert (scene.frame_start, scene.frame_end) == (1, result['frames'])
    assert (scene.render.fps, scene.render.fps_base) == (motion.fps, 1)
    controls = {item.id: item for item in profile.controls}
    captured = {anchor.anchor_id: anchor.position for anchor in motion.entry_snapshot.contact_anchors}
    surfaces = {surface.name: surface for surface in handle.surfaces}
    surfaces.setdefault('floor', Surface())
    root_moves = any(track.control_id == POSITION for track in motion.tracks)
    bounds, samples = [], []
    maxima = {'position_m': 0., 'angle_deg': 0.}
    handle._skin_cache_enabled = True
    try:
        for frame, row in enumerate(result['samples'], 1):
            scene.frame_set(frame)
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
            errors = replay_contacts(handle, profile, motion, time, values, row, captured, surfaces)
            sample = capture_sample(handle, frame, errors=errors)
            if root_moves:
                sample['rotations']['object_root'] = handle.rig.matrix_world.to_quaternion()
            sample['surfaces'] = {surface.name: seat_penetration(handle, surface) for surface in handle.surfaces if surface.size}
            assert abs(sample['floor'] - row['floor_m']) < .001
            bounds.extend(skin_bounds(handle))
            samples.append(sample)
    finally:
        handle._skin_cache_enabled = False
    review = review_samples(samples, height=profile.height_m, fps=motion.fps)
    assert review.passed, review.to_dict()
    scene.frame_set(1)
    sweep = [[operation(point[i] for point in bounds) for i in range(3)] for operation in (min, max)]
    return sweep, {**maxima, **review.metrics}


def render(key):
    out = case_path(key)
    result = numeric_valid(key)
    validator = store.digest(NATIVE)
    framing = store.digest(FRAMING)
    with store.producer_lease(out):
        recover_evidence(out)
        manifest, _, baked = validate_manifest(out)
        assert not manifest['views']
        motion_hash = store.digest(baked)
        profile = c.loads(c.AvatarProfile, (out / 'profile.json').read_text(encoding='utf-8'))
        motion = c.loads(c.ExecutableMotion, (out / 'executable.json').read_text(encoding='utf-8'))
        handle = store.open_preview(out)
        restore_surfaces(handle, result)
        bounds, maxima = verify_playback(handle, profile, motion, result)
        store.atomic_json(out / 'playback.json', {
            'passed': True, 'frames': result['frames'], 'maxima': maxima, 'motion_sha256': motion_hash,
            'result_sha256': store.digest(out / 'result.json'), 'validator_sha256': validator,
            'framing_sha256': framing, 'runtime': runtime(),
        })
        views, retirement = {}, []
        for label in VIEWS:
            view = render_view(handle, profile, out, label, bounds)
            media, plan = encode_view(out, label, manifest['expected_frames'], fps=manifest['fps'],
                                      fps_base=manifest['fps_base'])
            view.update(media=media, sheet_sha256=store.digest(out / (label + '-sheet.png')))
            views[label] = view
            retirement.append(plan)
            store.write_manifest(out, handle.scene, views=views, complete=False)
        store.write_manifest(out, handle.scene, views=views, complete=True)
        retire_pngs(out, retirement)
        assert motion_hash == store.digest(baked) and validator == store.digest(NATIVE) and framing == store.digest(FRAMING)
    print('COORDINATED_RENDER_PASSED', out.parent.name, out.name, maxima, flush=True)


if __name__ == '__main__':
    phase, key = sys.argv[sys.argv.index('--') + 1:]
    {'numeric': bake, 'render': render}[phase](key)
