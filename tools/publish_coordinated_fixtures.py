"""Publish profile-8 coordinated fixtures after current and visual evidence passes."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]

from avatar_app.motion import Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment, instantiate_movement, prepare_fragment
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.registry import parameter_schema
from tools import coordinated_boundary_evidence as boundary
from tools import coordinated_knee_crawl_evidence as knee
from tools import coordinated_evidence as evidence
from tools.artifact_bundle import validate_manifest
from tools.artifact_store import atomic_json, digest, files_complete, input_identity, producer_lease
from tools.storage_policy import MiB, enforce

FIXTURES = ROOT / 'tests/fixtures/coordinated_body_moves/v1'
EQUIVALENCE = ROOT / 'tests/blender_coordinated_revalidate.py'


def verify_equivalence(key, reviewed):
    out = evidence.case_path(key)
    manifest, _, motion = validate_manifest(out)
    proof = evidence.read(evidence.OUT / 'current-equivalence' / (key.replace('/', '.') + '.json'))
    assert proof['case'] == key and proof['passed'] and proof['current_review']['passed']
    assert proof['current_inputs'] == input_identity(out) and proof['runtime'] == evidence.runtime()
    assert proof['validator_sha256'] == digest(EQUIVALENCE)
    dependencies = {*evidence.HARNESS, 'tests/blender_support_revalidate_initial.py'}
    assert proof['dependencies'] == {name: digest(ROOT / name) for name in dependencies}
    assert proof['manifest_sha256'] == digest(out / 'preview-manifest.json')
    assert proof['frames'] == len(manifest['expected_frames'])
    assert proof['motion_sha256'] == reviewed['motion'] == digest(motion)
    assert manifest['complete'] and files_complete(out, manifest)
    assert proof['views'] == reviewed['views'] == {
        view: [manifest['views'][view]['media']['sha256'], digest(out / (view + '-sheet.png'))]
        for view in evidence.VIEWS
    }
    return proof['current_executable']


def verify_direct(key, reviewed):
    identity = evidence.review_identity(key)
    assert reviewed['motion'] == identity['motion']
    assert reviewed['views'] == {view: list(values) for view, values in identity['views'].items()}
    return evidence.read(evidence.case_path(key) / 'executable.json')


def add_examples(keys, reviews, manifest, payloads, *, equivalence=False, records=False):
    for key in keys:
        reviewed = reviews[key]
        assert set(reviewed['observations']) == set(evidence.VIEWS)
        assert all(note.strip() for note in reviewed['observations'].values())
        out = evidence.case_path(key)
        expected = verify_equivalence(key, reviewed) if equivalence else verify_direct(key, reviewed)
        result = evidence.read(out / 'result.json')
        stamp = result['stage_05_6c']
        profile = c.from_dict(c.AvatarProfile, evidence.read(out / 'profile.json'))
        entry = c.from_dict(c.MotionStateSnapshot, evidence.read(out / 'entry.json'))
        move = evidence.CASES[key]['move']
        catalog = catalog_for_profile(profile)
        surfaces = tuple(Surface(row['name'], row['height'], tuple(row['center']) if row['center'] else None,
                                 tuple(row['size']) if row['size'] else None) for row in stamp['surfaces'])
        instance = instantiate_movement(move, stamp['parameters'], instance_id='support.test', profile=profile,
                                        entry_state=entry, catalog=catalog)
        fragment = build_fragment(instance, entry, profile, surfaces, catalog)
        executable = prepare_fragment(fragment, entry, profile)
        assert executable == c.from_dict(c.ExecutableMotion, expected), key
        directory = FIXTURES / key.removesuffix('-revised')
        data = {
            'profile': c.to_dict(profile), 'entry': c.to_dict(entry), 'instance': c.to_dict(instance),
            'fragment': c.to_dict(fragment), 'executable': c.to_dict(executable),
            'surfaces': stamp['surfaces'], 'schema': parameter_schema(catalog.definitions[move]),
        }
        files = {field: directory / f'{field}.json' for field in data}
        if records:
            payloads.update((files[field], value) for field, value in data.items())
        manifest[key] = {
            'movement': move, 'parameters': stamp['parameters'], 'entry_pose': stamp['spec']['pose'],
            'frames': result['frames'], 'motion_sha256': reviewed['motion'], 'views': reviewed['views'],
            'visual_reuse': equivalence,
            **({'records': {field: path.relative_to(FIXTURES).as_posix() for field, path in files.items()}}
               if records else {}),
        }


def main():
    reviews = evidence.read(evidence.OUT / 'visual-review.json')
    baselines = {key: spec for key, spec in evidence.CASES.items() if spec['move'] != 'body.crawl'}
    boundaries = {key: spec for key, spec in boundary.boundary_cases().items() if spec['move'] != 'body.crawl'}
    feet = boundary.current_feet_crawl_cases()
    feet_baselines = [key for key in feet if key.removesuffix('-revised') in evidence.CASES]
    expected = {*baselines, *boundaries, *feet, *knee.CASES}
    assert expected <= reviews.keys(), f'Missing visual approvals: {sorted(expected - reviews.keys())}'
    cases, payloads = {}, {}
    add_examples(baselines, reviews, cases, payloads, equivalence=True, records=True)
    baseline_harness = evidence.HARNESS
    evidence.CASES.update(boundaries)
    evidence.HARNESS = (*baseline_harness, boundary.SCRIPT.relative_to(ROOT).as_posix())
    add_examples(boundaries, reviews, cases, payloads, equivalence=True)
    evidence.CASES.update(feet)
    evidence.NATIVE = boundary.SCRIPT
    evidence.HARNESS += ('tools/coordinated_crawl_limit_evidence.py',)
    add_examples(feet_baselines, reviews, cases, payloads, records=True)
    add_examples(feet.keys() - set(feet_baselines), reviews, cases, payloads)
    evidence.CASES.update(knee.CASES)
    evidence.NATIVE = knee.SCRIPT
    evidence.HARNESS = (*baseline_harness, 'tests/blender_knee_crawl.py', knee.SCRIPT.relative_to(ROOT).as_posix())
    add_examples(knee.CASES, reviews, cases, payloads, records=True)
    assert set(cases) == expected
    enforce(evidence.OUT, growth=MiB)
    with producer_lease(evidence.OUT):
        for path, data in payloads.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(path, data)
        atomic_json(FIXTURES / 'manifest.json', {
            'profile_version': 8, 'definition_version': 1, 'cases': cases,
        })
    print('PUBLISHED_COORDINATED_FIXTURES', sum('records' in row for row in cases.values()), len(cases), flush=True)


if __name__ == '__main__':
    main()
