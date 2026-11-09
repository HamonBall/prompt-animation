"""Stage 05.5 strict cache, native process and actual-review gates."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from ankles_feet_toes_cases import cases
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.legs_evidence import BLENDER, BUILD, PYTHON, runtime
from tools.storage_policy import ARTIFACTS, confined, enforce

OUT = ARTIFACTS / 'stages/05.5'
NATIVE = ROOT / 'tests/blender_movement_ankles_feet_toes.py'
RENDERER = ROOT / 'tools/render_ankles_feet.py'
PLAYBACK = ROOT / 'tools/ankles_feet_playback.py'
VIEWS = ('front', 'side')
CASES_SOURCE = 'tests/ankles_feet_toes_cases.py'
RAISED_PLACE = 'foot.place.raised'
INITIAL_CASES_SHA256 = '5b2830c89b656110cae3ceb8e7c4c2c0cce7b2899b71da0b77e3bf5efe3674d9'
INITIAL_RAISED_ROW = b"('foot.place.raised', 'foot.place', {}, 'raised-crouched')"
CURRENT_RAISED_ROW = b"('foot.place.raised', 'foot.place', {'clearance_m': .045}, 'raised-crouched')"


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def case_path(rig, case):
    if rig not in ('demo', 'mixamo') or case not in {row[0] for row in cases()}:
        raise ValueError('Unknown Stage 05.5 case')
    return confined(OUT / rig / case, OUT)


def source_valid(directory, rig):
    source = read(directory / 'source.json')
    if rig == 'demo':
        return source == {'kind': 'procedural-demo-v1'}
    return source['kind'] == 'imported' and source['sha256'] == store.digest(ROOT / 'Hip Hop Mixamo.fbx')


def process_valid(out, operation, marker):
    record = read(out / (operation + '-process.json'))
    log = out / (operation + '.log.gz')
    if record['exit_code'] != 0 or record['runtime'] != runtime() or record['log_sha256'] != store.digest(log):
        return False
    with gzip.open(log, 'rb') as stream:
        data = stream.read(8 * 1024**2 + 1)
    return len(data) <= 8 * 1024**2 and marker.encode() in data and BUILD.encode() in data and b'Blender quit' in data


def case_source_valid(case, recorded):
    source = (ROOT / CASES_SOURCE).read_bytes()
    if hashlib.sha256(source).hexdigest() == recorded:
        return True
    # The native harness uses only the selected row. Verify the whole old file
    # by reversing exactly the one authored clearance change.
    if case == RAISED_PLACE or recorded != INITIAL_CASES_SHA256 or source.count(CURRENT_RAISED_ROW) != 1:
        return False
    original = source.replace(CURRENT_RAISED_ROW, INITIAL_RAISED_ROW, 1)
    return hashlib.sha256(original).hexdigest() == recorded


def numeric_valid(out):
    manifest, _, _ = validate_manifest(out)
    result = read(out / 'result.json')
    stamp = result['stage_05_5']
    _, _, parameters, fixture = next(row for row in cases() if row[0] == out.name)
    entry = manifest['entry']
    sources = stamp['stage_producer']
    return (
        result['review']['passed'] and result['frames'] == len(result['samples']) == len(manifest['expected_frames'])
        and stamp['rig'] == out.parent.name and stamp['case'] == out.name
        and stamp['fixture'] == fixture and entry['entry_fixture'] == 'authored:' + fixture
        and entry['movement_parameters'] == json.loads(json.dumps(parameters))
        and manifest['inputs'] == store.input_identity(out)
        and stamp['application_producer_sha256'] == manifest['inputs']['producer_sha256']
        and source_valid(out, out.parent.name)
        and set(sources) == {CASES_SOURCE, NATIVE.relative_to(ROOT).as_posix(),
                            'tests/blender_movement_hips_knees.py', 'tools/preview_movement.py'}
        and case_source_valid(out.name, sources[CASES_SOURCE])
        and all(store.digest(ROOT / name) == sha for name, sha in sources.items() if name != CASES_SOURCE)
        and process_valid(out, 'numeric', 'FOOT_NUMERIC_PASSED')
    )


def render_valid(out):
    if not numeric_valid(out) or not process_valid(out, 'render', 'FOOT_RENDER_PASSED'):
        return False
    manifest, _, motion = validate_manifest(out)
    review = read(out / 'saved-playback-review.json')
    return (
        manifest['complete'] and set(manifest['views']) == set(VIEWS) and store.files_complete(out, manifest)
        and review['passed'] and review['frames'] == len(manifest['expected_frames'])
        and review['motion_sha256'] == store.digest(motion) and review['motion_mtime_ns'] == motion.stat().st_mtime_ns
        and review['result_sha256'] == store.digest(out / 'result.json')
        and review['validator_sha256'] == store.digest(PLAYBACK) and review['runtime'] == runtime()
        and all(view['renderer_sha256'] == store.digest(RENDERER) for view in manifest['views'].values())
    )


def produce(out, operation):
    if operation == 'numeric':
        if (out / 'preview-manifest.json').exists():
            assert numeric_valid(out), f'Stale numeric evidence: {out}'
            print('REUSED_CURRENT_FOOT_NUMERIC', out, flush=True)
            return 0
        script = NATIVE
        marker = 'FOOT_NUMERIC_PASSED'
    else:
        assert numeric_valid(out), f'Numeric gate failed: {out}'
        script = RENDERER
        marker = 'FOOT_RENDER_PASSED'
    # A failed command leaves bounded diagnostics for explicit reconciliation.
    log = out / (operation + '.log.gz')
    if log.exists() or (out / (operation + '-process.json')).exists():
        raise RuntimeError(f'Existing {operation} output needs reconciliation: {out}')
    enforce(out, growth=8 * 1024**2, temporary=32 * 1024**2)
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(BLENDER), '--background', '--factory-startup', '--threads', '2',
           '--python-exit-code', '1', '--python', str(script), '--',
           '--rig', out.parent.name, '--case', out.name]
    started = time.perf_counter()
    cap = 8 * 1024**2
    logged = 0
    with subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process, gzip.open(log, 'wb') as stream:
        for chunk in iter(lambda: process.stdout.read(65536), b''):
            if logged < cap:
                stream.write(chunk[:cap - logged])
            logged += len(chunk)
        code = process.wait()
    store.atomic_json(out / (operation + '-process.json'), {
        'exit_code': code, 'runtime': runtime(), 'log_sha256': store.digest(log),
        'elapsed_s': time.perf_counter() - started, 'truncated': logged > cap,
    })
    if code or logged > cap or not process_valid(out, operation, marker):
        raise RuntimeError(f'{operation} failed for {out} (exit {code}); see {log}')
    assert (numeric_valid if operation == 'numeric' else render_valid)(out)
    print(marker, out.parent.name, out.name, flush=True)
    return 0


def review_identity(out):
    manifest, _, motion = validate_manifest(out)
    return {
        'motion_sha256': store.digest(motion), 'frames_per_view': len(manifest['expected_frames']),
        'media': {label: view['media']['sha256'] for label, view in manifest['views'].items()},
        'sheets': {label: store.digest(out / (label + '-sheet.png')) for label in VIEWS},
    }


def record_review(out, observation):
    if not observation.strip() or not render_valid(out):
        raise ValueError('Actual observation and current complete render are required')
    target = OUT / 'visual-review.json'
    with store.producer_lease(OUT):
        data = read(target) if target.exists() else {'cases': {}}
        data['cases'][f'{out.parent.name}/{out.name}'] = {
            **review_identity(out), 'actually_inspected': True, 'observation': observation,
        }
        store.atomic_json(target, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('numeric', 'render', 'check', 'record-review'))
    parser.add_argument('--rig', required=True, choices=('demo', 'mixamo'))
    parser.add_argument('--case', required=True)
    parser.add_argument('--observation')
    args = parser.parse_args()
    out = case_path(args.rig, args.case)
    if args.operation == 'check':
        if not numeric_valid(out):
            return 1
        if not (out / 'render-process.json').exists() and not read(out / 'preview-manifest.json')['views']:
            return 10
        return 0 if render_valid(out) else 1
    if args.operation == 'record-review':
        if args.observation is None:
            parser.error('record-review requires --observation')
        record_review(out, args.observation)
        return 0
    return produce(out, args.operation)


if __name__ == '__main__':
    raise SystemExit(main())
