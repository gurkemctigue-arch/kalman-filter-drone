"""Pure fixture checks for the reused event reader; never watch a real PID."""
from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bridge_humble41_events01 as m


# Explicit fixture location, independent of the shell's current directory.
# An override also supports a frozen checkout in a different reviewed location.
TEST_PROJECT_ROOT = Path(os.environ.get('HUMBLE41_BRIDGE_TEST_PROJECT_ROOT',
    'D:/基于yolo和卡尔曼滤波' if os.name == 'nt' else m.ROOT))


def plan_fixture(kind='core'):
    ids = [f'{cls}_{group}_seed004' for cls in ('person', 'car') for group in m.GROUPS]
    value = {'schema_version': 1, 'mode': 'PROBE', 'frozen_root': m.ROOT,
        'prefix': m.PREFIXES[kind], 'selected_seeds': [4],
        'trials': [{'id': slot, 'flight_command': ['synthetic', slot]} for slot in ids]}
    value['plan_sha256'] = m.reader.canonical(value, 'plan_sha256')
    return value


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value)+'\n', encoding='utf-8')
    return m.sha(path)


def marker(plan, slot):
    trial = next(item for item in plan['trials'] if item['id'] == slot)
    return {'id': slot, 'plan_sha256': plan['plan_sha256'],
            'flight_command': trial['flight_command'], 'started_utc': '2000-01-01T00:00:00Z'}


def terminal(plan, slot, status='FAIL'):
    value = {'id': slot, 'plan_sha256': plan['plan_sha256'], 'status': status,
        'engineering_result': status, 'execution_status': 'COMPLETED',
        'finished_utc': '2000-01-01T00:01:00Z'}
    value['record_sha256'] = m.reader.canonical(value, 'record_sha256')
    return value


class BridgeTests(unittest.TestCase):
    def test_probe_mode_is_not_supported_and_cannot_create_output(self):
        with self.assertRaises(SystemExit), patch('sys.stderr', io.StringIO()):
            m.main(['watch', '--kind', 'probe'])
        self.assertEqual(m.tool_manifest()['kind_counts'], {'core': 12})

    def test_four_original_terminals_after_infrastructure_stop_keep_twelve_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'plan.json'; plan = plan_fixture()
            reader = m.DevelopmentEvents(path, save(path, plan), 'core')
            for number, trial in enumerate(plan['trials'][:4]):
                slot = trial['id']
                save(root/'slots'/(slot+'.started.json'), marker(plan, slot))
                value = terminal(plan, slot, 'PASS' if number < 3 else 'INFRASTRUCTURE_ERROR')
                if number == 3:
                    value.update(infrastructure_stop=True, execution_status='INTERRUPTED')
                    value['record_sha256'] = m.reader.canonical(value, 'record_sha256')
                save(root/'slots'/(slot+'.json'), value)
            result = m.run_bridge(reader, root/'output', pid=12, expected_token='synthetic',
                identity_provider=lambda pid: {'pid': pid, 'alive': True, 'start_token': 'synthetic'},
                identity_checker=lambda identity: {'verified_alive': False}, allowed_parent=root,
                sleeper=lambda seconds: self.fail('No sleep expected after exit'))
            self.assertEqual(result['planned_slots'], 12)
            self.assertEqual(result['start_events'], 4)
            self.assertEqual(result['complete_events'], 4)
            self.assertEqual(result['unattempted_slots'], 8)
            self.assertEqual(result['attempted_without_terminal'], [])
            self.assertFalse(result['engineering_verdict_computed'])
            rows = [json.loads(line) for line in (root/'output/events.jsonl').read_text().splitlines()]
            completed = [row for row in rows if row['event'] == 'COMPLETE_SLOT']
            self.assertEqual([row['status'] for row in completed], ['PASS']*3+['INFRASTRUCTURE_ERROR'])
            self.assertEqual(sum(row['event'] == 'INFRASTRUCTURE_STOP_NO_AUTOMATIC_RETRY' for row in rows), 1)

    def test_describe_is_inert_and_resolves_the_actual_reused_reader(self):
        with patch.object(m, 'DevelopmentEvents') as source, patch.object(m, 'run_bridge') as run, \
            redirect_stdout(io.StringIO()) as output:
            self.assertEqual(m.main(['describe']), 0)
        value = json.loads(output.getvalue())
        self.assertEqual(value['tool_manifest']['scope'],
                         'HUMBLE41_READONLY_DEVELOPMENT_PROGRESS_EVENTS_ONLY')
        self.assertEqual(value['tool_manifest']['reused_reader_sha256'], m.READER_SHA)
        self.assertIn('test_bridge_humble41_events01.py', value['tool_manifest']['files'])
        self.assertFalse(value['actual_action_executed'])
        source.assert_not_called(); run.assert_not_called()

    def test_core_header_retains_all_12_pending_cells(self):
        for kind, count in (('core', 12),):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'plan.json'; plan = plan_fixture(kind)
                reader = m.DevelopmentEvents(path, save(path, plan), kind)
                self.assertEqual(reader.header()['total'], count)
                self.assertEqual(reader.scan(), [])
                self.assertEqual(reader.seen, set())

    def test_foreign_root_formal_mode_bool_seed_or_partial_core_cannot_be_observed(self):
        for defect in ('root', 'old39_root', 'old39_prefix', 'mode', 'seed', 'partial', 'order', 'sha'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'plan.json'; plan = plan_fixture()
                if defect == 'root': plan['frozen_root'] = '/root/uav_tracking_fullplan_v4_humble38'
                elif defect == 'old39_root': plan['frozen_root'] = '/root/uav_tracking_fullplan_v4_humble39'
                elif defect == 'old39_prefix': plan['prefix'] = 'reliability_v4_humble39_probe01'
                elif defect == 'mode': plan['mode'] = 'FORMAL'
                elif defect == 'seed': plan['selected_seeds'] = [True]
                elif defect == 'partial': plan['trials'].pop()
                elif defect == 'order': plan['trials'].reverse()
                plan['plan_sha256'] = m.reader.canonical(plan, 'plan_sha256')
                digest = save(path, plan)
                self.assertRaises(ValueError, m.DevelopmentEvents, path,
                                  '0'*64 if defect == 'sha' else digest, 'core')

    def test_original_closed_fail_requires_the_original_start_and_remains_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'plan.json'; plan = plan_fixture('core')
            reader = m.DevelopmentEvents(path, save(path, plan), 'core'); slot = plan['trials'][0]['id']
            save(root/'slots'/(slot+'.json'), terminal(plan, slot))
            self.assertEqual(reader.scan(), [])
            self.assertIn(slot, reader.unclosed)
            save(root/'slots'/(slot+'.started.json'), marker(plan, slot))
            rows = reader.scan()
            self.assertEqual([row['event'] for row in rows], ['START_SLOT', 'COMPLETE_SLOT'])
            self.assertEqual(rows[-1]['status'], 'FAIL')
            self.assertEqual(rows[-1]['engineering_result'], 'FAIL')
            self.assertEqual(reader.scan(), [])

    def test_unknown_and_unfinished_producer_never_create_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'plan.json'; plan = plan_fixture('core')
            reader = m.DevelopmentEvents(path, save(path, plan), 'core'); slot = plan['trials'][0]['id']
            save(root/'slots'/(slot+'.started.json'), marker(plan, slot))
            save(root/'slots'/(slot+'.json'), terminal(plan, slot, 'UNKNOWN'))
            self.assertEqual([row['event'] for row in reader.scan()], ['START_SLOT'])
            (root/'slots'/(slot+'.json')).write_text('{unfinished', encoding='utf-8')
            self.assertEqual(reader.scan(), [])
            self.assertNotIn(('COMPLETE_SLOT', slot), reader.seen)

    def test_new_core_prerequisite_pass_does_not_supply_missing_slot_evidence(self):
        # require_completed_core40 returns result=PASS for a healthy, fully
        # audited execution even when individual engineering cells FAIL. The
        # separate all_original_core_cells_pass field controls that distinction.
        # This bridge never imports or calls that verifier and must not infer
        # terminal slots from its return object or a driver-level PASS.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'plan.json'; plan = plan_fixture()
            prerequisites = {'result': 'PASS', 'completed_count': 12,
                'all_original_core_cells_pass': False,
                'original_terminals': [{'id': trial['id'], 'status': 'FAIL'}
                                       for trial in plan['trials']],
                'formal_seed_use_authorized': False}
            plan['prerequisites'] = prerequisites
            plan['protocol'] = {'supported_birth_confirmation_runtime':
                                {'car': True, 'person': False}}
            plan['plan_sha256'] = m.reader.canonical(plan, 'plan_sha256')
            reader = m.DevelopmentEvents(path, save(path, plan), 'core')
            save(root/'observed_driver01'/'execution_terminal.json', prerequisites)
            self.assertEqual(reader.scan(), [])
            self.assertEqual(reader.total, 12)
            self.assertEqual(reader.seen, set())
            for trial in plan['trials']:
                slot = trial['id']
                save(root/'slots'/(slot+'.started.json'), marker(plan, slot))
                save(root/'slots'/(slot+'.json'), terminal(plan, slot))
            rows = reader.scan()
            completed = [row for row in rows if row['event'] == 'COMPLETE_SLOT']
            self.assertEqual(len(completed), 12)
            self.assertEqual({row['status'] for row in completed}, {'FAIL'})
            self.assertEqual({row['engineering_result'] for row in completed}, {'FAIL'})
            manifest = m.tool_manifest()
            self.assertFalse(manifest['consumes_prerequisite_results'])
            self.assertFalse(manifest['may_admit_core_or_change_verdict'])

    def test_bad_record_digest_rolls_back_partial_scan_and_plan_drift_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'plan.json'; plan = plan_fixture('core')
            reader = m.DevelopmentEvents(path, save(path, plan), 'core'); slot = plan['trials'][0]['id']
            save(root/'slots'/(slot+'.started.json'), marker(plan, slot))
            value = terminal(plan, slot); value['record_sha256'] = '0'*64
            save(root/'slots'/(slot+'.json'), value)
            self.assertRaises(ValueError, reader.scan)
            self.assertEqual(reader.seen, set())
            plan['extra'] = True; save(path, plan)
            self.assertRaises(ValueError, reader.scan)

    def test_all_12_algorithm_failures_are_preserved_for_the_existing_progress_page(self):
        path = TEST_PROJECT_ROOT/'scripts/monitor_project_progress.py'
        self.assertEqual(m.sha(path), m.MONITOR_SHA)
        spec = importlib.util.spec_from_file_location('humble41_fake_progress_count', path)
        monitor = importlib.util.module_from_spec(spec); spec.loader.exec_module(monitor)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan_path = root/'plan.json'; plan = plan_fixture()
            reader = m.DevelopmentEvents(plan_path, save(plan_path, plan), 'core')
            for trial in plan['trials']:
                slot = trial['id']
                save(root/'slots'/(slot+'.started.json'), marker(plan, slot))
                save(root/'slots'/(slot+'.json'), terminal(plan, slot))
            summary = monitor.evidence_summary({'events': [reader.header(), *reader.scan()],
                'ledger': None, 'plan': plan, 'errors': []})
            self.assertEqual(summary['planned_slots'], 12)
            self.assertEqual(summary['recorded_terminal_slots'], 12)
            self.assertEqual(summary['status_counts'], {'FAIL': 12})
            self.assertEqual(summary['state'], 'COMPLETED')
            self.assertIn('never counted as PASS', summary['claim_boundary'])

    def test_mismatched_pid_creation_identity_cannot_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'plan.json'; plan = plan_fixture()
            reader = m.DevelopmentEvents(path, save(path, plan), 'core')
            self.assertRaises(ValueError, m.run_bridge, reader, root/'output', pid=12,
                expected_token='expected', identity_provider=lambda pid: {'pid': pid, 'alive': True,
                'start_token': 'reused'}, identity_checker=lambda identity: {'verified_alive': True},
                allowed_parent=root)
            self.assertFalse((root/'output').exists())

    def test_exited_pid_never_supplies_missing_slots_or_engineering_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'plan.json'; plan = plan_fixture()
            reader = m.DevelopmentEvents(path, save(path, plan), 'core')
            result = m.run_bridge(reader, root/'output', pid=12, expected_token='synthetic',
                identity_provider=lambda pid: {'pid': pid, 'alive': True, 'start_token': 'synthetic'},
                identity_checker=lambda identity: {'verified_alive': False}, allowed_parent=root,
                sleeper=lambda seconds: self.fail('No sleep expected after exit'))
            self.assertEqual(result['complete_events'], 0)
            self.assertEqual(result['unattempted_slots'], 12)
            self.assertFalse(result['engineering_verdict_computed'])
            self.assertIn('OUTCOME_UNKNOWN', result['reason'])

    def test_one_final_scan_observes_a_terminal_written_at_pid_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'plan.json'; plan = plan_fixture('core')
            reader = m.DevelopmentEvents(path, save(path, plan), 'core'); slot = plan['trials'][0]['id']
            def exited(identity):
                save(root/'slots'/(slot+'.started.json'), marker(plan, slot))
                save(root/'slots'/(slot+'.json'), terminal(plan, slot))
                return {'verified_alive': False}
            result = m.run_bridge(reader, root/'output', pid=12, expected_token='synthetic',
                identity_provider=lambda pid: {'pid': pid, 'alive': True, 'start_token': 'synthetic'},
                identity_checker=exited, allowed_parent=root)
            self.assertEqual(result['start_events'], 1)
            self.assertEqual(result['complete_events'], 1)
            rows = [json.loads(line) for line in (root/'output/events.jsonl').read_text().splitlines()]
            self.assertEqual(rows[-1]['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
