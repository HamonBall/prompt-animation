"""Native feet-to-palm transfer on an elevated horizontal fixture."""
from pathlib import Path
import math
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action
from avatar_app.blender.pose import axes, position_hand
from avatar_app.blender.support_mechanics import calibrate_support
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.spatial import palm_rotation
from avatar_app.motion import Surface
from blender_movement_root_travel_flight import setup
from blender_support_body import make_pad
from blender_movement_support_transfers import save_case
from test_movement_support_transfers import compile_support
from tools.preview_movement import capture_entry


def palm_fixture(rig, side):
    handle, profile, _ = setup(rig, 'turned-crouched')
    profile = calibrate_support(handle, profile)
    root = rp.semantic_frame(handle, profile, 'pelvis').to_3x3()
    world = handle.rig.matrix_world
    inverse = world.inverted()
    sign = 1 if side == 'right' else -1
    upper, elbow, hand = (handle.bones[side.title() + part] for part in ('Arm', 'ForeArm', 'Hand'))
    shoulder = world @ upper.head
    wrist_target = shoulder + root @ Vector((.17 * sign, .20, -.28))
    pole = shoulder + root @ Vector((.40 * sign, .04, -.23))
    position_hand(handle, side.title(), inverse @ wrist_target, axes(handle), pole=inverse @ pole)
    current = Quaternion(rp.measure_orientation(handle, profile, side + '.hand'))
    forward = world.to_3x3() @ (hand.head - elbow.head)
    forward.z = 0
    desired = Quaternion(palm_rotation(tuple(forward), (0, 0, -1)))
    bone = world @ hand.matrix
    def orient(yaw):
        rotation = Quaternion((0, 0, 1), math.radians(yaw)) @ desired @ current.conjugated() @ bone.to_quaternion()
        hand.matrix = inverse @ (Matrix.Translation(bone.translation) @ rotation.to_matrix().to_4x4()
                                 @ Matrix.Diagonal((*bone.to_scale(), 1)))
        bpy.context.view_layer.update()
        return max(abs(rp.measure_joint_angle(handle, profile, side + '.wrist.' + axis)) / limit
                   for axis, limit in (('flexion', 70), ('deviation', 30)))

    # Leave room for wrist movement during acquisition while keeping the
    # palm flat. Select only from the authored in-plane fixture headings.
    heading = min((0, -15, 15, -30, 30, -45, 45), key=orient)
    orient(heading)
    bpy.context.view_layer.update()
    try:
        entry = capture_entry(handle, profile)
    except c.MotionContractError as error:
        print('PALM_ENTRY_FAILED', error.to_dict(), flush=True)
        raise
    point = Vector(rp.measure_endpoint(handle, profile, side + '.palm'))
    point -= Vector((0, 0, .035))
    surface = Surface('hand-pad', point.z, tuple(point[:2]), (.24, .24))
    make_pad(handle, surface)
    return handle, profile, entry, surface, point


def main(rig, side, *flags):
    handle, profile, entry, surface, point = palm_fixture(rig, side)
    assert set(entry.active_contacts) == {'left.sole', 'right.sole'}
    anchor = side + '.palm'
    params = {'anchor': anchor, 'from_anchor': side + '.sole', 'surface': surface.name,
              'target': tuple(point), 'acquire_s': 1.2}
    motion = compile_support(profile, entry, 'support.transfer', params, handle.surfaces)
    try:
        result = build_action(handle, motion, profile=profile)
    except c.PlanError as error:
        diagnostic = error.to_dict() if isinstance(error, c.MotionContractError) else str(error)
        print('PALM_TRANSFER_FAILED', getattr(error, 'review', None) or diagnostic, flush=True)
        raise
    rows = result['samples']
    supports = [set(row['active_support_anchors']) for row in rows]
    assert len(supports[0]) == 2 and anchor not in supports[0]
    assert any(len(active) == 3 for active in supports)
    assert supports[-1] == {'right.sole' if side == 'left' else 'left.sole', anchor}
    endpoint = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    palm = next(item for item in endpoint.contact_anchors if item.anchor_id == anchor)
    assert palm.surface_id == surface.name and palm.position == tuple(point)
    gaps = [row['support_skin_gaps_m'][anchor] for row in rows if 'support_skin_gaps_m' in row]
    assert gaps and max(gaps) < .025
    if '--save' in flags:
        save_case(rig, 'palm-transfer', handle, profile, motion, result, params)
    print('PALM_TRANSFER_PASSED', rig, side, result['frames'], max(gaps), result['review']['metrics'], flush=True)


if __name__ == '__main__':
    main(*sys.argv[sys.argv.index('--') + 1:])
