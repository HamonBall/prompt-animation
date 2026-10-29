"""Publish stage 05.2 fixtures only after numeric, saved-media and visual review."""
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment,prepare_fragment,value_error
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.limbs import IDS
from avatar_app.movement_library.spatial import multiply,inverse,normalize
from avatar_app.movement_library.registry import parameter_schema
from avatar_app.motion import Surface
from tools.artifact_store import atomic_json,render_complete,digest
from tools.artifact_bundle import validate_manifest
from shoulders_arms_cases import cases

SOURCE=ROOT/'artifacts/stages/05.2';DEST=ROOT/'tests/fixtures/shoulders_arms/v1'


def angular_velocity(a,b):
    q=normalize(multiply(b,inverse(a)))
    if q[0]<0:q=tuple(-v for v in q)
    length=math.sqrt(sum(v*v for v in q[1:]))
    if length<1e-12:return (0,0,0)
    factor=math.degrees(2*math.atan2(length,q[0]))*30/length
    return tuple(v*factor for v in q[1:])


def metrics(result,entry,instance,profile,motion):
    specs={v.id:v for v in profile.controls};initial={v.control_id:v.value for v in entry.measured_controls}
    parameters={v.name:v.value for v in instance.parameters};active=('left','right') if parameters['side']=='both' else (parameters['side'],)
    value=dict(result['review']['metrics']);value.update({'tracking_deg':0,'tracking_m':0,'other_hand_m':0,
        'elbow_preservation_deg':0,'head_drift_deg':0,'body_angle_drift_deg':0,'object_root_drift_m':0,
        'object_root_drift_deg':0,'min_clearance_m':math.inf,'max_pole_step_deg':0})
    previous={};checked=set()
    for sample in result['samples']:
        assert not sample['violations']
        checked.update(sample['checked_goal_ids'])
        for key,error in sample['tracking_errors'].items():
            metric='tracking_m' if specs[key].unit=='metre' else 'tracking_deg'
            value[metric]=max(value[metric],error)
        for side in ('left','right'):
            if side not in active:value['other_hand_m']=max(value['other_hand_m'],value_error(tuple(sample['measured'][side+'.hand.position']),initial[side+'.hand.position'],'vector'))
            if instance.definition_id not in ('arm.reach','arm.fold','arm.stroke'):
                value['elbow_preservation_deg']=max(value['elbow_preservation_deg'],abs(sample['measured'][side+'.elbow.flexion']-initial[side+'.elbow.flexion']))
        value['head_drift_deg']=max(value['head_drift_deg'],value_error(tuple(sample['measured']['head.orientation']),initial['head.orientation'],'quaternion'))
        for spec in profile.controls:
            if spec.value_shape=='scalar' and spec.chain in ('torso','spine.mid','spine.upper','head','neck'):
                value['body_angle_drift_deg']=max(value['body_angle_drift_deg'],abs(sample['measured'][spec.id]-initial[spec.id]))
        for suffix,shape in (('m','vector'),('deg','quaternion')):
            key='object_root.'+('position' if suffix=='m' else 'orientation')
            value['object_root_drift_'+suffix]=max(value['object_root_drift_'+suffix],value_error(tuple(sample['measured'][key]),initial[key],shape))
        value['min_clearance_m']=min(value['min_clearance_m'],*sample['arm_clearance_m'].values())
        for side,pole in sample['elbow_poles'].items():
            if side in previous:
                a=previous[side];length=math.sqrt(sum(v*v for v in a)*sum(v*v for v in pole))
                angle=math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(a,pole))/length))))
                value['max_pole_step_deg']=max(value['max_pole_step_deg'],angle)
            previous[side]=pole
    assert checked=={g.goal_id for g in motion.goal_checks},'A declared goal was not measured'
    assert value['tracking_deg']<=3 and value['tracking_m']<=.01
    assert value['other_hand_m']<=.002 and value['elbow_preservation_deg']<=.5
    assert value['head_drift_deg']<=.5 and value['body_angle_drift_deg']<=.5
    assert value['object_root_drift_m']<=.002 and value['object_root_drift_deg']<=.5
    assert value['min_clearance_m']>=-.003 and value['max_pole_step_deg']<=90
    value.update({'cycle_seam_deg':0,'cycle_seam_m':0,'cycle_velocity_delta_deg_s':0})
    if instance.definition_id in ('arm.circle','shoulder.roll'):
        orbit=[t for t in motion.tracks if t.curve.easing=='linear' and t.curve.duration_s<parameters['duration_s']-1e-8]
        assert orbit
        first=round(min(t.interval.start_s for t in orbit)*30)
        last=round(max(t.interval.end_s for t in orbit)*30)
        samples=result['samples'];a=samples[first]['measured'];b=samples[last]['measured']
        assert set(samples[first]['contacts'])==set(samples[last]['contacts'])
        for side in active:
            key=side+'.hand.position';value['cycle_seam_m']=max(value['cycle_seam_m'],math.dist(a[key],b[key]))
            key=side+'.upper_arm.orientation'
            value['cycle_seam_deg']=max(value['cycle_seam_deg'],value_error(tuple(a[key]),tuple(b[key]),'quaternion'))
            before=angular_velocity(a[key],samples[first+1]['measured'][key])
            after=angular_velocity(samples[last-1]['measured'][key],b[key])
            value['cycle_velocity_delta_deg_s']=max(value['cycle_velocity_delta_deg_s'],math.dist(before,after))
        assert value['cycle_seam_deg']<=3 and value['cycle_seam_m']<=.01 and value['cycle_velocity_delta_deg_s']<=10
    value['frame_count']=result['frames']
    return value


def publish():
    visual=json.loads((SOURCE/'visual-review.json').read_text(encoding='utf-8'))
    manifest={'schema_version':1,'definition_version':1,'profile_version':4,'rigs':{}}
    summary={}
    for rig in ('demo','mixamo'):
        source=SOURCE/rig;destination=DEST/rig;destination.mkdir(parents=True,exist_ok=True)
        profile=c.loads(c.AvatarProfile,(source/'profile.json').read_text(encoding='utf-8'));catalog=catalog_for_profile(profile)
        report=json.loads((source/'execution-review.json').read_text(encoding='utf-8'))
        inspected=set()
        for page in visual[rig]['inspected_pages']:
            assert digest(SOURCE/page['path'])==page['sha256'],('Inspected page changed',rig,page['path'])
            for name in page['cases']:
                for view in ('front','side'):
                    assert digest(source/name/(view+'-sheet.png'))==page['source_sheets'][name][view],('Inspected source changed',rig,name,view)
                inspected.add(name)
        assert set(visual[rig]['reviewed_cases'])<=inspected,('Review lacks inspected page provenance',rig)
        verified={};manifest['rigs'][rig]={};reviews=[]
        for name,id,_,pose in cases():
            if rig=='demo' and id.startswith('shoulder.'):
                assert report[name]['status']=='unavailable_on_rig' and report[name]['error']['code']=='MISSING_CAPABILITY'
                continue
            path=source/name;result=json.loads((path/'result.json').read_text(encoding='utf-8'))
            assert result['review']['passed'] and len(result['samples'])==result['frames']
            assert name in visual[rig]['reviewed_cases'],('Visual inspection missing',rig,name)
            assert render_complete(path,('front','side')),('Incomplete or stale saved evidence',rig,name)
            bundle,asset,motion_file=validate_manifest(path)
            assert bundle['entry']['entry_fixture']=='entry-'+pose+'.json',('Entry fixture changed',rig,name)
            entry=c.loads(c.MotionStateSnapshot,(path/'entry.json').read_text(encoding='utf-8'))
            instance=c.loads(c.MovementInstance,(path/'instance.json').read_text(encoding='utf-8'))
            fragment=c.loads(c.MotionFragment,(path/'fragment.json').read_text(encoding='utf-8'))
            assert build_fragment(instance,entry,profile,(Surface(),),catalog)==fragment,('Builder changed',rig,name)
            motion=prepare_fragment(fragment,entry,profile)
            assert motion==c.loads(c.ExecutableMotion,(path/'executable.json').read_text(encoding='utf-8'))
            verified[name]=metrics(result,entry,instance,profile,motion)
        for id in IDS:
            names=[name for name,kind,_,_ in cases() if kind==id]
            missing=rig=='demo' and id.startswith('shoulder.')
            status='unavailable_on_rig' if missing else 'reviewed_for_envelope'
            maxima={} if missing else {key:(min if key=='min_clearance_m' else max)(verified[name][key] for name in names)
                                       for key in verified[names[0]]}
            evidence=(f'artifacts/stages/05.2/{rig}: '+','.join(names),
                      'Actual optional clavicles only; absent anatomy is explicitly unavailable.' if missing else
                      'Named measured entry envelope, both sides, declared ranges/timing and independent overrides; arbitrary target feasibility remains conditional.',
                      'Every motion frame measured and saved playback checked; front/side complete media and inspected review pages.' if not missing else 'No proxy shoulder animation or additional bones.')
            evidence+=('Named entries: '+', '.join(sorted({pose for _,kind,_,pose in cases() if kind==id}))+'.',)
            if id=='arm.sweep':
                evidence+=('110-degree cross-body and bilateral maximum use the shoulder-height cross-body-clearance entry; lowered Mixamo entry at 110 degrees is explicitly rejected. No silent arm lift or torso help.',)
            review=c.VerificationRecord(id,1,profile.avatar_id,4,catalog.definitions[id].parameter_specs,evidence,
                                        tuple(c.ParameterValue(k,v) for k,v in maxima.items()),status)
            catalog.register_review(review,profile);reviews.append(c.to_dict(review))
            records={}
            if not missing:
                for kind in ('entry','instance','fragment'):
                    target=destination/(id+'-'+kind+'.json');target.write_text((source/(id+'.default')/(kind+'.json')).read_text(encoding='utf-8'),encoding='utf-8')
                    records[kind]=str(target.relative_to(DEST)).replace('\\','/')
            manifest['rigs'][rig][id]={'status':status,'cases':names,'records':records,'maxima':maxima}
        (destination/'profile.json').write_text(c.dumps(profile)+'\n',encoding='utf-8')
        atomic_json(destination/'schemas.json',{id:parameter_schema(catalog.definitions[id]) for id in IDS})
        atomic_json(destination/'reviews.json',reviews)
        summary[rig]={'passed_cases':len(verified),'unavailable_cases':sum(v['status']=='unavailable_on_rig' for v in report.values()),
                      'measured_frames':sum(v['frame_count'] for v in verified.values()),'rendered_frames':2*sum(v['frame_count'] for v in verified.values()),
                      'per_case':verified,'profile_sha256':digest(source/'profile.json')}
    atomic_json(DEST/'manifest.json',manifest);atomic_json(SOURCE/'validation-summary.json',summary)
    print('PUBLISHED_SHOULDERS_ARMS_FIXTURES',sum(v['passed_cases'] for v in summary.values()),'passed cases',flush=True)


if __name__=='__main__':publish()
