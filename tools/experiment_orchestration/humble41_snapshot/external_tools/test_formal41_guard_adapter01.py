"""Tiny synthetic metadata and original-guard/fake-child tests; no WSL or ROS."""
from contextlib import contextmanager, nullcontext, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import formal41_guard_adapter01 as m
import formal280_serial_guard01 as serial

SOURCE = Path(os.environ.get('STAGE1_PROJECT_ROOT') or
              ('D:/基于yolo和卡尔曼滤波' if os.name == 'nt' else '/mnt/d/基于yolo和卡尔曼滤波'))


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False)+'\n', encoding='utf-8')
    return m.binding(path)


class FakeOwner:
    def __init__(self, archive, root, *, fail_check=None, late_failure=False, missing=False, on_finish=None):
        self.archive, self.root = archive, root
        self.fail_check, self.late_failure, self.missing = fail_check, late_failure, missing
        self.on_finish = on_finish
        self._finished = None
        self.checks = 0
        self.finished = False

    def __enter__(self):
        return self

    def check(self):
        self.checks += 1
        if self.fail_check == self.checks:
            raise RuntimeError('Original10s observer stale')
        return {'sample_age_wall_s': 0., 'max_sample_age_wall_s': 10.}

    def __exit__(self, kind, value, traceback):
        self.finish(exception=kind is not None)
        if self.late_failure:
            raise RuntimeError('Archive process exceeded original1800s budget')

    def finish(self, exception=False):
        if self.on_finish:
            self.on_finish()
        self.finished = True
        if not self.missing:
            good = not exception and not self.late_failure
            self._finished = {'status': 'COMPLETE' if good else 'OWNER_INFRA_ERROR',
                'healthy_cleanup': good, 'archive_process': {'returncode': 0 if good else None,
                    'forced_stop': not good, 'elapsed_wall_s': 18., 'wall_budget_s': 1800.},
                'copy_terminal': {'path': str(self.archive/'execution_terminal.json'), 'sha256': 'a'*64}}
        return self._finished


class FakeProcess:
    def __init__(self, completed, *, natural_code=0, stop_after=signal.SIGINT, on_wait=None):
        self.returncode = None
        self.completed = completed
        self.natural_code, self.stop_after, self.on_wait = natural_code, stop_after, on_wait
        self.signals, self.waits = [], []

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.waits.append(timeout)
        if self.returncode is not None:
            return self.returncode
        if self.signals:
            raise subprocess.TimeoutExpired('fake owned runner', timeout)
        if self.on_wait:
            self.on_wait()
        self.completed()
        self.returncode = self.natural_code
        return self.returncode

    def send_signal(self, sent):
        self.signals.append(sent)
        if sent == self.stop_after:
            self.returncode = -int(sent)


class FormalAdapterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='formal41_fake_only_')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base/'arbitrary_final_root_not_development41'
        (self.root/'tools').mkdir(parents=True)
        (self.root/'scripts').mkdir()
        (self.root/'results').mkdir()
        self.tool = self.root/m.GUARD_RELATIVE
        self.tool.write_bytes((SOURCE/m.GUARD_RELATIVE).read_bytes())
        self.collector = self.root/m.COLLECTOR_RELATIVE
        self.collector.write_bytes(b'# synthetic collector; never executed\n')
        p = patch.object(m, 'COLLECTOR_SHA', m.binding(self.collector)['sha256'])
        p.start(); self.addCleanup(p.stop)
        hashes = {m.COLLECTOR_RELATIVE: m.COLLECTOR_SHA, m.RUNNER_RELATIVE: 'c'*64}
        self.plan_bindings = {}
        for label, mode in (('core', 'FORMAL'), ('extension', 'EXTENSION_FORMAL')):
            self.plan_bindings[label] = dump(self.root/'results'/label/'plan.json', {
                'mode': mode, 'frozen_root': str(self.root), 'source_hashes': hashes,
                'evidence_scope': 'FIXTURE_ONLY_NOT_FORMAL_EVIDENCE'})
        self.state = self.root/'results'/'original_guard_state'
        self.manifest_path = self.base/'synthetic_manifest.json'
        self.manifest = {'schema_version': 1, 'kind': 'RELIABILITY_V4_FORMAL_ADMISSION',
            'final_root': str(self.root), 'state_directory': str(self.state),
            'plans': self.plan_bindings, 'tool': m.binding(self.tool),
            'evidence_scope': 'FIXTURE_ONLY_NOT_FORMAL_EVIDENCE'}
        self.manifest['manifest_sha256'] = m.canonical(self.manifest)
        dump(self.manifest_path, self.manifest)
        self.tools_sha = m.canonical(m.tool_manifest())
        self.context = m.load_context(self.manifest_path, m.binding(self.manifest_path)['sha256'], self.tools_sha)

    def guard_fixture(self, *, status='PASS', owner_options=None, process_options=None):
        guard = m.load_original_guard(self.context)
        after = {'slot': {'status': 'PENDING', 'infrastructure_stop': False}}
        original = deepcopy(after)
        plan = self.context.plans['core']['data']
        command = ['bash', str(self.root/'scripts/run_research_session.sh'),
            str(self.root/m.RUNNER_RELATIVE), 'run', '--plan', str(self.context.plans['core']['path']),
            '--max-new-trials', '1']
        capacity = {'scheduled_slots': 280, 'pending_slots': 280}
        report = {'schema_version': 1, 'kind': 'RELIABILITY_V4_GUARD_ADMISSION_CHECK',
            'result': 'PASS', 'created_utc': '2026-10-31T00:00:00+00:00',
            'manifest': self.context.manifest_binding,
            'manifest_sha256': self.manifest['manifest_sha256'], 'tool': self.manifest['tool'],
            'next_matrix': 'core', 'next_slot_id': 'slot', 'capacity': capacity, 'command': command}
        admission = SimpleNamespace(manifest=self.manifest, state=self.state, report=report,
            context=SimpleNamespace(root=self.root, core=plan),
            runtime=SimpleNamespace(v4=SimpleNamespace(read_slots=Mock(return_value=after))),
            rows={'core': original, 'extension': {}})
        lock_events, owners, children = [], [], []
        @contextmanager
        def lock():
            lock_events.append('enter')
            yield
            lock_events.append('exit')
        def make_owner(archive, root, **kwargs):
            self.assertEqual(kwargs, {'archive_wall_budget_s': 1800.})
            self.assertEqual(root, self.root)
            value = FakeOwner(archive, root, **(owner_options or {}))
            owners.append(value)
            return value
        def popen(argv, **kwargs):
            self.assertEqual(argv, command)
            self.assertEqual(kwargs['cwd'], self.root)
            self.assertIs(kwargs['stderr'], subprocess.STDOUT)
            self.assertTrue(kwargs['start_new_session'])
            self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
            def completed():
                after['slot'] = {'status': status, 'infrastructure_stop': False}
            value = FakeProcess(completed, **(process_options or {}))
            children.append(value)
            return value
        def validate(actual, archive, root):
            self.assertTrue(owners[-1].finished)
            record = m.parse_json(m.file_bytes(archive.parent/'owner_result.json'))
            self.assertEqual(record['observer_owner_terminal'], actual)
            self.assertFalse((archive.parent.parent/'outcome.json').exists())
            if actual is None or actual.get('healthy_cleanup') is not True:
                raise ValueError('Original complete actual owner outcome required')
            return {'owner_terminal': actual, 'native_and_archive_verified': True}
        def capacity_after(*args):
            return {'scheduled_slots': 280, 'pending_slots': 280-int(after['slot']['status'] != 'PENDING')}
        return SimpleNamespace(guard=guard, admission=admission, checker=Mock(return_value=admission),
            after=after, command=command, lock=lock, lock_events=lock_events,
            make_owner=make_owner, popen=popen, validate=validate,
            capacity_after=capacity_after, owners=owners, children=children)

    def invoke(self, fixture, signals=None):
        observed = m.ObservedRunner(self.context, signals)
        with patch.object(fixture.guard, 'guard_lock', fixture.lock), \
                patch.object(fixture.guard, 'validate_storage', side_effect=fixture.capacity_after), \
                patch.object(m.owner, 'make_observer', side_effect=fixture.make_owner), \
                patch.object(m.owner, 'validate_observer_root', side_effect=fixture.validate), \
                patch.object(m, 'simulation_processes', return_value=[]), \
                patch.object(m.subprocess, 'Popen', side_effect=fixture.popen) as spawn:
            result = fixture.guard.execute_one(self.context.path, checker=fixture.checker,
                command_runner=observed)
            observed.retain_guard_outcome(result)
        self.assertEqual(fixture.lock_events, ['enter', 'exit'])
        return result, observed, spawn

    def test_ordinary_algorithm_FAIL_keeps_original_guard_ledger_and_serial_closure(self):
        fixture = self.guard_fixture(status='FAIL')
        result, observed, spawn = self.invoke(fixture)
        self.assertEqual((result['result'], result['preserved_status'], result['returncode']),
                         ('COMPLETED', 'FAIL', 0))
        self.assertEqual(result['started_this_invocation'], 1)
        self.assertEqual(fixture.after['slot']['status'], 'FAIL')
        self.assertEqual(result['capacity_after']['pending_slots'], 279)
        self.assertEqual(spawn.call_count, 1)
        owned = m.parse_json(m.file_bytes(observed.directory/'execution_terminal.json'))
        raw = m.parse_json(m.file_bytes(observed.directory/'owner_result.json'))
        self.assertEqual(owned['observer']['owner_terminal'], raw['observer_owner_terminal'])
        self.assertEqual(raw['command_execution']['command'], fixture.command)
        self.assertFalse(raw['command_execution']['forced_stop'])
        self.assertTrue((observed.directory/'guard_outcome_binding.json').is_file())
        outcome, _, before, after = serial.completed_receipt(observed.directory.parent,
            self.context.path, self.manifest, self.context.manifest_binding)
        self.assertEqual((outcome['preserved_status'], before, after), ('FAIL', 280, 279))

    def test_late_archive_failure_becomes_original_guard_STOP_without_rewriting_PASS_slot(self):
        fixture = self.guard_fixture(owner_options={'late_failure': True})
        result, observed, spawn = self.invoke(fixture)
        self.assertEqual((result['result'], result['preserved_status']), ('STOP', 'PASS'))
        self.assertIn('1800s', result['error'])
        self.assertIsNone(result['returncode'])
        raw = m.parse_json(m.file_bytes(observed.directory/'owner_result.json'))
        self.assertEqual(raw['command_execution']['returncode'], 0)
        self.assertEqual(raw['observer_owner_terminal']['status'], 'OWNER_INFRA_ERROR')
        self.assertEqual(fixture.after['slot']['status'], 'PASS')
        self.assertEqual(spawn.call_count, 1)
        with self.assertRaises(ValueError):
            serial.completed_receipt(observed.directory.parent, self.context.path,
                                     self.manifest, self.context.manifest_binding)

    def test_live_observer_failure_cleans_only_owned_child_and_original_guard_stops(self):
        fixture = self.guard_fixture(owner_options={'fail_check': 2})
        result, observed, spawn = self.invoke(fixture)
        self.assertEqual((result['result'], result['preserved_status']), ('STOP', 'PENDING'))
        self.assertEqual(fixture.children[0].signals, [signal.SIGINT])
        self.assertEqual(fixture.children[0].waits, [240])
        raw = m.parse_json(m.file_bytes(observed.directory/'owner_result.json'))
        self.assertEqual(raw['command_execution']['returncode'], -int(signal.SIGINT))
        self.assertTrue(raw['command_execution']['forced_stop'])
        self.assertEqual(spawn.call_count, 1)

    def test_full_original240_30_10_cleanup_graces_are_retained_and_forced_exit_fails(self):
        # Fake numeric POSIX SIGKILL on Windows, without issuing any OS signal.
        with patch.object(m.signal, 'SIGKILL', 9, create=True):
            fixture = self.guard_fixture(owner_options={'fail_check': 2},
                                         process_options={'stop_after': 9})
            result, observed, _ = self.invoke(fixture)
        child = fixture.children[0]
        self.assertEqual(result['result'], 'STOP')
        self.assertEqual(child.waits, [240, 30, 10])
        raw = m.parse_json(m.file_bytes(observed.directory/'owner_result.json'))
        self.assertTrue(raw['command_execution']['forced_stop'])
        self.assertEqual([row['grace_s'] for row in raw['command_execution']['outer_cleanup_actions']], child.waits)

    def test_owner_first_sample_failure_preserves_all_pending_without_launch(self):
        fixture = self.guard_fixture(owner_options={'fail_check': 1})
        result, observed, spawn = self.invoke(fixture)
        self.assertEqual((result['result'], result['started_this_invocation']), ('STOP', 0))
        self.assertEqual(result['capacity_after']['pending_slots'], 280)
        spawn.assert_not_called()
        raw = m.parse_json(m.file_bytes(observed.directory/'owner_result.json'))
        self.assertIsNone(raw['command_execution']['returncode'])

    def test_stop_during_owner_archive_is_deferred_until_full_actual_result_then_guard_STOP(self):
        # Call the installed Python handler directly; no OS signal is sent.
        with m.stop_signals() as signals:
            fixture = self.guard_fixture(owner_options={'on_finish': lambda:
                m.signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)})
            result, observed, _ = self.invoke(fixture, signals)
        self.assertEqual((result['result'], result['preserved_status']), ('STOP', 'PASS'))
        self.assertTrue(fixture.owners[0].finished)
        raw = m.parse_json(m.file_bytes(observed.directory/'owner_result.json'))
        self.assertEqual(raw['observer_owner_terminal']['status'], 'COMPLETE')
        self.assertEqual(raw['command_execution']['returncode'], 0)
        self.assertEqual(raw['command_execution']['stop_requests'], [int(signal.SIGTERM)])
        self.assertEqual(fixture.children[0].signals, [])

    def test_stop_during_owned_runner_still_interrupts_and_uses_original_cleanup(self):
        with m.stop_signals() as signals:
            fixture = self.guard_fixture(process_options={'on_wait': lambda:
                m.signal.getsignal(signal.SIGINT)(signal.SIGINT, None)})
            result, observed, _ = self.invoke(fixture, signals)
        self.assertEqual(result['result'], 'STOP')
        self.assertEqual(fixture.children[0].signals, [signal.SIGINT])
        raw = m.parse_json(m.file_bytes(observed.directory/'owner_result.json'))
        self.assertEqual(raw['command_execution']['stop_requests'], [int(signal.SIGINT)])
        self.assertTrue(raw['command_execution']['forced_stop'])

    def test_original_serial_batch_stops_after_one_late_archive_failure(self):
        fixture = self.guard_fixture(owner_options={'late_failure': True})
        calls = []
        def child(command, **kwargs):
            calls.append(command)
            original_result, observed, _ = self.invoke(fixture)
            kwargs['stdout'].write(json.dumps(original_result).encode('utf-8'))
            self.assertTrue((observed.directory/'guard_outcome_binding.json').is_file())
            return subprocess.CompletedProcess(command, 2)
        result = serial.run(self.context.path, self.base/'new_external_serial_batch',
                            ['fake-env', 'fake-reviewed-adapter'], command_runner=child)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['guard_calls_this_batch'], 1)
        self.assertEqual(result['closed_slots_this_batch'], 0)
        self.assertEqual(result['status'], 'STOPPED_ORIGINAL_RECORDS_RETAINED')
        self.assertEqual(fixture.after['slot']['status'], 'PASS')

    def test_missing_actual_owner_result_is_persisted_and_never_promoted_from_D(self):
        fixture = self.guard_fixture(owner_options={'missing': True})
        result, observed, _ = self.invoke(fixture)
        self.assertEqual(result['result'], 'STOP')
        raw = m.parse_json(m.file_bytes(observed.directory/'owner_result.json'))
        self.assertIsNone(raw['observer_owner_terminal'])
        owned = m.parse_json(m.file_bytes(observed.directory/'execution_terminal.json'))
        self.assertIsNone(owned['observer'])
        self.assertEqual(owned['status'], 'STOP_REQUIRED')

    def test_manifest_drift_during_original_command_stops_guard_after_retaining_owner(self):
        fixture = self.guard_fixture(process_options={'on_wait': lambda:
            self.manifest_path.write_bytes(self.manifest_path.read_bytes()+b'\n')})
        result, observed, _ = self.invoke(fixture)
        self.assertEqual((result['result'], result['preserved_status']), ('STOP', 'PASS'))
        self.assertIn('sealed manifest changed', result['error'])
        self.assertTrue((observed.directory/'owner_result.json').is_file())

    def test_collector_source_drift_during_command_cannot_reuse_owner_PASS(self):
        fixture = self.guard_fixture(process_options={'on_wait': lambda:
            self.collector.write_bytes(self.collector.read_bytes()+b'# drift\n')})
        result, observed, _ = self.invoke(fixture)
        self.assertEqual(result['result'], 'STOP')
        self.assertIn('collector source changed', result['error'])
        self.assertTrue((observed.directory/'owner_result.json').is_file())

    def test_preexisting_owned_directory_refuses_without_child_or_overwrite(self):
        fixture = self.guard_fixture()
        observed = m.ObservedRunner(self.context)
        invocation = self.state/('20261031T000000_'+'a'*32)
        invocation.mkdir(parents=True)
        dump(invocation/'admission.json', fixture.admission.report)
        (invocation/m.OWNED_NAME).mkdir()
        marker = invocation/m.OWNED_NAME/'old.txt'
        marker.write_text('original', encoding='utf-8')
        with (invocation/'runner.log').open('x') as stream, \
                patch.object(m.subprocess, 'Popen') as spawn, self.assertRaisesRegex(ValueError, 'no overwrite'):
            observed(fixture.command, cwd=self.root, stdout=stream, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(marker.read_text(encoding='utf-8'), 'original')
        spawn.assert_not_called()

    def test_original_guard_bytes_are_checked_before_execution(self):
        self.tool.write_bytes(self.tool.read_bytes()+b'\n# drift\n')
        with patch.object(m.importlib.util, 'spec_from_file_location') as load, \
                self.assertRaisesRegex(ValueError, 'guard source changed'):
            m.load_original_guard(self.context)
        load.assert_not_called()

    def test_guard_path_swap_after_hash_executes_only_checked_bytes_and_refuses(self):
        original = self.tool.read_bytes()
        marker = self.base/'untrusted_guard_executed.txt'
        replacement = ('from pathlib import Path\nPath('+repr(str(marker))+').write_text("BAD")\n').encode()
        spec = m.importlib.util.spec_from_file_location
        def swap(name, path):
            self.tool.write_bytes(replacement)
            return spec(name, path)
        with patch.object(m.importlib.util, 'spec_from_file_location', side_effect=swap), \
                self.assertRaisesRegex(ValueError, 'path/bytes changed'):
            m.load_original_guard(self.context)
        self.assertFalse(marker.exists())
        self.assertNotEqual(self.tool.read_bytes(), original)

    def test_bad_manifest_digest_or_candidate_refuses_without_execution(self):
        with self.assertRaisesRegex(ValueError, 'digest changed'):
            m.load_context(self.manifest_path, '0'*64, self.tools_sha)
        changed = deepcopy(self.manifest)
        changed['kind'] = 'CANDIDATE_NOT_REGISTERED'
        changed['manifest_sha256'] = m.canonical({key: value for key, value in changed.items() if key != 'manifest_sha256'})
        dump(self.manifest_path, changed)
        with self.assertRaisesRegex(ValueError, 'sealed formal admission'):
            m.load_context(self.manifest_path, m.binding(self.manifest_path)['sha256'], self.tools_sha)

    def test_adapter_does_not_add_sitl_lock_or_modify_guard_execute_one_arguments(self):
        expected = {'execution': 'NO_PENDING_SLOTS', 'result': 'PASS'}
        guard = SimpleNamespace(execute_one=Mock(return_value=expected))
        with patch.object(m, 'require_runtime'), patch.object(m, 'load_original_guard', return_value=guard), \
                patch.object(m, 'stop_signals', nullcontext), \
                patch.object(m.ObservedRunner, 'retain_guard_outcome') as retain:
            self.assertEqual(m.run_one(self.context, {'core': {'path': '/original', 'sha256': 'f'*64}}), expected)
        args, kwargs = guard.execute_one.call_args
        self.assertEqual(args, (self.context.path,))
        self.assertEqual(set(kwargs), {'resolutions', 'command_runner'})
        self.assertIsInstance(kwargs['command_runner'], m.ObservedRunner)
        retain.assert_called_once_with(expected)
        text = (m.EXTERNAL/'formal41_guard_adapter01.py').read_text(encoding='utf-8')
        self.assertNotIn('run_lock(', text)
        self.assertNotIn('exclusive_window(', text)

    def test_cli_missing_explicit_sealed_manifest_refuses_before_runtime(self):
        with patch.object(m, 'run_one') as run, patch.object(m, 'write_new') as write, \
                patch.object(m.subprocess, 'Popen') as spawn, redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(['run-one']), 2)
        run.assert_not_called(); write.assert_not_called(); spawn.assert_not_called()

    def test_describe_is_inert_and_has_no_default_development_root_or_manifest(self):
        with patch.object(m, 'load_original_guard') as load, patch.object(m, 'write_new') as write, \
                patch.object(m.subprocess, 'Popen') as spawn, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(m.main(['describe']), 0)
        value = json.loads(output.getvalue())
        self.assertFalse(value['actual_action_executed'])
        self.assertIsNone(value['manifest']['default_manifest'])
        load.assert_not_called(); write.assert_not_called(); spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
