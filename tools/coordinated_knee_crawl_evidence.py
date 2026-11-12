"""Bake and independently replay the floor hands-and-knees crawl."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import coordinated_boundary_evidence as boundary
from tools import coordinated_evidence as evidence

SCRIPT = Path(__file__).resolve()
CASES = {
    f'{rig}/hands-knees-crawl': {
        'move': 'body.crawl', 'pose': pose, 'max_frames': 105,
        'parameters': {'support': 'hands_knees', 'lead': lead, 'distance_m': .06,
                       'clearance_m': .03, 'swing_s': .6},
    }
    for rig, pose, lead in (('demo', 'neutral', 'left'), ('mixamo', 'turned', 'right'))
}


if __name__ == '__main__':
    evidence.CASES.clear()
    evidence.CASES.update(CASES)
    evidence.NATIVE = SCRIPT
    evidence.HARNESS += ('tests/blender_knee_crawl.py', SCRIPT.relative_to(ROOT).as_posix())
    if '--' in sys.argv:
        import blender_coordinated_evidence as native
        from blender_knee_crawl import setup_knee_crawl

        def make_entry(rig, spec):
            return (*setup_knee_crawl(rig, spec['pose']), dict(spec['parameters']))

        native.make_entry = make_entry
        phase, key = sys.argv[sys.argv.index('--') + 1:]
        {'numeric': native.bake, 'render': native.render}[phase](key)
    else:
        boundary.SCRIPT = SCRIPT
        evidence.make_plan = boundary.make_plan
        raise SystemExit(evidence.main())
