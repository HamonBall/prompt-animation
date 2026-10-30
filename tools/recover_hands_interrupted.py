"""Reconcile stopped media writers and journal only their owned decode scratch."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.artifact_store import atomic_json,digest
from tools.artifact_bundle import recover_bundle
from tools.lossless_evidence import recover_evidence
from tools.storage_policy import inventory,active_writer,confined
from tools.hands_evidence_cases import cases
OUT=ROOT/'artifacts/stages/05.3a';journal={'owner':'stage-05.3a-stopped-media-scratch','files':{},'state':'prepared'}
for rig in ('demo','mixamo'):
    for name,_,_,_ in cases():
        out=OUT/rig/name;assert not active_writer(out)
        recover_bundle(out);recover_evidence(out)
        for folder in (out/'.scratch').glob('ffv1-*'):
            assert folder.resolve().is_relative_to(OUT.resolve())
            for relative,record in inventory(folder)['files'].items():
                path=confined(folder/relative)
                assert path.suffix in ('.png','.json'),('Unrecognized scratch; preserve',path)
                journal['files'][path.relative_to(OUT).as_posix()]={'sha256':digest(path),'bytes':record['bytes']}
atomic_json(OUT/'interrupted-scratch-retirement.json',journal)
for relative,record in journal['files'].items():
    path=confined(OUT/relative);assert digest(path)==record['sha256'];path.unlink()
for rig in ('demo','mixamo'):
    for folder in (OUT/rig).glob('*/.scratch/ffv1-*'):
        for child in sorted(folder.rglob('*'),key=lambda p:len(p.parts),reverse=True):
            if child.is_dir():child.rmdir()
        folder.rmdir()
journal['state']='complete';atomic_json(OUT/'interrupted-scratch-retirement.json',journal)
print('HANDS_INTERRUPTED_SCRATCH_RECONCILED',len(journal['files']),sum(v['bytes'] for v in journal['files'].values()),flush=True)
