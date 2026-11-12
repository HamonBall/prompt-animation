"""Exercise the hands-and-feet cycle on measured horizontal support fixtures."""
from dataclasses import replace
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

import bpy
from mathutils import Matrix, Quaternion, Vector

from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action, set_contact
from avatar_app.blender.pose import axes, position_hand
from avatar_app.blender.support_mechanics import calibrate_support
from avatar_app.motion import ContactConstraint, Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import value_error
from avatar_app.movement_library.coordinated import CRAWL_ANCHORS
from avatar_app.movement_library.spatial import palm_rotation
from blender_movement_root_travel_flight import setup
from test_movement_support_transfers import compile_support
from tools.preview_movement import capture_entry


def prepare_palm(handle, profile, side, basis):
    world = handle.rig.matrix_world
    inverse = world.inverted()
    sign = 1 if side == 'right' else -1
    upper, elbow, hand = (handle.bones[side.title() + part] for part in ('Arm', 'ForeArm', 'Hand'))
    shoulder = world @ upper.head
    wrist = shoulder + basis @ Vector((.06 * sign, .19, 0))
    wrist.z = .060
    pole = shoulder + basis @ Vector((.35 * sign, -.16, -.35))
    position_hand(handle, side.title(), inverse @ wrist, axes(handle), pole=inverse @ pole)
    current = Quaternion(rp.measure_orientation(handle, profile, side + '.hand'))
    forward = world.to_3x3() @ (hand.head - elbow.head)
    forward.z = 0
    facing = Quaternion(palm_rotation(tuple(forward), (0, 0, -1)))
    bone = world @ hand.matrix

    def orient(yaw):
        delta = Quaternion((0, 0, 1), math.radians(yaw)) @ facing @ current.conjugated()
        rotation = delta @ bone.to_quaternion()
        hand.matrix = inverse @ (Matrix.Translation(bone.translation) @ rotation.to_matrix().to_4x4()
                                 @ Matrix.Diagonal((*bone.to_scale(), 1)))
        bpy.context.view_layer.update()
        return max(abs(rp.measure_joint_angle(handle, profile, side + '.wrist.' + axis)) / limit
                   for axis, limit in (('flexion', 70), ('deviation', 30)))

    orient(min((0, -15, 15, -30, 30, -45, 45), key=orient))


def prepare_low_stance(handle, profile):
    basis = rp.semantic_frame(handle, profile, 'pelvis').to_3x3()
    world = handle.rig.matrix_world
    inverse = world.inverted()
    hip = handle.bones['Hips']
    original = world @ hip.matrix
    lean = Quaternion(basis.col[0], math.radians(-72)).to_matrix().to_4x4()
    feet = {side: (world @ handle.bones[side + 'Foot'].head,
                   handle.bones[side + 'Foot'].matrix.to_quaternion().copy()) for side in ('Left', 'Right')}
    lengths = {item.id: item.value_m for item in profile.lengths}
    arm_reach = min(lengths[side + '.upper_arm'] + lengths[side + '.forearm'] for side in ('left', 'right'))
    shoulders = [world @ handle.bones[side + 'Arm'].head for side in ('Left', 'Right')]
    shoulder_offset = max((lean.to_3x3() @ (point - original.translation)).z for point in shoulders)
    target = original.translation.copy()
    target.z = .84 * arm_reach + .035 - shoulder_offset
    hip.matrix = inverse @ Matrix.Translation(target) @ lean @ Matrix.Translation(-original.translation) @ original
    bpy.context.view_layer.update()
    for side, sign in (('Left', -1), ('Right', 1)):
        foot, orientation = feet[side]
        goal = foot + basis @ Vector((.04 * sign, -.48, 0))
        pole = inverse.to_3x3() @ (basis @ Vector((.12 * sign, -.5, 1)))
        set_contact(handle, ContactConstraint(side.lower() + '_foot'), inverse @ goal, orientation, leg_pole=pole)
    return basis


def bake(handle, profile, entry, move, params):
    motion = compile_support(profile, entry, move, params, handle.surfaces)
    try:
        result = build_action(handle, motion, profile=profile)
    except c.PlanError as error:
        diagnostic = error.to_dict() if isinstance(error, c.MotionContractError) else str(error)
        print('CRAWL_SMOKE_FAILED', move, getattr(error, 'review', None) or diagnostic, flush=True)
        raise
    handle.scene.frame_set(handle.scene.frame_end)
    return result, c.from_dict(c.MotionStateSnapshot, result['ending_state'])


def check_cycle(handle, profile, entry, lead):
    result, ending = bake(handle, profile, entry, 'body.crawl',
                          {'lead': lead, 'distance_m': .04, 'swing_s': .5})
    rows = result['samples']
    assert all(len(row['active_support_anchors']) >= 3 for row in rows)
    assert set(ending.active_contacts) == set(entry.active_contacts) == set(CRAWL_ANCHORS)
    assert all(anchor.surface_id == 'floor' for anchor in ending.contact_anchors)
    assert abs((Quaternion(entry.root_transform.orientation) @ Vector((0, 1, 0))).z) > .8
    first, last = rows[0]['measured'], rows[-1]['measured']
    assert abs(value_error(first['pelvis.position'], last['pelvis.position']) - .04) < .002
    assert all(value_error(row['measured']['head.orientation'], first['head.orientation'], 'quaternion') < .5
               for row in rows)
    for anchor in CRAWL_ANCHORS:
        assert any(anchor not in row['active_support_anchors'] for row in rows)
        surface = next(item for item in entry.contact_anchors if item.anchor_id == anchor)
        assert max(row['measured'][anchor + '.position'][2] - surface.position[2] for row in rows) >= .03
        start = rows[0]['active_support_anchors'][anchor]['position']
        end = rows[-1]['active_support_anchors'][anchor]['position']
        assert abs(value_error(tuple(start), tuple(end)) - .04) < .002
        assert all(row['active_support_anchors'][anchor]['position'] in (start, end)
                   for row in rows if anchor in row['active_support_anchors'])
    return ending, rows


def setup_crawl(rig, pose):
    handle, profile, _ = setup(rig, pose)
    profile = calibrate_support(handle, profile)
    basis = prepare_low_stance(handle, profile)
    for side in ('left', 'right'):
        prepare_palm(handle, profile, side, basis)
    handle.surfaces = (Surface(),)
    try:
        entry = capture_entry(handle, profile)
    except c.MotionContractError:
        for limit in profile.joint_limits:
            angle = rp.measure_joint_angle(handle, profile, limit.control_id)
            if not limit.minimum <= angle <= limit.maximum:
                print('CRAWL_ENTRY_LIMIT', limit.control_id, angle, (limit.minimum, limit.maximum), flush=True)
        raise
    for side in ('left', 'right'):
        _, entry = bake(handle, profile, entry, 'support.acquire_release',
                        {'operation': 'acquire', 'anchor': side + '.palm', 'acquire_s': 1.2})
    return handle, profile, entry


def main(rig, pose, lead):
    handle, profile, entry = setup_crawl(rig, pose)
    ending, first = check_cycle(handle, profile, entry, lead)
    action = handle.rig.animation_data.action
    incompatible = replace(ending, active_contacts=tuple(anchor for anchor in ending.active_contacts if anchor != 'left.palm'))
    try:
        compile_support(profile, incompatible, 'body.crawl', {'lead': lead}, handle.surfaces)
    except c.MotionContractError as error:
        assert error.code == 'ENTRY_MISMATCH', error.to_dict()
    else:
        raise AssertionError('Crawl accepted an entry with a missing palm contact')
    assert handle.rig.animation_data.action == action
    _, second = check_cycle(handle, profile, ending, lead)
    assert value_error(first[-1]['measured']['pelvis.position'], second[0]['measured']['pelvis.position']) < .002
    print('COORDINATED_CRAWL_PASSED', rig, pose, lead, flush=True)


if __name__ == '__main__':
    main(*sys.argv[sys.argv.index('--') + 1:])
