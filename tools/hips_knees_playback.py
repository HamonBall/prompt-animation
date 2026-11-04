"""Read-only saved-action verification and physical rotation evidence for 05.4."""
import math,json
from pathlib import Path
from tools.artifact_store import atomic_json,digest
from tools.legs_evidence import runtime


def verify(h,p,out,result):
    import bpy
    from mathutils import Quaternion,Vector
    from avatar_app.blender import rig_profile as rp
    from avatar_app.blender.motion import capture_sample
    from avatar_app.movement_library import contracts as c
    from avatar_app.movement_library.compiler import value_error
    out=Path(out);scene=h.scene;source=digest(Path(__file__));motion=out/'motion.blend'
    before=(digest(motion),motion.stat().st_mtime_ns)
    entry=c.loads(c.MotionStateSnapshot,(out/'entry.json').read_text());specs={x.id:x for x in p.controls}
    anchors={a.anchor_id:Vector(a.position) for a in entry.contact_anchors}
    maximum={'degree_or_quaternion':0,'metre':0,'unitless_vector':0,'speed_deg_s':0,'acceleration_deg_s2':0,
             'floor_penetration_m':0,'contact_m':0,'independent_knee_error_deg':0}
    raw=[];previous=None;velocities={};world=h.rig.matrix_world.copy()
    for index,row in enumerate(result['samples']):
        scene.frame_set(index+1)
        assert max(abs(x) for line in h.rig.matrix_world-world for x in line)<1e-7,'Unexpected rig-object travel'
        actual=rp.capture_motion_state(h,p,revision=entry.revision,captured_time_s=row['time_s'])
        values={x.control_id:x.value for x in actual.measured_controls}
        for key,saved in row['measured'].items():
            saved=tuple(saved) if isinstance(saved,list) else saved;spec=specs[key]
            error=value_error(values[key],saved,spec.value_shape)
            group='metre' if spec.unit=='metre' else 'degree_or_quaternion' if spec.unit=='degree' or spec.value_shape=='quaternion' else 'unitless_vector'
            maximum[group]=max(maximum[group],error);assert error<({'metre':.0001,'degree_or_quaternion':.01,'unitless_vector':.0001}[group]),(key,error)
        rotations={'pelvis_semantic':tuple(rp.semantic_frame(h,p,'pelvis').to_quaternion())}
        for side in ('left','right'):
            hip,knee,ankle=(world @ h.bones[side.title()+part].head for part in ('UpLeg','Leg','Foot'))
            a,b=knee-hip,ankle-knee;geometric=math.degrees(a.angle(b))
            error=abs(geometric-values[side+'.knee.flexion']);maximum['independent_knee_error_deg']=max(maximum['independent_knee_error_deg'],error);assert error<.01
            for part,bone in (('thigh','UpLeg'),('shin','Leg'),('ankle','Foot')):
                rotations[side+'.'+part]=tuple((world @ h.bones[side.title()+bone].matrix).to_quaternion())
        for part in row['contacts']:
            side=part.split('_')[0];error=(Vector(rp.measure_endpoint(h,p,side+'.sole'))-anchors[side+'.sole']).length
            maximum['contact_m']=max(maximum['contact_m'],error);assert error<=.025
        floor=capture_sample(h,index+1,'saved_playback',{})['floor']
        maximum['floor_penetration_m']=max(maximum['floor_penetration_m'],max(0,-floor));assert floor>=-.003
        if previous is not None:
            for key,value in rotations.items():
                q=Quaternion(value);delta=q @ Quaternion(previous[key]).conjugated()
                if delta.w<0:delta.negate()
                velocity=delta.axis*math.degrees(delta.angle)*30;speed=velocity.length
                maximum['speed_deg_s']=max(maximum['speed_deg_s'],speed);assert speed<=360
                if key in velocities:
                    acceleration=(velocity-velocities[key]).length*30
                    maximum['acceleration_deg_s2']=max(maximum['acceleration_deg_s2'],acceleration);assert acceleration<=3000
                velocities[key]=velocity
        raw.append({'frame':index+1,'rotations':rotations});previous=rotations
    scene.frame_set(1);assert before==(digest(motion),motion.stat().st_mtime_ns)
    assert source==digest(Path(__file__))
    atomic_json(out/'saved-rotations.json',raw,compact=True)
    report={'passed':True,'frames':len(raw),'maxima':maximum,'motion_sha256':before[0],'motion_mtime_ns':before[1],
        'raw_sha256':digest(out/'saved-rotations.json'),'validator_sha256':source,'runtime_lock_sha256':runtime(),
        'result_sha256':digest(out/'result.json'),'no_motion_or_media_regenerated':True}
    atomic_json(out/'saved-playback-review.json',report);return report
