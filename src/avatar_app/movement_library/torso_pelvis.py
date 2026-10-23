"""Bounded spine/pelvis v1 builders using the shared fragment executor."""
from dataclasses import replace
import math
from . import contracts as c
from .joints import _number,_enum,_path,_fragment,_seconds
from .spatial import with_head_aim_v1,rotate,multiply,angle_rotation

IDS=('torso.lean','torso.twist','torso.curl','torso.wave','torso.sway',
     'pelvis.shift','pelvis.raise_lower','pelvis.tilt_turn','pelvis.circle')


def with_pelvis_v1(profile):
    profile=with_head_aim_v1(profile)
    if profile.version==3: return profile
    if profile.version!=2: c.fail('VERSION_MISMATCH','Pelvis measurement extension requires head-aim profile v2')
    extra=(c.ControlSpec('pelvis.position','metre','vector',3,('world',),'pelvis','measure.pelvis.position'),
           c.ControlSpec('pelvis.orientation','unitless','quaternion',4,('world',),'pelvis','measure.pelvis.orientation'),
           c.ControlSpec('object_root.position','metre','vector',3,('world',),'pelvis','measure.object_root.position'),
           c.ControlSpec('object_root.orientation','unitless','quaternion',4,('world',),'pelvis','measure.object_root.orientation'))
    return replace(profile,version=3,controls=profile.controls+extra,
        capabilities=tuple(sorted((*profile.capabilities,*(v.capability for v in extra)))),
        calibration_provenance=replace(profile.calibration_provenance,
            evidence=profile.calibration_provenance.evidence+('pelvis_v1:bone_world_transform_not_object_root',)))


def build(instance,entry,profile,surfaces):
    p={v.name:v.value for v in instance.parameters}; values={v.control_id:v.value for v in entry.measured_controls}
    spine=[j for j in ('torso','spine.mid','spine.upper') if j+'.pitch' in values]
    d=_seconds(p['duration_s']); hold=_seconds(p['hold_s']); paths={}; end=0; orbit=None
    id=instance.definition_id
    def path(control,points,delay=0,return_policy=None):
        nonlocal end
        paths[control],t=_path(values[control],points,d,hold,return_policy or p['return_policy'],delay)
        end=max(end,t)
    if id.startswith('torso.'):
        axis='yaw' if id=='torso.twist' else p['plane']
        joints=spine if id in ('torso.curl','torso.wave') else spine[:1]
        if not joints: c.fail('MISSING_CAPABILITY','No calibrated spine segment')
        for index,joint in enumerate(joints):
            control=joint+'.'+axis; amplitude=p['angle']/len(joints)
            points=[values[control]+amplitude]
            if id=='torso.sway': points.append(values[control]-amplitude)
            if id=='torso.wave':
                # A pulse recovers even when preserving the cycle's end state.
                path(control,points+[values[control]],index*8/c.FPS,'preserve_end')
            else:path(control,points)
    else:
        if set(entry.active_contacts)!={'left.sole','right.sole'}:
            c.fail('ENTRY_MISMATCH','Supported pelvis movement requires both captured floor sole anchors')
        if id=='pelvis.tilt_turn':
            target=multiply(values['pelvis.orientation'],angle_rotation(**{p['plane']:p['angle']}))
            path('pelvis.orientation',[target])
        else:
            origin=values['pelvis.position']
            axis={'forward':(0,1,0),'side':(1,0,0),'vertical':(0,0,1)}[p['plane']]
            offset=rotate(entry.root_transform.orientation,tuple(v*p['distance_m'] for v in axis))
            points=[tuple(a+b for a,b in zip(origin,offset))]
            if id=='pelvis.circle':
                # A closed 32-chord orbit has <0.2mm radial error at the 4cm limit.
                # Orbit chords use linear timing so there is no stop at each vertex.
                first=points[0];segments,end=_path(origin,[first],d,hold,'preserve_end')
                start_frame=round(end*c.FPS);step_frames=round(_seconds(d/4)*c.FPS)
                previous=first
                for index in range(1,33):
                    angle=index*2*math.pi/32
                    delta=rotate(entry.root_transform.orientation,(p['distance_m']*math.cos(angle),p['distance_m']*math.sin(angle),0))
                    target=first if index==32 else tuple(a+b for a,b in zip(origin,delta))
                    a=(start_frame+(index-1)*step_frames)/c.FPS;b=(start_frame+index*step_frames)/c.FPS
                    segments.append((a,b,previous,target,None));previous=target
                orbit=(start_frame/c.FPS,b);end=b
                if hold:segments.append((end,end+hold,first,first,None));end+=hold
                segments.append((end,end+d,first,origin,None));end+=d
                if hold:segments.append((end,end+hold,origin,origin,None));end+=hold
                paths['pelvis.position']=segments
            else:path('pelvis.position',points)
    # Head aim is independent; the arms retain their local pose and follow the torso.
    for control in ('head.orientation',):
        if control not in values: c.fail('MISSING_CAPABILITY','Body movement requires measured head orientation',control_id=control)
        paths[control]=[(0,end,values[control],values[control],None)]
    f=_fragment(instance,entry,profile,paths,end,(c.PhaseLandmark('end',end),))
    if orbit:
        f=replace(f,tracks=tuple(replace(t,curve=replace(t.curve,easing='linear'))
            if t.control_id=='pelvis.position' and orbit[0]<=t.interval.start_s and t.interval.end_s<=orbit[1] else t for t in f.tracks))
    if id=='torso.wave' and len(spine)==1:
        f=replace(f,phase_landmarks=f.phase_landmarks+(c.PhaseLandmark('single_spine_approximation',0),))
    # Metre goals are stricter than the shared 10mm limit.
    return replace(f,goals=tuple(replace(g,tolerance=.001) if g.target.unit=='metre' else g for g in f.goals))


BUILDERS={'body.torso_pelvis.v1':build}


def register_body(catalog,profile=None):
    from .registry import register_movement
    spine=tuple(j for j in ('torso','spine.mid','spine.upper') if profile is None or any(v.id==j+'.pitch' for v in profile.controls))
    for id in IDS:
        pelvis=id.startswith('pelvis.')
        params=(_number('duration_s','second',1,.8,3),_number('hold_s','second',.1,0,1),
                _enum('return_policy','return_to_entry',('return_to_entry','preserve_end')))
        if pelvis and id!='pelvis.tilt_turn':
            params+=(_number('distance_m','metre',-.02 if id=='pelvis.raise_lower' else .01,-.04,.04),
                     _enum('plane','vertical' if id=='pelvis.raise_lower' else 'side',('vertical',) if id=='pelvis.raise_lower' else ('side',) if id=='pelvis.circle' else ('forward','side')))
        else:
            params+=(_number('angle','degree',5 if pelvis else 10,-10 if pelvis else -20,10 if pelvis else 20),
                     _enum('plane','yaw' if id in ('torso.twist','pelvis.tilt_turn') else 'roll' if id=='torso.sway' else 'pitch',('yaw',) if id=='torso.twist' else ('pitch',) if id in ('torso.curl','torso.wave') else ('pitch','roll','yaw') if pelvis else ('pitch','roll')))
        owned=spine+('head',)+(('pelvis','left.thigh','left.shin','left.ankle','right.thigh','right.shin','right.ankle') if pelvis else ())
        caps=('measure.head.orientation','measure.torso.pitch')+(('measure.pelvis.position','measure.pelvis.orientation') if pelvis else ())
        register_movement(c.MovementDefinition(id,1,'body','Measured '+id+' with fixed world head orientation and preserved floor support',params,caps,(),owned,(),(),'body.torso_pelvis.v1',('torso_pelvis','bounded_cycle'),('end',),'return_to_entry'),catalog)
    return catalog
