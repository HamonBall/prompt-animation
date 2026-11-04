"""Explicit tiny real-Blender pipeline pilot; never touches stage evidence.

Run `python tests/evidence_job_smoke.py config` to write a runnable configuration.
Only an actual inspection can create review-approval.json; no auto-review here.
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.storage_policy import enforce

OUT = ROOT / 'artifacts/maintenance/evidence-runner'
CASE = OUT / 'smoke'
BLENDER = Path('C:/Program Files/Blender Foundation/Blender 5.1/blender.exe')
PYTHON = BLENDER.parent / '5.1/python/bin/python.exe'


def numeric():
    manifest, _, _ = validate_manifest(CASE)
    result = json.loads((CASE / 'result.json').read_text())
    assert result['review']['passed'] and manifest['inputs'] == store.input_identity(CASE)
    return manifest


def check():
    manifest = numeric()
    process = CASE / 'pilot-render.json'
    if not process.exists() and not manifest['complete']:
        return 10
    assert process.exists(), 'Unverified existing render'
    saved = json.loads(process.read_text())
    assert saved['source'] == store.digest(Path(__file__))
    assert saved['manifest'] == store.digest(CASE / 'preview-manifest.json')
    assert store.files_complete(CASE, manifest)
    return 0


def main(operation):
    if operation == 'config':
        enforce(OUT, growth=8*1024**2, temporary=64*1024**2)
        py = lambda op: [str(PYTHON), str(Path(__file__)), op]
        native = [str(BLENDER), '--background', '--threads', '2', '--factory-startup', '--python-exit-code', '1',
                  '--python', str(Path(__file__)), '--', 'render']
        store.atomic_json(OUT / 'pipeline.json', {'schema_version': 1, 'preflight_argv': py('preflight'),
            'numeric_gate_argv': py('prepare'), 'verify_argv': py('check'), 'review_check_argv': py('review'),
            'storage_argv': py('storage'), 'review_directory': str(OUT / 'review'),
            'cases': [{'id': 'demo/head.look', 'directory': str(CASE), 'check_argv': py('check'),
                       'render_argv': native, 'timeout_s': 300}]})
        print(str(OUT / 'pipeline.json'))
    elif operation in ('preflight', 'storage'):
        report = enforce(OUT, growth=8*1024**2 if operation == 'preflight' else 0, temporary=64*1024**2 if operation == 'preflight' else 0)
        print('EVIDENCE_RESULT ' + json.dumps(report))
    elif operation == 'prepare':
        if not (CASE / 'preview-manifest.json').exists():
            args = [str(BLENDER), '--background', '--threads', '2', '--factory-startup', '--python-exit-code', '1',
                    '--python', str(ROOT / 'tools/preview_movement.py'), '--', '--id', 'head.look', '--version', '1',
                    '--rig', 'demo', '--parameters', '{"yaw":5,"duration_s":0.8,"hold_s":0}',
                    '--entry', str(ROOT / 'tests/fixtures/movement_fragments/v1/entry-neutral.json'), '--output-dir', str(CASE)]
            subprocess.run(args, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        numeric()
    elif operation == 'check':
        return check()
    elif operation == 'render':
        from avatar_app.movement_library import contracts as c
        from tools.movement_evidence import render
        from tools.lossless_evidence import encode_view, retire_pngs, recover_evidence
        numeric()
        with store.producer_lease(CASE):
            recover_evidence(CASE)
            h = store.open_preview(CASE)
            profile = c.loads(c.AvatarProfile, (CASE / 'profile.json').read_text())
            views, plans = {}, []
            for label in ('front', 'side'):
                record = render(h, profile, CASE, side=label == 'side', width=64)
                media, plan = encode_view(CASE, label, range(h.scene.frame_start, h.scene.frame_end + 1), fps=30, fps_base=1)
                record['media'] = media
                views[label] = record
                plans.append(plan)
            h.scene.frame_set(1)
            store.write_manifest(CASE, h.scene, views=views, complete=True)
            retire_pngs(CASE, plans)
            store.atomic_json(CASE / 'pilot-render.json', {'source': store.digest(Path(__file__)),
                              'manifest': store.digest(CASE / 'preview-manifest.json')})
            check()
    elif operation == 'review':
        check()
        approval = OUT / 'review-approval.json'
        if not approval.exists():
            print('Actual full-motion review required; see review/review-index.json')
            return 75
        record = json.loads(approval.read_text())
        assert record['manifest_sha256'] == store.digest(CASE / 'preview-manifest.json')
        assert record['actually_inspected'] and record['observations']
    else:
        raise ValueError(operation)
    return 0


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    raise SystemExit(main(args[0]))
