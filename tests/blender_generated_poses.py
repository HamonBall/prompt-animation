"""Apply real model benchmark outputs to the actual rig without repeating inference."""
from pathlib import Path
import json
import math
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar_app.pose import update_pose
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.pose import build_pose_transition
from avatar_app.blender.scene import prepare_preview

rows = json.loads((ROOT / 'artifacts' / 'pose-benchmark.json').read_text(encoding='utf-8'))
assert len(rows) == 7 and all(row['passed'] for row in rows), 'Run the pose benchmark first.'
handle = import_avatar(str(ROOT / 'Hip Hop Andrejs.fbx'))
prepare_preview(handle)
output = ROOT / 'artifacts' / 'generated-poses'
output.mkdir(parents=True, exist_ok=True)
for index, row in enumerate(rows):
    record = row['plan']
    plan = update_pose(None, {**record['controls'], 'duration': .5}, record['contact'])
    build_pose_transition(handle, plan)
    handle.scene.frame_set(handle.scene.frame_end)
    for bone in handle.rig.pose.bones:
        assert all(math.isfinite(value) for matrix_row in bone.matrix for value in matrix_row)
    if '--render' in sys.argv:
        handle.scene.render.resolution_percentage = 60
        handle.scene.render.filepath = str(output / f'pose-{index + 1}.png')
        bpy.ops.render.render(write_still=True)
    print('MODEL_POSE_APPLIED', index + 1, row['prompt'], flush=True)
print('ALL_MODEL_POSES_APPLIED')
