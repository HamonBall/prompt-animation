"""Bounded geometric probe of authored sweep end frames, without retained scenes.

Uses the arm adapter's world-frame application formula. Full sampled execution is
still required for any resulting supported fixture; this is not an acceptance gate.
"""
import json
from pathlib import Path
import sys
import bpy
from mathutils import Quaternion,Matrix
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.blender.avatar import import_avatar
from avatar_app.blender.scene import prepare_preview
from avatar_app.blender import rig_profile as rp
from avatar_app.blender.pose import target_pose
from avatar_app.pose import update_pose
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.limbs import with_shoulders_v1
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment
from avatar_app.movement_library.curves import segment_distance
from avatar_app.motion import Surface
from tools.preview_movement import capture_entry
from tools.artifact_store import atomic_json

h=import_avatar(str(ROOT/'Hip Hop Mixamo.fbx'));prepare_preview(h)
p=with_shoulders_v1(rp.calibrate_joint_frames(h,avatar_id='diagnostic.mixamo',include_head_aim=True,recorded_at='2026-10-28'))
catalog=catalog_for_profile(p);report={}


def clearance(side):
    hip=rp.semantic_frame(h,p,'pelvis').translation;chest=rp.semantic_frame(h,p,'spine.upper').translation
    head=rp.semantic_frame(h,p,'head').translation;start=hip.lerp(chest,.35);axis=chest-start
    points=[h.rig.matrix_world @ h.bones[side.title()+name].head for name in ('Arm','ForeArm','Hand')]
    other='right' if side=='left' else 'left'
    opposite=[h.rig.matrix_world @ h.bones[other.title()+name].head for name in ('Arm','ForeArm','Hand')]
    values={'chest':float('inf'),'head':float('inf'),'opposite':float('inf')}
    for a,b in zip(points,points[1:]):
        for i in range(1,9):
            point=a.lerp(b,i/8);t=max(0,min(1,(point-start).dot(axis)/axis.length_squared))
            values['chest']=min(values['chest'],(point-(start+axis*t)).length-.093*p.height_m)
            values['head']=min(values['head'],(point-head).length-.083*p.height_m)
        for c0,d in zip(opposite,opposite[1:]):values['opposite']=min(values['opposite'],segment_distance(a,b,c0,d)-.036*p.height_m)
    return values


base=json.loads((ROOT/'tests/fixtures/movement_fragments/v1/entry-bent-turned.json').read_text())['controls']
variants=[('original',base)]
for left,right,forearm in ((90,90,0),(90,90,45)):
    values={'root_yaw':90,'torso_pitch':10,'head_yaw':-20}
    for side,e in (('left',left),('right',right)):
        values.update({side+'_arm_elevation':e,side+'_arm_azimuth':0,side+'_forearm_elevation':forearm,side+'_forearm_azimuth':90})
    variants.append((str((left,right,forearm)),values))
for name,controls in variants:
    minima={side:{part:float('inf') for part in ('chest','head','opposite')} for side in ('left','right')}
    for angle in range(0,111,10):
        h.rig.animation_data_clear();target_pose(h,update_pose(None,controls,'none'));entry=capture_entry(h,p)
        i=instantiate_movement('arm.sweep',{'side':'both','angle':angle},instance_id='probe.1',profile=p,entry_state=entry,catalog=catalog)
        m=prepare_fragment(build_fragment(i,entry,p,(Surface(),),catalog),entry,p)
        for side in ('left','right'):
            key=side+'.upper_arm.orientation'
            track=next(t for t in m.tracks if t.control_id==key)
            bone=h.bones[side.title()+'Arm'];world=h.rig.matrix_world @ bone.matrix
            rotation=Quaternion(track.curve.end_value) @ rp.semantic_frame(h,p,side+'.upper_arm').to_quaternion().conjugated() @ world.to_quaternion()
            bone.matrix=h.rig.matrix_world.inverted() @ (Matrix.Translation(world.translation) @ rotation.to_matrix().to_4x4() @ Matrix.Diagonal((*world.to_scale(),1)))
            bpy.context.view_layer.update()
        for side in minima:
            for part,value in clearance(side).items():minima[side][part]=min(minima[side][part],value)
    report[name]={'controls':controls,'minima':minima}
    print('SWEEP_CLEARANCE_DIAGNOSTIC',name,minima,flush=True)
atomic_json(ROOT/'artifacts/stages/05.2/sweep-clearance-diagnostic.json',report)
