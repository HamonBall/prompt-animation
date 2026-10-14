"""Bound the preview floor and prevent repeated work for unchanged poses."""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
import bpy
from mathutils import Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.scene import prepare_preview, resolve_seat
from avatar_app.blender import geometry, kinematics, pose
from avatar_app.pose import PosePlan, update_pose

handle = create_demo_avatar()
prepare_preview(handle)
bpy.context.view_layer.update()
floor = next(obj for obj in handle.environment if obj.name == 'Preview floor')
assert abs(floor.dimensions.x - 5) < 1e-6 and abs(floor.dimensions.y - 5) < 1e-6
assert len(floor.data.polygons) == 1
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            space = area.spaces.active
            assert space.shading.type == 'SOLID' and space.shading.color_type == 'TEXTURE'
            assert not space.overlay.show_floor

# Visual bounds must use the avatar skin, independent of the floor and seat.
pose.target_pose(handle, PosePlan())
handle._skin_cache_enabled = True
with patch.object(geometry, 'mesh_points', wraps=geometry.mesh_points) as extract:
    low, high = geometry.skin_bounds(handle)
    count = extract.call_count
    cached = handle._skin_bounds
    low.z = -999  # Callers cannot corrupt cached bounds.
    repeated_low, repeated_high = geometry.skin_bounds(handle)
    assert extract.call_count == count and handle._skin_bounds is cached
    assert repeated_low.z > -1 and (high - repeated_high).length < 1e-6
    pose.target_pose(handle, update_pose(None, {'pelvis_drop': .2}))
    moved_low, moved_high = geometry.skin_bounds(handle)
    assert extract.call_count > count and moved_high.z < high.z - .25
    resolve_seat(handle)
    seat_low, seat_high = geometry.skin_bounds(handle)
    assert (seat_low - moved_low).length < 1e-6
    assert (seat_high - moved_high).length < 1e-6
handle._skin_cache_enabled = False

# An identity rotation or already aligned bone must not update the whole scene.
bone = handle.bones['Head']
before = bone.matrix.copy()
update = Mock()
stub = SimpleNamespace(context=SimpleNamespace(view_layer=SimpleNamespace(update=update)))
with patch.object(pose, 'bpy', stub), patch.object(kinematics, 'bpy', stub):
    pose.rotate_bone(bone, Quaternion())
    kinematics.aim(bone, bone.tail - bone.head)
    assert not update.called
assert max(abs(v) for row in bone.matrix - before for v in row) < 1e-6
pose.rotate_bone(bone, Quaternion(Vector((0, 0, 1)), .2))
assert max(abs(v) for row in bone.matrix - before for v in row) > .01
print('PREVIEW_SIZE_SHADING_AND_CACHE_CHECKS_PASSED', flush=True)
