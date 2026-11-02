"""Observed temporary footprint, including provisional full-motion PNGs."""
import sys,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.artifact_store import atomic_json
from tools.storage_policy import ARTIFACTS,temporary_bytes,LIMITS
OUT=ARTIFACTS/'stages/05.3b';stop=OUT/'storage-monitor.stop'
assert not stop.exists(),'Do not silently restart a stopped monitor'
record={'owner':'05.3b','samples':0,'peak_temporary_bytes':0,'started_utc':datetime.now(timezone.utc).isoformat(),
        'measurement_scope':'Global shared scratch/pending plus stage provisional evidence PNGs; sampled observations, not a continuous maximum'}
def size(path):
    try:return path.stat().st_size
    except FileNotFoundError:return 0
try:
    while True:
        try:current=temporary_bytes(ARTIFACTS)
        except FileNotFoundError:continue
        current+=sum(size(path) for path in (OUT/'mixamo').glob('*/*/*.png') if path.stem.isdecimal())
        record.update(current_temporary_bytes=current,peak_temporary_bytes=max(current,record['peak_temporary_bytes']),
            samples=record['samples']+1,last_sample_utc=datetime.now(timezone.utc).isoformat(),running=not stop.exists())
        atomic_json(OUT/'temporary-monitor.json',record)
        assert current<=LIMITS['temporary']
        if stop.exists():break
        time.sleep(5)
finally:
    record['running']=False;atomic_json(OUT/'temporary-monitor.json',record)
