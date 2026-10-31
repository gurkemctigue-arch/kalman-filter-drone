"""Small fake-guard receipts only; no actual guard, admission, ROS or WSL."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

EXTERNAL = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('serial_guard_subject', EXTERNAL/'formal280_serial_guard01.py')
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
