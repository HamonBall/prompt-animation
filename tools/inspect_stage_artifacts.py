"""Read-only audit of preserved movement evidence and explicit entry labels.

Writes a new maintenance report; never rebuilds motion or rewrites old receipts.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.artifact_store import atomic_json,scene_path,digest
from spine_pelvis_cases import cases as body_cases
from shoulders_arms_cases import cases as arm_cases


def check_frames(directory,views,count):
    """Check every expected frame using cached enumeration metadata.

    Original PNG byte totals are independently checked against the pre-migration
    inventory. Read sheet/endpoint headers here without reopening tens of
    thousands of unchanged images merely to count their presence.
    """
    manifest=directory/'preview-manifest.json'
    bundle=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    if any('media' in bundle.get('views',{}).get(view,{}) for view in views):
        from tools.artifact_store import files_complete
        assert bundle['expected_frames']==list(range(1,count+1)) and bundle['complete']
        assert all(view in bundle['views'] for view in views) and files_complete(directory,bundle),directory
        for view in views:
            with (directory/(view+'-sheet.png')).open('rb') as stream:assert stream.read(8)==b'\x89PNG\r\n\x1a\n'
        return
    expected={f'{frame:04d}.png' for frame in range(1,count+1)}
    for view in views:
        with os.scandir(directory/view) as stream:
            frames={entry.name:entry.stat(follow_symlinks=False).st_size for entry in stream
                    if entry.is_file(follow_symlinks=False) and entry.name.endswith('.png')}
        assert set(frames)==expected and all(size>8 for size in frames.values()),(directory,view)
        for path in (directory/(view+'-sheet.png'),directory/view/'0001.png',directory/view/f'{count:04d}.png'):
            with path.open('rb') as stream:assert stream.read(8)==b'\x89PNG\r\n\x1a\n',path


def audit(stages=('05.1a','05.1b')):
    report={'schema_version':2,'stages':{}}
    body={name:(parameters,entry) for name,id,parameters,entry in body_cases()}
    arms={name:(parameters,entry) for name,id,parameters,entry in arm_cases()}
    hands={}
    if '05.3a' in stages:
        from tools.hands_evidence_cases import cases as hand_cases
        hands={name:(parameters,entry) for name,id,parameters,entry in hand_cases()}
    for stage in stages:
        base=ROOT/'artifacts/stages'/stage
        head=json.loads((base/'execution-review.json').read_text(encoding='utf-8')) if stage=='05.1a' else None
        rigs={}
        for rig in ('demo','mixamo'):
            entries={}
            names=head[rig]['cases'] if head else {n:v for n,v in arms.items() if rig!='demo' or not n.startswith('shoulder.')} if stage=='05.2' else hands if stage=='05.3a' else body
            for name in names:
                directory=base/rig/name
                result=json.loads((directory/'result.json').read_text(encoding='utf-8'))
                assert result['review']['passed'] and len(result['samples'])==result['frames'],directory
                scene=scene_path(directory)
                bundle=None
                manifest=directory/'preview-manifest.json'
                if manifest.exists() and json.loads(manifest.read_text(encoding='utf-8')).get('schema_version')==2:
                    from tools.artifact_bundle import validate_manifest
                    bundle,asset,motion=validate_manifest(directory)
                    assert bundle.get('verification',{}).get('passed') or bundle.get('complete'),directory
                views=list(bundle['views']) if stage=='05.3a' else ['front','side'] if stage in ('05.1b','05.2') or name.endswith('default') or name in ('look-left','world-turn','tilt-left') else ['front']
                check_frames(directory,views,result['frames'])
                if stage in ('05.1b','05.2','05.3a'):
                    marker=bundle['visual_evidence'] if bundle else json.loads((directory/'visual-source.json').read_text(encoding='utf-8'))
                    assert marker['result_sha256']==digest(directory/'result.json'),directory
                if head:
                    previous=head[rig]['cases'][name]
                    pose=previous['entry'];parameters=previous['parameters']
                else:
                    parameters,pose=(arms if stage=='05.2' else hands if stage=='05.3a' else body)[name]
                neutral=pose in ('neutral','free-space')
                entry_file=ROOT/'tests/fixtures/movement_fragments/v1'/('entry-neutral.json' if neutral else 'entry-bent-turned.json')
                if stage in ('05.2','05.3a'):
                    from avatar_app.movement_library import contracts as c
                    instance=c.loads(c.MovementInstance,(directory/'instance.json').read_text(encoding='utf-8'))
                    parameters={p.name:p.value for p in instance.parameters}
                    if pose in ('overhead','shoulders-bent','cross-body-clearance'):
                        entry_file=ROOT/'tests/fixtures/shoulders_arms/v1'/('entry-'+pose+'.json')
                    if stage=='05.3a':
                        entry_file=(ROOT/'tests/fixtures/shoulders_arms/v1/entry-shoulders-bent.json' if pose=='bent-turned' else
                                    ROOT/'tests/fixtures/elbows_wrists_hands/v1'/('entry-'+pose+'.json') if pose not in ('neutral','overhead') else entry_file)
                value={'case_id':name,'entry_fixture':str(entry_file),'captured_entry':str(directory/'entry.json'),
                       'entry_kind':'neutral' if neutral else 'authored_non_neutral','authored_entry':pose,
                       'movement_parameters':parameters,'parameter_label':'default parameters' if 'default' in name or name=='look-left' else 'case parameters',
                       'initial_frame':result['samples'][0]['frame'],'frame_end':result['samples'][-1]['frame'],
                       'scene':str(scene),'views':views,'frames_per_view':result['frames'],'scene_sha256':digest(scene)}
                if bundle:
                    value.update({'asset':str(asset),'asset_sha256':bundle['asset']['sha256'],
                                  'manifest':str(manifest),'current_frame':bundle['state']['current_frame']})
                migration=directory/'artifact-migration.json'
                if migration.is_file():
                    m=json.loads(migration.read_text(encoding='utf-8'))
                    value['migration']=str(migration)
                    prepared=Path(m['evidence_directory'])/'prepared.json'
                    if prepared.is_file():
                        p=json.loads(prepared.read_text(encoding='utf-8'))
                        value['current_frame']=p['source_signature']['current_frame']
                entries[name]=value
            rigs[rig]={'cases':len(entries),'rendered_frames':sum(v['frames_per_view']*len(v['views']) for v in entries.values()),'entries':entries}
            print(stage,rig,len(entries),'cases audited',flush=True)
        report['stages'][stage]=rigs
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/maintenance/storage-v2/evidence-audit.json')
    parser.add_argument('--stage',action='append',choices=('05.1a','05.1b','05.2','05.3a'),help='Audit selected stages; defaults to the preserved migration stages')
    args=parser.parse_args()
    value=audit(tuple(args.stage) if args.stage else ('05.1a','05.1b'));atomic_json(args.output,value)
    print(json.dumps({stage:{rig:{k:v for k,v in data.items() if k!='entries'} for rig,data in rigs.items()}
                      for stage,rigs in value['stages'].items()},indent=2))
