"""Prepare bounded review pages; this never marks an image inspected."""
import argparse,json,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.hands_evidence_cases import cases,detail_cases
from tools.artifact_store import atomic_json,digest
from tools.hands_render_state import render_complete
from tools.storage_policy import enforce
OUT=ROOT/'artifacts/stages/05.3a'
parser=argparse.ArgumentParser();parser.add_argument('--available',action='store_true')
parser.add_argument('--kind',choices=('full','detail','all'),default='all');args=parser.parse_args()
font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',21)
index=json.loads((OUT/'visual-index.json').read_text()) if (OUT/'visual-index.json').exists() else {}
for rig in ('demo','mixamo'):
    index.setdefault(rig,{})
    for kind,views in (('full',('front','side')),('detail',('hand-front','hand-side'))):
        if args.kind not in ('all',kind):continue
        ready=[]
        for name,id,parameters,pose in (detail_cases() if kind=='detail' else cases()):
            path=OUT/rig/name
            complete=render_complete(path,views)
            if not args.available:assert complete,(rig,name,'Incomplete visual source',kind)
            manifest=json.loads((path/'preview-manifest.json').read_text());frames=manifest['expected_frames']
            numbers=sorted({round(i*(len(frames)-1)/7) for i in range(8)})
            ready.append((name,pose,frames,numbers,complete))
        pages=[]
        for start in range(0,len(ready),8):
            group=ready[start:start+8]
            if not all(row[4] for row in group):continue
            enforce(OUT,growth=10*1024**2,temporary=10*1024**2)
            page=Image.new('RGB',(2048,40+174*len(group)),(27,30,34));draw=ImageDraw.Draw(page)
            draw.text((12,4),rig+' | '+kind+' | full timeline samples | paired views',font=font,fill='white');sources={}
            for row,(name,pose,frames,numbers,complete) in enumerate(group):
                y=40+row*174;draw.text((12,y),name+' | '+pose,font=font,fill=(230,235,240));sources[name]={}
                for side,view in enumerate(views):
                    source=OUT/rig/name/(view+'-sheet.png');sources[name][view]=digest(source)
                    with Image.open(source) as sheet:
                        assert sheet.width%128==0;columns=sheet.width//128
                        for column,number in enumerate(numbers):
                            x=number%columns*128;z=number//columns*128
                            page.paste(sheet.crop((x,z,x+128,z+128)).convert('RGB'),(column*256+side*128,y+28))
                for column,number in enumerate(numbers):draw.text((column*256+4,y+151),str(frames[number]),fill=(200,205,210))
            target=OUT/('review-'+kind)/(rig+'-'+str(start//8+1).zfill(2)+'.png');target.parent.mkdir(exist_ok=True);page.save(target)
            pages.append({'path':target.relative_to(OUT).as_posix(),'sha256':digest(target),'cases':[v[0] for v in group],
                          'source_sheets':sources,'timeline_frames':{v[0]:[v[2][i] for i in v[3]] for v in group}})
        index[rig][kind]={'pages':pages,'cases':sum(len(p['cases']) for p in pages),'expected_cases':len(ready)}
atomic_json(OUT/'visual-index.json',index)
print(json.dumps({rig:{kind:len(value['pages']) for kind,value in kinds.items()} for rig,kinds in index.items()}))
