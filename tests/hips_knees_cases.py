"""Explicit stage-05.4 coverage; no scheduler or generated Cartesian product."""
from avatar_app.movement_library.legs import IDS


def cases():
    rows=[]
    bounds={'hip.lift':(0,70),'hip.open_close':(-8,22),'hip.rotate':(-25,25),
            'leg.extend':(0,40),'knee.flex':(0,100),'knee.lift':(30,70),'knee.orient':(-35,35),'leg.kick':(30,60)}
    for id in IDS:
        entry='raised' if id in ('leg.extend','knee.orient') else 'neutral'
        sides=('both',) if id=='knee.pulse' else ('left','right')
        for side in sides:rows.append((id+'.default.'+side,id,{'side':side},entry))
        rows.append((id+'.turned',id,{'side':sides[-1]},'raised-turned' if entry=='raised' else 'turned'))
        if id in bounds:
            for label,angle in zip(('minimum','maximum'),bounds[id]):rows.append((id+'.'+label,id,{'angle':angle},entry))
        elif id=='knee.pulse':
            for label,depth in (('minimum',.005),('maximum',.05)):rows.append((id+'.'+label,id,{'depth_m':depth},'neutral'))
            rows.append((id+'.crouched',id,{},'crouched-turned'))
        else:
            for label,distance in (('minimum',0),('maximum',.20 if id=='leg.cross' else .10)):
                rows.append((id+'.'+label,id,{'distance_m':distance},'neutral'))
            rows.append((id+'.crouched',id,{},'crouched-turned'))
        rows.append((id+'.preserve',id,{'return_policy':'preserve_end','hold_s':0},entry))
    rows.extend((('swing.side','leg.swing',{'plane':'side','side':'right'},'turned'),
        ('timing.minimum','knee.lift',{'duration_s':1.5,'hold_s':0},'neutral'),
        ('timing.maximum','leg.kick',{'duration_s':3,'hold_s':1,'side':'right'},'turned')))
    return rows
