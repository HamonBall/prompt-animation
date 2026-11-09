"""Stage 05.4: finite leg motions with explicit free/support roles, profile 7."""
from dataclasses import replace
import math
from . import contracts as c
from .hands import with_hands_v1
from .joints import _enum,_number,_path,_fragment,_seconds
from .spatial import rotate,multiply,normalize
from .curves import axis_rotation

IDS=('hip.lift','hip.open_close','hip.rotate','leg.extend','leg.swing','knee.flex',
     'knee.lift','knee.orient','knee.pulse','leg.cross','leg.fold','leg.kick')
MARKER='leg_v1:geometric_knee_parent_hip_and_reachable_bend_plane'


def with_legs_v1(profile):
    if profile.version==7 and MARKER in profile.calibration_provenance.evidence:return profile
    if profile.version>6:c.fail('VERSION_MISMATCH','Unsupported leg profile migration')
    p=profile if profile.version in (5,6) else with_hands_v1(profile)
    controls=[];limits=[]
    for side,other,sign in (('left','right',1),('right','left',-1)):
        for suffix,chain,frame,axis,lo,hi in (
            ('hip.abduction','thigh','joint:pelvis',(0,sign,0),-25,40),
            ('hip.rotation','thigh','joint:pelvis',(0,0,sign),-60,60),
            ('knee.plane','shin','current_pelvis',(0,1,0),-180,180)):
            key=side+'.'+suffix
            controls.append(c.ControlSpec(key,'degree','scalar',1,(frame,),side+'.'+chain,'measure.'+key))
            limits.append(c.JointLimit(key,lo,hi,0,axis,other+'.'+suffix,1,
                'signed parent-relative swing/twist' if suffix.startswith('hip.') else
                'signed geometric pole about hip-to-ankle; pelvis-forward reference; undefined below 3 degrees',lo,hi))
    return replace(p,version=7,controls=p.controls+tuple(controls),joint_limits=tuple(
        replace(x,minimum=0,maximum=150,preferred_minimum=0,preferred_maximum=100,
                measurement_method='geometric unsigned thigh/shin segment angle; straight=0') if x.control_id.endswith('.knee.flexion') else x
        for x in p.joint_limits)+tuple(limits),
        capabilities=tuple(sorted(set((*p.capabilities,*(x.capability for x in controls))))),
        calibration_provenance=replace(p.calibration_provenance,evidence=p.calibration_provenance.evidence+(MARKER,)))


def hip_position(values,profile,side):
    lengths={x.id:x.value_m for x in profile.lengths}
    return tuple(values[side+'.foot.position'][i]-sum(values[side+'.'+part+'.direction'][i]*lengths[side+'.'+part]
                 for part in ('thigh','shin')) for i in range(3))


def reachable(values,profile,side,target):
    lengths={x.id:x.value_m for x in profile.lengths};a,b=(lengths[side+'.'+part] for part in ('thigh','shin'))
    distance=math.dist(hip_position(values,profile,side),target)
    if not abs(a-b)+1e-5<distance<=a+b+1e-5:
        c.fail('INVALID_PARAMETER','Foot target exceeds captured leg reach',control_id=side+'.foot.position',
               details={'distance_m':distance,'reach_m':a+b})


def build(instance,entry,profile,surfaces):
    if profile.version not in (7,8) or MARKER not in profile.calibration_provenance.evidence:
        c.fail('MISSING_CAPABILITY','Leg mechanics require calibrated profile 7')
    p={x.name:x.value for x in instance.parameters};v={x.control_id:x.value for x in entry.measured_controls}
    side=p['side'];other='right' if side=='left' else 'left';id=instance.definition_id
    d=_seconds(p['duration_s']);hold=_seconds(p['hold_s']);release= .2;paths={};end=0
    def path(key,points,delay=release):
        nonlocal end
        if key not in v:c.fail('MISSING_CAPABILITY','Leg quantity unavailable',control_id=key)
        paths[key],t=_path(v[key],points,d,hold,p['return_policy'],delay=delay);end=max(end,t)
    anchors={a.anchor_id:a for a in entry.contact_anchors}
    if id=='knee.pulse':
        if p['support']!='both_planted' or set(entry.active_contacts)!={'left.sole','right.sole'}:
            c.fail('ENTRY_MISMATCH','Supported knee pulse requires both captured planted soles')
        if any(v[s+'.knee.flexion']>70 for s in ('left','right')):
            c.fail('ENTRY_MISMATCH','Supported pulse requires an upright or shallow crouched entry')
        initial=v['pelvis.position'];target=tuple(x-(p['depth_m'] if i==2 else 0) for i,x in enumerate(initial))
        path('pelvis.position',[target],delay=0)
        for s in ('left','right'):
            shifted=dict(v)
            shifted[s+'.foot.position']=tuple(v[s+'.foot.position'][i]-(p['depth_m'] if i==2 else 0) for i in range(3))
            reachable(shifted,profile,s,v[s+'.foot.position'])
    else:
        if p['support']!='opposite_planted':c.fail('CONSTRAINT_CONFLICT','A free-leg movement cannot retain both planted feet')
        if other+'.sole' not in entry.active_contacts or other+'.sole' not in anchors:
            c.fail('ENTRY_MISMATCH','The opposite captured sole must support this free leg')
        required=('hip.flexion','hip.abduction','hip.rotation','knee.flexion','foot.position','foot.orientation')
        for suffix in required:
            if side+'.'+suffix not in v:c.fail('MISSING_CAPABILITY','Selected leg anatomy is unavailable',control_id=side+'.'+suffix)
        if abs(v[side+'.hip.flexion'])>80 or v[side+'.knee.flexion']>115:
            c.fail('ENTRY_MISMATCH','Free-leg entry exceeds the reviewed upright/raised/crouched envelope')
        key=lambda suffix:side+'.'+suffix
        angle=p.get('angle',0);basis=entry.root_transform.orientation;h=profile.height_m
        if id=='knee.orient':
            if v[key('knee.flexion')]<5:c.fail('ENTRY_MISMATCH','A fixed-foot knee plane edit needs at least 5 degrees bend')
            path(key('knee.plane'),[v[key('knee.plane')]+angle])
            path(key('foot.position'),[v[key('foot.position')]])
            path(key('foot.orientation'),[v[key('foot.orientation')]])
        elif id in ('leg.swing','leg.cross','leg.fold'):
            initial=v[key('foot.position')]
            offset=lambda delta:tuple(a+b for a,b in zip(initial,rotate(basis,delta)))
            lift=offset((0,.035*h,.13*h))
            if id=='leg.swing':
                delta=(0,p['distance_m'],0) if p['plane']=='forward' else ((-1 if side=='left' else 1)*p['distance_m'],0,0)
                center=p.get('target') or lift
                points=[lift,tuple(a+b for a,b in zip(center,rotate(basis,delta))),tuple(a-b for a,b in zip(center,rotate(basis,delta))),lift]
            elif id=='leg.cross':
                target=p.get('target') or offset(((1 if side=='left' else -1)*p['distance_m'],.18*h,.16*h))
                points=[lift,target]+([lift] if p['return_policy']=='return_to_entry' else [])
            else:
                target=p.get('target') or offset((0,-p['distance_m'],.20*h))
                points=[lift,target]+([lift] if p['return_policy']=='return_to_entry' else [])
            for point in points:reachable(v,profile,side,point)
            path(key('foot.position'),points)
            pitch=-25 if id=='leg.fold' else -10 if id=='leg.swing' else 0
            q=multiply(axis_rotation(rotate(basis,(1,0,0)),pitch),v[key('foot.orientation')])
            orientations=([q]*len(points) if id=='leg.swing' else
                          [q if i==1 else v[key('foot.orientation')] for i in range(len(points))])
            path(key('foot.orientation'),orientations)
        else:
            initial={name:v[key('hip.'+name)] for name in ('flexion','abduction','rotation')}
            if id=='leg.extend':
                if v[key('knee.flexion')]<20 or v[key('hip.flexion')]<20 or side+'.sole' in entry.active_contacts:
                    c.fail('ENTRY_MISMATCH','Leg extension requires a captured raised, bent, already-free leg')
                hips=[initial['flexion']];knees=[angle]
            elif id=='hip.lift':hips=[15,angle];knees=[35,angle+25]
            elif id in ('hip.open_close','hip.rotate'):hips=[25,25];knees=[50,50]
            elif id=='knee.flex':hips=[15,12+angle/2];knees=[30,angle]
            elif id=='knee.lift':hips=[20,angle];knees=[45,angle+30]
            else:hips=[35,angle,35];knees=[70,20,70]
            path(key('hip.flexion'),hips);path(key('knee.flexion'),knees)
            for name in ('abduction','rotation'):
                points=[initial[name]]*len(hips)
                if (id=='hip.open_close' and name=='abduction') or (id=='hip.rotate' and name=='rotation'):
                    points[1]=initial[name]+angle
                path(key('hip.'+name),points)
            path(key('foot.orientation'),[v[key('foot.orientation')]]*len(hips))
    if id!='knee.pulse' and p['return_policy']=='return_to_entry':
        previous=end;end+=release
        for segments in paths.values():segments.append((previous,end,segments[-1][3],segments[-1][3],None))
    prep=0 if id=='knee.pulse' else release
    for key,segments in paths.items():
        paths[key]=[(round(a*c.FPS)/c.FPS,round(b*c.FPS)/c.FPS,x,y,aim) for a,b,x,y,aim in segments]
    end=round(end*c.FPS)/c.FPS
    recovery=end if p['return_policy']=='preserve_end' else max(0,end-d-(release if id!='knee.pulse' else 0))
    landmarks=(c.PhaseLandmark('release',0),c.PhaseLandmark('preparation',prep),
               c.PhaseLandmark('action',min(end,prep+d+hold)),c.PhaseLandmark('recovery',recovery),c.PhaseLandmark('end',end))
    f=_fragment(instance,entry,profile,paths,end,landmarks)
    if id=='knee.pulse':return f
    # Release before movement; re-acquire only after measured-entry recovery.
    events=[]
    for anchor in entry.active_contacts:
        if anchor!=side+'.sole':
            events.append(c.ContactEvent(instance.instance_id+'.support',(instance.instance_id,),anchor,'floor',c.TimeInterval(0,end),0,0,0))
        else:
            events.append(c.ContactEvent(instance.instance_id+'.release',(instance.instance_id,),anchor,'floor',c.TimeInterval(0,release),0,release,0))
            if p['return_policy']=='return_to_entry':
                events.append(c.ContactEvent(instance.instance_id+'.recover',(instance.instance_id,),anchor,'floor',c.TimeInterval(end-release,end),0,0,0))
    return replace(f,contact_events=tuple(events))


BUILDERS={'legs.mechanics.v1':build}


def register_legs(catalog,profile):
    from .registry import register_movement
    if profile.version not in (7,8):return catalog
    bounds={'hip.lift':(0,70,40),'hip.open_close':(-8,22,12),'hip.rotate':(-25,25,15),
            'leg.extend':(0,40,15),'knee.flex':(0,100,60),'knee.lift':(30,70,55),
            'knee.orient':(-35,35,20),'leg.kick':(30,60,45)}
    for id in IDS:
        pulse=id=='knee.pulse'
        params=(_enum('side','both' if pulse else 'left',('both',) if pulse else ('left','right')),
                _enum('support','both_planted' if pulse else 'opposite_planted',('both_planted','opposite_planted')),
                _number('duration_s','second',1.5,1.5,3),_number('hold_s','second',.1,0,1),
                _enum('return_policy','return_to_entry',('return_to_entry','preserve_end')))
        if id in bounds:
            lo,hi,default=bounds[id];params+=(_number('angle','degree',default,lo,hi),)
        if pulse:params+=(_number('depth_m','metre',.02,.005,.05),)
        if id in ('leg.swing','leg.cross','leg.fold'):
            params+=(_number('distance_m','metre',.06 if id=='leg.swing' else .18 if id=='leg.cross' else .06,0,.10 if id!='leg.cross' else .20),
                     c.ParameterSpec('target','vector','metre','world',False,True,None,-20,20,dimensions=3,nullable=True))
        if id=='leg.swing':params+=(_enum('plane','forward',('forward','side')),)
        chains=('pelvis',)+tuple(s+'.'+part for s in ('left','right') for part in ('thigh','shin','ankle')) if pulse else tuple(s+'.'+part for s in ('left','right') for part in ('thigh','shin','ankle'))
        register_movement(c.MovementDefinition(id,1,'limb','Finite '+id+' with explicit captured support and measured recovery',
            params,(),(),chains,(),(),'legs.mechanics.v1',('leg_mechanics','both_planted' if pulse else 'free_leg'),
            ('release','preparation','action','recovery','end'),'return_to_entry'),catalog)
    return catalog
