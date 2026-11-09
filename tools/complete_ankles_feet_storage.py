"""Account for Stage 05.5 and verify preservation after the managed closure job."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.ankles_feet_evidence import OUT, read
from tools.artifact_store import atomic_json, digest
from tools.storage_policy import ARTIFACTS, LIMITS, confined, inventory, temporary_bytes


def main():
    maintenance = ARTIFACTS / 'maintenance'
    for batch in range(1, 17):
        report = read(maintenance / 'jobs' / f'stage-05.5-visual-{batch:02d}' / 'report.json')
        assert report['status'] == 'completed', (batch, report['status'])
    assert not read(maintenance / 'storage-v2/budget-check.json')['errors']
    before = read(OUT / 'storage-before.json')
    current = inventory()
    assert not current['leases'] and temporary_bytes(ARTIFACTS) == 0
    refreshes = {'maintenance/storage-v2/budget-check.json',
                 'maintenance/storage-v2/current-inventory.json'}
    for name, record in before['files'].items():
        if name not in refreshes:
            row = current['files'][name]
            assert (row['bytes'], row['mtime_ns']) == (record['bytes'], record['mtime_ns']), name
    for scratch in list(OUT.rglob('.scratch')):
        children = sorted(scratch.rglob('*'), key=lambda path: len(path.parts), reverse=True)
        assert all(child.is_dir() for child in children), scratch
        for child in children:
            confined(child, OUT).rmdir()
        confined(scratch, OUT).rmdir()

    publication = read(OUT / 'publication-summary.json')
    fixtures = ROOT / 'tests/fixtures/ankles_feet_toes/v1'
    assert (fixtures / 'manifest.json').is_file()
    fixture_bytes = sum(path.stat().st_size for path in fixtures.rglob('*') if path.is_file())
    cache_bytes = sum(path.stat().st_size for folder in ('src', 'tests', 'tools')
                      for path in (ROOT / folder).rglob('*.pyc'))
    max_case_bytes = 0
    for key in publication['cases']:
        directory = OUT / key
        manifest_path = directory / 'preview-manifest.json'
        manifest = read(manifest_path)
        expected_movies = {view['media']['path'] for view in manifest['views'].values()}
        assert len(expected_movies) == 2
        assert {path.name for path in directory.glob('*.mkv')} == expected_movies, key
        max_case_bytes = max(max_case_bytes, manifest_path.stat().st_size +
                             (directory / 'motion.blend').stat().st_size)
    assert max_case_bytes <= LIMITS['case']
    assert not list(OUT.rglob('*.blend1'))
    assert all(path.name == 'motion.blend' for path in OUT.rglob('*.blend'))
    assert not any(path.stem.isdecimal() for path in OUT.rglob('*.png'))
    target = OUT / 'completion-accounting.json'
    retired = read(maintenance / 'stage-05.5/visual-03/failed-render/retirement.json')
    assert retired['status'] == 'completed'
    report = {
        'stage': '05.5', 'storage_complete': True, 'limits': LIMITS,
        'before': {key: value for key, value in before.items() if key != 'files'},
        'preserved_predecessor_files': len(set(before['files']) - refreshes),
        'cases': len(publication['cases']), 'samples': publication['samples'],
        'movies': 2 * len(publication['cases']), 'view_frames': 2 * publication['samples'],
        'max_case_motion_manifest_bytes': max_case_bytes,
        'retired_bytes': retired['bytes_retired'], 'final_temporary_bytes': 0,
        'peak_temporary_bytes': None, 'render_preflight_temporary_reservation_bytes': 159129600,
        'outside_artifact_root': {'fixtures': fixture_bytes, 'local_code_caches': cache_bytes},
        'readme_sha256': digest(ROOT / 'README.md'),
    }
    for _ in range(4):
        current = inventory()
        report['after'] = {key: value for key, value in current.items() if key != 'files'}
        report['shared_asset_additions_bytes'] = (current['by_stage']['assets']['bytes'] -
                                                  before['by_stage']['assets']['bytes'])
        outside = fixture_bytes + cache_bytes
        report['conservative_stage_bytes'] = current['by_stage']['05.5']['bytes'] + outside
        report['conservative_global_bytes'] = current['bytes'] + outside
        assert report['conservative_stage_bytes'] <= LIMITS['stage']
        assert report['conservative_global_bytes'] <= LIMITS['global']
        atomic_json(target, report)
        if inventory()['bytes'] == current['bytes']:
            break
    else:
        raise RuntimeError('Accounting report size did not stabilize')
    print('ANKLES_FEET_STORAGE_PASSED', report['conservative_stage_bytes'],
          report['conservative_global_bytes'], flush=True)


if __name__ == '__main__':
    main()
