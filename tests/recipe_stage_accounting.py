"""Compact storage accounting for plain-data Stage 06 checks."""
import json
import os
import sys
from pathlib import Path

from tools.artifact_store import atomic_json
from tools.storage_policy import ARTIFACTS, MiB, enforce, inventory, temporary_bytes

OUT = ARTIFACTS / 'stages/06'


def main():
    mode = sys.argv[1]
    if mode not in ('before', 'after'):
        raise ValueError('Expected before or after')
    budget = enforce(OUT, growth=MiB if mode == 'before' else 8192, temporary=MiB)
    data = inventory()
    data.pop('files')
    data.pop('by_extension')
    data.pop('by_stage')
    job = ARTIFACTS / 'maintenance/jobs/stage-06-regression'
    report_path = job / 'report.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    own_supervisor = [lease for lease in data['leases'] if lease['active']
                      and Path(lease['path']).resolve() == (job / '.artifact-writer.lock').resolve()
                      and lease['pid'] == report.get('pid')
                      and report.get('status') == 'running'
                      and report.get('child_pid') == os.getpid()]
    if any(lease['active'] and lease not in own_supervisor for lease in data['leases']):
        raise RuntimeError('Active artifact writer requires reconciliation')
    data['own_supervisor_leases'] = own_supervisor
    fixture_root = Path(__file__).parent / 'fixtures/recipe_schedules'
    data['recipe_fixture_bytes'] = sum(path.stat().st_size for path in fixture_root.rglob('*') if path.is_file())
    data['temporary_bytes'] = temporary_bytes(ARTIFACTS)
    data['budget'] = budget
    data['temporary_reservation_bytes'] = MiB
    data['measured_temporary_peak'] = None
    atomic_json(OUT / f'accounting-{mode}.json', data)
    print(json.dumps({'mode': mode, 'retained_bytes': data['bytes'],
                      'fixture_bytes': data['recipe_fixture_bytes'],
                      'temporary_bytes': data['temporary_bytes'],
                      'own_supervisor_writers': len(own_supervisor), 'other_active_writers': 0}))


if __name__ == '__main__':
    main()
