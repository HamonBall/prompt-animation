"""Check every frame of a saved root-motion bundle against authored targets."""
from pathlib import Path
import math

from tools.artifact_store import digest


def verify(handle, profile, directory, result):
    from avatar_app.blender import rig_profile as rp
    from avatar_app.blender.geometry import skin_bounds
    from avatar_app.blender.motion import capture_sample, review_samples
    from avatar_app.movement_library import contracts as c
    from avatar_app.movement_library.compiler import ExecutionCursor, sample_motion, value_error
    from avatar_app.movement_library.root_motion import ORIENTATION

    directory = Path(directory)
    baked = directory / 'motion.blend'
    baked_sha = digest(baked)
    motion = c.loads(c.ExecutableMotion, (directory / 'executable.json').read_text(encoding='utf-8'))
    scene = handle.scene
    assert (scene.frame_start, scene.frame_end) == (1, result['frames'])
    assert scene.frame_end == len(result['samples']) == math.ceil(motion.duration_s * motion.fps) + 1
    assert (scene.render.fps, scene.render.fps_base) == (motion.fps, 1)
    controls = {item.id: item for item in profile.controls}
    anchors = {item.anchor_id: item.position for item in motion.entry_snapshot.contact_anchors}
    samples = []
    bounds = []
    cursor = ExecutionCursor()
    measured = motion.entry_snapshot
    maxima = dict(playback_m=0., playback_deg=0., tracking_m=0., tracking_deg=0., contact_m=0.)
    for frame, row in enumerate(result['samples'], 1):
        time_s = min(motion.duration_s, (frame - 1) / motion.fps)
        assert row['frame'] == frame and abs(row['time_s'] - time_s) < 1e-7 and not row['violations']
        targets = sample_motion(motion, time_s, measured, cursor)
        scene.frame_set(frame)
        measured = rp.capture_motion_state(handle, profile, revision=motion.entry_snapshot.revision,
                                            captured_time_s=time_s)
        values = {item.control_id: item.value for item in measured.measured_controls}
        assert values.keys() == row['measured'].keys()
        for key, value in values.items():
            spec = controls[key]
            saved = row['measured'][key]
            saved = tuple(saved) if isinstance(saved, list) else saved
            error = value_error(value, saved, spec.value_shape)
            angular = spec.unit == 'degree' or spec.value_shape == 'quaternion'
            metric = 'playback_deg' if angular else 'playback_m'
            maxima[metric] = max(maxima[metric], error)
            assert error < (.05 if angular else .001), (frame, key, error)
        for target in targets.controls:
            angular = target.control_id == ORIENTATION
            error = value_error(values[target.control_id], target.value, controls[target.control_id].value_shape)
            metric = 'tracking_deg' if angular else 'tracking_m'
            maxima[metric] = max(maxima[metric], error)
            assert error < (.05 if angular else .001), (frame, target.control_id, error)
        errors = {}
        for event in targets.active_contacts:
            if event.release_s and time_s >= event.interval.end_s - 1e-9:
                continue
            anchor = event.anchor_id
            errors[anchor] = math.dist(values[anchor + '.position'], anchors[anchor])
            assert errors[anchor] < .001, (frame, anchor, errors[anchor])
            assert math.dist(row['active_foot_anchors'][anchor], anchors[anchor]) < 1e-5
        assert errors.keys() == row['active_foot_anchors'].keys()
        assert row['root_support'] == ('grounded' if errors else 'airborne')
        maxima['contact_m'] = max(maxima['contact_m'], max(errors.values(), default=0))
        handle._skin_cache_enabled = True
        try:
            sample = capture_sample(handle, frame, errors=errors)
            bounds.extend(skin_bounds(handle))
        finally:
            handle._skin_cache_enabled = False
        sample['rotations']['object_root'] = handle.rig.matrix_world.to_quaternion()
        assert abs(sample['floor'] - row['floor_m']) < .001, (frame, sample['floor'], row['floor_m'])
        samples.append(sample)
    report = review_samples(samples, height=profile.height_m, fps=motion.fps)
    assert report.passed, report.to_dict()
    scene.frame_set(1)
    assert digest(baked) == baked_sha
    return {'passed': True, 'frames': len(samples), 'maxima': {**maxima, **report.metrics},
            'swept_bounds': [[operation(point[i] for point in bounds) for i in range(3)] for operation in (min, max)],
            'motion_sha256': baked_sha, 'result_sha256': digest(directory / 'result.json'),
            'validator_sha256': digest(Path(__file__))}
