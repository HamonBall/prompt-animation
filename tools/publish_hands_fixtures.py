"""Publish hand schemas/reviews only after numeric, saved-media and actual visual gates."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.hands import IDS
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.registry import parameter_schema
from tools.artifact_store import atomic_json,digest
from tools.hands_render_state import render_complete
from tools.hands_evidence_cases import cases,detail_cases
SOURCE=ROOT/'artifacts/stages/05.3a';DEST=ROOT/'tests/fixtures/elbows_wrists_hands/v1'
summary=json.loads((SOURCE/'validation-summary.json').read_text());visual=json.loads((SOURCE/'visual-review.json').read_text())
manifest={'schema_version':1,'definition_version':1,'profile_version':5,'rigs':{}}
for rig in ('demo','mixamo'):
    base=SOURCE/rig;destination=DEST/rig;destination.mkdir(parents=True,exist_ok=True)
    profile=c.loads(c.AvatarProfile,(base/'profile.json').read_text());catalog=catalog_for_profile(profile)
    expected={name for name,_,_,_ in cases()};assert summary[rig]['passed_cases']==len(expected) and not summary[rig]['pending']
    assert set(visual[rig]['reviewed_cases'])==expected
    inspected=set();inspected_detail=set()
    for page in visual[rig]['inspected_pages']:
        assert digest(SOURCE/page['path'])==page['sha256']
        for name,sheets in page['source_sheets'].items():
            for view,sha in sheets.items():assert digest(base/name/(view+'-sheet.png'))==sha
            if page['path'].startswith('review-full/'):inspected.add(name)
            if page['path'].startswith('review-detail/'):inspected_detail.add(name)
    assert inspected==expected
    assert inspected_detail=={row[0] for row in detail_cases()}
    reviews=[];manifest['rigs'][rig]={}
    for id in IDS:
        names=[name for name,kind,_,_ in cases() if kind==id];metrics={}
        for name in names:
            assert render_complete(base/name,('front','side'))
            r=json.loads((base/name/'result.json').read_text());assert r['review']['passed']
            for key,value in r['review']['metrics'].items():
                if isinstance(value,(int,float)) and key not in ('frames','semantic_frames'):metrics[key]=max(metrics.get(key,0),value)
        evidence=('artifacts/stages/05.3a/'+rig+': '+','.join(names),
                  'Named entry fixtures, independent sides, declared scalar ranges and timing; exact spatial goals remain conditional on measured reach, joint limits and clearance.',
                  'All motion frames measured; saved-action playback and lossless pixels checked per frame; full-motion front/side evidence and actually inspected review pages.',
                  'Additional measured palm-normal/finger-forward closeups cover defaults, wrist extremes, palms, overhead, near-straight and curve/chest cases.',
                  'No hand-to-surface attachment, finger gestures or generic recipe composer.')
        review=c.VerificationRecord(id,1,profile.avatar_id,5,catalog.definitions[id].parameter_specs,evidence,
                                    tuple(c.ParameterValue(k,v) for k,v in metrics.items()),'reviewed_for_envelope')
        catalog.register_review(review,profile);reviews.append(c.to_dict(review));records={}
        for kind in ('entry','instance','fragment','executable'):
            target=destination/(id+'-'+kind+'.json');target.write_text((base/(id+'.default')/(kind+'.json')).read_text(),encoding='utf-8')
            records[kind]=target.relative_to(DEST).as_posix()
        manifest['rigs'][rig][id]={'status':'reviewed_for_envelope','cases':names,'records':records,'metrics':metrics}
    (destination/'profile.json').write_text(c.dumps(profile),encoding='utf-8')
    (destination/'entry.json').write_text((base/'elbow.flex.default/entry.json').read_text(),encoding='utf-8')
    atomic_json(destination/'schemas.json',{id:parameter_schema(catalog.definitions[id]) for id in IDS})
    atomic_json(destination/'reviews.json',reviews)
atomic_json(DEST/'manifest.json',manifest)
print('PUBLISHED_HANDS_FIXTURES',sum(v['passed_cases'] for v in summary.values()),flush=True)
