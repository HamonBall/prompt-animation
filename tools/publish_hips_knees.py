"""Publish profile-7 schemas, examples and explicit reviews after all gates."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.legs import IDS
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.registry import parameter_schema
from tools.artifact_store import atomic_json
from tools.legs_evidence import OUT
from tools.hips_knees_views import visual_reviews
summary=json.loads((OUT/'validation-summary.json').read_text());replay=json.loads((OUT/'saved-playback-summary.json').read_text())
assert summary['passed'] and replay['passed'] and summary['case_count']==replay['case_count']==156
visual_reviews();fix=ROOT/'tests/fixtures/hips_knees/v1';manifest={'profile_version':7,'definition_version':1,'rigs':{}}
for rig in ('demo','mixamo'):
    p=c.loads(c.AvatarProfile,(OUT/rig/'profile.json').read_text());cat=catalog_for_profile(p);base=fix/rig;base.mkdir(parents=True,exist_ok=True)
    (base/'profile.json').write_text(c.dumps(p),encoding='utf-8');atomic_json(base/'schemas.json',{id:parameter_schema(cat.definitions[id]) for id in IDS})
    reviews=[];manifest['rigs'][rig]={}
    for id in IDS:
        record=c.VerificationRecord(id,1,p.avatar_id,7,cat.definitions[id].parameter_specs,
            ('artifacts/stages/05.4/validation-summary.json','artifacts/stages/05.4/saved-playback-summary.json',
             'artifacts/stages/05.4/visual-review.json','artifacts/stages/05.4/boundary-review.json',
             'conditional entry/support/reach/joint/floor/clearance envelope; no grasp, knee-floor or airborne physics'),
            tuple(c.ParameterValue(key,value) for key,value in summary['per_id'][id].items()),'reviewed_for_envelope')
        cat.register_review(record,p);reviews.append(c.to_dict(record))
        example=OUT/rig/(id+'.default.'+('both' if id=='knee.pulse' else 'left'));records={}
        for name in ('entry','instance','fragment','executable'):
            target=base/(id+'-'+name+'.json');target.write_bytes((example/(name+'.json')).read_bytes());records[name]=target.relative_to(fix).as_posix()
        manifest['rigs'][rig][id]={'status':'reviewed_for_envelope','records':records}
    atomic_json(base/'reviews.json',reviews)
    atomic_json(base/'capability-status.json',{'core_leg_chains':'existing exact thigh/shin/ankle mapping',
        'free_leg_support':'opposite captured sole required; release precedes movement',
        'pulse_support':'both captured floor soles planted; shallow crouch/upright entry',
        'plane':'reachable bent chain, not lateral knee hinge','knee_floor':'unavailable','airborne':'unavailable'})
atomic_json(fix/'manifest.json',manifest);print('PUBLISHED_HIPS_KNEES_FIXTURES',len(IDS),len(manifest['rigs']),flush=True)
