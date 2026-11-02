"""Pure metadata/fake-process tests. Never spawn WSL, a child or a real guard."""
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import formal54_durable_owner as owner


SERIAL_NAMES = ('formal280_serial_guard54.py', 'owned_guard_process54.py', 'formal280_serial_guard01.original.py',
    'test_formal280_serial_guard01.original.py', 'test_formal280_serial_guard54.py', 'test_native_owned_signal54.py')


class FakeProcess:
    def __init__(self, pid, *, code=0, timeouts=0, on_wait=None):
        self.pid, self.code, self.timeouts, self.on_wait = pid, code, timeouts, on_wait
        self.returncode, self.wait_calls = None, 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.on_wait:
            self.on_wait(self)
        if self.timeouts:
            self.timeouts -= 1
            raise subprocess.TimeoutExpired('synthetic-owned-command', timeout)
        self.returncode = self.code
        return self.code


class FakeBackend:
    def __init__(self):
        self.identities, self.spawned, self.sent, self.handles = {}, [], [], []
        self.clock = 0.
        self.next_handle = None
        self.on_sleep = None

    def require_runtime(self):
        pass

    def monotonic(self):
        return self.clock

    def sleep(self, seconds):
        self.clock += seconds
        if self.on_sleep:
            self.on_sleep(seconds)

    def identity(self, pid):
        return deepcopy(self.identities.get(pid))

    def spawn(self, command, **kwargs):
        handle = self.next_handle or FakeProcess(500+len(self.spawned))
        self.next_handle = None
        self.spawned.append((list(command), kwargs))
        self.handles.append(handle)
        self.identities[handle.pid] = {'pid': handle.pid, 'start_ticks': handle.pid*10,
            'start_token': 'linux:synthetic-boot:'+str(handle.pid*10), 'pgid': handle.pid, 'session': handle.pid,
            'argv': list(command), 'exe': str(Path(command[0]).resolve()), 'state': 'S'}
        return handle

    def send(self, pid, number):
        self.sent.append((pid, int(number)))


class Fixture:
    def __init__(self, base):
        self.base = Path(base).resolve()
        self.root = self.base/'synthetic_frozen'
        self.root.mkdir()
        self.serial = self.base/'synthetic_reviewed_serial'
        self.serial.mkdir()
        for name in SERIAL_NAMES:
            (self.serial/name).write_text('# synthetic source, never imported/executed\n', encoding='utf-8')
        self.description = {'schema_version': 1, 'scope': owner.SERIAL_SCOPE,
            'files': {name: owner.pin(self.serial/name)['sha256'] for name in SERIAL_NAMES}}
        self.serial_sha = owner.canonical(self.description)
        self.description_path = self.base/'serial_describe.json'
        self.save(self.description_path, self.description)
        self.manifest = self.base/'synthetic_admission.json'
        self.save(self.manifest, {'kind': 'RELIABILITY_V4_FORMAL_ADMISSION', 'synthetic_fixture_only': True,
            'final_root': str(self.root), 'state_directory': str(self.root/'results'/'state')})
        self.prefix = self.base/'synthetic_supplementary.sh'
        self.prefix.write_text('# synthetic prefix, never executed\n', encoding='utf-8')
        self.request_path = self.base/'request.json'
        self.owner = self.base/'durable'
        self.output = self.base/'batch'
        self.request = {'schema_version': 1, 'kind': owner.REQUEST_KIND, 'created_utc': '2020-01-01T00:00:00+00:00',
            'python_executable': str(Path(sys.executable).resolve()), 'serial_entry': owner.pin(self.serial/SERIAL_NAMES[0]),
            'serial_description': owner.pin(self.description_path), 'reviewed_serial_tools_sha256': self.serial_sha,
            'manifest': owner.pin(self.manifest), 'serial_output': str(self.output), 'working_directory': str(self.base),
            'guard_command': ['bash', str(self.prefix)], 'input_files': [owner.pin(self.prefix)]}
        self.save(self.request_path, self.request)
        self.backend = FakeBackend()

    @staticmethod
    def save(path, value):
        owner.write_new(path, value)

    def context(self):
        return owner.request_context(owner.pin(self.request_path), self.owner, owner.canonical(owner.description()), self.serial_sha)

    def launch(self):
        self.result = owner.launch(owner.pin(self.request_path), self.owner, owner.canonical(owner.description()),
                                  self.serial_sha, backend=self.backend)
        self.registry_pin, self.registry = owner.read_registry(self.owner, self.result['registry']['sha256'])
        owner.write_new(self.owner/'worker_control_ready.json', {'registry': self.registry_pin,
            'worker_process': self.result['worker_process'], 'command': self.backend.spawned[0][0],
            'stop_handlers_installed': True, 'synthetic_fixture_only': True})
        return self.result

    def run_worker(self, *, handle=None, handlers=False):
        self.backend.next_handle = handle
        (self.owner/'worker_control_ready.json').unlink()
        with patch.object(owner.os, 'getpid', return_value=self.result['worker_process']['pid']):
            return owner.supervise(self.registry_pin, self.registry, backend=self.backend, install_handlers=handlers)

    def original_terminal(self, process, **updates):
        self.output.mkdir(exist_ok=True)
        value = {'schema_version': 1, 'scope': owner.SERIAL_SCOPE,
            'owner_process': self.backend.identity(process.pid), 'serial_exit_code': process.code,
            'state': 'COMPLETED', 'dummy_fixture_only': True}
        value.update(updates)
        if not (self.output/'lifecycle_terminal.json').exists():
            owner.write_new(self.output/'lifecycle_terminal.json', value)


class DurableOwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='formal54_durable_pure_')
        self.addCleanup(self.temp.cleanup)
        self.case = Fixture(self.temp.name)

    def test_launch_binds_exact_original_serial_argv_and_verified_ack_without_waiting(self):
        result = self.case.launch()
        self.assertEqual(len(self.case.backend.spawned), 1)
        command, options = self.case.backend.spawned[0]
        self.assertIn('worker', command)
        self.assertIs(options['stdin'], subprocess.DEVNULL)
        self.assertEqual(self.case.backend.handles[0].wait_calls, 0)
        self.assertEqual(owner.load(self.case.owner/'launch_ack.json')['worker_process'], result['worker_process'])
        self.assertEqual(self.case.registry['serial_command'][-3:], ['--guard-command', 'bash', str(self.case.prefix)])
        self.assertFalse(self.case.output.exists())

    def test_separate_serial_reviewed_canonical_cannot_be_self_certified(self):
        with self.assertRaises(ValueError):
            owner.request_context(owner.pin(self.case.request_path), self.case.owner,
                                  owner.canonical(owner.description()), 'a'*64)
        self.assertEqual(self.case.backend.spawned, [])
        self.assertFalse(self.case.owner.exists())

    def test_fresh_owner_and_serial_outputs_refuse_resume(self):
        self.case.output.mkdir()
        with self.assertRaises(ValueError):
            self.case.launch()
        self.assertFalse(self.case.owner.exists())
        self.assertEqual(self.case.backend.spawned, [])

    def test_frozen_root_output_is_rejected_before_spawn(self):
        self.case.owner = self.case.root/'bad_owner'
        with self.assertRaises(ValueError):
            self.case.launch()
        self.assertEqual(self.case.backend.spawned, [])

    def test_spawn_failure_is_retained_with_no_fabricated_serial_wait(self):
        with patch.object(self.case.backend, 'spawn', side_effect=OSError('synthetic Popen failure')):
            with self.assertRaises(OSError):
                self.case.launch()
        terminal = owner.load(self.case.owner/'terminal.json')
        self.assertEqual(terminal['state'], 'LAUNCH_FAILED_BEFORE_ACK')
        self.assertFalse(terminal['serial_wait_completed'])
        self.assertFalse((self.case.owner/'launch_ack.json').exists())

    def test_unverified_launcher_child_is_never_signaled_or_acknowledged(self):
        original = self.case.backend.spawn
        def mismatch(*args, **kwargs):
            process = original(*args, **kwargs)
            self.case.backend.identities[process.pid]['argv'] = ['different-command']
            return process
        with patch.object(self.case.backend, 'spawn', mismatch), self.assertRaises(ValueError):
            self.case.launch()
        self.assertEqual(self.case.backend.sent, [])
        self.assertFalse((self.case.owner/'launch_ack.json').exists())
        self.assertTrue(owner.load(self.case.owner/'launch_failure.json')['worker_may_still_be_alive'])
        self.assertFalse((self.case.owner/'terminal.json').exists())

    def test_worker_real_handle_wait_and_original_terminal_are_both_required(self):
        self.case.launch()
        handle = FakeProcess(700, code=0, timeouts=3, on_wait=self.case.original_terminal)
        terminal = self.case.run_worker(handle=handle)
        self.assertEqual(handle.wait_calls, 4)
        self.assertTrue(terminal['serial_wait_completed'])
        self.assertTrue(terminal['serial_exit_evidence_complete'])
        self.assertFalse(terminal['descendant_cleanup_claimed'])
        self.assertEqual(self.case.backend.sent, [])

    def test_nonzero_serial_exit_is_retained_without_retry(self):
        self.case.launch()
        terminal = self.case.run_worker(handle=FakeProcess(700, code=2, on_wait=self.case.original_terminal))
        self.assertEqual(terminal['serial_returncode'], 2)
        self.assertTrue(terminal['serial_exit_evidence_complete'])
        self.assertEqual(len(self.case.backend.spawned), 2)
        self.assertFalse(terminal['automatic_retry'])

    def test_missing_original_serial_terminal_remains_incomplete(self):
        self.case.launch()
        terminal = self.case.run_worker(handle=FakeProcess(700))
        self.assertTrue(terminal['serial_wait_completed'])
        self.assertFalse(terminal['serial_exit_evidence_complete'])

    def test_malformed_original_terminal_does_not_erase_actual_exit_receipt(self):
        self.case.launch()
        self.case.output.mkdir()
        (self.case.output/'lifecycle_terminal.json').write_text('{broken', encoding='utf-8')
        terminal = self.case.run_worker(handle=FakeProcess(700))
        self.assertTrue(terminal['serial_wait_completed'])
        self.assertIn('original_terminal:', terminal['error'])
        self.assertFalse(terminal['serial_exit_evidence_complete'])

    def test_missing_ack_aborts_before_any_serial_spawn(self):
        self.case.launch()
        (self.case.owner/'launch_ack.json').unlink()
        terminal = self.case.run_worker()
        self.assertFalse(terminal['serial_started'])
        self.assertEqual(len(self.case.backend.spawned), 1)
        self.assertIn('No verified launcher ACK', terminal['error'])

    def test_ack_from_different_creation_cannot_start_serial(self):
        self.case.launch()
        path = self.case.owner/'launch_ack.json'
        value = owner.load(path)
        value['worker_process']['start_ticks'] += 1
        path.unlink()
        owner.write_new(path, value)
        terminal = self.case.run_worker()
        self.assertFalse(terminal['serial_started'])
        self.assertEqual(len(self.case.backend.spawned), 1)

    def test_worker_stop_is_forwarded_once_then_waits_past_five_seconds(self):
        self.case.launch()
        handlers = {}
        def register(number, handler):
            previous = handlers.get(number)
            handlers[number] = handler
            return previous
        def waited(process):
            if process.wait_calls <= 3:
                handlers[signal.SIGTERM](signal.SIGTERM)
            self.case.original_terminal(process)
        handle = FakeProcess(700, code=2, timeouts=8, on_wait=waited)
        with patch.object(owner.signal, 'signal', register):
            terminal = self.case.run_worker(handle=handle, handlers=True)
        self.assertEqual(handle.wait_calls, 9)
        self.assertEqual(self.case.backend.sent, [(700, int(signal.SIGTERM))])
        self.assertEqual(len(terminal['forwarded_signals']), 1)
        self.assertEqual(len(terminal['stop_requests']), 3)
        self.assertTrue(terminal['serial_wait_completed'])
        self.assertIsNone(handlers[signal.SIGTERM])

    def test_pid_reuse_or_wrong_argv_is_not_signaled_but_actual_handle_is_waited(self):
        for mutation in ('start_ticks', 'argv'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(prefix='formal54_reuse_') as directory:
                case = Fixture(directory)
                case.launch()
                handlers = {}
                def register(number, handler):
                    old = handlers.get(number)
                    handlers[number] = handler
                    return old
                def waited(process):
                    if process.wait_calls == 1:
                        handlers[signal.SIGTERM](signal.SIGTERM)
                        if mutation == 'start_ticks':
                            case.backend.identities[process.pid]['start_ticks'] += 1
                        else:
                            case.backend.identities[process.pid]['argv'] = ['wrong-process']
                handle = FakeProcess(700, timeouts=2, on_wait=waited)
                with patch.object(owner.signal, 'signal', register):
                    terminal = case.run_worker(handle=handle, handlers=True)
                self.assertEqual(case.backend.sent, [])
                self.assertTrue(terminal['serial_wait_completed'])
                self.assertGreaterEqual(handle.wait_calls, 3)
                self.assertIn('unverified_no_signal', terminal['error'])

    def test_stop_verifies_worker_identity_and_exact_command(self):
        self.case.launch()
        report = owner.stop(self.case.owner, self.case.registry_pin['sha256'], backend=self.case.backend, wait=False)
        self.assertEqual(report['status'], 'GRACEFUL_STOP_REQUESTED_NOT_COMPLETION')
        self.assertEqual(self.case.backend.sent, [(500, int(signal.SIGTERM))])
        request = owner.bound(report['stop_request'])
        self.assertEqual(request['verified_worker_process']['argv'], self.case.backend.spawned[0][0])

    def test_stop_never_signals_reused_pid_or_changed_command(self):
        self.case.launch()
        self.case.backend.identities[500]['argv'] = ['replacement']
        with self.assertRaises(ValueError):
            owner.stop(self.case.owner, self.case.registry_pin['sha256'], backend=self.case.backend)
        self.assertEqual(self.case.backend.sent, [])

    def test_watch_interrupt_does_not_signal_spawn_or_mark_terminal(self):
        self.case.launch()
        before = len(self.case.backend.spawned)
        def interrupted(seconds):
            raise KeyboardInterrupt()
        self.case.backend.on_sleep = interrupted
        code = owner.watch(self.case.owner, self.case.registry_pin['sha256'], backend=self.case.backend, output=lambda value: None)
        self.assertEqual(code, 130)
        self.assertEqual(len(self.case.backend.spawned), before)
        self.assertEqual(self.case.backend.sent, [])
        self.assertFalse((self.case.owner/'terminal.json').exists())

    def test_missing_owner_without_terminal_is_unknown_not_finished(self):
        self.case.launch()
        self.case.backend.identities.pop(500)
        report = owner.observe(self.case.owner, self.case.registry_pin['sha256'], backend=self.case.backend)
        self.assertEqual(report['status'], 'OWNER_IDENTITY_MISSING_OR_CHANGED_EVIDENCE_INCOMPLETE')
        self.assertFalse((self.case.owner/'terminal.json').exists())

    def test_foreign_live_owner_receipt_cannot_be_reported_as_current_task_alive(self):
        self.case.launch()
        path = self.case.owner/'worker_spawned.json'
        original = owner.load(path)
        foreign = deepcopy(self.case.backend.identities[500])
        foreign.update(pid=900, pgid=900, session=900, start_ticks=9000,
                       start_token='linux:foreign:9000', argv=['foreign-owner-command'])
        self.case.backend.identities[900] = foreign
        for mutation in ('foreign-registry', 'foreign-command'):
            value = deepcopy(original)
            value.update(worker_process=foreign, command=foreign['argv'])
            if mutation == 'foreign-registry':
                value['registry'] = {'path': '/foreign/registry.json', 'sha256': 'a'*64}
            path.unlink()
            owner.write_new(path, value)
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(ValueError, 'registry/command'):
                    owner.original_worker_start(self.case.owner, self.case.registry_pin, self.case.registry)
                report = owner.observe(self.case.owner, self.case.registry_pin['sha256'], backend=self.case.backend)
                self.assertEqual(report['status'], 'OWNER_IDENTITY_MISSING_OR_CHANGED_EVIDENCE_INCOMPLETE')
                self.assertIsNone(report['worker_process'])
                with self.assertRaises(ValueError):
                    owner.stop(self.case.owner, self.case.registry_pin['sha256'], backend=self.case.backend, wait=False)
        self.assertEqual(self.case.backend.sent, [])

    def test_acknowledged_spawn_byte_pin_catches_receipt_drift_with_same_identity_and_command(self):
        self.case.launch()
        path = self.case.owner/'worker_spawned.json'
        value = owner.load(path)
        value['created_utc'] = '2020-01-01T00:00:00+00:00'
        path.unlink()
        owner.write_new(path, value)
        report = owner.observe(self.case.owner, self.case.registry_pin['sha256'], backend=self.case.backend)
        self.assertEqual(report['status'], 'OWNER_IDENTITY_MISSING_OR_CHANGED_EVIDENCE_INCOMPLETE')
        self.assertIsNone(report['worker_process'])

    def test_partial_terminal_publication_is_not_completion_or_a_reason_to_skip_stop(self):
        self.case.launch()
        path = self.case.owner/'terminal.json'
        path.write_text('{unfinished', encoding='utf-8')
        report = owner.observe(self.case.owner, self.case.registry_pin['sha256'], backend=self.case.backend)
        self.assertEqual(report['status'], 'VERIFIED_WORKER_ALIVE')
        self.assertIn('JSONDecodeError', report['terminal_publication_error'])
        report = owner.stop(self.case.owner, self.case.registry_pin['sha256'], backend=self.case.backend, wait=False)
        self.assertEqual(report['status'], 'GRACEFUL_STOP_REQUESTED_NOT_COMPLETION')
        self.assertEqual(len(self.case.backend.sent), 1)

    def test_stop_waits_until_worker_terminal_without_a_five_second_cutoff(self):
        self.case.launch()
        def progress(seconds):
            if self.case.backend.clock >= 9:
                owner.write_new(self.case.owner/'terminal.json', {'registry': self.case.registry_pin,
                    'state': 'SERIAL_EXITED_WAITED', 'serial_wait_completed': True})
        self.case.backend.on_sleep = progress
        report = owner.stop(self.case.owner, self.case.registry_pin['sha256'], backend=self.case.backend)
        self.assertGreaterEqual(self.case.backend.clock, 9)
        self.assertEqual(report['status'], 'TERMINAL_RECORDED')
        self.assertEqual(len(self.case.backend.sent), 1)

    def test_bad_worker_startup_retains_failure_terminal_with_unknown_wait(self):
        self.case.launch()
        path = self.case.prefix
        path.write_text('# changed after launch\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            owner.worker_action(self.case.owner, self.case.registry_pin['sha256'], backend=self.case.backend)
        terminal = owner.load(self.case.owner/'terminal.json')
        self.assertEqual(terminal['state'], 'WORKER_FAILED_EVIDENCE_INCOMPLETE')
        self.assertFalse(terminal['serial_wait_completed'])
        self.assertIsNone(terminal['serial_started'])

    def test_actual_backend_call_shape_is_detached_with_no_real_spawn(self):
        with patch.object(owner.subprocess, 'Popen') as popen:
            owner.LinuxBackend().spawn(['absolute-python', '-B', 'script'], stdin=subprocess.DEVNULL)
        self.assertTrue(popen.call_args.kwargs['start_new_session'])
        self.assertTrue(popen.call_args.kwargs['close_fds'])

    def test_heartbeat_io_failure_preserves_error_but_does_not_abandon_or_kill_serial(self):
        self.case.launch()
        handle = FakeProcess(700, timeouts=7, on_wait=self.case.original_terminal)
        with patch.object(owner, 'heartbeat', side_effect=OSError('synthetic publication failure')):
            terminal = self.case.run_worker(handle=handle)
        self.assertEqual(handle.wait_calls, 8)
        self.assertTrue(terminal['serial_wait_completed'])
        self.assertIn('synthetic publication failure', terminal['error'])
        self.assertEqual(self.case.backend.sent, [])

    def test_adapter_observation_records_actual_creation_and_preserves_exec_transition(self):
        self.case.launch()
        self.case.output.mkdir()
        actual = {'pid': 800, 'start_token': 'linux:synthetic:8000', 'start_ticks': 8000,
                  'pgid': 800, 'session': 800, 'state': 'S', 'argv': ['python', 'actual_adapter.py']}
        self.case.backend.identities[800] = actual
        owner.write_new(self.case.output/'lifecycle_heartbeat.json', {'child_process': actual})
        report = owner.adapter_observation(self.case.registry, self.case.backend)
        self.assertEqual(report['status'], 'KERNEL_CREATION_VERIFIED')
        self.assertEqual(report['observed_kernel_process']['argv'], actual['argv'])
        self.assertTrue(report['exec_transition_may_change_argv'])
        self.assertFalse(report['adapter_cleanup_claimed'])
        self.case.backend.identities[800]['start_ticks'] += 1
        self.assertEqual(owner.adapter_observation(self.case.registry, self.case.backend)['status'], 'NOT_CURRENTLY_VERIFIED')

    def test_late_signal_during_terminal_write_cannot_change_accepted_stop_window(self):
        self.case.launch()
        handlers = {}
        def register(number, handler):
            previous = handlers.get(number)
            handlers[number] = handler
            return previous
        original = owner.write_new
        def write(path, value):
            if Path(path).name == 'terminal.json':
                handlers[signal.SIGTERM](signal.SIGTERM)
            return original(path, value)
        with patch.object(owner.signal, 'signal', register), patch.object(owner, 'write_new', write):
            terminal = self.case.run_worker(handle=FakeProcess(700, on_wait=self.case.original_terminal), handlers=True)
        self.assertEqual(terminal['stop_requests'], [])
        self.assertTrue(terminal['stop_window_closed_with_no_owned_serial'])
        self.assertEqual(self.case.backend.sent, [])

    def test_backend_exposes_no_group_kill_or_forced_kill(self):
        with patch.object(owner.os, 'kill') as killed:
            owner.LinuxBackend().send(123, signal.SIGTERM)
            with self.assertRaises(ValueError):
                owner.LinuxBackend().send(-123, signal.SIGTERM)
            with self.assertRaises(ValueError):
                owner.LinuxBackend().send(123, 9)
        killed.assert_called_once_with(123, signal.SIGTERM)

    def test_describe_is_inert_even_when_spawn_and_send_forbidden(self):
        with (patch.object(owner.LinuxBackend, 'spawn', side_effect=AssertionError('no spawn')),
              patch.object(owner.LinuxBackend, 'send', side_effect=AssertionError('no signal'))):
            self.assertFalse(owner.description()['watch_spawns_or_signals'])

    def test_resealed_registry_cannot_change_argv_or_omit_a_required_source_pin(self):
        self.case.launch()
        for change in ('argv', 'pins'):
            value = deepcopy(self.case.registry)
            if change == 'argv':
                value['serial_command'] = ['different-command']
            else:
                value['input_pins'].pop()
            path = self.case.owner/'registry.json'
            path.unlink()
            owner.write_new(path, value)
            with self.subTest(change=change), self.assertRaises(ValueError):
                owner.read_registry(self.case.owner, owner.pin(path)['sha256'])

    def test_stop_waits_for_control_handler_readiness_before_signaling(self):
        self.case.launch()
        ready_path = self.case.owner/'worker_control_ready.json'
        ready = owner.load(ready_path)
        ready_path.unlink()
        def ready_later(seconds):
            self.assertEqual(self.case.backend.sent, [])
            if self.case.backend.clock >= .3:
                owner.write_new(ready_path, ready)
        self.case.backend.on_sleep = ready_later
        owner.stop(self.case.owner, self.case.registry_pin['sha256'], backend=self.case.backend, wait=False)
        self.assertGreaterEqual(self.case.backend.clock, .3)
        self.assertEqual(len(self.case.backend.sent), 1)


if __name__ == '__main__':
    unittest.main()
