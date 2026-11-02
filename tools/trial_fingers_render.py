"""Bounded two-worker render trial: same saved-motion/pixel gates, fresh processes."""
import ctypes,subprocess,sys,time,json
from ctypes import wintypes
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.artifact_store import atomic_json,digest,render_complete
from tools.storage_policy import enforce,temporary_bytes,ARTIFACTS
OUT=ROOT/'artifacts/stages/05.3b';BLENDER='C:/Program Files/Blender Foundation/Blender 5.1/blender.exe'
enforce(OUT,growth=32*1024**2,temporary=256*1024**2)


class Memory(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in (
        'PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
        'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]


started=time.perf_counter();workers=[];record={'workers':{},'max_observed_combined_resident_bytes':0,'max_observed_temporary_bytes':0,
    'render_source_sha256':digest(ROOT/'tools/render_fingers.py'),'internal_threads_per_worker':2,'fresh_process_per_case':True,
    'serial_pilot_reference':'mixamo/gesture.fist.neutral/render-timing.json','equivalent_case_speedup_claimed':False}
for case in ('gesture.open.neutral','gesture.open.bent-turned'):
    path=OUT/'mixamo'/case;log=(path/'render.log').open('w',encoding='utf-8')
    process=subprocess.Popen([BLENDER,'--background','--threads','2','--factory-startup','--python-exit-code','1','--python',str(ROOT/'tools/render_fingers.py'),'--','--case',case],
        cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    workers.append((case,process,log));record['workers'][case]={'pid':process.pid,'observed_peak_resident_bytes':0}
while any(process.poll() is None for _,process,_ in workers):
    combined=0
    for case,process,_ in workers:
        memory=Memory();memory.cb=ctypes.sizeof(memory)
        if process.poll() is None and ctypes.windll.psapi.GetProcessMemoryInfo(wintypes.HANDLE(int(process._handle)),ctypes.byref(memory),memory.cb):
            combined+=memory.WorkingSetSize;row=record['workers'][case];row['observed_peak_resident_bytes']=max(row['observed_peak_resident_bytes'],memory.PeakWorkingSetSize)
    record['max_observed_combined_resident_bytes']=max(record['max_observed_combined_resident_bytes'],combined)
    try:record['max_observed_temporary_bytes']=max(record['max_observed_temporary_bytes'],temporary_bytes(ARTIFACTS))
    except FileNotFoundError:pass
    record['elapsed_s']=time.perf_counter()-started;atomic_json(OUT/'render-concurrency-trial.json',record);time.sleep(3)
for case,process,log in workers:
    log.close();row=record['workers'][case];row['exit_code']=process.returncode
    path=OUT/'mixamo'/case;manifest=json.loads((path/'preview-manifest.json').read_text());row['strict_media_complete']=render_complete(path,tuple(manifest['views']))
record['passed']=all(row['exit_code']==0 and row['strict_media_complete'] for row in record['workers'].values())
record['elapsed_s']=time.perf_counter()-started;atomic_json(OUT/'render-concurrency-trial.json',record);assert record['passed']
print('FINGERS_TWO_RENDER_WORKERS_PASSED',record,flush=True)
