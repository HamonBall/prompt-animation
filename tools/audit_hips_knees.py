"""Independent typed-track and measured leg evidence audit; never rebuild motion."""
import sys,json,math,argparse
from pathlib import Path
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.legs import IDS
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.compiler import instantiate_movement,build_fragment,prepare_fragment,sample_motion,ExecutionCursor,value_error,supporting_chains
from avatar_app.movement_library.registry import validate_snapshot,parameter_schema
from avatar_app.motion import Surface
from hips_knees_cases import cases
from tools.artifact_store import atomic_json,digest
from tools.artifact_bundle import validate_manifest
from tools.legs_evidence import OUT,runtime,numeric_valid
parser=argparse.ArgumentParser()
parser.add_argument('--saved-playback',action='store_true')
parser.add_argument('--case',help='Check this case on both rigs without publishing a full audit')
args=parser.parse_args()
if args.case and args.case not in {name for name,_,_,_ in cases()}:
    parser.error('unknown case')
summary={'passed':False,'cases':{},'samples':0,'per_id':{id:{'cases':0,'samples':0} for id in IDS},'runtime_lock_sha256':runtime()}
maximum={'tracking_deg':0,'tracking_m':0,'unrelated_deg':0,'unrelated_m':0,'floor_penetration_m':0,'contact_m':0,
         'independent_knee_error_deg':0,'native_speed_deg_s':0,'native_acceleration_deg_s2':0,'object_root_change':0}


def distance(a,b):return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))


def geometric_knee(points):
    a=tuple(y-x for x,y in zip(points[0],points[1]));b=tuple(y-x for x,y in zip(points[1],points[2]))
    norm=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(a,b))/norm))))


for rig in ('demo','mixamo'):
    base=OUT/rig;p=c.loads(c.AvatarProfile,(base/'profile.json').read_text());cat=catalog_for_profile(p)
    specs={v.id:v for v in p.controls};joints={v.semantic_id:v for v in p.rest_to_semantic_mappings}
    assert json.loads((base/'schemas.json').read_text())=={id:parameter_schema(cat.definitions[id]) for id in IDS}
    for name,id,parameters,pose in cases():
        if args.case and name!=args.case:continue
        out=base/name;assert numeric_valid(out),out
        manifest,asset,motion=validate_manifest(out);result=json.loads((out/'result.json').read_text())
        if args.saved_playback:
            review=json.loads((out/'saved-playback-review.json').read_text());assert review['passed']
            assert review['motion_sha256']==digest(motion) and review['motion_mtime_ns']==motion.stat().st_mtime_ns
            assert review['result_sha256']==digest(out/'result.json') and review['raw_sha256']==digest(out/'saved-rotations.json')
            assert review['validator_sha256']==digest(ROOT/'tools/hips_knees_playback.py') and review['runtime_lock_sha256']==runtime()
            raw=json.loads((out/'saved-rotations.json').read_text());assert len(raw)==result['frames']
            from avatar_app.movement_library.spatial import multiply,inverse
            limits={v.control_id:v for v in p.joint_limits}
            residual=0
            for frame,row in zip(raw,result['samples']):
                for side in ('left','right'):
                    delta=multiply(multiply(inverse(tuple(frame['rotations']['pelvis_semantic'])),tuple(frame['rotations'][side+'.thigh'])),inverse(joints[side+'.thigh'].rest_to_semantic.orientation))
                    if delta[0]<0:delta=tuple(-x for x in delta)
                    for suffix in ('flexion','abduction','rotation'):
                        key=side+'.hip.'+suffix;axis=limits[key].positive_axis
                        angle=math.degrees(2*math.atan2(sum(a*b for a,b in zip(delta[1:],axis)),delta[0]))
                        residual=max(residual,abs(angle-row['measured'][key]));assert abs(angle-row['measured'][key])<.01
            summary['cases'][rig+'/'+name]={'frames':result['frames'],'hip_projection_residual_deg':residual,'review_sha256':digest(out/'saved-playback-review.json')}
            summary['samples']+=result['frames'];continue
        e=c.loads(c.MotionStateSnapshot,(out/'entry.json').read_text());validate_snapshot(e,p)
        i=instantiate_movement(id,parameters,instance_id='legs.1',profile=p,entry_state=e,catalog=cat)
        f=build_fragment(i,e,p,(Surface(),),cat);x=prepare_fragment(f,e,p)
        assert i==c.loads(c.MovementInstance,(out/'instance.json').read_text())
        assert f==c.loads(c.MotionFragment,(out/'fragment.json').read_text())
        assert x==c.loads(c.ExecutableMotion,(out/'executable.json').read_text())
        assert result['frames']==len(result['samples'])==math.ceil(x.duration_s*30)+1
        entry={v.control_id:v.value for v in e.measured_controls};cursor=ExecutionCursor();previous=e
        owned={specs[t.control_id].chain for t in x.tracks}|set(supporting_chains(t.control_id for t in x.tracks))
        def is_owned(chain):
            while chain is not None:
                if chain in owned:return True
                chain=joints[chain].parent_id
            return False
        for n,row in enumerate(result['samples']):
            assert row['frame']==n+1 and not row['violations'];time_s=min(x.duration_s,n/30)
            target=sample_motion(x,time_s,previous,cursor);expected={v.control_id:v.value for v in target.controls}
            assert set(expected)==set(row['targets'])
            values={key:tuple(v) if isinstance(v,list) else v for key,v in row['measured'].items()}
            for key,value in expected.items():
                saved=row['targets'][key];saved=tuple(saved) if isinstance(saved,list) else saved
                assert value_error(value,saved,specs[key].value_shape)<1e-6
                error=value_error(values[key],value,specs[key].value_shape)
                field='tracking_m' if specs[key].unit=='metre' else 'tracking_deg';maximum[field]=max(maximum[field],error)
                assert error<=(.01 if specs[key].unit=='metre' else 3)
            assert set(row['checked_goal_ids'])=={g.goal_id for g in target.expected_goals}
            for goal in target.expected_goals:
                assert value_error(values[goal.target.control_id],goal.target.value,specs[goal.target.control_id].value_shape)<=goal.tolerance
            for key,value in values.items():
                if is_owned(specs[key].chain):continue
                error=value_error(value,entry[key],specs[key].value_shape)
                field='unrelated_m' if specs[key].unit=='metre' else 'unrelated_deg';maximum[field]=max(maximum[field],error)
                assert error<=(.002 if specs[key].unit=='metre' else .5 if specs[key].unit=='degree' or specs[key].value_shape=='quaternion' else .008726535)
            for side in ('left','right'):
                error=abs(geometric_knee(row['leg_points'][side])-values[side+'.knee.flexion'])
                maximum['independent_knee_error_deg']=max(maximum['independent_knee_error_deg'],error);assert error<.01
            for key in ('object_root.position','object_root.orientation'):
                error=value_error(values[key],entry[key],specs[key].value_shape);maximum['object_root_change']=max(maximum['object_root_change'],error);assert error<.0001
            maximum['floor_penetration_m']=max(maximum['floor_penetration_m'],max(0,-row['floor_m']));assert row['floor_m']>=-.003
            for error in row['contacts'].values():maximum['contact_m']=max(maximum['contact_m'],error);assert error<=.025
            assert row['leg_clearance_m'] is not None and row['leg_clearance_m']>=-.003
            active=tuple(key.split('_')[0]+'.sole' for key in row['contacts'])
            previous=replace(e,captured_time_s=time_s,root_transform=c.Transform(values['pelvis.position'],values['pelvis.orientation'],'world','metre'),
                measured_controls=tuple(c.ControlValue(key,specs[key].unit,specs[key].frames[0],value) for key,value in values.items()),
                active_contacts=active,contact_anchors=tuple(a for a in e.contact_anchors if a.anchor_id in active))
            validate_snapshot(previous,p)
        for native,field,limit in (('joint_speed_deg_s','native_speed_deg_s',360),('joint_acceleration_deg_s2','native_acceleration_deg_s2',3000)):
            value=result['review']['metrics'][native];maximum[field]=max(maximum[field],value);assert value<=limit
        if id=='knee.pulse':
            arrival=next(row for row in result['samples'] if abs(row['time_s']-parameters.get('duration_s',1.5))<1e-8)
            assert all(arrival['measured'][side+'.knee.flexion']>entry[side+'.knee.flexion']+.5 for side in ('left','right')),'Pelvis motion did not produce the declared supported knee bend'
        summary['cases'][rig+'/'+name]={'frames':result['frames'],'definition_id':id,'fixture':pose,'motion_sha256':digest(motion),
            'motion_mtime_ns':motion.stat().st_mtime_ns,'result_sha256':digest(out/'result.json'),'native_process_sha256':digest(out/'native-process.json')}
        summary['samples']+=result['frames'];summary['per_id'][id]['cases']+=1;summary['per_id'][id]['samples']+=result['frames']
        for field,value in (('max_tracking_deg',max((error for row in result['samples'] for key,error in row['tracking_errors'].items() if specs[key].unit=='degree' or specs[key].value_shape=='quaternion'),default=0)),
                            ('native_speed_deg_s',result['review']['metrics']['joint_speed_deg_s']),
                            ('native_acceleration_deg_s2',result['review']['metrics']['joint_acceleration_deg_s2']),
                            ('contact_m',result['review']['metrics']['contact_error_m'])):
            summary['per_id'][id][field]=max(summary['per_id'][id].get(field,0),value)
summary.update(passed=True,maxima=maximum,case_count=len(summary['cases']),validator_sha256=digest(Path(__file__)))
if not args.case:
    atomic_json(OUT/('saved-playback-summary.json' if args.saved_playback else 'validation-summary.json'),summary)
print('LEGS_INDEPENDENT_AUDIT_PASSED','saved_playback' if args.saved_playback else 'numeric',summary['case_count'],summary['samples'],maximum,flush=True)
