"""Publish measured default examples and rig-scoped review records after Stage 05.1a validation."""
import json
from dataclasses import replace
from pathlib import Path
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.movement_library.registry import parameter_schema

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'tests/fixtures/head_neck/v1'
DEFAULTS={'head.look':'look-left','head.nod':'nod-default','head.shake':'shake-default','head.tilt':'tilt-default','neck.lead':'lead-default'}


def generate():
    source=ROOT/'artifacts/stages/05.1a'
    report=json.loads((source/'execution-review.json').read_text())
    assert all(len(report[rig]['cases'])==37 and report[rig]['negative_checks_passed'] for rig in ('demo','mixamo'))
    manifest={'schema_version':1,'definition_version':1,'profile_version':2,'curve_extension':'look_at_world_v1',
        'source_revision':(source/'source-revision.txt').read_text().strip(),'rigs':{},
        'review_scope':'Two measured entry fixtures, listed cases/parameter boundaries; valid angular and world-target constraints remain mandatory. No arbitrary-rig or arbitrary-parent-trajectory claim.'}
    for rig in ('demo','mixamo'):
        folder=OUT/rig; folder.mkdir(parents=True,exist_ok=True)
        profile=c.loads(c.AvatarProfile,(source/rig/'profile.json').read_text())
        catalog=catalog_for_profile(profile)
        (folder/'profile.json').write_text(c.dumps(profile)+'\n',encoding='utf-8')
        reviews=[]
        for id,name in DEFAULTS.items():
            records={}
            for kind in ('entry','instance','fragment'):
                path=folder/(id+'-'+kind+'.json')
                path.write_text((source/rig/name/(kind+'.json')).read_text(),encoding='utf-8')
                records[kind]=path.relative_to(OUT).as_posix()
            selected=[(name,v) for name,v in report[rig]['cases'].items() if v['id']==id]
            definition=catalog.definitions[id]
            full_neck=id!='neck.lead' or report[rig]['neck_capable']
            status='reviewed_for_envelope' if full_neck else 'unavailable_on_rig'
            evidence=(f'artifacts/stages/05.1a/{rig}/: '+','.join(name for name,_ in selected),
                'Full-frame numeric/playback and front-sheet review; side views for default/baseline cases.',
                'World targets: fixture points 3m away at +/-25deg, with up to 30deg externally authored torso turn; torso look limits tested independently.',
                'Neck unavailable on demo; head_only is an explicitly requested and labelled approximation.' if not full_neck else 'Measured calibrated articulation; entry, reach and preservation checks remain mandatory.')
            envelope=definition.parameter_specs if full_neck else ()
            if id=='head.look':
                envelope=tuple(replace(p,enum_values=('torso',)) if p.name=='frame' else p for p in envelope)
                evidence+=('Registry envelope is torso mode. World-point fixture cases are reviewed separately in the receipt; arbitrary world points are not advertised as reviewed.',)
            review=c.VerificationRecord(id,1,profile.avatar_id,profile.version,envelope,evidence,
                (c.ParameterValue('max_tracking_error_deg',max(v['max_tracking_error_deg'] for _,v in selected)),),status)
            catalog.register_review(review,profile); reviews.append(c.to_dict(review))
            manifest['rigs'].setdefault(rig,{})[id]={'records':records,'status':status,'cases':[name for name,_ in selected]}
        (folder/'reviews.json').write_text(json.dumps(reviews,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        (folder/'parameters.json').write_text(json.dumps({id:parameter_schema(v) for id,v in catalog.definitions.items()},indent=2)+'\n',encoding='utf-8')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print('MEASURED_HEAD_NECK_FIXTURES_PUBLISHED',len(list(OUT.rglob('*.json'))))


if __name__=='__main__': generate()
