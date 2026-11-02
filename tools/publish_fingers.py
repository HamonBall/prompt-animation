"""Publish versioned examples and explicit supported/unavailable review records."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.fingers import IDS,DIGITS
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.registry import parameter_schema
from tools.artifact_store import atomic_json,digest
from tools.fingers_visual_valid import validate_visual_reviews
OUT=ROOT/'artifacts/stages/05.3b';FIX=ROOT/'tests/fixtures/fingers/v1'
summary=json.loads((OUT/'validation-summary.json').read_text());assert summary['passed']
visual=validate_visual_reviews();assert set(visual['cases'])==set(summary['cases'])
manifest={'profile_version':6,'definition_version':1,'rigs':{}}
for rig in ('demo','mixamo'):
    p=c.loads(c.AvatarProfile,(OUT/rig/'profile.json').read_text());catalog=catalog_for_profile(p);base=FIX/rig;base.mkdir(parents=True,exist_ok=True)
    (base/'profile.json').write_text(c.dumps(p),encoding='utf-8');atomic_json(base/'schemas.json',{id:parameter_schema(catalog.definitions[id]) for id in IDS})
    reviews=[];manifest['rigs'][rig]={}
    for id in IDS:
        status='reviewed_for_envelope' if rig=='mixamo' else 'unavailable_on_rig'
        record=c.VerificationRecord(id,1,p.avatar_id,6,catalog.definitions[id].parameter_specs,
            ('artifacts/stages/05.3b/validation-summary.json','artifacts/stages/05.3b/visual-review.json',
             'artifacts/stages/05.3b/boundary-review.json','thumb is an authored hinge approximation; no opposition/grasp'),
            tuple(c.ParameterValue(key,value) for key,value in summary['maxima'].items()) if rig=='mixamo' else (),status)
        catalog.register_review(record,p);reviews.append(c.to_dict(record));manifest['rigs'][rig][id]={'status':status,'records':{}}
        if rig=='mixamo':
            example=OUT/rig/('gesture.relaxed.left' if id=='hand.gesture' else 'curl.default')
            for name in ('entry','instance','fragment','executable'):
                target=base/(id+'-'+name+'.json');target.write_bytes((example/(name+'.json')).read_bytes())
                manifest['rigs'][rig][id]['records'][name]=target.relative_to(FIX).as_posix()
    atomic_json(base/'reviews.json',reviews)
    atomic_json(base/'capability-status.json',{'mapping':'exact existing chains; no anatomy changes',
        'available_digits':{side:[digit for digit in DIGITS if 'detail.'+side+'.finger.'+digit+'.mapped_three_joint' in p.capabilities] for side in ('left','right')},
        'thumb':'approximate hinge; opposition unavailable' if rig=='mixamo' else 'unavailable',
        'gestures':'authored approximate poses on measured calibrated controls' if rig=='mixamo' else 'unavailable'})
atomic_json(FIX/'manifest.json',manifest);print('PUBLISHED_FINGERS_FIXTURES',summary['case_count'],flush=True)
