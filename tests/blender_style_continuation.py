"""Continue a styled saved motion using its measured exit and test rejection rollback."""
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests')]

from avatar_app.blender.motion import build_action
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import prepare_fragment, value_error
from avatar_app.movement_library.patterns import transition_fragment
from avatar_app.movement_library.styles import apply_style
from blender_coordinated_evidence import restore_surfaces
from style_evidence import case_path, numeric_valid
from tools import artifact_store as store


def check(rig):
    if rig not in ('demo', 'mixamo'):
        raise ValueError('Unknown continuation rig')
    directory = case_path(rig + '/heavy-visible-maximum')
    result = numeric_valid(rig + '/heavy-visible-maximum')
    profile = c.loads(c.AvatarProfile, (directory / 'profile.json').read_text())
    ending = c.from_dict(c.MotionStateSnapshot, result['ending_state'])
    handle = store.open_preview(directory)
    restore_surfaces(handle, {'stage_05_6c': result['stage_05_7b']})
    handle.scene.frame_set(handle.scene.frame_end)
    values = {value.control_id: value for value in ending.measured_controls}
    control = values['left.elbow.flexion']
    source = transition_fragment((replace(control, value=control.value + 10.),), 2.,
                                 instance_id='style.continuation', entry=ending, profile=profile)
    styled = apply_style(source, 'style.fluid', (control.control_id,), entry=ending,
                         profile=profile, intensity=.5)
    motion = prepare_fragment(styled.fragment, ending, profile)
    action = handle.rig.animation_data.action
    frame = handle.scene.frame_current
    matrix = handle.rig.matrix_world.copy()
    try:
        incompatible = replace(ending, measured_controls=tuple(
            replace(value, value=value.value + 10.)
            if value.control_id == control.control_id else value
            for value in ending.measured_controls))
        build_action(handle, replace(motion, entry_snapshot=incompatible), profile=profile)
    except c.MotionContractError as error:
        assert error.code == 'ENTRY_MISMATCH', error.to_dict()
    else:
        raise AssertionError('Incompatible continuation unexpectedly succeeded')
    assert handle.rig.animation_data.action == action
    assert handle.scene.frame_current == frame and handle.rig.matrix_world == matrix
    continued = build_action(handle, motion, profile=profile)
    assert continued['review']['passed'] and not continued['experimental']
    rows = continued['samples']
    assert abs(rows[0]['measured'][control.control_id] - control.value) < .05
    assert abs(rows[-1]['measured'][control.control_id] - control.value - 10.) < .05
    for row in rows:
        assert row['active_foot_anchors'].keys() == set(ending.active_contacts)
        assert value_error(row['measured']['head.orientation'],
                           rows[0]['measured']['head.orientation'], 'quaternion') < .5
    print('STYLE_CONTINUATION_PASSED', rig, continued['frames'], continued['review'], flush=True)


if __name__ == '__main__':
    check(*sys.argv[sys.argv.index('--') + 1:])
