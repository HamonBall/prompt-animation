"""Independent full-sample scalar/physical/preservation audit of saved results."""
import sys,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import build_fragment,prepare_fragment,sample_motion,ExecutionCursor,value_error
from avatar_app.movement_library.spatial import multiply,inverse
from avatar_app.motion import Surface
from finger_cases import cases
from tools.artifact_store import digest,input_identity,atomic_json
from tools.artifact_bundle import validate_manifest
from tools.fingers_provenance import producer_valid
from tools.fingers_runtime import validate as validate_runtime
OUT=ROOT/'artifacts/stages/05.3b';p=c.loads(c.AvatarProfile,(OUT/'mixamo/profile.json').read_text());catalog=catalog_for_profile(p)
controls={x.id:x for x in p.controls};limits={x.control_id:x for x in p.joint_limits};summary={'cases':{},'samples':0,'maxima':{}}
maxima={'tracking_deg':0,'unrelated_deg':0,'unrelated_m':0,'speed_deg_s':0,'acceleration_deg_s2':0,'floor_penetration_m':0,'contact_m':0}


def velocity(a,b):
    q=multiply(tuple(b),inverse(tuple(a)))
    if q[0]<0:q=tuple(-v for v in q)
    length=math.sqrt(sum(x*x for x in q[1:]));angle=2*math.atan2(length,q[0])
    return tuple(x/length*math.degrees(angle)*30 for x in q[1:]) if length>1e-12 else (0,0,0)


for name,id,parameters,pose in cases():
    out=OUT/'mixamo'/name;manifest,asset,motion=validate_manifest(out);r=json.loads((out/'result.json').read_text())
    assert r['review']['passed'] and r['stage_05_3b']['no_topology_or_rest_skeleton_change']
    assert manifest['inputs']==input_identity(out)
    assert producer_valid(out)
    entry=c.loads(c.MotionStateSnapshot,(out/'entry.json').read_text());instance=c.loads(c.MovementInstance,(out/'instance.json').read_text())
    fragment=c.loads(c.MotionFragment,(out/'fragment.json').read_text());motion_plan=c.loads(c.ExecutableMotion,(out/'executable.json').read_text())
    if pose!='sequence':assert build_fragment(instance,entry,p,(Surface(),),catalog)==fragment
    else:
        # Verify all authored baseline arrivals, including the open -> fist -> point transition.
        for time,gesture in ((1.5,'open'),(3.1,'fist'),(4.7,'point')):
            row=r['samples'][round(time*30)]
            for key,value in row['measured'].items():
                if '.finger.' not in key or not key.endswith('.curl'):continue
                digit=key.split('.')[2];expected=0 if gesture=='open' or gesture=='point' and digit=='index' else .72*(65 if digit=='thumb' else 90)
                assert abs(value-expected)<.1,(name,time,key,value,expected)
    assert prepare_fragment(fragment,entry,p)==motion_plan
    assert len(r['samples'])==math.ceil(motion_plan.duration_s*30)+1==r['frames']
    entry_values={x.control_id:x.value for x in entry.measured_controls};cursor=ExecutionCursor();previous=None;velocities={}
    selected={'.'.join(t.control_id.split('.')[:3]) for t in motion_plan.tracks}
    first=r['samples'][0]
    for row in r['samples']:
        goals=sample_motion(motion_plan,row['time_s'],entry,cursor)
        expected={x.control_id:x.value for x in goals.controls}
        assert set(expected)==set(row['targets']) and not row['violations']
        for key,target in expected.items():
            assert abs(target-row['targets'][key])<1e-7
            error=abs(row['measured'][key]-target);maxima['tracking_deg']=max(maxima['tracking_deg'],error);assert error<=3
        for key,value in row['measured'].items():
            if key in limits:assert limits[key].minimum<=value<=limits[key].maximum
            if key in expected:continue
            spec=controls[key];value=tuple(value) if isinstance(value,list) else value
            error=value_error(value,entry_values[key],spec.value_shape)
            if spec.unit=='metre':maxima['unrelated_m']=max(maxima['unrelated_m'],error);assert error<=.002
            elif spec.unit=='degree' or spec.value_shape=='quaternion':maxima['unrelated_deg']=max(maxima['unrelated_deg'],error);assert error<=.5
        penetration=max(0,-row['floor_m']);maxima['floor_penetration_m']=max(maxima['floor_penetration_m'],penetration);assert penetration<=.003
        for value in row['contacts'].values():maxima['contact_m']=max(maxima['contact_m'],value);assert value<=.025
        for value in row.get('arm_clearance_m',{}).values():assert value>=-.003
        for key,point in row['finger_tips'].items():
            if '.'.join(key.split('.')[:3]) in selected:continue
            error=math.dist(point,first['finger_tips'][key]);maxima['unrelated_m']=max(maxima['unrelated_m'],error);assert error<=.002
        for key,q in row['finger_rotations'].items():
            if '.'.join(key.split('.')[:3]) in selected:continue
            error=value_error(tuple(q),tuple(first['finger_rotations'][key]),'quaternion')
            maxima['unrelated_deg']=max(maxima['unrelated_deg'],error);assert error<=.5
        if previous:
            for key,q in row['finger_rotations'].items():
                v=velocity(previous['finger_rotations'][key],q);speed=math.sqrt(sum(x*x for x in v));maxima['speed_deg_s']=max(maxima['speed_deg_s'],speed);assert speed<=360
                if key in velocities:
                    acceleration=math.sqrt(sum((a-b)**2 for a,b in zip(v,velocities[key])))*30
                    maxima['acceleration_deg_s2']=max(maxima['acceleration_deg_s2'],acceleration);assert acceleration<=3000
                velocities[key]=v
        previous=row
    summary['samples']+=r['frames'];summary['cases'][name]={'frames':r['frames'],'motion_sha256':digest(motion),'motion_mtime_ns':motion.stat().st_mtime_ns,
        'manifest_sha256':digest(out/'preview-manifest.json'),'result_sha256':digest(out/'result.json')}
summary['maxima']=maxima;summary['passed']=True;summary['case_count']=len(cases())
summary['runtime_lock_sha256']=validate_runtime()
summary['validator_sources']={name:digest(ROOT/name) for name in ('tools/audit_fingers.py','tools/fingers_provenance.py','tools/fingers_runtime.py')}
atomic_json(OUT/'validation-summary.json',summary);print('FINGERS_AUDIT_PASSED',summary['case_count'],summary['samples'],maxima,flush=True)
