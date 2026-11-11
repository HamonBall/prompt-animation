"""Finalize Stage 05.6b artifact accounting after the closure lease is released."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.artifact_store import atomic_json, digest
from tools.storage_policy import ARTIFACTS, LIMITS, confined, inventory, temporary_bytes
from tools.support_evidence import OUT, case_path, read


def main():
    maintenance = ARTIFACTS / 'maintenance'
    closure = read(maintenance / 'jobs/stage-05.6b-closure/report.json')
    assert closure['status'] == 'completed'
    budget = read(maintenance / 'storage-v2/budget-check.json')
    assert not budget['errors'] and budget['validated_bundles'] >= 1063
    before = read(ARTIFACTS / 'stages/05.6a/completion-accounting.json')['after']
    predecessor = read(ARTIFACTS / 'stages/05.5/storage-before.json')['files']
    refreshes = {'maintenance/storage-v2/budget-check.json', 'maintenance/storage-v2/current-inventory.json'}
    current = inventory()
    assert not current['leases'] and temporary_bytes(ARTIFACTS) == 0
    for name, row in predecessor.items():
        if name not in refreshes:
            found = current['files'][name]
            assert (found['bytes'], found['mtime_ns']) == (row['bytes'], row['mtime_ns']), name
    for scratch in OUT.rglob('.scratch'):
        safe = confined(scratch, OUT)
        assert not any(safe.iterdir()), safe
        safe.rmdir()
    publication = read(OUT / 'publication-summary.json')
    largest = 0
    for key in publication['cases']:
        out = case_path(key)
        path = out / 'preview-manifest.json'
        manifest = read(path)
        assert {item.name for item in out.glob('*.mkv')} == {view['media']['path'] for view in manifest['views'].values()}
        largest = max(largest, path.stat().st_size + (out / 'motion.blend').stat().st_size)
    assert largest <= LIMITS['case']
    assert all(item.name == 'motion.blend' for item in OUT.rglob('*.blend'))
    assert not list(OUT.rglob('*.blend1')) and not any(item.stem.isdecimal() for item in OUT.rglob('*.png'))
    fixtures = ROOT / 'tests/fixtures/support_transfers/v1'
    assert (fixtures / 'manifest.json').is_file()
    fixture_bytes = sum(item.stat().st_size for item in fixtures.rglob('*') if item.is_file())
    caches = sum(item.stat().st_size for folder in ('src', 'tests', 'tools') for item in (ROOT / folder).rglob('*.pyc'))
    report = {
        'stage': '05.6b', 'storage_complete': True, 'before': before,
        'validated_bundles': budget['validated_bundles'], 'cases': len(publication['cases']),
        'samples': publication['samples'], 'view_frames': 2 * publication['samples'],
        'max_case_motion_manifest_bytes': largest, 'preserved_pre_05_5_paths': len(set(predecessor) - refreshes),
        'outside_artifact_root': {'fixtures': fixture_bytes, 'local_code_caches': caches},
        'peak_temporary_bytes': None, 'final_temporary_bytes': 0, 'readme_sha256': digest(ROOT / 'README.md'),
    }
    path = OUT / 'completion-accounting.json'
    for _ in range(4):
        current = inventory()
        report['after'] = {key: value for key, value in current.items() if key != 'files'}
        report['shared_asset_additions_bytes'] = current['by_stage']['assets']['bytes'] - before['by_stage']['assets']['bytes']
        report['conservative_stage_bytes'] = current['by_stage']['05.6b']['bytes'] + fixture_bytes + caches
        report['conservative_global_bytes'] = current['bytes'] + fixture_bytes + caches
        assert report['conservative_stage_bytes'] <= LIMITS['stage']
        assert report['conservative_global_bytes'] <= LIMITS['global']
        atomic_json(path, report)
        if inventory()['bytes'] == current['bytes']:
            break
    else:
        raise RuntimeError('Final accounting report size did not stabilize')
    print('SUPPORT_STORAGE_PASSED', report['conservative_stage_bytes'], report['conservative_global_bytes'], flush=True)


if __name__ == '__main__':
    main()
