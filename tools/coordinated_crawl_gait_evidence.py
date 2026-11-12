"""Bake and review the revised crawl gait on both rigs."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import coordinated_boundary_evidence as boundary
from tools import coordinated_crawl_limit_evidence as crawl_limit
from tools import coordinated_evidence as evidence

SCRIPT = Path(__file__).resolve()
CASES = {
    'demo/low-crawl-gait': {
        'move': 'body.crawl', 'pose': 'turned-crouched', 'max_frames': 105,
        'parameters': {'lead': 'left', 'distance_m': .06, 'clearance_m': .04, 'swing_s': .6},
    },
    'mixamo/low-crawl-gait-maximum': {**crawl_limit.SPEC, 'max_frames': 141},
}


if __name__ == '__main__':
    evidence.CASES.clear()
    evidence.CASES.update(CASES)
    evidence.NATIVE = SCRIPT
    evidence.HARNESS += ('tools/coordinated_crawl_limit_evidence.py', SCRIPT.relative_to(ROOT).as_posix())
    if '--' in sys.argv:
        import blender_coordinated_evidence as native

        original_entry = native.make_entry

        def make_entry(rig, spec):
            return crawl_limit.make_entry(rig, spec) if rig == 'mixamo' else original_entry(rig, spec)

        native.make_entry = make_entry
        phase, key = sys.argv[sys.argv.index('--') + 1:]
        {'numeric': native.bake, 'render': native.render}[phase](key)
    else:
        boundary.SCRIPT = SCRIPT
        evidence.make_plan = boundary.make_plan
        raise SystemExit(evidence.main())
