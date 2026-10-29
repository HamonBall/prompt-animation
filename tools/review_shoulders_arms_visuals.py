"""Bounded review pages sampled from retained complete front/side contact sheets.

This tool prepares evidence; it never records human/agent visual acceptance.
"""
import json
from pathlib import Path
import sys
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from shoulders_arms_cases import cases
from avatar_app.movement_library.limbs import IDS
from tools.artifact_store import atomic_json,render_complete,digest
from tools.storage_policy import enforce

OUT=ROOT/'artifacts/stages/05.2'


def make_pages():
    index={};font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',21)
    for rig in ('demo','mixamo'):
        ready=[];pending=[]
        for name,id,parameters,pose in cases():
            if rig=='demo' and id.startswith('shoulder.'):continue
            path=OUT/rig/name
            if not render_complete(path,('front','side')):
                pending.append(name);continue
            m=json.loads((path/'preview-manifest.json').read_text())
            frames=m['expected_frames'];numbers=sorted({round(i*(len(frames)-1)/7) for i in range(8)})
            ready.append((name,pose,m,numbers))
        families={id:[v for v in ready if v[0].startswith(id+'.')] for id in IDS}
        expected={id:sum(1 for _,kind,_,_ in cases() if kind==id and (rig!='demo' or not id.startswith('shoulder.'))) for id in IDS}
        complete=[id for id in IDS if expected[id] and len(families[id])==expected[id]]
        pending.extend(v[0] for id in IDS if id not in complete for v in families[id])
        ready=[v for id in complete for v in families[id]]
        groups=[(id,start,families[id][start:start+8]) for id in complete for start in range(0,len(families[id]),8)]
        pages=[]
        for id,start,group in groups:
            enforce(OUT,growth=2048*1432*3,temporary=2048*1432*3)
            page=Image.new('RGB',(2048,40+len(group)*174),(27,30,34));draw=ImageDraw.Draw(page)
            draw.text((12,4),rig+' | full timeline samples, front / side',font=font,fill='white')
            for row,(name,pose,m,numbers) in enumerate(group):
                y=40+row*174
                draw.text((12,y),name+' | '+pose+' entry',font=font,fill=(230,235,240))
                for side,view in enumerate(('front','side')):
                    record=m['views'][view];width,height=record['resolution'][:2]
                    assert width==height==128,'Review does not silently resize evidence'
                    with Image.open(OUT/rig/name/(view+'-sheet.png')) as sheet:
                        columns=sheet.width//width
                        assert sheet.width%width==0 and sheet.height>=((len(m['expected_frames'])+columns-1)//columns)*height
                        for column,number in enumerate(numbers):
                            x=number%columns*width;z=number//columns*height
                            tile=sheet.crop((x,z,x+width,z+height)).convert('RGB')
                            page.paste(tile,(column*256+side*128,y+28))
                for column,number in enumerate(numbers):draw.text((column*256+4,y+151),str(m['expected_frames'][number]),fill=(200,205,210))
            target=OUT/f'{rig}-{id}-review-{start//8+1:02d}.png';page.save(target)
            enforce(OUT)
            if not pages:
                # The first page is a bounded pilot; use its measured encoded
                # size for the remaining batch, retaining per-page hard checks.
                enforce(OUT,growth=int(target.stat().st_size*1.5*(len(groups)-1)),temporary=2048*1432*3)
            pages.append({'path':target.relative_to(OUT).as_posix(),'sha256':digest(target),'cases':[v[0] for v in group],
                          'source_sheets':{v[0]:{view:digest(OUT/rig/v[0]/(view+'-sheet.png')) for view in ('front','side')} for v in group}})
        index[rig]={'pages':pages,'pending':pending,'ready_cases':len(ready),'complete_families':complete}
    atomic_json(OUT/'visual-index.json',index)
    print(json.dumps({rig:{'ready':v['ready_cases'],'pending':len(v['pending']),'pages':len(v['pages'])} for rig,v in index.items()}))


if __name__=='__main__':make_pages()
