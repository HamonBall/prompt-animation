"""Retire replaced 05.7a bakes and account after the strict storage-v2 audit."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.artifact_bundle import validate_manifest
from tools.artifact_store import atomic_json, digest, files_complete, producer_lease
from tools.root_motion_evidence import read
from tools.storage_policy import ARTIFACTS, LIMITS, confined, inventory, temporary_bytes

OUT = ARTIFACTS / 'stages/05.7a'
FIXTURES = ROOT / 'tests/fixtures/timing_patterns/v1'
RETIREMENT = OUT / 'completion-retirement.json'


def retire_replaced():
    """Retire only raw files from unreviewed bakes with published successors."""
    previous = read(OUT / 'floor-fix-predecessor-journal.json')['cases']
    candidates = {key: previous[key] for key in (
        'demo/range-steps-max', 'demo/range-strokes-alternating-max',
        'mixamo/range-strokes-alternating-max',
    )}
    candidates['demo/range-undulation-follow-through-current'] = read(
        OUT / 'follow-through-exit-marker-failure.json')
    publications = read(FIXTURES / 'manifest.json')['cases']
    reviews = read(OUT / 'visual-review.json')
    files = {}
    for key, archive in candidates.items():
        replacement = confined(OUT / key, OUT)
        manifest, _, motion = validate_manifest(replacement)
        expected_key = key.replace('/range-undulation-follow-through-current', '/undulation-follow-through')
        assert manifest['complete'] and files_complete(replacement, manifest)
        assert publications[expected_key]['motion'] == reviews[key]['motion'] == digest(motion)
        path = confined(OUT / archive['archive'], OUT)
        assert path.parent == replacement.parent and path != replacement
        for name, entry in archive['files'].items():
            if name not in ('numeric-process.json', 'numeric.log.gz'):
                file = confined(path / name, path)
                files[file.relative_to(OUT).as_posix()] = entry
    with producer_lease(OUT):
        record = read(RETIREMENT) if RETIREMENT.exists() else None
        if record is not None:
            assert record['files'] == files
        for name, entry in files.items():
            path = confined(OUT / name, OUT)
            if record is None or path.exists():
                assert path.stat().st_size == entry['bytes'] and digest(path) == entry['sha256'], path
        if record is None:
            atomic_json(RETIREMENT, {'files': files, 'status': 'pending'})
        for name in files:
            confined(OUT / name, OUT).unlink(missing_ok=True)
        total = sum(entry['bytes'] for entry in files.values())
        atomic_json(RETIREMENT, {'files': files, 'status': 'complete', 'retired_bytes': total})
    print('TIMING_REPLACED_BAKES_RETIRED', len(files), total, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retire-replaced', action='store_true')
    if parser.parse_args().retire_replaced:
        retire_replaced()
        return
    audit_path = ARTIFACTS / 'maintenance/storage-v2/budget-check.json'
    fixture_path = FIXTURES / 'manifest.json'
    audit = read(audit_path)
    assert not audit['errors'] and audit['validated_bundles'] >= 1123
    assert audit_path.stat().st_mtime_ns >= fixture_path.stat().st_mtime_ns
    retirement = read(RETIREMENT)
    assert retirement['status'] == 'complete' and audit_path.stat().st_mtime_ns >= RETIREMENT.stat().st_mtime_ns
    previous = read(ARTIFACTS / 'stages/05.6c/completion-accounting.json')['after']
    initial = inventory()
    assert not initial['leases'] and temporary_bytes(ARTIFACTS) == 0
    cases = read(fixture_path)['cases']
    fixture_bytes = sum(path.stat().st_size for path in FIXTURES.rglob('*.json'))
    cache_bytes = sum(path.stat().st_size for folder in ('src', 'tests', 'tools')
                      for path in (ROOT / folder).rglob('*.pyc'))
    largest = max(path.stat().st_size + (path.parent / 'motion.blend').stat().st_size
                  for path in OUT.rglob('preview-manifest.json'))
    assert largest <= LIMITS['case']
    assert all(path.name == 'motion.blend' for path in OUT.rglob('*.blend'))
    assert not list(OUT.rglob('*.blend1'))
    assert not any(path.stem.isdecimal() for path in OUT.rglob('*.png'))
    monitor = ARTIFACTS / 'maintenance/stage-05.7a/range-completion/temporary-monitor.json'
    accounting = {
        'stage': '05.7a', 'verified_baseline': previous, 'initial_stage_bytes': 3614556346,
        'validated_bundles': audit['validated_bundles'], 'accepted_cases': len(cases),
        'motion_samples': sum(case['frames'] for case in cases.values()),
        'max_case_motion_manifest_bytes': largest, 'final_temporary_bytes': 0,
        'range_temporary_monitor': read(monitor) if monitor.exists() else None,
        'retired_diagnostic_bytes': read(OUT / 'demo/exit-diagnostic-journal.json')['retirement_bytes'],
        'retired_replaced_bake_bytes': retirement['retired_bytes'],
        'outside_artifact_root': {'published_fixtures': fixture_bytes, 'workspace_caches': cache_bytes},
        'retained_prior_arm_evidence': ['demo/undulation-follow-through', 'mixamo/undulation-follow-through'],
        'readme_sha256': digest(ROOT / 'README.md'),
    }
    target = confined(OUT / 'completion-accounting.json', OUT)
    for _ in range(4):
        snapshot = inventory()
        accounting['after'] = {field: value for field, value in snapshot.items() if field != 'files'}
        accounting['conservative_stage_bytes'] = snapshot['by_stage']['05.7a']['bytes'] + fixture_bytes + cache_bytes
        accounting['conservative_global_bytes'] = snapshot['bytes'] + fixture_bytes + cache_bytes
        accounting['shared_asset_additions_bytes'] = (snapshot['by_stage']['assets']['bytes']
                                                       - previous['by_stage']['assets']['bytes'])
        assert accounting['conservative_stage_bytes'] <= LIMITS['stage']
        assert accounting['conservative_global_bytes'] <= LIMITS['global']
        with producer_lease(OUT):
            atomic_json(target, accounting)
        if inventory()['bytes'] == snapshot['bytes']:
            break
    else:
        raise RuntimeError('Final timing accounting did not stabilize')
    print('TIMING_STORAGE_PASSED', accounting['accepted_cases'], accounting['conservative_stage_bytes'],
          accounting['conservative_global_bytes'], flush=True)


if __name__ == '__main__':
    main()
