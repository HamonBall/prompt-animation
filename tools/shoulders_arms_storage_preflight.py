"""Measure representative lossless media and bound the complete 05.2 render batch."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.artifact_store import atomic_json
from tools.storage_policy import inventory,enforce,ARTIFACTS
from shoulders_arms_cases import cases,expected_frames

OUT=ARTIFACTS/'stages/05.2'


def pilot():
    from tools.lossless_evidence import encode_view
    from tools.artifact_store import open_preview
    from tools.movement_evidence import render
    from avatar_app.movement_library import contracts as c
    scratch=OUT/'.scratch';scratch.mkdir(exist_ok=True);report={}
    for rig in ('demo','mixamo'):
        source=OUT/rig/'arm.raise.default'
        manifest=json.loads((source/'preview-manifest.json').read_text())
        frames=manifest['expected_frames'];assert len(frames)==94
        enforce(OUT,temporary=64*1024**2,growth=16*1024**2)
        with tempfile.TemporaryDirectory(dir=scratch,prefix='media-pilot-') as temp:
            path=Path(temp).resolve();assert path.is_relative_to(scratch.resolve())
            if '--render' in sys.argv:
                for item in source.iterdir():
                    if item.is_file() and item.suffix in ('.json','.blend'):shutil.copy2(item,path/item.name)
                asset=(source/manifest['asset']['path']).resolve()
                manifest['asset']['path']=os.path.relpath(asset,path)
                manifest['bundle_root']=os.path.relpath(ARTIFACTS,path)
                shutil.copy2(source/manifest['profile']['path'],path/'profile.json')
                manifest['profile']['path']='profile.json'
                atomic_json(path/'preview-manifest.json',manifest)
                h=open_preview(path);h.scene.render.dither_intensity=0
                profile=c.loads(c.AvatarProfile,(path/'profile.json').read_text())
                render(h,profile,path);render(h,profile,path,True)
            sizes={};png_sizes={}
            for view in ('front','side'):
                if '--render' not in sys.argv:shutil.copytree(source/view,path/view)
                media,_=encode_view(path,view,frames,fps=manifest['fps'],fps_base=manifest['fps_base'])
                sizes[view]=(path/media['path']).stat().st_size
                png_sizes[view]=sum(p.stat().st_size for p in (path/view).glob('*.png'))
            report[rig]={'source':source.relative_to(ARTIFACTS).as_posix(),'frames':len(frames),
                'video_bytes':sizes,'source_png_bytes':png_sizes,
                'sheet_bytes':sum(((path if '--render' in sys.argv else source)/(v+'-sheet.png')).stat().st_size for v in sizes),
                'dither_intensity':0 if '--render' in sys.argv else 1,
                'every_decoded_frame_verified':True,'temporary_case_removed':True}
    atomic_json(OUT/'media-storage-pilot.json',report)
    print('SHOULDERS_ARMS_STORAGE_PILOT_PASSED',flush=True)


def preflight():
    from tools.artifact_store import input_identity,render_complete,files_complete
    report=json.loads((OUT/'media-storage-pilot.json').read_text());requests=[]
    selected=sys.argv[sys.argv.index('--case')+1] if '--case' in sys.argv else None
    selected_rig=sys.argv[sys.argv.index('--rig')+1] if selected and '--rig' in sys.argv else None
    producer=input_identity(OUT/'identity')['producer_sha256']
    immutable_names={'entry.json','instance.json','fragment.json','executable.json','result.json','motion.blend'}
    for rig in ('demo','mixamo'):
        if selected_rig and rig!=selected_rig:continue
        representative=report[rig];assert representative['every_decoded_frame_verified']
        media_rate=(sum(representative['video_bytes'].values())+representative['sheet_bytes'])/representative['frames']
        # Existing verified complete views add measured extreme cases to the pilot.
        for manifest in (OUT/rig).glob('*/preview-manifest.json'):
            value=json.loads(manifest.read_text());path=manifest.parent
            try:
                if value.get('complete') and all('media' in view for view in value.get('views',{}).values()) and files_complete(path,value):
                    size=sum((path/view['media']['path']).stat().st_size+(path/(name+'-sheet.png')).stat().st_size for name,view in value['views'].items())
                    media_rate=max(media_rate,size/len(value['expected_frames']))
            except OSError:continue  # Another producer may be committing this view.
        for name,id,parameters,pose in cases():
            if rig=='demo' and id.startswith('shoulder.'):continue
            if selected and name!=selected:continue
            path=OUT/rig/name
            manifest=json.loads((path/'preview-manifest.json').read_text())
            if '--skip-rendered' in sys.argv and manifest.get('inputs',{}).get('producer_sha256')==producer and render_complete(path,('front','side')):continue
            result=json.loads((path/'result.json').read_text());frames=result['frames']
            assert result['review']['passed'] and all((path/name).is_file() for name in immutable_names)
            existing=sum(p.stat().st_size for p in path.rglob('*') if p.is_file())
            # Render-only never serializes numeric data or motion again. Count
            # those exact immutable bytes, then reserve extra metadata (three
            # frame-hash copies and PNG recovery records) and 50% media headroom.
            immutable=sum((path/name).stat().st_size for name in immutable_names)
            metadata=sum(p.stat().st_size for p in path.glob('*.json') if p.name not in immutable_names)
            metadata_reserve=metadata+16384+frames*768
            predicted=int(immutable+metadata_reserve+frames*media_rate*1.5)
            requests.append({'case':rig+'/'+name,'frames':frames,'predicted_bytes':predicted,'existing_bytes':existing,
                             'immutable_bytes':immutable,'metadata_reserve_bytes':metadata_reserve,
                             'growth_bytes':max(0,predicted-existing)})
    growth=sum(v['growth_bytes'] for v in requests)
    # Include bounded review pages and logs. Two workers each render at most one
    # 280-frame case and encode one view at a time; 128 MiB reserves both.
    reserve=32*1024**2 if requests else 65536
    checked=enforce(OUT,growth=growth+reserve,temporary=128*1024**2 if requests else 0)
    atomic_json(OUT/'render-batch-preflight.json',{**checked,'cases':requests,'case_count':len(requests),
        'rendered_frames':2*sum(v['frames'] for v in requests),'review_and_log_reserve_bytes':reserve,
        'measured_media':'media-storage-pilot.json plus verified retained views','concurrent_workers':2,
        'immutable_motion_and_numeric_data_rewritten':False})
    print('SHOULDERS_ARMS_RENDER_BATCH_PREFLIGHT_PASSED',len(requests),growth,flush=True)


if __name__=='__main__':
    if '--pilot' in sys.argv:pilot()
    else:preflight()
