"""Quiet, resumable process supervisor. No model calls and no shell command strings.

Commands: run/start --plan FILE --job DIR; wait --job DIR --seconds 50;
report/cancel --job DIR. Plans contain trusted local commands, not model output.
Resume delegates cache validity to the existing producers/validators every time.
"""
from __future__ import annotations

import argparse
from collections import deque
import gzip
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.artifact_store import atomic_json, digest, process_alive, producer_lease
from tools.storage_policy import ARTIFACTS, confined, enforce

PHASES = ('preflight', 'numeric', 'render', 'verify', 'review', 'storage')
TERMINAL = {'completed', 'needs_review', 'failed', 'cancelled', 'interrupted'}
MAX_LOG = 8 * 1024**2  # Uncompressed output per attempt; still drain excess.
MAX_JOB_LOGS = 32 * 1024**2


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_plan(path):
    path = Path(path).resolve()
    if path.stat().st_size > 1024**2:
        raise ValueError('Plan exceeds 1 MiB')
    plan = read(path)
    if set(plan) != {'schema_version', 'steps'} or plan['schema_version'] != 1:
        raise ValueError('Expected schema_version=1 and steps')
    if not isinstance(plan['steps'], list) or not 1 <= len(plan['steps']) <= 1024:
        raise ValueError('Expected 1..1024 bounded steps')
    seen = set()
    rank = -1
    for step in plan['steps']:
        required = {'id', 'phase', 'argv', 'timeout_s'}
        allowed = required | {'idle_timeout_s', 'progress_paths', 'retry', 'case_id'}
        if not required <= set(step) or set(step) - allowed:
            raise ValueError('Unexpected step fields')
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}', step['id']) or step['id'] in seen:
            raise ValueError('Invalid/duplicate step id')
        seen.add(step['id'])
        current = PHASES.index(step['phase'])
        if current < rank:
            raise ValueError('Phases must be preflight -> numeric -> render -> verify -> review -> storage')
        rank = current
        check_argv(step['argv'])
        for name in ('timeout_s', 'idle_timeout_s'):
            value = step.get(name, 0)
            if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 86400:
                raise ValueError('Invalid timeout')
        if step['timeout_s'] <= 0:
            raise ValueError('Every command needs a hard deadline')
        for progress in step.get('progress_paths', []):
            confined(ROOT / progress)
        retry = step.get('retry')
        if retry:
            if set(retry) != {'exit_codes', 'recovery_argv', 'reason'} or not retry['reason'].strip():
                raise ValueError('Retry needs classified exit codes, recovery command and reason')
            if not retry['exit_codes'] or any(type(v) is not int or v in (0, 75) for v in retry['exit_codes']):
                raise ValueError('Invalid retry exit codes')
            check_argv(retry['recovery_argv'])
    phases = {s['phase'] for s in plan['steps']}
    if not {'preflight', 'numeric', 'verify', 'storage'} <= phases:
        raise ValueError('Preflight, numeric gate, verification and storage steps are mandatory')
    if 'render' in phases and 'review' not in phases:
        raise ValueError('Rendering requires a review/index step')
    return plan


def check_argv(argv):
    if not isinstance(argv, list) or not argv or any(not isinstance(v, str) or '\x00' in v for v in argv):
        raise ValueError('Commands must be argument arrays')
    if Path(argv[0]).name.lower() in {'cmd', 'cmd.exe', 'powershell', 'powershell.exe', 'pwsh', 'pwsh.exe', 'sh', 'bash'}:
        raise ValueError('Use executable argument arrays, not shell wrappers')


class ProcessTree:
    """Contain descendants on Windows; create a process group on POSIX."""
    def __init__(self, process):
        self.process = process
        self.handle = None
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            class Basic(ctypes.Structure):
                _fields_ = [('per_process', ctypes.c_int64), ('per_job', ctypes.c_int64),
                            ('flags', wintypes.DWORD), ('minimum', ctypes.c_size_t),
                            ('maximum', ctypes.c_size_t), ('active', wintypes.DWORD),
                            ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                            ('scheduling', wintypes.DWORD)]
            class Limits(ctypes.Structure):
                _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                            ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                            ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            kernel.CreateJobObjectW.restype = wintypes.HANDLE
            kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.CreateJobObjectW(None, None)
            limits = Limits()
            limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE
            if not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                if handle:
                    kernel.CloseHandle(handle)
                raise OSError('Cannot establish Windows process-tree containment')
            if not kernel.AssignProcessToJobObject(handle, int(process._handle)):
                kernel.CloseHandle(handle)
                if process.poll() is None:
                    raise OSError('Cannot assign native worker to Windows job')
            else:
                self.handle, self.kernel = handle, kernel

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
        elif os.name != 'nt':
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()


def execute(argv, job, label, timeout, idle=0, progress_paths=(), on_start=None):
    """All monitoring here is ordinary Python, never an agent/model loop."""
    log = job / (label + '.log.gz')
    existing_bytes = sum(p.stat().st_size for p in job.glob('*.log.gz') if p != log)
    if existing_bytes + MAX_LOG > MAX_JOB_LOGS:
        raise RuntimeError('Job diagnostic budget reached; inspect retained failure logs')
    tail = deque(maxlen=16)
    state = {'last': time.monotonic(), 'bytes': 0, 'truncated': False, 'payload': None, 'error': None}
    started = time.monotonic()
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    # Suspend on Windows until assigned to a kill-on-close job: no orphan race.
    if os.name == 'nt':
        flags |= 4  # CREATE_SUSPENDED
    process = subprocess.Popen(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, creationflags=flags, start_new_session=os.name != 'nt')
    tree = None
    reason = None
    def drain():
        pending = b''
        try:
            with gzip.open(log, 'wb') as stream:
                while chunk := process.stdout.read1(8192):
                    state['last'] = time.monotonic()
                    remaining = MAX_LOG - state['bytes']
                    stream.write(chunk[:max(0, remaining)])
                    state['bytes'] += len(chunk)
                    state['truncated'] |= len(chunk) > remaining
                    pending += chunk
                    lines = pending.split(b'\n')
                    pending = lines.pop()[-8192:]
                    for line in lines:
                        text = line.decode('utf-8', 'replace')[-2048:]
                        tail.append(text)
                        if line.startswith(b'EVIDENCE_RESULT '):
                            try:
                                state['payload'] = json.loads(line[16:])
                            except ValueError:
                                pass
                if pending:
                    tail.append(pending.decode('utf-8', 'replace')[-2048:])
        except Exception as exc:
            state['error'] = str(exc)
    thread = threading.Thread(target=drain, daemon=True)
    try:
        tree = ProcessTree(process)
        if on_start:
            on_start(process.pid)
        thread.start()
        if os.name == 'nt':
            import ctypes
            resume = ctypes.WinDLL('ntdll').NtResumeProcess
            resume.argtypes = [ctypes.c_void_p]
            resume.restype = ctypes.c_long
            if resume(int(process._handle)) != 0:
                raise OSError('Cannot resume contained worker')
        stamps = {}
        while process.poll() is None:
            now = time.monotonic()
            for path in progress_paths:
                try:
                    stamp = Path(path).stat().st_mtime_ns
                except FileNotFoundError:
                    continue
                if stamps.get(path) != stamp:
                    stamps[path] = stamp
                    state['last'] = now
            if (job / 'cancel.request').exists():
                reason = 'cancelled'
            elif now - started >= timeout:
                reason = 'deadline_exceeded'
            elif idle and now - state['last'] >= idle:
                reason = 'progress_timeout'
            elif state['error']:
                reason = 'log_write_failed'
            if reason:
                break
            try:
                process.wait(timeout=min(0.25, max(0.01, timeout - (now - started))))
            except subprocess.TimeoutExpired:
                pass
    finally:
        if tree:
            tree.close()
        else:
            process.kill()
            process.wait()
        if thread.ident:
            thread.join(timeout=5)
        process.stdout.close()
    if state['error'] and not reason:
        reason = 'log_write_failed'
    return {'exit_code': process.returncode, 'reason': reason, 'elapsed_s': round(time.monotonic() - started, 3),
            'log': str(log), 'output_bytes': state['bytes'], 'log_truncated': state['truncated'],
            'diagnostic': '\n'.join(tail)[-3000:] if reason or process.returncode else '',
            'result': state['payload']}


def job_path(path):
    return confined(Path(path).absolute(), ARTIFACTS / 'maintenance')


def run(plan_path, job):
    plan = load_plan(plan_path)
    job = job_path(job)
    enforce(job, growth=MAX_JOB_LOGS + 1024**2, temporary=0)
    with producer_lease(job):
        previous = read(job / 'report.json') if (job / 'report.json').exists() else {}
        if previous.get('child_pid') and process_alive(previous['child_pid']):
            raise RuntimeError('Prior worker may still be alive; reconcile it before resuming')
        (job / 'cancel.request').unlink(missing_ok=True)
        atomic_json(job / 'plan.json', plan)
        report = {'schema_version': 1, 'status': 'running', 'pid': os.getpid(), 'child_pid': None,
                  'plan_sha256': digest(job / 'plan.json'), 'started': time.time(), 'steps': [],
                  'previous_status': previous.get('status'), 'case_counts': {'completed': 0, 'reused': 0, 'failed': 0},
                  'phase_seconds': {}, 'review_indexes': [], 'model_calls_by_runner': 0,
                  'terminal_reports': 1}
        def save():
            atomic_json(job / 'report.json', report)
        def child(pid):
            report['child_pid'] = pid
            save()
        save()
        try:
            for step in plan['steps']:
                if (job / 'cancel.request').exists():
                    report['status'] = 'cancelled'
                    break
                report['current_step'] = step['id']
                save()
                attempts = []
                for attempt in range(2):
                    record = execute(step['argv'], job, step['id'] + '.' + str(attempt), step['timeout_s'],
                                     step.get('idle_timeout_s', 0), [ROOT / p for p in step.get('progress_paths', [])], child)
                    report['child_pid'] = None
                    attempts.append(record)
                    retry = step.get('retry')
                    if attempt or record['reason'] or not retry or record['exit_code'] not in retry['exit_codes']:
                        break
                    recovery = execute(retry['recovery_argv'], job, step['id'] + '.recovery', step['timeout_s'], on_start=child)
                    report['child_pid'] = None
                    attempts.append({'recovery': True, 'retry_reason': retry['reason'], **recovery})
                    if recovery['exit_code'] or recovery['reason']:
                        record = recovery
                        break
                elapsed = sum(a['elapsed_s'] for a in attempts)
                report['phase_seconds'][step['phase']] = round(report['phase_seconds'].get(step['phase'], 0) + elapsed, 3)
                report['steps'].append({'id': step['id'], 'phase': step['phase'], 'case_id': step.get('case_id'), 'attempts': attempts})
                payload = record.get('result') or {}
                if isinstance(payload, dict):
                    for key in ('review_index',):
                        if payload.get(key):
                            report['review_indexes'].append(payload[key])
                if record['reason'] or record['exit_code']:
                    report['status'] = ('cancelled' if record['reason'] == 'cancelled' else
                                        'needs_review' if record['exit_code'] == 75 and not record['reason'] else 'failed')
                    report['failed_step'] = step['id']
                    report['case_counts']['failed'] += int(bool(step.get('case_id')) and report['status'] == 'failed')
                    break
                if step['phase'] == 'render' and step.get('case_id'):
                    reused = isinstance(payload, dict) and payload.get('reused') is True
                    report['case_counts']['reused' if reused else 'completed'] += 1
                save()
            else:
                report['status'] = 'completed'
        except KeyboardInterrupt:
            report['status'] = 'cancelled'
        except Exception as exc:
            report.update(status='failed', error=str(exc)[:3000])
        finally:
            report['child_pid'] = None
            try:
                report['storage'] = enforce(job)
            except Exception as exc:
                report.update(status='failed', error='Final storage check: ' + str(exc))
            report['elapsed_s'] = round(time.time() - report['started'], 3)
            report['finished'] = time.time()
            report['log_bytes'] = sum(p.stat().st_size for p in job.glob('*.log.gz'))
            save()
        return report


def summary(report, job):
    keys = ('status', 'elapsed_s', 'case_counts', 'phase_seconds', 'failed_step', 'error', 'review_indexes', 'storage', 'model_calls_by_runner')
    value = {key: report[key] for key in keys if key in report}
    value['report'] = str(job / 'report.json')
    counter = job / 'status-requests.json'
    value['cli_status_requests'] = read(counter).get('count', 0) if counter.exists() else 0
    if report.get('status') in ('failed', 'cancelled', 'needs_review') and report.get('steps'):
        value['diagnostic'] = report['steps'][-1]['attempts'][-1]['diagnostic'][-1200:]
    return value


def read_status(job):
    path = job / 'report.json'
    launch = read(job / 'launch.json') if (job / 'launch.json').exists() else {}
    if not path.exists():
        return {'status': 'starting' if launch.get('pid') and process_alive(launch['pid']) else 'interrupted'}
    value = read(path)
    if launch.get('started', 0) > value['started'] and launch.get('pid') != value.get('pid'):
        return {'status': 'starting' if process_alive(launch['pid']) else 'interrupted'}
    if value['status'] == 'running' and not process_alive(value['pid']):
        value['status'] = 'interrupted'
    return value


def start_job(plan, job):
    # Serialize launch requests as well as worker ownership. The launch lock is
    # separate so the new supervisor can acquire its own job lease immediately.
    with producer_lease(job / '.launch'):
        if read_status(job)['status'] in ('running', 'starting'):
            raise RuntimeError('Job is already active')
        launched_at = time.time()
        with (job / 'launcher.log').open('wb') as log:
            process = subprocess.Popen([sys.executable, str(Path(__file__)), 'run', '--plan', str(plan.resolve()), '--job', str(job)],
                                       cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), start_new_session=os.name != 'nt')
        atomic_json(job / 'launch.json', {'pid': process.pid, 'started': launched_at})
        return process


def open_progress_window(jobs_root):
    powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    try:
        subprocess.Popen(
            [str(powershell), '-NoProfile', '-STA', '-File',
             str(ROOT / 'tools/watch_evidence_jobs.ps1'), '-JobsRoot', str(jobs_root)],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except OSError:
        # A desktop viewer is optional and must never interrupt evidence work.
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('run', 'start', 'wait', 'report', 'cancel'))
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=50)
    parser.add_argument('--no-viewer', action='store_true', help='Skip the Windows progress window on start')
    args = parser.parse_args(argv)
    job = job_path(args.job)
    if args.operation in ('run', 'start') and not args.plan:
        parser.error('--plan is required')
    if args.operation == 'run':
        value = run(args.plan, job)
    elif args.operation == 'start':
        load_plan(args.plan)
        if read_status(job)['status'] in ('running', 'starting'):
            raise RuntimeError('Job is already active')
        enforce(job, growth=MAX_JOB_LOGS + 1024**2)
        job.mkdir(parents=True, exist_ok=True)
        process = start_job(args.plan, job)
        if os.name == 'nt' and not args.no_viewer:
            open_progress_window(job.parent)
        print(json.dumps({'status': 'started', 'pid': process.pid, 'report': str(job / 'report.json'),
                          'next_action': 'Keep this managed tool session alive. Use its completion event or hand off the session/report location; do not poll.'}), flush=True)
        # Some hosts kill detached descendants as soon as the launcher exits.
        # This silent guardian keeps the tool session alive without model calls.
        try:
            process.wait()
        except KeyboardInterrupt:
            (job / 'cancel.request').write_text('cancel\n')
            process.wait()
        value = read_status(job)
    else:
        if args.operation == 'cancel':
            job.mkdir(parents=True, exist_ok=True)
            (job / 'cancel.request').write_text('cancel\n')
        if not 0 <= args.seconds <= 60:
            parser.error('--seconds must be 0..60')
        deadline = time.monotonic() + (args.seconds if args.operation == 'wait' else 0)
        while True:
            value = read_status(job)
            if value['status'] in TERMINAL or time.monotonic() >= deadline:
                break
            time.sleep(min(1, max(0, deadline - time.monotonic())))
        # Separate counter avoids racing the supervisor's report writes.
        counter = job / 'status-requests.json'
        if job.exists():
            count = read(counter).get('count', 0) if counter.exists() else 0
            atomic_json(counter, {'count': count + 1})
    print(json.dumps(summary(value, job), separators=(',', ':')))
    return 0 if value['status'] == 'completed' else 75 if value['status'] == 'needs_review' else 1 if value['status'] in ('failed', 'interrupted') else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error': str(error)[:1200]}))
        raise SystemExit(1)
