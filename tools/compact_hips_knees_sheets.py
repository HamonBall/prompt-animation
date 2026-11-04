"""Retain full movies and pixel-exact summary cells after actual full review.

CPU-only image assembly, no motion execution, rendering, avatar copies or resize.
Per-ID defaults retain complete sheets. Durable per-case proof precedes replacing
other inspected review aids; every original video frame remains unchanged.
"""
import sys,json,math,hashlib
from array import array
from pathlib import Path
import bpy
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.artifact_store import atomic_json,atomic_replace,digest,producer_lease
from tools.artifact_bundle import validate_manifest
from tools.storage_policy import enforce,confined
from tools.legs_evidence import OUT,numeric_valid
rig=sys.argv[sys.argv.index('--rig')+1];name=sys.argv[sys.argv.index('--case')+1];out=confined(OUT/rig/name)
assert rig in ('demo','mixamo')
target=out/'sheet-retention.json';review_path=OUT/'visual-review.json';key=rig+'/'+name
review=json.loads(review_path.read_text());inspected=review['cases'][key];assert inspected['actually_inspected']
manifest,asset,motion=validate_manifest(out);assert numeric_valid(out)
assert inspected['motion_sha256']==digest(motion) and inspected['media']=={v:m['media']['sha256'] for v,m in manifest['views'].items()}
before=(digest(motion),motion.stat().st_mtime_ns);source=digest(Path(__file__))
enforce(out,growth=4*1024**2,temporary=64*1024**2)
if name.endswith('.default.left') or name=='knee.pulse.default.both':
    inspected['retention_complete']=True;inspected['sheet_retention']='complete per-ID default sheets'
    atomic_json(review_path,review);print('KEPT_FULL_DEFAULT_SHEETS',key,flush=True);raise SystemExit(0)


def sha_pixels(pixels):return hashlib.sha256(array('f',pixels.ravel()).tobytes()).hexdigest()


def make_summary(label,frames,metadata):
    path=out/(label+'-sheet.png');width=metadata['media']['size'][0];count=len(manifest['expected_frames'])
    assert metadata['media']['size']==[width,width]
    rows=math.ceil(count/12);image=bpy.data.images.load(str(path),check_existing=False)
    candidate=out/('.candidate-'+label+'-summary.png');result=None
    try:
        assert list(image.size)==[12*width,rows*width]
        pixels=np.array(image.pixels[:],dtype=np.float32).reshape((rows*width,12*width,4))
        summary=np.zeros((width,width*len(frames),4),dtype=np.float32);summary[:,:,3]=1
        hashes=[]
        for index,frame in enumerate(frames):
            x=(frame-1)%12*width;y=(rows-1-(frame-1)//12)*width
            cell=pixels[y:y+width,x:x+width,:]
            expected=metadata['media']['decoded_pixel_sha256'][frame-1]
            assert sha_pixels(cell)==expected,('Full review sheet differs from verified source frame',key,label,frame)
            summary[:,index*width:(index+1)*width,:]=cell;hashes.append(expected)
        result=bpy.data.images.new('Owned reviewed summary',width*len(frames),width,alpha=True)
        result.pixels.foreach_set(summary.ravel())
        scene=bpy.context.scene;scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
        scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.compression=100
        result.save_render(str(candidate),scene=scene)
        check=bpy.data.images.load(str(candidate),check_existing=False)
        try:
            actual=np.array(check.pixels[:],dtype=np.float32).reshape((width,width*len(frames),4))
            for index,expected in enumerate(hashes):assert sha_pixels(actual[:,index*width:(index+1)*width,:])==expected
        finally:bpy.data.images.remove(check)
        return {'original_full_sheet_sha256':digest(path),'original_bytes':path.stat().st_size,
            'summary_sha256':digest(candidate),'summary_bytes':candidate.stat().st_size,'frames':frames,'pixel_sha256':hashes,
            'candidate':candidate.name,'path':path.name}
    finally:
        if result is not None:bpy.data.images.remove(result)
        bpy.data.images.remove(image)


with producer_lease(out):
    if target.exists():
        journal=json.loads(target.read_text());assert journal['owner']=='05.4-reviewed-sheet-retention'
        if journal['state']=='complete':
            assert (journal['motion_sha256'],journal['motion_mtime_ns'])==before
            assert journal['media']==inspected['media'] and journal['actually_inspected_complete_sheets']
            assert set(journal['views'])==set(manifest['views'])
            for label,record in journal['views'].items():
                assert digest(confined(out/record['path']))==record['summary_sha256']
                view=manifest['views'][label]['sheet_representation']
                assert view['full_sheet_sha256']==record['original_full_sheet_sha256']
                assert view['summary_sha256']==record['summary_sha256'] and view['pixel_identity_preserved']
            if not inspected['retention_complete']:
                original={label:r['original_full_sheet_sha256'] for label,r in journal['views'].items()}
                assert inspected['sheets']==original
                inspected['full_sheets']=original
                inspected['sheets']={label:r['summary_sha256'] for label,r in journal['views'].items()}
                inspected['sheet_retention']='selected original-resolution phase frames after complete-sheet inspection; all movie frames retained'
                inspected['retention_complete']=True
                atomic_json(review_path,review)
            print('REVIEW_SHEET_RETENTION_REUSED',key,flush=True);raise SystemExit(0)
    else:
        assert inspected['sheets']=={label:digest(out/(label+'-sheet.png')) for label in manifest['views']}
        executable=json.loads((out/'executable.json').read_text());tracks=executable['tracks']
        # All synchronized phase endpoints are retained at original resolution.
        frames=sorted({1,len(manifest['expected_frames']),*(round(t['interval']['end_s']*30)+1 for t in tracks if t['curve']['kind']=='transition')})
        assert frames and frames[-1]<=len(manifest['expected_frames'])
        journal={'owner':'05.4-reviewed-sheet-retention','state':'prepared','motion_sha256':before[0],
            'motion_mtime_ns':before[1],'media':inspected['media'],'frames_in_each_full_movie':len(manifest['expected_frames']),
            'actually_inspected_complete_sheets':True,'method':'Full-resolution cells, no resampling; each selected cell SHA equals its validated movie source frame',
            'validator_sha256':source,'views':{label:make_summary(label,frames,m) for label,m in manifest['views'].items()}}
        atomic_json(target,journal)
    assert journal['motion_sha256']==before[0] and journal['media']==inspected['media']
    for label,record in journal['views'].items():
        destination=confined(out/record['path']);candidate=confined(out/record['candidate'])
        if digest(destination)!=record['summary_sha256']:
            assert digest(destination)==record['original_full_sheet_sha256'] and digest(candidate)==record['summary_sha256']
            atomic_replace(candidate,destination)
        manifest['views'][label]['sheet_representation']={'kind':'selected_frames_after_full_review','frames':record['frames'],
            'full_sheet_sha256':record['original_full_sheet_sha256'],'summary_sha256':record['summary_sha256'],
            'pixel_identity_preserved':True}
    # The bundle's execution inputs/state and full-motion media are untouched.
    atomic_json(out/'preview-manifest.json',manifest)
    inspected['full_sheets']={label:r['original_full_sheet_sha256'] for label,r in journal['views'].items()}
    inspected['sheets']={label:r['summary_sha256'] for label,r in journal['views'].items()}
    inspected['sheet_retention']='selected original-resolution phase frames after complete-sheet inspection; all movie frames retained'
    inspected['retention_complete']=True;atomic_json(review_path,review)
    journal['state']='complete';atomic_json(target,journal)
    assert before==(digest(motion),motion.stat().st_mtime_ns) and source==digest(Path(__file__))
    print('REVIEWED_SHEETS_COMPACTED',key,sum(r['original_bytes']-r['summary_bytes'] for r in journal['views'].values()),flush=True)
