"""Close the Stage 05.4 storage gate after review and global budget checks."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from hips_knees_cases import cases
from tools.artifact_bundle import validate_manifest
from tools.artifact_store import atomic_json,digest
from tools.legs_evidence import OUT
from tools.storage_policy import ARTIFACTS,LIMITS,confined,inventory,temporary_bytes


def read(path):
    return json.loads(path.read_text())


def main():
    monitor=read(OUT/'temporary-monitor.json')
    assert not monitor['running'] and monitor['current_temporary_bytes']==0
    before=read(OUT/'storage-before.json')
    numeric=read(OUT/'validation-summary.json')
    replay=read(OUT/'saved-playback-summary.json')
    resume=read(OUT/'resume-no-growth.json')
    visual=read(OUT/'visual-review.json')
    keys={rig+'/'+name for rig in ('demo','mixamo') for name,_,_,_ in cases()}
    assert numeric['passed'] and replay['passed'] and resume['passed'] and visual['complete']
    assert all(set(data['cases'])==keys for data in (numeric,replay,visual))
    maintenance=ARTIFACTS/'maintenance/storage-v2'
    audit=read(maintenance/'hips-knees-evidence-audit.json')['stages']['05.4']
    assert sum(row['cases'] for row in audit.values())==len(keys)
    assert not read(maintenance/'budget-check.json')['errors']
    current=inventory()
    assert not current['leases'] and temporary_bytes(ARTIFACTS)==0
    allowed={'maintenance/storage-v2/budget-check.json','maintenance/storage-v2/current-inventory.json'}
    for name,row in before['files'].items():
        if name not in allowed:
            stat=(ARTIFACTS/name).stat()
            assert (stat.st_size,stat.st_mtime_ns)==(row['bytes'],row['mtime_ns']),name
    assert current['by_stage']['assets']==before['by_stage']['assets']
    assert not list(OUT.glob('*/development-*')) and not list(OUT.rglob('*.blend1'))
    assert all(p.name=='motion.blend' for p in OUT.rglob('*.blend'))
    assert not any(p.stem.isdecimal() for p in OUT.rglob('*.png'))
    max_case=movies=frames=full_sheets=selected_sheets=sheet_bytes_retired=0
    for key in sorted(keys):
        directory=OUT/key
        manifest,_,motion=validate_manifest(directory)
        review=visual['cases'][key]
        assert review['actually_inspected'] and review['retention_complete']
        assert review['motion_sha256']==numeric['cases'][key]['motion_sha256']==digest(motion)
        expected={v['media']['path'] for v in manifest['views'].values()}
        assert {p.name for p in directory.glob('*.mkv')}==expected
        assert len(expected)==2 and set(manifest['views'])=={'front','side'}
        for label,view in manifest['views'].items():
            assert review['media'][label]==view['media']['sha256']
            assert review['sheets'][label]==digest(directory/(label+'-sheet.png'))
            if 'sheet_representation' in view:selected_sheets+=1
            else:full_sheets+=1
        sheet_journal=directory/'sheet-retention.json'
        if sheet_journal.exists():
            record=read(sheet_journal)
            assert record['state']=='complete'
            sheet_bytes_retired+=sum(v['original_bytes']-v['summary_bytes'] for v in record['views'].values())
        movies+=len(expected)
        frames+=len(expected)*len(manifest['expected_frames'])
        max_case=max(max_case,motion.stat().st_size+(directory/'preview-manifest.json').stat().st_size)
    assert frames==2*numeric['samples']==2*replay['samples']
    assert max_case<=LIMITS['case']
    for path in list(OUT.rglob('.scratch')):
        children=sorted(path.rglob('*'),key=lambda p:len(p.parts),reverse=True)
        assert all(p.is_dir() for p in children)
        for child in children:confined(child,OUT).rmdir()
        confined(path,OUT).rmdir()
    for name,record in resume['payloads'].items():
        path=ARTIFACTS/name
        stat=path.stat()
        assert (digest(path),stat.st_size,stat.st_mtime_ns)==(record['sha256'],record['bytes'],record['mtime_ns'])
    fixture_bytes=sum(p.stat().st_size for p in (ROOT/'tests/fixtures/hips_knees').rglob('*') if p.is_file())
    assert fixture_bytes>0
    caches=sum(p.stat().st_size for folder in ('src','tests','tools') for p in (ROOT/folder).rglob('*.pyc'))
    reservation=read(OUT/'render-batch-preflight.json')['concurrent_temporary_reservation_bytes']
    assert max(reservation,monitor['peak_temporary_bytes'])<=LIMITS['temporary']
    readme=digest(ROOT/'README.md')
    assert readme=='57dd7de96640eb40e5a6ac4541edc6c8e1784e693ead5ee970754be8238059ab'
    retired=[record for rows in read(OUT/'development-retirement.json')['cases'].values() for record in rows]
    for journal in (OUT/'retention-journals').glob('retired-*.json'):
        retired.extend(read(journal)['operations'])
    assert retired and all(record['state']=='complete' for record in retired)
    retired_files=[file for record in retired for file in record['files'].values()]
    report={'stage':'05.4','storage_complete':True,'before':{k:v for k,v in before.items() if k!='files'},
            'preserved_predecessor_files':len(set(before['files'])-allowed),
            'maintenance_refreshes':sorted(allowed),'cases':len(keys),'motion_samples':numeric['samples'],
            'movies':movies,'movie_frames':frames,'full_sheets':full_sheets,'selected_sheets':selected_sheets,
            'retirement':{'development_operations':len(retired),'development_files':len(retired_files),
                          'development_bytes':sum(row['bytes'] for row in retired_files),
                          'review_sheet_net_bytes_reclaimed':sheet_bytes_retired},
            'max_case_motion_manifest_bytes':max_case,'outside_artifact_root':{'fixtures':fixture_bytes,'local_code_caches':caches},
            'temporary':{**monitor,'final_bytes':0,'concurrent_reservation_bytes':reservation},
            'limits':LIMITS,'readme_sha256':readme,'shared_asset_additions_bytes':0}
    target=OUT/'completion-accounting.json'
    for _ in range(4):
        current=inventory()
        report['after']={k:v for k,v in current.items() if k not in ('files','free_bytes')}
        report['conservative_stage_total_bytes']=current['by_stage']['05.4']['bytes']+fixture_bytes+caches
        report['conservative_global_total_bytes']=current['bytes']+fixture_bytes+caches
        assert report['conservative_stage_total_bytes']<=LIMITS['stage']
        assert report['conservative_global_total_bytes']<=LIMITS['global']
        atomic_json(target,report)
        if inventory()['bytes']==current['bytes']:break
    else:
        raise RuntimeError('Accounting report size did not stabilize')
    print('LEGS_STORAGE_AND_PRESERVATION_PASSED',report['conservative_stage_total_bytes'],flush=True)


if __name__=='__main__':main()
