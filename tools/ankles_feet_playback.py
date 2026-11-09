"""Independently read every saved Stage 05.5 frame before rendering."""
import math
from pathlib import Path

from tools.artifact_store import digest


def verify(handle, profile, directory, result):
    from mathutils import Quaternion, Vector
    from avatar_app.blender import rig_profile as rp
    from avatar_app.blender.motion import capture_sample
    from avatar_app.movement_library import contracts as c
    from avatar_app.movement_library.compiler import ExecutionCursor, sample_motion, value_error

    out = Path(directory)
    baked = out / 'motion.blend'
    before = (digest(baked), baked.stat().st_mtime_ns)
    motion = c.loads(c.ExecutableMotion, (out / 'executable.json').read_text())
    scene = handle.scene
    assert scene.frame_start == 1 and scene.frame_end == result['frames'] == len(result['samples'])
    assert (scene.render.fps, scene.render.fps_base) == (motion.fps, 1)
    controls = {item.id: item for item in profile.controls}
    anchors = {item.anchor_id: item.position for item in motion.entry_snapshot.contact_anchors}
    acquired = {}
    cursor = ExecutionCursor()
    previous = {}
    velocity = {}
    measured = motion.entry_snapshot
    rig_world = handle.rig.matrix_world.copy()
    maxima = dict(tracking_m=0, tracking_deg=0, contact_m=0, floor_penetration_m=0,
                  playback_m=0, playback_deg=0, speed_deg_s=0, acceleration_deg_s2=0)
    for frame, row in enumerate(result['samples'], 1):
        assert row['frame'] == frame and not row['violations']
        time_s = min(motion.duration_s, (frame - 1) / motion.fps)
        assert abs(time_s - row['time_s']) < 1e-7
        scene.frame_set(frame)
        assert max(abs(value) for line in handle.rig.matrix_world - rig_world for value in line) < 1e-7
        targets = sample_motion(motion, time_s, measured, cursor)
        measured = rp.capture_motion_state(handle, profile, revision=motion.entry_snapshot.revision,
                                            captured_time_s=time_s)
        actual = {item.control_id: item.value for item in measured.measured_controls}
        assert set(actual) == set(row['measured'])
        for key, value in actual.items():
            spec = controls[key]
            saved = row['measured'][key]
            saved = tuple(saved) if isinstance(saved, list) else saved
            error = value_error(value, saved, spec.value_shape)
            angular = spec.unit == 'degree' or spec.value_shape == 'quaternion'
            metric = 'playback_deg' if angular else 'playback_m'
            maxima[metric] = max(maxima[metric], error)
            assert error < (.01 if angular else .0001), (key, frame, error)
        for target in targets.controls:
            spec = controls[target.control_id]
            angular = spec.unit == 'degree' or spec.value_shape == 'quaternion'
            error = value_error(actual[target.control_id], target.value, spec.value_shape)
            metric = 'tracking_deg' if angular else 'tracking_m'
            maxima[metric] = max(maxima[metric], error)
            assert error <= (3 if angular else .01), (target.control_id, frame, error)
        active = set()
        for event in targets.active_contacts:
            key = event.anchor_id
            point = actual[key + '.position']
            if event.acquire_s and event.interval.start_s > 0 and event.event_id not in acquired:
                assert abs(point[2]) <= .003, (key, frame, point)
                acquired[event.event_id] = point
                anchors[key] = point
            if ((event.acquire_s and time_s <= event.interval.start_s + 1e-9) or
                    (event.release_s and time_s >= event.interval.end_s - 1e-9)):
                continue
            active.add(key)
            error = math.dist(point, anchors[key])
            assert error <= .025, (key, frame, error)
            assert math.dist(anchors[key], row['active_foot_anchors'][key]) < .0001
            maxima['contact_m'] = max(maxima['contact_m'], error)
        assert active == set(row['active_foot_anchors']), (frame, active, row['active_foot_anchors'])
        floor = capture_sample(handle, frame)['floor']
        assert floor >= -.003
        maxima['floor_penetration_m'] = max(maxima['floor_penetration_m'], -floor)
        for mapping in profile.rest_to_semantic_mappings:
            key = mapping.semantic_id
            if key.rsplit('.', 1)[-1] not in ('thigh', 'shin', 'ankle', 'toe'):
                continue
            current = (rig_world @ handle.rig.pose.bones[mapping.source_bones[0]].matrix).to_quaternion()
            if key in previous:
                delta = current @ previous[key].conjugated()
                if delta.w < 0:
                    delta.negate()
                tangent = Vector((delta.x, delta.y, delta.z))
                speed = 2 * math.degrees(math.atan2(tangent.length, delta.w)) * motion.fps
                angular_velocity = tangent.normalized() * speed
                assert speed <= 360, (frame, key, speed)
                maxima['speed_deg_s'] = max(maxima['speed_deg_s'], speed)
                if key in velocity:
                    acceleration = (angular_velocity - velocity[key]).length * motion.fps
                    assert acceleration <= 3000, (frame, key, acceleration)
                    maxima['acceleration_deg_s2'] = max(maxima['acceleration_deg_s2'], acceleration)
                velocity[key] = angular_velocity
            previous[key] = Quaternion(current)
    scene.frame_set(1)
    assert before == (digest(baked), baked.stat().st_mtime_ns)
    return {'passed': True, 'frames': scene.frame_end, 'maxima': maxima,
            'motion_sha256': before[0], 'motion_mtime_ns': before[1],
            'result_sha256': digest(out / 'result.json'), 'validator_sha256': digest(Path(__file__))}
