"""Small synthetic extension metadata only; no real plans, PIDs or runtime calls."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bridge_formal280_events01 as reader
import bridge_humble41_events01 as core
import bridge_humble41_extension_events01 as m


EXTERNAL = Path(__file__).resolve().parent
CONDITIONS = ('depth_noise', 'depth_holes', 'dropout', 'latency', 'combined',
              'speed_changes_velocity', 'speed_changes_position', 'far_distance')
EXPECTED_IDS = [f'{cls}_extension_{condition}_seed004'
                for cls in ('person', 'car') for condition in CONDITIONS]


def fixture():
    value = {'schema_version': 1, 'mode': 'EXTENSION_PROBE',
        'frozen_root': '/root/uav_tracking_fullplan_v4_humble41',
        'prefix': 'reliability_v4_humble41_extensions_probe',
        'selected_classes': ['person', 'car'], 'selected_seeds': [4],
        'selected_groups': ['stage1_velocity', 'stage1_position'],
        'selected_extension_conditions': list(CONDITIONS),
        'trials': [{'id': f'{cls}_extension_{condition}_seed004',
            'target_class': cls, 'seed': 4, 'extension_condition': condition,
            'flight_command': ['NEVER_EXECUTED_FIXTURE', cls, condition]}
            for cls in ('person', 'car') for condition in CONDITIONS]}
    value['plan_sha256'] = reader.canonical(value, 'plan_sha256')
    return value


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, allow_nan=False)+'\n').encode('utf-8')
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


class ExtensionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='extension41_events_fake_', dir=EXTERNAL)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path, self.plan = self.root/'plan.json', fixture()
        self.digest = put(self.path, self.plan)

    def subject(self):
        return m.ExtensionEvents(self.path, self.digest)

    def marker(self, index):
        trial = self.plan['trials'][index]
        return put(self.root/'slots'/(trial['id']+'.started.json'), {
            'id': trial['id'], 'plan_sha256': self.plan['plan_sha256'],
            'flight_command': trial['flight_command'], 'started_utc': '2000-01-01T00:00:00Z'})

    def terminal(self, index, status='FAIL', *, start=True):
        if start:
            self.marker(index)
        slot = self.plan['trials'][index]['id']
        value = {'id': slot, 'plan_sha256': self.plan['plan_sha256'], 'status': status,
            'engineering_result': status, 'execution_status': 'COMPLETED',
            'finished_utc': '2000-01-01T00:01:00Z'}
        value['record_sha256'] = reader.canonical(value, 'record_sha256')
        path = self.root/'slots'/(slot+'.json')
        put(path, value)
        return path

    def run_fake(self, *, bridge=None, provider=None, checker=None, output='output'):
        return m.run_bridge(bridge or self.subject(), self.root/output, pid=123,
            expected_token='FAKE_CREATION_ONLY', allowed_parent=self.root,
            identity_provider=provider or (lambda pid: {'pid': pid, 'alive': True,
                                                       'start_token': 'FAKE_CREATION_ONLY'}),
            identity_checker=checker or (lambda identity: {'verified_alive': False}),
            sleeper=lambda seconds: self.fail('No sleep expected after fake process exit'))

    def test_pending_header_retains_exact_16_and_reuses_existing_loop(self):
        bridge = self.subject()
        self.assertIs(m.run_bridge, core.run_bridge)
        self.assertIsInstance(bridge, reader.PlanEvents)
        self.assertEqual((bridge.total, bridge.kind, bridge.header()['total']), (16, 'extension', 16))
        self.assertEqual([entry['slot'] for entry in bridge.entries], EXPECTED_IDS)
        self.assertEqual(bridge.scan(), [])
        result = self.run_fake(bridge=bridge)
        self.assertEqual((result['planned_slots'], result['start_events'], result['complete_events'],
                          result['unattempted_slots']), (16, 0, 0, 16))
        self.assertFalse(result['engineering_verdict_computed'])

    def test_foreign_scope_partial_order_ids_or_digest_refuse(self):
        for defect in ('root', 'mode', 'prefix', 'conditions', 'id', 'order', 'partial',
                       'seed', 'trial_class', 'trial_extension_condition', 'trial_float_seed4',
                       'internal_digest', 'file_digest'):
            with self.subTest(defect=defect):
                value = deepcopy(self.plan)
                if defect == 'root': value['frozen_root'] = '/root/uav_tracking_fullplan_v4_humble40'
                elif defect == 'mode': value['mode'] = 'EXTENSION_FORMAL'
                elif defect == 'prefix': value['prefix'] = 'reliability_v4_humble40_extensions_probe'
                elif defect == 'conditions': value['selected_extension_conditions'].reverse()
                elif defect == 'id': value['trials'][0]['id'] = 'person_stage1_velocity_seed004'
                elif defect == 'order': value['trials'].reverse()
                elif defect == 'partial': value['trials'].pop()
                elif defect == 'seed': value['selected_seeds'] = [True]
                elif defect == 'trial_class': value['trials'][0]['target_class'] = 'car'
                elif defect == 'trial_extension_condition': value['trials'][0]['extension_condition'] = 'latency'
                elif defect == 'trial_float_seed4': value['trials'][0]['seed'] = 4.0
                value['plan_sha256'] = reader.canonical(value, 'plan_sha256')
                if defect == 'internal_digest': value['plan_sha256'] = '0'*64
                digest = put(self.path, value)
                self.assertRaises(ValueError, m.ExtensionEvents, self.path,
                                  '0'*64 if defect == 'file_digest' else digest)

    def test_future_missing_plan_refuses_without_creating_observer_output(self):
        missing = self.root/'future_extension'/'plan.json'
        with self.assertRaises((OSError, ValueError)):
            self.run_fake(bridge=m.ExtensionEvents(missing, '0'*64))
        self.assertFalse(missing.exists())
        self.assertFalse((self.root/'output').exists())

    def test_closed_fail_is_preserved_and_unknown_or_orphan_never_complete(self):
        terminal = self.terminal(0, 'FAIL')
        self.terminal(1, 'UNKNOWN')
        self.terminal(8, 'PASS', start=False)
        bridge = self.subject()
        result = self.run_fake(bridge=bridge)
        self.assertEqual((result['start_events'], result['complete_events'],
                          result['unattempted_slots']), (2, 1, 14))
        self.assertEqual(result['attempted_without_terminal'], [EXPECTED_IDS[1]])
        rows = [json.loads(line) for line in (self.root/'output/events.jsonl').read_text().splitlines()]
        completed = [row for row in rows if row['event'] == 'COMPLETE_SLOT']
        self.assertEqual([(row['status'], row['engineering_result']) for row in completed], [('FAIL', 'FAIL')])
        self.assertEqual(completed[0]['original_source']['sha256'], hashlib.sha256(terminal.read_bytes()).hexdigest())
        self.assertEqual(set(bridge.unclosed), {EXPECTED_IDS[1], EXPECTED_IDS[8]})
        self.assertEqual(bridge.scan(), [])

    def test_unfinished_terminal_waits_and_emits_original_closure_once(self):
        self.marker(0)
        path = self.root/'slots'/(EXPECTED_IDS[0]+'.json')
        path.write_text('{"id":', encoding='utf-8')
        bridge = self.subject()
        self.assertEqual([row['event'] for row in bridge.scan()], ['START_SLOT'])
        self.assertNotIn(('COMPLETE_SLOT', EXPECTED_IDS[0]), bridge.seen)
        self.terminal(0, 'INCOMPLETE_EVIDENCE', start=False)
        rows = bridge.scan()
        self.assertEqual([(row['event'], row['status']) for row in rows], [('COMPLETE_SLOT', 'INCOMPLETE_EVIDENCE')])
        self.assertEqual(bridge.scan(), [])

    def test_record_digest_failure_rolls_back_scan_and_plan_drift_refuses(self):
        path = self.terminal(0)
        original = json.loads(path.read_text(encoding='utf-8'))
        put(path, dict(original, engineering_result='FORGED_WITHOUT_DIGEST'))
        bridge = self.subject()
        self.assertRaises(ValueError, bridge.scan)
        self.assertEqual(bridge.seen, set())
        put(path, original)
        self.assertEqual([row['event'] for row in bridge.scan()], ['START_SLOT', 'COMPLETE_SLOT'])
        put(self.path, dict(self.plan, changed_after_binding=True))
        self.assertRaises(ValueError, bridge.scan)

    def test_dead_or_reused_pid_refuses_before_creating_output(self):
        for alive, token in ((False, 'FAKE_CREATION_ONLY'), (True, 'REUSED_CREATION')):
            with self.subTest(alive=alive, token=token):
                self.assertRaises(ValueError, self.run_fake,
                    provider=lambda pid: {'pid': pid, 'alive': alive, 'start_token': token})
                self.assertFalse((self.root/'output').exists())

    def test_final_scan_captures_terminal_written_at_identity_exit(self):
        checks = []
        def exited(identity):
            checks.append(identity)
            self.terminal(15, 'FAIL')
            return {'verified_alive': False, 'identity_matches': False}
        result = self.run_fake(checker=exited)
        self.assertEqual(len(checks), 1)
        self.assertEqual((result['planned_slots'], result['start_events'], result['complete_events'],
                          result['unattempted_slots']), (16, 1, 1, 15))
        self.assertIn('OUTCOME_UNKNOWN', result['reason'])
        self.assertFalse(result['engineering_verdict_computed'])
        rows = [json.loads(line) for line in (self.root/'output/events.jsonl').read_text().splitlines()]
        completed = next(row for row in rows if row['event'] == 'COMPLETE_SLOT')
        self.assertEqual((completed['slot'], completed['number'], completed['matrix'], completed['status']),
                         (EXPECTED_IDS[15], 16, 'extension', 'FAIL'))

    def test_describe_is_inert_and_cli_has_no_kind_override(self):
        with patch.object(m, 'ExtensionEvents') as source, patch.object(m, 'run_bridge') as run, \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(m.main(['describe']), 0)
        self.assertFalse(json.loads(output.getvalue())['actual_action_executed'])
        source.assert_not_called(); run.assert_not_called()
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit):
            m.main(['watch', '--kind', 'extension'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
