"""Publish Stage 05.5 fixtures from current numeric and visually reviewed evidence."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.feet import IDS
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.registry import parameter_schema
from ankles_feet_toes_cases import cases
from tools.ankles_feet_evidence import OUT, case_path, read, render_valid, review_identity
from tools.artifact_store import atomic_json


def main():
    rows = list(cases())
    reviews = read(OUT / 'visual-review.json')['cases']
    expected = {f'{rig}/{name}' for rig in ('demo', 'mixamo') for name, movement, *_ in rows
                if (rig, movement) != ('demo', 'toes.curl')}
    assert len(expected) == 123 and set(reviews) == expected
    summaries = {}
    for rig in ('demo', 'mixamo'):
        for name, movement, *_ in rows:
            key = f'{rig}/{name}'
            if key not in expected:
                continue
            out = case_path(rig, name)
            review = reviews[key]
            identity = review_identity(out)
            assert render_valid(out), key
            assert review['actually_inspected'] and review['observation'].strip(), key
            assert all(review[field] == value for field, value in identity.items()), key
            playback = read(out / 'saved-playback-review.json')
            summaries[key] = {'movement': movement, 'frames': identity['frames_per_view'],
                              'motion_sha256': identity['motion_sha256'], 'maxima': playback['maxima']}
    summary = {'cases': summaries, 'samples': sum(row['frames'] for row in summaries.values())}
    assert summary['samples'] == 13227
    summary_path = OUT / 'publication-summary.json'
    atomic_json(summary_path, summary)

    fixtures = ROOT / 'tests/fixtures/ankles_feet_toes/v1'
    manifest = {'profile_version': 8, 'definition_version': 1, 'rigs': {}}
    for rig in ('demo', 'mixamo'):
        profile = c.loads(c.AvatarProfile,
                          (case_path(rig, 'ankle.flex.default.left') / 'profile.json').read_text())
        catalog = catalog_for_profile(profile)
        base = fixtures / rig
        base.mkdir(parents=True, exist_ok=True)
        atomic_json(base / 'profile.json', c.to_dict(profile))
        records = []
        manifest['rigs'][rig] = {}
        for movement in IDS:
            status = 'reviewed_for_envelope'
            examples = {}
            measurements = {}
            if (rig, movement) == ('demo', 'toes.curl'):
                status = 'unavailable_on_rig'
                assert movement not in catalog.definitions
                envelope = ()
            else:
                envelope = catalog.definitions[movement].parameter_specs
                case = case_path(rig, movement + '.default.left')
                assert f'{rig}/{case.name}' in expected
                for field in ('entry', 'instance', 'fragment', 'executable'):
                    target = base / f'{movement}-{field}.json'
                    atomic_json(target, read(case / f'{field}.json'))
                    examples[field] = target.relative_to(fixtures).as_posix()
                for key, row in summaries.items():
                    if key.startswith(rig + '/') and row['movement'] == movement:
                        for metric, value in row['maxima'].items():
                            measurements[metric] = max(measurements.get(metric, value), value)
            record = c.VerificationRecord(
                movement, 1, profile.avatar_id, 8, envelope,
                ('artifacts/stages/05.5/publication-summary.json',
                 'artifacts/stages/05.5/visual-review.json',
                 'docs/contracts/ankles-feet-toes-v1.md',
                 'artifacts/maintenance/jobs/stage-05.5-raised-entry/report.json'),
                tuple(c.ParameterValue(metric, value) for metric, value in sorted(measurements.items())),
                status)
            if examples:
                catalog.register_review(record, profile)
            records.append(c.to_dict(record))
            manifest['rigs'][rig][movement] = {'status': status, 'records': examples}
        atomic_json(base / 'reviews.json', records)
        atomic_json(base / 'schemas.json', {movement: parameter_schema(catalog.definitions[movement])
                                           for movement in IDS if movement in catalog.definitions})
    atomic_json(fixtures / 'manifest.json', manifest)
    print('PUBLISHED_ANKLES_FEET_FIXTURES', len(IDS), len(manifest['rigs']), flush=True)


if __name__ == '__main__':
    main()
