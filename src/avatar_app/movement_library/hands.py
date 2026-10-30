"""Stage 05.3a: finite elbow, forearm, wrist and free hand mechanics.

Profile v5 is opt-in; old profile meanings and reviewed catalogs stay intact.
"""
from dataclasses import replace
import math
from . import contracts as c
from .joints import _number, _enum, _path, _fragment, _seconds
from .spatial import rotate, multiply, inverse
from .curves import arc, axis_rotation
from .limbs import shoulder_position, with_shoulders_v1

IDS=('elbow.flex','elbow.orient','forearm.twist','wrist.flex','wrist.deviate',
     'wrist.circle','hand.orient','hand.trace','hand.hold')
MARKER='hand_v1:geometric_elbow_and_root_referenced_plane'


def forearm_twist_sign(profile,side):
    """Supination sign from bind anatomy, independent of the current elbow bend."""
    axis=next(x.positive_axis for x in profile.joint_limits if x.control_id==side+'.forearm.twist')
    direction=next(x.position for x in profile.landmarks if x.id==side+'.forearm.tip')
    dot=sum(a*b for a,b in zip(axis,direction))
    if abs(dot)<1e-8:c.fail('MISSING_CAPABILITY','Forearm twist axis is not longitudinal')
    return 1 if dot>0 else -1


def with_hands_v1(profile):
    if profile.version==5 and MARKER in profile.calibration_provenance.evidence:return profile
    if profile.version>4:c.fail('VERSION_MISMATCH','Unsupported hand profile migration')
    p=with_shoulders_v1(profile);extra=[];limits=[]
    for side in ('left','right'):
        id=side+'.elbow.plane'
        extra.append(c.ControlSpec(id,'degree','scalar',1,('current_root',),side+'.forearm','measure.'+id))
        limits.append(c.JointLimit(id,-180,180,0,(0,1,0),None,1,
            'signed geometric pole angle about shoulder-to-wrist, root backward reference',-60,60))
        for suffix,unit,shape,dim in (('torso_position','metre','vector',3),('torso_orientation','unitless','quaternion',4)):
            id=side+'.hand.'+suffix
            extra.append(c.ControlSpec(id,unit,shape,dim,('current_torso',),side+'.wrist','measure.'+id))
    for suffix,unit,shape,dim in (('position','metre','vector',3),('orientation','unitless','quaternion',4)):
        id='torso_frame.'+suffix
        extra.append(c.ControlSpec(id,unit,shape,dim,('world',),'torso','measure.'+id))
    return replace(p,version=5,controls=p.controls+tuple(extra),joint_limits=tuple(
        replace(v,minimum=0,maximum=145,preferred_minimum=0,measurement_method='geometric unsigned segment angle; straight=0')
        if v.control_id.endswith('.elbow.flexion') else v for v in p.joint_limits)+tuple(limits),
        capabilities=tuple(sorted(set((*p.capabilities,*(v.capability for v in extra))))),
        calibration_provenance=replace(p.calibration_provenance,evidence=p.calibration_provenance.evidence+(MARKER,)))


def build(instance,entry,profile,surfaces):
    if profile.version!=5 or MARKER not in profile.calibration_provenance.evidence:
        c.fail('MISSING_CAPABILITY','Hand mechanics require calibrated profile v5')
    p={v.name:v.value for v in instance.parameters};v={x.control_id:x.value for x in entry.measured_controls}
    id=instance.definition_id;sides=('left','right') if p['side']=='both' else (p['side'],)
    paths={};linear_segments=set();d=_seconds(p['duration_s']);hold=_seconds(p['hold_s']);end=0
    def framed(side,base,selector):
        candidates=[]
        for prefix,frame in (('','world'),('entry_','entry_body'),('torso_','current_torso')):
            for key in (prefix+base,side+'_'+prefix+base):
                if p.get(key) is not None:candidates.append((p[key],frame))
        if len(candidates)>1:c.fail('CONSTRAINT_CONFLICT','Choose one explicitly framed '+base+' for each side')
        value,frame=candidates[0] if candidates else (None,p[selector])
        if candidates and selector in instance.explicit_parameters and p[selector]!=frame:
            c.fail('INVALID_PARAMETER','Frame selector conflicts with the spatial parameter frame')
        return value,frame
    def path(key,points,cycle=False):
        nonlocal end
        if key not in v:c.fail('MISSING_CAPABILITY','Required calibrated hand quantity unavailable',control_id=key)
        if cycle:
            step=math.ceil(d*30/32)/30
            segments=[(i*step,(i+1)*step,a,b,None) for i,(a,b) in enumerate(zip(points,points[1:]))]
            t=32*step
            if hold:segments.append((t,t+hold,points[-1],points[-1],None));t+=hold
        else:segments,t=_path(v[key],points,d,hold,p['return_policy'])
        paths[key]=segments;end=max(end,t)
    def orbit_path(key,points):
        nonlocal end
        segments,t=_path(v[key],[points[0]],d,hold,'preserve_end')
        step=math.ceil(d*30/(len(points)-1))/30
        for a,b in zip(points,points[1:]):
            linear_segments.add((key,round(t,8)));segments.append((t,t+step,a,b,None));t+=step
        if p['return_policy']=='return_to_entry':segments.append((t,t+d,points[-1],v[key],None));t+=d
        paths[key]=segments;end=max(end,t)
    for side in ('left','right'):
        if side not in sides and any(value is not None for key,value in p.items() if key.startswith(side+'_')):
            c.fail('INVALID_PARAMETER','Override names an inactive side')
    for side in sides:
        needs=(('hand.orientation','wrist.flexion','wrist.deviation') if id in ('hand.orient','hand.trace','hand.hold','elbow.orient') else
               ('wrist.flexion','wrist.deviation') if id.startswith('wrist.') else ('elbow.flexion','forearm.twist'))
        for suffix in needs:
            if side+'.'+suffix not in v:c.fail('MISSING_CAPABILITY','Required calibrated hand quantity unavailable',control_id=side+'.'+suffix)
        angle=p.get(side+'_angle') if p.get(side+'_angle') is not None else p.get('angle',0)
        if id in ('elbow.flex','forearm.twist','wrist.flex','wrist.deviate'):
            suffix={'elbow.flex':'elbow.flexion','forearm.twist':'forearm.twist','wrist.flex':'wrist.flexion','wrist.deviate':'wrist.deviation'}[id]
            path(side+'.'+suffix,[angle])
        elif id=='elbow.orient':
            if v[side+'.elbow.flexion']<3:c.fail('ENTRY_MISMATCH','A stationary-wrist plane edit needs at least 3 degrees of elbow bend')
            path(side+'.elbow.plane',[v[side+'.elbow.plane']+angle])
            path(side+'.hand.position',[v[side+'.hand.position']])
            path(side+'.hand.orientation',[v[side+'.hand.orientation']])
        elif id=='wrist.circle':
            orbit=arc((1,0,0),(-1,0,0),(0,1,0),1,steps=32,phase_easing='smooth')
            for index,suffix in enumerate(('flexion','deviation')):
                key=side+'.wrist.'+suffix
                points=[v[key]+angle*x[index] for x in orbit];points[0]=points[-1]=v[key]
                path(key,points,True)
        else:
            if id in ('hand.trace','hand.hold'):
                target,position_frame=framed(side,'target','position_frame')
                if any(p.get(prefix+'target') is not None for prefix in ('','entry_','torso_')) and len(sides)==2:
                    c.fail('INVALID_PARAMETER','Bilateral targets require independent left/right targets')
                origin=entry.root_transform.position;basis=entry.root_transform.orientation
                relative=position_frame=='current_torso'
                position_key=side+'.hand.'+('torso_position' if relative else 'position')
                if relative:origin=v['torso_frame.position'];basis=(1,0,0,0)
                if target is not None and position_frame=='entry_body':
                    target=tuple(a+b for a,b in zip(origin,rotate(basis,target)))
                target=target or v[position_key]
                points=[target]
                if id=='hand.trace':
                    if p['path']=='line':
                        offset=rotate(basis,(0,p['distance_m'],0));points=[tuple(a+b for a,b in zip(target,offset))]
                    else:
                        orbit=arc(target,rotate(basis,(1,0,0)),rotate(basis,(0,0,1)),abs(p['distance_m']),
                                  steps=16,sweep_degrees=(180 if p['path']=='arc' else 360)*(1 if p['distance_m']>=0 else -1),phase_easing='smooth')
                        # Tangent circle starts at the supplied wrist target.
                        points=[tuple(x[i]-rotate(basis,(abs(p['distance_m']),0,0))[i] for i in range(3)) for x in orbit]
                shoulder=shoulder_position(v,profile,side);lengths={x.id:x.value_m for x in profile.lengths}
                a,b=(lengths[side+'.'+part] for part in ('upper_arm','forearm'))
                for point in points:
                    world=tuple(a+b for a,b in zip(origin,rotate(v['torso_frame.orientation'],point))) if relative else point
                    dist=math.dist(world,shoulder)
                    if not abs(a-b)+1e-5<dist<=a+b+1e-5:c.fail('INVALID_PARAMETER','Hand target is unreachable',control_id=side+'.hand.position')
                    if p.get('flexion_deg') is not None:
                        actual=math.degrees(math.acos(max(-1,min(1,(dist*dist-a*a-b*b)/(2*a*b)))))
                        if abs(actual-p['flexion_deg'])>3:c.fail('CONSTRAINT_CONFLICT','Hard elbow flexion conflicts with wrist endpoint')
                if id=='hand.trace' and p['path']!='line':orbit_path(position_key,points)
                else:path(position_key,points)
                plane=p.get(side+'_elbow_plane_deg') if p.get(side+'_elbow_plane_deg') is not None else p.get('elbow_plane_deg')
                if plane is not None:
                    if v[side+'.elbow.flexion']<3:
                        if p['plane_policy']=='hard':c.fail('CONSTRAINT_CONFLICT','A hard elbow plane is undefined at a straight arm')
                    else:path(side+'.elbow.plane',[plane])
            orientation,orientation_frame=framed(side,'orientation','orientation_frame')
            if orientation is not None and any(key in instance.explicit_parameters for key in ('angle',side+'_angle')):
                c.fail('CONSTRAINT_CONFLICT','Choose a palm quaternion or an entry-relative roll angle')
            orientation_key=side+'.hand.'+('torso_orientation' if orientation_frame=='current_torso' else 'orientation')
            if any(p.get(prefix+'orientation') is not None for prefix in ('','entry_','torso_')) and len(sides)==2:
                c.fail('INVALID_PARAMETER','Bilateral palm orientations require independent targets')
            if orientation is not None:
                if orientation_frame=='entry_body':orientation=multiply(entry.root_transform.orientation,orientation)
                path(orientation_key,[orientation])
            elif id=='hand.orient':
                initial=v[orientation_key]
                path(orientation_key,[multiply(axis_rotation(rotate(initial,(0,1,0)),angle),initial)])
            else:path(orientation_key,[v[orientation_key]])
    for key,segments in paths.items():
        if segments[-1][1]<end:segments.append((segments[-1][1],end,segments[-1][3],segments[-1][3],None))
        paths[key]=[(round(a*c.FPS)/c.FPS,round(b*c.FPS)/c.FPS,x,y,aim) for a,b,x,y,aim in segments]
    end=round(end*c.FPS)/c.FPS
    f=_fragment(instance,entry,profile,paths,end,(c.PhaseLandmark('arrival',d),c.PhaseLandmark('end',end)))
    f=replace(f,tracks=tuple(replace(t,curve=replace(t.curve,easing='linear')) if (t.control_id,round(t.interval.start_s,8)) in linear_segments else t for t in f.tracks))
    if id=='wrist.circle':f=replace(f,tracks=tuple(replace(t,curve=replace(t.curve,easing='linear')) for t in f.tracks))
    return f


BUILDERS={'hands.mechanics.v1':build}


def register_hands(catalog,profile):
    from .registry import register_movement
    if profile.version!=5:return catalog
    for id in IDS:
        bounds={'elbow.flex':(0,130,45),'elbow.orient':(-45,45,20),'forearm.twist':(-179,179,45),
                'wrist.flex':(-60,60,20),'wrist.deviate':(-25,25,10),'wrist.circle':(-10,10,5),'hand.orient':(-150,150,30)}
        params=(_enum('side','left',('left','right','both')),_number('duration_s','second',1.5,1.5,3),
                _number('hold_s','second',.1,0,1),_enum('return_policy','return_to_entry',('return_to_entry','preserve_end')))
        if id in bounds:
            lo,hi,default=bounds[id];angle=_number('angle','degree',default,lo,hi)
            params+=(angle,replace(angle,name='left_angle',default=None,nullable=True),replace(angle,name='right_angle',default=None,nullable=True))
        if id.startswith('hand.'):
            params+=(_enum('orientation_frame','world',('world','entry_body','current_torso')),)
            params+=tuple(c.ParameterSpec(side+prefix+'orientation','quaternion','unitless',frame,False,True,None,dimensions=4,nullable=True)
                          for prefix,frame in (('','world'),('entry_','entry_body'),('torso_','current_torso')) for side in ('','left_','right_'))
        if id in ('hand.hold','hand.trace'):
            params+=(_enum('position_frame','world',('world','entry_body','current_torso')),)
            params+=tuple(c.ParameterSpec(side+prefix+'target','vector','metre',frame,False,True,None,-20,20,dimensions=3,nullable=True)
                          for prefix,frame in (('','world'),('entry_','entry_body'),('torso_','current_torso')) for side in ('','left_','right_'))
            params+=tuple(replace(_number(name,'degree',0,-180,180),default=None,nullable=True)
                          for name in ('elbow_plane_deg','left_elbow_plane_deg','right_elbow_plane_deg'))
            params+=(_enum('plane_policy','soft',('soft','hard')),
                     replace(_number('flexion_deg','degree',45,0,130),default=None,nullable=True))
        if id=='hand.trace':params+=(_enum('path','line',('line','arc','circle')),_number('distance_m','metre',.02,-.04,.04))
        parts=('wrist',) if id.startswith('wrist.') else ('forearm','wrist') if id in ('elbow.flex','forearm.twist','hand.orient') else ('upper_arm','forearm','wrist')
        chains=tuple(s+'.'+part for s in ('left','right') for part in parts)
        register_movement(c.MovementDefinition(id,1,'limb','Calibrated '+id+'; free space, independent sides',params,(),(),chains,(),(),
            'hands.mechanics.v1',('hand_mechanics','no_surface_attachment'),('arrival','end'),'return_to_entry'),catalog)
    return catalog
