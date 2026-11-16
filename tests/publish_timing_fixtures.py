"""Publish the typed records from verified, visually approved 05.7a cases."""

import argparse
from dataclasses import replace
import hashlib

import timing_baseline_evidence as baseline
import timing_pattern_evidence as first
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import prepare_fragment
from tools import artifact_store as store
from tools.root_motion_evidence import read
from tools.storage_policy import enforce

FIXTURES = baseline.ROOT / 'tests/fixtures/timing_patterns/v1'
IDS = {
    'transition-hold': ('timing.transition', 'timing.hold'),
    'repeat': ('timing.repeat',), 'phase': ('timing.phase_offset',),
    'sway': ('pattern.sway',), 'undulation': ('pattern.undulation',),
    'stroke-synchronized': ('pattern.strokes_synchronized',),
    'stroke-alternating': ('pattern.strokes_alternating',),
    'steps': ('pattern.steps',),
    'mirror': ('timing.mirror',), 'synchronize': ('timing.synchronize',),
    'alternate': ('timing.alternate',), 'overlap': ('timing.overlap',),
}
RECORDS = {'profile': c.AvatarProfile, 'entry': c.MotionStateSnapshot,
           'fragment': c.MotionFragment, 'executable': c.ExecutableMotion}


def movement_ids(name):
    name = name.removeprefix('range-')
    if name == 'traveling-steps':
        name = 'steps'
    elif name.startswith('strokes-'):
        name = 'stroke-' + name.split('-')[1]
    else:
        name = next((key for key in IDS if name == key or name.startswith(key + '-')), name)
    return IDS[name]


def build_manifest(include_range):
    reviews = read(baseline.OUT / 'visual-review.json')
    cases, records = {}, {}
    if include_range:
        from timing_baseline_compatibility import approved_baseline_identities
        reusable = approved_baseline_identities()
    else:
        reusable = {}

    def include(adapter, keys):
        for key in keys:
            evidence = adapter.case_path(key)
            identity = reusable[key] if key in reusable else adapter.review_identity(key)
            assert identity == {field: reviews[key][field] for field in ('motion', 'views')}
            assert all(reviews[key]['observations'][view].strip() for view in adapter.VIEWS)
            values = {field: c.loads(kind, (evidence / f'{field}.json').read_text(encoding='utf-8'))
                      for field, kind in RECORDS.items()}
            executable = values['executable']
            rebuilt = prepare_fragment(values['fragment'], values['entry'], values['profile'])
            assert rebuilt == replace(executable, loop=None), key
            snapshot = {}
            for field, value in values.items():
                payload = (c.dumps(value) + '\n').encode('utf-8')
                name = f'records/{hashlib.sha256(payload).hexdigest()}.json'
                records[name] = payload
                snapshot[field] = name
            result = read(evidence / 'result.json')
            published_key = key.replace('/range-undulation-follow-through-current', '/undulation-follow-through')
            cases[published_key] = {'ids': movement_ids(evidence.name), 'frames': result['frames'],
                          'records': snapshot, **identity}

    for adapter in (first, baseline):
        include(adapter, tuple(key for key in adapter.CASES if not include_range or key in reusable))
    if include_range:
        import timing_follow_through_evidence as follow_through
        from timing_range_evidence import configure
        with follow_through.configure():
            include(baseline, tuple(follow_through.CASES))
        configure()
        include(baseline, tuple(key for key in baseline.CASES if key not in follow_through.CASES))
    assert {id for case in cases.values() for id in case['ids']} == {id for ids in IDS.values() for id in ids}
    return {'schema_version': 1, 'profile_version': 8, 'cases': cases}, records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--include-range', action='store_true')
    args = parser.parse_args()
    manifest, records = build_manifest(args.include_range)
    if not args.check:
        enforce(baseline.OUT)
        (FIXTURES / 'records').mkdir(parents=True, exist_ok=True)
        for relative, payload in records.items():
            path = FIXTURES / relative
            if not path.exists():
                path.write_bytes(payload)
        assert all((FIXTURES / relative).read_bytes() == payload for relative, payload in records.items())
        store.atomic_json(FIXTURES / 'manifest.json', manifest)
        # Hash names identify the generated fixture records this publisher owns.
        for path in (FIXTURES / 'records').glob('*.json'):
            relative = path.relative_to(FIXTURES).as_posix()
            if relative not in records:
                assert path.stem == hashlib.sha256(path.read_bytes()).hexdigest()
                path.unlink()
    assert read(FIXTURES / 'manifest.json')['cases'] == {
        key: {**case, 'ids': list(case['ids'])} for key, case in manifest['cases'].items()
    }
    assert set((FIXTURES / 'records').glob('*.json')) == {FIXTURES / name for name in records}
    assert all((FIXTURES / relative).read_bytes() == payload for relative, payload in records.items())
    print('TIMING_FIXTURES_VERIFIED', len(manifest['cases']), len(records), sum(map(len, records.values())), flush=True)


if __name__ == '__main__':
    main()
