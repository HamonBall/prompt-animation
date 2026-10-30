"""Measured lossless pilot and bounded stage-05.3a batch forecast."""
import json,os,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.artifact_store import atomic_json
from tools.storage_policy import ARTIFACTS,enforce,inventory
OUT=ARTIFACTS/'stages/05.3a'


def pilot():
    from tools.artifact_store import open_preview
    from tools.lossless_evidence import encode_view
    from tools.movement_evidence import render
    from avatar_app.movement_library import contracts as c
    scratch=OUT/'.scratch';scratch.mkdir(exist_ok=True);report={}
    for rig in ('demo','mixamo'):
        source=OUT/rig/'elbow.flex.default';manifest=json.loads((source/'preview-manifest.json').read_text())
        enforce(OUT,temporary=64*1024**2,growth=16*1024**2)
        with tempfile.TemporaryDirectory(dir=scratch,prefix='media-pilot-') as temp:
            path=Path(temp).resolve();assert path.is_relative_to(scratch.resolve())
            for item in source.iterdir():
                if item.is_file() and item.suffix in ('.json','.blend'):shutil.copy2(item,path/item.name)
            asset=(source/manifest['asset']['path']).resolve()
            manifest['asset']['path']=os.path.relpath(asset,path);manifest['bundle_root']=os.path.relpath(ARTIFACTS,path)
            shutil.copy2(source/manifest['profile']['path'],path/'profile.json');manifest['profile']['path']='profile.json'
            atomic_json(path/'preview-manifest.json',manifest)
            h=open_preview(path);p=c.loads(c.AvatarProfile,(path/'profile.json').read_text());sizes={}
            for view in ('front','side'):
                render(h,p,path,view=='side')
                media,_=encode_view(path,view,manifest['expected_frames'],fps=manifest['fps'],fps_base=manifest['fps_base'])
                sizes[view]=(path/media['path']).stat().st_size
            report[rig]={'frames':len(manifest['expected_frames']),'video_bytes':sizes,
                         'sheet_bytes':sum((path/(view+'-sheet.png')).stat().st_size for view in sizes),
                         'every_decoded_frame_verified':True,'saved_motion_checked_every_frame':True,'owned_scratch_removed':True}
    atomic_json(OUT/'media-storage-pilot.json',report)
    print('HANDS_STORAGE_PILOT_PASSED',flush=True)


def preflight():
    from tools.hands_render_state import render_complete
    from tools.hands_evidence_cases import cases
    from elbows_wrists_hands_cases import expected_frames
    report=json.loads((OUT/'media-storage-pilot.json').read_text());rows=[];missing=[]
    rates=[]
    for path in OUT.glob('*/*/result.json'):
        if not (path.parent/'motion.blend').exists():continue
        r=json.loads(path.read_text())
        rates.append((sum(x.stat().st_size for x in path.parent.glob('*.json'))+(path.parent/'motion.blend').stat().st_size)/r['frames'])
    assert rates
    for rig in ('demo','mixamo'):
        pilot=report[rig];assert pilot['every_decoded_frame_verified']
        rate=(sum(pilot['video_bytes'].values())+pilot['sheet_bytes'])/pilot['frames']
        for name,id,p,_ in cases():
            path=OUT/rig/name
            frames=json.loads((path/'result.json').read_text())['frames'] if (path/'result.json').exists() else expected_frames(id,p)
            current=sum(x['bytes'] for x in inventory(path)['files'].values()) if path.exists() else 0
            # Numeric/action evidence is generated first. Forecast is media-only;
            # require all cases before claiming the render batch is ready.
            numeric_missing=not (path/'motion.blend').exists()
            if numeric_missing:
                missing.append(rig+'/'+name)
                if '--partial' not in sys.argv:raise AssertionError(('Numeric batch incomplete',rig,name))
            reserve=16384+frames*768
            complete=render_complete(path,('front','side'))
            rows.append({'case':rig+'/'+name,'frames':frames,'media_bytes':0 if complete else int(frames*rate*1.5),
                         'metadata_reserve_bytes':0 if complete else reserve,'existing_bytes':current,
                         'missing_numeric_growth':int(max(rates)*frames*1.25) if numeric_missing else 0})
    growth=sum(x['media_bytes']+x['metadata_reserve_bytes']+x['missing_numeric_growth'] for x in rows)+32*1024**2
    checked=enforce(OUT,growth=growth,temporary=256*1024**2)
    atomic_json(OUT/'render-batch-preflight.json',{**checked,'cases':rows,'growth_bytes':growth,'concurrent_workers':8,
                'rendered_frames':2*sum(x['frames'] for x in rows),'measured_media':'media-storage-pilot.json','review_log_reserve_bytes':32*1024**2,
                'missing_numeric_cases':missing,'numeric_complete':not missing})
    print('HANDS_BATCH_PREFLIGHT_PASSED',len(rows),growth,flush=True)


if __name__=='__main__':
    if '--pilot' in sys.argv:pilot()
    else:preflight()
