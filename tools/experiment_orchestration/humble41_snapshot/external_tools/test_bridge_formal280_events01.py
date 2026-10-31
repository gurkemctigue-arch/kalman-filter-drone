"""Tiny synthetic metadata only; imports the existing monitor without starting it."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

EXTERNAL = Path(__file__).resolve().parent
PROJECT = Path(os.environ.get('UAV_BRIDGE_PROJECT_ROOT', str(Path.cwd()))).resolve()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


b = module('formal_bridge_subject', EXTERNAL/'bridge_formal280_events01.py')
monitor = module('existing_progress_monitor_fixture', PROJECT/'scripts/monitor_project_progress.py')


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, allow_nan=False)+'\n').encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='formal_bridge_fake_only_', dir=EXTERNAL)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pair()

    def pair(self, core_count=2, extension_count=2, duplicate=False):
        self.core_path, self.extension_path = self.root/'core/plan.json', self.root/'extension/plan.json'
        self.total = core_count+extension_count
        common = {'schema_version': 1, 'study_kind': 'POST_REPAIR_ENGINEERING_VALIDATION',
                  'protocol': {'scope': 'FAKE_METADATA_ONLY'}, 'protocol_sha256': 'c'*64}
        self.core = dict(common, mode='FORMAL', trials=[{'id': f'core_{i}',
            'flight_command': ['NEVER_EXECUTED_FAKE', str(i)]} for i in range(core_count)])
        self.core['plan_sha256'] = b.canonical(self.core, 'plan_sha256')
        self.core_sha = put(self.core_path, self.core)
        self.extension = dict(common, mode='EXTENSION_FORMAL', trials=[{'id': f'extension_{i}',
            'flight_command': ['NEVER_EXECUTED_FAKE', str(i)]} for i in range(extension_count)],
            core_reference_binding={'path': str(self.core_path), 'sha256': self.core_sha,
                                    'plan_sha256': self.core['plan_sha256']})
        if duplicate:
            self.extension['trials'][0]['id'] = self.core['trials'][0]['id']
        self.extension['plan_sha256'] = b.canonical(self.extension, 'plan_sha256')
        self.extension_sha = put(self.extension_path, self.extension)

    def subject(self):
        return b.PlanEvents(self.core_path, self.core_sha, self.extension_path, self.extension_sha,
                           total=self.total)

    def marker(self, matrix, index):
        plan, path = (self.core, self.core_path) if matrix == 'core' else (self.extension, self.extension_path)
        trial = plan['trials'][index]
        value = {'id': trial['id'], 'plan_sha256': plan['plan_sha256'],
                 'flight_command': trial['flight_command'], 'started_utc': '2026-10-31T01:00:00+00:00'}
        put(path.parent/'slots'/(trial['id']+'.started.json'), value)

    def terminal(self, matrix, index, status='PASS', *, start=True):
        if start:
            self.marker(matrix, index)
        plan, path = (self.core, self.core_path) if matrix == 'core' else (self.extension, self.extension_path)
        slot = plan['trials'][index]['id']
        value = {'id': slot, 'plan_sha256': plan['plan_sha256'], 'status': status,
                 'engineering_result': status, 'execution_status': 'COMPLETED',
                 'finished_utc': '2026-10-31T01:01:00+00:00',
                 'infrastructure_stop': status in {'INFRASTRUCTURE_ERROR', 'INTERRUPTED'}}
        value['record_sha256'] = b.canonical(value, 'record_sha256')
        p = path.parent/'slots'/(slot+'.json')
        put(p, value)
        return p

    def summary(self, rows):
        p = self.root/'fixture_events.jsonl'
        p.write_text(''.join(json.dumps(x)+'\n' for x in rows), encoding='utf-8')
        return monitor.evidence_summary(monitor.source_records({'events': str(p)}))

    def run_fake(self, subject=None, checker=None, batch=None, token='FAKE_KERNEL_CREATION'):
        return b.run_bridge(subject or self.subject(), self.root/'new_observer', pid=123,
            expected_token=token, identity_provider=lambda pid: {'pid': pid, 'alive': True,
                'start_token': 'FAKE_KERNEL_CREATION'},
            identity_checker=checker or (lambda identity: {'verified_alive': False}),
            batch_summary=batch, sleeper=lambda seconds: None, allowed_parent=self.root)

    def test_empty_two_plan_header_keeps_actual280_unattempted(self):
        self.pair(120, 160)
        s = self.subject()
        report = self.summary([s.header()]+s.scan())
        self.assertEqual((report['planned_slots'], report['attempted_slots'],
                          report['recorded_terminal_slots'], report['unattempted_slots']), (280, 0, 0, 280))
        self.assertEqual(report['state'], 'UNVERIFIED')

    def test_both_plans_standard_events_preserve_fail_and_pending_denominators(self):
        self.terminal('core', 0, 'FAIL')
        self.marker('extension', 0)
        s = self.subject()
        rows = [s.header()]+s.scan()
        report = self.summary(rows)
        self.assertEqual((report['attempted_slots'], report['recorded_terminal_slots'],
                          report['unattempted_slots']), (2, 1, 2))
        self.assertEqual(report['attempted_without_terminal'], ['extension_0'])
        self.assertEqual(report['status_counts'], {'FAIL': 1})
        self.assertEqual(report['current_slot'], 'extension_0')
        completed = next(x for x in rows if x['event'] == 'COMPLETE_SLOT')
        self.assertEqual(completed['matrix'], 'core')
        self.assertEqual(completed['original_source']['sha256'],
            hashlib.sha256((self.core_path.parent/'slots/core_0.json').read_bytes()).hexdigest())
        self.assertEqual(s.scan(), [])

    def test_global_duplicate_ids_and_wrong_plan_sha_refuse(self):
        self.pair(duplicate=True)
        self.assertRaisesRegex(ValueError, 'globally unique', self.subject)
        self.pair()
        self.assertRaises(ValueError, b.PlanEvents, self.core_path, 'f'*64,
                          self.extension_path, self.extension_sha, total=4)

    def test_extension_reference_and_declared_count_must_match(self):
        self.assertRaisesRegex(ValueError, 'denominator', b.PlanEvents, self.core_path, self.core_sha,
                              self.extension_path, self.extension_sha, total=5)
        self.extension['core_reference_binding']['sha256'] = 'd'*64
        self.extension['plan_sha256'] = b.canonical(self.extension, 'plan_sha256')
        self.extension_sha = put(self.extension_path, self.extension)
        self.assertRaisesRegex(ValueError, 'does not bind', self.subject)

    def test_unknown_running_or_orphaned_terminal_never_complete(self):
        self.terminal('core', 0, 'UNKNOWN')
        self.terminal('core', 1, 'RUNNING')
        self.terminal('extension', 0, 'PASS', start=False)
        s = self.subject()
        report = self.summary([s.header()]+s.scan())
        self.assertEqual(report['recorded_terminal_slots'], 0)
        self.assertEqual(report['attempted_slots'], 2)
        self.assertEqual(len(s.unclosed), 3)

    def test_partial_json_waits_then_original_closure_emits_once(self):
        self.marker('core', 0)
        p = self.core_path.parent/'slots/core_0.json'
        p.write_text('{"id":', encoding='utf-8')
        s = self.subject()
        self.assertEqual([x['event'] for x in s.scan()], ['START_SLOT'])
        self.terminal('core', 0, 'INCOMPLETE_EVIDENCE')
        self.assertEqual([x['event'] for x in s.scan()], ['COMPLETE_SLOT'])
        self.assertEqual(s.scan(), [])

    def test_changed_record_or_marker_binding_refuses_transactionally(self):
        self.marker('core', 0)
        p = self.terminal('core', 1)
        value = json.loads(p.read_text())
        value['engineering_result'] = 'FORGED_WITHOUT_RESEAL'
        put(p, value)
        s = self.subject()
        self.assertRaisesRegex(ValueError, 'digest', s.scan)
        self.assertEqual(s.seen, set())
        p.unlink()
        marker = self.core_path.parent/'slots/core_1.started.json'
        value = json.loads(marker.read_text())
        value['plan_sha256'] = 'f'*64
        put(marker, value)
        self.assertRaisesRegex(ValueError, 'identity', s.scan)

    def test_changed_plan_and_duplicate_nonfinite_metadata_refuse(self):
        s = self.subject()
        self.core_path.write_text('{}')
        self.assertRaisesRegex(ValueError, 'plan changed', s.scan)
        p = self.root/'bad.json'
        for raw in ('{"a":1,"a":2}', '{"a":NaN}'):
            p.write_text(raw)
            self.assertRaises(ValueError, b.small_json, p)

    def test_infrastructure_original_status_is_closed_and_fault_is_visible(self):
        self.terminal('extension', 1, 'INFRASTRUCTURE_ERROR')
        s = self.subject()
        report = self.summary([s.header()]+s.scan())
        self.assertEqual(report['recorded_terminal_slots'], 1)
        self.assertEqual(report['status_counts'], {'INFRASTRUCTURE_ERROR': 1})
        self.assertEqual(report['state'], 'STOPPED_FAULT')

    def test_final_scan_after_creation_identity_exit_keeps_outcome_unknown(self):
        self.marker('core', 0)
        def checker(identity):
            self.terminal('core', 0, 'FAIL')
            return {'verified_alive': False, 'identity_matches': False}
        result = self.run_fake(checker=checker)
        self.assertEqual((result['start_events'], result['complete_events']), (1, 1))
        self.assertIn('OUTCOME_UNKNOWN', result['reason'])
        self.assertFalse(result['engineering_verdict_computed'])

    def test_reused_pid_refuses_before_creating_output_and_never_reuses_output(self):
        self.assertRaises(ValueError, self.run_fake, token='DIFFERENT_CREATION')
        self.assertFalse((self.root/'new_observer').exists())
        self.run_fake()
        self.assertRaisesRegex(ValueError, 'Fresh external', self.run_fake)

    def test_batch_zero_pending_never_manufactures_missing_slot_completions(self):
        p = self.root/'original_batch_summary.json'
        put(p, {'schema_version': 1, 'scope': b.BATCH_SCOPE, 'status': 'GUARD_PENDING_EXHAUSTED'})
        result = self.run_fake(batch=p)
        self.assertEqual((result['start_events'], result['complete_events'], result['unattempted_slots']), (0, 0, 4))
        rows = [json.loads(x) for x in (self.root/'new_observer/events.jsonl').read_text().splitlines()]
        self.assertEqual(self.summary(rows)['state'], 'UNVERIFIED')

    def test_all_closed_is_execution_complete_even_with_fail_not_allpass(self):
        for matrix in ('core', 'extension'):
            for i in range(2):
                self.terminal(matrix, i, 'FAIL' if i else 'EVALUATION_PENDING')
        s = self.subject()
        report = self.summary([s.header()]+s.scan())
        self.assertEqual(report['state'], 'COMPLETED')
        self.assertEqual(report['unattempted_slots'], 0)
        self.assertEqual(report['status_counts'], {'EVALUATION_PENDING': 2, 'FAIL': 2})
        self.assertNotIn('PASS', report['status_counts'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
