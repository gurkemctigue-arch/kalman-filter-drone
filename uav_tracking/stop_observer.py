"""Observational sidecar for a new development root, never a shutdown fix.

The signal/wait actions in StopObserver.stop match the hash-bound original
run_stage1_trial.py stop. Observation failures are recorded, never allowed to
prevent those original cleanup actions. Existing runtime health gates remain
authoritative; EVIDENCE_COMPLETE below is not a successful-process verdict.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid


def utc():
    return datetime.now(timezone.utc).isoformat()


def process_identity(pid):
    path = Path('/proc') / str(pid) / 'stat'
    with path.open('rb') as stream:
        raw = stream.read(8193)
    if len(raw) > 8192:
        raise ValueError('Owned process stat exceeds bound')
    text = raw.decode(errors='replace')
    values = text[text.rfind(')')+2:].split()
    if len(values) < 20:
        raise ValueError('Incomplete owned process stat')
    with Path('/proc/sys/kernel/random/boot_id').open('r') as stream:
        boot_id = stream.read(129).strip()
    if len(boot_id) > 128:
        raise ValueError('Boot identity exceeds bound')
    return dict(pid=pid, ppid=int(values[1]), pgid=int(values[2]), session=int(values[3]),
                start_ticks=int(values[19]), boot_id=boot_id,
                clock_ticks_per_s=os.sysconf('SC_CLK_TCK'), observed_utc=utc())


class StopObserver:
    def __init__(self, events_path, summary_path):
        self.events_path, self.summary_path = Path(events_path), Path(summary_path)
        self.errors, self.started_processes, self.stops = [], {}, []
        self.sequence, self.closed = 0, False
        # Refuse reuse before the first owned process has been launched.
        if self.summary_path.exists():
            raise FileExistsError(self.summary_path)
        with self.events_path.open('x', encoding='utf-8'):
            pass
        self._emit('observer_created', scope='OBSERVATION_ONLY_NO_RUNTIME_ACCEPTANCE')

    def _error(self, stage, error):
        self.errors.append(dict(stage=stage, type=type(error).__name__, message=str(error)))

    def _emit(self, event, **values):
        """Return event even if evidence storage fails; never abort cleanup."""
        self.sequence += 1
        result = dict(sequence=self.sequence, event=event, utc=utc(),
                      monotonic_s=time.monotonic(), **values)
        try:
            with self.events_path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(result, allow_nan=False)+'\n')
                stream.flush(); os.fsync(stream.fileno())
        except Exception as error:
            self._error('event_write:'+event, error)
        return result

    def _identity(self, pid, stage):
        try:
            return process_identity(pid)
        except Exception as error:
            self._error(stage, error)
            return dict(pid=pid, status='NOT_OBSERVED', reason=type(error).__name__+':'+str(error))

    def started(self, name, process):
        identity = self._identity(process.pid, 'started_identity:'+name)
        if name in self.started_processes:
            self._error('duplicate_started:'+name, ValueError('Duplicate owned component'))
        self.started_processes[name] = identity
        self._emit('owned_started', component=name, creation_identity=identity)

    def _signal(self, name, process, signum, *, leader_only):
        current = self._identity(process.pid, 'signal_identity:'+name)
        creation = self.started_processes.get(name)
        if (creation is not None and 'start_ticks' in creation and 'start_ticks' in current
                and (creation['start_ticks'],creation['boot_id']) != (current['start_ticks'],current['boot_id'])):
            self._error('signal_identity:'+name, ValueError('Owned PID creation identity changed'))
        # This is observation, not permission to signal an unrelated process.
        # The original Popen lifecycle and actions are retained unchanged.
        self._emit('signal_requested', component=name, signal=signum.name,
            signal_number=int(signum), scope='leader_only' if leader_only else 'process_group',
            recipient_pid=process.pid if leader_only else None,
            recipient_pgid=None if leader_only else process.pid,
            creation_identity=creation, current_identity=current)
        action_utc, action_monotonic_s = utc(), time.monotonic()
        try:
            if leader_only:
                process.send_signal(signum)
            else:
                os.killpg(process.pid, signum)
        except BaseException as error:
            self._emit('signal_raised', component=name, signal=signum.name,
                action_utc=action_utc, action_monotonic_s=action_monotonic_s,
                error=type(error).__name__+':'+str(error))
            raise
        self._emit('signal_returned', component=name, signal=signum.name,
                   action_utc=action_utc, action_monotonic_s=action_monotonic_s)

    def _wait(self, name, process, timeout):
        self._emit('wait_planned', component=name, timeout_s=timeout)
        # No observation I/O between this timestamp and the original wait.
        invocation_utc, invocation_monotonic_s = utc(), time.monotonic()
        try:
            result = process.wait(timeout=timeout)
        except BaseException as error:
            self._emit('wait_raised', component=name, timeout_s=timeout,
                invocation_utc=invocation_utc, invocation_monotonic_s=invocation_monotonic_s,
                deadline_monotonic_s=invocation_monotonic_s+timeout,
                error_type=type(error).__name__, error=str(error))
            raise
        self._emit('wait_returned', component=name, timeout_s=timeout,
            invocation_utc=invocation_utc, invocation_monotonic_s=invocation_monotonic_s,
            deadline_monotonic_s=invocation_monotonic_s+timeout, native_exit_code=result)
        return result

    def stop(self, name, process, timeout=10):
        record = dict(component=name, requested_timeout_s=timeout,
                      creation_identity=self.started_processes.get(name), signals=[])
        self.stops.append(record)
        self._emit('stop_invoked', **record)
        try:
            if process:
                # Preserve the original one initial Popen.poll() call.
                initial = process.poll()
                record['initial_poll_exit_code'] = initial
                self._emit('initial_poll', component=name, native_exit_code=initial)
            else:
                initial = None
            if process and initial is None:
                record['signals'].append('SIGINT')
                self._signal(name, process, signal.SIGINT, leader_only=name=='ros')
                try:
                    record['native_exit_code'] = self._wait(name, process, timeout)
                except subprocess.TimeoutExpired:
                    record['signals'].append('SIGTERM')
                    self._signal(name, process, signal.SIGTERM, leader_only=False)
                    try:
                        record['native_exit_code'] = self._wait(name, process, 5)
                    except subprocess.TimeoutExpired:
                        record['signals'].append('SIGKILL')
                        self._signal(name, process, signal.SIGKILL, leader_only=False)
                        record['native_exit_code'] = self._wait(name, process, 3)
            elif process:
                record['native_exit_code'] = initial
            else:
                record['missing_process'] = True
        except BaseException as error:
            record['raised'] = dict(type=type(error).__name__,message=str(error))
            raise
        finally:
            record['invocation_closed'] = True
            self._emit('stop_invocation_closed', **record)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._emit('observer_closed')
        report = dict(schema_version=1, scope='STOP_OBSERVATION_ONLY',
            status='EVIDENCE_COMPLETE' if not self.errors else 'EVIDENCE_INCOMPLETE',
            runtime_acceptance='NOT_EVALUATED_EXISTING_PROCESS_AUDIT_REMAINS_REQUIRED',
            errors=self.errors, events=self.sequence, started_processes=self.started_processes,
            stop_invocations=self.stops, finished_utc=utc(),
            limitations=['Observer timestamps surround original calls; instrumentation adds small I/O overhead.',
                         'Signal return is not process exit; only original Popen.wait/poll results are native exit observations.',
                         'No stack capture, cleanup action, retry or acceptance upgrade is added by this sidecar.'])
        temporary = self.summary_path.with_name(self.summary_path.name+'.partial.'+uuid.uuid4().hex)
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                json.dump(report, stream, indent=2, allow_nan=False)
                stream.flush(); os.fsync(stream.fileno())
            # Hard-link publication is exclusive on both Linux and Windows;
            # unlike rename/replace it cannot overwrite an existing final name.
            os.link(temporary, self.summary_path)
        except Exception as error:
            self._error('summary_publish', error)
            report['status'] = 'EVIDENCE_INCOMPLETE'
            report['unpublished_partial'] = str(temporary)
            return report
        try:
            temporary.unlink()
        except OSError:
            # Publication already succeeded with fully fsynced bytes. Retaining
            # a staging hard-link copy does not invalidate or rewrite evidence.
            pass
        return report
