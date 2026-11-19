"""Bounded diagnostic retirement and final Stage 05.7b storage accounting."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'tests')]
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.storage_policy import ARTIFACTS, LIMITS, confined, inventory, temporary_bytes

OUT = ARTIFACTS / 'stages/05.7b'
FIXTURES = ROOT / 'tests/fixtures/motion_styles/v1'
JOURNAL = OUT / 'diagnostic-retirement.json'


def read(path):
    import json
    return json.loads(path.read_text(encoding='utf-8'))


def retire():
    publication = read(FIXTURES / 'manifest.json')
    key = 'demo/fluid-visible-maximum'
    successor = confined(OUT / key, OUT)
    manifest, _, motion = validate_manifest(successor)
    assert manifest['complete'] and store.files_complete(successor, manifest)
    assert store.digest(motion) == publication['cases'][key]['motion']
    assert store.digest(motion) == read(OUT / 'visual-review.json')[key]['motion']
    original = confined(OUT / 'demo/fluid-maximum', OUT)
    if JOURNAL.exists():
        record = read(JOURNAL)
    else:
        note = read(ARTIFACTS / 'maintenance/stage-05.7b/low-amplitude-diagnostic.json')
        assert store.digest(original / 'preview-manifest.json') == note['manifest_sha256']
        validate_manifest(original)
        assert not any(lease['active'] for lease in inventory()['leases']
                       if Path(lease['path']).is_relative_to(original))
        files = {}
        for path in original.rglob('*'):
            if path.is_file():
                checked = confined(path, original)
                files[checked.relative_to(original).as_posix()] = {
                    'bytes': checked.stat().st_size, 'sha256': store.digest(checked)}
        record = dict(status='pending', reason='Superseded unapproved low-amplitude diagnostic',
                      successor=key, files=files)
        store.atomic_json(JOURNAL, record)
    for relative, expected in record['files'].items():
        path = confined(original / relative, original)
        if path.exists():
            assert path.stat().st_size == expected['bytes'] and store.digest(path) == expected['sha256']
            path.unlink()
    if original.exists():
        for directory in sorted(original.rglob('*'), key=lambda path: len(path.parts), reverse=True):
            if directory.is_dir():
                confined(directory, original).rmdir()
        original.rmdir()
    record.update(status='complete', retired_bytes=sum(item['bytes'] for item in record['files'].values()))
    store.atomic_json(JOURNAL, record)
    print('STYLE_DIAGNOSTIC_RETIRED', record['retired_bytes'], flush=True)


def account():
    audit_path = ARTIFACTS / 'maintenance/storage-v2/budget-check.json'
    audit = read(audit_path)
    assert not audit['errors']
    assert audit_path.stat().st_mtime_ns >= max(JOURNAL.stat().st_mtime_ns,
        (FIXTURES / 'manifest.json').stat().st_mtime_ns)
    assert read(JOURNAL)['status'] == 'complete'
    publication = read(FIXTURES / 'manifest.json')
    assert len(publication['cases']) == 32 and temporary_bytes(ARTIFACTS) == 0
    fixture_bytes = sum(path.stat().st_size for path in FIXTURES.rglob('*.json'))
    cache_bytes = sum(path.stat().st_size for folder in ('src', 'tests', 'tools')
                      for path in (ROOT / folder).rglob('*.pyc'))
    largest = max(path.stat().st_size + (path.parent / 'motion.blend').stat().st_size
                  for path in OUT.rglob('preview-manifest.json'))
    assert largest <= LIMITS['case']
    assert all(path.name == 'motion.blend' for path in OUT.rglob('*.blend'))
    assert not list(OUT.rglob('*.blend1'))
    baseline = read(ARTIFACTS / 'stages/05.7a/completion-accounting.json')['after']
    record = dict(stage='05.7b', cases=32, validated_bundles=audit['validated_bundles'],
        motion_samples=sum(case['frames'] for case in publication['cases'].values()),
        max_case_motion_manifest_bytes=largest, initial_retained_bytes=3866827293,
        baseline_by_class=baseline['by_class'], final_temporary_bytes=0,
        temporary_peak='unavailable', temporary_reservation_bytes=140607488,
        retired_diagnostic_bytes=read(JOURNAL)['retired_bytes'],
        outside_artifacts=dict(published_fixtures=fixture_bytes, workspace_caches=cache_bytes))
    for attempt in range(4):
        current = inventory()
        record['after'] = {key: value for key, value in current.items() if key != 'files'}
        record['shared_asset_additions_bytes'] = current['by_stage']['assets']['bytes'] - baseline['by_stage']['assets']['bytes']
        record['conservative_global_bytes'] = current['bytes'] + fixture_bytes + cache_bytes
        record['conservative_stage_bytes'] = current['by_stage']['05.7b']['bytes'] + fixture_bytes
        assert record['conservative_global_bytes'] <= LIMITS['global']
        assert record['conservative_stage_bytes'] <= LIMITS['stage']
        store.atomic_json(OUT / 'completion-accounting.json', record)
        if inventory()['bytes'] == current['bytes']:
            print('STYLE_STORAGE_PASSED', record['conservative_global_bytes'], flush=True)
            return
    raise RuntimeError('Style accounting did not stabilize')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('retire', 'account'))
    {'retire': retire, 'account': account}[parser.parse_args().operation]()
