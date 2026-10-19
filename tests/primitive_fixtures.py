"""Test-only movement builders; never added to the application catalog."""
from dataclasses import replace
import json
from pathlib import Path
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library import registry as r
from avatar_app.movement_library.compiler import instantiate_movement, build_fragment, prepare_fragment
from avatar_app.motion import Surface

ROOT=Path(__file__).parent/'fixtures/movement_fragments/v1'
LEGACY_BASELINE='7fbec2c12a6d9312835125d68cadba44f0bbf277'


def carry_contacts(instance,entry,duration):
    return tuple(c.ContactEvent(instance.instance_id+'.'+a.anchor_id,(instance.instance_id,),a.anchor_id,a.surface_id,
        c.TimeInterval(0,duration),0,0,0) for a in entry.contact_anchors if a.anchor_id in entry.active_contacts)


def head_builder(instance,entry,profile,surfaces):
    params={p.name:p.value for p in instance.parameters}
    angle,duration=params['angle'],params['duration_s']
    control=next(v for v in profile.controls if v.id=='head.yaw')
    frame=control.frames[0]
    source=(instance.instance_id,)
    prefix=instance.instance_id
    tracks=(
        c.TrackSpec(prefix+'.entry',source,'head.yaw','degree',frame,'scalar',1,
                    c.CurveSpec('hold',None,None,.2),'measured_entry',c.TimeInterval(0,.2)),
        c.TrackSpec(prefix+'.turn',source,'head.yaw','degree',frame,'scalar',1,
                    c.CurveSpec('transition',None,angle,duration,'smooth'),'measured_entry',c.TimeInterval(.2,.2+duration)),
        c.TrackSpec(prefix+'.hold',source,'head.yaw','degree',frame,'scalar',1,
                    c.CurveSpec('hold',angle,angle,.2),'explicit',c.TimeInterval(.2+duration,.4+duration)))
    contacts=carry_contacts(instance,entry,duration+.4)
    goal=c.GoalSpec(prefix+'.goal','test.clause',c.ControlValue('head.yaw','degree',frame,angle),
                    c.TimeInterval(.2+duration,.4+duration),.1)
    return c.MotionFragment(prefix+'.fragment',source,(),duration+.4,tracks,contacts,
                             (c.PhaseLandmark('arrival',duration+.2),),(),(goal,))


def reach_builder(instance,entry,profile,surfaces):
    values={p.name:p.value for p in instance.parameters}; source=(instance.instance_id,)
    track=c.TrackSpec(instance.instance_id+'.reach',source,'left.hand.position','metre','world','vector',3,
        c.CurveSpec('transition',None,values['target'],1,'smooth'),'measured_entry',c.TimeInterval(0,1))
    goal=c.GoalSpec(instance.instance_id+'.goal','test.clause',
                    c.ControlValue(track.control_id,'metre','world',values['target']),c.TimeInterval(1,1),.01)
    return c.MotionFragment(instance.instance_id+'.fragment',source,(),1,(track,),carry_contacts(instance,entry,1),(),(),(goal,))


def make_catalog():
    catalog=r.Catalog({'test.head_builder':head_builder,'test.reach_builder':reach_builder})
    r.register_movement(c.MovementDefinition('test.head_transition',1,'joint','Test-only calibrated head transition',
        (c.ParameterSpec('angle','number','degree',None,False,True,25,-60,60),
         c.ParameterSpec('duration_s','number','second',None,False,True,1.2,.4,4)),
        ('measure.head.yaw',),(),('head',),(),(),'test.head_builder',('test_only',)),catalog)
    r.register_movement(c.MovementDefinition('test.hand_target',1,'limb','Test-only endpoint validation',
        (c.ParameterSpec('target','vector','metre','world',True,False,None,-20,20,dimensions=3),),
        ('measure.left.hand.position',),(),('left.upper_arm','left.forearm','left.wrist'),(),(),
        'test.reach_builder',('test_only',)),catalog)
    return catalog


def executable(profile,entry,*,id='test.head_transition',parameters=None,instance_id='preview.1'):
    catalog=make_catalog()
    instance=instantiate_movement(id,parameters or {},instance_id=instance_id,profile=profile,entry_state=entry,catalog=catalog)
    fragment=build_fragment(instance,entry,profile,(Surface(),),catalog)
    return instance,fragment,prepare_fragment(fragment,entry,profile)


def generate():
    profile=c.loads(c.AvatarProfile,(Path(__file__).parent/'fixtures/rig_profiles/demo.json').read_text(encoding='utf-8'))
    values=[]
    for control in profile.controls:
        if control.value_shape=='scalar': value=0
        elif control.value_shape=='quaternion': value=(1,0,0,0)
        elif control.id.endswith('.direction'): value=(0,1,0)
        else: value=(0,0,1)
        values.append(c.ControlValue(control.id,control.unit,control.frames[0],value))
    entry=c.MotionStateSnapshot(profile.avatar_id,profile.version,1,0,
        c.Transform((0,0,1),(1,0,0,0),'world','metre'),tuple(values),(),())
    instance,fragment,motion=executable(profile,entry)
    files={'entry-snapshot.json':c.to_dict(entry),'instance.json':c.to_dict(instance),
           'fragment.json':c.to_dict(fragment),'executable.json':c.to_dict(motion),
           'entry-neutral.json':{'schema_version':1,'controls':{},'contact':'none'},
           'entry-bent-turned.json':{'schema_version':1,'controls':{'root_yaw':90,'torso_pitch':15,
                'head_pitch':10,'head_yaw':-20,'left_arm_elevation':45,'left_forearm_elevation':80,
                'left_forearm_azimuth':60},'contact':'none'}}
    bad=c.to_dict(fragment); bad['tracks'][1]['curve']['end_value']=True
    files['invalid-number.json']=bad
    bad=c.to_dict(fragment); bad['tracks']*=86
    files['over-budget.json']=bad
    bad=c.to_dict(fragment); bad['tracks'][0]['frame']='camera'
    files['invalid-frame.json']=bad
    files['manifest.json']={'schema_version':1,'api_version':1,'legacy_source_revision':LEGACY_BASELINE,
        'record_fixtures':{'entry-snapshot.json':'MotionStateSnapshot','instance.json':'MovementInstance',
                           'fragment.json':'MotionFragment','executable.json':'ExecutableMotion'},
        'entry_setup_fixtures':['entry-neutral.json','entry-bent-turned.json'],
        'invalid_fixtures':{'invalid-number.json':'INVALID_SCHEMA','invalid-frame.json':'INVALID_PARAMETER',
                            'over-budget.json':'RESOURCE_LIMIT'},
        'bounds':{'fps':c.FPS,'max_seconds':c.MAX_SECONDS,'max_samples':c.MAX_SAMPLES,
                  'max_tracks':c.MAX_TRACKS,'max_contacts':c.MAX_CONTACTS},
        'catalog':'test-only; production catalog remains empty'}
    ROOT.mkdir(parents=True,exist_ok=True)
    for name,value in files.items():
        (ROOT/name).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')
    print('Generated',len(files),'single-fragment fixtures')


if __name__=='__main__': generate()
