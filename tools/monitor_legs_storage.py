"""Sample global temporary bytes during stage 05.4; never claim an exact peak."""
import json,os,sys,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.artifact_store import atomic_json
from tools.storage_policy import ARTIFACTS,temporary_bytes,LIMITS
OUT=ARTIFACTS/'stages/05.4';stop=OUT/'storage-monitor.stop';assert not stop.exists()
target=OUT/'temporary-monitor.json'
record={'owner':'05.4','samples':0,'peak_temporary_bytes':0,'started_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Global scratch/pending plus stage provisional numbered PNGs; sampled, not continuous maximum',
        'earlier_numeric_pilots_unmonitored_reservation_bytes':32*1024**2}
if target.exists():
    previous=json.loads(target.read_text())
    assert previous['owner']=='05.4'
    now=datetime.now(timezone.utc)
    last=datetime.fromisoformat(previous['last_sample_utc'])
    assert not previous['running'] or (now-last).total_seconds()>60,'Previous sampler may still be active'
    record=previous
    record.setdefault('sampling_interruptions',[]).append({'last_sample_utc':last.isoformat(),'resumed_utc':now.isoformat()})
record['pid']=os.getpid()
try:
    while True:
        current=temporary_bytes(ARTIFACTS)
        for path in OUT.glob('*/*/*/*.png'):
            if path.stem.isdecimal():
                try:current+=path.stat().st_size
                except FileNotFoundError:pass
        record.update(current_temporary_bytes=current,peak_temporary_bytes=max(current,record['peak_temporary_bytes']),
            samples=record['samples']+1,last_sample_utc=datetime.now(timezone.utc).isoformat(),running=not stop.exists())
        atomic_json(target,record);assert current<=LIMITS['temporary']
        if stop.exists():break
        time.sleep(5)
finally:
    record['running']=False;atomic_json(target,record)
