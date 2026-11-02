"""Whole-tree preservation, owned-history retirement and budget accounting."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.artifact_store import atomic_json,digest,render_complete
from tools.artifact_bundle import validate_manifest
from tools.storage_policy import ARTIFACTS,inventory,temporary_bytes,LIMITS,enforce,confined,active_writer
from finger_cases import cases
from tools.fingers_visual_valid import validate_visual_reviews
from tools.fingers_runtime import validate as validate_runtime
OUT=ARTIFACTS/'stages/05.3b'


def retire_pilot():
    old=OUT/'mixamo/development-fist-before-api';new=OUT/'mixamo/gesture.fist.neutral';target=OUT/'development-history-retirement.json'
    if not old.exists():return json.loads(target.read_text())
    manifest,_,motion=validate_manifest(new);assert render_complete(new,tuple(manifest['views']))
    validate_visual_reviews()
    numeric=json.loads((OUT/'validation-summary.json').read_text())
    assert numeric['passed'] and digest(motion)==numeric['cases']['gesture.fist.neutral']['motion_sha256']
    assert not active_writer(old) and not (old/'.artifact-writer.lock').exists()
    original=json.loads((OUT/'development-pilot.json').read_text())['files'];files={}
    for path in old.iterdir():
        assert path.is_file() and path.suffix in ('.json','.blend','.log')
        assert digest(path)==original[path.name]
        files[path.name]={'bytes':path.stat().st_size,'sha256':digest(path)}
    assert set(files)==set(original)
    journal={'owner':'stage-05.3b','reason':'Superseded unreviewed pre-API pilot; accepted current-profile/catalog replacement independently validated and visually reviewed',
        'state':'prepared','replacement_motion_sha256':digest(motion),'files':files}
    atomic_json(target,journal)
    assert old.resolve().is_relative_to(OUT.resolve())
    for name,record in files.items():
        path=confined(old/name);assert digest(path)==record['sha256'];path.unlink()
    old.rmdir();journal['state']='complete';atomic_json(target,journal);return journal


def main():
    validate_runtime()
    monitor=json.loads((OUT/'temporary-monitor.json').read_text());assert not monitor['running']
    assert temporary_bytes(ARTIFACTS)==0
    before=json.loads((OUT/'storage-before.json').read_text());summary=json.loads((OUT/'validation-summary.json').read_text())
    visual=validate_visual_reviews()
    assert summary['passed'] and json.loads((OUT/'resume-no-growth.json').read_text())['passed']
    assert not any(row['active'] for row in inventory()['leases'])
    migration=json.loads((OUT/'floor-isolation-migration.json').read_text())
    assert migration['current_renderer_sha256']==digest(ROOT/'tools/render_fingers.py')
    preserved_body_movies=0
    movies=frames=max_case=0
    for name,_,_,_ in cases():
        out=OUT/'mixamo'/name;manifest,asset,motion=validate_manifest(out)
        assert render_complete(out,tuple(manifest['views']))
        assert digest(motion)==summary['cases'][name]['motion_sha256'] and motion.stat().st_mtime_ns==summary['cases'][name]['motion_mtime_ns']
        original=migration['cases'][name]
        assert digest(motion)==original['motion_sha256'] and motion.stat().st_mtime_ns==original['motion_mtime_ns']
        for label in ('front','side'):
            assert manifest['views'][label]==original['full_body_views'][label]
        for label,mtime in original['full_body_payload_mtimes_ns'].items():
            assert (out/manifest['views'][label]['media']['path']).stat().st_mtime_ns==mtime
            preserved_body_movies+=1
        assert all(v.get('renderer_sha256')==digest(ROOT/'tools/render_fingers.py') for k,v in manifest['views'].items() if k not in ('front','side'))
        expected={v['media']['path'] for v in manifest['views'].values()};assert {p.name for p in out.glob('*.mkv')}==expected
        movies+=len(expected);frames+=len(expected)*len(manifest['expected_frames'])
        max_case=max(max_case,motion.stat().st_size+(out/'preview-manifest.json').stat().st_size)
        assert not any(p.stem.isdecimal() for p in out.glob('*/*.png'))
    history=retire_pilot()
    # Only empty, owned scratch directories; all payload retirement is shared/journalled.
    for path in sorted(OUT.rglob('.scratch'),key=lambda p:len(p.parts),reverse=True):
        assert not any(p.is_file() for p in path.rglob('*'))
        assert path.resolve().is_relative_to(OUT.resolve())
        for child in sorted(path.rglob('*'),key=lambda p:len(p.parts),reverse=True):
            if child.is_dir():child.rmdir()
        path.rmdir()
    assert not list(OUT.rglob('*.blend1')) and not list(OUT.rglob('failure-pin.json'))
    assert all(p.name=='motion.blend' for p in OUT.rglob('*.blend'))
    allowed=('maintenance/storage-v2/budget-check.json','maintenance/storage-v2/current-inventory.json');preserved=0
    for relative,record in before['files'].items():
        if relative in allowed:continue
        stat=(ARTIFACTS/relative).stat();assert stat.st_size==record['bytes'] and stat.st_mtime_ns==record['mtime_ns'],relative
        preserved+=1
    budget=json.loads((ARTIFACTS/'maintenance/storage-v2/budget-check.json').read_text());assert not budget['errors']
    fixture_bytes=sum(p.stat().st_size for p in (ROOT/'tests/fixtures/fingers').rglob('*') if p.is_file())
    caches=sum(p.stat().st_size for folder in ('src','tests','tools') for p in (ROOT/folder).rglob('*.pyc'))
    temporary_reservation=max(256*1024**2,
        json.loads((OUT/'page-selection.json').read_text())['combined_temporary_reservation_bytes'],
        json.loads((OUT/'page-assembly-resource-check.json').read_text())['concurrent_temporary_reservation_bytes'])
    assert temporary_reservation<=LIMITS['temporary']
    initial_readme='25aa821a1ff205577f521ba99af02af5fec677f2f3448dab862cfcf3f1a6bfe8'
    readme=ROOT/'README.md';readme_hash=digest(readme)
    # Preserve the concurrent title edit, never rewrite the frozen user file.
    restored_title=readme.read_bytes().replace(b'# Avatar Animation \r\n',b'# Avatar Animation prototype\r\n',1)
    assert readme_hash==initial_readme or (
        readme_hash=='57dd7de96640eb40e5a6ac4541edc6c8e1784e693ead5ee970754be8238059ab'
        and hashlib.sha256(restored_title).hexdigest()==initial_readme)
    report={'stage':'05.3b','storage_complete':True,'before':{k:v for k,v in before.items() if k!='files'},
        'preserved_predecessor_files':preserved,'explicit_maintenance_refresh_exceptions':list(allowed),
        'cases':len(cases()),'motion_samples':summary['samples'],'movies':movies,'rendered_frames':frames,
        'max_case_motion_manifest_bytes':max_case,'shared_asset_additions_bytes':0,'retired_files':len(history['files']),
        'retired_bytes':sum(x['bytes'] for x in history['files'].values()),'unresolved_failure_pins':0,'exceptions':[],
        'floor_view_correction':{'motion_payloads_preserved':len(cases()),'full_body_movies_preserved':preserved_body_movies},
        'outside_artifact_root':{'fixture_bytes':fixture_bytes,'all_local_code_caches_conservatively_counted_bytes':caches,'generated_media':[]},
        'README':{'initial_sha256':initial_readme,'current_sha256':readme_hash,'current_mtime_ns':readme.stat().st_mtime_ns,
            'concurrent_change':'title lost prototype; exact rest of initial bytes confirmed' if readme_hash!=initial_readme else None,
            'written_by_stage':False},
        'temporary':{'observed_peak_bytes':monitor['peak_temporary_bytes'],'observations':monitor['samples'],'final_bytes':0,
            'continuous_maximum_claimed':False,'maximum_concurrent_reservation_bytes':temporary_reservation,
            'earlier_unmonitored_numeric_pilot_reservation_bytes':32*1024**2},'limits':LIMITS,'README_preserved':True}
    assert max_case<=LIMITS['case']
    for _ in range(4):
        current=inventory();assert current['by_stage']['assets']==before['by_stage']['assets']
        report['after']={k:v for k,v in current.items() if k!='files'}
        report['conservative_stage_total_bytes']=current['by_stage']['05.3b']['bytes']+fixture_bytes+caches
        report['conservative_global_total_bytes']=current['bytes']+fixture_bytes+caches
        assert report['conservative_stage_total_bytes']<=LIMITS['stage'] and report['conservative_global_total_bytes']<=LIMITS['global']
        enforce(OUT,growth=16384);atomic_json(OUT/'completion-accounting.json',report)
    print('FINGERS_STORAGE_AND_PRESERVATION_PASSED',report['conservative_stage_total_bytes'],flush=True)


if __name__=='__main__':main()
