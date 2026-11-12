"""Verify the 100 mm Mixamo crawl from a low stance with more wrist reach."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import coordinated_boundary_evidence as boundary
from tools import coordinated_evidence as evidence

SCRIPT = Path(__file__).resolve()
KEY = 'mixamo/low-crawl-right-maximum'
SPEC = {
    'move': 'body.crawl', 'pose': 'crouched', 'max_frames': 265,
    'parameters': {'lead': 'right', 'distance_m': .10, 'clearance_m': .06, 'swing_s': .9},
}


def make_entry(rig, spec):
    import bpy
    from mathutils import Matrix, Vector

    from avatar_app.blender.motion import set_contact
    from avatar_app.blender.pose import axes, position_hand
    from avatar_app.motion import ContactConstraint, Surface
    from blender_movement_crawl import (bake, calibrate_support, capture_entry, prepare_low_stance, prepare_palm,
                                        setup)

    handle, profile, _ = setup(rig, spec['pose'])
    profile = calibrate_support(handle, profile)
    basis = prepare_low_stance(handle, profile)
    world = handle.rig.matrix_world
    inverse = world.inverted()
    feet = {side: (handle.bones[side + 'Foot'].head.copy(),
                   handle.bones[side + 'Foot'].matrix.to_quaternion().copy())
            for side in ('Left', 'Right')}
    hips = handle.bones['Hips']
    lowered = hips.matrix.copy()
    lowered.translation += inverse.to_3x3() @ Vector((0, 0, -.012))
    hips.matrix = lowered
    bpy.context.view_layer.update()
    for side, sign in (('Left', -1), ('Right', 1)):
        target, orientation = feet[side]
        pole = inverse.to_3x3() @ (basis @ Vector((.12 * sign, -.5, 1)))
        set_contact(handle, ContactConstraint(side.lower() + '_foot'), target, orientation, leg_pole=pole)
    for side in ('left', 'right'):
        prepare_palm(handle, profile, side, basis)
        hand = handle.bones[side.title() + 'Hand']
        elbow = handle.bones[side.title() + 'ForeArm']
        # Keep the palm heading and elbow side from the established low fixture.
        # A slightly longer forward reach makes the forearm less vertical.
        wrist = hand.head.copy() + inverse.to_3x3() @ (basis.col[1] * .006)
        orientation = hand.matrix.to_quaternion().copy()
        position_hand(handle, side.title(), wrist, axes(handle), pole=elbow.head.copy())
        hand.matrix = Matrix.Translation(hand.head) @ orientation.to_matrix().to_4x4()
        bpy.context.view_layer.update()
    handle.surfaces = (Surface(),)
    entry = capture_entry(handle, profile)
    for side in ('left', 'right'):
        _, entry = bake(handle, profile, entry, 'support.acquire_release',
                        {'operation': 'acquire', 'anchor': side + '.palm', 'acquire_s': 1.2})
    return handle, profile, entry, dict(spec['parameters'])


if __name__ == '__main__':
    evidence.CASES.clear()
    evidence.CASES[KEY] = SPEC
    evidence.NATIVE = SCRIPT
    evidence.HARNESS += (SCRIPT.relative_to(ROOT).as_posix(),)
    if '--' in sys.argv:
        import blender_coordinated_evidence as native

        native.make_entry = make_entry
        phase, key = sys.argv[sys.argv.index('--') + 1:]
        {'numeric': native.bake, 'render': native.render}[phase](key)
    else:
        boundary.SCRIPT = SCRIPT
        evidence.make_plan = boundary.make_plan
        raise SystemExit(evidence.main())
