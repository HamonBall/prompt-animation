"""One isolated Stage 05.5 native case using the shared baking transaction."""
import argparse
from pathlib import Path
import sys
import time

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from ankles_feet_toes_cases import cases
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.foot_mechanics import calibrate_feet
from avatar_app.blender.motion import build_action, set_contact
from avatar_app.blender.scene import prepare_preview
from avatar_app.motion import ContactConstraint, Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment, instantiate_movement, prepare_fragment
from avatar_app.movement_library.joints import catalog_for_profile
from blender_movement_hips_knees import fixture
from tools import artifact_store as store
from tools.preview_movement import capture_entry
from tools.storage_policy import ARTIFACTS, confined, enforce

OUT = ARTIFACTS / 'stages/05.5'
SOURCES = ('tests/ankles_feet_toes_cases.py', 'tests/blender_movement_ankles_feet_toes.py',
           'tests/blender_movement_hips_knees.py', 'tools/preview_movement.py')


def seated_fixture(handle, profile, raised_side):
    """Author a seated leg configuration with a floor sole and a raised ankle."""
    fixture(handle, profile, 'neutral', raised_side)
    world = handle.rig.matrix_world
    inverse = world.inverted()
    forward = rp.semantic_frame(handle, profile, 'pelvis').to_3x3().col[1].copy()
    forward.z = 0
    forward.normalize()
    lengths = {item.id: item.value_m for item in profile.lengths}
    feet = {}
    for side in ('left', 'right'):
        foot = handle.bones[side.title() + 'Foot']
        feet[side] = (world @ foot.head, foot.matrix.to_quaternion().copy())
    hip = world @ handle.bones['LeftUpLeg'].head
    drop = hip.z - feet['left'][0].z - lengths['left.shin']
    pelvis = handle.bones['Hips']
    matrix = pelvis.matrix.copy()
    matrix.translation -= inverse.to_3x3() @ Vector((0, 0, drop))
    pelvis.matrix = matrix
    bpy.context.view_layer.update()
    for side, (head, orientation) in feet.items():
        target = head + forward * lengths[side + '.thigh']
        if side == raised_side:
            target.z += .09 * profile.height_m
        set_contact(handle, ContactConstraint(side + '_foot'), inverse @ target, orientation,
                    leg_pole=inverse.to_3x3() @ forward)
    assert all(rp.measure_joint_angle(handle, profile, side + '.knee.flexion') > 65
               for side in ('left', 'right'))
    return capture_entry(handle, profile)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rig', required=True, choices=('demo', 'mixamo'))
    parser.add_argument('--case', required=True, choices=tuple(row[0] for row in cases()))
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    name, movement, params, pose = next(row for row in cases() if row[0] == args.case)
    out = confined(OUT / args.rig / name, OUT)
    started = time.perf_counter()
    handle = create_demo_avatar() if args.rig == 'demo' else import_avatar(str(ROOT / 'Hip Hop Mixamo.fbx'))
    prepare_preview(handle)
    profile = calibrate_feet(handle, rp.calibrate_joint_frames(
        handle, avatar_id='feet.' + args.rig, recorded_at='2026-11-05', include_head_aim=True,
    ))
    catalog = catalog_for_profile(profile)
    side = params.get('side', 'left')
    entry = seated_fixture(handle, profile, side) if pose == 'seated-raised' else fixture(handle, profile, pose, side)
    if 'raised' in pose and (movement.startswith('ankle.') or movement == 'toes.curl'):
        # The 05.4 raised-leg fixture preserves the world sole orientation.
        # For free local articulation, author a bind-relative ankle at the
        # same raised endpoint so both signed bounds have joint-limit room.
        handle.bones[side.title() + 'Foot'].matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        entry = capture_entry(handle, profile)
        assert side + '.sole' not in entry.active_contacts
    print('FOOT_ENTRY', args.rig, name, entry.active_contacts,
          {a.anchor_id: a.position for a in entry.contact_anchors}, flush=True)
    if movement == 'toes.curl' and movement not in catalog.definitions:
        try:
            instantiate_movement(movement, params, instance_id='feet.1', profile=profile,
                                 entry_state=entry, catalog=catalog)
        except c.MotionContractError as error:
            assert error.code == 'UNKNOWN_ID' and all(not item.id.endswith('.toe.flexion') for item in profile.controls)
        else:
            raise AssertionError('Unmapped toe movement became executable')
        print('FOOT_TOES_UNAVAILABLE', args.rig, name, flush=True)
        return
    source = store.input_identity(out)['producer_sha256']
    harness = {path: store.digest(ROOT / path) for path in SOURCES}
    fingerprint = rp._fingerprint(handle)
    instance = instantiate_movement(movement, params, instance_id='feet.1', profile=profile,
                                    entry_state=entry, catalog=catalog)
    fragment = build_fragment(instance, entry, profile, (Surface(),), catalog)
    motion = prepare_fragment(fragment, entry, profile)
    prepared = time.perf_counter()
    try:
        result = build_action(handle, motion, profile=profile)
    except Exception as error:
        print('FOOT_NUMERIC_FAILED', getattr(error, 'review', None) or
              (error.to_dict() if hasattr(error, 'to_dict') else str(error)), flush=True)
        raise
    assert result['review']['passed'] and rp._fingerprint(handle) == fingerprint
    assert source == store.input_identity(out)['producer_sha256']
    assert all(store.digest(ROOT / path) == digest for path, digest in harness.items())
    result['stage_05_5'] = {
        'rig': args.rig, 'case': name, 'fixture': pose,
        'application_producer_sha256': source, 'stage_producer': harness,
        'timings_s': {'prepare': prepared - started, 'execute': time.perf_counter() - prepared},
    }
    if not args.smoke:
        enforce(out, growth=8 * 1024**2, temporary=32 * 1024**2)
        with store.producer_lease(out):
            for file, record in (('profile', profile), ('entry', entry), ('instance', instance),
                                 ('fragment', fragment), ('executable', motion)):
                (out / (file + '.json')).write_text(c.dumps(record), encoding='utf-8')
            store.write_source_identity(out, args.rig)
            store.atomic_json(out / 'result.json', result, compact=True)
            handle.scene.frame_set(1)
            store.save_scene(out / 'preview.blend')
            store.write_manifest(out, handle.scene, metadata=store.entry_metadata('authored:' + pose, params, handle.scene),
                                 complete=False)
    print('FOOT_NUMERIC_PASSED', args.rig, name, result['frames'], result['review'], flush=True)


if __name__ == '__main__':
    main()
