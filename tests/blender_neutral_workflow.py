"""Real application load/reset regression, plus segmented-demo diagnostic views."""
import json
import math
from pathlib import Path
import sys
import time
from unittest.mock import patch
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from avatar_app import main as app
from avatar_app.pose import update_pose
from avatar_app.motion import ActionPlan,action_from_pose
from avatar_app.blender.pose import axes, target_pose
from tools.artifact_store import atomic_json

OUT = ROOT / 'artifacts/maintenance/neutral-artifacts/neutral'
OUT.mkdir(parents=True, exist_ok=True)


def measure(h):
    right, forward, up = axes(h)
    values = {}
    for side, sign in (('Left', -1), ('Right', 1)):
        expected = right * sign * math.sin(math.radians(8)) - up * math.cos(math.radians(8))
        for part in ('Arm', 'ForeArm', 'Hand'):
            bone = h.bones[side + part]
            direction = (bone.tail - bone.head).normalized()
            error = math.degrees(math.acos(max(-1, min(1, direction.dot(expected)))))
            assert error < .1, (side, part, error)
            values[side + part] = error
    return values


def state(h):
    ad = h.rig.animation_data
    return {'current_frame': h.scene.frame_current, 'initial_frame': h.scene.frame_start,
            'final_frame': h.scene.frame_end, 'action': ad.action.name,
            'slot': ad.action_slot.identifier, 'history_length': len(app._state['history']),
            'arm_error_deg': measure(h)}


def views(h, label):
    scene = h.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.color_type = 'MATERIAL'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.view_settings.view_transform = 'Standard'
    scene.render.resolution_x = scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    focus = Vector((0, 0, 1.05))
    for name, offset in [('front', Vector((0, 4, .1))), ('side', Vector((4, 0, .1))),
                         ('three-quarter', Vector((2, 4, .3)))]:
        scene.camera.location = focus + offset
        scene.camera.rotation_euler = (-offset).to_track_quat('-Z', 'Y').to_euler()
        scene.camera.data.type = 'ORTHO'
        scene.camera.data.ortho_scale = 2
        scene.render.filepath = str(OUT / f'{label}-{name}.png')
        bpy.ops.render.render(write_still=True)


with patch.object(app, '_default_avatar', return_value=ROOT / 'absent.fbx'):
    app.main()
report = {}
for name, filename in [('demo', ''), ('andrejs', 'Hip Hop Andrejs.fbx'), ('mixamo', 'Hip Hop Mixamo.fbx')]:
    records = []
    for iteration in range(2):
        bpy.context.scene.avatar_path = str(ROOT / filename) if filename else ''
        assert bpy.ops.avatar.load() == {'FINISHED'}
        h = app._state['avatar']
        assert h.scene.frame_current == h.scene.frame_end
        assert len(app._state['history']) == 1
        assert app._state['plan'].values == ()
        records.append({'fresh_load': state(h)})
        if name == 'demo' and iteration == 0:
            # The application default camera, before diagnostic camera changes.
            h.scene.render.engine = 'BLENDER_WORKBENCH'
            h.scene.render.filepath = str(OUT / 'demo-app-default-camera.png')
            bpy.ops.render.render(write_still=True)
            views(h, 'demo-neutral-before')
        asymmetric = update_pose(app._state['plan'], {'left_arm_elevation': 45,
            'left_forearm_elevation': 80, 'left_forearm_azimuth': 60, 'right_hand_pitch': 20, 'duration': .5})
        app.apply_candidate(bpy.context, action_from_pose(asymmetric), 'Authored regression', time.perf_counter(), h, app._state['plan'])
        assert isinstance(app._state['plan'],ActionPlan)
        h.scene.frame_set(h.scene.frame_end)
        h.scene.avatar_prompt = 'neutral pose'
        assert bpy.ops.avatar.prompt() == {'FINISHED'}
        reset_display = h.scene.frame_current
        assert app._state['plan'].values == ()
        assert app._state['reviewed_plan'] is app._state['plan']
        # Reset is a transition: its first frame preserves the previous pose.
        h.scene.frame_set(h.scene.frame_end)
        records[-1]['reset'] = state(h)
        records[-1]['reset']['displayed_transition_frame'] = reset_display
    report[name] = records

    # Explicit zero and wrist controls override neutral defaults on every rig.
    h.rig.animation_data_clear()
    target_pose(h, update_pose(None, {'right_arm_elevation': 0}))
    up = axes(h)[2]
    assert (h.bones['RightHand'].tail - h.bones['RightHand'].head).normalized().dot(up) < -.9999
    baseline = h.bones['RightHand'].matrix.to_quaternion().copy()
    from avatar_app.blender.pose import rotation
    pose = update_pose(None, {'right_arm_elevation': 0, 'right_hand_pitch': 30})
    target_pose(h, pose)
    assert abs((rotation(pose, 'right_hand', axes(h)) @ baseline).dot(h.bones['RightHand'].matrix.to_quaternion())) > .9999

    if name == 'demo':
        from tools.preview_movement import load_entry
        signature = {'bones': {b.name: [list(row) for row in b.matrix_local] for b in h.rig.data.bones},
                     'meshes': {o.name: {'vertices': len(o.data.vertices), 'polygons': len(o.data.polygons),
                                       'groups': [g.name for g in o.vertex_groups]} for o in h.objects if o.type == 'MESH'}}
        atomic_json(OUT / 'demo-geometry-before.json', signature)
        for label, values in [('bent', None), ('elbow-30', {'left_arm_elevation': 90, 'left_forearm_elevation': 120,
                                                        'right_arm_elevation': 90, 'right_forearm_elevation': 120}),
                              ('elbow-90', {'left_arm_elevation': 90, 'left_forearm_elevation': 180,
                                          'right_arm_elevation': 90, 'right_forearm_elevation': 180})]:
            if values is None:
                load_entry(h, ROOT / 'tests/fixtures/movement_fragments/v1/entry-bent-turned.json')
            else:
                target_pose(h, update_pose(None, values))
            for side in ('Left', 'Right'):
                assert (h.bones[side+'Arm'].tail-h.bones[side+'ForeArm'].head).length < 1e-6
                assert (h.bones[side+'ForeArm'].tail-h.bones[side+'Hand'].head).length < 1e-6
            views(h, 'demo-' + label + '-before')
    print('APPLICATION_NEUTRAL_PASSED', name, flush=True)
atomic_json(OUT / 'workflow-review.json', report)
print('ALL_APPLICATION_NEUTRAL_CHECKS_PASSED', flush=True)
