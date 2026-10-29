"""Build labelled review pages from the actual rendered front/side frames.

Uses Pillow from the development workspace runtime, not the application runtime.
Every case spans its complete timeline; full numbered frames remain alongside it.
"""
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from spine_pelvis_cases import cases
from tools.artifact_store import render_complete
from avatar_app.movement_library import contracts as c
from avatar_app.movement_library.compiler import build_fragment
from avatar_app.movement_library.joints import catalog_for_profile
from avatar_app.motion import Surface

OUT=ROOT/'artifacts/stages/05.1b'
font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',22)

def make_pages():
    index={}
    entry_kinds={name:pose for name,id,parameters,pose in cases()}
    for rig in ('demo','mixamo'):
        ready=[];pending=[]
        profile=c.loads(c.AvatarProfile,(OUT/rig/'profile.json').read_text());catalog=catalog_for_profile(profile)
        for name,id,p,pose in cases():
            path=OUT/rig/name;marker=path/'visual-source.json'
            if not render_complete(path,('front','side'),allow_legacy=True):
                pending.append(name);continue
            entry=c.loads(c.MotionStateSnapshot,(path/'entry.json').read_text())
            instance=c.loads(c.MovementInstance,(path/'instance.json').read_text())
            saved=c.loads(c.MotionFragment,(path/'fragment.json').read_text())
            if build_fragment(instance,entry,profile,(Surface(),),catalog)!=saved:
                pending.append(name);continue
            result=json.loads((path/'result.json').read_text());count=result['frames']
            numbers=sorted({round(i*(count-1)/7)+1 for i in range(8)})
            ready.append((name,numbers))
        pages=[]
        for start in range(0,len(ready),8):
            group=ready[start:start+8];page=Image.new('RGB',(2048,40+len(group)*174),(27,30,34));draw=ImageDraw.Draw(page)
            draw.text((12,4),rig+' — full-cycle review, paired front / side views',font=font,fill='white')
            for row,(name,numbers) in enumerate(group):
                y=40+row*174;draw.text((12,y),name+' | '+('default parameters; ' if name.endswith('.default') else '')+('neutral entry' if entry_kinds[name] in ('neutral','free-space') else 'authored non-neutral entry'),font=font,fill=(230,235,240))
                for column,number in enumerate(numbers):
                    for side,view in enumerate(('front','side')):
                        path=OUT/rig/name/view/f'{number:04d}.png'
                        with Image.open(path) as image:page.paste(image.convert('RGB'),(column*256+side*128,y+28))
                    draw.text((column*256+4,y+151),str(number),fill=(200,205,210))
            target=OUT/f'{rig}-review-{start//8+1:02d}.png';page.save(target)
            pages.append({'path':str(target),'cases':[name for name,_ in group]})
        index[rig]={'pages':pages,'pending':pending,'ready_cases':len(ready)}
    (OUT/'visual-index.json').write_text(json.dumps(index,indent=2))
    print(json.dumps({rig:{'ready':v['ready_cases'],'pending':len(v['pending']),'pages':len(v['pages'])} for rig,v in index.items()}))

if __name__=='__main__':make_pages()
