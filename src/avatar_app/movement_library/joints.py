"""Stage 05.1a: pure calibrated head/neck movement builders, definition version 1."""
import math
from . import contracts as c
from .spatial import angle_rotation, projected_angles, multiply, inverse, look_rotation

IDS=('head.look','head.nod','head.shake','head.tilt','neck.lead')


def _seconds(value): return math.ceil(value*c.FPS-1e-9)/c.FPS


def _values(entry): return {v.control_id:v.value for v in entry.measured_controls}


def _control(profile,id):
    value=next((v for v in profile.controls if v.id==id),None)
    if value is None: c.fail('MISSING_CAPABILITY','Movement needs a calibrated quantity',control_id=id)
    return value


def _contacts(instance,entry,duration):
    return tuple(c.ContactEvent(instance.instance_id+'.'+a.anchor_id,(instance.instance_id,),a.anchor_id,a.surface_id,
        c.TimeInterval(0,duration),0,0,0) for a in entry.contact_anchors if a.anchor_id in entry.active_contacts)


def _track(instance,profile,id,index,start,end,a,b,*,aim=None):
    spec=_control(profile,id)
    kind='hold' if a==b else 'transition'
    curve=c.CurveSpec(kind,a,b,end-start,'smooth',aim)
    return c.TrackSpec(instance.instance_id+'.t'+str(index),(instance.instance_id,),id,spec.unit,spec.frames[0],
                       spec.value_shape,spec.dimensions,curve,'explicit' if a is not None else 'measured_entry',c.TimeInterval(start,end))


def _fragment(instance,entry,profile,paths,duration,landmarks,*,approximation=False):
    tracks=[]; goals=[]; requirements=[]
    values=_values(entry)
    for id,segments in paths.items():
        spec=_control(profile,id)
        requirements.append(c.StateRequirement(instance.instance_id+'.r'+str(len(requirements)),
            c.ControlValue(id,spec.unit,spec.frames[0],values[id]),.05))
        for start,end,a,b,aim in segments:
            track=_track(instance,profile,id,len(tracks),start,end,a,b,aim=aim)
            tracks.append(track)
            # Every authored destination, not merely the final return, must be measured.
            goal_time=max(start,end-1/c.FPS) if aim is not None and track.curve.kind=='hold' else end
            goals.append(c.GoalSpec(instance.instance_id+'.g'+str(len(goals)),instance.instance_id,
                c.ControlValue(id,spec.unit,spec.frames[0],b),c.TimeInterval(goal_time,goal_time),.1))
    if approximation: landmarks=(*landmarks,c.PhaseLandmark('head_only_approximation',0))
    return c.MotionFragment(instance.instance_id+'.fragment',(instance.instance_id,),tuple(requirements),duration,
        tuple(tracks),_contacts(instance,entry,duration),tuple(landmarks),(),tuple(goals))


def _path(initial,points,duration,hold,return_policy,delay=0):
    segments=[]; time=0; value=initial
    if delay:
        segments.append((0,delay,initial,initial,None)); time=delay
    for target in points:
        segments.append((time,time+duration,value,target,None)); time+=duration; value=target
        if hold:
            segments.append((time,time+hold,value,value,None)); time+=hold
    if return_policy=='return_to_entry':
        segments.append((time,time+duration,value,initial,None)); time+=duration
    return segments,time


def build_gesture(instance,entry,profile,surfaces):
    p={v.name:v.value for v in instance.parameters}; values=_values(entry)
    suffix={'head.nod':'pitch','head.shake':'yaw','head.tilt':'roll'}[instance.definition_id]
    id='head.'+suffix; initial=values[id]
    sign=-1 if p.get('direction')=='right' else 1
    points=[initial+sign*p['angle']]
    if instance.definition_id=='head.shake': points.append(initial-sign*p['angle'])
    path,end=_path(initial,points,_seconds(p['duration_s']),_seconds(p['hold_s']),p['return_policy'])
    return _fragment(instance,entry,profile,{id:path},end,(c.PhaseLandmark('arrival',_seconds(p['duration_s'])),c.PhaseLandmark('end',end)))


def _check_orientation(profile,entry,target,frame):
    values=_values(entry)
    local=angle_rotation(values['head.pitch'],values['head.yaw'],values['head.roll'])
    current=values['head.orientation' if frame=='world' else 'head.torso_orientation']
    parent=multiply(current,inverse(local))
    requested=projected_angles(multiply(inverse(parent),target))
    for suffix,value in requested.items():
        limit=next(v for v in profile.joint_limits if v.control_id=='head.'+suffix)
        if not limit.minimum<=value<=limit.maximum:
            c.fail('INVALID_PARAMETER','Look target is outside the current head-only angular envelope; torso will not be moved',
                   control_id=limit.control_id,details={'requested_deg':value,'minimum':limit.minimum,'maximum':limit.maximum})


def build_look(instance,entry,profile,surfaces):
    p={v.name:v.value for v in instance.parameters}; values=_values(entry)
    world=p['frame']=='world'
    if world:
        if p['target'] is None: c.fail('INVALID_PARAMETER','World look requires an explicit world target point')
        if any(k in instance.explicit_parameters for k in ('yaw','pitch')):
            c.fail('INVALID_PARAMETER','World look takes a point; omit torso yaw/pitch parameters')
        position=values.get('head.position')
        if position is None: c.fail('MISSING_CAPABILITY','World look requires head-aim profile v2')
        distance=sum((a-b)**2 for a,b in zip(position,p['target']))**.5
        if not .25<=distance<=10: c.fail('INVALID_PARAMETER','World target must be 0.25..10 metres from the measured head')
        target=look_rotation(position,p['target']); id='head.orientation'
    else:
        if p['target'] is not None: c.fail('INVALID_PARAMETER','A world target requires frame=world')
        target=angle_rotation(p['pitch'],p['yaw']); id='head.torso_orientation'
    _control(profile,id)
    _check_orientation(profile,entry,target,p['frame'])
    initial=values[id]; d=_seconds(p['duration_s']); hold=_seconds(p['hold_s'])
    aim=p['target'] if world else None
    path=[(0,d,initial,target,aim)]; end=d
    if world and p['return_policy']=='return_to_entry': hold=max(hold,1/c.FPS)
    if hold:
        path.append((end,end+hold,target,target,aim)); end+=hold
    if p['return_policy']=='return_to_entry':
        path.append((end,end+d,None if world else target,initial,None)); end+=d
    return _fragment(instance,entry,profile,{id:path},end,(c.PhaseLandmark('arrival',d),c.PhaseLandmark('end',end)))


def build_neck_lead(instance,entry,profile,surfaces):
    p={v.name:v.value for v in instance.parameters}; values=_values(entry)
    capable='anatomy.neck' in profile.capabilities
    approx=p['neck_policy']=='head_only'
    if not capable and not approx:
        c.fail('MISSING_CAPABILITY','Neck articulation is unavailable; explicitly request neck_policy=head_only for the approximation',
               details={'missing':['anatomy.neck'],'approximation':'head_only'})
    paths={}; duration=_seconds(p['duration_s']); hold=_seconds(p['hold_s']); delay=8/c.FPS if not approx else 0
    # A lead is one authored motion with a stagger, not a general composition operator.
    for suffix in ('yaw','pitch'):
        for chain,fraction,offset in (('head',1 if approx else 1-p['neck_share'],delay),('neck',p['neck_share'],0)):
            if chain=='neck' and approx: continue
            id=chain+'.'+suffix
            initial=values[id]; target=initial+p[suffix]*fraction
            paths[id]=[(0,offset,initial,initial,None)] if offset else []
            paths[id].append((offset,offset+duration,initial,target,None))
            arrival=duration+delay
            if offset+duration<arrival+hold:
                paths[id].append((offset+duration,arrival+hold,target,target,None))
            if p['return_policy']=='return_to_entry':
                paths[id].append((arrival+hold,arrival+hold+duration,target,initial,None))
    end=duration+delay+hold+(duration if p['return_policy']=='return_to_entry' else 0)
    return _fragment(instance,entry,profile,paths,end,(c.PhaseLandmark('head_start',delay),
        c.PhaseLandmark('arrival',duration+delay),c.PhaseLandmark('end',end)),approximation=approx)


def _number(name,unit,default,minimum,maximum):
    return c.ParameterSpec(name,'number',unit,None,False,True,default,minimum,maximum)


def _enum(name,default,choices):
    return c.ParameterSpec(name,'enum','unitless',None,False,True,default,enum_values=choices)


BUILDERS={'joints.look.v1':build_look,'joints.gesture.v1':build_gesture,'joints.neck_lead.v1':build_neck_lead}


def register_head_neck(catalog,*,head_only=False):
    from .registry import register_movement
    angular=tuple('measure.head.'+s for s in ('yaw','pitch','roll'))
    for id in IDS:
        default_return='preserve_end' if id=='head.look' else 'return_to_entry'
        common=(_number('duration_s','second',1,.8,3),_number('hold_s','second',.2,0,1),
                _enum('return_policy',default_return,('preserve_end','return_to_entry')))
        if id=='head.look':
            params=(_number('yaw','degree',25,-60,60),_number('pitch','degree',0,-40,40),
                _enum('frame','torso',('torso','world')),
                c.ParameterSpec('target','vector','metre','world',False,True,None,-20,20,dimensions=3,nullable=True))+common
            caps=angular+('measure.head.orientation','measure.head.torso_orientation','measure.head.position')
            builder='joints.look.v1'; chains=('head',)
        elif id=='neck.lead':
            params=(_number('yaw','degree',30,-50,50),_number('pitch','degree',0,-30,30),
                _number('neck_share','unitless',.4,.2,.6),_enum('neck_policy','require_neck',('require_neck','head_only')))+common
            caps=angular if head_only else angular+('anatomy.neck','measure.neck.yaw','measure.neck.pitch','measure.neck.roll')
            builder='joints.neck_lead.v1'; chains=('head',) if head_only else ('head','neck')
        else:
            params=(_number('angle','degree',20,-35 if id!='head.shake' else 0,35),)+common
            if id=='head.shake': params+=(_enum('direction','left',('left','right')),)
            caps=angular; builder='joints.gesture.v1'; chains=('head',)
        tags=('head_neck','single_cycle')+(('head_only_approximation_requires_opt_in',) if head_only and id=='neck.lead' else ())
        definition=c.MovementDefinition(id,1,'joint',id+'; calibrated measured entry, explicit timing/return and capability-scoped execution',
            params,caps,(),chains,(),(),builder,tags,('arrival','end'),default_return)
        register_movement(definition,catalog)
    return catalog


def catalog_for_profile(profile):
    """Profile-scoped neck fallback is explicit metadata, never fake anatomy."""
    from .registry import Catalog
    return register_head_neck(Catalog(BUILDERS),head_only='anatomy.neck' not in profile.capabilities)
