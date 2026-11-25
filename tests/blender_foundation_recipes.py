"""Exercise Stage 08 candidates without writing an artifact bundle."""

from dataclasses import replace
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.blender.motion import build_action, build_action_frames, mesh_floor
from avatar_app.blender.geometry import support_skin_height
from avatar_app.blender.requests import bake_request, bind_foundation, request_frames
from avatar_app.blender.rig_profile import measure_endpoint, measure_joint_angle, measure_orientation
from avatar_app.blender.scene import resolve_seat
from avatar_app.blender.support_mechanics import calibrate_support
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import compile_recipe, value_error
from avatar_app.movement_library.composer import compose_recipe
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.recipes import (
    compile_floor_sit_sequence, compile_lie_sequence, compile_run_sequence, compile_walk_sequence, foundation_recipe,
)
from avatar_app.movement_library.spatial import rotate
from avatar_app.motion import scale_timing
from avatar_app.planning.presets import preset_plan, select_motion_foundation
from avatar_app.planning.movements import floor_sitting_plan, sitting_plan
from avatar_app.planning.routes import select_common_foundation
from blender_movement_coordinated_body_moves import check_takeoff, setup, setup_floor_sit
from blender_support_body import body_fixture
from tools.preview_movement import capture_entry


def compile_foundation(name, handle, profile, entry, **options):
    catalog = catalog_for_profile(profile)
    recipe = foundation_recipe(name, entry, profile, **options)
    resolved = compose_recipe(recipe, entry, profile, handle.surfaces, catalog)
    return compile_recipe(resolved, entry, profile, surfaces=handle.surfaces, catalog=catalog)


def bake_jump(handle, profile, entry, compact=False):
    motion = compile_foundation('jump', handle, profile, entry, compact_jump=compact)
    result = build_action(handle, motion, profile=profile)
    assert result['review']['passed'], result['review']
    rows = result['samples']
    support_motion = SimpleNamespace(entry_snapshot=motion.entry_snapshot,
                                     tracks=tuple(track for track in motion.tracks
                                                  if not track.control_id.endswith('.upper_arm.orientation')),
                                     contact_events=motion.contact_events, duration_s=motion.duration_s)
    check_takeoff(support_motion, rows)
    ending = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    anchors = {anchor.anchor_id: anchor.position for anchor in entry.contact_anchors}
    assert set(ending.active_contacts) == set(entry.active_contacts)
    for anchor in ending.contact_anchors:
        if anchor.anchor_id in ending.active_contacts:
            assert value_error(anchor.position, anchors[anchor.anchor_id]) < .002
    return result


def jump_playback(handle, profile):
    scene = handle.scene
    start = scene.frame_start
    frames = range(start, scene.frame_end + 1)
    sides = ('Left', 'Right')
    sole_ids = tuple(side.lower() + '.sole' for side in sides)
    scene.frame_set(start)
    start_soles = tuple(measure_endpoint(handle, profile, key) for key in sole_ids)
    start_hips = handle.rig.matrix_world @ handle.bones['Hips'].head
    start_arms = tuple(tuple(handle.bones[side + 'Arm'].matrix_basis.to_quaternion()) for side in sides)
    peak_clearance = 0.
    arm_excursion = [0., 0.]
    airborne = []
    for frame in frames:
        scene.frame_set(frame)
        soles = tuple(measure_endpoint(handle, profile, key) for key in sole_ids)
        floor = mesh_floor(handle)
        peak_clearance = max(peak_clearance, floor)
        # Use the same playback threshold for both paths. Report sample times
        # separately from the compiler's authored release and acquire events.
        if floor > .01 and all(point[2] - origin[2] > .025
                               for point, origin in zip(soles, start_soles, strict=True)):
            airborne.append(frame - start)
        for index, side in enumerate(sides):
            orientation = tuple(handle.bones[side + 'Arm'].matrix_basis.to_quaternion())
            excursion = value_error(orientation, start_arms[index], 'quaternion')
            arm_excursion[index] = max(arm_excursion[index], excursion)

    fps = scene.render.fps / scene.render.fps_base
    assert airborne and airborne[0] > 0 and airborne[-1] < len(frames) - 1
    assert airborne == list(range(airborne[0], airborne[-1] + 1)), airborne
    end_hips = handle.rig.matrix_world @ handle.bones['Hips'].head
    return {
        'duration_s': (len(frames) - 1) / fps,
        'flight_first_s': airborne[0] / fps,
        'flight_last_s': airborne[-1] / fps,
        'flight_samples': len(airborne),
        'peak_clearance_m': peak_clearance,
        'end_horizontal_pelvis_drift_m': (end_hips - start_hips).xy.length,
        'end_sole_drift_m': max(value_error(point, origin)
                                for point, origin in zip(soles, start_soles, strict=True)),
        'upper_arm_excursion_deg': dict(zip(sides, arm_excursion, strict=True)),
    }


def floor_continuation(rig, pose):
    if pose in ('neutral', 'neutral-arms'):
        handle, profile, _ = setup(rig, 'neutral')
        profile = calibrate_support(handle, profile)
        entry = capture_entry(handle, profile)
    else:
        handle, profile, entry = setup_floor_sit(rig, pose)
    seated = compile_foundation('sit_floor', handle, profile, entry, floor_sit_arms=pose == 'neutral-arms')
    first = bake_floor_segment('sit', handle, profile, seated)
    assert first['review']['passed'], first['review']
    soles = {'left.sole', 'right.sole'}
    assert all(soles <= set(row['active_support_anchors']) for row in first['samples'])
    ending = c.from_dict(c.MotionStateSnapshot, first['ending_state'])
    assert set(ending.active_contacts) == soles | {'pelvis.support'}
    assert first['samples'][-1]['support_skin_gaps_m']['pelvis.support'] < .003

    handle.scene.frame_set(handle.scene.frame_end)
    lying = compile_foundation('lie_back', handle, profile, ending)
    second = bake_floor_segment('lie', handle, profile, lying)
    assert second['review']['passed'], second['review']
    first_pose = first['samples'][-1]['measured']
    second_pose = second['samples'][0]['measured']
    assert value_error(first_pose['pelvis.position'], second_pose['pelvis.position']) < .002
    assert value_error(first_pose['pelvis.orientation'], second_pose['pelvis.orientation'], 'quaternion') < .05
    assert all(soles <= set(row['active_support_anchors']) for row in second['samples'])
    final = c.from_dict(c.MotionStateSnapshot, second['ending_state'])
    assert set(final.active_contacts) == soles | {'back.support'}
    print('FOUNDATION_FLOOR_CONTINUATION_PASSED', rig, pose,
          json.dumps({'sit': first['review']['metrics'], 'lie': second['review']['metrics']}), flush=True)


def bake_floor_segment(name, handle, profile, motion):
    try:
        return build_action(handle, motion, profile=profile)
    except c.PlanError as error:
        diagnostic = error.to_dict() if isinstance(error, c.MotionContractError) else getattr(error, 'review', {})
        print('FOUNDATION_FLOOR_REJECTED', name, json.dumps(diagnostic), flush=True)
        raise


def floor_playback(handle, profile):
    scene = handle.scene
    start, end = scene.frame_start, scene.frame_end
    scene.frame_set(start)
    initial_pelvis = handle.rig.matrix_world @ handle.bones['Hips'].head
    ids = ('left.sole', 'right.sole')
    initial_soles = tuple(measure_endpoint(handle, profile, key) for key in ids)
    minimum_floor = float('inf')
    first_pelvis_support = None
    fps = scene.render.fps / scene.render.fps_base
    for frame in range(start, end + 1):
        scene.frame_set(frame)
        minimum_floor = min(minimum_floor, mesh_floor(handle))
        gap = support_skin_height(handle, 'pelvis')
        if first_pelvis_support is None and abs(gap) <= .003:
            first_pelvis_support = (frame - start) / fps
    end_pelvis = handle.rig.matrix_world @ handle.bones['Hips'].head
    ending_soles = tuple(measure_endpoint(handle, profile, key) for key in ids)
    return {
        'duration_s': (end - start) / fps,
        'pelvis_support_first_s': first_pelvis_support,
        'pelvis_floor_gap_m': gap,
        'floor_penetration_m': max(0., -minimum_floor),
        'pelvis_horizontal_travel_m': (end_pelvis - initial_pelvis).xy.length,
        'pelvis_final_height_m': end_pelvis.z,
        'ending_leg_angles_deg': {key: measure_joint_angle(handle, profile, key)
                                 for side in ('left', 'right')
                                 for key in (side + '.hip.flexion', side + '.knee.flexion',
                                             side + '.ankle.flexion')},
        'ending_sole_displacement_m': dict(zip(ids, (value_error(a, b) for a, b in
                                                     zip(initial_soles, ending_soles, strict=True)), strict=True)),
    }


def compare_floor_sit(rig, baseline_only):
    legacy, legacy_profile, _ = setup(rig, 'neutral')
    baseline = build_action(legacy, floor_sitting_plan())
    assert baseline['review']['passed'], baseline['review']
    legacy_measured = floor_playback(legacy, legacy_profile)
    if baseline_only:
        print('FOUNDATION_FLOOR_BASELINE', rig, json.dumps(legacy_measured), flush=True)
        return

    handle, profile, _ = setup(rig, 'neutral')
    profile = calibrate_support(handle, profile)
    entry = capture_entry(handle, profile)
    candidate = compile_foundation('sit_floor', handle, profile, entry, floor_sit_arms=True)
    candidate_result = bake_floor_segment('sit', handle, profile, candidate)
    assert candidate_result['review']['passed'], candidate_result['review']
    print('FOUNDATION_FLOOR_COMPARISON', rig,
          json.dumps({'legacy': legacy_measured, 'recipe': floor_playback(handle, profile)}), flush=True)


def walk_playback(handle, profile):
    scene = handle.scene
    start, end = scene.frame_start, scene.frame_end
    keys = ('left.sole', 'right.sole')

    def measure(frame):
        scene.frame_set(frame)
        return (handle.rig.matrix_world @ handle.bones['Hips'].head,
                tuple(measure_endpoint(handle, profile, key) for key in keys))

    first_pelvis, first_feet = measure(start)
    last_pelvis, last_feet = measure(end)
    return {
        'duration_s': (end - start) * scene.render.fps_base / scene.render.fps,
        'pelvis_travel_m': (last_pelvis - first_pelvis).xy.length,
        'pelvis_height_change_m': last_pelvis.z - first_pelvis.z,
        'sole_travel_m': [value_error(a, b) for a, b in zip(first_feet, last_feet, strict=True)],
        'stance_width_m': (Vector(last_feet[0]) - Vector(last_feet[1])).xy.length,
    }


def gait_upper_body_playback(handle, profile):
    scene = handle.scene
    bones = {side + '.upper_arm': handle.bones[side.title() + 'Arm'] for side in ('left', 'right')}
    bones['torso'] = handle.bones['Spine']
    scene.frame_set(scene.frame_start)
    initial = {key: tuple(bone.matrix_basis.to_quaternion()) for key, bone in bones.items()}
    excursions = dict.fromkeys(bones, 0.)
    elbows = {side: [] for side in ('left', 'right')}
    for frame in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(frame)
        for key, bone in bones.items():
            rotation = tuple(bone.matrix_basis.to_quaternion())
            excursions[key] = max(excursions[key], value_error(rotation, initial[key], 'quaternion'))
        for side, values in elbows.items():
            values.append(measure_joint_angle(handle, profile, side + '.elbow.flexion'))
    return {'local_excursion_deg': excursions, 'elbow_range_deg': {
        side: (min(values), max(values)) for side, values in elbows.items()
    }}


def prepare_walk_entry(handle, profile, entry):
    instance = c.MovementInstance('load', 'pelvis.raise_lower', 1, (
        c.ParameterValue('distance_m', -.04),
        c.ParameterValue('duration_s', 1.),
        c.ParameterValue('hold_s', 0.),
        c.ParameterValue('return_policy', 'preserve_end'),
    ), ('request',))
    recipe = c.MotionRecipe('recipe.walk_load', profile.avatar_id, profile.version, entry.revision,
                            'new', (instance,), (), (), (), None,
                            (c.ClauseCoverage('request', 'Load both planted legs', 'fulfilled', ('load',)),))
    catalog = catalog_for_profile(profile)
    resolved = compose_recipe(recipe, entry, profile, handle.surfaces, catalog)
    motion = compile_recipe(resolved, entry, profile, surfaces=handle.surfaces, catalog=catalog)
    result = build_action(handle, motion, profile=profile)
    rows = result['samples']
    assert result['review']['passed']
    assert all(set(row['active_foot_anchors']) == set(entry.active_contacts) for row in rows)
    assert abs(rows[-1]['measured']['pelvis.position'][2] - rows[0]['measured']['pelvis.position'][2] + .04) < .002
    handle.scene.frame_set(handle.scene.frame_end)
    return c.from_dict(c.MotionStateSnapshot, result['ending_state'])


def compare_walk(rig, count, recipe_pose):
    legacy, legacy_profile, _ = setup(rig, 'neutral')
    baseline = build_action(legacy, preset_plan('walk', steps=count))
    assert baseline['review']['passed'], baseline['review']
    legacy_measured = walk_playback(legacy, legacy_profile)

    handle, profile, entry = setup(rig, 'neutral' if recipe_pose == 'loaded' else recipe_pose)
    if recipe_pose == 'loaded':
        entry = prepare_walk_entry(handle, profile, entry)
    try:
        motion = compile_foundation('walk', handle, profile, entry, steps=count)
    except c.MotionContractError as error:
        print('FOUNDATION_WALK_REJECTED', rig, count, recipe_pose, json.dumps(error.to_dict()),
              'legacy', json.dumps(legacy_measured), flush=True)
        raise
    result = build_action(handle, motion, profile=profile)
    assert result['review']['passed'], result['review']
    rows = result['samples']
    start_pelvis = next(value.value for value in entry.measured_controls if value.control_id == 'pelvis.position')
    assert value_error(rows[0]['measured']['pelvis.position'], start_pelvis) < .002
    assert all(row['active_foot_anchors'] for row in rows)
    soles = {'left.sole', 'right.sole'}
    assert set(rows[0]['active_foot_anchors']) == set(rows[-1]['active_foot_anchors']) == soles
    single_support = []
    for row in rows:
        active = frozenset(row['active_foot_anchors'])
        if not single_support or active != single_support[-1]:
            single_support.append(active)
    assert [next(iter(stance)) for stance in single_support if len(stance) == 1] == (
        ['right.sole', 'left.sole'] * (count // 2))
    print('FOUNDATION_WALK_COMPARISON', rig, count, recipe_pose,
          json.dumps({'legacy': legacy_measured, 'recipe': walk_playback(handle, profile),
                      'planted_throughout': True, 'frames': len(rows)}), flush=True)


def atomic_walk(rig, count, preset_travel=False, pose='neutral', arm_motion=False, save=False):
    handle, profile, entry = setup(rig, pose)
    preset_height = (handle.rig.matrix_world.to_3x3() @ (handle.up * handle.height)).length
    first, continuations = compile_walk_sequence(entry, profile, handle.surfaces,
                                                 steps=count, preset_height_m=preset_height if preset_travel else None,
                                                 arm_motion=arm_motion)
    try:
        result = build_action(handle, first, profile=profile, continuations=continuations)
    except c.MotionContractError as error:
        print('FOUNDATION_ATOMIC_WALK_REJECTED', rig, count, json.dumps(error.to_dict()), flush=True)
        raise
    assert result['review']['passed'], result['review']
    rows = result['samples']
    assert [row['frame'] for row in rows] == list(range(1, len(rows) + 1))
    assert rows[-1]['time_s'] == (len(rows) - 1) / first.fps
    assert len(rows) == (103 + count * 36 if preset_travel else 61 + count * 60)
    soles = {'left.sole', 'right.sole'}
    assert all(row['active_foot_anchors'] for row in rows)
    assert all(set(row['active_foot_anchors']) == soles for row in rows
               if row['segment'] in (0, len(continuations)))
    assert abs(rows[0]['measured']['pelvis.position'][2] - rows[-1]['measured']['pelvis.position'][2]) < .002
    end = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    assert end.captured_time_s == rows[-1]['time_s'] and set(end.active_contacts) == soles
    if preset_travel:
        initial = {anchor.anchor_id: anchor.position for anchor in entry.contact_anchors}
        travel = .13 * preset_height * count
        for index in range(1, count + 2):
            stance = {'right.sole' if index % 2 else 'left.sole'}
            assert any(row['segment'] == index and set(row['active_foot_anchors']) == stance for row in rows)
        start = Vector(rows[0]['measured']['pelvis.position'])
        finish = Vector(rows[-1]['measured']['pelvis.position'])
        forward = Vector(rotate(entry.root_transform.orientation, (0, 1, 0))).xy.normalized()
        assert ((finish - start).xy - travel * forward).length < .003
        achieved = (finish - start).xy.length
        for anchor in end.contact_anchors:
            if anchor.anchor_id in soles:
                assert abs(value_error(anchor.position[:2], initial[anchor.anchor_id][:2]) - travel) < .003
    if arm_motion:
        for side in ('left', 'right'):
            key = side + '.upper_arm.orientation'
            initial_arm = rows[0]['measured'][key]
            largest = max(value_error(row['measured'][key], initial_arm, 'quaternion') for row in rows)
            assert abs(largest - 25.) < .5
            assert value_error(rows[-1]['measured'][key], initial_arm, 'quaternion') < .05
    for frame in (1, 31, len(rows) - 30, len(rows)):
        handle.scene.frame_set(frame)
        expected = rows[frame - 1]['measured']['pelvis.position']
        assert value_error(tuple(handle.rig.matrix_world @ handle.bones['Hips'].head), expected) < .002

    handle.scene.frame_set(1)
    action_before = handle.rig.animation_data.action
    actions_before = set(bpy.data.actions.keys())
    timeline_before = handle.scene.frame_start, handle.scene.frame_end, handle.scene.frame_current
    try:
        build_action(handle, first, profile=profile, continuations=(lambda _: first,))
    except c.MotionContractError as error:
        assert error.code == 'ENTRY_MISMATCH', error.to_dict()
    else:
        raise AssertionError('Continuation accepted an outdated entry')
    assert handle.rig.animation_data.action == action_before
    assert set(bpy.data.actions.keys()) == actions_before
    assert (handle.scene.frame_start, handle.scene.frame_end, handle.scene.frame_current) == timeline_before

    candidate = build_action_frames(handle, first, profile=profile, continuations=continuations)
    try:
        # 31 load samples and the first two walk samples, including the seam.
        for _ in range(33):
            next(candidate)
    finally:
        candidate.close()
    assert handle.rig.animation_data.action == action_before
    assert set(bpy.data.actions.keys()) == actions_before
    assert (handle.scene.frame_start, handle.scene.frame_end, handle.scene.frame_current) == timeline_before
    if save:
        assert arm_motion and preset_travel and rig in ('demo', 'mixamo') and count in (2, 4)
        save_foundation_bake(rig, f'walk-{count}-{pose}', handle, profile, entry, result, pose,
                             {'steps': count, 'arm_motion': True, 'preset_height_m': preset_height})
    print('FOUNDATION_ATOMIC_WALK_PASSED', rig, count, len(rows),
          {'pelvis_travel_m': achieved, 'entry': pose, 'arm_motion': arm_motion} if preset_travel else {},
          result['review']['metrics'], flush=True)


def save_foundation_bake(rig, case, handle, profile, entry, result, pose, parameters):
    from tools import artifact_store as store
    from tools.storage_policy import ARTIFACTS, MiB, confined, enforce

    stage = ARTIFACTS / 'stages/08'
    out = confined(stage / rig / case, stage)
    enforce(out, growth=12 * MiB, temporary=32 * MiB)
    with store.producer_lease(out):
        if (out / store.MANIFEST).exists():
            raise FileExistsError(f'An evidence bundle already exists at {out}')
        for name, record in (('profile', profile), ('entry', entry)):
            store.atomic_json(out / (name + '.json'), c.to_dict(record), compact=True)
        result['validation_source_sha256'] = store.digest(Path(__file__))
        store.atomic_json(out / 'result.json', result, compact=True)
        store.write_source_identity(out, rig)
        handle.scene.frame_set(1)
        store.save_scene(out / 'preview.blend')
        store.write_manifest(out, handle.scene, complete=False,
                             metadata=store.entry_metadata(pose, parameters, handle.scene))


def prepared_chair(rig, placement=None):
    if placement not in (None, 'translated'):
        raise ValueError('Chair placement must be translated or omitted')
    handle, profile, entry, pad, anchor_id = body_fixture(rig, 'pelvis')
    seat = replace(pad, name='seat')
    if placement == 'translated':
        offset = Vector((.19, -.14, 0))
        handle.rig.matrix_world = Matrix.Translation(offset) @ handle.rig.matrix_world
        handle.environment[-1].location += offset
        seat = replace(seat, center=tuple(a + b for a, b in zip(seat.center, offset.xy, strict=True)))
        bpy.context.view_layer.update()
        entry = capture_entry(handle, profile)
    handle.surfaces = tuple(seat if surface == pad else surface for surface in handle.surfaces)
    motion = compile_foundation('sit_seat', handle, profile, entry)
    result = build_action(handle, motion, profile=profile)
    assert result['review']['passed'], result['review']
    soles = {'left.sole', 'right.sole'}
    assert all(soles <= set(row['active_support_anchors']) for row in result['samples'])
    ending = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    assert set(ending.active_contacts) == soles | {anchor_id}
    anchor, = [item for item in ending.contact_anchors if item.anchor_id == anchor_id]
    assert anchor.surface_id == seat.name and abs(anchor.position[2] - seat.height) < .003
    assert result['samples'][-1]['support_skin_gaps_m'][anchor_id] < .003
    print('FOUNDATION_PREPARED_CHAIR_PASSED', rig, placement or 'fixture',
          result['frames'], result['review']['metrics'], flush=True)


def chair_endpoint(handle, profile):
    handle.scene.frame_set(handle.scene.frame_end)
    return {'pelvis': tuple(handle.rig.matrix_world @ handle.bones['Hips'].head),
            **{side + '.sole': measure_endpoint(handle, profile, side + '.sole') for side in ('left', 'right')},
            **{side + '.' + joint: measure_joint_angle(handle, profile, side + '.' + joint)
               for side in ('left', 'right') for joint in ('knee.flexion', 'elbow.flexion')}}


def standing_chair(rig, height=.45, pose='neutral', *, compare=False, save_prefix=None):
    handle, profile, _ = setup(rig, pose)
    profile = calibrate_support(handle, profile)
    _, seat = resolve_seat(handle, height)
    entry = capture_entry(handle, profile)
    motion = compile_foundation('sit_seat', handle, profile, entry, chair_descent=True)
    result = bake_floor_segment('chair', handle, profile, motion)
    assert result['review']['passed']
    rows = result['samples']
    soles = {'left.sole', 'right.sole'}
    assert all(soles <= set(row['active_support_anchors']) for row in rows)
    end = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    assert set(end.active_contacts) == soles | {'pelvis.support'}
    anchor, = [value for value in end.contact_anchors if value.anchor_id == 'pelvis.support']
    assert anchor.surface_id == seat.name and abs(anchor.position[2] - seat.height) < .003
    assert rows[-1]['support_skin_gaps_m']['pelvis.support'] < .003
    if save_prefix is not None:
        save_foundation_bake(rig, f'{save_prefix}-{height:g}-{pose}', handle, profile, entry, result, pose,
                             {'seat_height_m': height})
    print('FOUNDATION_STANDING_CHAIR_PASSED', rig, height, pose, len(rows), result['review']['metrics'], flush=True)
    if compare:
        actual = chair_endpoint(handle, profile)
        actual_gap = support_skin_height(handle, 'pelvis', seat) - height
        legacy, baseline_profile, _ = setup(rig, pose)
        _, baseline_seat = resolve_seat(legacy, height)
        baseline = build_action(legacy, sitting_plan(baseline_seat.height, baseline_seat))
        expected = chair_endpoint(legacy, baseline_profile)
        baseline_gap = support_skin_height(legacy, 'pelvis', baseline_seat) - height
        differences = {key: value_error(value, expected[key], 'vector' if isinstance(value, tuple) else 'scalar')
                       for key, value in actual.items()}
        print('FOUNDATION_CHAIR_COMPARISON', rig, height, pose, json.dumps({
            'differences': differences,
            'pelvis_actual': actual['pelvis'], 'pelvis_preset': expected['pelvis'],
            'seat_gap_actual': actual_gap, 'seat_gap_preset': baseline_gap,
        }), flush=True)
        assert baseline['review']['passed'] and baseline['frames'] == len(rows)
        assert all(differences[key] < .003 for key in ('pelvis', 'left.sole', 'right.sole'))
        assert all(differences[key] < 2. for key in differences if key.endswith('.flexion'))


def run_smoke(rig, count, pose='neutral', *, compare=False, arm_motion=False):
    handle, profile, entry = setup(rig, pose)
    height = (handle.rig.matrix_world.to_3x3() @ (handle.up * handle.height)).length
    first, continuations = compile_run_sequence(entry, profile, handle.surfaces, steps=count, preset_height_m=height,
                                                arm_motion=arm_motion)
    try:
        result = build_action(handle, first, profile=profile, continuations=continuations)
    except c.PlanError as error:
        print('FOUNDATION_RUN_REJECTED', rig, count,
              json.dumps(error.to_dict() if isinstance(error, c.MotionContractError)
                         else getattr(error, 'review', {})), flush=True)
        raise
    rows = result['samples']
    assert len(rows) == 103 + count * 27 and result['review']['passed']
    apex_frames = [31 + 13 + 27 * index for index in range(count)]
    assert all(rows[frame - 1]['floor_m'] > .01 and not rows[frame - 1]['active_foot_anchors']
               for frame in apex_frames)
    assert set(rows[-1]['active_foot_anchors']) == {'left.sole', 'right.sole'}
    travel = value_error(rows[0]['measured']['pelvis.position'][:2], rows[-1]['measured']['pelvis.position'][:2])
    assert abs(travel - .17 * height * count) < .003
    if arm_motion:
        spine = tuple(joint + '.pitch' for joint in ('torso', 'spine.mid', 'spine.upper')
                      if joint + '.pitch' in rows[0]['measured'])
        assert abs(sum(rows[30]['measured'][key] - rows[0]['measured'][key] for key in spine) - 10.) < .1
        assert all(abs(rows[-1]['measured'][key] - rows[0]['measured'][key]) < .1 for key in spine)
        for index, frame in enumerate(frame + 2 for frame in apex_frames):
            leading = 'left' if index % 2 == 0 else 'right'
            for side in ('left', 'right'):
                angle = rows[frame - 1]['measured'][side + '.elbow.flexion']
                assert abs(angle - (65. if side == leading else 85.)) < 3., (frame, side, angle)
        for side in ('left', 'right'):
            key = side + '.elbow.flexion'
            assert abs(rows[-1]['measured'][key] - rows[0]['measured'][key]) < .1
    print('FOUNDATION_RUN_PASSED', rig, count, len(rows), travel, result['review']['metrics'], flush=True)
    if compare:
        measured = walk_playback(handle, profile)
        measured['upper_body'] = gait_upper_body_playback(handle, profile)
        legacy, legacy_profile, _ = setup(rig, 'neutral')
        legacy_result = build_action(legacy, preset_plan('run', steps=count))
        assert legacy_result['review']['passed'], legacy_result['review']
        baseline = walk_playback(legacy, legacy_profile)
        baseline['upper_body'] = gait_upper_body_playback(legacy, legacy_profile)
        print('FOUNDATION_RUN_COMPARISON', rig, pose,
              json.dumps({'legacy_neutral': baseline, 'recipe': measured}), flush=True)
        assert abs(measured['duration_s'] - baseline['duration_s']) <= 1 / first.fps
        for key in ('pelvis_travel_m', 'pelvis_height_change_m', 'stance_width_m'):
            assert abs(measured[key] - baseline[key]) < .003, key
        assert all(abs(actual - expected) < .003 for actual, expected in
                   zip(measured['sole_travel_m'], baseline['sole_travel_m'], strict=True))


def wave_playback(handle, profile, side, times):
    scene = handle.scene
    frames_per_second = scene.render.fps / scene.render.fps_base
    poses = []
    for time in times:
        scene.frame_set(scene.frame_start + round(time * frames_per_second))
        arm = handle.rig.matrix_world.to_3x3()
        directions = {}
        for joint, bone_name in (('upper_arm', 'Arm'), ('forearm', 'ForeArm')):
            bone = handle.bones[side.title() + bone_name]
            directions[joint] = (arm @ (bone.tail - bone.head)).normalized()
        poses.append({
            'palm': measure_orientation(handle, profile, side + '.hand'),
            **directions,
            **{joint: measure_joint_angle(handle, profile, side + '.' + joint)
               for joint in ('elbow.flexion', 'forearm.twist', 'wrist.flexion', 'wrist.deviation')},
        })
    return poses


def wave_smoke(rig, side, waves, tempo, *, compare=False, save=False):
    handle, profile, entry = setup(rig, 'neutral')
    motion = compile_foundation('wave', handle, profile, entry, side=side, waves=waves, tempo=tempo)
    try:
        result = build_action(handle, motion, profile=profile)
    except c.PlanError as error:
        details = error.to_dict() if isinstance(error, c.MotionContractError) else getattr(error, 'review', {})
        if 'issues' in details:
            issues = details['issues']
            details = {**details, 'issue_count': len(issues), 'issues': issues[:5]}
        print('FOUNDATION_WAVE_REJECTED', rig, side, json.dumps(details), flush=True)
        raise
    rows = result['samples']
    assert all(set(row['active_foot_anchors']) == {'left.sole', 'right.sole'} for row in rows)
    forearm = side + '.forearm.direction'
    directions = [track for track in motion.tracks if track.control_id == forearm]
    peaks = directions[1:-1:2]
    assert len(peaks) == waves
    assert all(Vector(rows[round(track.interval.end_s * motion.fps)]['measured'][forearm]).angle(
        Vector(track.curve.end_value)) < math.radians(.5) for track in peaks)
    for track in motion.tracks:
        key = track.control_id
        assert value_error(rows[0]['measured'][key], rows[-1]['measured'][key], track.value_shape) < .1
    if save:
        save_foundation_bake(rig, f'wave-{side}-{waves}-{tempo:g}', handle, profile, entry, result,
                             'neutral', {'side': side, 'waves': waves, 'tempo': tempo})
    print('FOUNDATION_WAVE_PASSED', rig, side, waves, tempo, len(rows), result['review']['metrics'], flush=True)
    if compare:
        times = [(1.5 + .65 * index) * tempo for index in range(2 * waves + 1)]
        measured = wave_playback(handle, profile, side, times)
        legacy, legacy_profile, _ = setup(rig, 'neutral')
        baseline = build_action(legacy, scale_timing(preset_plan('wave', side=side, waves=waves), tempo))
        assert baseline['review']['passed'] and baseline['frames'] == len(rows)
        previous = wave_playback(legacy, legacy_profile, side, times)
        joints = ('elbow.flexion', 'forearm.twist', 'wrist.flexion', 'wrist.deviation')
        differences = [{'palm_error_deg': value_error(a['palm'], b['palm'], 'quaternion'),
                        **{part + '_error_deg': math.degrees(a[part].angle(b[part]))
                           for part in ('upper_arm', 'forearm')},
                        **{key: round(a[key] - b[key], 3) for key in joints}}
                       for a, b in zip(measured, previous, strict=True)]
        palm = side + '.hand.orientation'
        errors = []
        for frame, row in enumerate(rows, legacy.scene.frame_start):
            legacy.scene.frame_set(frame)
            reference = measure_orientation(legacy, legacy_profile, side + '.hand')
            errors.append((value_error(row['measured'][palm], reference, 'quaternion'), row['time_s']))
        print('FOUNDATION_WAVE_COMPARISON', rig, side,
              json.dumps({'landmarks': differences, 'peak_palm_error_deg_and_time_s': max(errors)}), flush=True)
        assert max(row['upper_arm_error_deg'] for row in differences) < 2.
        assert max(row['forearm_error_deg'] for row in differences) < 3.


def request_smoke(rig, pose):
    handle, profile, measured = setup(rig, pose)
    selected = select_common_foundation('wave with your left hand slowly')
    model = select_motion_foundation({'name': 'wave', 'side': 'left'})
    assert selected == replace(model, tempo=1.25)
    assert select_common_foundation('make the wave gentler') is None

    def playback_state():
        animation = handle.rig.animation_data
        return handle.scene.frame_current, animation.action if animation else None

    before = playback_state()
    request = bind_foundation(handle, selected, profile, revision=7)
    assert request.motion.entry_snapshot == replace(measured, revision=7)
    assert playback_state() == before
    for arguments, expected in (({'revision': 6}, 'STALE_REVISION'),
                                ({'revision': 7, 'approximate': True}, 'UNSUPPORTED_GOAL')):
        try:
            request_frames(handle, request, **arguments)
        except c.MotionContractError as error:
            assert error.code == expected, error.to_dict()
        else:
            raise AssertionError(f'The bake accepted {arguments}')

    builder = request_frames(handle, request, revision=7)
    for _ in range(6):
        next(builder)
    builder.close()
    assert playback_state() == before
    result = bake_request(handle, request, revision=7)
    assert result['review']['passed'], result['review']
    assert len(result['samples']) == round(request.motion.duration_s * request.motion.fps) + 1
    assert all(set(row['active_foot_anchors']) == {'left.sole', 'right.sole'} for row in result['samples'])
    print('FOUNDATION_REQUEST_PASSED', rig, pose, len(result['samples']), flush=True)


def seated_extension(rig, pose):
    handle, profile, _ = setup(rig, pose)
    profile = calibrate_support(handle, profile)
    entry = capture_entry(handle, profile)
    motion, following = compile_floor_sit_sequence(entry, profile, handle.surfaces)
    try:
        result = build_action(handle, motion, profile=profile, continuations=following)
    except c.PlanError as error:
        detail = error.to_dict() if isinstance(error, c.MotionContractError) else getattr(error, 'review', {})
        if 'issues' in detail:
            detail['issues'] = detail['issues'][:5]
        print('FLOOR_EXTENSION_REJECTED', rig, json.dumps(detail), flush=True)
        raise
    rows = result['samples']
    assert len(rows) == 151 and result['review']['passed']
    ending = rows[-1]
    extended = [row for row in rows if row['segment'] == 1]
    assert all('pelvis.support' in row['active_support_anchors'] for row in extended)
    seam = rows[rows.index(extended[0]) - 1]
    assert set(seam['active_support_anchors']) == {'pelvis.support', 'left.sole', 'right.sole'}
    assert set(ending['active_support_anchors']) == {'pelvis.support'}
    assert ending['support_skin_gaps_m']['pelvis.support'] < .003
    knees = [ending['measured'][side + '.knee.flexion'] for side in ('left', 'right')]
    endpoint_heights = {key: ending['measured'][key + '.position'][2]
                        for key in ('left.heel', 'left.sole', 'right.heel', 'right.sole')}
    print('FLOOR_EXTENSION_MEASURED', rig, pose, len(rows), knees, endpoint_heights,
          floor_playback(handle, profile), result['review']['metrics'], flush=True)
    assert all(abs(knee - 15.) < 2. for knee in knees), knees


def atomic_lie(rig, pose):
    if pose == 'neutral':
        handle, profile, _ = setup(rig, pose)
        profile = calibrate_support(handle, profile)
        entry = capture_entry(handle, profile)
    else:
        handle, profile, entry = setup_floor_sit(rig, pose)
    motion, continuations = compile_lie_sequence(entry, profile, handle.surfaces,
                                                floor_sit_arms=pose == 'neutral')
    result = build_action(handle, motion, profile=profile, continuations=continuations)
    rows = result['samples']
    assert result['review']['passed'] and len(rows) == 254
    assert rows[126]['segment'] == 0 and rows[127]['segment'] == 1
    assert set(rows[126]['active_support_anchors']) == {'left.sole', 'right.sole', 'pelvis.support'}
    assert set(rows[-1]['active_support_anchors']) == {'left.sole', 'right.sole', 'back.support'}
    assert all({'left.sole', 'right.sole'} <= set(row['active_support_anchors']) for row in rows)
    assert rows[-1]['support_skin_gaps_m']['back.support'] < .003
    handle.scene.frame_set(handle.scene.frame_end)
    assert value_error(tuple(handle.rig.matrix_world @ handle.bones['Hips'].head),
                       rows[-1]['measured']['pelvis.position']) < .002
    print('FOUNDATION_ATOMIC_LIE_PASSED', rig, pose, len(rows), result['review']['metrics'], flush=True)


def main(rig, pose, variant=None, entry_pose='neutral', output=None):
    if pose == 'floor-extend':
        seated_extension(rig, variant or 'neutral')
        return

    if pose == 'request':
        request_smoke(rig, variant or 'neutral')
        return

    if pose in ('run', 'run-compare', 'run-compare-arms'):
        run_smoke(rig, int(variant), entry_pose, compare=pose != 'run', arm_motion=pose == 'run-compare-arms')
        return

    if pose in ('chair-standing', 'chair-compare', 'chair-save', 'chair-refresh'):
        save_prefix = {'chair-save': 'chair', 'chair-refresh': 'chair-refresh'}.get(pose)
        standing_chair(rig, float(variant) if variant else .45, entry_pose,
                       compare=pose == 'chair-compare', save_prefix=save_prefix)
        return

    if pose == 'atomic-lie':
        atomic_lie(rig, variant)
        return

    if pose in ('wave', 'wave-compare', 'wave-save'):
        wave_smoke(rig, variant, int(entry_pose), float(output) if output else 1.,
                   compare=pose == 'wave-compare', save=pose == 'wave-save')
        return

    if pose == 'atomic-walk':
        atomic_walk(rig, int(variant), preset_travel=entry_pose.startswith('preset-travel'),
                    pose='turned' if 'turned' in entry_pose else 'neutral', arm_motion='arms' in entry_pose,
                    save=output == 'save')
        return

    if pose == 'walk':
        compare_walk(rig, int(variant), entry_pose)
        return

    if pose in ('floor-compare', 'floor-baseline'):
        compare_floor_sit(rig, baseline_only=pose == 'floor-baseline')
        return

    if pose == 'chair':
        prepared_chair(rig, variant)
        return

    if pose == 'floor':
        floor_continuation(rig, variant)
        return

    if pose in ('compare', 'compare-compact', 'jump-save'):
        legacy, legacy_profile, _ = setup(rig, 'neutral')
        result = build_action(legacy, preset_plan('jump'))
        assert result['review']['passed'], result['review']
        baseline = jump_playback(legacy, legacy_profile)
        if pose == 'jump-save':
            # Reload the isolated worker's factory state so the saved candidate
            # can reuse the single-import asset and its canonical Blender IDs.
            bpy.ops.wm.read_factory_settings()
        handle, profile, entry = setup(rig, 'neutral')
        result = bake_jump(handle, profile, entry, compact=pose != 'compare')
        measured = jump_playback(handle, profile)
        print('FOUNDATION_JUMP_COMPARISON', rig,
              json.dumps({'legacy': baseline, 'recipe': measured}), flush=True)
        if pose == 'jump-save':
            assert result['frames'] == 79 and measured['duration_s'] == baseline['duration_s'] == 2.6
            assert measured['flight_samples'] == baseline['flight_samples'] == 15
            assert abs(measured['peak_clearance_m'] - baseline['peak_clearance_m']) < .01
            assert measured['end_sole_drift_m'] < .002
            assert all(abs(angle - baseline['upper_arm_excursion_deg'][side]) < 2.5
                       for side, angle in measured['upper_arm_excursion_deg'].items())
            save_foundation_bake(rig, 'jump-compact-neutral', handle, profile, entry, result, 'neutral',
                                 {'compact_jump': True})
        return

    handle, profile, entry = setup(rig, pose)
    result = bake_jump(handle, profile, entry)
    print('FOUNDATION_JUMP_PASSED', rig, pose, result['frames'], result['review']['metrics'], flush=True)


if __name__ == '__main__':
    main(*sys.argv[sys.argv.index('--') + 1:])
