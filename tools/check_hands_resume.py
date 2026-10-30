"""Repeat a complete case twice without retaining new motions, assets or movies."""
import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tools.artifact_store import atomic_json,digest
from tools.hands_render_state import render_complete
OUT=ROOT/'artifacts/stages/05.3a';case=OUT/'demo/elbow.flex.default'
assert render_complete(case,('front','side','hand-front','hand-side'))

def snapshot():
    paths=(list((ROOT/'artifacts/assets').glob('*/*'))+list(OUT.rglob('motion.blend'))+
           list(OUT.rglob('*.mkv'))+list(OUT.rglob('preview-manifest.json')))
    records={str(p.relative_to(ROOT/'artifacts')):{'bytes':p.stat().st_size,'sha256':digest(p),'mtime_ns':p.stat().st_mtime_ns} for p in paths if p.is_file()}
    return {'records':records,'stage_motion_count':len(list(OUT.rglob('motion.blend'))),
            'stage_movie_count':len(list(OUT.rglob('*.mkv'))),
            'shared_avatar_count':len(list((ROOT/'artifacts/assets').glob('*/avatar.blend'))),'case_movie_count':len(list(case.glob('*.mkv')))}
before=snapshot();steps=[]
for _ in range(2):
    with (OUT/'resume-check.log').open('w',encoding='utf-8') as log:
        subprocess.run(['C:/Program Files/Blender Foundation/Blender 5.1/blender.exe','--background','--threads','2','--factory-startup','--python-exit-code','1',
                        '--python',str(ROOT/'tools/render_hands_evidence.py'),'--','--rig','demo','--case','elbow.flex.default'],
                       cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert snapshot()==before,'Repeat changed retained payload or counts'
    assert render_complete(case,('front','side','hand-front','hand-side'));steps.append({'passed':True})
atomic_json(OUT/'resume-no-growth.json',{'passed':True,'repeats':steps,'motion_count':before['stage_motion_count'],
    'stage_movie_count':before['stage_movie_count'],
    'shared_avatar_count':before['shared_avatar_count'],'case_movie_count':before['case_movie_count'],
    'protected_payload_files':len(before['records']),'payload_bytes':sum(v['bytes'] for v in before['records'].values())})
print('HANDS_NO_GROWTH_REPEAT_PASSED',flush=True)
