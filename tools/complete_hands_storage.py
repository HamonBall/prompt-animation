"""Final retention, predecessor preservation and whole-root accounting for 05.3a."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.artifact_store import atomic_json,digest
from tools.artifact_bundle import validate_manifest,recover_bundle
from tools.lossless_evidence import recover_evidence
from tools.storage_policy import ARTIFACTS,inventory,temporary_bytes,enforce,LIMITS,active_writer,confined
from tools.hands_evidence_cases import cases,detail_cases
from tools.hands_render_state import render_complete
OUT=ARTIFACTS/'stages/05.3a'


def retire_development():
    journal_path=OUT/'development-history-retirement.json'
    journal=json.loads(journal_path.read_text()) if journal_path.exists() else {'owner':'stage-05.3a-development-history','cases':{}}
    for old,new in (('forearm.twist.palms-up','forearm.twist.palms-up.straight'),('forearm.twist.palms-down','forearm.twist.palms-down.straight')):
        directory=OUT/'demo'/old;replacement=OUT/'demo'/new
        if not directory.exists():continue
        assert render_complete(replacement,('front','side','hand-front','hand-side'))
        _,asset,motion=validate_manifest(replacement);assert not active_writer(directory)
        inv=inventory(directory);records={}
        for relative,record in inv['files'].items():
            path=confined(directory/relative)
            assert path.suffix in ('.json','.blend','.log'),('Unexpected development payload; preserve',path)
            records[relative]={'bytes':record['bytes'],'sha256':digest(path)}
        journal['cases'][old]={'replacement':str(replacement.relative_to(ARTIFACTS)),'replacement_motion_sha256':digest(motion),
            'reason':'Superseded unreviewed development fixture; replacement checks explicit actual palm-up/down normals. Distinct motion is not claimed equivalent.',
            'files':records,'state':'prepared'}
        atomic_json(journal_path,journal)
        assert directory.resolve().is_relative_to(OUT.resolve())
        for relative,record in records.items():
            path=confined(directory/relative);assert digest(path)==record['sha256'];path.unlink()
        for path in sorted(directory.rglob('*'),key=lambda p:len(p.parts),reverse=True):
            if path.is_dir():path.rmdir()
        directory.rmdir();journal['cases'][old]['state']='complete';atomic_json(journal_path,journal)
    return journal


def complete():
    monitor=json.loads((OUT/'temporary-monitor.json').read_text());assert not monitor['running']
    assert temporary_bytes(ARTIFACTS)==0,'Reconcile owned scratch first'
    current=inventory();assert not any(v['active'] and str(OUT) in v['path'] for v in current['leases'])
    summary=json.loads((OUT/'validation-summary.json').read_text());rows={};max_case=0;movies=0;frames=0
    detail_names={row[0] for row in detail_cases()}
    for rig in ('demo','mixamo'):
        assert not summary[rig]['pending'];n=0
        for name,_,_,_ in cases():
            out=OUT/rig/name;recover_bundle(out);recover_evidence(out)
            assert render_complete(out,('front','side'))
            manifest,asset,motion=validate_manifest(out);previous=summary[rig]['cases'][name]
            if name in detail_names:
                assert render_complete(out,('front','side','hand-front','hand-side'))
                assert all(manifest['views'][v].get('renderer_sha256')==digest(ROOT/'tools/render_hands_details.py')
                           for v in ('hand-front','hand-side'))
            assert digest(motion)==previous['motion_sha256'] and motion.stat().st_mtime_ns==previous['motion_mtime_ns']
            expected={view['media']['path'] for view in manifest['views'].values()}
            assert {p.name for p in out.glob('*.mkv')}==expected,('Extra owned movie',out)
            assert not any(p.stem.isdecimal() for view in manifest['views'] for p in (out/view).glob('*.png'))
            size=motion.stat().st_size+(out/'preview-manifest.json').stat().st_size;assert size<=LIMITS['case'];max_case=max(max_case,size)
            movies+=len(expected);frames+=len(expected)*len(manifest['expected_frames']);n+=1
        rows[rig]={'cases':n,'motion_samples':summary[rig]['samples']}
    history=retire_development();before=json.loads((OUT/'storage-before.json').read_text());preserved=0;allowed=[]
    for relative,record in before['files'].items():
        path=ARTIFACTS/relative
        if relative in ('maintenance/storage-v2/budget-check.json','maintenance/storage-v2/current-inventory.json'):
            allowed.append(relative);continue
        stat=path.stat();assert stat.st_size==record['bytes'] and stat.st_mtime_ns==record['mtime_ns'],('Predecessor changed',relative)
        preserved+=1
    budget=json.loads((ARTIFACTS/'maintenance/storage-v2/budget-check.json').read_text());assert not budget['errors']
    assert json.loads((OUT/'resume-no-growth.json').read_text())['passed']
    assert not list(OUT.rglob('failure-pin.json'))
    assert not list(OUT.rglob('*.blend1'))
    assert all(path.name=='motion.blend' for path in OUT.rglob('*.blend')),'Unexpected standalone avatar/scene copy'
    for path in sorted(OUT.rglob('.scratch'),key=lambda p:len(p.parts),reverse=True):
        assert not any(p.is_file() for p in path.rglob('*')),('Owned scratch remains',path)
        for child in sorted(path.rglob('*'),key=lambda p:len(p.parts),reverse=True):
            if child.is_dir():child.rmdir()
        path.rmdir()
    caches=sum(p.stat().st_size for name in ('src','tests','tools') for p in (ROOT/name).rglob('*.pyc'))
    fixtures=sum(p.stat().st_size for p in (ROOT/'tests/fixtures/elbows_wrists_hands').rglob('*') if p.is_file())
    retired_files=sum(len(v['files']) for v in history['cases'].values());retired_bytes=sum(x['bytes'] for v in history['cases'].values() for x in v['files'].values())
    report={'stage':'05.3a','storage_complete':True,'before':{k:v for k,v in before.items() if k!='files'},'rigs':rows,
        'rendered_frames':frames,'retained_movies':movies,'max_case_motion_manifest_bytes':max_case,
        'preserved_predecessor_files':preserved,'explicitly_refreshed_maintenance_reports':allowed,
        'shared_asset_additions':0,'retired_development_files':retired_files,'retired_development_bytes':retired_bytes,
        'temporary':{'final_bytes':0,'observed_peak_bytes':monitor['peak_temporary_bytes'],'observations':monitor['samples'],
                     'measurement_scope':monitor.get('measurement_scope','Shared scratch and pending files'),
                     'recorded_monitor_restarts':monitor.get('restarts',[]),
                     'reserved_concurrent_bytes':256*1024**2,'continuous_peak_claimed':False,
                     'monitoring_limitations':'Interrupted observations, including 2026-10-30 09:28:29 to 09:50:48 UTC and a later restart. Per-write budget guards remained enabled.'},
        'outside_artifact_root':{'versioned_hand_fixture_bytes':fixtures,'all_local_source_code_cache_bytes_conservatively_counted':caches,'generated_media':[]},
        'limits':LIMITS,'exceptions':[],'unresolved_failure_pins':0}
    for _ in range(4):
        after=inventory();stage_bytes=after['by_stage']['05.3a']['bytes']
        assert after['by_stage']['assets']['bytes']==before['by_stage']['assets']['bytes']
        assert after['bytes']+fixtures+caches<=LIMITS['global'] and stage_bytes+fixtures+caches<=LIMITS['stage']
        enforce(OUT,growth=16384);report['after']={k:v for k,v in after.items() if k!='files'}
        report['conservative_stage_total_bytes']=stage_bytes+fixtures+caches;report['conservative_global_total_bytes']=after['bytes']+fixtures+caches
        atomic_json(OUT/'completion-accounting.json',report)
    print('HANDS_STORAGE_AND_PRESERVATION_PASSED',report['conservative_stage_total_bytes'],flush=True)


if __name__=='__main__':complete()
