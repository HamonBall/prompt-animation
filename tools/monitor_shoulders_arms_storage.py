"""One bounded live scratch accounting record for the current stage run."""
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.artifact_store import atomic_json
from tools.storage_policy import ARTIFACTS,temporary_bytes,LIMITS

OUT=ARTIFACTS/'stages/05.2';target=OUT/'temporary-monitor.json';stop=OUT/'storage-monitor.stop'
owner='stage-05.2-temporary-monitor-v1'
record=json.loads(target.read_text()) if target.exists() else {'owner':owner,'peak_temporary_bytes':0,'samples':0}
assert record['owner']==owner
stop.unlink(missing_ok=True)
try:
    while True:
        current=temporary_bytes(ARTIFACTS)
        record.update({'current_temporary_bytes':current,'peak_temporary_bytes':max(current,record['peak_temporary_bytes']),
                       'samples':record['samples']+1,'limit_bytes':LIMITS['temporary'],'running':not stop.exists()})
        atomic_json(target,record)
        if current>LIMITS['temporary']:raise RuntimeError('Global temporary budget exceeded')
        if stop.exists():break
        time.sleep(5)
finally:
    record['running']=False;atomic_json(target,record)
