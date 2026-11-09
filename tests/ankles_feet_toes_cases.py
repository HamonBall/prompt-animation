"""The explicit Stage 05.5 matrix, shared by the native and evidence drivers."""
from avatar_app.movement_library.feet import ANGLES, IDS


def cases():
    rows = []
    for move in IDS:
        pose = 'raised' if move.startswith('ankle.') or move == 'toes.curl' else 'crouched'
        for side in ('left', 'right'):
            rows.append((f'{move}.default.{side}', move, {'side': side}, pose))
        rows.append((move + '.turned', move, {'side': 'right'}, pose + '-turned'))
        if move in ANGLES:
            for label, bound in zip(('minimum', 'maximum'), ANGLES[move][:2]):
                rows.append((f'{move}.{label}', move, {'angle': bound}, pose))
        else:
            for label, bound in (('minimum', .045), ('maximum', .13)):
                rows.append((f'{move}.clearance.{label}', move, {'clearance_m': bound}, pose))
    rows.extend((
        ('pivot.forefoot.positive', 'foot.pivot', {'anchor': 'forefoot'}, 'crouched'),
        ('pivot.forefoot.negative', 'foot.pivot', {'anchor': 'forefoot', 'angle': -20, 'side': 'right'}, 'crouched-turned'),
        ('ankle.flex.supported.up', 'ankle.flex', {'support': 'pivot'}, 'crouched'),
        ('ankle.flex.supported.down', 'ankle.flex', {'support': 'pivot', 'angle': -12}, 'crouched'),
        ('ankle.tilt.supported', 'ankle.tilt', {'support': 'pivot', 'angle': 2}, 'crouched'),
        ('foot.place.distance.minimum', 'foot.place', {'distance_m': -.06}, 'crouched'),
        ('foot.place.distance.maximum', 'foot.place', {'distance_m': .09}, 'crouched'),
        ('foot.place.raised', 'foot.place', {'clearance_m': .045}, 'raised-crouched'),
        ('foot.tap.distance.minimum', 'foot.tap', {'distance_m': -.06}, 'crouched'),
        ('foot.tap.distance.maximum', 'foot.tap', {'distance_m': .09, 'side': 'right'}, 'crouched-turned'),
        ('foot.lift.preserve', 'foot.lift', {'return_policy': 'preserve_end'}, 'crouched'),
        ('ankle.flex.seated', 'ankle.flex', {'side': 'right'}, 'seated-raised'),
        ('timing.minimum', 'foot.lift', {'duration_s': .8, 'hold_s': 0}, 'crouched'),
        ('timing.maximum', 'foot.lift', {'duration_s': 2, 'hold_s': .5}, 'crouched-turned'),
    ))
    return tuple(rows)
