"""Full-playback preservation of authored arms through existing head/torso IDs."""
from pathlib import Path
import sys
import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from avatar_app.blender.demo import create_demo_avatar
from avatar_app.blender.avatar import import_avatar,discard_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.motion import build_action
from avatar_app.movement_library.joints import catalog_for_profile,IDS as HEAD
from avatar_app.movement_library.torso_pelvis import with_pelvis_v1,IDS as BODY
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment,value_error
from avatar_app.motion import Surface
from tools.preview_movement import load_entry,capture_entry
from tools.artifact_store import atomic_json

out=ROOT/'artifacts/maintenance/neutral-artifacts/preservation'
report={}
for rig in ('demo','mixamo'):
    h=create_demo_avatar() if rig=='demo' else import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'))
    prepare_preview(h)
    p=with_pelvis_v1(rp.calibrate_joint_frames(h,avatar_id='maintenance.'+rig,include_head_aim=True,recorded_at='2026-10-23'))
    catalog=catalog_for_profile(p)
    arm_controls=[s.id for s in p.controls if s.value_shape=='scalar' and
                  any(s.chain==side+'.'+joint for side in ('left','right') for joint in ('upper_arm','forearm','wrist'))]
    results={}
    for id in (*HEAD,*(v for v in BODY if v.startswith('torso.'))):
        h.rig.animation_data_clear()
        load_entry(h,ROOT/'tests/fixtures/movement_fragments/v1/entry-bent-turned.json')
        entry=capture_entry(h,p)
        values={v.control_id:v.value for v in entry.measured_controls}
        hand_points={side:(h.bones[side+'Hand'].head.copy() if id in HEAD else
                         h.bones[side+'Arm'].parent.matrix.inverted() @ h.bones[side+'Hand'].head)
                     for side in ('Left','Right')}
        parameters={'duration_s':.8,'hold_s':0}
        if id=='neck.lead' and 'anatomy.neck' not in p.capabilities:parameters['neck_policy']='head_only'
        i=instantiate_movement(id,parameters,instance_id='preservation.1',profile=p,entry_state=entry,catalog=catalog)
        f=build_fragment(i,entry,p,(Surface(),),catalog)
        result=build_action(h,prepare_fragment(f,entry,p),profile=p)
        maximum=0;endpoint=0
        for sample in result['samples']:
            h.scene.frame_set(sample['frame'])
            for control in arm_controls:
                maximum=max(maximum,abs(rp.measure_joint_angle(h,p,control)-values[control]))
            for side in ('Left','Right'):
                point=h.bones[side+'Hand'].head.copy() if id in HEAD else (
                      h.bones[side+'Arm'].parent.matrix.inverted() @ h.bones[side+'Hand'].head)
                endpoint=max(endpoint,(h.rig.matrix_world.to_3x3() @ (point-hand_points[side])).length)
        assert maximum<.5,(rig,id,maximum)
        assert endpoint<.002,(rig,id,endpoint)
        results[id]={'frames':result['frames'],'arm_drift_deg':maximum,'hand_endpoint_drift_m':endpoint,
                     'entry_fixture':'entry-bent-turned.json','entry_kind':'authored_non_neutral'}
        print('ARM_PRESERVATION_PASSED',rig,id,maximum,flush=True)
    report[rig]=results
    discard_avatar(h)
atomic_json(out/'review.json',report)
print('ALL_ARM_PRESERVATION_CHECKS_PASSED',flush=True)
