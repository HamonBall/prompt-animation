"""Repeat one completed case without growing media, motions or shared assets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.artifact_store import atomic_json,digest,render_complete
from tools.artifact_bundle import validate_manifest
from tools.storage_policy import ARTIFACTS,active_writer

OUT=ARTIFACTS/'stages/05.2'


def snapshot(case):
    manifest,asset,motion=validate_manifest(case)
    paths=[asset,motion,*((case/view['media']['path']) for view in manifest['views'].values())]
    paths.extend((ARTIFACTS/'assets').glob('*/asset.json'))
    paths.extend((ARTIFACTS/'assets').glob('*/avatar.blend'))
    records={p.relative_to(ARTIFACTS).as_posix():{'bytes':p.stat().st_size,'sha256':digest(p)} for p in set(paths)}
    return {'payload_bytes':sum(v['bytes'] for v in records.values()),'payload_files':len(records),
            'payload_fingerprint':hashlib.sha256(json.dumps(records,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'stage_motion_files':len(list(OUT.glob('*/*/motion.blend'))),'shared_avatar_files':len(list((ARTIFACTS/'assets').glob('*/avatar.blend'))),
            'case_movie_files':len(list(case.glob('*.mkv')))}


def check(rig,name):
    case=OUT/rig/name
    assert not active_writer(case),'Wait for this rig writer to finish'
    assert render_complete(case,('front','side')),'Current complete evidence is required'
    before=snapshot(case);steps=[]
    blender=Path('C:/Program Files/Blender Foundation/Blender 5.1/blender.exe')
    for _ in range(2):
        with (OUT/'resume-check.log').open('w',encoding='utf-8') as log:
            subprocess.run([str(blender),'--background','--threads','2','--factory-startup','--python-exit-code','1',
                '--python',str(ROOT/'tests/blender_movement_shoulders_arms.py'),'--','--rig',rig,'--case',name,
                '--render-only','--lossless-video','--skip-rendered'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        after=snapshot(case)
        for key in ('payload_fingerprint','payload_bytes','payload_files','stage_motion_files','shared_avatar_files'):
            assert after[key]==before[key],('Repeat changed accepted payload',key)
        assert after['case_movie_files']<=before['case_movie_files']
        assert render_complete(case,('front','side'))
        steps.append(after)
    report={'owner':'stage-05.2-resume-no-growth-v1','case':rig+'/'+name,'passed':True,'repeats':2,
            'before':before,'after_each_repeat':steps,'scope':'Selected case payload and all shared assets; global stage motion count'}
    atomic_json(OUT/'resume-no-growth.json',report)
    print('SHOULDERS_ARMS_RESUME_NO_GROWTH_PASSED',rig,name,before,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--rig',choices=('demo','mixamo'),default='demo')
    parser.add_argument('--case',default='arm.raise.default');args=parser.parse_args();check(args.rig,args.case)
