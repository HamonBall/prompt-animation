"""Continue the reviewed traveling cycle from its saved, measured exit."""

from dataclasses import replace
from math import dist
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests')]

from avatar_app.blender.motion import build_action
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import prepare_fragment, value_error
from avatar_app.movement_library.patterns import step_pattern
from avatar_app.movement_library.spatial import rotate
from blender_coordinated_evidence import restore_surfaces
from timing_pattern_evidence import case_path, numeric_valid, replay_valid
from tools import artifact_store as store


def verify_continuation(rig):
    key = rig + '/traveling-steps'
    path = case_path(key)
    result = numeric_valid(key)
    replay_valid(key)
    profile = c.loads(c.AvatarProfile, (path / 'profile.json').read_text(encoding='utf-8'))
    executable = c.loads(c.ExecutableMotion, (path / 'executable.json').read_text(encoding='utf-8'))
    assert executable.loop is not None
    ending = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    handle = store.open_preview(path)
    restore_surfaces(handle, {'stage_05_6c': result['stage_05_7a']})
    handle.scene.frame_set(handle.scene.frame_end)
    action = handle.rig.animation_data.action
    frame = handle.scene.frame_current
    try:
        build_action(handle, replace(executable, loop=None), profile=profile)
    except c.MotionContractError as error:
        assert error.code == 'ENTRY_MISMATCH', error.to_dict()
    else:
        raise AssertionError('The original cycle unexpectedly accepted its translated exit as its entry')
    assert handle.rig.animation_data.action == action and handle.scene.frame_current == frame

    parameters = result['stage_05_7a']['parameters']
    fragment = step_pattern(parameters['lead'], {'distance_m': parameters['distance_m'],
                            'clearance_m': parameters['clearance_m']}, parameters['count'],
                            fragment_id='steps.continuation', entry=ending, profile=profile,
                            surfaces=handle.surfaces)
    motion = prepare_fragment(fragment, ending, profile)
    continued = build_action(handle, motion, profile=profile)
    assert continued['review']['passed'] and continued['frames'] == result['frames']
    original_end = result['samples'][-1]
    first, last = continued['samples'][0], continued['samples'][-1]
    expected_delta = rotate(ending.root_transform.orientation, executable.loop.per_cycle_root_transform.position)

    def difference(after, before):
        return tuple(a - b for a, b in zip(after, before))

    pelvis = 'pelvis.position'
    previous_pelvis = original_end['measured'][pelvis]
    entry_error = dist(previous_pelvis, first['measured'][pelvis])
    travel_error = value_error(difference(last['measured'][pelvis], previous_pelvis), expected_delta)
    assert entry_error < .001 and travel_error < .002
    assert all(row['active_foot_anchors'] for row in continued['samples'])
    for id in ending.active_contacts:
        before = original_end['active_foot_anchors'][id]
        assert dist(first['active_foot_anchors'][id], before) < .001
        assert value_error(difference(last['active_foot_anchors'][id], before), expected_delta) < .002
    head = original_end['measured']['head.orientation']
    head_error = max(value_error(row['measured']['head.orientation'], head, 'quaternion')
                     for row in continued['samples'])
    assert head_error <= .5
    print(f'TIMING_CONTINUATION_PASSED {rig} frames={continued["frames"]} '
          f'entry_m={entry_error:.7f} displacement_m={travel_error:.7f} head_deg={head_error:.7f}', flush=True)


if __name__ == '__main__':
    rig, = sys.argv[sys.argv.index('--') + 1:]
    verify_continuation(rig)
