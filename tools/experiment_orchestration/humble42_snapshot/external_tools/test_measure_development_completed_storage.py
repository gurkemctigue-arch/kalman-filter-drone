"""Pure bounded fixtures. Never import ROS, read real bags or run measure."""
from __future__ import annotations

from contextlib import redirect_stdout
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
SPEC = importlib.util.spec_from_file_location('parameterized_storage_fixture_subject',
    EXTERNAL / 'measure_development_completed_storage.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


class ReceiptFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='development_storage_fixture_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = 'reliability_v4_candidate42_probe01'
        self.directory = self.root / ('results/' + self.prefix + '_person_stage1_velocity_seed004')
        self.directory.mkdir(parents=True)
        self.trial = {'id': 'person_stage1_velocity_seed004', 'name': self.directory.name,
            'directory': str(self.directory), 'seed': 4, 'duration_s': 75, 'target_class': 'person'}
        self.plan = {'frozen_root': str(self.root), 'plan_sha256': 'original-plan'}
        self.closed = {'path': 'original-terminal.json', 'sha256': 'a' * 64}
        self.checks = SimpleNamespace(require_completed_record=Mock(return_value=self.closed))
        self.runner = object()
        self.bag = self.directory / 'rosbag/rosbag_0.db3.zstd'
        self.bag.parent.mkdir()
        self.bag.write_bytes(b'fixture payload; stat only, never opened')
        self.metadata = self.directory / 'rosbag/metadata.yaml'
        self.metadata.write_text('fixture: native-metadata-only\n', encoding='utf-8')
        (self.directory / 'demo.mp4').write_bytes(b'fixture video; stat only')
        self.reports = {
            'bag_integrity.json': {'status': 'PASS', 'policy': m.ARCHIVE_POLICY,
                'recorder_exit_code': 0, 'spool_retained': False,
                'raw_validation': {'status': 'PASS', 'message_count': 5,
                    'topic_counts': {'/clock': 5}, 'files': [
                        {'path': 'rosbag_0.db3', 'bytes': 100, 'sha256': 'b' * 64}]},
                'native_reader_validation': {'status': 'PASS', 'full_stream_read': True,
                    'message_count': 5, 'topic_counts': {'/clock': 5}},
                'compressed_files': [{'path': 'rosbag_0.db3.zstd', 'bytes': self.bag.stat().st_size,
                    'raw_bytes': 100, 'raw_sha256': 'b' * 64, 'zstd_test': 'PASS'}],
                'published_metadata_sha256': m.sha(self.metadata),
                'archive_processing': {'wall_s': 1., 'scope': 'original completed archive'}},
            'recording_closure.json': {'status': 'PASS', 'observations': [{'last_clock_ns': 85_000_000_000}]},
            'summary.json': {'follow_start_s': 10., 'termination_reason': 'follow_duration_reached'},
            'process_exit_codes.json': {'gazebo': 0, 'px4': 0, 'ros': 0, 'bag': 0, 'monitor': 0, 'agent': -2},
            'run_config.json': {'duration': 75., 'seed': 4, 'target_class': 'person', 'no_bag': False}}
        self.record = {'status': 'FAIL', 'artifact_hashes': {'rosbag/metadata.yaml': m.sha(self.metadata)}}
        self.persist()

    def persist(self):
        for name, value in self.reports.items():
            path = self.directory / name
            put(path, value)
            self.record['artifact_hashes'][name] = m.sha(path)

    def receipt(self):
        return m.build_receipt(self.runner, self.checks, self.plan, self.trial, self.record,
                               root=self.root, prefix=self.prefix)

    def test_actual75s_sizes_auxiliary_bytes_failure_and_bound_preserved(self):
        row = self.receipt()
        self.assertEqual(row['original_status'], 'FAIL')
        self.assertEqual(row['original_terminal'], self.closed)
        self.assertEqual(row['total_trial_bytes'], sum(row['files'].values()))
        self.assertEqual(row['auxiliary_bytes'], row['total_trial_bytes'] - row['bag_bytes'])
        self.assertEqual(row['raw_sqlite_bytes'], 100)
        self.assertFalse(row['capacity_admission_performed'])
        self.assertFalse(row['inventory_payload_content_reads'])
        temporary = row['temporary_archive_evidence']
        self.assertIsNone(temporary['observed_peak_bytes'])
        self.assertFalse(temporary['bound_is_measurement'])
        self.assertEqual(temporary['archive_component_bound_without_growth_or_margin_bytes'],
                         300 + 2 * self.bag.stat().st_size)

    def test_no_payload_read_or_hash(self):
        original_bytes, original_text = Path.read_bytes, Path.read_text
        def read_bytes(path, *args, **kwargs):
            self.assertNotIn(path.suffix.lower(), {'.zstd', '.db3', '.mp4', '.pt'})
            return original_bytes(path, *args, **kwargs)
        def read_text(path, *args, **kwargs):
            self.assertNotIn(path.suffix.lower(), {'.zstd', '.db3', '.mp4', '.pt'})
            return original_text(path, *args, **kwargs)
        with patch.object(Path, 'read_bytes', read_bytes), patch.object(Path, 'read_text', read_text):
            self.receipt()
        self.assertRaisesRegex(ValueError, 'payload reads', m.sha, self.bag)

    def test_old_duration_foreign_root_prefix_seed_and_bool_refused(self):
        for key, value in (('duration_s', 45), ('duration_s', 20), ('seed', True), ('seed', 0),
                           ('directory', str(self.root / 'results/old41_person_stage1_velocity_seed004'))):
            with self.subTest(key=key, value=value):
                previous = self.trial[key]
                self.trial[key] = value
                self.assertRaises(ValueError, self.receipt)
                self.trial[key] = previous
        self.plan['frozen_root'] = str(self.root / 'another-source')
        self.assertRaisesRegex(ValueError, 'same-source', self.receipt)

    def test_recorded_config_must_match_actual75s_class_seed_and_bag(self):
        original = deepcopy(self.reports['run_config.json'])
        for key, value in (('duration', 45), ('seed', True), ('seed', 5), ('target_class', 'car'), ('no_bag', True)):
            with self.subTest(key=key):
                self.reports['run_config.json'] = {**original, key: value}
                self.persist()
                self.assertRaisesRegex(ValueError, 'recorded configuration', self.receipt)

    def test_full_source_clock_exposure_and_follow_termination_required(self):
        for value in (84_999_999_999, 75_000_000_000, True, None):
            with self.subTest(last_clock=value):
                self.reports['recording_closure.json']['observations'][-1]['last_clock_ns'] = value
                self.persist()
                self.assertRaisesRegex(ValueError, 'full75s', self.receipt)
        self.reports['recording_closure.json']['observations'][-1]['last_clock_ns'] = 85_000_000_000
        self.reports['summary.json']['termination_reason'] = 'telemetry_timeout'
        self.persist()
        self.assertRaisesRegex(ValueError, 'full75s', self.receipt)

    def test_native_count_and_topics_must_reproduce_raw(self):
        original = deepcopy(self.reports['bag_integrity.json'])
        mutations = [lambda v: v['native_reader_validation'].update(message_count=4),
            lambda v: v['native_reader_validation'].update(topic_counts={'/clock': 4}),
            lambda v: v['native_reader_validation'].update(full_stream_read=False),
            lambda v: v['raw_validation'].update(message_count=True),
            lambda v: v['raw_validation'].update(topic_counts={})]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.reports['bag_integrity.json'] = deepcopy(original)
                mutate(self.reports['bag_integrity.json'])
                self.persist()
                self.assertRaisesRegex(ValueError, 'native stream/count', self.receipt)

    def test_archive_closure_recorder_and_spool_are_mandatory(self):
        original = deepcopy(self.reports['bag_integrity.json'])
        for values in ({'status': 'FAIL'}, {'recorder_exit_code': -2}, {'recorder_exit_code': False}, {'spool_retained': True}):
            with self.subTest(values=values):
                self.reports['bag_integrity.json'] = {**deepcopy(original), **values}
                self.persist()
                self.assertRaisesRegex(ValueError, 'Closed full75s', self.receipt)

    def test_raw_compressed_correspondence_duplicate_escape_and_stat_refused(self):
        original = deepcopy(self.reports['bag_integrity.json'])
        mutations = [lambda v: v['compressed_files'].append(deepcopy(v['compressed_files'][0])),
            lambda v: v['raw_validation']['files'].append(deepcopy(v['raw_validation']['files'][0])),
            lambda v: v['compressed_files'][0].update(path='../escape.db3.zstd'),
            lambda v: v['compressed_files'][0].update(path='C:\\escape.db3.zstd'),
            lambda v: v['raw_validation']['files'][0].update(path='/escape.db3'),
            lambda v: v['compressed_files'][0].update(bytes=999),
            lambda v: v['compressed_files'][0].update(raw_bytes=101),
            lambda v: v['compressed_files'][0].update(raw_sha256='c' * 64),
            lambda v: v['compressed_files'][0].update(zstd_test='FAIL'),
            lambda v: v['raw_validation']['files'][0].update(bytes=True)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.reports['bag_integrity.json'] = deepcopy(original)
                mutate(self.reports['bag_integrity.json'])
                self.persist()
                self.assertRaises(ValueError, self.receipt)

    def test_published_metadata_must_remain_original(self):
        self.metadata.write_text('modified: true\n', encoding='utf-8')
        self.assertRaisesRegex(ValueError, 'published metadata', self.receipt)

    def test_bound_report_mutation_and_concurrent_inventory_refused(self):
        put(self.directory / 'summary.json', {'follow_start_s': 0})
        self.assertRaisesRegex(ValueError, 'bound report changed', self.receipt)
        self.persist()
        before = m.inventory(self.directory)
        with patch.object(m, 'inventory', side_effect=[before, {**before, 'late-file': 1}]):
            self.assertRaisesRegex(ValueError, 'changed during inventory', self.receipt)

    def test_inherited_infrastructure_refusal_happens_before_stat(self):
        self.checks.require_completed_record.side_effect = ValueError('infrastructure stop')
        with patch.object(m, 'inventory', side_effect=AssertionError('must not inventory')):
            self.assertRaisesRegex(ValueError, 'infrastructure', self.receipt)

    def test_unknown_status_stays_unknown(self):
        for status in ('INCOMPLETE_EVIDENCE', 'EVALUATION_PENDING'):
            self.record['status'] = status
            self.assertEqual(self.receipt()['original_status'], status)

    def test_existing_budget_consumer_accepts_compatible_receipt_without_payload_read(self):
        workspace = EXTERNAL.parents[1] / '\u57fa\u4e8eyolo\u548c\u5361\u5c14\u66fc\u6ee4\u6ce2'
        spec = importlib.util.spec_from_file_location('candidate_storage_budget_fixture',
            workspace / 'tools/reliability_v4_storage_budget.py')
        budget = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(budget)
        self.record.update(id=self.trial['id'], plan_sha256=self.plan['plan_sha256'],
            execution_status='COMPLETED', infrastructure_stop=False, flight_exit_code=0)
        self.record['record_sha256'] = budget.guard.sealed(self.record, 'record_sha256')
        terminal, sample = self.root / 'matrix/slot.json', self.root / 'stats/receipt.json'
        put(terminal, self.record)
        put(sample, self.receipt())
        paths = {'terminal': terminal, 'size': sample,
            **{key: self.directory / filename for key, filename in
               (('archive', 'bag_integrity.json'), ('summary', 'summary.json'), ('closure', 'recording_closure.json'))}}
        original = Path.read_bytes
        def bounded(path, *args, **kwargs):
            self.assertNotIn(path.suffix.lower(), {'.zstd', '.db3', '.mp4', '.pt'})
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_bytes', bounded):
            row = budget.read_sample(('core', 'person', 'stage1_velocity'), self.plan, self.trial, paths, {})
        self.assertEqual(row['original_status'], 'FAIL')
        self.assertEqual(row['raw_bytes'], 100)
        self.assertEqual(row['compressed_bytes'], self.bag.stat().st_size)


class CanonicalAndOutputFixtures(unittest.TestCase):
    def test_canonical_is_accepted_failure_first_order_refused(self):
        candidate = {'core_classes': ['person', 'car'], 'core_groups': [
            'stage1_velocity', 'stage1_position', 'stage2_crossing',
            'stage3_midpoint', 'stage3_active', 'stage3_multi_active']}
        plan = {'selected_classes': candidate['core_classes'], 'selected_groups': candidate['core_groups'],
                'selected_seeds': [4]}
        m.canonical_order(candidate, plan)
        for key, value in (('selected_classes', ['car', 'person']), ('selected_seeds', [True]),
                           ('selected_groups', list(reversed(candidate['core_groups'])))):
            with self.subTest(key=key):
                self.assertRaises(ValueError, m.canonical_order, candidate, {**plan, key: value})

    def test_output_is_new_and_only_under_actual_candidate_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / 'results/freeze_validation'
            parent.mkdir(parents=True)
            target = parent / 'artifact_storage_candidate42_01'
            self.assertEqual(m.checked_output(root, target), target)
            for invalid in (root / 'artifact_storage_candidate42_01', parent / 'foreign_name'):
                self.assertRaises(ValueError, m.checked_output, root, invalid)
            target.mkdir()
            self.assertRaises(ValueError, m.checked_output, root, target)

    def test_default_describe_is_inert(self):
        with patch.object(m, 'helper_manifest', return_value={'scope': m.KIND}), \
                patch.object(m, 'collect', side_effect=AssertionError('must not measure')), \
                patch.object(m, 'dependencies', side_effect=AssertionError('must not load runtime')), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(m.main([]), 0)
        self.assertFalse(json.loads(output.getvalue())['actual_measurement_executed'])

    def test_duplicate_and_nonfinite_metadata_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.json'
            for raw in ('{"id":1,"id":2}', '{"id":NaN}', '[]'):
                path.write_text(raw, encoding='utf-8')
                self.assertRaises(ValueError, m.read_small, path)


class CompletionFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='extension_storage_fixture_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.driver = self.root / 'observed_driver01'
        self.driver.mkdir()
        self.source = {'candidate': 'actual42'}
        self.expected_contract = {'path': 'actual-extension-contract.json', 'sha256': 'd' * 64}
        self.prerequisites = {'core': {'all_original_core_cells_pass': True},
                              'safety': {'all_four_original_pass': True}}
        self.contract = {'plan_pending': {'plan_sha256': 'actual-plan'}, 'prerequisites': self.prerequisites}
        self.plan = {'plan_sha256': 'actual-plan', 'trials': [{'id': f'original{n:02d}'} for n in range(16)]}
        self.rows = {trial['id']: {'status': 'PASS', 'engineering_result': 'PASS',
                     'record_sha256': 'record-' + trial['id']} for trial in self.plan['trials']}
        self.audit = {'record_binding': {'sha256': 'a' * 64}, 'known_algorithm_failures': []}
        self.core = SimpleNamespace(FALSE_FIELDS=('formal_seed_use_authorized', 'automatic_retry'),
            original41=SimpleNamespace(audit_record=Mock(return_value=self.audit)),
            pending_identity=Mock(return_value=self.contract['plan_pending']))
        self.owner = SimpleNamespace(validate_observer_root=Mock(return_value={'status': 'PASS_REAL_OWNER'}))
        self.runner = SimpleNamespace(read_slots=Mock(return_value=self.rows), verify_sources=Mock(),
                                     simulation_processes=Mock(return_value=[]))
        self.ctx = SimpleNamespace(root=str(self.root), runner=self.runner, review={'source': '42'},
                                   modules={'humble33_diagnostic_checks01': object()})
        self.extension = SimpleNamespace(SCOPE='PARAMETERIZED_EXTENSION16_NORMAL_RUNNER_DEVELOPMENT_ONLY',
            core=self.core, owner=self.owner, locations=Mock(return_value={'run_driver': self.driver}),
            entry_binding=Mock(return_value=self.source),
            stable=SimpleNamespace(metadata_binding=lambda path, **kwargs: m.binding(path)))
        self.terminal = {'schema_version': 1, 'scope': self.extension.SCOPE, 'action': 'run', 'returncode': 0,
            'status': 'ORIGINAL_EXTENSION16_TERMINALS_COMPLETE', 'error': None, 'slot_read_error': None,
            'planned_count': 16, 'attempt_count': 16, 'terminal_count': 16,
            'entry_binding_before': self.source, 'entry_binding_after': self.source,
            'final_errors': [], 'cleanup': {'residual_processes': []}, 'contract': self.expected_contract,
            'plan': self.contract['plan_pending'], 'prerequisites': self.prerequisites,
            'formal_seed_use_authorized': False, 'automatic_retry': False,
            'attempts': [], 'slots': [], 'observer': {'status': 'PASS_REAL_OWNER'},
            'observer_owner_terminal': {'path': 'actual-owner-terminal.json', 'sha256': 'e' * 64}}
        for number, trial in enumerate(self.plan['trials'], 1):
            record = self.rows[trial['id']]
            started = {'slot': trial['id'], 'number': number, 'entry_binding': self.source,
                'contract': self.expected_contract, 'plan_sha256': self.plan['plan_sha256'],
                'started_utc': f'2026-11-01T00:{number:02d}:00+00:00', 'original_attempt_number': 1}
            marker = self.driver / f'{number:02d}_{trial["id"]}.started.json'
            put(marker, started)
            attempt = {'slot': trial['id'], 'number': number, 'error': None, 'audit': self.audit,
                'runner_result': {'started_this_invocation': 1}, 'started_marker': m.binding(marker),
                'started_utc': started['started_utc'], 'record': {'status': record['status'],
                    'engineering_result': record['engineering_result'], 'record_binding': self.audit['record_binding']}}
            put(self.driver / f'{number:02d}_{trial["id"]}.attempt_terminal.json', attempt)
            self.terminal['attempts'].append(attempt)
            self.terminal['slots'].append({'slot': trial['id'], 'status': record['status'],
                'engineering_result': record['engineering_result'], 'audit': self.audit})
        self.persist()

    def persist(self):
        self.terminal['actual_slot_statuses'] = {key: {'status': row['status'], 'record_sha256': row['record_sha256']}
                                               for key, row in self.rows.items()}
        self.terminal['status_counts'] = dict(m.Counter(row['status'] for row in self.rows.values()))
        put(self.driver / 'execution_terminal.json', self.terminal)

    def completed(self):
        return m.extension_completed(self.extension, self.ctx, self.contract, self.plan, self.expected_contract)

    def test_original16_real_owner_and_all_pass_verified(self):
        result = self.completed()
        self.assertEqual(result['completed_count'], 16)
        self.assertTrue(result['all_original_extension_cells_pass'])
        self.assertFalse(result['formal_seed_use_authorized'])
        self.assertEqual(self.core.original41.audit_record.call_count, 16)
        self.owner.validate_observer_root.assert_called_once()

    def test_missing16_terminal_and_changed_source_refuse(self):
        original = deepcopy(self.terminal)
        for mutation in (lambda value: value.update(attempt_count=15),
                          lambda value: value.update(entry_binding_after={'candidate': 'old41'}),
                          lambda value: value['attempts'].pop(),
                          lambda value: value.update(automatic_retry=True)):
            self.terminal = deepcopy(original)
            mutation(self.terminal)
            self.persist()
            self.assertRaises(ValueError, self.completed)

    def test_real_post_wait_owner_failure_is_not_summary_pass(self):
        self.owner.validate_observer_root.side_effect = ValueError('actual owner failed')
        self.assertRaisesRegex(ValueError, 'actual owner', self.completed)

    def test_changed_original_attempt_and_started_marker_refuse(self):
        attempt = self.driver / '01_original00.attempt_terminal.json'
        put(attempt, {'foreign': True})
        self.assertRaisesRegex(ValueError, 'per-attempt terminal', self.completed)
        put(attempt, self.terminal['attempts'][0])
        put(self.driver / '01_original00.started.json', {'foreign': True})
        self.assertRaisesRegex(ValueError, 'started marker', self.completed)

    def test_algorithm_fail_retained_without_eligibility(self):
        trial = self.plan['trials'][-1]
        self.rows[trial['id']].update(status='FAIL', engineering_result='FAIL')
        item, attempt = self.terminal['slots'][-1], self.terminal['attempts'][-1]
        item.update(status='FAIL', engineering_result='FAIL')
        attempt['record'].update(status='FAIL', engineering_result='FAIL')
        put(self.driver / f'16_{trial["id"]}.attempt_terminal.json', attempt)
        self.persist()
        result = self.completed()
        self.assertFalse(result['all_original_extension_cells_pass'])
        self.assertEqual(result['original_terminals'][-1]['status'], 'FAIL')


class CollectionFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='complete28_storage_fixture_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'results/freeze_validation').mkdir(parents=True)
        self.core_path = self.root / 'results/core_matrix/plan.json'
        self.extension_path = self.root / 'results/extension_matrix/plan.json'
        self.plans = []
        self.rows = {}
        for label, count, path in (('core', 12, self.core_path), ('extension', 16, self.extension_path)):
            plan = {'label': label, 'trials': [{'id': label + str(number),
                'directory': str(self.root / ('results/' + label + str(number)))} for number in range(count)]}
            self.plans.append(plan)
            put(path, plan)
            self.rows[label] = {trial['id']: {'status': 'PASS'} for trial in plan['trials']}
        self.source, self.supplement = {'source': 'actual42'}, {'strict512': 'actual-cold-build'}
        self.manifest = {'scope': m.KIND, 'dependencies': 'dynamic-final-reviewed'}
        self.args = SimpleNamespace(output=self.root / 'results/freeze_validation/artifact_storage_candidate42_01',
            reviewed_helpers_sha256=m.canonical(self.manifest), contract=Path('actual-extension-contract.json'),
            contract_sha256='a' * 64)
        self.runner = SimpleNamespace(read_slots=lambda plan: self.rows[plan['label']],
                                     simulation_processes=Mock(return_value=[]))
        self.ctx = SimpleNamespace(root=str(self.root), runner=self.runner,
            candidate={'prefix': 'actual_core42'}, admission={'prefix': 'actual_extension42',
                '_admission_binding': {'path': 'actual-admission.json', 'sha256': 'b' * 64}},
            modules={'humble33_diagnostic_checks01': object()})
        self.contract = {'prerequisites': {'core': {'all_original_core_cells_pass': True},
                                          'safety': {'all_four_original_pass': True}}}
        self.extension = SimpleNamespace(entry_binding=Mock(return_value=self.source),
            core=SimpleNamespace(locations=lambda candidate: {'plan': self.core_path}),
            locations=lambda ctx: {'plan': self.extension_path})
        self.extension_result = {'all_original_extension_cells_pass': True}

    def collect(self):
        def receipt(runner, checks, plan, trial, record, **kwargs):
            return {'trial': trial['directory'], 'original_status': record['status'],
                    'original_terminal': {'original': trial['id']}, 'capacity_admission_performed': False}
        context = (self.extension, self.ctx, self.contract, self.plans[1], self.plans[0], self.source, self.supplement)
        with patch.object(m, 'readonly_context', return_value=context), \
                patch.object(m, 'extension_completed', return_value=self.extension_result), \
                patch.object(m, 'helper_manifest', return_value=self.manifest), \
                patch.object(m, 'build_receipt', side_effect=receipt):
            return m.collect(self.args)

    def test_all28_persist_with_exact_source_and_no_capacity_admission(self):
        output = self.collect()
        summary = m.read_small(output / 'complete28.json')
        self.assertEqual(len(summary['receipts']), 28)
        self.assertEqual(summary['original_status_counts'], {'PASS': 28})
        self.assertEqual(summary['source_binding'], self.source)
        self.assertEqual(summary['strict512_build_evidence'], self.supplement)
        self.assertTrue(summary['eligible_for_budget_input'])
        self.assertFalse(summary['capacity_admission_performed'])
        self.assertFalse(summary['formal_seed_use_authorized'])
        self.assertFalse(summary['temporary_peak_observed'])
        self.assertRaises(ValueError, self.collect)

    def test_extension_fail_is_preserved_and_not_eligible(self):
        self.rows['extension']['extension15']['status'] = 'FAIL'
        self.extension_result['all_original_extension_cells_pass'] = False
        summary = m.read_small(self.collect() / 'complete28.json')
        self.assertEqual(summary['original_status_counts'], {'PASS': 27, 'FAIL': 1})
        self.assertEqual(len(summary['receipts']), 28)
        self.assertFalse(summary['eligible_for_budget_input'])
        self.assertFalse(summary['all28_original_cells_pass'])
        self.assertFalse(summary['capacity_admission_performed'])

    def test_missing_cell_or_unverified_safety_produces_no_output(self):
        self.rows['extension'].pop('extension15')
        self.assertRaisesRegex(ValueError, 'All original12', self.collect)
        self.assertFalse(self.args.output.exists())
        self.rows['extension']['extension15'] = {'status': 'PASS'}
        self.contract['prerequisites']['safety']['all_four_original_pass'] = False
        self.assertRaisesRegex(ValueError, 'core12/safety4', self.collect)
        self.assertFalse(self.args.output.exists())


if __name__ == '__main__':
    unittest.main()
