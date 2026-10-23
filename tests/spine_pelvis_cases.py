"""Shared authored Stage 05.1b case matrix; no Blender import."""
from avatar_app.movement_library.torso_pelvis import IDS


def cases():
    for id in IDS:
        value='distance_m' if id.startswith('pelvis.') and id!='pelvis.tilt_turn' else 'angle'
        maximum=.04 if value=='distance_m' else 10 if id.startswith('pelvis.') else 20
        small=.005 if value=='distance_m' else 3
        for label,parameters,pose in (
            ('default',{},'crouched-turned'),('small',{value:small,'duration_s':.8,'hold_s':0},'crouched-turned'),
            ('min',{value:-maximum,'duration_s':.8,'hold_s':0},'crouched-turned'),
            ('max',{value:maximum,'duration_s':3,'hold_s':1},'crouched-turned'),
            ('zero',{value:0},'crouched-turned'),('preserve',{'return_policy':'preserve_end'},'crouched-turned')):
            yield id+'.'+label,id,parameters,pose
        if id.startswith('torso.'): yield id+'.neutral',id,{},'neutral'
        if id=='torso.lean':yield id+'.free-space',id,{},'free-space'
        if id=='pelvis.raise_lower':yield id+'.turned-standing',id,{},'turned-standing'
        if id in ('torso.lean','torso.sway','pelvis.tilt_turn','pelvis.shift'):
            for plane in (('pitch','roll') if id.startswith('torso.') else ('pitch','roll','yaw') if id=='pelvis.tilt_turn' else ('side','forward')):
                yield id+'.'+plane,id,{'plane':plane},'crouched-turned'
                yield id+'.'+plane+'-negative',id,{'plane':plane,value:-small},'crouched-turned'
                default='pitch' if id=='torso.lean' else 'roll' if id=='torso.sway' else 'yaw' if id=='pelvis.tilt_turn' else 'side'
                if plane!=default:
                    for label,boundary in (('min',-maximum),('max',maximum)):
                        yield id+'.'+plane+'-'+label,id,{'plane':plane,value:boundary},'crouched-turned'
