"""Publish reviewed Stage 05.6a fixtures and reconcile final storage."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.registry import parameter_schema
from avatar_app.movement_library.root_motion import IDS
from tools.artifact_store import atomic_json, digest, producer_lease
from tools.root_motion_evidence import OUT, VIEWS, case_path, read, review_identity
from tools.storage_policy import ARTIFACTS, LIMITS, MiB, confined, enforce, inventory, temporary_bytes

FIXTURES = ROOT / 'tests/fixtures/root_travel_flight/v1'
MAINTENANCE = ARTIFACTS / 'maintenance'
JOBS = MAINTENANCE / 'jobs'
SUMMARY = OUT / 'publication-summary.json'
EXAMPLES = dict(zip(IDS, ('line', 'turn-left', 'pitch', 'hover')))
RECORDS = {'entry': c.MotionStateSnapshot, 'instance': c.MovementInstance,
           'fragment': c.MotionFragment, 'executable': c.ExecutableMotion}


def completed(*names):
    for name in names:
        report = read(JOBS / f'stage-05.6a-{name}' / 'report.json')
        assert report['status'] == 'completed', (name, report['status'])


def publish():
    completed('smoke-scale', 'matrix-numeric', 'render-pilot-resume', 'render-matrix', 'regressions')
    plan = read(MAINTENANCE / 'stage-05.6a/stage-05.6a-matrix-numeric/numeric.json')
    expected = {step['argv'][-1] for step in plan['steps'] if step['phase'] == 'numeric'}
    reviews = read(OUT / 'visual-review.json')['cases']
    assert set(reviews) == expected and len(expected) == 32
    enforce(OUT, growth=4 * MiB)
    with producer_lease(OUT):
        cases = {}
        for key in sorted(expected):
            out = case_path(key)
            identity = review_identity(out)
            review = reviews[key]
            assert review['actually_inspected'] and all(review['observations'][label].strip() for label in VIEWS)
            assert all(review[field] == value for field, value in identity.items()), key
            case = read(out / 'instance.json')
            cases[key] = {'movement': case['definition_id'], **identity,
                          'maxima': read(out / 'saved-playback-review.json')['maxima']}
        samples = sum(row['frames_per_view'] for row in cases.values())
        assert samples == 2240
        manifest = {'profile_version': 8, 'definition_version': 1, 'rigs': {}}
        payloads = {}
        for rig in ('demo', 'mixamo'):
            base = FIXTURES / rig
            rig_cases = {key: row for key, row in cases.items() if key.startswith(rig + '/')}
            assert len(rig_cases) == 16
            profile = c.from_dict(c.AvatarProfile, read(case_path(rig + '/line') / 'profile.json'))
            assert profile.version == 8
            catalog = catalog_for_profile(profile)
            payloads[base / 'profile.json'] = c.to_dict(profile)
            payloads[base / 'schemas.json'] = {move: parameter_schema(catalog.definitions[move]) for move in IDS}
            records = []
            manifest['rigs'][rig] = {}
            for move in IDS:
                key = rig + '/' + EXAMPLES[move]
                assert cases[key]['movement'] == move
                examples = {}
                for field, record_type in RECORDS.items():
                    value = c.from_dict(record_type, read(case_path(key) / f'{field}.json'))
                    target = base / f'{move}-{field}.json'
                    payloads[target] = c.to_dict(value)
                    examples[field] = target.relative_to(FIXTURES).as_posix()
                measurements = {}
                for row in rig_cases.values():
                    if row['movement'] == move:
                        for metric, value in row['maxima'].items():
                            measurements[metric] = max(measurements.get(metric, value), value)
                record = c.VerificationRecord(
                    move, 1, profile.avatar_id, 8, catalog.definitions[move].parameter_specs,
                    ('artifacts/stages/05.6a/publication-summary.json', 'artifacts/stages/05.6a/visual-review.json',
                     'docs/contracts/root-travel-flight-v1.md', 'artifacts/maintenance/jobs/stage-05.6a-smoke-scale/report.json'),
                    tuple(c.ParameterValue(metric, value) for metric, value in sorted(measurements.items())),
                    'reviewed_for_envelope',
                )
                catalog.register_review(record, profile)
                records.append(c.to_dict(record))
                manifest['rigs'][rig][move] = {'status': record.status, 'records': examples, 'example_case': key}
            payloads[base / 'reviews.json'] = records
        for path, payload in payloads.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(path, payload)
        atomic_json(FIXTURES / 'manifest.json', manifest)
        atomic_json(SUMMARY, {'cases': cases, 'samples': samples})
    print('PUBLISHED_ROOT_MOTION_FIXTURES', len(IDS), len(manifest['rigs']), flush=True)


def account():
    completed('closure')
    budget = read(MAINTENANCE / 'storage-v2/budget-check.json')
    assert not budget['errors'] and budget['validated_bundles'] >= 1021
    prior = ARTIFACTS / 'stages/05.5'
    before = read(prior / 'completion-accounting.json')['after']
    assert before['bytes'] == 3097982325
    current = inventory()
    assert not current['leases'] and temporary_bytes(ARTIFACTS) == 0
    predecessor = read(prior / 'storage-before.json')['files']
    refreshes = {'maintenance/storage-v2/budget-check.json', 'maintenance/storage-v2/current-inventory.json'}
    for name, old in predecessor.items():
        if name not in refreshes:
            new = current['files'][name]
            assert (new['bytes'], new['mtime_ns']) == (old['bytes'], old['mtime_ns']), name
    for scratch in list(OUT.rglob('.scratch')):
        safe = confined(scratch, OUT)
        assert not any(safe.iterdir()), safe
        safe.rmdir()
    publication = read(SUMMARY)
    largest = 0
    for key in publication['cases']:
        out = case_path(key)
        path = out / 'preview-manifest.json'
        manifest = read(path)
        assert {file.name for file in out.glob('*.mkv')} == {view['media']['path'] for view in manifest['views'].values()}
        largest = max(largest, path.stat().st_size + (out / 'motion.blend').stat().st_size)
    assert largest <= LIMITS['case']
    assert not list(OUT.rglob('*.blend1'))
    assert all(path.name == 'motion.blend' for path in OUT.rglob('*.blend'))
    assert not any(path.stem.isdecimal() for path in OUT.rglob('*.png'))
    assert (FIXTURES / 'manifest.json').is_file()
    fixtures = sum(path.stat().st_size for path in FIXTURES.rglob('*') if path.is_file())
    caches = sum(path.stat().st_size for folder in ('src', 'tests', 'tools') for path in (ROOT / folder).rglob('*.pyc'))
    report = {
        'stage': '05.6a', 'storage_complete': True, 'before': before, 'validated_bundles': budget['validated_bundles'],
        'cases': len(publication['cases']), 'motion_samples': publication['samples'],
        'view_frames': 2 * publication['samples'], 'movies': 2 * len(publication['cases']),
        'max_case_motion_manifest_bytes': largest, 'preserved_pre_05_5_paths': len(set(predecessor) - refreshes),
        'outside_artifact_root': {'fixtures': fixtures, 'local_code_caches': caches},
        'render_preflight_temporary_reservation_bytes': 155680768, 'peak_temporary_bytes': None,
        'final_temporary_bytes': 0, 'readme_sha256': digest(ROOT / 'README.md'),
    }
    target = OUT / 'completion-accounting.json'
    for _ in range(4):
        current = inventory()
        report['after'] = {key: value for key, value in current.items() if key != 'files'}
        report['shared_asset_additions_bytes'] = current['by_stage']['assets']['bytes'] - before['by_stage']['assets']['bytes']
        report['conservative_stage_bytes'] = current['by_stage']['05.6a']['bytes'] + fixtures + caches
        report['conservative_global_bytes'] = current['bytes'] + fixtures + caches
        assert report['conservative_stage_bytes'] <= LIMITS['stage']
        assert report['conservative_global_bytes'] <= LIMITS['global']
        atomic_json(target, report)
        if inventory()['bytes'] == current['bytes']:
            break
    else:
        raise RuntimeError('Final accounting report size did not stabilize')
    print('ROOT_MOTION_STORAGE_PASSED', report['conservative_stage_bytes'],
          report['conservative_global_bytes'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('publish', 'account'))
    args = parser.parse_args()
    (publish if args.operation == 'publish' else account)()
