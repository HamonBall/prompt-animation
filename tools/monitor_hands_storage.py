"""Bounded stage 05.3a temporary-footprint observations."""
import json,time,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.artifact_store import atomic_json
from tools.storage_policy import ARTIFACTS,temporary_bytes,LIMITS
OUT=ARTIFACTS/'stages/05.3a';target=OUT/'temporary-monitor.json';stop=OUT/'storage-monitor.stop'
record={'owner':'stage-05.3a','peak_temporary_bytes':0,'samples':0}
if target.exists():record=json.loads(target.read_text())
record.setdefault('restarts',[]).append({'previous_sample_utc':record.get('last_sample_utc'),
    'restart_utc':datetime.now(timezone.utc).isoformat()})
stop.unlink(missing_ok=True)
def provisional_size(path):
    try:return path.stat().st_size
    except FileNotFoundError:
        # Verified publication may retire a PNG between enumeration and stat.
        record['concurrent_retirements_observed']=record.get('concurrent_retirements_observed',0)+1
        return 0
try:
    while True:
        try:scratch=temporary_bytes(ARTIFACTS)
        except FileNotFoundError:
            record['concurrent_scratch_retirements']=record.get('concurrent_scratch_retirements',0)+1
            time.sleep(.1);continue
        # Evidence PNGs are retained until verified movie publication. Include
        # their provisional footprint as well as shared-writer scratch/pending.
        provisional=sum(provisional_size(p) for rig in ('demo','mixamo')
            for view in ('front','side','hand-front','hand-side')
            for p in (OUT/rig).glob('*/'+view+'/*.png') if p.stem.isdecimal())
        current=scratch+provisional
        record.update(current_temporary_bytes=current,peak_temporary_bytes=max(current,record['peak_temporary_bytes']),
                      current_scratch_pending_bytes=scratch,current_provisional_evidence_bytes=provisional,
                      last_sample_utc=datetime.now(timezone.utc).isoformat(),
                      measurement_scope='Shared scratch/pending plus stage provisional evidence PNGs; earlier samples measured shared scratch/pending only.',
                      samples=record['samples']+1,limit_bytes=LIMITS['temporary'],running=not stop.exists())
        atomic_json(target,record)
        if current>LIMITS['temporary']:raise RuntimeError('Temporary budget exceeded')
        if stop.exists():break
        time.sleep(5)
finally:
    record['running']=False;atomic_json(target,record)
