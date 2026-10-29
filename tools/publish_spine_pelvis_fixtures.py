"""Publish measured Stage 05.1b examples after numeric and visual review."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment,prepare_fragment,value_error
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.registry import parameter_schema
from avatar_app.movement_library.torso_pelvis import IDS
from avatar_app.movement_library.spatial import rotate,inverse
from avatar_app.motion import Surface
from spine_pelvis_cases import cases
from tools.artifact_store import render_complete

SOURCE=ROOT/'artifacts/stages/05.1b';DEST=ROOT/'tests/fixtures/spine_pelvis/v1'


def publish():
    visual=json.loads((SOURCE/'visual-review.json').read_text())
    manifest={'schema_version':1,'definition_version':1,'profile_version':3,
        'source_revision':'7f84a4a379010b10259d84906f04d90199829229 plus Stage 05.1b working tree','rigs':{}}
    summary={}
    for rig in ('demo','mixamo'):
        source=SOURCE/rig;destination=DEST/rig;destination.mkdir(parents=True,exist_ok=True)
        profile=c.loads(c.AvatarProfile,(source/'profile.json').read_text());catalog=catalog_for_profile(profile)
        (destination/'profile.json').write_text(c.dumps(profile)+'\n')
        (destination/'schemas.json').write_text(json.dumps({id:parameter_schema(catalog.definitions[id]) for id in IDS},indent=2)+'\n')
        verified={};manifest['rigs'][rig]={};reviews=[]
        for name,id,parameters,pose in cases():
            path=source/name;result=json.loads((path/'result.json').read_text())
            assert result['review']['passed'],(rig,name)
            assert name in visual[rig]['reviewed_cases'],('Visual review missing',rig,name)
            assert render_complete(path,('front','side'),allow_legacy=True),('Stale or incomplete visual',name)
            for view in ('front','side'):
                assert len(list((path/view).glob('*.png')))==result['frames'],('Missing frames',name,view)
                assert (path/(view+'-sheet.png')).exists()
            entry=c.loads(c.MotionStateSnapshot,(path/'entry.json').read_text())
            instance=c.loads(c.MovementInstance,(path/'instance.json').read_text())
            fragment=c.loads(c.MotionFragment,(path/'fragment.json').read_text())
            assert build_fragment(instance,entry,profile,(Surface(),),catalog)==fragment,('Stale builder evidence',name)
            prepare_fragment(fragment,entry,profile)
            specs={v.id:v for v in profile.controls};initial={v.control_id:v.value for v in entry.measured_controls}
            metrics=dict(result['review']['metrics'])
            metrics['tracking_deg']=max((error for sample in result['samples'] for key,error in sample['tracking_errors'].items() if specs[key].unit=='degree' or specs[key].value_shape=='quaternion'),default=0)
            metrics['tracking_m']=max((error for sample in result['samples'] for key,error in sample['tracking_errors'].items() if specs[key].unit=='metre'),default=0)
            metrics['head_error_deg']=max(value_error(tuple(s['measured']['head.orientation']),initial['head.orientation'],'quaternion') for s in result['samples'])
            metrics['object_root_error_m']=max(value_error(tuple(s['measured']['object_root.position']),initial['object_root.position'],'vector') for s in result['samples'])
            metrics['object_root_error_deg']=max(value_error(tuple(s['measured']['object_root.orientation']),initial['object_root.orientation'],'quaternion') for s in result['samples'])
            metrics['unrelated_arm_deg']=max(abs(s['measured'][spec.id]-initial[spec.id]) for s in result['samples'] for spec in profile.controls
                if spec.value_shape=='scalar' and any(spec.chain==side+'.'+joint for side in ('left','right') for joint in ('upper_arm','forearm','wrist')))
            assert metrics['unrelated_arm_deg']<.5,(rig,name,'Unrelated arm changed')
            metrics['circle_radial_error_m']=0
            metrics['wave_peak_gap_error_frames']=0
            if id=='torso.wave' and next(v.value for v in instance.parameters if v.name=='angle')!=0:
                peaks=[]
                for control in ('torso.pitch','spine.mid.pitch','spine.upper.pitch'):
                    track=next(t for t in fragment.tracks if t.control_id==control and t.curve.kind=='transition')
                    near=[s['frame'] for s in result['samples'] if s['time_s']<=track.interval.end_s+1e-8 and abs(s['measured'][control]-track.curve.end_value)<.01]
                    assert near,(rig,name,'Wave peak not achieved',control)
                    peaks.append(min(near))
                metrics['wave_peak_gap_error_frames']=max(abs(b-a-8) for a,b in zip(peaks,peaks[1:]))
                assert metrics['wave_peak_gap_error_frames']<=1,(rig,name,'Wave order lost',peaks)
            if id=='pelvis.circle':
                orbit=[t for t in fragment.tracks if t.control_id=='pelvis.position' and t.curve.easing=='linear']
                radius=abs(next(v.value for v in instance.parameters if v.name=='distance_m'))
                start=min(t.interval.start_s for t in orbit);end=max(t.interval.end_s for t in orbit)
                for sample in result['samples']:
                    if not start-1e-8<=sample['time_s']<=end+1e-8:continue
                    delta=tuple(a-b for a,b in zip(sample['measured']['pelvis.position'],initial['pelvis.position']))
                    local=rotate(inverse(initial['pelvis.orientation']),delta)
                    metrics['circle_radial_error_m']=max(metrics['circle_radial_error_m'],abs((local[0]**2+local[1]**2)**.5-radius))
                assert metrics['circle_radial_error_m']<.001,(rig,name,'Circle deviates from orbit')
            metrics['frames']=result['frames'];verified[name]=metrics
        for id in IDS:
            names=[name for name,case_id,_,_ in cases() if case_id==id]
            maxima={key:max(verified[name][key] for name in names) for key in verified[names[0]]}
            records={kind:f'{rig}/{id}-{kind}.json' for kind in ('entry','instance','fragment')}
            for kind,path in records.items():
                (DEST/path).write_text((source/(id+'.default')/(kind+'.json')).read_text()+'\n')
            review=c.VerificationRecord(id,1,profile.avatar_id,profile.version,catalog.definitions[id].parameter_specs,
                (f'artifacts/stages/05.1b/{rig}/: '+','.join(names),
                 'Captured 90-degree heading, asymmetric arms/head and 9cm supported crouch; neutral torso cases also tested.',
                 'All frames measured and replayed; full-cycle front and side frame evidence with inspected contact sheets.',
                 'Entry-dependent reach and joint-limit rejection; circle uses 32 continuous linear chords with eased radial entry/exit.'),
                tuple(c.ParameterValue(key,value) for key,value in maxima.items()),'reviewed_for_envelope')
            catalog.register_review(review,profile);reviews.append(c.to_dict(review))
            manifest['rigs'][rig][id]={'records':records,'status':'reviewed_for_envelope','cases':names}
        (destination/'reviews.json').write_text(json.dumps(reviews,indent=2)+'\n')
        summary[rig]={'cases':len(verified),'frames':sum(v['frames'] for v in verified.values()),
            'maxima':{key:max(v[key] for v in verified.values()) for key in next(iter(verified.values()))},'per_case':verified}
        (source/'execution-review.json').write_text(json.dumps(verified,indent=2)+'\n')
    (DEST/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (SOURCE/'validation-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (SOURCE/'execution-review.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('PUBLISHED_SPINE_PELVIS_FIXTURES',sum(v['cases'] for v in summary.values()),'cases',sum(v['frames'] for v in summary.values()),'measured frames')


if __name__=='__main__':publish()
