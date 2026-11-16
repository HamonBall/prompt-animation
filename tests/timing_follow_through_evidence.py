"""Current-source unilateral wave replacements for the reviewed baseline."""

from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import timing_baseline_evidence as evidence
from timing_range_evidence import CASES as RANGE_CASES

CAPTURE = evidence.capture
CASES = {
    key: (*evidence.CASES[key.replace('/range-', '/').removesuffix('-current')][:-1], spec[-1])
    for key, spec in RANGE_CASES.items() if key.endswith('/range-undulation-follow-through-current')
}


def capture(key):
    captured = CAPTURE(key)
    _, _, fragment, _, result, parameters = captured
    rows = result['samples']
    spine = {track.control_id for track in fragment.tracks
             if track.control_id in ('torso.pitch', 'spine.mid.pitch', 'spine.upper.pitch')}
    assert spine, key
    expected_peak = parameters['angle'] / len(spine)
    for control in sorted(spine):
        start = rows[0]['measured'][control]
        peak = max(row['measured'][control] - start for row in rows)
        assert abs(peak - expected_peak) < .05, (key, control, peak, expected_peak)
        assert abs(rows[-1]['measured'][control] - start) < .05, (key, control)
    arm_control = f"{parameters['follow_through']}.upper_arm.orientation"
    assert any(track.control_id == arm_control and track.curve.kind == 'hold'
               and track.interval.start_s == 0 for track in fragment.tracks), key
    return captured


def configure():
    return patch.multiple(evidence, CASES=CASES, SCRIPT=Path(__file__).resolve(),
                          HARNESS=(*evidence.HARNESS, 'tests/timing_range_evidence.py',
                                   'tests/timing_follow_through_evidence.py'),
                          capture=capture)


if __name__ == '__main__':
    native = '--' in sys.argv
    if native:
        sys.argv[1:] = sys.argv[sys.argv.index('--') + 1:]
    with configure():
        result = evidence.main()
    if not native:
        raise SystemExit(result)
