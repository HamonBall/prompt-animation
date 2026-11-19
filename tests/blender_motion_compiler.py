"""Native Stage 07 smoke for a measured sequential activation."""
from pathlib import Path
from dataclasses import replace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.blender import rig_profile
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.motion import build_action, build_action_frames
from avatar_app.blender.scene import prepare_preview
from avatar_app.motion import Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment, compile_recipe, prepare_fragment, value_error
from avatar_app.movement_library.composer import compose_recipe
from avatar_app.movement_library.joints import catalog_for_profile
from test_recipe_composition import instance, recipe
from tools.preview_movement import capture_entry


def main(rig):
    handle = create_demo_avatar() if rig == 'demo' else import_avatar(str(ROOT / 'Hip Hop Mixamo.fbx'))
    prepare_preview(handle)
    profile = rig_profile.calibrate_joint_frames(handle, avatar_id='compiler.' + rig,
                                                  recorded_at='2026-11-19', include_head_aim=True)
    entry = capture_entry(handle, profile)
    catalog = catalog_for_profile(profile)
    first = instance(profile, catalog, 'first', 'head.look', yaw=10, hold_s=0.)
    second = instance(profile, catalog, 'second', 'head.look', yaw=-10, hold_s=0.)
    value = recipe(profile, entry, (first, second), (c.Relation('then', 'after', 'first', 'second', 0),))
    resolved = compose_recipe(value, entry, profile, (Surface(),), catalog)
    compiled = compile_recipe(resolved, entry, profile, catalog=catalog)
    assert c.loads(c.ExecutableMotion, c.dumps(compiled)) == compiled
    direct = prepare_fragment(build_fragment(first, entry, profile, (Surface(),), catalog), entry, profile)
    one = compile_recipe(compose_recipe(recipe(profile, entry, (first,)), entry, profile, (Surface(),), catalog),
                         entry, profile, catalog=catalog)
    direct_rows = build_action(handle, direct, profile=profile)['samples']
    recipe_rows = build_action(handle, one, profile=profile)['samples']
    assert len(direct_rows) == len(recipe_rows)
    for a, b in zip(direct_rows, recipe_rows, strict=True):
        assert a['targets'] == b['targets'] and a['time_s'] == b['time_s']
        for control in profile.controls:
            residual = value_error(a['measured'][control.id], b['measured'][control.id], control.value_shape)
            assert residual < (.001 if control.unit == 'metre' else .05), (control.id, residual)
    result = build_action(handle, compiled, profile=profile)
    assert result['frames'] == 61, result['frames']
    assert result['review']['passed'], result['review']
    ending = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    assert ending.captured_time_s == 2
    track = compiled.tracks[0]
    seam = result['samples'][30]['targets'][track.control_id]
    assert value_error(seam, track.curve.end_value, track.value_shape) < .05

    previous = handle.rig.animation_data.action
    frame = handle.scene.frame_current
    activation, = compiled.recipe_activation_v1
    changed = replace(activation, planned=replace(activation.planned, phase_landmarks=()))
    try:
        build_action(handle, replace(compiled, recipe_activation_v1=(changed,)), profile=profile)
    except c.MotionContractError as error:
        assert error.code == 'ENTRY_MISMATCH', error
        assert error.instance_id == 'second', error
    else:
        raise AssertionError('Altered activation topology was accepted')
    assert handle.rig.animation_data.action == previous
    assert handle.scene.frame_current == frame
    candidate = build_action_frames(handle, compiled, profile=profile)
    for _ in range(31):
        next(candidate)
    candidate.close()
    assert (handle.rig.animation_data.action, handle.scene.frame_current) == (previous, frame)
    previous_surfaces = handle.surfaces
    handle.surfaces = (*previous_surfaces, Surface('changed', .1, (0, 0), (.2, .2)))
    try:
        build_action(handle, compiled, profile=profile)
    except c.MotionContractError as error:
        assert error.code == 'STALE_REVISION', error
    else:
        raise AssertionError('Changed surfaces were accepted')
    finally:
        handle.surfaces = previous_surfaces
    assert handle.rig.animation_data.action == previous
    print(f'STAGE07 {rig} sequential smoke passed: 61 frames, measured seam and rollback')


def support_recipe(rig, route, pose, *, save=False):
    from blender_movement_coordinated_body_moves import setup, setup_floor_sit
    handle, profile, entry = (setup_floor_sit if route == 'seat' else setup)(rig, pose)
    surfaces = tuple(handle.surfaces)
    catalog = catalog_for_profile(profile)
    wave = instance(profile, catalog, 'wave', 'arm.stroke', side='right', amplitude_m=.04)
    if route == 'seat':
        base = instance(profile, catalog, 'base', 'body.floor_transfer', route='standing_to_seated')
        if rig == 'mixamo':
            wave = instance(profile, catalog, 'wave', 'arm.raise', side='right', angle=15)
        items = (base, wave)
        relations = (c.Relation('then', 'after', 'base', 'wave', 0),)
    elif route == 'step':
        base = instance(profile, catalog, 'base', 'body.step', side='right' if pose == 'crouched' else 'left',
                        distance_m=.06, clearance_m=.04)
        look = instance(profile, catalog, 'look', 'head.look', yaw=10)
        gesture = instance(profile, catalog, 'wave', 'arm.raise', side='right', angle=15)
        items = (base, gesture, look)
        relations = ()
    elif route == 'loop':
        items = (instance(profile, catalog, 'look', 'head.look', yaw=10, return_policy='return_to_entry'),)
        relations = ()
    else:
        items, relations = (wave,), ()
    value = recipe(profile, entry, items, relations)
    if route == 'loop':
        value = replace(value, loop=c.LoopSpec(2, c.Transform((0, 0, 0), (1, 0, 0, 0), 'entry_body', 'metre'),
                                              3, .01, 10))
    resolved = compose_recipe(value, entry, profile, surfaces, catalog)
    motion = compile_recipe(resolved, entry, profile, surfaces=surfaces, catalog=catalog)
    try:
        result = build_action(handle, motion, profile=profile)
    except c.MotionContractError as error:
        print('STAGE07_ROUTE_ERROR', error.to_dict(), flush=True)
        raise
    ending = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    assert set(ending.active_contacts) == ({'left.sole', 'right.sole', 'pelvis.support'} if route == 'seat'
                                           else set(entry.active_contacts))
    if route == 'loop':
        assert len(result['loop_seams']) == 2
    if save:
        from tools import artifact_store as store
        from tools.storage_policy import ARTIFACTS, MiB, enforce
        out = ARTIFACTS / 'stages/07' / rig / (route + '-' + pose)
        enforce(out, growth=8 * MiB, temporary=32 * MiB)
        with store.producer_lease(out):
            for name, record in (('profile', profile), ('entry', entry), ('resolved', resolved), ('executable', motion)):
                store.atomic_json(out / (name + '.json'), c.to_dict(record), compact=True)
            store.atomic_json(out / 'result.json', result, compact=True)
            store.write_source_identity(out, rig)
            handle.scene.frame_set(1)
            store.save_scene(out / 'preview.blend')
            store.write_manifest(out, handle.scene, complete=False,
                                 metadata=store.entry_metadata(pose, {'route': route}, handle.scene))
    print(f'STAGE07 {rig} {route} {pose}: {result["frames"]} frames', result['review']['metrics'], flush=True)


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else ['demo']
    rig = args[0]
    assert rig in ('demo', 'mixamo'), rig
    if len(args) > 1:
        support_recipe(*args[:3], save=args[3:] == ['save'])
    else:
        main(rig)
