"""Run a supplemental authored case through the same fresh-process harness."""
import runpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests'),str(ROOT)]
import elbows_wrists_hands_cases as fixture
from hands_trace_range_cases import cases as extra
from tools.artifact_store import atomic_json,digest,producer_lease
primary=fixture.cases
def combined(quick=False):
    yield from primary(quick)
    if not quick:yield from extra()
fixture.cases=combined
arguments=sys.argv[sys.argv.index('--')+1:];rig=arguments[arguments.index('--rig')+1];name=arguments[arguments.index('--case')+1]
assert name in {v[0] for v in extra()}
driver=ROOT/'tools/run_hands_numeric_case.py';sys.argv=[str(driver),'--',*arguments]
runpy.run_path(str(driver),run_name='__main__')
out=ROOT/'artifacts/stages/05.3a'/rig/name
with producer_lease(out):
    atomic_json(out/'supplemental-driver.json',{'driver_sha256':digest(Path(__file__)),
        'fixture_sha256':digest(ROOT/'tests/hands_trace_range_cases.py'),'harness':'tests/blender_movement_elbows_wrists_hands.py'})
