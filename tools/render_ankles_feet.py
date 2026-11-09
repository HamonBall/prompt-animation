"""Render current saved Stage 05.5 motion through the shared lossless writer."""
import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]

from avatar_app.movement_library import contracts as c
from tools import artifact_store as store
from tools.ankles_feet_evidence import VIEWS, case_path, numeric_valid, read, runtime
from tools.ankles_feet_playback import verify
from tools.artifact_bundle import validate_manifest
from tools.lossless_evidence import encode_view, recover_evidence, retire_pngs
from tools.movement_evidence import render
from tools.storage_policy import enforce


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rig', required=True)
    parser.add_argument('--case', required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    out = case_path(args.rig, args.case)
    assert numeric_valid(out)
    renderer = store.digest(Path(__file__))
    with store.producer_lease(out):
        recover_evidence(out)
        manifest, _, motion = validate_manifest(out)
        assert not manifest['views'], 'Existing media needs explicit reconciliation'
        before = (store.digest(motion), motion.stat().st_mtime_ns)
        profile = c.loads(c.AvatarProfile, (out / 'profile.json').read_text())
        handle = store.open_preview(out)
        started = time.perf_counter()
        playback = verify(handle, profile, out, read(out / 'result.json'))
        playback['runtime'] = runtime()
        store.atomic_json(out / 'saved-playback-review.json', playback)
        playback_s = time.perf_counter() - started
        views = {}
        plans = []
        timings = {}
        for label in VIEWS:
            started = time.perf_counter()
            view = render(handle, profile, out, side=label == 'side', width=160, lower_body=True)
            media, plan = encode_view(out, label, manifest['expected_frames'],
                                      fps=manifest['fps'], fps_base=manifest['fps_base'])
            view.update(media=media, renderer_sha256=renderer, framing='lower body and both floor contacts')
            views[label] = view
            plans.append(plan)
            timings[label] = time.perf_counter() - started
            store.write_manifest(out, handle.scene, views=views, complete=False)
        store.write_manifest(out, handle.scene, views=views, complete=True)
        retire_pngs(out, plans)
        assert before == (store.digest(motion), motion.stat().st_mtime_ns)
        assert renderer == store.digest(Path(__file__))
        store.atomic_json(out / 'render-timing.json', {
            'saved_playback_s': playback_s, 'seconds_by_view': timings,
            'rendered_frames': len(VIEWS) * len(manifest['expected_frames']),
        })
        enforce(out)
    print('FOOT_RENDER_PASSED', args.rig, args.case, playback['maxima'], flush=True)


if __name__ == '__main__':
    main()
