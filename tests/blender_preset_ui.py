"""Prompt-only interface uses internal foundations and preserves cancellation."""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from avatar_app import main as app
from avatar_app.motion import ActionPlan
from avatar_app.pose import update_pose
from avatar_app.blender.motion import build_action_frames, build_action
from avatar_app.blender.requests import BoundFoundation
from avatar_app.blender.rig_profile import measure_endpoint
from avatar_app.blender.geometry import support_skin_height
from avatar_app.models import PlanError
from avatar_app.planning.action_interpreter import decode_action
from avatar_app.planning.presets import preset_plan, foot_target, planted
from avatar_app.planning.movements import movement

args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else ['demo']
rig = args[0]
assert rig in ('demo', 'mixamo')
with patch.object(app, '_default_avatar', return_value=ROOT / ('Hip Hop Mixamo.fbx' if rig == 'mixamo' else 'absent.fbx')):
    app.main()
scene = bpy.context.scene
if args[1:2] == ['chair']:
    height = float(args[2]) if len(args) > 2 else .45
    original = app._state['plan']
    handle = app._state['avatar']
    prior_action = handle.rig.animation_data.action
    try:
        app.generate(bpy.context, 'sit on a chair')
    except PlanError as error:
        assert 'Enable the preview seat' in str(error)
    else:
        raise AssertionError('The request accepted a missing seat')
    assert app._state['plan'] is original and handle.rig.animation_data.action == prior_action
    scene.avatar_seat_height = height
    scene.avatar_show_seat = True
    scene.avatar_prompt = 'sit on a chair'
    with patch.object(app, 'bake_request', wraps=app.bake_request) as bake:
        assert bpy.ops.avatar.prompt() == {'FINISHED'}
    bound = bake.call_args.args[1]
    assert isinstance(bound, BoundFoundation)
    assert scene.frame_end - scene.frame_start + 1 == 136
    plan = app._state['plan']
    assert plan.final_pose.get('pelvis_drop') > .1 and plan.final_pose.contact == 'both'
    assert plan.final_pose.revision == plan.revision > original.revision
    scene.frame_set(scene.frame_end)
    seat = next(surface for surface in handle.surfaces if surface.name == 'seat')
    assert abs(support_skin_height(handle, 'pelvis', seat) - seat.height) < .003
    correction, _ = decode_action(json.dumps(dict(kind='timing', base=None, stages=[], changes={},
                                                  contact=None, factor=1.1, message='Sit more slowly')), plan)
    assert tuple(stage.id for stage in correction.stages) == tuple(stage.id for stage in plan.stages)
    assert correction.duration > plan.duration
    print('PUBLIC_CHAIR_PREVIEW_PASSED', rig, height, 136, plan.final_pose.get('pelvis_drop'), flush=True)
    raise SystemExit(0)

assert not hasattr(bpy.types.Scene, 'avatar_preset')
assert not hasattr(bpy.types, 'AVATAR_OT_preset')
assert 'preset' not in bpy.ops.avatar.prompt.get_rna_type().properties
scene.avatar_use_reference = False
scene.avatar_prompt = 'wave with your left hand'
started = time.perf_counter()
with patch('avatar_app.planning.action_interpreter.get_model', side_effect=AssertionError('Simple prompt called AI')), \
     patch.object(app, 'load_reference', side_effect=AssertionError('Unexpected web context')), \
     patch.object(app, 'bake_request', wraps=app.bake_request) as bake:
    assert bpy.ops.avatar.prompt() == {'FINISHED'}
preview_seconds = time.perf_counter() - started
bound = bake.call_args.args[1]
assert isinstance(bound, BoundFoundation), 'Expected the public prompt to use the recipe backend'
assert scene.frame_end - scene.frame_start + 1 == 208
handle = app._state['avatar']
entry_hand = measure_endpoint(handle, bound.profile, 'left.hand')
scene.frame_set(scene.frame_start + 60)
assert sum((a - b) ** 2 for a, b in zip(measure_endpoint(handle, bound.profile, 'left.hand'), entry_hand)) > .01
scene.frame_set(scene.frame_end)
assert sum((a - b) ** 2 for a, b in zip(measure_endpoint(handle, bound.profile, 'left.hand'), entry_hand)) < 1e-6
assert handle.rig.animation_data.action is not None
print('FIRST_PUBLIC_PREVIEW', rig, 'avatar.prompt', type(bound.motion).__name__, scene.frame_end,
      round(preview_seconds, 3), flush=True)
assert scene.avatar_prompt == 'wave with your left hand'
assert isinstance(app._state['plan'], ActionPlan)
assert app._state['plan'].description == 'Wave left hand 3 times'
assert not app._state['experimental']


class Layout:
    def __init__(self):
        self.properties, self.operators, self.labels = [], [], []
    def column(self): return self
    def prop(self, data, name, **kwargs): self.properties.append(name)
    def operator(self, name, **kwargs): self.operators.append(name)
    def label(self, text, **kwargs): self.labels.append(text)


layout = Layout()
app.AVATAR_PT_panel.draw(SimpleNamespace(layout=layout), bpy.context)
assert layout.properties == ['avatar_prompt'], layout.properties
assert layout.operators == ['avatar.prompt', 'avatar.play'], layout.operators
assert not any('preset' in label.lower() or 'stages' in label.lower() or 'body controls' in label.lower()
               for label in layout.labels), layout.labels
assert 'DEFAULT_CLOSED' in app.AVATAR_PT_settings.bl_options

# A descriptive prompt can adapt a foundation via the same interpreter and
# builder, without selecting a move in the UI.
class Model:
    def complete(self, messages, schema, **kwargs):
        payload = json.loads(messages[-1]['content'])
        assert payload['request'] == scene.avatar_prompt
        assert {b['name'] for b in payload['motion_foundations']} == {'jump','walk','lie','run','wave'}
        return json.dumps({'kind': 'adapt', 'base': {'name': 'wave', 'side': 'left', 'waves': 1},
            'stages': [], 'changes':{'head':'left:20'}, 'contact':None, 'factor':1.1,
            'message':'Greet gently and look toward the other person.'})

scene.avatar_prompt = 'Greet someone gently with your left hand and look toward them.'
with patch('avatar_app.planning.action_interpreter.get_model', return_value=Model()):
    assert bpy.ops.avatar.prompt() == {'FINISHED'}
assert len(app._state['plan'].stages) == 4
assert dict(app._state['plan'].stages[0].targets)['head_yaw'] == 20
assert abs(app._state['plan'].final_pose.get('head_yaw') - 20) < .01
assert all(stage.contacts for stage in app._state['plan'].stages)

# Cancel after takeoff while foot-path IK is actively moving both legs.
handle = app._state['avatar']
scene.frame_set(scene.frame_end)
old_action = handle.rig.animation_data.action
old_frame = scene.frame_current
iterator = build_action_frames(handle, preset_plan('jump'))
for _ in range(40): next(iterator)
assert scene.frame_current == 40
iterator.close()
assert handle.rig.animation_data.action == old_action
assert scene.frame_current == old_frame

# A raised incoming foot must not be accepted as a floor attachment merely
# because its bone stayed at the planned height.
initial = update_pose(None, {**foot_target('left', height=.04),
    **foot_target('right', height=.04), 'pelvis_drop': .05}, 'both')
build_action(handle, ActionPlan((movement('look', 'Look while feet are floor-supported',
    {'head':'left:15'}, 1, planted('left','right')),), initial=initial))
scene.frame_set(scene.frame_end)
assert all(abs(support_skin_height(handle, side+'_foot')) < .025 for side in ('left','right'))
print('PROMPT_ONLY_FOUNDATIONS_AND_AIRBORNE_CANCEL_PASSED', flush=True)
