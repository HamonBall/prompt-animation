"""Exercise a floor hands-and-knees crawl on the native stage rigs."""
import math
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

import bpy
from mathutils import Matrix, Quaternion, Vector

from avatar_app.blender import rig_profile as rp
from avatar_app.blender.foot_mechanics import apply_local
from avatar_app.blender.geometry import support_skin_height
from avatar_app.blender.kinematics import aim
from avatar_app.blender.primitive import FragmentAdapter
from avatar_app.blender.support_mechanics import apply_palm, body_contact_point, calibrate_support, place_crawl_knees
from avatar_app.motion import Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.coordinated import KNEE_CRAWL_ANCHORS
from blender_movement_crawl import bake, prepare_palm
from blender_movement_root_travel_flight import setup


def setup_knee_crawl(rig, pose):
    handle, profile, _ = setup(rig, pose)
    profile = calibrate_support(handle, profile)
    floor = Surface()
    handle.surfaces = (floor,)
    world = handle.rig.matrix_world
    inverse = world.inverted()
    basis = rp.semantic_frame(handle, profile, 'pelvis').to_3x3()
    hips = handle.bones['Hips']
    original = world @ hips.matrix
    lean = Quaternion(basis.col[0], math.radians(-96)).to_matrix().to_4x4()
    hip_goal = original.translation.copy()
    hip_goal.z = .48
    hips.matrix = inverse @ Matrix.Translation(hip_goal) @ lean @ Matrix.Translation(-original.translation) @ original
    bpy.context.view_layer.update()
    for side, sign in (('Left', -1), ('Right', 1)):
        upper, lower = (handle.bones[side + part] for part in ('UpLeg', 'Leg'))
        aim(upper, inverse.to_3x3() @ (basis @ Vector((sign * .12, .12, -1))))
        aim(lower, inverse.to_3x3() @ (basis @ Vector((0, -1, .30))))
    knees = KNEE_CRAWL_ANCHORS[2:]
    knee_height = sum(body_contact_point(handle, profile, anchor, floor).z for anchor in knees) / 2
    lowered = hips.matrix.copy()
    lowered.translation += inverse.to_3x3() @ Vector((0, 0, -knee_height))
    hips.matrix = lowered
    bpy.context.view_layer.update()
    targets = [(anchor, (*body_contact_point(handle, profile, anchor, floor)[:2], 0.)) for anchor in knees]
    place_crawl_knees(handle, profile, targets, floor)
    anchors = [c.ContactAnchor(anchor, 'floor', goal, 'world', 'metre') for anchor, goal in targets]
    adapter = SimpleNamespace(handle=handle, profile=profile,
                              joints={joint.semantic_id: joint for joint in profile.rest_to_semantic_mappings},
                              limits={limit.control_id: limit for limit in profile.joint_limits})
    adapter._check_reach = lambda control, goal: FragmentAdapter._check_reach(adapter, control, goal)
    for side in ('left', 'right'):
        ankle = side + '.ankle.flexion'
        entry_angle = rp.measure_joint_angle(handle, profile, ankle)
        candidates = sorted(range(-40, 41, 5), key=lambda angle: abs(angle - entry_angle))
        for angle in (entry_angle, *candidates):
            apply_local(adapter, {ankle: angle})
            if support_skin_height(handle, side + '_foot') >= .012:
                break
        else:
            raise AssertionError(f'{rig} {side} trailing foot needs more clearance')
        prepare_palm(handle, profile, side, basis)
        anchor = side + '.palm'
        x, y, _ = rp.measure_endpoint(handle, profile, anchor)
        goal = (x, y, 0.)
        apply_palm(adapter, side, goal, 1.)
        anchors.append(c.ContactAnchor(anchor, 'floor', goal, 'world', 'metre'))
    entry = rp.capture_motion_state(handle, profile, revision=1, captured_time_s=0.,
                                   active_contacts=KNEE_CRAWL_ANCHORS, contact_anchors=tuple(anchors))
    return handle, profile, entry


def main(rig, pose, lead):
    handle, profile, entry = setup_knee_crawl(rig, pose)
    params = {'support': 'hands_knees', 'lead': lead, 'distance_m': .06, 'clearance_m': .03, 'swing_s': .6}
    result, ending = bake(handle, profile, entry, 'body.crawl', params)
    rows = result['samples']
    assert all(len(row['active_support_anchors']) >= 3 for row in rows)
    assert set(ending.active_contacts) == set(KNEE_CRAWL_ANCHORS)
    assert not any(row['active_foot_anchors'] for row in rows)
    starts = {anchor.anchor_id: anchor.position for anchor in entry.contact_anchors}
    assert all(abs(math.dist(starts[anchor.anchor_id], anchor.position) - .06) < .001
               for anchor in ending.contact_anchors)
    continuation, next_exit = bake(handle, profile, ending, 'body.crawl', params)
    assert set(next_exit.active_contacts) == set(KNEE_CRAWL_ANCHORS)
    assert math.dist(rows[-1]['measured']['pelvis.position'],
                     continuation['samples'][0]['measured']['pelvis.position']) < .002
    print('KNEE_CRAWL_PASSED', rig, pose, lead, result['review']['metrics'], flush=True)


if __name__ == '__main__':
    main(*sys.argv[sys.argv.index('--') + 1:])
