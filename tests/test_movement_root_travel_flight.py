"""Pure root-trajectory checks using the published profile-8 snapshots."""
from dataclasses import replace
from pathlib import Path
import unittest

from avatar_app.motion import Surface
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import (
    ExecutionCursor, build_fragment, instantiate_movement, prepare_fragment, sample_motion,
)
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.root_motion import IDS, POSITION
from avatar_app.movement_library.spatial import angle_rotation

FIXTURES = Path(__file__).parent / 'fixtures/ankles_feet_toes/v1/demo'


def compile_case(profile, entry, move, params):
    catalog = catalog_for_profile(profile)
    instance = instantiate_movement(move, params, instance_id='root.test', profile=profile,
                                    entry_state=entry, catalog=catalog)
    fragment = build_fragment(instance, entry, profile, (Surface(),), catalog)
    return instance, fragment, prepare_fragment(fragment, entry, profile)


class RootContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = c.loads(c.AvatarProfile, (FIXTURES / 'profile.json').read_text())
        cls.ground = c.loads(c.MotionStateSnapshot, (FIXTURES / 'heel.raise-entry.json').read_text())
        values = tuple(replace(value, value=(*value.value[:2], value.value[2] + 1.2))
                       if value.unit == 'metre' and value.frame == 'world' else value
                       for value in cls.ground.measured_controls)
        root = cls.ground.root_transform
        cls.air = replace(cls.ground, active_contacts=(), contact_anchors=(), measured_controls=values,
                          root_transform=replace(root, position=(*root.position[:2], root.position[2] + 1.2),
                                                 orientation=angle_rotation(yaw=90)))

    def test_line_arc_frames_and_round_trip(self):
        for path, frame in (('line', 'world'), ('line', 'entry_body'), ('arc', 'world'), ('arc', 'entry_body')):
            with self.subTest(path=path, frame=frame):
                _, _, motion = compile_case(self.profile, self.air, 'root.travel',
                                             {'path': path, 'frame': frame, 'duration_s': 3.5})
                self.assertEqual(c.loads(c.ExecutableMotion, c.dumps(motion)), motion)
                cursor = ExecutionCursor()
                path_values = [next(value.value for value in sample_motion(
                    motion, i / c.FPS, self.air, cursor).controls if value.control_id == POSITION)
                    for i in range(106)]
                start, end, middle = path_values[0], path_values[-1], path_values[52]
                axis = 1 if frame == 'world' else 0
                self.assertAlmostEqual(end[axis] - start[axis], 1 if axis else -1)
                deviation = abs(middle[1-axis] - start[1-axis])
                self.assertAlmostEqual(deviation, 0) if path == 'line' else self.assertGreater(deviation, .13)

    def test_takeoff_releases_then_holds(self):
        _, _, motion = compile_case(self.profile, self.ground, 'root.hover', {})
        self.assertEqual({event.anchor_id for event in motion.contact_events}, {'left.sole', 'right.sole'})
        self.assertTrue(all(event.release_s == event.interval.end_s == .2 for event in motion.contact_events))
        self.assertAlmostEqual(motion.duration_s, 2.7)
        self.assertEqual([t.curve.end_value[2] for t in motion.tracks if t.control_id == POSITION][-2:], [.8, .8])

    def test_invalid_requests_and_missing_capability(self):
        for entry, move, params, code in (
            (self.ground, 'root.turn', {'mode': 'grounded_pivot'}, 'CONSTRAINT_CONFLICT'),
            (self.ground, 'root.travel', {}, 'CONSTRAINT_CONFLICT'),
            (self.air, 'root.hover', {}, 'ENTRY_MISMATCH'),
            (self.air, 'root.travel', {'distance_m': 2.1}, 'INVALID_PARAMETER'),
            (self.air, 'root.travel', {'path': 'arc', 'arc_deg': 0}, 'INVALID_PARAMETER'),
            (self.air, 'root.orient', {'angle_deg': float('nan')}, 'INVALID_PARAMETER'),
        ):
            with self.subTest(move=move, params=params), self.assertRaises(c.MotionContractError) as error:
                compile_case(self.profile, entry, move, params)
            self.assertEqual(error.exception.code, code)
        profile = replace(self.profile, version=7)
        self.assertTrue(set(IDS).isdisjoint(catalog_for_profile(profile).definitions))


if __name__ == '__main__':
    unittest.main()
