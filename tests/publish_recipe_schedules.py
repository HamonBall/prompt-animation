"""Publish/verify bounded deterministic Stage 06 logical fixtures (no Blender)."""
import argparse
import json
from dataclasses import replace
from pathlib import Path

from avatar_app.motion import Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.composer import compose_recipe
from test_recipe_composition import context, instance, recipe

OUT = Path(__file__).parent / 'fixtures/recipe_schedules/v1'


def cases():
    for rig in ('demo', 'mixamo'):
        profile, entry, catalog = context(rig, 'standing-to-seated')
        arm = instance(profile, catalog, 'gesture', 'arm.stroke')
        head = instance(profile, catalog, 'look', 'head.look')
        seat = instance(profile, catalog, 'seat', 'body.floor_transfer', route='standing_to_seated')
        hold = instance(profile, catalog, 'hold', 'hand.hold')
        values = {
            'parallel': recipe(profile, entry, (arm, head)),
            'sequential': recipe(profile, entry, (seat, arm), (c.Relation('then', 'after', 'seat', 'gesture', 0),)),
            'hard-conflict': recipe(profile, entry, (hold, arm)),
            'duplicate-contact': recipe(profile, entry, (head, instance(profile, catalog, 'look2', 'head.look'))),
        }
        # Contact-only duplicate schedule uses a single active sole and two
        # real acquisition instances, avoiding unrelated head-track conflicts.
        contact_entry = replace(entry, active_contacts=('right.sole',))
        values['duplicate-contact'] = recipe(profile, contact_entry, tuple(
            instance(profile, catalog, id, 'support.acquire_release', operation='acquire') for id in ('a', 'b')))
        for name, value in values.items():
            selected_entry = contact_entry if name == 'duplicate-contact' else entry
            data = {'recipe': c.to_dict(value), 'entry_case': f'{rig}/standing-to-seated',
                    'active_contacts': list(selected_entry.active_contacts)}
            try:
                data['resolved'] = c.to_dict(compose_recipe(value, selected_entry, profile, (Surface(),), catalog))
            except c.MotionContractError as error:
                if name != 'hard-conflict':
                    raise
                data['error'] = {'code': error.code, 'details': error.details}
            yield f'{rig}-{name}.json', data
        cyclic = c.to_dict(values['parallel'])
        cyclic['relations'] = [c.to_dict(c.Relation('forward', 'after', 'gesture', 'look', 0)),
                               c.to_dict(c.Relation('back', 'after', 'look', 'gesture', 0))]
        try:
            c.from_dict(c.MotionRecipe, cyclic)
        except c.MotionContractError as error:
            yield f'{rig}-cycle.json', {'recipe': cyclic, 'error': {'code': error.code, 'message': str(error)}}
        else:
            raise AssertionError('Cycle was accepted')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    expected = dict(cases())
    if args.write:
        OUT.mkdir(parents=True, exist_ok=True)
    for name, value in expected.items():
        text = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'
        path = OUT / name
        if args.write:
            path.write_text(text, encoding='utf-8')
        elif path.read_text(encoding='utf-8') != text:
            raise AssertionError(f'Stale logical fixture: {path}')
    if {path.name for path in OUT.glob('*.json')} != set(expected):
        raise AssertionError('Unexpected logical fixture files')
    print(json.dumps({'verified_cases': len(expected), 'bytes': sum(path.stat().st_size for path in OUT.glob('*.json'))}))


if __name__ == '__main__':
    main()
