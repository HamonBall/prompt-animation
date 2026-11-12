"""Rebuild a coordinated case and prove whether its reviewed media still applies."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import value_error
from tools import artifact_store as store
from tools import coordinated_boundary_evidence as boundary
from tools.artifact_bundle import validate_manifest
from tools.coordinated_evidence import CASES, FRAMING, HARNESS, OUT, VIEWS
from tools.root_motion_evidence import check_process, read, runtime
from tools.storage_policy import confined, enforce


def resolve_case(key, group='baseline'):
    """Resolve against the selected registry before any native work or writes."""
    if group not in ('baseline', 'boundary'):
        raise ValueError(f'Unknown coordinated revalidation group: {group}')
    cases = CASES if group == 'baseline' else boundary.boundary_cases()
    if key not in cases:
        raise ValueError(f'Unknown coordinated movement case in {group}: {key}')
    return confined(OUT / key, OUT), cases[key]


def revalidate(key, group='baseline'):
    out, spec = resolve_case(key, group)
    from blender_coordinated_evidence import build_action, check_takeoff, compile_support, make_entry
    from blender_support_revalidate_initial import frame_state
    from tools.blender_artifact_worker import signature

    rig = out.parent.name
    manifest, _, baked = validate_manifest(out)
    old = read(out / 'result.json')
    stamp = old['stage_05_6c']
    inputs = store.input_identity(out)
    assert stamp['key'] == key and stamp['spec'] == spec
    assert stamp['producer'] == manifest['inputs']['producer_sha256']
    assert {k: v for k, v in inputs.items() if k != 'producer_sha256'} == {
        k: v for k, v in manifest['inputs'].items() if k != 'producer_sha256'}
    source = read(out / 'source.json')
    if rig == 'demo':
        assert source == {'kind': 'procedural-demo-v1'}
    else:
        assert source['kind'] == 'imported' and source['sha256'] == store.digest(ROOT / 'Hip Hop Mixamo.fbx')
    check_process(out, 'numeric', 'COORDINATED_NUMERIC_PASSED')
    check_process(out, 'render', 'COORDINATED_RENDER_PASSED')
    assert old['review']['passed'] and not old['experimental']
    assert manifest['complete'] and set(manifest['views']) == set(VIEWS) and store.files_complete(out, manifest)
    review = read(OUT / 'visual-review.json')[key]
    playback = read(out / 'playback.json')
    assert review['motion'] == playback['motion_sha256'] == store.digest(baked)
    assert playback['passed'] and playback['runtime'] == runtime()
    assert playback['result_sha256'] == store.digest(out / 'result.json')
    assert playback['framing_sha256'] == store.digest(FRAMING)
    assert set(review['views']) == set(review['observations']) == set(VIEWS)
    for label in VIEWS:
        assert review['observations'][label].strip()
        assert review['views'][label] == [manifest['views'][label]['media']['sha256'],
                                          store.digest(out / (label + '-sheet.png'))]

    harness = HARNESS if group == 'baseline' else (*HARNESS, boundary.SCRIPT.relative_to(ROOT).as_posix())
    dependencies = {name: store.digest(ROOT / name)
                    for name in (*harness, 'tests/blender_support_revalidate_initial.py')}
    handle, profile, entry, params = make_entry(rig, spec)
    assert params == stamp['parameters'] == manifest['entry']['movement_parameters']
    motion = compile_support(profile, entry, spec['move'], params, handle.surfaces)
    result = build_action(handle, motion, profile=profile)
    assert result['review']['passed'] and not result['experimental']
    if spec['move'] == 'body.takeoff_land':
        takeoff_review = check_takeoff if group == 'baseline' else boundary.verify_takeoff
        takeoff_review(motion, result['samples'])
        assert result['review']['metrics']['contact_error_m'] < .001
    frames = manifest['expected_frames']
    assert len(frames) == result['frames'] == old['frames'] == playback['frames'] <= spec['max_frames']
    for previous, current in zip(old['samples'], result['samples'], strict=True):
        for name in ('active_foot_anchors', 'active_support_anchors'):
            assert previous.get(name) == json.loads(json.dumps(current.get(name))), (key, current['frame'], name)
    handle.scene.frame_set(frames[0])
    assert signature()['asset_exact'] == manifest['asset']['content_hash']
    fresh = list(frame_state(handle, frames))
    saved = store.open_preview(out)
    assert (saved.scene.frame_start, saved.scene.frame_end) == (frames[0], frames[-1])
    assert (saved.scene.render.fps, saved.scene.render.fps_base) == (motion.fps, 1)
    maxima = {'position_m': 0., 'angle_deg': 0., 'scale': 0.}
    for left, right in zip(frame_state(saved, frames), fresh, strict=True):
        assert left.keys() == right.keys()
        for name in right:
            for index, (metric, shape) in enumerate((('position_m', 'vector'), ('angle_deg', 'quaternion'),
                                                    ('scale', 'vector'))):
                maxima[metric] = max(maxima[metric], value_error(left[name][index], right[name][index], shape))
    assert maxima['position_m'] < 1e-5 and maxima['angle_deg'] < .001 and maxima['scale'] < 1e-6, maxima
    assert inputs == store.input_identity(out)
    assert all(store.digest(ROOT / name) == digest for name, digest in dependencies.items())
    folder = OUT / 'current-equivalence'
    enforce(folder, growth=128 * 1024)
    with store.producer_lease(folder):
        store.atomic_json(folder / (key.replace('/', '.') + '.json'), {
            'case': key, 'passed': True, 'frames': len(frames), 'maxima': maxima,
            'current_review': result['review'], 'current_executable': c.to_dict(motion),
            'manifest_sha256': store.digest(out / 'preview-manifest.json'),
            'motion_sha256': review['motion'], 'views': review['views'], 'current_inputs': inputs,
            'runtime': runtime(), 'dependencies': dependencies, 'validator_sha256': store.digest(Path(__file__)),
        })
    print('COORDINATED_EQUIVALENT', key, maxima, flush=True)


if __name__ == '__main__':
    revalidate(*sys.argv[sys.argv.index('--') + 1:])
