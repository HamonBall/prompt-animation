"""Native fixed pelvis, back and knee contacts on bounded horizontal fixtures."""
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.blender import rig_profile as rp
from avatar_app.blender.geometry import skin_bounds, support_skin_height
from avatar_app.blender.motion import build_action
from avatar_app.blender.support_mechanics import calibrate_support
from avatar_app.movement_library import contracts as c
from avatar_app.motion import Surface
from blender_movement_ankles_feet_toes import seated_fixture
from blender_movement_root_travel_flight import setup
from blender_movement_support_transfers import save_case
from test_movement_support_transfers import compile_support
from tools.preview_movement import capture_entry


def make_pad(handle, surface):
    thickness = .05
    bpy.ops.mesh.primitive_cube_add(size=1, location=(*surface.center, surface.height - thickness / 2))
    pad = bpy.context.object
    pad.name = 'Support pad'
    pad.dimensions = (*surface.size, thickness)
    handle.environment.append(pad)
    handle.surfaces = (Surface(), surface)
    bpy.context.view_layer.update()


def body_fixture(rig, kind):
    pose = 'turned-crouched-raised-left' if kind == 'knee' else 'neutral'
    handle, profile, _ = setup(rig, pose)
    profile = calibrate_support(handle, profile)
    if kind == 'pelvis':
        seated_fixture(handle, profile, None)
    if kind == 'back':
        pelvis = handle.bones['Hips']
        world = handle.rig.matrix_world
        bone = world @ pelvis.matrix
        right = rp.semantic_frame(handle, profile, 'pelvis').to_3x3().col[0]
        rotation = Quaternion(right, math.pi / 2).to_matrix().to_4x4()
        transform = Matrix.Translation(bone.translation) @ rotation @ Matrix.Translation(-bone.translation)
        pelvis.matrix = world.inverted() @ transform @ bone
        bpy.context.view_layer.update()
        height = .60 - skin_bounds(handle)[0].z
        transform = Matrix.Translation(Vector((0, 0, height)))
        pelvis.matrix = world.inverted() @ transform @ world @ pelvis.matrix
        bpy.context.view_layer.update()
    entry = capture_entry(handle, profile)
    anchor = 'left.knee.support' if kind == 'knee' else kind + '.support'
    point = Vector(rp.measure_endpoint(handle, profile, anchor))
    part = 'left_knee' if kind == 'knee' else kind
    size = (.16, .16) if kind == 'knee' else (.24, .24)
    region = Surface(kind + '-pad', 0, tuple(point[:2]), size)
    skin = support_skin_height(handle, part, region)
    assert math.isfinite(skin)
    surface = Surface(region.name, skin - .025, region.center, region.size)
    make_pad(handle, surface)
    print('BODY_SUPPORT_ENTRY', rig, kind, point.z, skin, surface.height, entry.active_contacts, flush=True)
    return handle, profile, entry, surface, anchor


def main(rig, kind, *flags):
    handle, profile, entry, surface, anchor = body_fixture(rig, kind)
    transfer = kind != 'back'
    params = {'anchor': anchor, 'surface': surface.name, 'acquire_s': 1.2, 'hold_s': .3, 'release_s': 1.2}
    if transfer:
        params['from_anchor'] = 'right.sole'
    else:
        params['allow_airborne'] = True
    motion = compile_support(profile, entry, 'support.transfer' if transfer else 'support.acquire_release',
                             params, handle.surfaces)
    try:
        result = build_action(handle, motion, profile=profile)
    except c.PlanError as error:
        diagnostic = error.to_dict() if isinstance(error, c.MotionContractError) else str(error)
        print('BODY_SUPPORT_FAILED', getattr(error, 'review', None) or diagnostic, flush=True)
        raise
    rows = result['samples']
    supports = [set(row['active_support_anchors']) for row in rows]
    assert anchor not in supports[0]
    assert any(anchor in active for active in supports)
    if transfer:
        assert any({anchor, 'right.sole'} <= active for active in supports)
        assert anchor in supports[-1] and 'right.sole' not in supports[-1]
    else:
        assert supports[-1] == set()
    gaps = [row['support_skin_gaps_m'][anchor] for row in rows if 'support_skin_gaps_m' in row]
    assert gaps and max(gaps) < .025
    if '--save' in flags:
        save_case(rig, kind + ('-transfer' if transfer else '-cycle'), handle, profile, motion, result, params)
    print('BODY_SUPPORT_PASSED', rig, kind, result['frames'], max(gaps), result['review']['metrics'], flush=True)


if __name__ == '__main__':
    main(*sys.argv[sys.argv.index('--') + 1:])
