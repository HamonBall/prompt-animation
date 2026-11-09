"""Exercise root motion on the existing Demo and Mixamo rigs."""
import argparse
from pathlib import Path
import sys
import time

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.blender import rig_profile as rp
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.foot_mechanics import calibrate_feet
from avatar_app.blender.motion import build_action, build_action_frames
from avatar_app.blender.scene import prepare_preview
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import value_error
from avatar_app.movement_library.root_motion import ORIENTATION, POSITION
from blender_movement_hips_knees import fixture
from test_movement_root_travel_flight import compile_case
from tools import artifact_store as store
from tools.preview_movement import capture_entry
from tools.storage_policy import ARTIFACTS, enforce


CASES = {
    'hover': ('root.hover', {}, 'neutral'),
    'hover-low': ('root.hover', {'elevation_m': .2, 'duration_s': 1.5, 'hold_s': .2}, 'neutral'),
    'hover-high': ('root.hover', {'elevation_m': 2.5, 'duration_s': 3.5, 'hold_s': 1.5}, 'turned'),
    'hover-air': ('root.hover', {'mode': 'airborne', 'elevation_m': .8}, 'air-turned'),
    'line': ('root.travel', {}, 'air-turned'),
    'line-short': ('root.travel', {'distance_m': .1, 'duration_s': 1.5, 'heading_deg': -180, 'frame': 'world'}, 'air'),
    'line-long': ('root.travel', {'distance_m': 2, 'duration_s': 3.5, 'heading_deg': 180, 'frame': 'world'}, 'air-turned'),
    'arc-left': ('root.travel', {'path': 'arc', 'arc_deg': 90, 'distance_m': 2}, 'air-turned'),
    'arc-right': ('root.travel', {'path': 'arc', 'arc_deg': -90, 'frame': 'world'}, 'air'),
    'arc-shallow': ('root.travel', {'path': 'arc', 'arc_deg': 15, 'distance_m': .1}, 'air'),
    'turn-left': ('root.turn', {'angle_deg': 120}, 'air-turned'),
    'turn-right': ('root.turn', {'angle_deg': -120, 'duration_s': 1.5}, 'air'),
    'pivot-left': ('root.turn', {'mode': 'grounded_pivot', 'angle_deg': 20}, 'raised-right'),
    'pivot-right': ('root.turn', {'mode': 'grounded_pivot', 'angle_deg': -20}, 'turned-raised-left'),
    'pitch': ('root.orient', {'angle_deg': 90}, 'air-turned'),
    'roll': ('root.orient', {'axis': 'roll', 'angle_deg': -90, 'frame': 'world'}, 'air-turned'),
}
SOURCES = (
    'tests/blender_movement_root_travel_flight.py', 'tests/test_movement_root_travel_flight.py',
    'tests/blender_movement_hips_knees.py', 'tools/preview_movement.py',
    'tests/fixtures/movement_fragments/v1/entry-neutral.json',
)


def setup(rig, pose):
    handle = create_demo_avatar() if rig == 'demo' else import_avatar(str(ROOT / 'Hip Hop Mixamo.fbx'))
    prepare_preview(handle)
    profile = calibrate_feet(handle, rp.calibrate_joint_frames(
        handle, avatar_id='root.' + rig, recorded_at='2026-11-09', include_head_aim=True,
    ))
    entry = fixture(handle, profile, pose, 'right' if pose.endswith('-right') else 'left')
    if pose.startswith('air'):
        handle.rig.matrix_world = Matrix.Translation(Vector((.35, .2, 1.25))) @ handle.rig.matrix_world
        bpy.context.view_layer.update()
        entry = capture_entry(handle, profile)
        assert not entry.active_contacts
    return handle, profile, entry


def measure_case(handle, profile, entry, motion):
    result = build_action(handle, motion, profile=profile)
    assert result['review']['passed']
    samples = result['samples']
    assert len(samples) == result['frames'] and samples[-1]['time_s'] == motion.duration_s
    assert max(sample['tracking_errors'][POSITION] for sample in samples) < .001
    assert max(sample['tracking_errors'][ORIENTATION] for sample in samples) < .05
    for frame, sample in enumerate(samples, 1):
        handle.scene.frame_set(frame)
        actual = handle.rig.matrix_world
        assert value_error(tuple(actual.translation), sample['measured'][POSITION]) < .001
        assert value_error(tuple(actual.to_quaternion()), sample['measured'][ORIENTATION], 'quaternion') < .05
    return result


def boundaries(rig):
    handle, profile, entry = setup(rig, 'neutral')
    try:
        compile_case(profile, entry, 'root.turn', {'mode': 'grounded_pivot', 'angle_deg': 15})
    except c.MotionContractError as error:
        assert error.code == 'CONSTRAINT_CONFLICT'
    else:
        raise AssertionError('Turn bypassed two locked soles')
    _, _, hover = compile_case(profile, entry, 'root.hover', {})
    measure_case(handle, profile, entry, hover)
    entry = capture_entry(handle, profile)
    action = handle.rig.animation_data.action
    basis = handle.rig.matrix_world.copy()
    timeline = handle.scene.frame_start, handle.scene.frame_end, handle.scene.frame_current
    _, _, line = compile_case(profile, entry, 'root.travel', {})
    candidate = build_action_frames(handle, line, profile=profile)
    for _ in range(12):
        next(candidate)
    assert (handle.rig.matrix_world.translation - basis.translation).length > .01
    candidate.close()
    assert handle.rig.animation_data.action == action
    assert (handle.rig.matrix_world.translation - basis.translation).length < 1e-5
    assert (handle.scene.frame_start, handle.scene.frame_end, handle.scene.frame_current) == timeline
    result = measure_case(handle, profile, entry, line)
    ending = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    assert not ending.active_contacts and not ending.contact_anchors
    _, _, turn = compile_case(profile, ending, 'root.turn', {})
    continued = measure_case(handle, profile, ending, turn)
    assert value_error(continued['samples'][0]['measured'][POSITION], result['samples'][-1]['measured'][POSITION]) < .001
    assert all(sample['floor_m'] > .02 for sample in continued['samples'])
    print('ROOT_BOUNDARIES_PASSED', rig, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rig', choices=('demo', 'mixamo'), required=True)
    parser.add_argument('--case', choices=(*CASES, 'boundaries'), required=True)
    parser.add_argument('--save', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if args.case == 'boundaries':
        boundaries(args.rig)
        return
    move, params, pose = CASES[args.case]
    out = ARTIFACTS / 'stages/05.6a' / args.rig / args.case
    source = store.input_identity(out)['producer_sha256']
    harness = {path: store.digest(ROOT / path) for path in SOURCES}
    started = time.perf_counter()
    handle, profile, entry = setup(args.rig, pose)
    instance, fragment, motion = compile_case(profile, entry, move, params)
    prepared = time.perf_counter()
    try:
        result = measure_case(handle, profile, entry, motion)
    except Exception as error:
        print('ROOT_NUMERIC_FAILED', getattr(error, 'review', None) or
              (error.to_dict() if hasattr(error, 'to_dict') else str(error)), flush=True)
        raise
    assert source == store.input_identity(out)['producer_sha256']
    assert all(store.digest(ROOT / path) == digest for path, digest in harness.items())
    result['stage_05_6a'] = {
        'case': args.case, 'rig': args.rig, 'fixture': pose, 'stage_producer': harness,
        'application_producer_sha256': source,
        'timings_s': {'prepare': prepared - started, 'execute_and_playback': time.perf_counter() - prepared},
    }
    if args.save:
        enforce(out, growth=8 * 1024**2, temporary=32 * 1024**2)
        with store.producer_lease(out):
            for name, record in (('profile', profile), ('entry', entry), ('instance', instance),
                                 ('fragment', fragment), ('executable', motion)):
                (out / (name + '.json')).write_text(c.dumps(record), encoding='utf-8')
            store.write_source_identity(out, args.rig)
            store.atomic_json(out / 'result.json', result, compact=True)
            handle.scene.frame_set(1)
            store.save_scene(out / 'preview.blend')
            store.write_manifest(out, handle.scene, metadata=store.entry_metadata('authored:' + pose, params, handle.scene),
                                 complete=False)
    print('ROOT_NUMERIC_PASSED', args.rig, args.case, result['frames'], result['review'], flush=True)


if __name__ == '__main__':
    main()
