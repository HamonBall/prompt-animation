"""Resumable storage-v2 inventory, obsolete-history retirement and bundle migration.

Dry run is the default. One operation journal is reused across retries.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tools.artifact_store import atomic_json,digest,atomic_replace,producer_lease
from tools.storage_policy import ARTIFACTS,MiB,GiB,inventory,confined,active_writer,enforce,temporary_bytes

OUT=ARTIFACTS/'maintenance/storage-v2'
BLENDER=Path('C:/Program Files/Blender Foundation/Blender 5.1/blender.exe')


def append_event(event,out=OUT):
    out.mkdir(parents=True,exist_ok=True)
    with (out/'journal.jsonl').open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(event,sort_keys=True,allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())


def invoke(mode,job,path,report):
    atomic_json(path,job)
    log=path.with_suffix('.log')
    with log.open('w',encoding='utf-8') as stream:
        result=subprocess.run([str(BLENDER),'--background','--factory-startup','--python-exit-code','1',
            '--python',str(ROOT/'tools/storage_v2_worker.py'),'--','--mode',mode,'--job',str(path),'--report',str(report)],stdout=stream,stderr=subprocess.STDOUT)
    if not report.exists():raise RuntimeError('Worker produced no verification: '+str(log))
    data=json.loads(report.read_text(encoding='utf-8'))
    if result.returncode or not data['passed']:raise RuntimeError(data.get('error','Worker failed')+'; '+str(log))
    return data


def case_id(directory):
    import hashlib
    return hashlib.sha256(str(directory.relative_to(ARTIFACTS)).encode()).hexdigest()[:20]


def accepted(directory,source):
    directory=confined(directory);source=confined(source)
    lock=active_writer(directory)
    if lock:raise RuntimeError('Active writer: '+lock)
    result=directory/'result.json'
    profile=directory/'profile.json'
    if not profile.exists():profile=directory.parent/'profile.json'
    if not result.exists() or not profile.exists():raise RuntimeError('Missing accepted numeric evidence/profile')
    data=json.loads(result.read_text(encoding='utf-8'))
    if not data.get('review',{}).get('passed'):raise RuntimeError('Current result is not accepted')
    sha=digest(source);key=case_id(directory);folder=OUT/'cases'/key;folder.mkdir(parents=True,exist_ok=True)
    job={'directory':str(directory),'source':str(source),'source_sha256':sha,
         'trajectory':str(folder/'trajectory.f32.gz'),'accepted':str(folder/'accepted.json')}
    lease=directory/'.artifact-writer.lock'
    if lease.exists():job['lease']=json.loads(lease.read_text(encoding='utf-8'))
    proof=folder/'accepted.json'
    identity={'source':sha,'result':digest(result),'profile':digest(profile),
              'verifier':digest(ROOT/'tools/storage_v2_worker.py')+digest(ROOT/'tools/artifact_bundle.py')+
                         digest(ROOT/'tools/blender_artifact_worker.py')+digest(ROOT/'tools/artifact_store.py')}
    stamp=folder/'identity.json'
    if not (proof.exists() and stamp.exists() and json.loads(stamp.read_text(encoding='utf-8'))==identity
            and Path(job['trajectory']).exists()):
        enforce(directory,temporary=160*MiB,migration=True)
        value=invoke('accepted',job,folder/'job.json',proof)
        if digest(source)!=sha:raise RuntimeError('Canonical changed during playback verification')
        atomic_json(stamp,identity)
        append_event({'operation':'accepted_verified','case':str(directory),'source_sha256':sha,
                      'numeric_error':value['numeric_error'],'frames':value['playback']['frames']})
    return job,folder


def retire_history(directory,*,apply=False):
    directory=confined(directory);canonical=directory/'preview.blend'
    backups=sorted(directory.glob('*.blend1'))
    if not backups:return {'status':'no_backups','bytes':0}
    if not canonical.is_file():return {'status':'retained_backup_only','paths':[str(p) for p in backups]}
    if active_writer(directory):return {'status':'pending_active_writer','bytes':sum(p.stat().st_size for p in backups)}
    migration=directory/'artifact-migration.json'
    manifest=directory/'preview-manifest.json'
    current=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    if current.get('schema_version')==2 and current.get('verification'):
        record={'canonical_sha256':current['original_scene']['sha256'],'retained':[]}
    elif migration.exists():record=json.loads(migration.read_text(encoding='utf-8'))
    else:raise RuntimeError('No canonical migration record')
    if record['canonical_sha256']!=digest(canonical):raise RuntimeError('Changed canonical hash')
    pins=list(directory.glob('failure-pin.json'))
    if pins:return {'status':'retained_pinned_failure','paths':[str(p) for p in backups]}
    candidates=[];reasons={r['path']:r['reason'] for r in record.get('retained',[])}
    for path in backups:
        confined(path);candidates.append({'path':str(path),'bytes':path.stat().st_size,'sha256':digest(path),
                                        'reason':reasons.get(str(path),'Superseded generated backup')})
    if not apply:return {'status':'dry_run_history','files':candidates}
    job,folder=accepted(directory,canonical)
    if digest(canonical)!=record['canonical_sha256']:raise RuntimeError('Canonical changed after verification')
    # Durable enumeration precedes the first deletion. Different actions are
    # obsolete history here, never falsely classified as equivalent duplicates.
    append_event({'operation':'obsolete_history_prepared','case':str(directory),'canonical_sha256':record['canonical_sha256'],'files':candidates})
    recovered=0
    for item in candidates:
        path=confined(item['path'])
        if active_writer(directory) or digest(path)!=item['sha256']:raise RuntimeError('Backup/writer changed before retirement')
        path.unlink();recovered+=item['bytes']
        append_event({'operation':'obsolete_history_retired',**item,'accepted':str(folder/'accepted.json')})
    return {'status':'history_retired','bytes':recovered,'files':len(candidates)}


def migrate_case(directory,*,apply=False):
    from tools.artifact_bundle import validate_manifest,commit_bundle
    directory=confined(directory);manifest=directory/'preview-manifest.json';source=directory/'preview.blend'
    if active_writer(directory):return {'status':'pending_active_writer'}
    if manifest.exists() and json.loads(manifest.read_text(encoding='utf-8')).get('schema_version')==2:
        m,asset,motion=validate_manifest(directory)
        if source.exists():
            identity=m.get('original_scene') or {}
            if digest(source)!=identity.get('sha256'):raise RuntimeError('Pending old scene changed')
            if apply:
                if list(directory.glob('*.blend1')):retire_history(directory,apply=True)
                append_event({'operation':'resumed_scene_retirement','path':str(source),'sha256':identity['sha256'],'bytes':source.stat().st_size})
                source.unlink()
        return {'status':'already_v2','motion_bytes':motion.stat().st_size}
    if not source.exists():return {'status':'no_canonical'}
    if not apply:return {'status':'dry_run_bundle','bytes':source.stat().st_size}
    job,folder=accepted(directory,source)
    # Snapshot all immutable case inputs; numeric results and images are not
    # regenerated or rewritten by migration.
    baseline={p.name:digest(p) for p in directory.glob('*.json') if p.name!='preview-manifest.pending.json'}
    original_bytes=source.stat().st_size
    proof=json.loads(Path(job['accepted']).read_text(encoding='utf-8'))
    extracted=proof if proof.get('prepared_bundle') and (directory/'preview-manifest.pending.json').exists() else invoke('extract',job,folder/'job.json',folder/'extracted.json')
    verified=invoke('verify',job,folder/'job.json',folder/'verified.json')
    if digest(source)!=job['source_sha256'] or active_writer(directory):raise RuntimeError('Case changed during migration')
    for name,sha in baseline.items():
        if digest(directory/name)!=sha:raise RuntimeError('Input changed during migration: '+name)
    append_event({'operation':'bundle_verified','case':str(directory),'original':str(source),
                  'original_sha256':job['source_sha256'],'original_bytes':original_bytes,
                  'asset':extracted['asset'],'motion':extracted['motion'],'verification':verified})
    pending=directory/'preview-manifest.pending.json'
    value=json.loads(pending.read_text(encoding='utf-8'));value['verification']=verified
    views=value.get('views') or {}
    if not views:
        views={view:{} for view in ('front','side') if (directory/view).is_dir()}
        if not views and (directory/'frames').is_dir() and (directory/'contact-sheet.png').exists():
            views={'legacy':{'frames_dir':'frames','sheet':'contact-sheet.png'}}
    value['views']=views
    from tools.artifact_store import files_complete
    value['complete']=bool(views and files_complete(directory,{**value,'motion':{'path':'motion.pending.blend'}}))
    value['visual_evidence']={'representation':'png_sequence' if views else 'none_required',
          'views':views,'frames':value['expected_frames'],'fps':value['fps'],'fps_base':value['fps_base'],
          'complete':value['complete'],'result_sha256':value['inputs'].get('result.json'),'origin':'preserved_accepted_evidence'}
    labels=ARTIFACTS/'maintenance/neutral-artifacts/evidence-audit.json'
    if not value.get('entry') and labels.exists():
        parts=directory.relative_to(ARTIFACTS).parts
        if len(parts)==4 and parts[0]=='stages':
            index=json.loads(labels.read_text(encoding='utf-8'))
            value['entry']=index.get('stages',{}).get(parts[1],{}).get(parts[2],{}).get('entries',{}).get(parts[3],{})
    if value.get('entry'):
        value['entry']={k:v for k,v in value['entry'].items() if k in ('entry_fixture','entry_kind','authored_entry','movement_parameters','parameter_label','initial_frame','current_frame')}
        value['entry']['captured_entry']='entry.json' if (directory/'entry.json').exists() else None
    atomic_json(pending,value)
    m=commit_bundle(directory)
    append_event({'operation':'bundle_committed','case':str(directory),'original':str(source),
                  'original_sha256':job['source_sha256'],'original_bytes':original_bytes,'manifest_sha256':digest(manifest)})
    if list(directory.glob('*.blend1')):retire_history(directory,apply=True)
    if digest(source)!=job['source_sha256']:raise RuntimeError('Old scene changed after manifest commit')
    source.unlink();append_event({'operation':'full_scene_retired','path':str(source),'bytes':original_bytes,'sha256':job['source_sha256']})
    Path(job['trajectory']).unlink(missing_ok=True)
    return {'status':'migrated','original_bytes':original_bytes,'motion_bytes':(directory/'motion.blend').stat().st_size,'verification':verified}


def compact_diagnostics(*,apply=False):
    """Reduce owned v1 dumps in place, preserving compact proof and old links."""
    import hashlib
    baseline=json.loads((OUT/'baseline-files.json').read_text(encoding='utf-8'));items=[]
    def compact(value):
        if isinstance(value,dict):
            return {k:({'sha256':hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest(),
                        'sample_frames':list(v)} if k=='poses' and isinstance(v,dict) else compact(v)) for k,v in value.items()}
        if isinstance(value,list):
            if len(value)>64:return {'sha256':hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest(),'items':len(value)}
            return [compact(v) for v in value]
        return value
    for rel,item in baseline.items():
        if not rel.startswith('maintenance/neutral-artifacts/'):continue
        p=confined(ARTIFACTS/rel)
        if p.name!='prepared.json' or not p.exists():continue
        data=json.loads(p.read_text(encoding='utf-8'))
        if data.get('storage_compaction'):continue
        if active_writer(p.parent):raise RuntimeError('Active diagnostic writer: '+str(p))
        if digest(p)!=item['sha256']:raise RuntimeError('Diagnostic changed since inventory: '+str(p))
        reduced=compact(data)
        reduced['storage_compaction']={'owner':'storage-v2','original_sha256':item['sha256'],
                                       'original_bytes':item['bytes'],'representation':'deduplicated_fingerprints'}
        record={'path':str(p),'bytes':item['bytes'],'sha256':item['sha256']}
        if apply:
            append_event({'operation':'diagnostic_compaction_prepared',**record})
            if digest(p)!=item['sha256']:raise RuntimeError('Diagnostic changed before replacement')
            atomic_json(p,reduced)
            append_event({'operation':'diagnostic_compacted',**record,'retained_bytes':p.stat().st_size,'retained_sha256':digest(p)})
        items.append(record)
    return items


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true');parser.add_argument('--operation',choices=('inventory','retire-history','migrate','check','compact-diagnostics'),default='inventory')
    parser.add_argument('--case');parser.add_argument('--limit',type=int)
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    if args.operation=='compact-diagnostics':
        values=compact_diagnostics(apply=args.apply);print(len(values),'owned diagnostics',sum(v['bytes'] for v in values),'original bytes');return
    if args.operation in ('inventory','check'):
        data=inventory();files=data.pop('files');atomic_json(OUT/'current-inventory.json',data)
        if args.operation=='check':
            from tools.artifact_bundle import validate_manifest
            errors=[]
            if data['bytes']>4*GiB:errors.append('global')
            for stage,v in data['by_stage'].items():
                limit=GiB if stage=='05.1b' else 512*MiB
                if stage not in ('assets','maintenance','exports') and v['bytes']>limit:errors.append('stage/'+stage)
            if data['by_stage'].get('maintenance',{}).get('bytes',0)>256*MiB:errors.append('maintenance')
            for category,limit in (('assets',512*MiB),('exports',256*MiB)):
                if data['by_stage'].get(category,{}).get('bytes',0)>limit:errors.append(category)
            if temporary_bytes(ARTIFACTS)>512*MiB:errors.append('temporary')
            if len(list((ARTIFACTS/'exports').rglob('*.blend')))>2:errors.append('export_count')
            bundles=0
            for rel,item in files.items():
                path=ARTIFACTS/rel
                if '.scratch' in path.parts:continue
                if path.suffix=='.blend1':errors.append('historical_backup/'+rel)
                if path.name=='preview-manifest.json':
                    m=json.loads(path.read_text(encoding='utf-8'))
                    if m.get('schema_version')!=2:continue
                    try:
                        m,asset,motion=validate_manifest(path.parent);bundles+=1
                        if motion.stat().st_size+path.stat().st_size>8*MiB:errors.append('case/'+str(path.parent))
                        from tools.artifact_store import files_complete
                        if m.get('views') and not (m['complete'] and files_complete(path.parent,m)):
                            errors.append('visual_evidence/'+str(path.parent))
                    except Exception as error:errors.append('bundle/'+rel+': '+str(error))
                if path.name in ('preview.blend','visual-preview.blend'):errors.append('remaining_standalone/'+rel)
            data['validated_bundles']=bundles;data['errors']=errors
            atomic_json(OUT/'budget-check.json',data)
            if errors:raise RuntimeError('Over-budget categories: '+','.join(errors))
        print(json.dumps(data,indent=2));return
    if args.operation=='retire-history':
        directories=sorted({p.parent for p in (ARTIFACTS/'stages/05.1b').rglob('*.blend1')})
    else:
        directories=sorted({p.parent for p in ARTIFACTS.rglob('result.json') if '.scratch' not in p.parts and 'storage-v2' not in p.parts})
    results=[]
    for directory in directories:
        if args.case and directory.relative_to(ARTIFACTS).as_posix()!=args.case:continue
        if args.limit is not None and len(results)>=args.limit:break
        try:
            if active_writer(directory):value={'status':'pending_active_writer'}
            elif args.apply:
                with producer_lease(directory):
                    value=retire_history(directory,apply=True) if args.operation=='retire-history' else migrate_case(directory,apply=True)
            else:value=retire_history(directory) if args.operation=='retire-history' else migrate_case(directory)
        except Exception as error:value={'status':'retained_pending','error':str(error),'bytes':sum(p.stat().st_size for p in directory.glob('*.blend*'))}
        value['case']=str(directory);results.append(value)
        atomic_json(OUT/(args.operation+'-status.json'),results)
        print(directory.relative_to(ARTIFACTS),value['status'],value.get('bytes',value.get('motion_bytes',value.get('error',''))),flush=True)


if __name__=='__main__':main()
