"""Compare current sole and balance bakes with earlier reviewed saved actions."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT)]

from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import value_error
import blender_movement_support_transfers as native
from tools import artifact_store as store
from tools.artifact_bundle import validate_manifest
from tools.blender_artifact_worker import signature
from tools.root_motion_evidence import check_process, runtime
from tools.storage_policy import enforce
from tools.support_evidence import KEYS, OUT, VIEWS, case_path, read


def frame_state(handle, frames):
    """World transform of each deforming bone and every mesh in the scene."""
    rig = handle.rig
    for frame in frames:
        handle.scene.frame_set(frame)
        transforms = {'armature': rig.matrix_world.copy()}
        transforms.update((f'bone:{bone.name}', rig.matrix_world @ bone.matrix) for bone in rig.pose.bones)
        transforms.update((f'mesh:{obj.name}', obj.matrix_world.copy())
                          for obj in handle.scene.objects if obj.type == 'MESH')
        yield {name: (tuple(matrix.translation), tuple(matrix.to_quaternion().normalized()),
                      tuple(matrix.to_scale())) for name, matrix in transforms.items()}


def compare(rig, case, handle, profile, motion, result, params):
    key = rig + '/' + case
    out = case_path(key)
    manifest, _, baked = validate_manifest(out)
    old = read(out / 'result.json')
    stamp = old['stage_05_6b']
    current_inputs = store.input_identity(out)
    assert stamp['producer'] == manifest['inputs']['producer_sha256']
    assert {k: v for k, v in current_inputs.items() if k != 'producer_sha256'} == {
        k: v for k, v in manifest['inputs'].items() if k != 'producer_sha256'}
    assert stamp['parameters'] == params == manifest['entry']['movement_parameters']
    source = read(out / 'source.json')
    if rig == 'demo':
        assert source == {'kind': 'procedural-demo-v1'}
    else:
        assert source['kind'] == 'imported' and source['sha256'] == store.digest(ROOT / 'Hip Hop Mixamo.fbx')
    check_process(out, 'numeric', 'SUPPORT_NUMERIC_PASSED')
    check_process(out, 'render', 'SUPPORT_RENDER_PASSED')
    assert old['review']['passed'] and result['review']['passed']
    assert manifest['complete'] and set(manifest['views']) == set(VIEWS) and store.files_complete(out, manifest)
    review = read(OUT / 'visual-review.json')[key]
    assert all(review['observations'][label].strip() for label in VIEWS)
    assert review['motion'] == store.digest(baked)
    for label, hashes in review['views'].items():
        assert hashes == [manifest['views'][label]['media']['sha256'], store.digest(out / (label + '-sheet.png'))]
    assert c.from_dict(c.AvatarProfile, read(out / 'profile.json')) == profile
    assert c.from_dict(c.ExecutableMotion, read(out / 'executable.json')) == motion
    frames = manifest['expected_frames']
    assert len(frames) == result['frames'] == old['frames']
    fresh_contacts = [{name: list(position) for name, position in row['active_foot_anchors'].items()}
                      for row in result['samples']]
    assert fresh_contacts == [row['active_foot_anchors'] for row in old['samples']]
    handle.scene.frame_set(1)
    assert signature()['asset_exact'] == manifest['asset']['content_hash']
    current = list(frame_state(handle, frames))
    reopened = store.open_preview(out)
    assert (reopened.scene.frame_start, reopened.scene.frame_end) == (frames[0], frames[-1])
    assert (reopened.scene.render.fps, reopened.scene.render.fps_base) == (motion.fps, 1)
    maxima = {'position_m': 0., 'angle_deg': 0., 'scale': 0.}
    for saved, fresh in zip(frame_state(reopened, frames), current, strict=True):
        assert saved.keys() == fresh.keys()
        for name, values in fresh.items():
            position, angle, scale = (value_error(saved[name][0], values[0]),
                                      value_error(saved[name][1], values[1], 'quaternion'),
                                      value_error(saved[name][2], values[2]))
            maxima['position_m'] = max(maxima['position_m'], position)
            maxima['angle_deg'] = max(maxima['angle_deg'], angle)
            maxima['scale'] = max(maxima['scale'], scale)
    assert maxima['position_m'] < 1e-5 and maxima['angle_deg'] < .001 and maxima['scale'] < 1e-6, maxima
    report = {
        'case': key, 'passed': True, 'frames': len(frames), 'maxima': maxima,
        'current_review': result['review'], 'saved_motion_sha256': review['motion'], 'views': review['views'],
        'manifest_sha256': store.digest(out / 'preview-manifest.json'),
        'current_producer_sha256': current_inputs['producer_sha256'], 'runtime': runtime(),
        'harness_sha256': store.digest(Path(native.__file__)), 'validator_sha256': store.digest(Path(__file__)),
    }
    folder = OUT / 'initial-equivalence'
    enforce(folder, growth=8192)
    with store.producer_lease(folder):
        store.atomic_json(folder / f'{rig}.{case}.json', report)
    print('SUPPORT_INITIAL_EQUIVALENT', key, maxima, flush=True)


if __name__ == '__main__':
    key, = sys.argv[sys.argv.index('--') + 1:]
    assert key in KEYS
    rig, case = key.split('/')
    native.save_case = compare
    if case.startswith('balance-'):
        native.balance(rig, case.split('-')[1], save=True)
    else:
        native.main(rig, save=True, cycle=case == 'sole-cycle')
