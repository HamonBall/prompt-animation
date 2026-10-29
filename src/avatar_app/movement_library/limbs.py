"""Stage 05.2 finite shoulder and arm movements through the shared bridge."""
from dataclasses import replace
import math
from . import contracts as c
from .joints import _number,_enum,_path,_fragment,_seconds
from .spatial import rotate,multiply,normalize
from .curves import axis_rotation,arc,line,tangent_rotation_axes

IDS=('shoulder.shrug','shoulder.reach','shoulder.roll','arm.raise','arm.sweep','arm.swing',
     'arm.circle','arm.fold','arm.reach','arm.stroke')
MARKER='shoulder_arm_v1:optional_clavicle_and_world_upper_arm_orientation'


def with_shoulders_v1(profile):
    from .torso_pelvis import with_pelvis_v1
    if profile.version==4 and MARKER in profile.calibration_provenance.evidence:return profile
    profile=with_pelvis_v1(profile)
    extra=[];limits=[];mapped={j.semantic_id:j for j in profile.rest_to_semantic_mappings}
    for side,other,sign in (('left','right',1),('right','left',-1)):
        chain=side+'.upper_arm';id=chain+'.orientation'
        extra.append(c.ControlSpec(id,'unitless','quaternion',4,('world',),chain,'measure.'+id))
        chain=side+'.clavicle'
        if chain not in mapped:continue
        for suffix,axis,lo,hi in (('elevation',(0,sign,0),-12,12),('protraction',(0,0,-sign),-12,12),('twist',(-sign,0,0),-12,12)):
            id=chain+'.'+suffix
            extra.append(c.ControlSpec(id,'degree','scalar',1,('joint:'+mapped[chain].parent_id,),chain,'measure.'+id))
            limits.append(c.JointLimit(id,lo,hi,0,axis,other+'.clavicle.'+suffix if other+'.clavicle' in mapped else None,1,
                'signed parent-relative calibrated swing/twist; mirrored elevation/protraction',lo,hi))
    return replace(profile,version=4,controls=profile.controls+tuple(extra),joint_limits=profile.joint_limits+tuple(limits),
        capabilities=tuple(sorted(set((*profile.capabilities,*(v.capability for v in extra))))),
        calibration_provenance=replace(profile.calibration_provenance,evidence=profile.calibration_provenance.evidence+(MARKER,)))


def shoulder_position(values,profile,side):
    lengths={v.id:v.value_m for v in profile.lengths}
    hand=values[side+'.hand.position']
    return tuple(hand[i]-sum(values[side+'.'+part+'.direction'][i]*lengths[side+'.'+part]
                 for part in ('upper_arm','forearm')) for i in range(3))


def build(instance,entry,profile,surfaces):
    p={v.name:v.value for v in instance.parameters};values={v.control_id:v.value for v in entry.measured_controls}
    sides=('left','right') if p['side']=='both' else (p['side'],)
    d=_seconds(p['duration_s']);hold=_seconds(p['hold_s']);paths={};landmarks=[];end=0
    basis=entry.root_transform.orientation if p['frame']=='entry_body' else (1,0,0,0)
    id=instance.definition_id
    for side in ('left','right'):
        if side not in sides and any(p.get(side+'_'+field) is not None for field in ('angle','target')):
            c.fail('INVALID_PARAMETER','Side-specific overrides must name an active side')
    if p.get('target') is not None and any(p.get(side+'_target') is not None for side in ('left','right')):
        c.fail('INVALID_PARAMETER','Choose one world target representation')
    def path(control,points,*,cycle=False):
        nonlocal end
        if cycle:
            segments,t=_path(values[control],[points[0]],d,hold,'preserve_end')
            step=max(1,math.ceil(d*c.FPS/(len(points)-1)))/c.FPS
            orbit_start=t
            for a,b in zip(points,points[1:]):segments.append((t,t+step,a,b,None));t+=step
            landmarks.append(c.PhaseLandmark('sweep',orbit_start))
            if p['return_policy']=='return_to_entry':segments.append((t,t+d,points[-1],values[control],None));t+=d
            paths[control]=segments
        else:paths[control],t=_path(values[control],points,d,hold,p['return_policy'])
        end=max(end,t)
    for side in sides:
        sign=1 if side=='left' else -1
        angle=p.get(side+'_angle') if p.get(side+'_angle') is not None else p.get('angle',0)
        if id.startswith('shoulder.'):
            if side+'.clavicle.elevation' not in values:c.fail('MISSING_CAPABILITY','Exact shoulder movement requires a mapped clavicle',details={'missing':[side+'.clavicle']})
            control=side+'.clavicle.'+('protraction' if id=='shoulder.reach' else 'elevation')
            if id=='shoulder.roll':
                # Start at the captured shoulder, lift, roll and lower back to
                # it. A centred orbit would depress relaxed arms into the torso.
                orbit=arc((.5,0,0),(-1,0,0),(0,1,0),.5,steps=32,
                          sweep_degrees=360 if angle>=0 else -360,phase_easing='smooth')
                for axis,index in (('elevation',0),('protraction',1)):
                    key=side+'.clavicle.'+axis
                    points=[values[key]+abs(angle)*v[index] for v in orbit]
                    points[0]=points[-1]=values[key]
                    path(key,points,cycle=True)
            else:path(control,[values[control]+angle])
        elif id in ('arm.reach','arm.fold','arm.stroke'):
            control=side+'.hand.position';initial=values[control]
            target=p.get(side+'_target') or p.get('target')
            if p.get('target') is not None and len(sides)==2:c.fail('INVALID_PARAMETER','Bilateral world reach needs left_target/right_target')
            shoulder=shoulder_position(values,profile,side)
            if target is None:
                if id=='arm.reach':
                    delta=rotate(basis,(0,p['distance_m'],0) if p['plane']=='forward' else (-sign*p['distance_m'],0,0))
                    toward=normalize(tuple(a-b for a,b in zip(initial,shoulder)))
                    target=tuple(a+b-t*.025*profile.height_m for a,b,t in zip(initial,delta,toward))
                else:
                    other=shoulder_position(values,profile,'right' if side=='left' else 'left')
                    center=tuple((a+b)/2 for a,b in zip(shoulder,other))
                    # A stroke sweeps toward the centre from its own working
                    # area. Reserve its full excursion before approaching;
                    # bilateral default paths must not swap through one another.
                    lateral=max(.12*profile.height_m,p['amplitude_m']+.04*profile.height_m) if id=='arm.stroke' else .08*profile.height_m
                    forward=.17 if id=='arm.stroke' else .20
                    delta=rotate(basis,(-sign*lateral,forward*profile.height_m,-.06*profile.height_m))
                    target=tuple(a+b for a,b in zip(center,delta))
            line(initial,target)
            lengths={v.id:v.value_m for v in profile.lengths}
            a,b=(lengths[side+'.'+part] for part in ('upper_arm','forearm'))
            points=[target]
            if id=='arm.stroke':
                offset=rotate(basis,(sign*p['amplitude_m'],-.025*profile.height_m,-.025*profile.height_m))
                points.append(tuple(a+b for a,b in zip(target,offset)))
            for point in points:
                distance=math.dist(point,shoulder)
                if not abs(a-b)+1e-5<distance<a+b-1e-5:c.fail('INVALID_PARAMETER','Endpoint path exceeds measured arm reach',control_id=control)
            path(control,points)
        else:
            control=side+'.upper_arm.orientation';initial=values[control]
            axis=rotate(basis,(0,0,-sign) if id=='arm.sweep' else (1,0,0) if p.get('plane','forward')=='forward' else (0,sign,0))
            if id=='arm.circle':
                # Entry is tangent to an outward orbit, rather than the centre
                # of an orbit that pulls relaxed arms through the torso. Signed
                # radius selects traversal direction; absolute frames close
                # exactly without accumulated upper-arm twist.
                orbit=arc((1,0,0),(-1,0,0),(0,1,0),1,steps=32,phase_easing='smooth')
                other='right' if side=='left' else 'left'
                outward=tuple(a-b for a,b in zip(shoulder_position(values,profile,side),shoulder_position(values,profile,other)))
                side_axis,forward_axis=tangent_rotation_axes(values[side+'.upper_arm.direction'],outward,rotate(basis,(0,1,0)))
                points=[multiply(axis_rotation(forward_axis,angle*v[1]),
                         multiply(axis_rotation(side_axis,abs(angle)*v[0]),initial)) for v in orbit]
                points[0]=points[-1]=initial;path(control,points,cycle=True)
            else:
                points=[multiply(axis_rotation(axis,angle),initial)]
                if id=='arm.swing':points.append(multiply(axis_rotation(axis,-angle),initial))
                path(control,points)
    # Synchronize bilateral endings with a hold, without scheduling other instances.
    for key,segments in paths.items():
        if segments[-1][1]<end:segments.append((segments[-1][1],end,segments[-1][3],segments[-1][3],None))
    phases=(c.PhaseLandmark('approach',0),c.PhaseLandmark('arrival',d),
            c.PhaseLandmark('recovery',end-d if p['return_policy']=='return_to_entry' else end),c.PhaseLandmark('end',end))
    if id in ('arm.stroke','arm.circle','shoulder.roll'):phases+=(c.PhaseLandmark('sweep',d+hold),)
    f=_fragment(instance,entry,profile,paths,end,phases)
    if id in ('arm.circle','shoulder.roll'):
        # Constant chord timing avoids a pause at every orbit vertex.
        f=replace(f,tracks=tuple(replace(t,curve=replace(t.curve,easing='linear')) if t.curve.duration_s<d else t for t in f.tracks))
    return replace(f,goals=tuple(replace(g,tolerance=.001) if g.target.unit=='metre' else g for g in f.goals))


BUILDERS={'limbs.shoulder_arm.v1':build}


def register_arms(catalog,profile=None):
    from .registry import register_movement
    for id in IDS:
        shoulder=id.startswith('shoulder.');endpoint=id in ('arm.fold','arm.reach','arm.stroke')
        bound=8 if id=='shoulder.roll' else 10 if shoulder else 20 if id=='arm.circle' else 150 if id=='arm.raise' else 110 if id=='arm.sweep' else 70
        default=4 if shoulder else 12 if id=='arm.circle' else 20
        angular=_number('angle','degree',default,-30 if id=='arm.raise' else -70 if id=='arm.sweep' else -bound,bound)
        params=(_enum('side','left',('left','right','both')),_enum('plane','forward',('forward','side')),
                _enum('frame','entry_body',('entry_body','world')),angular,
                replace(angular,name='left_angle',default=None,nullable=True),replace(angular,name='right_angle',default=None,nullable=True),
                _number('duration_s','second',1.5,1,3),_number('hold_s','second',.1,0,1),
                _enum('return_policy','return_to_entry',('return_to_entry','preserve_end')))
        if shoulder:
            params=tuple(replace(v,default='joint_parent',enum_values=('joint_parent',)) if v.name=='frame' else v for v in params if v.name!='plane')
        if id=='arm.circle':params=tuple(v for v in params if v.name!='plane')
        if id=='arm.sweep':params=tuple(replace(v,default='horizontal',enum_values=('horizontal',)) if v.name=='plane' else v for v in params)
        if endpoint:
            params=tuple(v for v in params if v.name not in ('angle','left_angle','right_angle') and (id=='arm.reach' or v.name!='plane'))
            if id=='arm.reach':params+=(_number('distance_m','metre',.02,-.08,.08),)
            if id=='arm.stroke':params+=(_number('amplitude_m','metre',.08,0,.16),)
            params+=tuple(c.ParameterSpec(name,'vector','metre','world',False,True,None,-20,20,dimensions=3,nullable=True)
                          for name in ('target','left_target','right_target'))
        # Side-specific optional anatomy is checked by the builder, so one missing
        # clavicle does not disable the available opposite side.
        caps=() if shoulder else ('measure.left.upper_arm.orientation','measure.right.upper_arm.orientation')
        chains=tuple(side+'.'+part for side in ('left','right') for part in (('clavicle',) if shoulder else ('upper_arm','forearm','wrist') if endpoint else ('upper_arm',)))
        if shoulder and profile is not None:
            available={control.chain for control in profile.controls}
            chains=tuple(chain for chain in chains if chain in available)
        tags=('shoulder_arm','coordinated_elbow' if endpoint else 'preserve_elbow_bend','optional_clavicle' if shoulder else 'finite_segment')
        phases=('approach','arrival','recovery','end')+(('sweep',) if id in ('arm.stroke','arm.circle','shoulder.roll') else ())
        register_movement(c.MovementDefinition(id,1,'joint' if shoulder else 'limb','Measured '+id+' with explicit ownership, entry and finite recovery',
            params,caps,(),chains,(),(),'limbs.shoulder_arm.v1',tags,phases,'return_to_entry'),catalog)
    return catalog

