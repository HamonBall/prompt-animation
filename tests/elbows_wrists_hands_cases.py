"""Deterministic authored stage-05.3a coverage, shared by producer and audits."""
from avatar_app.movement_library.hands import IDS
from avatar_app.movement_library.hands import forearm_twist_sign
from avatar_app.movement_library.spatial import inverse,rotate,multiply,palm_rotation,normalize
from avatar_app.movement_library.curves import axis_rotation
import math


def cases(quick=False):
    bounds={'elbow.flex':(0,130),'elbow.orient':(-45,45),'forearm.twist':(-179,179),
            'wrist.flex':(-60,60),'wrist.deviate':(-25,25),'wrist.circle':(-10,10),'hand.orient':(-150,150)}
    for id in IDS:
        yield id+'.default',id,{},'bent-turned'
        if quick:continue
        for side in ('right','both'):yield id+'.'+side,id,{'side':side},'bent-turned'
        yield id+'.preserve',id,{'return_policy':'preserve_end'},'bent-turned'
        if id!='elbow.orient':yield id+'.neutral',id,{'distance_m':0} if id=='hand.trace' else {},'neutral'
        if id in bounds:
            lo,hi=bounds[id]
            for name,angle in (('min',lo),('max',hi),('zero',0)):
                yield id+'.'+name,id,{'side':'both','angle':angle,'hold_s':1 if name=='max' else 0,
                                    'duration_s':3 if name=='max' else 1.5},'bent-turned'
            yield id+'.independent',id,{'side':'both','left_angle':lo/2,'right_angle':hi/2},'bent-turned'
        else:
            for name,distance in (('min',-.04),('max',.04),('zero',0)):
                yield id+'.'+name,id,{'side':'both',**({'distance_m':distance} if id=='hand.trace' else {}),
                                    'duration_s':3 if name=='max' else 1.5,'hold_s':1 if name=='max' else 0},'bent-turned'
            yield id+'.independent-targets',id,{'side':'both'},'bent-turned'
        if id in ('forearm.twist','hand.orient'):
            for pose in ('straight','palms-bent'):
                for name in ('palms-up','palms-down'):
                    yield id+'.'+name+'.'+pose,id,{'side':'both'},pose
            if id=='hand.orient':yield id+'.opposite-palms',id,{'side':'both'},'palms-bent'
        if id in ('wrist.flex','wrist.deviate'):yield id+'.overhead',id,{'side':'both'},'overhead'
        if id=='elbow.orient':yield id+'.near-straight',id,{},'near-straight'
        if id=='hand.trace':
            for shape in ('arc','circle'):yield id+'.'+shape,id,{'path':shape,'side':'both'},'bent-turned'
        if id=='hand.hold':
            for frame in ('entry_body','current_torso'):yield id+'.'+frame,id,{'side':'both','position_frame':frame,'orientation_frame':frame},'bent-turned'
            yield id+'.chest-forward-elbows',id,{'side':'both'},'chest'


def parameters_for(name,parameters,entry,profile):
    p=dict(parameters);v={x.control_id:x.value for x in entry.measured_controls}
    if '.palms-' in name or name.endswith('.opposite-palms'):
        for side in ('left','right'):
            down='.palms-down' in name or name.endswith('.opposite-palms') and side=='right'
            normal=(0,0,-1 if down else 1)
            direction=v[side+'.forearm.direction'];forward=normalize((direction[0],direction[1],0))
            if name.startswith('hand.orient.'):
                p[side+'_orientation']=palm_rotation(forward,normal)
            else:
                initial=rotate(v[side+'.hand.orientation'],(0,0,1));axis=direction
                cross=(initial[1]*normal[2]-initial[2]*normal[1],initial[2]*normal[0]-initial[0]*normal[2],initial[0]*normal[1]-initial[1]*normal[0])
                angle=math.degrees(math.atan2(sum(a*b for a,b in zip(axis,cross)),sum(a*b for a,b in zip(initial,normal))))
                raw=v[side+'.forearm.twist']+forearm_twist_sign(profile,side)*angle
                target=(raw+180)%360-180
                if abs(target+180)<1e-4 and raw>0:target=180
                p[side+'_angle']=max(-179,min(179,target))
    if name.endswith(('.entry_body','.current_torso','.independent-targets')):
        frame=p.get('position_frame','world')
        origin=entry.root_transform.position if frame=='entry_body' else v['torso_frame.position']
        q=entry.root_transform.orientation if frame=='entry_body' else v['torso_frame.orientation']
        for side in ('left','right'):
            target=v[side+'.hand.position']
            if name.endswith('.independent-targets'):
                d=rotate(entry.root_transform.orientation,(0,.01 if side=='left' else .02,0))
                target=tuple(a+b for a,b in zip(target,d))
            if frame!='world':target=rotate(inverse(q),tuple(a-b for a,b in zip(target,origin)))
            prefix='entry_' if frame=='entry_body' else 'torso_' if frame=='current_torso' else ''
            p[side+'_'+prefix+'target']=target
            orientation=v[side+'.hand.orientation']
            p[side+'_'+prefix+'orientation']=multiply(inverse(q),orientation) if frame!='world' else orientation
    if name.endswith('.chest-forward-elbows'):
        # Fixture has hands at shoulder/chest height with elbows forward. Explicit
        # torso-relative endpoints and measured pole controls express the combination.
        origin=v['torso_frame.position'];q=v['torso_frame.orientation']
        p.update(position_frame='current_torso',orientation_frame='current_torso')
        for side in ('left','right'):
            p[side+'_torso_target']=rotate(inverse(q),tuple(a-b for a,b in zip(v[side+'.hand.position'],origin)))
            p[side+'_torso_orientation']=multiply(inverse(q),v[side+'.hand.orientation'])
            p[side+'_elbow_plane_deg']=v[side+'.elbow.plane']
        # Each side's plane is independent; symmetric fixture gives mirrored angles.
    return p


def expected_frames(id,p):
    d=math.ceil(p.get('duration_s',1.5)*30)/30;hold=math.ceil(p.get('hold_s',.1)*30)/30
    if id=='wrist.circle':duration=32*math.ceil(d*30/32)/30+hold
    elif id=='hand.trace' and p.get('path') in ('arc','circle'):
        duration=d+hold+16*math.ceil(d*30/16)/30+(d if p.get('return_policy')!='preserve_end' else 0)
    else:duration=d+hold+(d if p.get('return_policy')!='preserve_end' else 0)
    return math.ceil(duration*30-1e-7)+1
