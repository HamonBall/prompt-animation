"""Verified historical scene compaction. Dry run by default; --apply commits.

Only Stage 05.1a/05.1b are eligible. Numeric records, images and old receipts are
never regenerated. Every candidate is reopened in a fresh Blender process.
"""
import argparse
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
from tools.artifact_store import atomic_json, atomic_replace, digest, producer_lease, process_alive

EVIDENCE = ROOT / 'artifacts/maintenance/neutral-artifacts/compaction'
BLENDER = Path('C:/Program Files/Blender Foundation/Blender 5.1/blender.exe')
STAGES = ('05.1a', '05.1b')
VALIDATOR_VERSION = 2


def safe_path(path, allowed):
    path = Path(os.path.abspath(path))
    roots = [Path(os.path.abspath(p)) for p in allowed]
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError('Compaction path outside allowed stage roots: ' + str(path))
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError('Compaction refuses symlink/junction traversal: ' + str(part))
    if path.resolve() != path:
        raise ValueError('Compaction path does not resolve in place')
    return path


def inventory(directory, allowed, *, hashes=False):
    directory = safe_path(directory, allowed)
    value = {}
    def visit(current):
        # DirEntry keeps Windows enumeration metadata cached. Repeated Path.stat
        # calls on tens of thousands of frames make an audit unnecessarily slow.
        with os.scandir(current) as entries:
            for entry in entries:
                path = Path(entry.path)
                stat = entry.stat(follow_symlinks=False)
                if entry.is_symlink() or getattr(stat, 'st_file_attributes', 0) & 0x400:
                    raise ValueError('Compaction refuses reparse/symlink traversal: ' + str(path))
                if entry.is_dir(follow_symlinks=False):
                    visit(path)
                    continue
                if entry.name == '.artifact-writer.lock':
                    owner = json.loads(path.read_text(encoding='utf-8'))
                    if owner['pid'] != os.getpid() and process_alive(owner['pid']):
                        raise RuntimeError('Active artifact writer: ' + str(path))
                    continue
                record = {'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
                if hashes and path.suffix in ('.blend', '.blend1', '.json'):
                    record['sha256'] = digest(path)
                value[str(path.relative_to(directory))] = record
    visit(directory)
    return value


def active_blender_processes():
    """Fail closed before spawning workers; no historical writer may be active."""
    if os.name != 'nt':
        result = subprocess.run(['pgrep','-a','blender'], capture_output=True, text=True)
        return result.stdout.strip()
    result = subprocess.run(['powershell','-NoProfile','-Command',
        "Get-Process blender -ErrorAction SilentlyContinue | Select-Object Id,ProcessName | ConvertTo-Json -Compress"],
        capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError('Cannot establish active Blender writer state')
    return result.stdout.strip()


def worker(mode, job, report, log):
    with Path(log).open('w', encoding='utf-8') as stream:
        completed = subprocess.run([str(BLENDER), '--background', '--factory-startup', '--python-exit-code', '1',
                    '--python', str(ROOT/'tools/blender_artifact_worker.py'), '--',
                    '--mode', mode, '--job', str(job), '--report', str(report)], stdout=stream, stderr=subprocess.STDOUT)
    if not Path(report).is_file():
        raise RuntimeError(f'Blender {mode} produced no report; see {log}')
    value = json.loads(Path(report).read_text(encoding='utf-8'))
    if completed.returncode != 0 or not value.get('passed'):
        raise RuntimeError(f'Blender {mode} failed: {value.get("error", completed.returncode)}; see {log}')
    return value


def compact_case(directory, allowed, evidence, *, apply=False):
    directory = safe_path(directory, allowed)
    canonical = directory / 'preview.blend'
    migration = directory / 'artifact-migration.json'
    files = sorted(p for p in directory.iterdir() if p.suffix in ('.blend','.blend1'))
    for path in files: safe_path(path, allowed)
    if not files: return {'directory': str(directory), 'status': 'no_scenes'}
    if migration.is_file():
        previous = json.loads(migration.read_text(encoding='utf-8'))
        if canonical.is_file() and previous.get('canonical_sha256') == digest(canonical):
            pending = [Path(p) for p in previous.get('retired', {}) if Path(p).exists()]
            for path in pending:
                safe_path(path, allowed)
                if digest(path) != previous['retired'][str(path)]['sha256']:
                    raise RuntimeError('Pending retirement changed: ' + str(path))
            if apply:
                for path in pending: path.unlink()
            if not previous.get('retained') or previous.get('validator_version') == VALIDATOR_VERSION:
                return {'directory': str(directory), 'status': 'already_compacted', 'pending_retirements': len(pending)}
    source = canonical if canonical.is_file() else directory / 'visual-preview.blend'
    if not source.is_file():
        return {'directory': str(directory), 'status': 'retained_backup_only', 'files': [str(p) for p in files]}
    before = inventory(directory, allowed, hashes=apply)
    baseline = inventory(directory, allowed)
    if {k: {x:v for x,v in s.items() if x != 'sha256'} for k,s in before.items()} != baseline:
        raise RuntimeError('Inventory changed during hashing: ' + str(directory))
    plan = {'directory': str(directory), 'status': 'dry_run', 'source': str(source),
            'before_bytes': sum(v['bytes'] for v in before.values()),
            'originals': {str(p): before[str(p.relative_to(directory))] for p in files}}
    if not apply: return plan
    required = max(p.stat().st_size for p in files) * 2 + 64 * 1024 * 1024
    if shutil.disk_usage(directory).free < required:
        raise RuntimeError('Insufficient temporary disk space for case: ' + str(directory))
    evidence.mkdir(parents=True, exist_ok=True)
    candidate = directory / ('.compact-' + uuid.uuid4().hex + '.blend')
    job_path = evidence / 'job.json'
    job = {'directory': str(directory), 'source': str(source), 'originals': [str(p) for p in files],
           'candidate': str(candidate), 'prepared': str(evidence/'prepared.json')}
    atomic_json(job_path, job)
    try:
        prepared = worker('prepare', job_path, evidence/'prepared.json', evidence/'prepare.log')
        verified = worker('verify', job_path, evidence/'verified.json', evidence/'verify.log')
        # Freshly recheck every original byte, not only sizes or filenames.
        now = inventory(directory, allowed, hashes=True)
        now.pop(candidate.name, None)
        if now != before:
            raise RuntimeError('Historical case changed during validation; all originals retained')
        original_scene_bytes = sum(p.stat().st_size for p in files)
        retired = {p: plan['originals'][p] for p in prepared['retire'] if p != str(canonical)}
        manifest = {'schema_version': 1, 'validator_version': VALIDATOR_VERSION, 'status': 'committed', 'source': str(source),
                    'originals': plan['originals'], 'retired': retired, 'retained': prepared['retained'],
                    'canonical_sha256': digest(candidate), 'canonical_bytes': candidate.stat().st_size,
                    'preserved_cameras': prepared['preserved_cameras'], 'verification': verified,
                    'evidence_directory': str(evidence), 'save': prepared['save']}
        if migration.is_file():
            manifest['previous_migration'] = json.loads(migration.read_text(encoding='utf-8'))
        # Commit canonical plus durable migration map before retiring other files.
        atomic_replace(candidate, canonical)
        atomic_json(migration, manifest)
        for path, record in retired.items():
            target = safe_path(path, allowed)
            if digest(target) != record['sha256']:
                raise RuntimeError('Retirement changed after commit; retained: ' + path)
            target.unlink()
        remaining = sum(p.stat().st_size for p in directory.iterdir() if p.suffix in ('.blend','.blend1'))
        manifest.update(status='complete', saved_bytes=original_scene_bytes-remaining)
        atomic_json(migration, manifest)
        return {'directory': str(directory), 'status': 'compacted', 'saved_bytes': manifest['saved_bytes'],
                'retired_files': len(retired), 'retained': prepared['retained'], 'verification': verified,
                'save': prepared['save'], 'source_load_seconds': prepared['originals'][str(source)]['load_seconds']}
    finally:
        # Only the candidate owned by this invocation is eligible for cleanup.
        candidate.unlink(missing_ok=True)


def main():
    if '--legacy-duplicates' not in sys.argv:
        from tools.storage_v2 import main as storage_main
        storage_main()
        return
    sys.argv.remove('--legacy-duplicates')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--stage', choices=STAGES, action='append')
    parser.add_argument('--case', help='Exact stage-relative case directory, e.g. demo/look-left')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--jobs', type=int, choices=(1,2), default=1,
                        help='Independent cases in flight; each still gets a fresh verification process')
    args = parser.parse_args()
    roots = [ROOT/'artifacts/stages'/s for s in (args.stage or STAGES)]
    active = active_blender_processes()
    if active: raise RuntimeError('Historical compaction blocked by active Blender process(es): ' + active)
    report = {'apply': args.apply, 'started': time.time(), 'cases': []}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    run_root=EVIDENCE/'runs'/(str(time.time_ns())+'-'+uuid.uuid4().hex[:8])
    run_root.mkdir(parents=True)
    latest=EVIDENCE/('apply-report.json' if args.apply else 'dry-run.json')
    if latest.is_file(): shutil.copy2(latest,run_root/'previous-report.json')
    report['run_directory']=str(run_root)
    with ExitStack() as stack:
        for root in roots:
            safe_path(root, roots)
            stack.enter_context(producer_lease(root))
        baseline = {str(root): inventory(root, roots) for root in roots}
        # Check a second inventory after the first complete traversal.
        if baseline != {str(root): inventory(root, roots) for root in roots}:
            raise RuntimeError('Stage inventory is changing; compaction postponed')
        directories = sorted({p.parent for root in roots for p in root.rglob('*.blend*')})
        selected=[]
        for directory in directories:
            stage = next(root for root in roots if directory.is_relative_to(root))
            relative = directory.relative_to(stage)
            if args.case and str(relative).replace('\\','/') != args.case: continue
            if args.limit is not None and len(selected) >= args.limit: break
            selected.append((directory,stage,relative))
        def run(item):
            directory,stage,relative=item
            label = stage.name + '/' + str(relative).replace('\\','/')
            try:
                value = compact_case(directory, roots, run_root/stage.name/relative, apply=args.apply)
            except Exception as exc:
                value = {'directory': str(directory), 'status': 'retained_validation_failed', 'error': str(exc)}
            return label,value
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for future in as_completed([pool.submit(run,item) for item in selected]):
                label,value=future.result()
                report['cases'].append(value)
                atomic_json(EVIDENCE/('apply-report.json' if args.apply else 'dry-run.json'), report)
                atomic_json(run_root/'report.json',report)
                print(label, value['status'], value.get('saved_bytes', value.get('error', '')), flush=True)
    report['finished'] = time.time()
    report['saved_bytes'] = sum(v.get('saved_bytes',0) for v in report['cases'])
    atomic_json(EVIDENCE/('apply-report.json' if args.apply else 'dry-run.json'), report)
    atomic_json(run_root/'report.json',report)
    print('COMPACTION_BYTES_SAVED', report['saved_bytes'], flush=True)


if __name__ == '__main__': main()
