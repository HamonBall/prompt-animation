"""Bounded two-native-worker numeric trial, retaining full acceptance checks."""
import sys,ctypes,subprocess,time,json
from ctypes import wintypes
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.legs_evidence import OUT,BLENDER,runtime,numeric_valid
from tools.artifact_store import atomic_json,digest,input_identity
from tools.storage_policy import enforce,temporary_bytes,ARTIFACTS
runtime();enforce(OUT,growth=12*1024**2,temporary=128*1024**2)


class Memory(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in (
        'PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
        'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]


record={'workers':{},'max_observed_combined_resident_bytes':0,'max_observed_temporary_bytes':0,
    'fresh_process_per_case':True,'threads_per_worker':2,'equivalent_case_speedup_claimed':False,
    'serial_reference':'demo/hip.lift.default.left/native-process.json','temporary_reservation_bytes':128*1024**2}
workers=[];started=time.perf_counter()
for rig in ('demo','mixamo'):
    name='knee.lift.default.right';out=OUT/rig/name;assert not out.exists();out.mkdir(parents=True)
    log=(out/'execution.log').open('w');source=input_identity(out)['producer_sha256']
    p=subprocess.Popen([str(BLENDER),'--background','--threads','2','--factory-startup','--python-exit-code','1',
        '--python',str(ROOT/'tests/blender_movement_hips_knees.py'),'--','--rig',rig,'--case',name],
        stdout=log,stderr=subprocess.STDOUT,cwd=ROOT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    workers.append((rig,out,p,log,source));record['workers'][rig]={'pid':p.pid,'observed_peak_resident_bytes':0}
while any(p.poll() is None for _,_,p,_,_ in workers):
    combined=0
    for rig,_,p,_,_ in workers:
        memory=Memory();memory.cb=ctypes.sizeof(memory)
        if p.poll() is None and ctypes.windll.psapi.GetProcessMemoryInfo(wintypes.HANDLE(int(p._handle)),ctypes.byref(memory),memory.cb):
            combined+=memory.WorkingSetSize;row=record['workers'][rig];row['observed_peak_resident_bytes']=max(row['observed_peak_resident_bytes'],memory.PeakWorkingSetSize)
    record['max_observed_combined_resident_bytes']=max(record['max_observed_combined_resident_bytes'],combined)
    record['max_observed_temporary_bytes']=max(record['max_observed_temporary_bytes'],temporary_bytes(ARTIFACTS))
    record['elapsed_s']=time.perf_counter()-started;atomic_json(OUT/'numeric-concurrency-trial.json',record);time.sleep(3)
for rig,out,p,log,source in workers:
    log.close();atomic_json(out/'native-process.json',{'exit_code':p.returncode,'log_sha256':digest(out/'execution.log'),
        'runtime_lock_sha256':runtime(),'producer_at_start':source,'elapsed_s':time.perf_counter()-started})
    record['workers'][rig].update(exit_code=p.returncode,numeric_valid=numeric_valid(out))
record['passed']=all(row['exit_code']==0 and row['numeric_valid'] for row in record['workers'].values())
record['elapsed_s']=time.perf_counter()-started;atomic_json(OUT/'numeric-concurrency-trial.json',record);assert record['passed']
print('LEGS_TWO_NATIVE_WORKERS_PASSED',record,flush=True)
