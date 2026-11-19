"""Publish source-bound typed records after current-source visual review."""
import argparse
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests')]

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import prepare_fragment
from tools import artifact_store as store
from tools.storage_policy import enforce
import style_evidence
import style_range_evidence
import style_pattern_evidence

FIXTURES = ROOT / 'tests/fixtures/motion_styles/v1'
RECORDS = {'profile': c.AvatarProfile, 'entry': c.MotionStateSnapshot,
           'fragment': c.MotionFragment, 'executable': c.ExecutableMotion,
           'source-fragment': c.MotionFragment, 'style': c.StyledFragment}


def publication():
    reviews = style_evidence.read(style_evidence.OUT / 'visual-review.json')
    cases, records = {}, {}
    for adapter in (style_evidence, style_range_evidence, style_pattern_evidence):
        for key in adapter.CASES:
            directory = adapter.case_path(key)
            identity = adapter.review_identity(key)
            review = reviews[key]
            assert identity == {field: review[field] for field in ('motion', 'views')}
            assert all(review['observations'][view].strip() for view in adapter.VIEWS)
            values = {name: c.loads(kind, (directory / (name + '.json')).read_text(encoding='utf-8'))
                      for name, kind in RECORDS.items()}
            assert prepare_fragment(values['fragment'], values['entry'], values['profile']) == replace(
                values['executable'], loop=None)
            application = values['style']
            assert application.fragment == values['fragment']
            assert application.source_sha256 == sha256(c.dumps(values['source-fragment']).encode()).hexdigest()
            references = {}
            for name, value in values.items():
                payload = (c.dumps(value) + '\n').encode()
                relative = 'records/' + sha256(payload).hexdigest() + '.json'
                records[relative] = payload
                references[name] = relative
            cases[key] = dict(style_id=application.style_id, intensity=application.intensity,
                              frames=adapter.CASES[key][2], records=references, **identity)
    assert len(cases) == 32
    assert {case['style_id'] for case in cases.values()} == {
        'style.' + name for name in ('fluid', 'robotic', 'heavy', 'playful', 'exaggerated', 'tired')}
    return dict(schema_version=1, stage='05.7b', cases=cases), records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    manifest, records = publication()
    if args.apply:
        enforce(style_evidence.OUT, growth=sum(len(payload) for payload in records.values()))
        FIXTURES.mkdir(parents=True, exist_ok=True)
        with store.producer_lease(style_evidence.OUT):
            for relative, payload in records.items():
                path = FIXTURES / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists():
                    assert path.read_bytes() == payload
                else:
                    path.write_bytes(payload)
            store.atomic_json(FIXTURES / 'manifest.json', manifest)
    else:
        assert style_evidence.read(FIXTURES / 'manifest.json') == manifest
        assert all((FIXTURES / name).read_bytes() == payload for name, payload in records.items())
    print('STYLE_FIXTURES_VERIFIED', len(cases := manifest['cases']), len(records), flush=True)


if __name__ == '__main__':
    main()
