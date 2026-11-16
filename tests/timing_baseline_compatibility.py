"""Prove unchanged baseline evidence across two scoped pattern fixes."""

from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import timing_baseline_evidence as baseline
import timing_pattern_evidence as first
from tools import artifact_store as store
from tools.root_motion_evidence import read

SOURCE = baseline.ROOT / 'src/avatar_app/movement_library/patterns.py'
AFFECTED = {f'{rig}/undulation-follow-through' for rig in ('demo', 'mixamo')}


def predecessor_digest():
    """Reconstruct precisely the removed predecessor bytes for identity checking."""
    data = SOURCE.read_bytes()
    split = b'\r\n' if b'\r\n' in data else b'\n'
    marker = b'        # The torso moves during the delay. Keep each selected arm in its'
    end = b'        torso = replace(torso, tracks=prelude + torso.tracks)' + split
    assert data.count(marker) == data.count(end) == 1
    begin = data.index(marker)
    finish = data.index(end, begin) + len(end)
    data = data[:begin] + data[finish:]

    def restore(current, prior):
        nonlocal data
        current = current.encode().replace(b'\n', split)
        prior = prior.encode().replace(b'\n', split)
        assert data.count(current) == 1, current
        data = data.replace(current, prior)

    start = data.index(b'        swing_side = order[index % 2]')
    finish = data.index(b'        for track in fragment.tracks:', start)
    assert b'        def translated_track(point, key):' in data[start:finish]
    data = data[:start] + data[finish:]
    restore('start_value=translated_track(curve.start_value, key),',
            'start_value=translated(curve.start_value, measured[key], previous[key]),')
    restore('end_value=translated_track(curve.end_value, key))',
            'end_value=translated(curve.end_value, measured[key], previous[key]))')
    restore('value=translated_track(target.value, key))',
            'value=translated(target.value, measured[key], previous[key]))')
    restore('            if index >= 2 and event.interval.start_s > 0:\n'
            '                target = (*target[:2], event.target_world_v1[2])\n', '')
    return sha256(data).hexdigest()


def approved_baseline_identities():
    """Verify the exact previous source and output, then classify affected consumers."""
    previous = predecessor_digest()
    digest = store.digest
    reviews = read(baseline.OUT / 'visual-review.json')
    result = {}

    def historical_digest(path):
        return previous if Path(path).resolve() == SOURCE else digest(path)

    with patch.object(store, 'digest', historical_digest):
        for adapter in (first, baseline):
            for key, spec in adapter.CASES.items():
                proof = adapter.review_identity(key)
                assert proof == {field: reviews[key][field] for field in ('motion', 'views')}
                assert all(reviews[key]['observations'][view].strip() for view in adapter.VIEWS)
                has_follow_through = (adapter is baseline and spec[2] == 'torso'
                                       and spec[3]['follow_through'] is not None)
                assert has_follow_through == (key in AFFECTED), key
                if key.endswith('/traveling-steps'):
                    saved = read(adapter.case_path(key) / 'result.json')
                    assert saved['stage_05_7a']['parameters']['count'] <= 2, key
                if not has_follow_through:
                    result[key] = proof
    assert len(result) == len(first.CASES) + len(baseline.CASES) - len(AFFECTED)
    return result


if __name__ == '__main__':
    proofs = approved_baseline_identities()
    print('TIMING_BASELINE_REUSE_VERIFIED', len(proofs), 'requires_replacement', sorted(AFFECTED), flush=True)
