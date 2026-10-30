"""Independent rebuild, actual-measurement and per-ID stage-05.3a audit."""
import argparse,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.hands import IDS
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import build_fragment,prepare_fragment,sample_motion,value_error,ExecutionCursor
from avatar_app.motion import Surface
from tools.hands_evidence_cases import cases
from tools.artifact_store import atomic_json,input_identity,digest
from tools.hands_render_state import render_complete
from tools.hands_source_compatibility import numeric_source_valid
from tools.artifact_bundle import validate_manifest
from tools.publish_shoulders_arms_fixtures import angular_velocity
OUT=ROOT/'artifacts/stages/05.3a'


def audit(available=False,visual=False):
    result={};producer=input_identity(OUT/'identity')['producer_sha256']
    for rig in ('demo','mixamo'):
        base=OUT/rig;p=c.loads(c.AvatarProfile,(base/'profile.json').read_text());catalog=catalog_for_profile(p)
        controls={x.id:x for x in p.controls};pending=[];rows={};maxima={}
        def maximum(key,value):maxima[key]=max(maxima.get(key,0),value)
        for name,id,_,_ in cases():
            out=base/name
            if not (out/'result.json').exists():pending.append(name);continue
            r=json.loads((out/'result.json').read_text())
            if not numeric_source_valid(out):pending.append(name);continue
            if available and (not (out/'preview-manifest.json').exists() or
                json.loads((out/'preview-manifest.json').read_text())['inputs']!=input_identity(out)):
                pending.append(name);continue
            p0=c.loads(c.MotionStateSnapshot,(out/'entry.json').read_text());initial={x.control_id:x.value for x in p0.measured_controls}
            instance=c.loads(c.MovementInstance,(out/'instance.json').read_text());stored=c.loads(c.MotionFragment,(out/'fragment.json').read_text())
            parameters={x.name:x.value for x in instance.parameters}
            rebuilt=build_fragment(instance,p0,p,(Surface(),),catalog);assert stored==rebuilt,(rig,name,'fragment rebuild')
            motion=prepare_fragment(rebuilt,p0,p);assert c.loads(c.ExecutableMotion,(out/'executable.json').read_text())==motion
            assert r['review']['passed'] and len(r['samples'])==r['frames']==math.ceil(motion.duration_s*30)+1
            manifest,asset,baked=validate_manifest(out);assert len(manifest['expected_frames'])==r['frames']
            if visual:assert render_complete(out,('front','side')),(rig,name,'full saved-motion evidence missing')
            cursor=ExecutionCursor();sample_max=0
            for sample in r['samples']:
                assert not sample['violations']
                targets=sample_motion(motion,sample['time_s'],p0,cursor)
                for target in targets.controls:
                    spec=controls[target.control_id];measured=sample['measured'][target.control_id]
                    if isinstance(measured,list):measured=tuple(measured)
                    error=value_error(measured,target.value,spec.value_shape)
                    gate=.01 if spec.unit=='metre' else 3
                    assert error<=gate,(rig,name,target.control_id,error,gate)
                    maximum('endpoint_error_m' if spec.unit=='metre' else 'orientation_angle_error_deg',error);sample_max=max(sample_max,error)
                for side in ('left','right'):
                    if id.startswith('wrist.'):
                        endpoint=side+'.hand.position';actual=tuple(sample['measured'][endpoint])
                        error=value_error(actual,initial[endpoint],'vector');assert error<=.002
                        maximum('wrist_edit_hand_path_error_m',error)
                        twist=side+'.forearm.twist';error=abs(sample['measured'][twist]-initial[twist]);assert error<=.5
                        maximum('wrist_edit_forearm_twist_error_deg',error)
                    if id=='forearm.twist':
                        for suffix in ('flexion','deviation'):
                            key=side+'.wrist.'+suffix;error=abs(sample['measured'][key]-initial[key]);assert error<=.5
                            maximum('forearm_twist_wrist_bend_error_deg',error)
                for clearance in sample.get('arm_clearance_m',{}).values():
                    maximum('body_penetration_m',max(0,-clearance));assert clearance>=-.003
                for key in ('head.orientation','object_root.position','object_root.orientation'):
                    spec=controls[key];actual=sample['measured'][key]
                    actual=tuple(actual) if isinstance(actual,list) else actual
                    error=value_error(actual,initial[key],spec.value_shape)
                    assert error<=(.002 if spec.unit=='metre' else .5)
                    maximum(key.replace('.','_')+'_drift',error)
            if id=='wrist.circle' or id=='hand.trace' and parameters.get('path')=='circle':
                first,last=r['samples'][0],r['samples'][-1]
                assert set(first['contacts'])==set(last['contacts'])
                active=('left','right') if parameters['side']=='both' else (parameters['side'],)
                for side in active:
                    endpoint=side+'.hand.position';error=value_error(tuple(first['measured'][endpoint]),tuple(last['measured'][endpoint]),'vector')
                    assert error<=.01;maximum('cycle_seam_endpoint_m',error)
                    for key in (side+'.upper_arm.orientation',side+'.hand.orientation'):
                        a,b=first['measured'][key],last['measured'][key]
                        error=value_error(tuple(a),tuple(b),'quaternion');assert error<=3
                        maximum('cycle_seam_orientation_deg',error)
                        before=angular_velocity(a,r['samples'][1]['measured'][key])
                        after=angular_velocity(r['samples'][-2]['measured'][key],b)
                        error=math.dist(before,after);assert error<=10
                        maximum('cycle_velocity_delta_deg_s',error)
            for key,value in r['review']['metrics'].items():
                if isinstance(value,(int,float)) and key not in ('frames','semantic_frames'):maximum(key,value)
            rows[name]={'id':id,'frames':r['frames'],'max_tracking_error':sample_max,'motion_sha256':digest(baked),'motion_mtime_ns':baked.stat().st_mtime_ns}
        if not available:assert not pending,(rig,'missing current numeric evidence',pending)
        result[rig]={'passed_cases':len(rows),'pending':pending,'samples':sum(x['frames'] for x in rows.values()),
                     'per_id':{id:[name for name,row in rows.items() if row['id']==id] for id in IDS},'maxima':maxima,'cases':rows}
    atomic_json(OUT/('numeric-progress.json' if available else 'validation-summary.json'),result)
    print(json.dumps({rig:{'passed':r['passed_cases'],'pending':len(r['pending']),'samples':r['samples'],'maxima':r['maxima']} for rig,r in result.items()}))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--available',action='store_true');parser.add_argument('--visual',action='store_true');args=parser.parse_args()
    audit(args.available,args.visual)
