"""Additional authored arc/circle endpoint and traversal range baselines."""
def cases():
    for shape in ('arc','circle'):
        for label,distance in (('min',-.04),('max',.04)):
            yield 'hand.trace.'+shape+'.'+label,'hand.trace',{'side':'both','path':shape,'distance_m':distance,
                'duration_s':3 if label=='max' else 1.5,'hold_s':1 if label=='max' else 0},'bent-turned'
