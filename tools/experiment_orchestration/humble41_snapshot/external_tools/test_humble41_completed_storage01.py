"""Pure stdlib fixtures; never import ROS or run real prerequisites/measure."""
from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

EXTERNAL = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('storage38_fixture_subject',
    EXTERNAL / 'measure_humble41_completed_storage01.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


class ReceiptFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='storage38_fixture_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.object(m, 'ROOT', self.root).start()
        self.directory = self.root / 'results/reliability_v4_humble41_person_seed004'
        self.directory.mkdir(parents=True)
        self.trial = {'id':'person_seed004', 'name':self.directory.name,
            'directory':str(self.directory), 'seed':4, 'duration_s':75}
        self.plan = {'plan_sha256':'plan38'}
        self.closed = {'record_sha256':'terminal38'}
        self.checks = SimpleNamespace(require_completed_record=Mock(return_value=self.closed))
        self.runner = object()
        bag = self.directory / 'rosbag/rosbag_0.db3.zstd'
        bag.parent.mkdir()
        bag.write_bytes(b'compressed fixture - never decoded')
        self.reports = {
            'bag_integrity.json': {'status':'PASS', 'policy':m.ARCHIVE_POLICY,
                'recorder_exit_code':0, 'spool_retained':False,
                'raw_validation':{'status':'PASS', 'files':[{'path':'rosbag_0.db3','bytes':100}]},
                'native_reader_validation':{'status':'PASS','full_stream_read':True},
                'compressed_files':[{'path':'rosbag_0.db3.zstd','bytes':bag.stat().st_size,
                    'raw_bytes':100,'zstd_test':'PASS'}],
                'archive_processing':{'started_at_utc':'2026-10-30T01:00:00+00:00',
                    'finished_at_utc':'2026-10-30T01:00:01+00:00','wall_s':1,
                    'scope':'closed_recording_validation_compression_native_read_verified_copy_and_owned_spool_cleanup'}},
            'recording_closure.json':{'status':'PASS','observations':[{'last_clock_ns':85_000_000_000}]},
            'summary.json':{'follow_start_s':10,'termination_reason':'follow_duration_reached'},
            'process_exit_codes.json':{'gazebo':0,'px4':0,'ros':0,'bag':0,'monitor':0,'agent':-2},
            'run_config.json':{'duration_s':75,'seed':4}}
        self.record = {'status':'FAIL','artifact_hashes':{}}
        self.persist()

    def persist(self):
        for name, value in self.reports.items():
            path = self.directory / name
            put(path,value)
            self.record['artifact_hashes'][name] = m.sha(path)

    def receipt(self):
        return m.build_receipt(self.runner,self.checks,self.plan,self.trial,self.record)

    def test_stat_preserves_failure_and_never_claims_measured_peak(self):
        row = self.receipt()
        self.assertEqual(row['original_status'],'FAIL')
        self.assertEqual(row['original_terminal'],self.closed)
        self.assertEqual(row['total_trial_bytes'],sum(row['files'].values()))
        self.assertFalse(row['inventory_payload_content_reads'])
        self.assertFalse(row['capacity_admission_performed'])
        temp = row['temporary_archive_evidence']
        self.assertIsNone(temp['observed_peak_bytes'])
        self.assertFalse(temp['bound_is_measurement'])
        self.assertEqual(temp['archive_component_bound_without_growth_or_margin_bytes'],
            3*row['raw_sqlite_bytes']+2*row['compressed_sqlite_bytes'])
        self.assertEqual(temp['archive_processing_receipt'],self.reports['bag_integrity.json']['archive_processing'])

    def test_unknown_evidence_stays_in_receipt(self):
        for status in ('INCOMPLETE_EVIDENCE','EVALUATION_PENDING'):
            with self.subTest(status=status):
                self.record['status'] = status
                self.assertEqual(self.receipt()['original_status'],status)

    def test_full_source_clock_exposure_required(self):
        for value in (84_999_999_999,75_000_000_000,True,None):
            with self.subTest(last_clock=value):
                self.reports['recording_closure.json']['observations'][-1]['last_clock_ns'] = value
                self.persist()
                self.assertRaises(ValueError,self.receipt)

    def test_old_duration_and_seed_and_root_are_rejected(self):
        for key,value in (('duration_s',45),('duration_s',20),('seed',True),('seed',0),
                ('directory',str(self.root/'results/reliability_v4_humble28_person_seed004'))):
            with self.subTest(key=key,value=value):
                original = self.trial[key]
                self.trial[key] = value
                self.assertRaises(ValueError,self.receipt)
                self.trial[key] = original

    def test_missing_native_or_recorder_closure_refuses(self):
        original = deepcopy(self.reports['bag_integrity.json'])
        mutations = [lambda v:v.update(status='FAIL'),lambda v:v.update(recorder_exit_code=-2),
            lambda v:v.update(spool_retained=True),lambda v:v['raw_validation'].update(status='FAIL'),
            lambda v:v['native_reader_validation'].update(status='FAIL'),
            lambda v:v['native_reader_validation'].update(full_stream_read=False)]
        for mutate in mutations:
            self.reports['bag_integrity.json'] = deepcopy(original)
            mutate(self.reports['bag_integrity.json']);self.persist()
            self.assertRaises(ValueError,self.receipt)

    def test_inherited_terminal_refusal_precedes_inventory(self):
        self.checks.require_completed_record.side_effect = ValueError('infrastructure stop')
        with patch.object(m,'inventory',side_effect=AssertionError('must not stat')):
            self.assertRaisesRegex(ValueError,'infrastructure',self.receipt)

    def test_bound_report_mutation_refuses(self):
        put(self.directory/'summary.json',{'follow_start_s':0})
        self.assertRaisesRegex(ValueError,'bound report changed',self.receipt)

    def test_payload_bytes_never_read_or_hashed(self):
        original = Path.read_bytes
        def bounded(path,*args,**kwargs):
            self.assertNotIn(path.suffix,('.zstd','.db3','.mp4'))
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_bytes',bounded):
            self.receipt()
        self.assertRaises(ValueError,m.sha,self.directory/'rosbag/rosbag_0.db3.zstd')

    def test_archive_sizes_duplicates_and_escape_refuse(self):
        original = deepcopy(self.reports['bag_integrity.json'])
        mutations = [lambda v:v['compressed_files'].append(deepcopy(v['compressed_files'][0])),
            lambda v:v['raw_validation']['files'].append(deepcopy(v['raw_validation']['files'][0])),
            lambda v:v['compressed_files'][0].update(path='../escape.zstd'),
            lambda v:v['compressed_files'][0].update(path='/absolute.zstd'),
            lambda v:v['compressed_files'][0].update(path='C:\\escape.zstd'),
            lambda v:v['compressed_files'][0].update(bytes=999),
            lambda v:v['compressed_files'][0].update(raw_bytes=101),
            lambda v:v['compressed_files'][0].update(zstd_test='FAIL'),
            lambda v:v['raw_validation']['files'][0].update(bytes=True)]
        for mutate in mutations:
            self.reports['bag_integrity.json'] = deepcopy(original)
            mutate(self.reports['bag_integrity.json']);self.persist()
            self.assertRaises(ValueError,self.receipt)

    def test_concurrent_inventory_change_refuses(self):
        real = m.inventory(self.directory)
        changed = {**real,'late-file':1}
        with patch.object(m,'inventory',side_effect=[real,changed]):
            self.assertRaisesRegex(ValueError,'changed during inventory',self.receipt)

    def test_symlink_inventory_refuses_when_host_supports_it(self):
        link = self.directory/'linked-report.json'
        try:
            link.symlink_to(self.directory/'summary.json')
        except OSError as error:
            self.skipTest('Host cannot create symlinks: '+str(error))
        self.assertRaisesRegex(ValueError,'Linked',self.receipt)


class ExtensionFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='storage38_extension_fixture_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root/'extension/observed_driver01'
        self.directory.mkdir(parents=True)
        self.plan = {'plan_sha256': 'fixture38', 'trials': [{'id': f'cell{i:02d}'} for i in range(16)]}
        statuses = ('PASS', 'FAIL', 'INCOMPLETE_EVIDENCE', 'EVALUATION_PENDING')
        self.rows = {trial['id']: {'status': statuses[i % 4], 'engineering_result': statuses[i % 4],
            'record_sha256': 'record'+str(i)} for i, trial in enumerate(self.plan['trials'])}
        self.source = {'source': 'fixture-only'}
        self.contract = {'path': str(self.root/'contract.json'), 'sha256': 'contract-fixture'}
        self.pending = {'plan': 'original fixture plan'}
        self.prerequisites = {'core': {'all_pass': True}, 'safety': {'all_four_original_pass': True}}
        self.actual_owner = {'actual_post_wait': True}
        self.observer = {'finished_utc': '2026-10-31T01:00:00+00:00'}
        def audit(runner, plan, trial, record, review, checks, *, extension):
            self.assertTrue(extension)
            return {'record_binding': {'id': trial['id']},
                    'known_algorithm_failures': ['retained stress failure'] if record['status'] == 'FAIL' else []}
        self.matrix = SimpleNamespace(SCOPE='fixture-only-not-evidence',
            checked_plan=Mock(return_value=self.plan), verify_same_core=Mock(),
            entry_binding=Mock(return_value=self.source),
            locations=lambda kind: {'run_driver': self.directory},
            load_contract=Mock(return_value=({'plan_pending': self.pending, 'prerequisites': self.prerequisites}, self.plan)),
            audit_record=Mock(side_effect=audit), pending_identity=lambda plan: self.pending,
            stable=SimpleNamespace(metadata_binding=lambda path, json_only: m.binding(path)),
            owner=SimpleNamespace(validate_observer_root=Mock(return_value=self.observer)))
        self.runner = SimpleNamespace(read_slots=lambda plan: self.rows,
                                      simulation_processes=Mock(return_value=[]))
        slots, attempts = [], []
        for number, trial in enumerate(self.plan['trials'], 1):
            record = self.rows[trial['id']]
            evidence = audit(None, None, trial, record, None, None, extension=True)
            item = {'slot': trial['id'], 'status': record['status'],
                    'engineering_result': record['engineering_result'], 'audit': evidence}
            slots.append(item)
            marker = self.directory/f'{number:02d}_{trial["id"]}.started.json'
            put(marker, {'slot': trial['id'], 'number': number, 'entry_binding': self.source,
                'contract': self.contract, 'plan_sha256': self.plan['plan_sha256'],
                'started_utc': '2026-10-31T00:00:00+00:00', 'original_attempt_number': 1})
            attempt = {'slot': trial['id'], 'number': number, 'error': None, 'audit': evidence,
                'started_utc': '2026-10-31T00:00:00+00:00', 'runner_result': {'started_this_invocation': 1},
                'record': {'status': record['status'], 'engineering_result': record['engineering_result'],
                           'record_binding': evidence['record_binding']}, 'started_marker': m.binding(marker)}
            attempts.append(attempt)
            put(self.directory/f'{number:02d}_{trial["id"]}.attempt_terminal.json', attempt)
        self.terminal = {'schema_version': 1, 'scope': self.matrix.SCOPE, 'action': 'run', 'matrix_kind': 'extension',
            'returncode': 0, 'status': 'ORIGINAL_MATRIX_TERMINALS_COMPLETE', 'error': None, 'slot_read_error': None,
            'planned_count': 16, 'attempt_count': 16, 'terminal_count': 16,
            'entry_binding_before': self.source, 'entry_binding_after': self.source,
            'final_errors': [], 'cleanup': {'residual_processes': []}, 'formal_seed_use_authorized': False,
            'readiness_claimed': False, 'automatic_retry': False, 'automatic_next_action': False,
            'contract': self.contract, 'plan': self.pending, 'prerequisites': self.prerequisites,
            'slots': slots, 'attempts': attempts, 'observer': self.observer, 'observer_owner_terminal': self.actual_owner,
            'actual_slot_statuses': {key: {'status': row['status'], 'record_sha256': row['record_sha256']}
                                     for key, row in self.rows.items()},
            'status_counts': {status: 4 for status in statuses}}
        self.persist()

    def persist(self):
        put(self.directory/'execution_terminal.json', self.terminal)

    def completed(self):
        return m.extension_completed(self.matrix, self.runner,
            {'humble33_diagnostic_checks01': object(), 'humble33_development_observer01': object()},
            {}, {}, SimpleNamespace())

    def test_original16_failures_and_unknowns_remain(self):
        result = self.completed()
        self.assertEqual(result['completed_count'], 16)
        self.assertEqual([row['status'] for row in result['original_terminals']],
                         [row['status'] for row in self.rows.values()])
        self.assertEqual(self.matrix.audit_record.call_count, 16)
        self.assertFalse(result['engineering_pass_claimed'])

    def test_original_post_wait_owner_result_is_used_for_future_validation(self):
        self.completed()
        self.matrix.owner.validate_observer_root.assert_called_once_with(self.actual_owner,
            self.directory/'observer_driver', str(m.ROOT))

    def test_missing_original_owner_result_cannot_use_unchanged_d_copy_summary(self):
        self.terminal.pop('observer_owner_terminal'); self.persist()
        def require_original(actual, *args):
            if not isinstance(actual, dict): raise ValueError('Original owner result required')
            return self.observer
        self.matrix.owner.validate_observer_root.side_effect = require_original
        self.assertRaisesRegex(ValueError, 'Original owner', self.completed)

    def test_incomplete_or_unhealthy_or_formal_terminal_refuses(self):
        original = deepcopy(self.terminal)
        for mutation in ({'returncode': True}, {'terminal_count': 15}, {'attempt_count': 15},
                {'error': 'stopped'}, {'final_errors': ['observer']}, {'formal_seed_use_authorized': True},
                {'cleanup': {'residual_processes': [123]}}, {'entry_binding_after': {'foreign': True}}):
            self.terminal = {**deepcopy(original), **mutation}
            self.persist()
            self.assertRaises(ValueError, self.completed)

    def test_slot_drop_reorder_and_record_denominator_refuse(self):
        self.terminal['slots'].reverse()
        self.persist()
        self.assertRaises(ValueError, self.completed)
        self.terminal['slots'].reverse()
        self.persist()
        self.rows.pop(next(iter(self.rows)))
        self.assertRaises(ValueError, self.completed)

    def test_changed_original_attempt_or_marker_refuses(self):
        first = self.plan['trials'][0]['id']
        put(self.directory/f'01_{first}.attempt_terminal.json', {'substitute': True})
        self.assertRaises(ValueError, self.completed)
        put(self.directory/f'01_{first}.attempt_terminal.json', self.terminal['attempts'][0])
        put(self.directory/f'01_{first}.started.json', {'substitute': True})
        self.assertRaises(ValueError, self.completed)

    def test_prerequisite_or_stress_diagnostic_or_observer_change_refuses(self):
        original = deepcopy(self.terminal)
        for key, value in (('prerequisites', {'safety': 'missing'}), ('observer', {'foreign': True})):
            self.terminal = {**deepcopy(original), key: value}
            self.persist()
            self.assertRaises(ValueError, self.completed)
        self.terminal = deepcopy(original)
        self.terminal['slots'][1]['audit']['known_algorithm_failures'] = []
        self.persist()
        self.assertRaises(ValueError, self.completed)


class EntryFixtures(unittest.TestCase):
    def test_describe_does_not_import_runtime_or_measure(self):
        with (patch.object(m.importlib, 'import_module', side_effect=AssertionError('runtime import')),
                redirect_stdout(io.StringIO()) as captured):
            self.assertEqual(m.main(['describe']), 0)
        value = json.loads(captured.getvalue())
        self.assertFalse(value['actual_measurement_executed'])
        self.assertEqual(value['manifest']['development_cells'], {'core': 12, 'extension': 16})
        self.assertFalse(value['manifest']['bag_payload_reads'])

    def test_unreviewed_helper_refuses_before_runtime_import(self):
        with patch.object(m.importlib, 'import_module', side_effect=AssertionError('runtime import')):
            self.assertRaisesRegex(ValueError, 'reviewed storage', m.readonly_context,
                                   SimpleNamespace(reviewed_helpers_sha256=None))

    def test_missing_or_bad_actual_review_refuses_before_any_runtime_import(self):
        manifest={'synthetic':'only'}
        for value in [None,'future','A'*64]:
            args=SimpleNamespace(review=None,review_sha256=value,
                                 reviewed_helpers_sha256=m.canonical(manifest))
            with patch.object(m,'helper_manifest',return_value=manifest), \
                    patch.object(m.importlib,'import_module') as imported:
                self.assertRaisesRegex(ValueError,'actual final41 source review',m.readonly_context,args)
                imported.assert_not_called()

    def test_wrapper_is_metadata_only_and_uses_actual_humble41(self):
        shell = (EXTERNAL/'run_humble41_storage_measure01.sh').read_text(encoding='utf-8')
        self.assertIn('STAGE1_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble41', shell)
        self.assertIn('HUMBLE41_STORAGE_ACTION=measure', shell)
        self.assertIn('ros_gz_shutdown_A01_ws', shell)
        self.assertNotIn('run_reliability_v4.py', shell)
        self.assertNotIn('colcon ', shell)

    def test_same_source_rejects_every_foreign_identity(self):
        same = {key: 'same' for key in ('frozen_root', 'results_root', 'source_hashes', 'model_hashes', 'protocol')}
        m.same_source(same, same)
        for key in same:
            self.assertRaises(ValueError, m.same_source, same, {**same, key: 'foreign'})


if __name__ == '__main__':
    unittest.main(verbosity=2)


