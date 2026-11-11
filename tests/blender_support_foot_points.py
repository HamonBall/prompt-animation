"""Native acquisition and release checks for rigid heel and forefoot support."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.blender.motion import build_action
from avatar_app.movement_library import contracts as c
from blender_movement_root_travel_flight import setup
from blender_movement_support_transfers import save_case
from test_movement_support_transfers import compile_support


def main(rig, part, *flags):
    assert part in ('heel', 'forefoot')
    handle, profile, entry = setup(rig, 'turned-crouched-raised-left')
    assert entry.active_contacts == ('right.sole',)
    anchor = 'left.' + part
    params = {'anchor': anchor, 'acquire_s': 1.2, 'hold_s': .3, 'release_s': 1.2}
    move = compile_support(profile, entry, 'support.acquire_release', params)
    result = build_action(handle, move, profile=profile)
    samples = result['samples']
    active = [set(sample['active_foot_anchors']) for sample in samples]
    assert active[0] == active[-1] == {'right.sole'}
    assert active.count({'right.sole', anchor}) >= 9
    assert all('right.sole' in anchors for anchors in active)
    target = next(event.target_world_v1 for event in move.contact_events if event.anchor_id == anchor)
    for row, anchors in zip(samples, active):
        if anchor in anchors:
            assert tuple(row['active_foot_anchors'][anchor]) == target
    assert result['review']['metrics']['contact_error_m'] < .001
    try:
        compile_support(profile, entry, 'support.transfer', {'anchor': 'right.' + part})
    except c.MotionContractError as error:
        assert error.code == 'CONSTRAINT_CONFLICT'
    else:
        raise AssertionError('Two fixed support targets competed for the same leg')
    if '--save' in flags:
        save_case(rig, part + '-cycle', handle, profile, move, result, params)
    print('FIXED_FOOT_POINT_PASSED', rig, part, result['frames'], result['review']['metrics'], flush=True)


if __name__ == '__main__':
    main(*sys.argv[sys.argv.index('--') + 1:])
