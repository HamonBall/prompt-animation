"""Check actual footfalls, flight, travel and review on procedural/imported rigs."""
from pathlib import Path
import json
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender.geometry import skin_bounds
from avatar_app.blender.motion import build_action
from avatar_app.planning.presets import preset_plan
from avatar_app.planning.movements import movement
from avatar_app.motion import ActionPlan, ContactConstraint
from avatar_app.pose import PosePlan

args = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
avatar = args[0] if args else 'demo'
names = [s for s in args[1:] if not s.startswith('--')] or ['jump', 'walk', 'run', 'wave', 'lie']
handle = create_demo_avatar() if avatar == 'demo' else import_avatar(str(ROOT/(
    'Hip Hop Mixamo.fbx' if avatar == 'mixamo' else 'Hip Hop Andrejs.fbx')))
prepare_preview(handle)
out = ROOT/'artifacts'/'presets'
out.mkdir(parents=True, exist_ok=True)
reports = {}
rest_hips = handle.rig.matrix_world @ handle.bones['Hips'].bone.head_local
rest_feet = {s: (handle.rig.matrix_world @ handle.bones[s+'Foot'].bone.head_local).z for s in ('Left','Right')}
for name in names:
    plan = preset_plan(name)
    try:
        result = build_action(handle, plan)
    except Exception as exc:
        print('PRESET_FAILURE', avatar, name, json.dumps(getattr(exc,'review',{})), flush=True)
        raise
    assert result['review']['passed'], result
    airborne = []
    for frame in range(handle.scene.frame_start, handle.scene.frame_end+1):
        handle.scene.frame_set(frame)
        if skin_bounds(handle)[0].z > .01 and all((handle.rig.matrix_world @ handle.bones[s+'Foot'].head).z > rest_feet[s]+.025
               for s in ('Left','Right')):
            airborne.append(frame)
    if name in ('jump','run'):
        assert airborne, name+' never left the floor'
    if name == 'walk':
        assert not airborne, 'Walking lost both supports'
    if name == 'lie':
        assert not airborne, 'Lying route floated during a support handoff'
    handle.scene.frame_set(handle.scene.frame_end)
    if name in ('walk','run'):
        direction = (handle.rig.matrix_world.to_3x3() @ handle.forward).normalized()
        travel = ((handle.rig.matrix_world @ handle.bones['Hips'].head)-rest_hips).dot(direction)
        height = (handle.rig.matrix_world.to_3x3() @ (handle.up*handle.height)).length
        assert abs(travel/height-plan.final_pose.get('pelvis_forward')) < .02, (name, travel)
    result['airborne_frames'] = len(airborne)
    reports[name] = result
    print('PRESET_PASSED', avatar, name, result['review']['metrics'], 'airborne',len(airborne), flush=True)
    if '--render' in args:
        frame = airborne[len(airborne)//2] if airborne else round(handle.scene.frame_end/2)
        handle.scene.frame_set(frame)
        handle.scene.render.resolution_percentage = 60
        handle.scene.render.filepath = str(out/f'{avatar}-{name}.png')
        bpy.ops.render.render(write_still=True)
    if name == 'walk':
        # A prompt edit after locomotion must keep the displaced floor anchors.
        end = result['ending_pose']
        initial = PosePlan(tuple(sorted(end['controls'].items())), end['contact'])
        followup = ActionPlan((movement('look', 'Turn head after walking', {'head':'left:25'}, 1,
            (ContactConstraint('left_foot'), ContactConstraint('right_foot'))),), initial=initial)
        build_action(handle, followup)
        handle.scene.frame_set(handle.scene.frame_end)
        position = handle.rig.matrix_world @ handle.bones['Hips'].head
        assert (position-rest_hips).dot(direction) > height*.5, 'Follow-up reset travel'
(out/f'{avatar}-review.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
print('ALL_PRESET_CHECKS_PASSED', avatar, flush=True)
