"""Render review indexes from complete sheets; never claims human inspection."""
import sys,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from finger_cases import cases
from tools.artifact_store import atomic_json,digest
from tools.storage_policy import enforce
OUT=ROOT/'artifacts/stages/05.3b'


def main():
    # Blender's bundled Pillow is not required; use its native image buffers.
    import bpy,numpy as np
    bpy.context.scene.view_settings.view_transform='Standard'
    bpy.context.scene.view_settings.look='None'
    bpy.context.scene.render.dither_intensity=0
    pages=OUT/'review-pages';pages.mkdir(exist_ok=True)
    existing=OUT/'visual-index.json'
    index=json.loads(existing.read_text()) if existing.exists() else {'cases':{},'generator_sha256':digest(Path(__file__))}
    assert index['generator_sha256']==digest(Path(__file__))
    for name,_,parameters,_ in cases():
        out=OUT/'mixamo'/name;manifest=json.loads((out/'preview-manifest.json').read_text())
        if not manifest['complete']:continue
        if name in index['cases'] and all(digest(OUT/row['path'])==row['sha256'] and all(digest(OUT/path)==sha for path,sha in row['sheets'].items()) for row in index['cases'][name]):continue
        labels=tuple(manifest['views']);records=[]
        for view in labels:
            path=out/(view+'-sheet.png');image=bpy.data.images.load(str(path),check_existing=False)
            width,height=image.size;pixels=np.array(image.pixels[:],dtype=np.float32).reshape((height,width,4))
            bpy.data.images.remove(image);records.append((view,path,width,height,pixels))
        # Two equal-width full sheets per page, without removing any motion frame.
        targets=[]
        groups=[records[:2]]+[records[i:i+2] for i in range(2,len(records),2)]
        for number,group in enumerate(groups):
            width=max(row[2] for row in group);height=sum(row[3] for row in group)
            enforce(OUT,growth=width*height*4+65536,temporary=width*height*16+65536)
            pixels=np.zeros((height,width,4),dtype=np.float32);pixels[:,:,3]=1;y=height
            for view,path,w,h,data in group:y-=h;pixels[y:y+h,:w]=data
            target=pages/(name+'.'+str(number)+'.png');image=bpy.data.images.new('Owned complete review page',width,height,alpha=True)
            image.pixels.foreach_set(pixels.ravel());image.save_render(str(target));bpy.data.images.remove(image)
            targets.append({'path':target.relative_to(OUT).as_posix(),'sha256':digest(target),'views':[row[0] for row in group],
                'sheets':{row[1].relative_to(OUT).as_posix():digest(row[1]) for row in group}})
        index['cases'][name]=targets
    atomic_json(OUT/'visual-index.json',index);print('FINGERS_REVIEW_PAGES_CREATED',sum(len(v) for v in index['cases'].values()),flush=True)


if __name__=='__main__':main()
