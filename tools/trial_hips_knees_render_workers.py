"""Measure a bounded two-rig render trial before opening the review queue."""
import json
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
from tools.artifact_store import atomic_json
from tools.hips_knees_views import render_valid
from tools.legs_evidence import OUT,PYTHON


def main():
    assert json.loads((OUT/'render-batch-preflight.json').read_text())['native_workers']==2
    case='leg.cross.maximum'
    for rig in ('demo','mixamo'):
        assert not (OUT/rig/case/'render-process.json').exists()
    start=time.perf_counter()
    peak=0
    report={'case':case,'workers':{},'threads_per_native_worker':2,'equivalent_case_speedup_claimed':False}
    with ExitStack() as stack:
        jobs={}
        for rig in ('demo','mixamo'):
            log=stack.enter_context((OUT/('render-concurrency-'+rig+'.log')).open('xb'))
            jobs[rig]=stack.enter_context(subprocess.Popen(
                [str(PYTHON),str(ROOT/'tools/run_hips_knees_render.py'),'--rig',rig,'--case',case],
                cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
        while any(process.poll() is None for process in jobs.values()):
            monitor=json.loads((OUT/'temporary-monitor.json').read_text())
            assert monitor['running']
            peak=max(peak,monitor['current_temporary_bytes'])
            time.sleep(3)
        for rig,process in jobs.items():
            directory=OUT/rig/case
            row={'exit_code':process.returncode,'accepted':process.returncode==0 and render_valid(directory)}
            if row['accepted']:
                row['timings']=json.loads((directory/'render-timing.json').read_text())
            report['workers'][rig]=row
    report.update(wall_s=time.perf_counter()-start,observed_peak_temporary_bytes=peak,
                  passed=all(row['accepted'] for row in report['workers'].values()))
    atomic_json(OUT/'render-concurrency-trial.json',report)
    assert report['passed'],report
    print('LEGS_TWO_RENDER_WORKERS_PASSED',report,flush=True)


if __name__=='__main__':main()
