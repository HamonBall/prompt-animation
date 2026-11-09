"""Reject invalid 05.5 inputs transactionally and exercise profile-7 compatibility."""
from dataclasses import replace
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.blender import rig_profile as rp
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.foot_mechanics import calibrate_feet
from avatar_app.blender.motion import build_action, build_action_frames
from avatar_app.blender.scene import prepare_preview
from avatar_app.motion import Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment, instantiate_movement, prepare_fragment, value_error
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.legs import with_legs_v1
from blender_movement_hips_knees import fixture


def pose_state(handle):
    action = handle.rig.animation_data
    scene = handle.scene
    return (action.action if action else None,
            action.action_slot if action else None, (scene.frame_start, scene.frame_end, scene.frame_current),
            {bone.name: (bone.rotation_mode, bone.matrix_basis.copy()) for bone in handle.rig.pose.bones},
            handle.rig.matrix_world.copy())


def assert_unchanged(before, handle):
    after = pose_state(handle)
    assert before[:3] == after[:3]
    assert max(abs(v) for row in before[4] - after[4] for v in row) < 1e-6
    for name, (mode, matrix) in before[3].items():
        assert after[3][name][0] == mode
        assert max(abs(v) for row in matrix - after[3][name][1] for v in row) < 1e-6


def prepared(profile, entry, movement, **params):
    catalog = catalog_for_profile(profile)
    instance = instantiate_movement(movement, params, instance_id='feet.boundary', profile=profile,
                                    entry_state=entry, catalog=catalog)
    fragment = build_fragment(instance, entry, profile, (Surface(),), catalog)
    return prepare_fragment(fragment, entry, profile)


def main():
    rig = sys.argv[sys.argv.index('--rig') + 1]
    assert rig in ('demo', 'mixamo')
    handle = create_demo_avatar() if rig == 'demo' else import_avatar(str(ROOT / 'Hip Hop Mixamo.fbx'))
    prepare_preview(handle)
    initial = pose_state(handle)
    legs = with_legs_v1(rp.calibrate_joint_frames(handle, avatar_id='feet.boundary.' + rig,
                                                recorded_at='2026-11-05', include_head_aim=True))
    feet = calibrate_feet(handle, legs)
    entry = fixture(handle, feet, 'crouched', 'left')
    before = pose_state(handle)
    invalid = (
        ('foot.pivot', {'anchor': 'sole'}, 'INVALID_PARAMETER'),
        ('foot.place', {'target': (12, 0, 0)}, 'INVALID_PARAMETER'),
        ('ankle.flex', {}, 'CONSTRAINT_CONFLICT'),
    )
    for movement, params, expected in invalid:
        try:
            prepared(feet, entry, movement, **params)
        except c.MotionContractError as error:
            assert error.code == expected, error.to_dict()
        else:
            raise AssertionError(f'Unexpected accepted request: {movement}')
        assert_unchanged(before, handle)
    fake = replace(entry, contact_anchors=tuple(
        replace(item, position=(item.position[0], item.position[1] + .015, item.position[2]))
        if item.anchor_id == 'left.heel' else item for item in entry.contact_anchors
    ))
    try:
        build_action(handle, prepared(feet, fake, 'foot.pivot'), profile=feet)
    except c.MotionContractError as error:
        assert error.code == 'ENTRY_MISMATCH'
    else:
        raise AssertionError('A forged inactive heel anchor was accepted')
    assert_unchanged(before, handle)
    frames = build_action_frames(handle, prepared(feet, entry, 'foot.pivot'), profile=feet)
    for _ in range(15):
        next(frames)
    frames.close()
    assert_unchanged(before, handle)

    # Re-execute a free-leg and a both-planted profile-7 case alongside the
    # same definitions on profile 8. Compare all inherited measured controls.
    specs = {item.id: item for item in legs.controls}
    worst = {'degree': 0, 'metre': 0, 'unitless': 0}
    for movement, pose in (('hip.lift', 'turned'), ('knee.pulse', 'crouched')):
        results = []
        for profile in (legs, feet):
            handle.rig.animation_data_clear()
            handle.rig.matrix_world = initial[4]
            for bone in handle.rig.pose.bones:
                bone.rotation_mode, bone.matrix_basis = initial[3][bone.name]
            bpy.context.view_layer.update()
            entry = fixture(handle, profile, pose, 'left')
            results.append(build_action(handle, prepared(profile, entry, movement), profile=profile))
        first, second = results
        assert first['review']['passed'] and second['review']['passed']
        assert first['frames'] == second['frames']
        for left, right in zip(first['samples'], second['samples']):
            for key, spec in specs.items():
                error = value_error(left['measured'][key], right['measured'][key], spec.value_shape)
                group = 'degree' if spec.value_shape == 'quaternion' else spec.unit
                assert error < (.001 if group == 'degree' else .00001), (key, error)
                worst[group] = max(worst[group], error)
    print('FOOT_BOUNDARIES_AND_LEG_COMPATIBILITY_PASSED', rig, worst, flush=True)


if __name__ == '__main__':
    main()
