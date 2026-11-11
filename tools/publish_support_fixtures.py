"""Publish Stage 05.6b fixtures after native, visual, and compatibility gates."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]

from avatar_app.motion import Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment, instantiate_movement, prepare_fragment
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.registry import parameter_schema
from tools.artifact_bundle import validate_manifest
from tools.artifact_store import atomic_json, digest, files_complete, input_identity, producer_lease
from tools.storage_policy import ARTIFACTS, MiB, enforce
from tools.support_evidence import ADDITIONAL_KEYS, ENVELOPE_KEYS, KEYS, NATIVE, OUT, VIEWS, case_path, identity, read, runtime

JOBS = ARTIFACTS / 'maintenance/jobs'
FIXTURES = ROOT / 'tests/fixtures/support_transfers/v1'
EQUIVALENCE = ROOT / 'tests/blender_support_revalidate_initial.py'
EXAMPLES = {'support.acquire_release': 'back-cycle', 'support.transfer': 'knee-transfer', 'body.balance': 'balance-fast'}


def earlier_identity(out, key, reviewed):
    proof = read(OUT / 'initial-equivalence' / (key.replace('/', '.') + '.json'))
    manifest, _, motion = validate_manifest(out)
    assert proof['case'] == key and proof['passed'] and proof['current_review']['passed']
    assert proof['frames'] == len(manifest['expected_frames'])
    assert proof['current_producer_sha256'] == input_identity(out)['producer_sha256'] and proof['runtime'] == runtime()
    assert proof['harness_sha256'] == digest(ROOT / NATIVE) and proof['validator_sha256'] == digest(EQUIVALENCE)
    assert proof['manifest_sha256'] == digest(out / 'preview-manifest.json')
    assert proof['saved_motion_sha256'] == reviewed['motion'] == digest(motion)
    assert proof['views'] == reviewed['views']
    assert manifest['complete'] and files_complete(out, manifest)
    assert all(reviewed['views'][label] == [manifest['views'][label]['media']['sha256'],
                                          digest(out / (label + '-sheet.png'))] for label in VIEWS)
    return proof


def movement_id(case):
    if case.startswith('balance-'):
        return 'body.balance'
    if case.endswith('-transfer') or case in ('palm-left-fast', 'knee-right-slow'):
        return 'support.transfer'
    return 'support.acquire_release'


def example(out, move):
    result = read(out / 'result.json')
    stamp = result['stage_05_6b']
    profile = c.from_dict(c.AvatarProfile, read(out / 'profile.json'))
    entry = c.from_dict(c.MotionStateSnapshot, read(out / 'entry.json'))
    catalog = catalog_for_profile(profile)
    instance = instantiate_movement(move, stamp['parameters'], instance_id='support.test', profile=profile,
                                    entry_state=entry, catalog=catalog)
    surfaces = tuple(Surface(row['name'], row['height'], tuple(row['center']) if row['center'] else None,
                             tuple(row['size']) if row['size'] else None) for row in stamp['surfaces'])
    fragment = build_fragment(instance, entry, profile, surfaces, catalog)
    motion = prepare_fragment(fragment, entry, profile)
    assert motion == c.from_dict(c.ExecutableMotion, read(out / 'executable.json'))
    return profile, catalog, {'profile': profile, 'entry': entry, 'instance': instance,
                              'fragment': fragment, 'executable': motion}, stamp['surfaces']


def main():
    for job in ('regressions-resume', 'initial-equivalence', 'additional-render-batch', 'envelope-render-batch'):
        report = read(JOBS / f'stage-05.6b-{job}' / 'report.json')
        assert report['status'] == 'completed', (job, report['status'])
    keys = KEYS + ADDITIONAL_KEYS + ENVELOPE_KEYS
    reviews = read(OUT / 'visual-review.json')
    assert set(keys) == set(reviews)
    enforce(OUT, growth=4 * MiB)
    with producer_lease(OUT):
        cases = {}
        for key in keys:
            out = case_path(key)
            row = reviews[key]
            assert all(row['observations'][label].strip() for label in VIEWS)
            if key in KEYS:
                earlier_identity(out, key, row)
            else:
                current = identity(out)
                assert row['motion'] == current['motion']
                assert row['views'] == {label: list(values) for label, values in current['views'].items()}
            playback = read(out / 'support-playback.json')
            cases[key] = {'movement': movement_id(out.name), 'frames': playback['frames'],
                          'motion_sha256': row['motion'], 'views': row['views'], 'maxima': playback['maxima'],
                          'visual_reuse': key in KEYS}
        manifest = {'profile_version': 8, 'definition_version': 1, 'rigs': {}}
        payloads = {}
        for rig in ('demo', 'mixamo'):
            manifest['rigs'][rig] = {}
            for move, case in EXAMPLES.items():
                key = rig + '/' + case
                profile, catalog, records, surfaces = example(case_path(key), move)
                base = FIXTURES / rig
                files = {}
                for field, record in records.items():
                    path = base / f'{move}-{field}.json'
                    payloads[path] = c.to_dict(record)
                    files[field] = path.relative_to(FIXTURES).as_posix()
                surface_path = base / f'{move}-surfaces.json'
                payloads[surface_path] = surfaces
                files['surfaces'] = surface_path.relative_to(FIXTURES).as_posix()
                definition = catalog.definitions[move]
                maximum = {}
                for name, row in cases.items():
                    if name.startswith(rig + '/') and row['movement'] == move:
                        for metric, value in row['maxima'].items():
                            maximum[metric] = max(maximum.get(metric, value), value)
                review = c.VerificationRecord(
                    move, 1, profile.avatar_id, 8, definition.parameter_specs,
                    ('artifacts/stages/05.6b/publication-summary.json', 'artifacts/stages/05.6b/visual-review.json',
                     'docs/contracts/support-transfers-v1.md'),
                    tuple(c.ParameterValue(metric, value) for metric, value in sorted(maximum.items())),
                    'reviewed_for_envelope',
                )
                catalog.register_review(review, profile)
                for field, value in (('review', c.to_dict(review)), ('schema', parameter_schema(definition))):
                    path = base / f'{move}-{field}.json'
                    payloads[path] = value
                    files[field] = path.relative_to(FIXTURES).as_posix()
                manifest['rigs'][rig][move] = {'example_case': key, 'status': review.status, 'records': files}
        for path, data in payloads.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(path, data)
        atomic_json(FIXTURES / 'manifest.json', manifest)
        atomic_json(OUT / 'publication-summary.json', {'cases': cases, 'samples': sum(row['frames'] for row in cases.values())})
    print('PUBLISHED_SUPPORT_FIXTURES', len(keys), len(EXAMPLES) * len(manifest['rigs']), flush=True)


if __name__ == '__main__':
    main()
