"""Bounded coverage of baselines, selection, signs, limits and authored entries."""
def cases():
    rows=[]
    for gesture in ('open','relaxed','fist','point'):
        for pose in ('neutral','bent-turned'):
            rows.append(('gesture.'+gesture+'.'+pose,'hand.gesture',{'gesture':gesture,'side':'both'},pose))
    for side in ('left','right'):
        rows.append(('gesture.relaxed.'+side,'hand.gesture',{'side':side},'neutral'))
    rows.extend([
        ('curl.default','finger.curl_spread',{'side':'both'},'neutral'),
        ('curl.minimum','finger.curl_spread',{'side':'both','curl':0,'spread_deg':0},'bent-turned'),
        ('curl.maximum','finger.curl_spread',{'side':'both','curl':1,'spread_deg':0},'neutral'),
        ('spread.minimum','finger.curl_spread',{'side':'both','selection':'four_fingers','curl':0,'spread_deg':-20},'bent-turned'),
        ('spread.maximum','finger.curl_spread',{'side':'both','selection':'four_fingers','curl':0,'spread_deg':20},'bent-turned'),
        ('thumb.minimum','finger.curl_spread',{'side':'both','selection':'thumb','curl':0,'spread_deg':-15},'neutral'),
        ('thumb.maximum','finger.curl_spread',{'side':'both','selection':'thumb','curl':1,'spread_deg':15},'bent-turned'),
        ('curl.asymmetric','finger.curl_spread',{'side':'both','curl':0,'thumb_curl':.2,'index_curl':.9,'middle_curl':.1,'ring_curl':.6,'pinky_curl':.35},'bent-turned'),
        ('timing.maximum','finger.curl_spread',{'side':'both','selection':'index','duration_s':3,'hold_s':1,'return_policy':'preserve_end'},'neutral'),
        ('timing.minimum','finger.curl_spread',{'side':'both','selection':'index','duration_s':1.5,'hold_s':0},'neutral'),
    ])
    for index,digit in enumerate(('thumb','index','middle','ring','pinky')):
        rows.append(('selection.'+digit,'finger.curl_spread',{'selection':digit,'curl':.5,'spread_deg':-5 if index%2 else 5,
                    'side':'left' if index%2 else 'right'},'bent-turned'))
    rows.append(('gesture.open-fist-point','hand.gesture',{'gesture':'point','side':'both'},'sequence'))
    return rows
