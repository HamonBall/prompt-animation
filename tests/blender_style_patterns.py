"""Native semantic-preservation probes for styled existing pattern families."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests')]

from avatar_app.movement_library.compiler import prepare_fragment, value_error
from avatar_app.movement_library.patterns import stroke_pattern, torso_pattern, step_pattern
from avatar_app.movement_library.styles import apply_style


def parameters(style, family, rig):
    if style not in ('style.fluid', 'style.heavy', 'style.playful'):
        raise ValueError('Unknown pattern style')
    if family not in ('stroke', 'torso', 'step') or rig not in ('demo', 'mixamo'):
        raise ValueError('Unknown pattern or rig')
    return 'turned-crouched' if family == 'step' or rig == 'mixamo' else 'neutral'


def check(style, family, rig):
    pose = parameters(style, family, rig)
    from avatar_app.blender.motion import build_action
    from blender_movement_root_travel_flight import setup
    handle, profile, entry = setup(rig, pose)
    kwargs = dict(fragment_id='style.pattern', entry=entry, profile=profile, surfaces=handle.surfaces)
    if family == 'stroke':
        source = stroke_pattern('synchronized', {'amplitude_m': .04, 'duration_s': 1.2, 'hold_s': .1}, 1, **kwargs)
    elif family == 'torso':
        source = torso_pattern('sway', {'angle': 5.}, 1, **kwargs)
    else:
        source = step_pattern('left', {'distance_m': .06, 'clearance_m': .04}, 2, **kwargs)
    controls = tuple(sorted({t.control_id for t in source.tracks if t.curve.kind == 'transition'}))
    application = apply_style(source, style, controls, entry=entry, profile=profile, intensity=1.)
    baseline = build_action(handle, prepare_fragment(source, entry, profile), profile=profile)
    assert baseline['review']['passed'] and not baseline['experimental'], baseline['review']
    handle.scene.frame_set(1)
    result = build_action(handle, prepare_fragment(application.fragment, entry, profile), profile=profile)
    assert result['review']['passed'] and not result['experimental'], result['review']
    assert application.fragment.contact_events == source.contact_events
    rows, originals = result['samples'], baseline['samples']
    assert len(rows) == len(originals)
    specs = {control.id: control for control in profile.controls}
    maxima = {}
    for actual, original in zip(rows, originals):
        assert actual['active_foot_anchors'] == original['active_foot_anchors']
        head = value_error(actual['measured']['head.orientation'], original['measured']['head.orientation'], 'quaternion')
        assert head < .5, head
    for key in controls:
        shape = specs[key].value_shape
        error = max(value_error(rows[i]['measured'][key], originals[i]['measured'][key], shape) for i in (0, -1))
        maxima[key] = error
        assert error < (.01 if specs[key].unit == 'metre' else 3.), (key, error)
    print('STYLE_PATTERN_PASSED', style, family, rig, result['review'], 'endpoint_errors', maxima, flush=True)
    return handle, profile, entry, source, application, prepare_fragment(application.fragment, entry, profile), result


if __name__ == '__main__':
    if '--' in sys.argv:
        check(*sys.argv[sys.argv.index('--') + 1:])
    else:
        for style in ('style.fluid', 'style.heavy', 'style.playful'):
            for family in ('stroke', 'torso', 'step'):
                for rig in ('demo', 'mixamo'):
                    parameters(style, family, rig)
        for args in (('bad', 'stroke', 'demo'), ('style.fluid', 'bad', 'demo'), ('style.fluid', 'step', 'bad')):
            try:
                parameters(*args)
            except ValueError:
                continue
            raise AssertionError('Accepted invalid pattern route')
        print('STYLE_PATTERN_ROUTING_PASSED')
