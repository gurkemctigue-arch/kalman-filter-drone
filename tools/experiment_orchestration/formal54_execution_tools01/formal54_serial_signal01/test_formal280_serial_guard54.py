"""Small fake-guard receipts only; no actual guard, admission, ROS or WSL."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import ast
from contextlib import redirect_stdout
import io
import os
import signal
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

EXTERNAL = Path(__file__).resolve().parent
sys.path.insert(0, str(EXTERNAL))
SPEC = importlib.util.spec_from_file_location('serial_guard_subject', EXTERNAL/'formal280_serial_guard54.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


class FakeGuard:
    """Emit the real guard schemas and original state paths, using tiny files."""
    def __init__(self, test, actions):
        self.test, self.actions, self.calls = test, list(actions), 0

    def __call__(self, command, *, stdin, stdout, stderr, check):
        self.test.assertEqual(command[-3:], ['run-one', '--manifest', str(self.test.manifest)])
        self.test.assertIs(stdin, subprocess.DEVNULL)
        self.test.assertFalse(check)
        self.calls += 1
        action = self.actions.pop(0)
        if 'exception' in action:
            stdout.write(b'partial original output\n')
            raise action['exception']
        code = action.get('returncode', 0)
        if action.get('mode') in {'refuse', 'non_json', 'partial'}:
            texts = {'refuse': b'{"result":"REFUSED","error":"physical capacity","new_slot_authorized":false}',
                     'non_json': b'environment text only\n', 'partial': b'{"result":"COMPLE'}
            stdout.write(texts[action['mode']])
            stderr.write(b'original diagnostic stderr\n')
            return SimpleNamespace(returncode=code)
        if action.get('mode') == 'exhausted':
            value = {'schema_version': 1, 'kind': 'RELIABILITY_V4_GUARD_ADMISSION_CHECK', 'result': 'PASS',
                'execution': 'NO_PENDING_SLOTS', 'started_this_invocation': 0, 'next_matrix': None,
                'next_slot_id': None, 'command': None, 'manifest': m.binding(self.test.manifest),
                'manifest_sha256': self.test.value['manifest_sha256'], 'tool': self.test.value['tool'],
                'capacity': {'scheduled_slots': 280, 'pending_slots': action.get('pending', 0)}}
            value.update(action.get('mutate', {}))
            stdout.write(json.dumps(value).encode())
            return SimpleNamespace(returncode=code)
        sequence = len(m.directories(self.test.state))+1
        directory = self.test.state/f'20261031T010101_{sequence:032x}'
        directory.mkdir(parents=True)
        before = action.get('before', 1)
        slot = action.get('slot_id', 'slot'+str(self.calls))
        admission = {'schema_version': 1, 'kind': 'RELIABILITY_V4_GUARD_ADMISSION_CHECK', 'result': 'PASS',
            'manifest': m.binding(self.test.manifest), 'manifest_sha256': self.test.value['manifest_sha256'],
            'tool': self.test.value['tool'], 'next_matrix': 'core', 'next_slot_id': slot,
            'command': ['bash', 'actual-frozen-wrapper', 'run', '--max-new-trials', '1'],
            'capacity': {'scheduled_slots': 280, 'pending_slots': before}}
        admission.update(action.get('admission_mutate', {}))
        put(directory/'admission.json', admission)
        (directory/'runner.log').write_text('original runner output\n', encoding='utf-8')
        outcome = {'schema_version': 1, 'kind': 'RELIABILITY_V4_GUARD_SINGLE_INVOCATION',
            'result': 'COMPLETED', 'returncode': 0, 'error': None, 'slot_id': slot,
            'started_this_invocation': 1, 'preserved_status': action.get('status', 'PASS'),
            'runner_log': {'path': str(directory/'runner.log'), 'sha256': 'b'*64},
            'admission': m.binding(directory/'admission.json'),
            'capacity_after': {'scheduled_slots': 280, 'pending_slots': action.get('after', before-1)}}
        outcome.update(action.get('mutate', {}))
        if action.get('mode') == 'partial_receipt':
            (directory/'outcome.json').write_text('{"schema_version":', encoding='utf-8')
        else:
            put(directory/'outcome.json', outcome)
        if action.get('mode') == 'two_directories':
            (self.test.state/f'20261031T010101_{999:032x}').mkdir()
        stdout.write(b'Normal sourced-environment text before the guard result\n')
        stdout.write(json.dumps(outcome).encode())
        return SimpleNamespace(returncode=code)


class SerialGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='serial_guard_fake_only_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.state = self.root/'original-guard-state'
        self.manifest = self.root/'fake-admission.json'
        self.output = self.root/'new-batch'
        self.value = {'schema_version': 1, 'kind': 'RELIABILITY_V4_FORMAL_ADMISSION',
            'final_root': str(self.root/'frozen'), 'state_directory': str(self.state),
            'manifest_sha256': 'a'*64, 'tool': {'path': str(self.root/'fake-guard.py'), 'sha256': 'c'*64}}
        put(self.manifest, self.value)

    def run_fake(self, actions):
        fake = FakeGuard(self, actions)
        result = m.run(self.manifest, self.output, ['FAKE_GUARD_ONLY'], command_runner=fake)
        return result, fake

    def test_closed_fail_and_unknown_evidence_continue_then_zero_pending(self):
        result, fake = self.run_fake([{'before': 3, 'status': 'FAIL'},
            {'before': 2, 'status': 'INCOMPLETE_EVIDENCE'}, {'before': 1, 'status': 'EVALUATION_PENDING'}])
        self.assertEqual(fake.calls, 3)
        self.assertEqual(result['status'], 'GUARD_PENDING_EXHAUSTED')
        self.assertEqual(result['observed_terminal_status_counts'], {'FAIL': 1, 'INCOMPLETE_EVIDENCE': 1, 'EVALUATION_PENDING': 1})
        self.assertEqual(result['already_consumed_before_batch'], 277)
        self.assertEqual(result['guard_reported_pending_slots'], 0)
        self.assertIn('Normal sourced-environment text', (self.output/'0001/stdout.log').read_text())

    def test_stop_refused_nonzero_and_process_exception_never_call_again(self):
        for action in ({'before': 2, 'mutate': {'result': 'STOP'}},
                {'mode': 'refuse', 'returncode': 2}, {'mode': 'refuse', 'returncode': 0},
                {'before': 2, 'returncode': 2}, {'exception': OSError('fake executable failed')}):
            with self.subTest(action=action), tempfile.TemporaryDirectory(prefix='serial_stop_') as temporary:
                self.output = Path(temporary)/'fresh'
                result, fake = self.run_fake([action, {'before': 1}])
                self.assertEqual(fake.calls, 1)
                self.assertEqual(result['status'], 'STOPPED_ORIGINAL_RECORDS_RETAINED')
                self.assertTrue((self.output/'0001/stdout.log').is_file())
                self.assertTrue((self.output/'summary.json').is_file())

    def test_partial_nonjson_and_partial_original_receipt_stop(self):
        for mode in ('non_json', 'partial', 'partial_receipt'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix='serial_badjson_') as temporary:
                self.output = Path(temporary)/'fresh'
                result, fake = self.run_fake([{'mode': mode}, {'before': 1}])
                self.assertEqual(fake.calls, 1)
                self.assertEqual(result['status'], 'STOPPED_ORIGINAL_RECORDS_RETAINED')

    def test_running_infra_unknown_and_forged_completion_fields_stop(self):
        mutations = [{'preserved_status': value} for value in ('RUNNING', 'INFRASTRUCTURE_ERROR', 'INTERRUPTED', 'UNKNOWN')]
        mutations += [{'started_this_invocation': value} for value in (0, 2, True)]
        mutations += [{'error': 'unhandled'}, {'returncode': 2}, {'kind': 'unrelated'}, {'schema_version': True}]
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(prefix='serial_semantic_') as temporary:
                self.output = Path(temporary)/'fresh'
                result, fake = self.run_fake([{'mutate': mutation}, {'before': 1}])
                self.assertEqual(fake.calls, 1)
                self.assertEqual(result['status'], 'STOPPED_ORIGINAL_RECORDS_RETAINED')

    def test_denominator_jump_and_duplicate_slot_stop_after_original_records_retained(self):
        cases = [[{'before': 2, 'after': 0}], [{'before': 3}, {'before': 1}],
                 [{'before': 2, 'slot_id': 'same'}, {'before': 1, 'slot_id': 'same'}]]
        for actions in cases:
            with self.subTest(actions=actions), tempfile.TemporaryDirectory(prefix='serial_count_') as temporary:
                self.output = Path(temporary)/'fresh'
                result, fake = self.run_fake(actions)
                self.assertEqual(result['status'], 'STOPPED_ORIGINAL_RECORDS_RETAINED')
                self.assertEqual(fake.calls, len(actions))

    def test_wrong_manifest_and_full_denominator_are_rejected(self):
        for change in ({'manifest': {'path': str(self.root/'other.json'), 'sha256': 'f'*64}},
                       {'capacity': {'scheduled_slots': 120, 'pending_slots': 1}},
                       {'next_slot_id': 'another'}):
            with self.subTest(change=change), tempfile.TemporaryDirectory(prefix='serial_binding_') as temporary:
                self.output = Path(temporary)/'fresh'
                result, _ = self.run_fake([{'admission_mutate': change}])
                self.assertEqual(result['status'], 'STOPPED_ORIGINAL_RECORDS_RETAINED')

    def test_no_pending_original_sentinel_completes_without_claiming_new_flights(self):
        result, fake = self.run_fake([{'mode': 'exhausted'}])
        self.assertEqual(fake.calls, 1)
        self.assertEqual(result['status'], 'GUARD_PENDING_EXHAUSTED')
        self.assertEqual(result['closed_slots_this_batch'], 0)
        self.assertEqual(result['already_consumed_before_batch'], 280)

    def test_no_pending_sentinel_with_nonzero_count_or_wrong_shape_stops(self):
        for change in ({'pending': 1}, {'mutate': {'started_this_invocation': True}},
                       {'mutate': {'command': ['unexpected']}}):
            with self.subTest(change=change), tempfile.TemporaryDirectory(prefix='serial_sentinel_') as temporary:
                self.output = Path(temporary)/'fresh'
                result, _ = self.run_fake([{'mode': 'exhausted', **change}])
                self.assertEqual(result['status'], 'STOPPED_ORIGINAL_RECORDS_RETAINED')

    def test_multiple_new_guard_invocations_stop(self):
        result, fake = self.run_fake([{'mode': 'two_directories'}])
        self.assertEqual(fake.calls, 1)
        self.assertEqual(result['status'], 'STOPPED_ORIGINAL_RECORDS_RETAINED')

    def test_old_batch_output_is_not_overwritten_or_reused(self):
        self.output.mkdir()
        original = self.output/'summary.json'
        original.write_text('keep original bytes', encoding='utf-8')
        fake = FakeGuard(self, [{'before': 1}])
        self.assertRaisesRegex(ValueError, 'already exists', m.run, self.manifest,
                               self.output, ['FAKE_GUARD_ONLY'], command_runner=fake)
        self.assertEqual(fake.calls, 0)
        self.assertEqual(original.read_text(), 'keep original bytes')

    def test_metadata_parser_rejects_duplicate_nonfinite_and_trailing_text(self):
        for text in ('{"result":1,"result":2}', '{"value":NaN}', '{"a":1} extra', '{"a":'):
            self.assertRaises(ValueError, m.parse_object, text)

    def test_no_guard_state_output_or_frozen_source_output(self):
        for output in (self.state/'wrapper', self.root/'frozen/wrapper'):
            output.parent.mkdir(parents=True, exist_ok=True)
            fake = FakeGuard(self, [{'before': 1}])
            self.assertRaises(ValueError, m.run, self.manifest, output, ['FAKE'], command_runner=fake)
            self.assertEqual(fake.calls, 0)


class FakeOwnedProcess:
    def __init__(self, backend, command, code=0):
        self.pid = 543210
        self.backend = backend
        self.command = command
        self.final_code = code
        self.returncode = None
        self.waits = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.waits += 1
        if self.waits == 1 and self.backend.on_first_wait:
            self.backend.on_first_wait()
        if self.waits <= self.backend.wait_timeouts:
            raise subprocess.TimeoutExpired(self.command, timeout)
        self.returncode = self.final_code
        return self.returncode


class FakeLinuxBackend:
    def __init__(self, guard=None, *, on_first_wait=None, wait_timeouts=1, code=0):
        self.guard = guard
        self.on_first_wait = on_first_wait
        self.wait_timeouts = wait_timeouts
        self.code = code
        self.sent = []
        self.children = []
        self.identity_changes = {}

    def require_runtime(self):
        pass

    def identity(self, pid):
        value = {'pid': pid, 'start_token': 'linux:fake-boot:'+str(pid),
                 'start_ticks': pid, 'pgid': pid, 'session': pid, 'state': 'S'}
        if pid == 543210:
            value.update(self.identity_changes)
        return value

    def spawn(self, command, **kwargs):
        if self.guard:
            self.guard(command, **kwargs, check=False)
        child = FakeOwnedProcess(self, command, self.code)
        self.children.append(child)
        return child

    def send(self, pid, number):
        self.sent.append((pid, int(number)))


class OwnedSignalTests(SerialGuardTests):
    # Inherit fixtures only; original gate tests are exercised once above.
    def test_legacy_receipt_gate_functions_and_constants_are_unchanged(self):
        original = ast.parse((EXTERNAL/'formal280_serial_guard01.original.py').read_text(encoding='utf-8'))
        current = ast.parse((EXTERNAL/'formal280_serial_guard54.py').read_text(encoding='utf-8'))
        def functions(tree):
            return {node.name: ast.dump(node, include_attributes=False) for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name not in {'run', 'main'}}
        self.assertEqual(functions(original), functions(current))
        self.assertEqual(m.TOTAL, 280)
        self.assertEqual(m.CLOSED, {'PASS', 'FAIL', 'INCOMPLETE_EVIDENCE', 'EVALUATION_PENDING'})

    def run_owned(self, actions, backend, owner_setup=None):
        backend.guard = FakeGuard(self, actions)
        owner = m.OwnedGuardRunner(self.output, backend=backend, install_signal_handlers=False)
        if owner_setup:
            owner_setup(owner)
        with owner:
            result = m.run(self.manifest, self.output, ['FAKE_GUARD_ONLY'], command_runner=owner)
            owner.finish(result)
        return result, owner

    def test_owned_normal_batch_retains_fail_unknown_and_full_denominator(self):
        backend = FakeLinuxBackend(wait_timeouts=0)
        result, owner = self.run_owned([{'before': 2, 'status': 'FAIL'},
                                       {'before': 1, 'status': 'INCOMPLETE_EVIDENCE'}], backend)
        self.assertEqual(result['orchestration_state'], 'COMPLETED')
        self.assertEqual(result['observed_terminal_status_counts'], {'FAIL': 1, 'INCOMPLETE_EVIDENCE': 1})
        self.assertEqual(result['scheduled_slots'], 280)
        self.assertEqual(owner.completed_children, 2)
        self.assertEqual(backend.sent, [])
        self.assertEqual(load_test(self.output/'lifecycle_terminal.json')['state'], 'COMPLETED')

    def test_stop_forwards_one_verified_pid_waits_cleanup_and_starts_no_next_slot(self):
        for number in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(number=number), tempfile.TemporaryDirectory(prefix='owned_signal_') as temporary:
                self.output = Path(temporary)/'fresh'
                backend = FakeLinuxBackend(wait_timeouts=3)
                def setup(owner):
                    backend.on_first_wait = lambda: (owner.request_stop(number), owner.request_stop(number))
                result, owner = self.run_owned([{'before': 2, 'status': 'FAIL'}, {'before': 1}], backend, setup)
                self.assertEqual(backend.guard.calls, 1)
                self.assertEqual(backend.sent, [(543210, int(number))])
                self.assertEqual(backend.children[0].waits, 4)
                self.assertEqual(result['orchestration_state'], 'STOPPED_BY_SIGNAL')
                self.assertEqual(result['closed_slots_this_batch'], 1)
                self.assertEqual(result['observed_terminal_status_counts'], {'FAIL': 1})
                self.assertFalse((self.output/'0002').exists())
                receipt = load_test(self.output/'0001/owned_process_terminal.json')
                self.assertTrue(receipt['wait_completed'])
                self.assertFalse(receipt['descendant_cleanup_claimed'])
                self.assertEqual(receipt['returncode'], 0)
                self.assertEqual(load_test(self.output/'lifecycle_heartbeat.json')['state'], 'STOPPED_BY_SIGNAL')

    def test_identity_and_pgid_mismatch_never_signal_another_process_but_wait_handle(self):
        for change in ({'start_token': 'linux:reused:999'}, {'pgid': 999}, {'start_ticks': 999}, {'session': 999}):
            with self.subTest(change=change), tempfile.TemporaryDirectory(prefix='owned_identity_') as temporary:
                self.output = Path(temporary)/'fresh'
                backend = FakeLinuxBackend(wait_timeouts=2)
                def setup(owner):
                    def changed():
                        backend.identity_changes = change
                        owner.request_stop(signal.SIGTERM)
                    backend.on_first_wait = changed
                result, owner = self.run_owned([{'before': 2}, {'before': 1}], backend, setup)
                self.assertEqual(backend.sent, [])
                self.assertGreaterEqual(backend.children[0].waits, 3)
                self.assertEqual(backend.children[0].returncode, 0)
                self.assertEqual(backend.guard.calls, 1)
                self.assertEqual(result['orchestration_state'], 'STOPPED_BY_SIGNAL')
                self.assertIn('identity/PGID changed', result['error'])

    def test_signal_before_first_call_creates_no_guard_invocation(self):
        backend = FakeLinuxBackend()
        result, owner = self.run_owned([{'before': 1}], backend,
                                     lambda owner: owner.request_stop(signal.SIGTERM))
        self.assertEqual(backend.guard.calls, 0)
        self.assertEqual(backend.children, [])
        self.assertEqual(result['guard_calls_this_batch'], 0)
        self.assertEqual(result['orchestration_state'], 'STOPPED_BY_SIGNAL')
        self.assertEqual(result['scheduled_slots'], 280)

    def test_nonzero_exit_is_failed_not_signal_stop_and_no_retry(self):
        backend = FakeLinuxBackend(code=7, wait_timeouts=0)
        result, owner = self.run_owned([{'before': 2}, {'before': 1}], backend)
        self.assertEqual(result['orchestration_state'], 'FAILED_OR_REFUSED')
        self.assertEqual(result['guard_calls_this_batch'], 1)
        self.assertEqual(load_test(self.output/'0001/owned_process_terminal.json')['returncode'], 7)
        self.assertEqual(backend.sent, [])

    def test_owned_refusal_does_not_write_into_preexisting_output(self):
        self.output.mkdir()
        marker = self.output/'old-evidence.json'
        marker.write_bytes(b'old immutable evidence')
        backend = FakeLinuxBackend()
        owner = m.OwnedGuardRunner(self.output, backend=backend, install_signal_handlers=False)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            with owner:
                m.run(self.manifest, self.output, ['FAKE_GUARD_ONLY'], command_runner=owner)
        self.assertEqual(list(self.output.iterdir()), [marker])
        self.assertEqual(marker.read_bytes(), b'old immutable evidence')
        self.assertEqual(backend.children, [])

    def test_heartbeat_io_failure_requests_owned_stop_and_waits_before_terminal(self):
        backend = FakeLinuxBackend(wait_timeouts=3)
        def setup(owner):
            original = owner.heartbeat
            calls = []
            def fail_once():
                if owner.child is not None and not calls:
                    calls.append(1)
                    raise OSError('synthetic heartbeat disk full')
                return original()
            owner.heartbeat = fail_once
        result, owner = self.run_owned([{'before': 2}, {'before': 1}], backend, setup)
        self.assertEqual(backend.guard.calls, 1)
        self.assertEqual(backend.sent, [(543210, int(signal.SIGTERM))])
        self.assertEqual(backend.children[0].returncode, 0)
        self.assertIn('synthetic heartbeat disk full', result['error'])
        self.assertEqual(result['orchestration_state'], 'FAILED_OR_REFUSED')
        self.assertEqual(result['stop_requests'][0]['source'], 'cleanup_after_error')

    def test_original_archive_digest_and_inert_describe(self):
        from owned_guard_process54 import describe, ORIGINAL_SERIAL_SHA256
        value = describe()
        self.assertEqual(m.digest(EXTERNAL/'formal280_serial_guard01.original.py'), ORIGINAL_SERIAL_SHA256)
        self.assertFalse(value['actual_formal_execution_started'])
        self.assertFalse(value['native_signal_validation_claimed'])
        self.assertIsNone(value['batch_timeout_s'])
        self.assertIsNone(value['cleanup_timeout_s'])

    def test_real_handler_registration_is_restored_without_sending_a_signal(self):
        previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
        owner = m.OwnedGuardRunner(self.output, backend=FakeLinuxBackend())
        with owner:
            for number in previous:
                self.assertEqual(signal.getsignal(number), owner.request_stop)
        for number, handler in previous.items():
            self.assertEqual(signal.getsignal(number), handler)
        self.assertFalse(self.output.exists())

    def test_real_backend_uses_isolated_session_and_positive_pid_signal_only(self):
        from owned_guard_process54 import LinuxBackend
        backend = LinuxBackend()
        with patch('owned_guard_process54.subprocess.Popen') as spawn:
            backend.spawn(['DUMMY_ONLY'], stdin=subprocess.DEVNULL, stdout='out', stderr='err')
        spawn.assert_called_once_with(['DUMMY_ONLY'], start_new_session=True,
                                      stdin=subprocess.DEVNULL, stdout='out', stderr='err')
        with patch('owned_guard_process54.os.kill') as send:
            backend.send(543210, signal.SIGTERM)
        send.assert_called_once_with(543210, signal.SIGTERM)

    def test_second_child_identity_capture_exception_cannot_reuse_first_child_identity(self):
        class SecondIdentityFails(FakeLinuxBackend):
            def spawn(backend, command, **kwargs):
                child = super().spawn(command, **kwargs)
                child.pid += len(backend.children)
                return child

            def identity(backend, pid):
                if pid == 543212:
                    raise OSError('second child stat unreadable')
                return super().identity(pid)

        backend = SecondIdentityFails(wait_timeouts=1)
        result, owner = self.run_owned([{'before': 2}, {'before': 1}], backend)
        first = load_test(self.output/'0001/owned_process_terminal.json')
        second = load_test(self.output/'0002/owned_process_terminal.json')
        self.assertEqual(first['child_process']['pid'], 543211)
        self.assertFalse(first['identity_unverified'])
        self.assertEqual(second['owned_popen_pid'], backend.children[1].pid)
        self.assertEqual(second['owned_popen_pid'], 543212)
        self.assertIsNone(second['child_process'])
        self.assertTrue(second['identity_unverified'])
        self.assertIn('second child stat unreadable', second['identity_capture_error'])
        self.assertTrue(second['wait_completed'])
        self.assertEqual(second['returncode'], 0)
        self.assertGreaterEqual(backend.children[1].waits, 2)
        self.assertEqual(backend.sent, [])
        self.assertEqual(result['guard_calls_this_batch'], 2)
        self.assertEqual(result['closed_slots_this_batch'], 1)
        self.assertEqual(result['orchestration_state'], 'FAILED_OR_REFUSED')
        self.assertEqual(result['scheduled_slots'], 280)
        self.assertFalse((self.output/'0003').exists())

    def test_signal_after_annotation_and_explicit_terminal_boundary_keep_one_final_decision(self):
        import owned_guard_process54 as owned_module
        for timing in ('after_provisional_annotation', 'after_closed_boundary'):
            with self.subTest(timing=timing), tempfile.TemporaryDirectory(prefix='owned_terminal_race_') as temporary:
                self.output = Path(temporary)/'fresh'
                backend = FakeLinuxBackend(wait_timeouts=0)
                saved_owner = []
                original_write = owned_module.write_new
                def setup(owner):
                    saved_owner.append(owner)
                    original_annotate = owner.annotate
                    def annotate(result):
                        original_annotate(result)
                        if timing == 'after_provisional_annotation' and not owner.stop_window_closed:
                            self.assertEqual(result['orchestration_state'], 'COMPLETED')
                            owner.request_stop(signal.SIGTERM)
                    owner.annotate = annotate
                def write_at_boundary(path, value):
                    if timing == 'after_closed_boundary' and Path(path).name == 'summary.json':
                        self.assertTrue(saved_owner[0].stop_window_closed)
                        saved_owner[0].request_stop(signal.SIGTERM)
                    return original_write(path, value)
                with patch.object(owned_module, 'write_new', side_effect=write_at_boundary):
                    result, owner = self.run_owned([{'before': 1}], backend, setup)
                summary = load_test(self.output/'summary.json')
                terminal = load_test(self.output/'lifecycle_terminal.json')
                heartbeat = load_test(self.output/'lifecycle_heartbeat.json')
                expected = 'STOPPED_BY_SIGNAL' if timing == 'after_provisional_annotation' else 'COMPLETED'
                expected_code = 2 if timing == 'after_provisional_annotation' else 0
                self.assertEqual(result, summary)
                self.assertEqual(summary['orchestration_state'], expected)
                self.assertEqual(terminal['state'], expected)
                self.assertEqual(heartbeat['state'], expected)
                self.assertEqual(summary['stop_requests'], terminal['stop_requests'])
                self.assertEqual(summary['stop_requests'], heartbeat['stop_requests'])
                self.assertEqual(summary['terminal_boundary'], terminal['terminal_boundary'])
                self.assertEqual(summary['terminal_boundary'], heartbeat['terminal_boundary'])
                self.assertEqual(summary['serial_exit_code'], expected_code)
                self.assertEqual(terminal['serial_exit_code'], expected_code)
                self.assertEqual(len(owner.post_terminal_requests), int(timing == 'after_closed_boundary'))
                with patch.object(m, 'run', return_value=result), redirect_stdout(io.StringIO()):
                    code = m.main(['--manifest', str(self.manifest), '--output', str(self.output),
                                   '--guard-command', 'DUMMY_ONLY'])
                self.assertEqual(code, expected_code)


# Avoid duplicating inherited legacy cases while reusing their fixture setup.
for _name in list(SerialGuardTests.__dict__):
    if _name.startswith('test_'):
        setattr(OwnedSignalTests, _name, None)


def load_test(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
