"""Small native robotic-style pilot; no retained motion or rendered evidence."""
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests')]

from avatar_app.movement_library.compiler import prepare_fragment, value_error
from avatar_app.movement_library.patterns import transition_fragment
from avatar_app.movement_library.styles import apply_robotic, apply_style, STYLE_REGISTRY


def case_parameters(rig, pose, intensity):
    if rig not in ('demo', 'mixamo') or pose not in ('neutral', 'turned-crouched'):
        raise ValueError('Unknown style pilot rig or entry')
    if intensity not in ('0', '0.5', '1'):
        raise ValueError('Unknown style pilot intensity')
    return float(intensity)


def check(rig, pose, intensity):
    intensity = case_parameters(rig, pose, intensity)
    from avatar_app.blender.motion import build_action
    from blender_movement_root_travel_flight import setup
    handle, profile, entry = setup(rig, pose)
    values = {v.control_id: v for v in entry.measured_controls}
    key = 'left.elbow.flexion'
    target = replace(values[key], value=values[key].value + 8.)
    source = transition_fragment((target,), 2., instance_id='style.pilot',
                                 entry=entry, profile=profile)
    styled = apply_robotic(source, (key,), entry=entry, profile=profile, intensity=intensity)
    result = build_action(handle, prepare_fragment(styled.fragment, entry, profile), profile=profile)
    assert result['review']['passed'] and not result['experimental'], result['review']
    rows = result['samples']
    assert len(rows) == 61
    assert abs(rows[-1]['measured'][key] - target.value) < .05
    for row in rows:
        assert row['active_foot_anchors'].keys() == set(entry.active_contacts)
        assert value_error(row['measured']['head.orientation'],
                           rows[0]['measured']['head.orientation'], 'quaternion') < .5
        if row['time_s'] <= .4 * intensity + 1e-9:
            assert abs(row['measured'][key] - values[key].value) < .05
    print('STYLE_ROBOTIC_PASSED', rig, pose, intensity, result['review'], flush=True)


def check_family(style, rig, pose, intensity, excursion=8.):
    if style not in STYLE_REGISTRY:
        raise ValueError('Unknown style family')
    amount = case_parameters(rig, pose, intensity)
    excursion = float(excursion)
    if excursion not in (8., 40.):
        raise ValueError('Unknown style pilot excursion')
    from avatar_app.blender.motion import build_action
    from blender_movement_root_travel_flight import setup
    handle, profile, entry = setup(rig, pose)
    values = {v.control_id: v for v in entry.measured_controls}
    key = 'left.elbow.flexion'
    target = replace(values[key], value=values[key].value + excursion)
    first = transition_fragment((target,), 2., instance_id='style.family', entry=entry, profile=profile)
    track, = first.tracks
    returning = replace(track, track_id='style.return', interval=type(track.interval)(2., 4.),
                        curve=replace(track.curve, start_value=target.value, end_value=values[key].value))
    source = replace(first, duration_s=4., tracks=(track, returning),
                     contact_events=tuple(replace(e, interval=type(e.interval)(0., 4.)) for e in first.contact_events))
    amplitude = style in ('style.exaggerated', 'style.tired')
    application = apply_style(source, style, (key,), entry=entry, profile=profile,
                              intensity=amount, amplitude_unlocked=amplitude)
    motion = prepare_fragment(application.fragment, entry, profile)
    result = build_action(handle, motion, profile=profile)
    assert result['review']['passed'] and not result['experimental'], result['review']
    rows = result['samples']
    assert len(rows) == 121
    assert abs(rows[-1]['measured'][key] - values[key].value) < .05
    factor = 1 + ((.25 if style == 'style.exaggerated' else -.25) * amount if amplitude else 0)
    assert abs(rows[60]['measured'][key] - (values[key].value + excursion * factor)) < .05
    for row in rows:
        assert row['active_foot_anchors'].keys() == set(entry.active_contacts)
        assert value_error(row['measured']['head.orientation'],
                           rows[0]['measured']['head.orientation'], 'quaternion') < .5
    print('STYLE_FAMILY_PASSED', style, rig, pose, amount, result['review'], flush=True)
    return handle, profile, entry, source, application, motion, result


if __name__ == '__main__':
    if '--' in sys.argv:
        args = sys.argv[sys.argv.index('--') + 1:]
        if len(args) in (4, 5):
            check_family(*args)
        else:
            check(*args)
    else:
        for rig in ('demo', 'mixamo'):
            for pose in ('neutral', 'turned-crouched'):
                for intensity in ('0', '0.5', '1'):
                    case_parameters(rig, pose, intensity)
                    for style in STYLE_REGISTRY:
                        assert style.startswith('style.')
        for args in (('bad', 'neutral', '1'), ('demo', 'bad', '1'), ('demo', 'neutral', '2')):
            try:
                case_parameters(*args)
            except ValueError:
                continue
            raise AssertionError('Invalid case was accepted')
        print('STYLE_ROUTING_PASSED')
