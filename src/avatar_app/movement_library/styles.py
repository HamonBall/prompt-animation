"""Local style transforms over the existing typed fragment bridge.

Native and visual validation determine the reviewed envelope; authoring a
candidate here does not certify its speed, acceleration or solved contacts.
"""
from dataclasses import dataclass, replace
from hashlib import sha256
from types import MappingProxyType

from . import contracts as c
from .compiler import prepare_fragment


@dataclass(frozen=True)
class StyleDefinition:
    id: str
    default_intensity: float
    minimum: float
    maximum: float
    maximum_hold_fraction: float
    compatibility: str


STYLE_REGISTRY = MappingProxyType({
    'style.robotic': StyleDefinition('style.robotic', .5, 0., 1., .2,
        'Explicit head yaw/pitch/roll and elbow flexion transitions; sole contacts only; '
        'selected controls only; no intermediate locked goals or measured-entry bindings.'),
    **{key: StyleDefinition(key, .5, 0., 1., 0., description) for key, description in (
        ('style.fluid', 'Blend toward seventh-order easing, fixed duration and path.'),
        ('style.heavy', 'Blend toward a slower preparation and late effort, fixed duration.'),
        ('style.playful', 'Blend toward early arrival and gradual recovery; deterministic, no noise.'),
        ('style.exaggerated', 'Up to 25 percent more unlocked intermediate excursion; fixed entry/exit.'),
        ('style.tired', 'Up to 25 percent less unlocked intermediate excursion; fixed entry/exit.'),
    )},
})


StyledFragment = c.StyledFragment


def _record(source, result, style_id, intensity, controls, unlocked=False):
    return StyledFragment(result, source.fragment_id, source.source_instance_ids,
                          style_id, intensity, controls,
                          sha256(c.dumps(source).encode()).hexdigest(), unlocked)


BUILDER_ID = 'styles.fragment.v1'


def style_builder(*args, **kwargs):
    c.fail('CONSTRAINT_CONFLICT', 'A style requires a source fragment and explicit control scope; use apply_style')


def register_styles(catalog, profile):
    from .registry import register_movement
    for definition in STYLE_REGISTRY.values():
        parameter = c.ParameterSpec('intensity', 'number', 'unitless', None, False, True,
                                    definition.default_intensity, definition.minimum, definition.maximum)
        register_movement(c.MovementDefinition(definition.id, 1, 'style', definition.compatibility,
            (parameter,), (), (), (), (), (), BUILDER_ID,
            ('local_fragment_transform', 'explicit_scope_required', 'experimental')), catalog)
    return catalog


def restyle(application, source, intensity, *, entry, profile):
    """Replace one style intensity using the hash-bound, unmodified source."""
    if (type(application) is not StyledFragment or type(source) is not c.MotionFragment
            or sha256(c.dumps(source).encode()).hexdigest() != application.source_sha256):
        c.fail('STALE_REVISION', 'Restyling requires the exact original source fragment')
    return apply_style(source, application.style_id, application.control_ids,
                       entry=entry, profile=profile, intensity=intensity,
                       amplitude_unlocked=application.amplitude_unlocked)


def apply_style(fragment, style_id, control_ids, *, entry, profile, intensity=.5,
                amplitude_unlocked=False):
    """Style one fragment locally; amplitude edits require explicit permission.

Amplitude permission declares intermediate authored waypoints to be optional.
Locked goals still override it. Entry/exit and all unselected controls remain
unchanged. This function is not a scheduler or a multi-instance composer.
    """
    c.check_type(style_id, c.ID, 'style_id')
    c.check_type(amplitude_unlocked, bool, 'amplitude_unlocked')
    if style_id not in STYLE_REGISTRY:
        c.fail('UNKNOWN_ID', 'Unknown style')
    if style_id == 'style.robotic':
        return apply_robotic(fragment, control_ids, entry=entry, profile=profile, intensity=intensity)
    if type(fragment) is not c.MotionFragment:
        c.fail('INVALID_PARAMETER', 'Style needs an original fragment')
    c.check_type(intensity, float, 'intensity')
    if not 0 <= intensity <= 1 or type(control_ids) is not tuple or not control_ids:
        c.fail('INVALID_PARAMETER', 'Invalid style intensity or scope')
    for key in control_ids:
        c.check_type(key, c.ID, 'control_id')
    c.distinct(control_ids, None)
    prepare_fragment(fragment, entry, profile)
    selected = set(control_ids)
    if not selected <= {track.control_id for track in fragment.tracks}:
        c.fail('UNKNOWN_ID', 'Style selected an unauthored control')
    if intensity == 0:
        return _record(fragment, fragment, style_id, intensity, control_ids, amplitude_unlocked)
    if any(t.track_id.startswith('styled.') or t.curve.style_timing is not None for t in fragment.tracks):
        c.fail('CONSTRAINT_CONFLICT', 'Restyle the original source instead of stacking')
    chosen = [t for t in fragment.tracks if t.control_id in selected]
    moving = [t for t in chosen if t.curve.kind == 'transition']
    if not moving or any(t.start_source != 'explicit' or t.curve.look_at_world_v1 is not None for t in chosen):
        c.fail('CONSTRAINT_CONFLICT', 'Style needs an explicit fixed-path transition')
    for track in moving:
        if any(g.locked and g.target.control_id == track.control_id
               and g.interval.end_s > track.interval.start_s
               and g.interval.start_s < track.interval.end_s for g in fragment.goals):
            c.fail('CONSTRAINT_CONFLICT', 'Style would change intermediate locked goal timing')
    amplitude = style_id in ('style.exaggerated', 'style.tired')
    if amplitude:
        if not amplitude_unlocked:
            c.fail('CONSTRAINT_CONFLICT', 'Amplitude changes need explicit optional-waypoint permission')
        # Limit amplitude edits to free upper-body scalar channels. Endpoint IK,
        # support controls and quaternion extrapolation need separate envelopes.
        allowed = {'head.yaw', 'head.pitch', 'head.roll', 'torso.yaw', 'torso.pitch', 'torso.roll',
                   'left.elbow.flexion', 'right.elbow.flexion'}
        if not selected <= allowed or any(e.anchor_id not in ('left.sole', 'right.sole') for e in fragment.contact_events):
            c.fail('CONSTRAINT_CONFLICT', 'Amplitude style is outside the free scalar envelope')
        origins = {}
        for key in selected:
            group = sorted((t for t in chosen if t.control_id == key), key=lambda t: t.interval.start_s)
            first, last = group[0], group[-1]
            end = last.curve.start_value if last.curve.kind == 'hold' else last.curve.end_value
            if first.value_shape != 'scalar' or first.curve.start_value != end:
                c.fail('CONSTRAINT_CONFLICT', 'Amplitude style requires an explicit returning scalar excursion')
            origins[key] = first.curve.start_value
        if any(g.locked and g.target.control_id in selected
               and g.target.value != origins[g.target.control_id] for g in fragment.goals):
            c.fail('CONSTRAINT_CONFLICT', 'Locked selected goals take precedence over amplitude style')
        scale = 1 + (.25 if style_id == 'style.exaggerated' else -.25) * intensity
        def scaled(value, key):
            return None if value is None else origins[key] + (value - origins[key]) * scale
        def transform(track):
            curve = replace(track.curve, start_value=scaled(track.curve.start_value, track.control_id),
                            end_value=scaled(track.curve.end_value, track.control_id))
            return replace(track, curve=curve)
    else:
        def transform(track):
            if track.curve.kind == 'hold':
                return track
            return replace(track, curve=replace(track.curve, style_timing=c.StyleTimingV1(style_id, intensity)))
    tracks = []
    for track in fragment.tracks:
        if track.control_id in selected:
            track = transform(track)
            token = sha256((style_id + track.track_id).encode()).hexdigest()[:24]
            track = replace(track, track_id='styled.' + token)
        tracks.append(track)
    result = replace(fragment, tracks=tuple(tracks))
    prepare_fragment(result, entry, profile)
    return _record(fragment, result, style_id, intensity, control_ids, amplitude_unlocked)


def apply_robotic(fragment, control_ids, *, entry, profile, intensity=.5):
    """Add a bounded preparation pause without moving any arrival boundary.

All selected tracks retain their path and endpoint. Unselected tracks, goals,
contacts, landmarks and duration remain exactly equal. Only explicitly bound
transitions are supported, so delayed measured-state binding cannot be frozen
prematurely. Style stacking requires returning to the source fragment.
    """
    if type(fragment) is not c.MotionFragment:
        c.fail('INVALID_PARAMETER', 'Style requires an original authored fragment')
    c.check_type(intensity, float, 'intensity')
    if not 0 <= intensity <= 1:
        c.fail('INVALID_PARAMETER', 'Style intensity must be between zero and one')
    if type(control_ids) is not tuple or not control_ids:
        c.fail('INVALID_PARAMETER', 'Style requires an explicit tuple of control IDs')
    for control in control_ids:
        c.check_type(control, c.ID, 'control_id')
    c.distinct(control_ids, None)
    prepare_fragment(fragment, entry, profile)
    selected = set(control_ids)
    if not selected <= {track.control_id for track in fragment.tracks}:
        c.fail('UNKNOWN_ID', 'Style selection contains an unauthored control')
    if intensity == 0:
        return _record(fragment, fragment, 'style.robotic', intensity, control_ids)
    if any(track.track_id.startswith('styled.') or track.curve.style_timing is not None for track in fragment.tracks):
        c.fail('CONSTRAINT_CONFLICT', 'Restyle the original source instead of stacking styles')
    candidates = [track for track in fragment.tracks
                  if track.control_id in selected and track.curve.kind == 'transition']
    if not candidates:
        c.fail('INVALID_PARAMETER', 'Selected controls have no transition to style')
    # Support transfer timing is deliberately excluded until its native envelope
    # is established. Even a fixed schedule does not prove safe retimed IK.
    allowed = {'head.yaw', 'head.pitch', 'head.roll',
               'left.elbow.flexion', 'right.elbow.flexion'}
    if not selected <= allowed or any(event.anchor_id not in ('left.sole', 'right.sole')
                                      for event in fragment.contact_events):
        c.fail('CONSTRAINT_CONFLICT', 'Contact-driving motion is outside this style envelope')
    for track in candidates:
        if track.start_source != 'explicit' or track.curve.look_at_world_v1 is not None:
            c.fail('CONSTRAINT_CONFLICT', 'Style requires an explicit fixed path')
        if any(goal.locked and goal.target.control_id == track.control_id
               and goal.interval.end_s > track.interval.start_s
               and goal.interval.start_s < track.interval.end_s for goal in fragment.goals):
            c.fail('CONSTRAINT_CONFLICT', 'Style overlaps an intermediate locked goal')
    if len(fragment.tracks) + len(candidates) > c.MAX_TRACKS:
        c.fail('RESOURCE_LIMIT', 'Style expansion exceeds the shared track budget')
    tracks = []
    for track in fragment.tracks:
        if track not in candidates:
            tracks.append(track)
            continue
        pause = track.curve.duration_s * .2 * intensity
        split = track.interval.start_s + pause
        token = sha256(track.track_id.encode()).hexdigest()[:24]
        tracks.append(replace(track, track_id=f'styled.{token}.pause',
            interval=c.TimeInterval(track.interval.start_s, split),
            curve=c.CurveSpec('hold', track.curve.start_value, None, pause)))
        tracks.append(replace(track, track_id=f'styled.{token}.move',
            interval=c.TimeInterval(split, track.interval.end_s),
            curve=replace(track.curve, duration_s=track.curve.duration_s - pause,
                          easing='smootherstep')))
    result = replace(fragment, tracks=tuple(tracks))
    prepare_fragment(result, entry, profile)
    return _record(fragment, result, 'style.robotic', intensity, control_ids)
