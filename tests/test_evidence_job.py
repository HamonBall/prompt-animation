"""Small real-process tests: no Blender, renders or accepted stage writes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
import uuid
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import evidence_job as job
from tools import evidence_pipeline as pipeline


def python(code):
    return [sys.executable, '-c', code]


class JobTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / 'artifacts/maintenance/evidence-runner/.scratch' / ('test-' + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.output = self.root / 'job'
        self.output.mkdir()
        self.plan = self.root / 'plan.json'

    def tearDown(self):
        assert self.root.resolve().is_relative_to((ROOT / 'artifacts/maintenance/evidence-runner/.scratch').resolve())
        shutil.rmtree(self.root)

    def plan_steps(self, code='pass'):
        return [{'id': phase, 'phase': phase, 'argv': python(code), 'timeout_s': 10}
                for phase in ('preflight', 'numeric', 'verify', 'storage')]

    def run_plan(self, steps):
        self.plan.write_text(json.dumps({'schema_version': 1, 'steps': steps}))
        with patch.object(job, 'job_path', lambda p: Path(p)), patch.object(job, 'enforce', return_value={}):
            return job.run(self.plan, self.output)

    def test_quiet_payload_and_large_output(self):
        result = job.execute(python("print('x'*20000);print('EVIDENCE_RESULT {\"reused\":true}')"), self.output, 'noise', 10)
        self.assertEqual(result['exit_code'], 0)
        self.assertTrue(result['result']['reused'])
        self.assertEqual(result['diagnostic'], '')
        self.assertGreater(result['output_bytes'], 20000)

    def test_deadline_and_idle_timeout(self):
        for name, timeout, idle in [('deadline', .3, 0), ('idle', 5, .3)]:
            result = job.execute(python('import time;time.sleep(10)'), self.output, name, timeout, idle)
            self.assertEqual(result['reason'], 'deadline_exceeded' if name == 'deadline' else 'progress_timeout')
            self.assertLess(result['elapsed_s'], 4)

    def test_cancel(self):
        (self.output / 'cancel.request').write_text('cancel')
        result = job.execute(python('import time;time.sleep(10)'), self.output, 'cancel', 20)
        self.assertEqual(result['reason'], 'cancelled')

    def test_child_tree_is_terminated(self):
        pidfile = self.root / 'child.pid'
        code = ('import subprocess,sys,time;from pathlib import Path;'
                'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]);'
                f'Path({str(pidfile)!r}).write_text(str(p.pid));time.sleep(30)')
        result = job.execute(python(code), self.output, 'tree', 1)
        self.assertEqual(result['reason'], 'deadline_exceeded')
        self.assertTrue(pidfile.exists())
        pid = int(pidfile.read_text())
        for _ in range(20):
            if not job.process_alive(pid):
                break
            time.sleep(.05)
        self.assertFalse(job.process_alive(pid))

    def test_numeric_failure_stops_render(self):
        steps = self.plan_steps()
        steps[1]['argv'] = python('raise SystemExit(2)')
        result = self.run_plan(steps)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(len(result['steps']), 2)

    def test_review_gate_returns_instead_of_waiting(self):
        steps = self.plan_steps()
        steps.insert(3, {'id': 'review', 'phase': 'review', 'argv': python('raise SystemExit(75)'), 'timeout_s': 10})
        result = self.run_plan(steps)
        self.assertEqual(result['status'], 'needs_review')
        self.assertNotIn('storage', [s['id'] for s in result['steps']])

    def test_one_classified_retry_with_recovery(self):
        marker = self.root / 'retry'
        steps = self.plan_steps()
        steps[1]['argv'] = python(f'from pathlib import Path;raise SystemExit(0 if Path({str(marker)!r}).exists() else 7)')
        steps[1]['retry'] = {'exit_codes': [7], 'reason': 'Injected transient state',
                             'recovery_argv': python(f'from pathlib import Path;Path({str(marker)!r}).touch()')}
        result = self.run_plan(steps)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(result['steps'][1]['attempts']), 3)

    def test_retry_is_bounded(self):
        steps = self.plan_steps()
        steps[1]['argv'] = python('raise SystemExit(7)')
        steps[1]['retry'] = {'exit_codes': [7], 'reason': 'Injected persistent failure', 'recovery_argv': python('pass')}
        result = self.run_plan(steps)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(len(result['steps'][1]['attempts']), 3)

    def test_resume_does_not_trust_old_success(self):
        steps = self.plan_steps()
        self.assertEqual(self.run_plan(steps)['status'], 'completed')
        steps[1]['argv'] = python('raise SystemExit(3)')
        self.assertEqual(self.run_plan(steps)['status'], 'failed')

    def test_plan_rejects_shell_and_phase_reordering(self):
        for bad in ([{'id': 'bad', 'phase': 'numeric', 'argv': ['cmd.exe', '/c', 'echo hi'], 'timeout_s': 5}],
                    list(reversed(self.plan_steps()))):
            self.plan.write_text(json.dumps({'schema_version': 1, 'steps': bad}))
            with self.assertRaises(ValueError):
                job.load_plan(self.plan)

    def test_output_cap_drains_without_deadlock(self):
        with patch.object(job, 'MAX_LOG', 1024):
            result = job.execute(python("print('x'*100000)"), self.output, 'cap', 10)
        self.assertEqual(result['exit_code'], 0)
        self.assertTrue(result['log_truncated'])
        import gzip
        self.assertEqual(len(gzip.decompress(Path(result['log']).read_bytes())), 1024)

    def test_restarted_job_does_not_report_previous_completion(self):
        job.atomic_json(self.output / 'report.json', {'status': 'completed', 'pid': 1, 'started': 1})
        job.atomic_json(self.output / 'launch.json', {'pid': os.getpid(), 'started': 2})
        self.assertEqual(job.read_status(self.output)['status'], 'starting')

    def test_changed_pipeline_config_rejected(self):
        # A frozen plan must not silently execute edited case command definitions.
        with patch.object(pipeline, 'config', return_value={}), patch.object(pipeline, 'digest', return_value='new'), \
             patch.object(sys, 'argv', ['pipeline', 'case', '--config', str(self.plan), '--config-sha256', 'old', '--case-id', 'a']):
            with self.assertRaisesRegex(ValueError, 'configuration changed'):
                pipeline.main()

    def test_managed_start_waits_and_reports_terminal_state(self):
        self.plan.write_text(json.dumps({'schema_version': 1, 'steps': self.plan_steps()}))
        from contextlib import redirect_stdout
        from io import StringIO
        output = StringIO()
        from unittest.mock import Mock
        worker = Mock(pid=123)
        with patch.object(job, 'job_path', return_value=self.output), \
             patch.object(job, 'enforce', return_value={}), \
             patch.object(job, 'read_status', side_effect=[{'status': 'interrupted'}, {'status': 'completed'}]), \
             patch.object(job, 'start_job', return_value=worker), redirect_stdout(output):
            self.assertEqual(job.main(['start', '--plan', str(self.plan), '--job', str(self.output)]), 0)
        worker.wait.assert_called_once_with()
        messages = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([m['status'] for m in messages], ['started', 'completed'])

    def test_render_adapter_reuses_and_rejects_invalid(self):
        value = {'cases': [{'id': 'a', 'check_argv': ['checker'], 'render_argv': ['renderer']}]}
        with patch.object(pipeline, 'command', return_value=0) as command:
            self.assertEqual(pipeline.run_case(value, 'a'), 0)
            self.assertEqual(command.call_count, 1)
        with patch.object(pipeline, 'command', return_value=2) as command:
            with self.assertRaises(RuntimeError):
                pipeline.run_case(value, 'a')
            self.assertEqual(command.call_count, 1)
        with patch.object(pipeline, 'command', side_effect=[10, 0, 0]) as command:
            self.assertEqual(pipeline.run_case(value, 'a'), 0)
            self.assertEqual(command.call_count, 3)


if __name__ == '__main__':
    unittest.main()
