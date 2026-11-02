"""Own one original adapter at a time; never select a slot or kill a process tree.

Linux runtime only. Import, describe and fake-backend tests are inert. The direct
child starts a new session; signals target only its verified PID, not its group.
There is deliberately no total/cleanup deadline and no SIGKILL escalation here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

SCOPE = 'FORMAL54_OWNED_SERIAL_SIGNAL_FORWARDING_NOT_GUARD_ADMISSION'
ORIGINAL_SERIAL_SHA256 = '6c8d2cd68b2f5d3a8acfea791ca1c82d49d595d664745073dea851802ac7971a'


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def binding(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


class LinuxBackend:
    def require_runtime(self):
        require(sys.platform.startswith('linux') and Path('/proc/self/stat').is_file(),
                'Owned formal execution requires Linux /proc; describe/tests do not execute')

    def identity(self, pid):
        try:
            text = Path('/proc').joinpath(str(pid), 'stat').read_text(encoding='ascii')
            fields = text[text.rfind(')')+2:].split()
            boot = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='ascii').strip()
            return {'pid': int(pid), 'start_token': 'linux:'+boot+':'+fields[19],
                    'start_ticks': int(fields[19]), 'pgid': int(fields[2]),
                    'session': int(fields[3]), 'state': fields[0]}
        except FileNotFoundError:
            return None

    def spawn(self, command, **kwargs):
        return subprocess.Popen(command, start_new_session=True, **kwargs)

    def send(self, pid, number):
        os.kill(pid, number)


class OwnedGuardRunner:
    """A subprocess.run-compatible callback with an explicitly owned child."""
    def __init__(self, output, *, backend=None, install_signal_handlers=True):
        self.output = Path(output).absolute()
        self.backend = backend or LinuxBackend()
        self.install_signal_handlers = install_signal_handlers
        self.previous_handlers = {}
        self.requests = []
        self.forwarded = []
        self.child = None
        self.child_pid = None
        self.child_identity = None
        self.child_identity_verified = False
        self.child_identity_error = None
        self.child_path = None
        self.child_code = None
        self.state = 'STARTING'
        self.completed_children = 0
        self.owner_identity = None
        self.finalized = False
        self.attached = False
        self.stop_window_closed = False
        self.post_terminal_requests = []
        self.terminal_boundary = None
        self.terminal_stop_requests = None

    def __enter__(self):
        self.backend.require_runtime()
        require(binding(Path(__file__).parent/'formal280_serial_guard01.original.py')['sha256']
                == ORIGINAL_SERIAL_SHA256, 'Archived original serial bytes changed')
        self.owner_identity = self.backend.identity(os.getpid())
        require(self.owner_identity and self.owner_identity.get('start_token'),
                'Cannot bind the native serial owner creation identity')
        try:
            if self.install_signal_handlers:
                for number in (signal.SIGINT, signal.SIGTERM):
                    self.previous_handlers[number] = signal.signal(number, self.request_stop)
        except BaseException:
            self.restore_handlers()
            raise
        return self

    def restore_handlers(self):
        for number, handler in self.previous_handlers.items():
            signal.signal(number, handler)
        self.previous_handlers.clear()

    def __exit__(self, kind, value, traceback):
        try:
            # An owned Popen is never abandoned merely because an outer write failed.
            if self.child is not None and self.child.poll() is None:
                self.request_stop(signal.SIGTERM, source='cleanup_after_error')
                self._wait_owned(write_heartbeat=False)
            if not self.finalized and self.attached:
                self.finish(None, error=None if value is None else type(value).__name__+': '+str(value))
        finally:
            self.restore_handlers()
        return False

    def request_stop(self, number, frame=None, *, source='external_signal'):
        # No filesystem operations, exceptions or process signaling in a handler.
        request = {'signal': int(number), 'observed_utc': utc(), 'source': source}
        if self.stop_window_closed:
            # No owned child remains at this explicit terminal decision boundary.
            # Later signals cannot mutate the committed task or its exit code.
            self.post_terminal_requests.append(request)
        else:
            self.requests.append(request)

    def check_start_allowed(self):
        require(not self.requests and not self.stop_window_closed,
                'Stop requested or terminal committed; no further original guard invocation is allowed')

    def attach_batch(self):
        """Called only after the original serial creates its fresh batch output."""
        require(not self.attached and self.output.is_dir() and not self.output.is_symlink(),
                'Lifecycle must attach once to the freshly created serial directory')
        require(not any((self.output/name).exists() for name in
                ('lifecycle_events.jsonl', 'lifecycle_heartbeat.json', 'lifecycle_terminal.json')),
                'Never resume or overwrite lifecycle evidence')
        self.attached = True
        self.state = 'CHECKING_ORIGINAL_RECEIPTS'
        self.heartbeat()

    def _event(self, event, **values):
        with (self.output/'lifecycle_events.jsonl').open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps({'utc': utc(), 'scope': SCOPE, 'event': event, **values}, allow_nan=False)+'\n')

    def heartbeat(self):
        require(self.attached and self.output.is_dir(), 'Original serial must create its fresh output first')
        owner = self.backend.identity(os.getpid())
        require(owner and owner.get('start_token') == self.owner_identity['start_token'],
                'Serial owner PID creation identity changed')
        value = {'schema_version': 1, 'scope': SCOPE, 'heartbeat_utc': utc(),
                 'state': self.state, 'owner_process': self.owner_identity,
                 'owner_verified_at_heartbeat': True, 'child_process': self.child_identity,
                 'owned_popen_pid': self.child_pid, 'identity_unverified': not self.child_identity_verified,
                 'child_returncode': self.child_code, 'stop_requests': list(self.requests),
                 'forwarded_signals': list(self.forwarded), 'completed_owned_children': self.completed_children,
                 'scheduled_slots': 280, 'engineering_verdict_computed': False,
                 'batch_timeout_s': None, 'cleanup_timeout_s': None,
                 'terminal_boundary': self.terminal_boundary}
        temporary = self.output/'lifecycle_heartbeat.json.new'
        # This directory is newly owned by the original serial; never resume it.
        with temporary.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write('\n')
        temporary.replace(self.output/'lifecycle_heartbeat.json')

    def _verified_live_child(self):
        observed = self.backend.identity(self.child.pid)
        if observed is None or observed.get('state') in {'Z', 'X'}:
            return None
        for key in ('pid', 'start_token', 'start_ticks', 'pgid', 'session'):
            require(observed.get(key) == self.child_identity.get(key),
                    'Owned child identity/PGID changed; refusing to signal another process')
        require(observed['pgid'] == self.child.pid and observed['session'] == self.child.pid,
                'Owned adapter is no longer its isolated session/group leader')
        return observed

    def _forward_requested(self):
        if not self.requests or self.forwarded:
            return
        observed = self._verified_live_child()
        if observed is None:
            return  # A zombie is reaped via the real Popen handle, never signaled.
        number = self.requests[0]['signal']
        try:
            self.backend.send(self.child.pid, number)
        except ProcessLookupError:
            return
        record = {'signal': number, 'utc': utc(), 'verified_process': observed,
                  'target': 'owned_adapter_pid_only', 'group_signaled': False,
                  'request_source': self.requests[0]['source']}
        self.forwarded.append(record)
        self.state = 'STOPPING_WAITING_ORIGINAL_ADAPTER_CLEANUP'
        self._event('STOP_SIGNAL_FORWARDED', **record)

    def _wait_owned(self, *, write_heartbeat=True):
        heartbeat_error = None
        identity_error = None
        while True:
            if identity_error is None:
                try:
                    self._forward_requested()
                except (OSError, ValueError) as error:
                    # Never signal an unverified identity, and never abandon our
                    # actual Popen handle merely because verification failed.
                    identity_error = error
                    self.state = 'IDENTITY_ERROR_WAITING_OWNED_PROCESS'
            if write_heartbeat:
                try:
                    self.heartbeat()
                except (OSError, ValueError) as error:
                    heartbeat_error = error
                    self.request_stop(signal.SIGTERM, source='cleanup_after_error')
                    write_heartbeat = False
            try:
                code = self.child.wait(timeout=1.0)
                break
            except subprocess.TimeoutExpired:
                continue
        self.child_code = code
        if identity_error is not None:
            raise identity_error
        if heartbeat_error is not None:
            raise heartbeat_error
        return code

    def __call__(self, command, *, stdin, stdout, stderr, check):
        self.check_start_allowed()
        require(self.attached, 'Original serial batch lifecycle was not attached')
        require(check is False and stdin is subprocess.DEVNULL, 'Original subprocess callback semantics changed')
        require(self.child is None, 'A previous owned adapter has not been closed')
        invocation = Path(stdout.name).resolve(strict=True).parent
        require(invocation.parent == self.output.resolve() and Path(stderr.name).parent.resolve() == invocation,
                'Only original serial invocation log paths may own the adapter')
        self.child_path = invocation
        self.child_code = None
        self.child_pid = None
        self.child_identity = None
        self.child_identity_verified = False
        self.child_identity_error = None
        self.forwarded = []
        self.check_start_allowed()
        self.child = self.backend.spawn(command, stdin=stdin, stdout=stdout, stderr=stderr)
        self.child_pid = self.child.pid
        try:
            self.child_identity = self.backend.identity(self.child.pid)
            require(self.child_identity and self.child_identity.get('start_token')
                    and self.child_identity.get('pgid') == self.child.pid
                    and self.child_identity.get('session') == self.child.pid,
                    'Cannot bind isolated owned adapter PID/start_ticks/PGID')
            self.child_identity_verified = True
            self.state = 'RUNNING_ORIGINAL_ADAPTER'
            write_new(invocation/'owned_process_started.json', {'schema_version': 1, 'scope': SCOPE,
                'started_utc': utc(), 'command': list(command), 'owner_process': self.owner_identity,
                'child_process': self.child_identity, 'batch_timeout_s': None})
            self._event('OWNED_ADAPTER_STARTED', child_process=self.child_identity, invocation=str(invocation))
            code = self._wait_owned()
        except BaseException as error:
            self.request_stop(signal.SIGTERM, source='cleanup_after_error')
            # If identity capture failed, do not guess ownership from a PID alone.
            if not self.child_identity_verified:
                self.child_identity_error = type(error).__name__+': '+str(error)
                self.child_identity = None
                self.state = 'IDENTITY_UNVERIFIED_WAITING_OWNED_PROCESS'
                while self.child.poll() is None:
                    try:
                        self.child.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        pass
            else:
                self._wait_owned(write_heartbeat=False)
            raise
        finally:
            code = self.child.poll()
            # Popen returncode comes from wait/poll, never from PID disappearance.
            require(code is not None, 'Owned adapter still running; refusing a fabricated terminal')
            self.child_code = code
            write_new(invocation/'owned_process_terminal.json', {'schema_version': 1, 'scope': SCOPE,
                'finished_utc': utc(), 'child_process': self.child_identity, 'returncode': code,
                'owned_popen_pid': self.child.pid, 'identity_unverified': not self.child_identity_verified,
                'identity_capture_error': self.child_identity_error,
                'wait_completed': True, 'stop_requests': list(self.requests), 'forwarded_signals': list(self.forwarded),
                'descendant_cleanup_claimed': False, 'original_adapter_receipts_remain_authoritative': True})
            self.completed_children += 1
            self.child = None
            self.state = 'STOPPED_AFTER_ORIGINAL_ADAPTER_WAIT' if self.requests else 'CHECKING_ORIGINAL_RECEIPTS'
            self.heartbeat()
        return subprocess.CompletedProcess(command, code)

    def annotate(self, result):
        requests = self.requests if self.terminal_stop_requests is None else self.terminal_stop_requests
        external_stop = any(request['source'] == 'external_signal' for request in requests)
        result['orchestration_state'] = ('STOPPED_BY_SIGNAL' if external_stop else
            'COMPLETED' if result['status'] == 'GUARD_PENDING_EXHAUSTED' and not requests else 'FAILED_OR_REFUSED')
        result['stop_requests'] = list(requests)
        result['owned_process_waits_completed'] = self.completed_children
        result['engineering_acceptance_claimed'] = False
        result['serial_exit_code'] = 0 if result['orchestration_state'] == 'COMPLETED' else 2
        result['terminal_boundary'] = self.terminal_boundary

    def finish(self, result, *, error=None):
        if self.finalized:
            return
        require(self.child is None, 'Cannot commit a batch terminal while an owned adapter remains')
        # This single flag assignment is the stop-handler decision boundary.
        # Before it, requests are accepted and are included by the snapshot below.
        # After it, handler calls are explicitly post-terminal and cannot change
        # any terminal file or the return value. There is no running child here.
        self.stop_window_closed = True
        self.terminal_stop_requests = list(self.requests)
        self.terminal_boundary = {'closed_utc': utc(),
            'policy': 'STOP_HANDLER_WINDOW_CLOSED_WITH_NO_OWNED_CHILD_BEFORE_FINAL_FILES',
            'accepted_stop_requests': len(self.terminal_stop_requests)}
        if result is not None:
            self.annotate(result)
            write_new(self.output/'summary.json', result)
        self.state = (result['orchestration_state'] if result is not None else
                      'STOPPED_BY_SIGNAL' if any(request['source'] == 'external_signal' for request in self.terminal_stop_requests)
                      else 'FAILED_OR_REFUSED')
        self.heartbeat()
        write_new(self.output/'lifecycle_terminal.json', {'schema_version': 1, 'scope': SCOPE,
            'finished_utc': utc(), 'state': self.state, 'owner_process': self.owner_identity,
            'last_owned_process': self.child_identity, 'last_owned_returncode': self.child_code,
            'last_owned_popen_pid': self.child_pid, 'identity_unverified': not self.child_identity_verified,
            'completed_owned_children': self.completed_children, 'stop_requests': list(self.terminal_stop_requests),
            'terminal_boundary': self.terminal_boundary,
            'serial_exit_code': result['serial_exit_code'] if result is not None else 2,
            'original_serial_summary': binding(self.output/'summary.json') if (self.output/'summary.json').is_file() else None,
            'error': error, 'scheduled_slots': 280, 'automatic_retry': False,
            'batch_timeout_s': None, 'cleanup_timeout_s': None, 'engineering_acceptance_claimed': False})
        self.finalized = True


def describe():
    directory = Path(__file__).resolve().parent
    files = ('formal280_serial_guard54.py', 'owned_guard_process54.py',
             'formal280_serial_guard01.original.py', 'test_formal280_serial_guard01.original.py',
             'test_formal280_serial_guard54.py', 'test_native_owned_signal54.py')
    return {'schema_version': 1, 'scope': SCOPE, 'files': {name: binding(directory/name)['sha256'] for name in files},
            'original_serial_sha256': ORIGINAL_SERIAL_SHA256, 'runtime_platform': 'Linux /proc',
            'batch_timeout_s': None, 'cleanup_timeout_s': None, 'signal_target': 'verified owned adapter PID only',
            'original_guard_gate_changed': False, 'slot_selection_changed': False,
            'native_signal_validation_claimed': False, 'actual_formal_execution_started': False}
