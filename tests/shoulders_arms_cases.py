"""Deterministic stage 05.2 baseline matrix; no Blender dependency."""
from avatar_app.movement_library.limbs import IDS
from avatar_app.movement_library.limbs import shoulder_position
from avatar_app.movement_library.spatial import rotate,normalize
import math


def expected_frames(id,parameters):
    d=math.ceil(parameters.get('duration_s',1.5)*30)/30;hold=parameters.get('hold_s',.1)
    recovery=0 if parameters.get('return_policy')=='preserve_end' else d
    if id in ('arm.circle','shoulder.roll'):duration=d+hold+math.ceil(d*30/32)*32/30+recovery
    else:
        points=2 if id in ('arm.swing','arm.stroke') else 1
        duration=points*(d+hold)+recovery
    return math.ceil(duration*30-1e-7)+1


def case_parameters(name,parameters,entry,profile):
    """Author explicit measured world targets for the target-override fixtures."""
    values={v.control_id:v.value for v in entry.measured_controls};parameters=dict(parameters)
    if name=='arm.reach.cross-body-target':
        left=shoulder_position(values,profile,'left');right=shoulder_position(values,profile,'right')
        center=tuple((a+b)/2 for a,b in zip(left,right))
        offset=rotate(entry.root_transform.orientation,(.06*profile.height_m,.20*profile.height_m,-.10*profile.height_m))
        parameters['target']=tuple(a+b for a,b in zip(center,offset))
    if name.endswith('.independent-targets'):
        parameters['side']='both'
        for side,distance in (('left',.01),('right',.02)):
            hand=values[side+'.hand.position'];shoulder=shoulder_position(values,profile,side)
            radial=normalize(tuple(a-b for a,b in zip(hand,shoulder)))
            offset=rotate(entry.root_transform.orientation,(0,distance*profile.height_m,0))
            parameters[side+'_target']=tuple(a+b-r*.04*profile.height_m for a,b,r in zip(hand,offset,radial))
    return parameters

def cases(quick=False):
    for id in IDS:
        pose='shoulders-bent' if id.startswith('shoulder.') else 'bent-turned'
        yield id+'.default',id,{},pose
        if quick:continue
        for side in ('right','both'):yield id+'.'+side,id,{'side':side},pose
        if id.startswith('shoulder.'):
            yield id+'.independent',id,{'side':'both','left_angle':2,'right_angle':6},pose
        elif id not in ('arm.fold','arm.reach','arm.stroke'):
            yield id+'.independent',id,{'side':'both','left_angle':6,'right_angle':12 if id=='arm.circle' else 30},pose
        else:yield id+'.independent-targets',id,{'side':'both'},pose
        yield id+'.neutral',id,{},'neutral'
        yield id+'.preserve',id,{'return_policy':'preserve_end'},pose
        if id in ('arm.raise','arm.swing'):yield id+'.side',id,{'plane':'side'},pose
        if id=='arm.sweep':yield id+'.backward',id,{'angle':-20},pose
        if id=='arm.sweep':yield id+'.cross-body',id,{'angle':110},'cross-body-clearance'
        if id=='arm.circle':yield id+'.overhead',id,{},'overhead'
        if not id.startswith('shoulder.') and id not in ('arm.fold','arm.reach','arm.stroke'):
            yield id+'.world',id,{'frame':'world'},pose
        bound=8 if id=='shoulder.roll' else 10 if id.startswith('shoulder.') else 20 if id=='arm.circle' else 150 if id=='arm.raise' else 110 if id=='arm.sweep' else 70
        for label,angle in (('min',-30 if id=='arm.raise' else -70 if id=='arm.sweep' else -bound),('max',bound),('zero',0)):
            if id not in ('arm.fold','arm.reach','arm.stroke'):yield id+'.'+label,id,{'angle':angle,'side':'both'},'cross-body-clearance' if id=='arm.sweep' and label=='max' else pose
        if id=='arm.reach':
            yield id+'.cross-body-target',id,{},pose
            for label,distance in (('min',-.08),('max',.08)):yield id+'.'+label,id,{'distance_m':distance,'side':'both'},pose
        if id=='arm.stroke':
            for label,amplitude in (('min',0),('max',.16)):yield id+'.'+label,id,{'amplitude_m':amplitude,'side':'both'},pose
        for label,duration in (('fast',1),('slow',3)):
            yield id+'.'+label,id,{'duration_s':duration},pose
