"""Final read-only payload, retained-evidence and storage accounting for 05.2."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from shoulders_arms_cases import cases
from tools.artifact_store import atomic_json,digest,render_complete
from tools.artifact_bundle import validate_manifest
from tools.storage_policy import ARTIFACTS,inventory,temporary_bytes,enforce,LIMITS

OUT=ARTIFACTS/'stages/05.2';MAINT=ARTIFACTS/'maintenance/storage-v2'


def complete():
    budget=json.loads((MAINT/'budget-check.json').read_text());assert not budget['errors']
    monitor=json.loads((OUT/'temporary-monitor.json').read_text());assert not monitor['running']
    assert temporary_bytes(ARTIFACTS)==0,'Owned scratch must be reconciled first'
    snapshot=inventory();assert not any(v['active'] for v in snapshot['leases'] if str(OUT) in v['path'])
    baseline=json.loads((OUT/'render-motion-baseline.json').read_text());rows={};max_case=0;retired_files=0;retired_bytes=0
    for rig in ('demo','mixamo'):
        supported=[name for name,id,_,_ in cases() if rig!='demo' or not id.startswith('shoulder.')]
        frames=0;media_bytes=0
        for name in supported:
            path=OUT/rig/name;assert render_complete(path,('front','side')),(rig,name)
            manifest,asset,motion=validate_manifest(path)
            previous=baseline['rigs'][rig][name]
            assert digest(motion)==previous['sha256'] and motion.stat().st_mtime_ns==previous['mtime_ns'],('Motion rewritten',rig,name)
            files={view['media']['path'] for view in manifest['views'].values()}
            assert {p.name for p in path.glob('*.mkv')}==files,('Extra media',rig,name)
            assert not any(p.stem.isdecimal() for view in ('front','side') for p in (path/view).glob('*.png'))
            frames+=len(manifest['expected_frames'])*2
            media_bytes+=sum((path/name).stat().st_size for name in files)
            size=motion.stat().st_size+(path/'preview-manifest.json').stat().st_size;assert size<=LIMITS['case'];max_case=max(max_case,size)
            retirement=json.loads((path/'media-retirement.json').read_text());assert retirement['state']=='complete'
            retired_files+=retirement['removed_files'];retired_bytes+=retirement['removed_bytes']
        rows[rig]={'cases':len(supported),'rendered_frames':frames,'lossless_movies':2*len(supported),'movie_bytes':media_bytes,'motion_bytes_and_mtimes_unchanged':True}
    assert sum(r['cases'] for r in rows.values())==197 and sum(r['rendered_frames'] for r in rows.values())==47006
    assert not list(OUT.rglob('failure-pin.json')),'An unresolved reproduction remains pinned'
    original=json.loads((MAINT/'baseline-files.json').read_text());protected=0
    for relative,record in original.items():
        parts=Path(relative).parts
        if len(parts)<3 or parts[:2] not in (('stages','05.1a'),('stages','05.1b')):continue
        if not (relative.endswith('.png') or Path(relative).name in ('result.json','profile.json')):continue
        path=ARTIFACTS/relative;stat=path.stat()
        assert stat.st_size==record['bytes'] and stat.st_mtime_ns==record['mtime_ns'],('Predecessor evidence changed',relative)
        protected+=1
    before=json.loads((OUT/'resume-inventory.json').read_text())
    stage_before=json.loads((MAINT/'stage-052-baseline.json').read_text())
    assets=list((ARTIFACTS/'assets').glob('*/avatar.blend'))
    assert len(assets)==3 and snapshot['by_stage']['assets']['bytes']==before['by_stage']['assets']['bytes']
    validation=json.loads((OUT/'validation-summary.json').read_text())
    assert sum(value['passed_cases'] for value in validation.values())==197
    visual=json.loads((OUT/'visual-review.json').read_text())
    assert len(visual['demo']['reviewed_cases'])==82 and len(visual['mixamo']['reviewed_cases'])==115
    unit_log=(OUT/'all-unit-final.log').read_text()
    assert '\nOK (skipped=12)' in unit_log and 'FAILED' not in unit_log
    assert json.loads((OUT/'resume-no-growth.json').read_text())['passed']
    enforce(OUT,growth=65536)
    atomic_json(OUT/'resume-checkpoint.json',{
        'status':'complete','stage':'05.2','date':'2026-10-29',
        'numeric_positive_cases':197,'explicit_unavailable_cases':33,
        'actual_motion_samples':23503,'rendered_frames':47006,
        'visual_reviewed_cases':{'demo':82,'mixamo':115},
        'completion_accounting':'completion-accounting.json',
        'receipt':'to do/stages/receipts/05.2.md',
        'uncommitted_changes_preserved':True,'next_stage_started':False})
    report={'owner':'stage-05.2-completion-accounting-v1','storage_complete':True,'before_resume':before,
            'before_stage':stage_before,'rigs':rows,'max_case_motion_manifest_bytes':max_case,
            'shared_assets':{'count':3,'bytes':snapshot['by_stage']['assets']['bytes'],'additions':0},
            'predecessor_png_numeric_profile_files_unchanged':protected,'unresolved_failure_pins':0,
            'current_media_transactions':{'retired_generated_files':retired_files,'retired_bytes':retired_bytes},
            'temporary':{'final_bytes':0,'observed_peak_bytes':monitor['peak_temporary_bytes'],'sample_count':monitor['samples'],
                         'batch_reserved_bytes':128*1024**2,'limit_bytes':LIMITS['temporary']},
            'limits':LIMITS,'exceptions':[],'generated_media_outside_artifacts':[]}
    target=OUT/'completion-accounting.json'
    # Include this bounded report itself in the final actual byte accounting.
    for _ in range(5):
        enforce(OUT,growth=65536)
        value=inventory();report['after']={key:item for key,item in value.items() if key!='files'}
        old_size=target.stat().st_size if target.exists() else None
        atomic_json(target,report)
        if old_size==target.stat().st_size:break
    final=inventory();assert final['bytes']<=LIMITS['global'] and final['by_stage']['05.2']['bytes']<=LIMITS['stage']
    print('SHOULDERS_ARMS_STORAGE_COMPLETE',json.dumps({'global_bytes':final['bytes'],'stage_bytes':final['by_stage']['05.2']['bytes'],
           'protected_files':protected,'movies':394,'rendered_frames':47006,'max_case_bytes':max_case}),flush=True)


if __name__=='__main__':complete()
