"""Private JSON fixtures: complete denominator, original FAIL and PID final scan."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

import bridge_development_events as m

ROOT = '/root/uav_tracking_fullplan_v4_fixture42'
PREFIX = 'fixture42_probe'


def fixture(kind='core'):
    groups = m.original.GROUPS if kind == 'core' else m.CONDITIONS
    trials = []
    for cls in m.CLASSES:
        for group in groups:
            slot = f'{cls}_{group}_seed004' if kind == 'core' else f'{cls}_extension_{group}_seed004'
            trials.append({'id': slot, 'target_class': cls, 'seed': 4,
                'group' if kind == 'core' else 'extension_condition': group,
                'flight_command': ['synthetic-no-execution', slot]})
    plan = {'schema_version': 1, 'mode': 'PROBE' if kind == 'core' else 'EXTENSION_PROBE',
        'frozen_root': ROOT, 'prefix': PREFIX, 'selected_classes': list(m.CLASSES),
        'selected_seeds': [4], 'selected_groups': list(m.original.GROUPS) if kind == 'core'
            else ['stage1_velocity', 'stage1_position'], 'trials': trials}
    if kind == 'extension':
        plan['selected_extension_conditions'] = list(m.CONDITIONS)
    return plan


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value)+'\n', encoding='utf-8')
    return m.sha(path)


def load(path, plan, kind='core'):
    plan['plan_sha256'] = m.reader.canonical(plan, 'plan_sha256')
    return m.DevelopmentEvents(path, save(path, plan), root=ROOT, prefix=PREFIX, kind=kind)


class BridgeTests(unittest.TestCase):
    def test_pending_both_complete_denominators(self):
        for kind, count in [('core', 12), ('extension', 16)]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                bridge = load(Path(directory)/'plan.json', fixture(kind), kind)
                self.assertEqual(bridge.header()['total'], count)
                self.assertEqual(bridge.scan(), [])

    def test_foreign_binding_or_formal_partial_boolean_seed_refused(self):
        for defect in ['root', 'prefix', 'mode', 'partial', 'seed', 'order', 'trial']:
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                plan = fixture()
                if defect == 'root': plan['frozen_root'] += '_foreign'
                elif defect == 'prefix': plan['prefix'] += '_foreign'
                elif defect == 'mode': plan['mode'] = 'FORMAL'
                elif defect == 'partial': plan['trials'].pop()
                elif defect == 'seed': plan['selected_seeds'] = [True]
                elif defect == 'order': plan['trials'].reverse()
                else: plan['trials'][0]['target_class'] = 'car'
                self.assertRaises(ValueError, load, Path(directory)/'plan.json', plan)

    def test_original_fail_final_scan_preserves_unattempted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = fixture()
            bridge = load(root/'plan.json', plan); trial = plan['trials'][0]; slot = trial['id']
            save(root/'slots'/(slot+'.started.json'), {'id': slot,
                'plan_sha256': plan['plan_sha256'], 'flight_command': trial['flight_command'],
                'started_utc': '2000-01-01T00:00:00Z'})
            terminal = {'id': slot, 'plan_sha256': plan['plan_sha256'], 'status': 'FAIL',
                'engineering_result': 'FAIL', 'execution_status': 'COMPLETED',
                'finished_utc': '2000-01-01T00:01:00Z'}
            terminal['record_sha256'] = m.reader.canonical(terminal, 'record_sha256')
            save(root/'slots'/(slot+'.json'), terminal)
            result = m.original.run_bridge(bridge, root/'out', pid=12, expected_token='fixture',
                identity_provider=lambda pid: {'pid': pid, 'alive': True, 'start_token': 'fixture'},
                identity_checker=lambda identity: {'verified_alive': False}, allowed_parent=root,
                sleeper=lambda seconds: self.fail('Unexpected wait'))
            self.assertEqual((result['planned_slots'], result['start_events'],
                              result['complete_events'], result['unattempted_slots']), (12, 1, 1, 11))
            rows = [json.loads(line) for line in (root/'out/events.jsonl').read_text().splitlines()]
            self.assertEqual([r['status'] for r in rows if r['event'] == 'COMPLETE_SLOT'], ['FAIL'])
            self.assertFalse(result['engineering_verdict_computed'])

    def test_unknown_not_promoted_and_drift_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan = fixture(); path = root/'plan.json'
            bridge = load(path, plan); trial = plan['trials'][0]; slot = trial['id']
            save(root/'slots'/(slot+'.started.json'), {'id': slot,
                'plan_sha256': plan['plan_sha256'], 'flight_command': trial['flight_command'],
                'started_utc': '2000-01-01T00:00:00Z'})
            terminal = {'id': slot, 'plan_sha256': plan['plan_sha256'], 'status': 'UNKNOWN',
                'engineering_result': 'UNKNOWN', 'execution_status': 'COMPLETED',
                'finished_utc': '2000-01-01T00:01:00Z'}
            terminal['record_sha256'] = m.reader.canonical(terminal, 'record_sha256')
            save(root/'slots'/(slot+'.json'), terminal)
            self.assertEqual([r['event'] for r in bridge.scan()], ['START_SLOT'])
            plan['extra'] = True; save(path, plan)
            self.assertRaises(ValueError, bridge.scan)

    def test_pid_reuse_refused_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); bridge = load(root/'plan.json', fixture())
            self.assertRaises(ValueError, m.original.run_bridge, bridge, root/'out', pid=12,
                expected_token='old', identity_provider=lambda pid:
                    {'pid': pid, 'alive': True, 'start_token': 'reused'},
                identity_checker=lambda identity: {'verified_alive': True}, allowed_parent=root)
            self.assertFalse((root/'out').exists())

    def test_describe_inert(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(m.main(['describe']), 0)
        record = json.loads(output.getvalue())
        self.assertFalse(record['actual_action_executed'])
        self.assertFalse(record['tool_manifest']['engineering_verdict_computed'])


if __name__ == '__main__':
    unittest.main()
