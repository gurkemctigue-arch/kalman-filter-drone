"""Pure temporary fixtures only: no real bags/logs, ROS, inference or flights."""
from __future__ import annotations
from contextlib import redirect_stdout
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import offline_pipeline_timing as timing


def bag(sequence, kind, message=None, recorder=None, failed_kind=None):
    topic_kind = failed_kind if kind == 'decode_error' else kind
    topic = next(name for name, value in timing.TOPICS.items() if value == topic_kind)
    value = {'stream': 'bag', 'bag_sequence': sequence, 'record_timestamp_ns': recorder if recorder is not None else (sequence + 1) * 1_000_000_000,
             'topic': topic, 'kind': kind, 'message': message or {}}
    if failed_kind is not None:
        value['failed_kind'] = failed_kind
    return value


def detector(sequence, acquisition=1_000_000_000, *, epoch=0, completed=None, wall=.25, recorder=None):
    return bag(sequence, 'detector', {'clock_epoch': epoch, 'acquisition_ns': acquisition,
               'completed_s': acquisition / 1e9 + .1 if completed is None else completed, 'inference_wall_s': wall}, recorder)


def job(line=1, acquisition=1_000_000_000, **updates):
    message = {'schema_version': 1, 'job_key': [0, acquisition], 'status': 'completed',
               'scope': 'production_work_before_timing_log', 'stage_sum_excludes_inclusive_lock_holds': True,
               'production_work_before_timing_log_wall_s': .6,
               'measured_prefix_wall_s': .6,
               'stages': {'yolo_predict': {'wall_s': .4, 'count': 1}, 'bookkeeping': {'wall_s': .2, 'count': 2}},
               'input_lock_holds': {'entry': {'wall_s': 100., 'scope': 'inclusive_not_part_of_stage_sum'}}}
    message.update(updates)
    return {'stream': 'job_log', 'kind': 'job_timing', 'log_index': 0, 'line_number': line, 'message': message}


def analyze(events):
    return timing.analyze_events(events, {'fixture': True})


class DomainAndDenominatorTests(unittest.TestCase):
    def test_rates_keep_recorder_and_source_domains_distinct(self):
        result = analyze([detector(0, recorder=10_000_000_000), detector(1, 1_500_000_000, recorder=12_000_000_000)])
        self.assertEqual(result['detector_completion_recorder_rate']['hz'], .5)
        self.assertEqual(result['detector_processed_source_fps']['hz'], 2.)
        self.assertEqual(result['detector_completion_recorder_rate']['time_domain'], 'UNVERIFIED_RECORDER_TIMESTAMP_DOMAIN')
        self.assertEqual(result['actual_worker_processed_wall_fps']['status'], 'NOT_OBSERVED')
        self.assertIsNone(result['actual_worker_processed_wall_fps']['hz'])
        self.assertAlmostEqual(result['detector_acquisition_to_prepublication_source_s']['statistics_s']['mean'], .1)

    def test_duplicate_acquisitions_are_unknown_without_denominator_loss(self):
        result = analyze([detector(0), detector(1), detector(2, 2_000_000_000)])
        metric = result['detector_acquisition_to_prepublication_source_s']
        self.assertEqual((metric['total'], metric['known'], metric['unknown']), (3, 1, 2))
        self.assertEqual(metric['unknown_reasons'], {'duplicate_source_key': 2})
        self.assertIsNone(result['detector_processed_source_fps']['hz'])

    def test_acquisition_reversal_and_epoch_change_are_not_sorted_away(self):
        for events in ([detector(0, 2_000_000_000), detector(1)], [detector(0), detector(1, 2_000_000_000, epoch=1)]):
            with self.subTest(events=events):
                result = analyze(events)
                self.assertEqual(result['detector_acquisition_to_prepublication_source_s']['unknown'], 2)
                self.assertEqual([row['event_index'] for row in result['detector_acquisition_to_prepublication_source_s']['samples']], [0, 1])
                self.assertEqual(result['anomalies'][0]['reason'], 'detector_source_epoch_changed_or_acquisition_reversed')
                self.assertIsNotNone(result['detector_completion_recorder_rate']['hz'])

    def test_recorded_clock_reversal_invalidates_source_metrics_only(self):
        result = analyze([bag(0, 'clock', {'clock': {'sec': 2, 'nanosec': 0}}), detector(1),
                          bag(2, 'clock', {'clock': {'sec': 1, 'nanosec': 0}}), detector(3, 2_000_000_000)])
        self.assertIsNone(result['detector_processed_source_fps']['hz'])
        self.assertIsNotNone(result['detector_completion_recorder_rate']['hz'])
        self.assertEqual(result['detector_processing_prefix_wall_s']['known'], 2)

    def test_malformed_clock_nested_payload_is_retained_as_anomaly(self):
        for clock in (None, [], True, {'sec': True, 'nanosec': 0}, {'sec': 1, 'nanosec': 1_000_000_000}):
            with self.subTest(clock=clock):
                result = analyze([bag(0, 'clock', {'clock': clock}), detector(1)])
                self.assertEqual(result['detector_acquisition_to_prepublication_source_s']['unknown'], 1)
                self.assertEqual(result['anomalies'][0]['reason'], 'recorded_source_clock_invalid_or_reversed')

    def test_bag_sequence_duplicate_and_reversal_invalidate_rates(self):
        for sequence in (0, -1, True):
            with self.subTest(sequence=sequence):
                result = analyze([detector(0), detector(sequence, 2_000_000_000)])
                self.assertIsNone(result['detector_completion_recorder_rate']['hz'])
                self.assertIsNone(result['detector_processed_source_fps']['hz'])
                self.assertEqual(result['detector_processing_prefix_wall_s']['known'], 2)

    def test_recorder_reversal_is_not_repaired_with_source_times(self):
        result = analyze([detector(0, recorder=2_000_000_000), detector(1, 2_000_000_000, recorder=1_000_000_000)])
        self.assertIsNone(result['detector_completion_recorder_rate']['hz'])
        self.assertEqual(result['detector_processed_source_fps']['hz'], 1.)

    def test_equal_recorder_time_is_unknown_rate_not_infinite(self):
        result = analyze([detector(0, recorder=1), detector(1, 2_000_000_000, recorder=1)])
        self.assertIsNone(result['detector_completion_recorder_rate']['hz'])

    def test_missing_boolean_and_unbounded_keys_are_unknown(self):
        events = [detector(0), detector(1, 2_000_000_000), detector(2, 3_000_000_000)]
        del events[0]['message']['acquisition_ns']
        events[1]['message']['clock_epoch'] = True
        events[2]['message']['acquisition_ns'] = 10**1000
        result = analyze(events)
        self.assertEqual(result['detector_acquisition_to_prepublication_source_s']['unknown_reasons'], {'missing_source_key': 3})

    def test_invalid_durations_are_unknown_and_never_zero(self):
        for wall in (-1, float('nan'), float('inf'), True, 10**1000):
            with self.subTest(wall=str(wall)[:30]):
                result = analyze([detector(0, wall=wall)])
                self.assertEqual(result['detector_processing_prefix_wall_s']['unknown'], 1)
                self.assertIsNone(result['detector_processing_prefix_wall_s']['statistics_s']['mean'])
        self.assertEqual(analyze([detector(0, completed=.9)])['detector_acquisition_to_prepublication_source_s']['unknown'], 1)

    def test_decode_errors_retain_all_opportunity_denominators(self):
        events = [bag(0, 'decode_error', failed_kind='detector'), bag(1, 'decode_error', failed_kind='controller_status'),
                  bag(2, 'controller_command', {'track_id': 1}), bag(3, 'decode_error', failed_kind='controller_command')]
        result = analyze(events)
        self.assertEqual(result['detector_acquisition_to_prepublication_source_s']['unknown'], 1)
        self.assertEqual(result['controller_reported_measurement_age_source_s']['unknown'], 1)
        for name in ('capture_to_controller_causal_source_s', 'capture_to_px4_setpoint_causal_source_s', 'physical_capture_to_px4_effect_wall_s'):
            self.assertEqual((result[name]['status'], result[name]['known'], result[name]['unknown']), ('NOT_OBSERVED', 0, 2))
            self.assertTrue(all(value is None for value in result[name]['statistics_s'].values()))

    def test_repeated_track_and_payload_do_not_establish_causality(self):
        events = [detector(0), bag(1, 'controller_status', {'track_id': 7, 'time_since_measurement_s': .7}),
                  bag(2, 'controller_command', {'track_id': 7, 'header': {'stamp': {'sec': 1}}}),
                  bag(3, 'flight_command', {'track_id': 7, 'header': {'stamp': {'sec': 1}}}),
                  bag(4, 'px4_setpoint', {'timestamp': 1_000_000})]
        result = analyze(events)
        self.assertEqual(result['controller_reported_measurement_age_source_s']['statistics_s']['mean'], .7)
        self.assertEqual(result['physical_capture_to_px4_effect_wall_s']['status'], 'NOT_OBSERVED')

    def test_incorrect_kind_or_stream_cannot_remove_decode_denominators(self):
        events = [bag(0, 'decode_error', failed_kind='detector'), job()]
        events[0]['failed_kind'] = 'controller_command'
        with self.assertRaises(ValueError):
            analyze(events)
        events = [detector(0)]
        events[0]['stream'] = 'job_log'
        with self.assertRaises(ValueError):
            analyze(events)

    def test_empty_and_single_sample_rates_remain_unknown(self):
        for events in ([], [detector(0)]):
            result = analyze(events)
            self.assertIsNone(result['detector_completion_recorder_rate']['hz'])
            self.assertEqual(result['detector_completion_recorder_rate']['unknown_completion_messages'], len(events))
            self.assertFalse(result['flight_acceptance_granted'])


class JobTimingTests(unittest.TestCase):
    def test_final_prefix_is_distinct_from_predict_and_inclusive_holds(self):
        result = analyze([detector(0), job()])
        self.assertEqual(result['completed_job_before_timing_log_wall_s']['statistics_s']['mean'], .6)
        self.assertEqual(result['completed_job_yolo_predict_wall_s']['statistics_s']['mean'], .4)
        self.assertEqual(result['job_log_coverage']['completed_detector_keys_missing_unique_job_log'], [])
        self.assertTrue(any('excludes its timing-log write' in text for text in result['boundaries']))

    def test_partial_failed_and_early_return_jobs_remain_in_denominator(self):
        for updates, reason in (({'scope': 'partial_before_diagnostics_encode_and_publish'}, 'partial_or_unrecognized_timing_scope'),
                                ({'schema_version': True}, 'partial_or_unrecognized_timing_scope'),
                                ({'status': 'early_return'}, 'job_not_completed'), ({'status': 'exception'}, 'job_not_completed'),
                                ({'stage_sum_excludes_inclusive_lock_holds': False}, 'partial_or_unrecognized_timing_scope')):
            with self.subTest(updates=updates):
                result = analyze([job(**updates)])
                self.assertEqual(result['completed_job_before_timing_log_wall_s']['unknown_reasons'], {reason: 1})
                self.assertEqual(result['completed_job_yolo_predict_wall_s']['unknown'], 1)

    def test_inconsistent_final_and_exclusive_stage_partitions_are_unknown(self):
        for updates in ({'measured_prefix_wall_s': .5}, {'measured_prefix_wall_s': None},
                        {'production_work_before_timing_log_wall_s': .3, 'measured_prefix_wall_s': .3},
                        {'stages': {'yolo_predict': {'wall_s': .6, 'count': True}}}):
            with self.subTest(updates=updates):
                result = analyze([job(**updates)])
                self.assertEqual(result['completed_job_before_timing_log_wall_s']['unknown'], 1)
                self.assertEqual(result['completed_job_yolo_predict_wall_s']['unknown'], 1)

    def test_duplicate_job_keys_are_all_unknown(self):
        result = analyze([detector(0), job(), job(2)])
        self.assertEqual(result['completed_job_before_timing_log_wall_s']['unknown_reasons'], {'duplicate_job_key': 2})
        self.assertEqual(result['job_log_coverage']['completed_detector_keys_missing_unique_job_log'], [(0, 1_000_000_000)])

    def test_missing_jobs_disclose_unique_detector_keys(self):
        result = analyze([detector(0), detector(1, 2_000_000_000), job()])
        self.assertEqual(result['job_log_coverage']['completed_detector_keys_missing_unique_job_log'], [(0, 2_000_000_000)])

    def test_job_line_reversal_and_duplicate_remain_anomalies(self):
        for line in (1, True):
            with self.subTest(line=line):
                result = analyze([job(2), job(line, 2_000_000_000)])
                self.assertEqual(result['completed_job_before_timing_log_wall_s']['unknown_reasons'], {'job_log_line_order_invalid': 1})
                self.assertEqual(result['anomalies'][0]['reason'], 'job_log_line_duplicate_or_reversed')

    def test_same_physical_line_with_different_job_keys_is_all_unknown(self):
        result = analyze([job(2), job(2, 2_000_000_000)])
        for name in ('completed_job_before_timing_log_wall_s', 'completed_job_yolo_predict_wall_s'):
            self.assertEqual((result[name]['total'], result[name]['known'], result[name]['unknown']), (2, 0, 2))
            self.assertEqual(result[name]['unknown_reasons'], {'job_log_physical_coordinate_duplicate': 2})
        self.assertEqual(sum(row['reason'] == 'job_log_physical_coordinate_duplicate' for row in result['anomalies']), 2)

    def test_same_line_in_two_distinct_logs_is_not_a_coordinate_conflict(self):
        rows = [job(1), job(1, 2_000_000_000)]
        rows[1]['log_index'] = 1
        self.assertEqual(analyze(rows)['completed_job_before_timing_log_wall_s']['known'], 2)

    def test_invalid_status_and_nested_stages_do_not_crash_or_become_known(self):
        for status in ({'invalid': 1}, [], None, True):
            with self.subTest(status=status):
                result = analyze([job(status=status)])
                self.assertEqual(result['job_outcomes'], {'UNKNOWN_INVALID_OR_MISSING_STATUS': 1})
                self.assertEqual(result['completed_job_before_timing_log_wall_s']['unknown'], 1)
        for stages in (None, [], {'yolo_predict': None}, {'yolo_predict': {'wall_s': .2, 'count': True}},
                       {'yolo_predict': {'wall_s': .2, 'count': 2}}):
            with self.subTest(stages=stages):
                result = analyze([job(stages=stages)])
                self.assertEqual(result['completed_job_yolo_predict_wall_s']['unknown'], 1)

    def test_ansi_log_suffix_is_decoration_but_trailing_junk_is_error(self):
        with tempfile.TemporaryDirectory(prefix='offline_timing_log_fixture_') as directory:
            path = Path(directory) / 'fixture.log'
            payload = json.dumps(job()['message'])
            path.write_text('ordinary line\n\x1b[32m[INFO] INFERENCE_JOB_TIMING ' + payload + '\x1b[0m\n'
                            + 'INFERENCE_JOB_TIMING ' + payload + ' unexpected\n', encoding='utf-8')
            rows = list(timing.job_events(path, 0))
            self.assertEqual([row['line_number'] for row in rows], [2, 3])
            self.assertEqual([row['kind'] for row in rows], ['job_timing', 'decode_error'])
            self.assertEqual(analyze(rows)['completed_job_before_timing_log_wall_s']['unknown'], 1)

    def test_log_duplicate_json_keys_overflow_and_nonobject_are_decode_errors(self):
        with tempfile.TemporaryDirectory(prefix='offline_timing_bad_log_fixture_') as directory:
            path = Path(directory) / 'fixture.log'
            payloads = ['{"status":"completed","status":"exception"}', '{"duration":1e999}', '[]', '{"duration":NaN}']
            path.write_text('\n'.join('INFERENCE_JOB_TIMING ' + value for value in payloads) + '\n', encoding='utf-8')
            rows = list(timing.job_events(path, 0))
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(row['kind'] == 'decode_error' for row in rows))
            self.assertEqual(analyze(rows)['completed_job_before_timing_log_wall_s']['unknown'], 4)


class FileBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='offline_timing_binding_fixture_')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root, self.trial, self.export = self.base / 'source', self.base / 'trial', self.base / 'export'
        self.plan = self.base / 'immutable_plan'
        for directory in (self.root, self.trial, self.export, self.root / 'results', self.plan):
            directory.mkdir(parents=True)
        for index, name in enumerate(timing.SOURCE_FILES):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# fixture source ' + str(index) + '\n', encoding='utf-8')
        (self.trial / 'rosbag').mkdir()
        (self.trial / 'rosbag/metadata.yaml').write_text('fixture: true\n', encoding='utf-8')
        (self.trial / 'run_config.json').write_text('{"fixture":true}\n', encoding='utf-8')
        self.events = self.export / 'events.jsonl'
        self.events.write_text(json.dumps(detector(0)) + '\n', encoding='utf-8')
        self.context_path = self.export / 'context.json'
        self.context = {'schema_version': 1, 'kind': timing.CONTEXT_KIND, 'source_root': str(self.root), 'trial': str(self.trial),
                        'tools': timing.tool_manifest(), 'events': timing.pin(self.events), 'topic_kinds': timing.TOPICS,
                        'source_bindings': {name: timing.pin(self.root / name) for name in timing.SOURCE_FILES},
                        'receipt_bindings': {name: timing.pin(self.trial / name) if (self.trial / name).is_file() else None for name in timing.RECEIPT_FILES},
                        'bag_metadata': timing.pin(self.trial / 'rosbag/metadata.yaml'), 'job_logs': [],
                        'protected_roots': [str(self.plan)], 'source_results_root': str(self.root / 'results'),
                        'coverage': {'fixture': True}, 'recorder_timestamp_clock': 'UNVERIFIED_RECORDER_TIMESTAMP_DOMAIN'}
        self.save_context()

    def save_context(self):
        self.context_path.write_text(json.dumps(self.context, allow_nan=False), encoding='utf-8')
        self.context_pin = timing.pin(self.context_path)

    def run_analysis(self, output=None):
        return timing.analyze_files(self.events, self.context_pin, output or self.base / 'new_report.json')

    def bind_job_fixture(self, rows):
        path = self.base / 'bound_fixture.log'
        path.write_text('\n'.join('INFERENCE_JOB_TIMING ' + json.dumps(row['message']) for row in rows) + '\n', encoding='utf-8')
        self.context['job_logs'] = [timing.pin(path)]
        self.events.write_text('\n'.join(json.dumps(row) for row in [detector(0), *rows]) + '\n', encoding='utf-8')
        self.context['events'] = timing.pin(self.events)
        self.save_context()
        return path

    def test_source_bound_fixture_analyzes_to_exclusive_new_report(self):
        result_pin = self.run_analysis()
        report = timing.read(timing.checked(result_pin))
        self.assertEqual(report['detector_acquisition_to_prepublication_source_s']['known'], 1)
        self.assertEqual(report['inputs']['events'], self.context['events'])
        self.assertFalse(report['formal_seed_use_authorized'])

    def test_context_event_source_and_metadata_tampering_refused(self):
        for label, path in (('context', self.context_path), ('events', self.events),
                            ('source', self.root / timing.SOURCE_FILES[0]), ('metadata', self.trial / 'rosbag/metadata.yaml')):
            with self.subTest(label=label):
                original = path.read_bytes()
                path.write_bytes(original + b' ')
                with self.assertRaises(ValueError):
                    self.run_analysis()
                self.assertFalse((self.base / 'new_report.json').exists())
                path.write_bytes(original)

    def test_identical_source_copy_cannot_replace_named_actual_source(self):
        relative = timing.SOURCE_FILES[0]
        alias = self.base / 'source_copy.py'
        alias.write_bytes((self.root / relative).read_bytes())
        self.context['source_bindings'][relative] = timing.pin(alias)
        self.save_context()
        with self.assertRaises(ValueError):
            self.run_analysis()

    def test_identical_receipt_copy_and_new_omitted_receipt_are_refused(self):
        alias = self.base / 'config_copy.json'
        alias.write_bytes((self.trial / 'run_config.json').read_bytes())
        self.context['receipt_bindings']['run_config.json'] = timing.pin(alias)
        self.save_context()
        with self.assertRaises(ValueError):
            self.run_analysis()
        self.context['receipt_bindings']['run_config.json'] = timing.pin(self.trial / 'run_config.json')
        self.save_context()
        (self.trial / 'bag_integrity.json').write_text('{}', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.run_analysis()

    def test_existing_output_frozen_source_and_original_trial_are_refused(self):
        existing = self.base / 'existing.json'
        existing.write_text('preserve', encoding='utf-8')
        for output in (existing, self.events, self.root / 'new.json', self.root / 'results/new.json', self.trial / 'new.json', self.base / 'new.txt'):
            with self.subTest(output=output):
                with self.assertRaises(ValueError):
                    self.run_analysis(output)
        self.assertEqual(existing.read_text(), 'preserve')

    def test_external_original_plan_root_and_alias_are_protected(self):
        plan = self.plan
        self.context['protected_roots'] = [str(plan)]
        self.save_context()
        with self.assertRaises(ValueError):
            self.run_analysis(plan / 'new_report.json')
        with self.assertRaises(ValueError):
            timing.export_native(self.root, self.trial, plan / 'new_export', [], [plan])
        self.assertFalse((plan / 'new_export').exists())
        self.context['protected_roots'] = [str(plan / '..' / 'immutable_plan')]
        self.save_context()
        with self.assertRaises(ValueError):
            self.run_analysis()

    def test_missing_protected_plan_root_fails_before_any_export(self):
        with self.assertRaises(ValueError):
            timing.export_native(self.root, self.trial, self.base / 'unprotected_export', [])
        self.assertFalse((self.base / 'unprotected_export').exists())
        self.context['protected_roots'] = []
        self.save_context()
        with self.assertRaises(ValueError):
            self.run_analysis()

    def test_changed_source_results_alias_contract_is_refused(self):
        self.context['source_results_root'] = str(self.base / 'different_results')
        self.save_context()
        with self.assertRaises(ValueError):
            self.run_analysis()

    def test_context_path_alias_is_not_an_original_pin(self):
        altered = copy.deepcopy(self.context_pin)
        altered['path'] = str(self.export / '..' / 'export' / 'context.json')
        with self.assertRaises(ValueError):
            timing.analyze_files(self.events, altered, self.base / 'new.json')

    def test_duplicate_job_log_sources_refused(self):
        log = self.base / 'fixture.log'
        log.write_text('', encoding='utf-8')
        self.context['job_logs'] = [timing.pin(log), timing.pin(log)]
        self.save_context()
        with self.assertRaises(ValueError):
            self.run_analysis()

    def test_job_events_without_bound_original_log_are_refused(self):
        self.events.write_text(json.dumps(job()) + '\n', encoding='utf-8')
        self.context['events'] = timing.pin(self.events)
        self.save_context()
        with self.assertRaises(ValueError):
            self.run_analysis()
        self.assertFalse((self.base / 'new_report.json').exists())

    def test_reparsed_bound_original_job_log_enables_only_identical_events(self):
        self.bind_job_fixture([job()])
        report = timing.read(self.run_analysis()['path'])
        self.assertEqual(report['completed_job_before_timing_log_wall_s']['known'], 1)
        self.assertEqual(report['coverage']['bound_job_logs_reparsed'], 1)
        self.assertEqual(report['coverage']['bound_original_job_events_reconstructed'], 1)
        self.assertTrue(report['coverage']['normalized_job_events_equal_bound_original_logs'])

    def test_unbound_log_index_missing_added_reordered_and_changed_job_events_are_refused(self):
        rows = [job(1), job(2, 2_000_000_000)]
        self.bind_job_fixture(rows)
        mutations = []
        out_of_range = copy.deepcopy(rows)
        out_of_range[0]['log_index'] = 1
        mutations.append(('unbound_log_index', out_of_range))
        mutations.extend([('missing', rows[:1]), ('added', [*rows, job(3, 3_000_000_000)]), ('reordered', rows[::-1])])
        changed = copy.deepcopy(rows)
        changed[0]['message']['production_work_before_timing_log_wall_s'] = .7
        changed[0]['message']['measured_prefix_wall_s'] = .7
        changed[0]['message']['stages']['bookkeeping']['wall_s'] = .3
        mutations.append(('internally_consistent_forged_duration', changed))
        coordinate = copy.deepcopy(rows)
        coordinate[0]['line_number'] = 3
        mutations.append(('changed_physical_line', coordinate))
        for label, normalized in mutations:
            with self.subTest(label=label):
                self.events.write_text('\n'.join(json.dumps(row) for row in [detector(0), *normalized]) + '\n', encoding='utf-8')
                self.context['events'] = timing.pin(self.events)
                self.save_context()
                with self.assertRaises(ValueError):
                    self.run_analysis()
                self.assertFalse((self.base / 'new_report.json').exists())

    def test_reconstruction_retains_malformed_original_log_opportunities(self):
        path = self.base / 'malformed_bound_fixture.log'
        path.write_text('ordinary\nINFERENCE_JOB_TIMING not-json\n', encoding='utf-8')
        rows = list(timing.job_events(path, 0))
        self.context['job_logs'] = [timing.pin(path)]
        self.events.write_text(json.dumps(rows[0]) + '\n', encoding='utf-8')
        self.context['events'] = timing.pin(self.events)
        self.save_context()
        report = timing.read(self.run_analysis()['path'])
        self.assertEqual(report['completed_job_before_timing_log_wall_s']['unknown'], 1)
        self.assertEqual(report['coverage']['bound_original_job_events_reconstructed'], 1)

    def test_blank_jsonl_lines_are_not_silently_dropped(self):
        self.events.write_text(json.dumps(detector(0)) + '\n\n', encoding='utf-8')
        self.context['events'] = timing.pin(self.events)
        self.save_context()
        with self.assertRaises(ValueError):
            self.run_analysis()

    def native_modules(self, rows, *, fail_after=None, mutate=None):
        fixture = ModuleType('_offline_timing_fixture')
        source = self.root / timing.SOURCE_FILES[0]
        source.write_text('from contextlib import contextmanager\nimport _offline_timing_fixture\n'
                          '@contextmanager\ndef open_bag_reader(path, module):\n'
                          '    yield _offline_timing_fixture.reader, {"pure_mock": True}\n', encoding='utf-8')
        class Reader:
            index = 0
            def get_all_topics_and_types(self):
                return [SimpleNamespace(name=name, type='fixture/Message') for name in {row[0] for row in rows}]
            def has_next(self):
                if mutate is not None and self.index == len(rows):
                    mutate()
                if fail_after is not None and self.index >= fail_after:
                    raise RuntimeError('injected native fixture failure')
                return self.index < len(rows)
            def read_next(self):
                row = rows[self.index]
                self.index += 1
                return row
        fixture.reader = Reader()
        modules = {name: ModuleType(name) for name in ('rosbag2_py', 'rclpy', 'rclpy.serialization', 'rosidl_runtime_py',
                    'rosidl_runtime_py.utilities', 'rosidl_runtime_py.convert')}
        modules['rclpy.serialization'].deserialize_message = lambda data, cls: data
        modules['rosidl_runtime_py.utilities'].get_message = lambda name: dict
        modules['rosidl_runtime_py.convert'].message_to_ordereddict = lambda value: value
        modules['_offline_timing_fixture'] = fixture
        return modules

    def test_fully_mocked_export_preserves_native_order_decode_errors_and_nan(self):
        payload = detector(0)['message']
        rows = [('/clock', {'clock': {'sec': 1, 'nanosec': 0}}, 10),
                ('/unselected', {}, 11), ('/tracking/detection_diagnostics', SimpleNamespace(data=json.dumps(payload)), 12),
                ('/tracking/detection_diagnostics', SimpleNamespace(data='broken'), 13),
                ('/fmu/in/trajectory_setpoint', {'position': [1., float('nan'), 3.]}, 14)]
        log = self.base / 'native_fixture.log'
        log.write_text('INFERENCE_JOB_TIMING ' + json.dumps(job()['message']) + '\n', encoding='utf-8')
        original_path = list(sys.path)
        with patch.dict(sys.modules, self.native_modules(rows)):
            try:
                context_pin = timing.export_native(self.root, self.trial, self.base / 'native_export', [log], [self.plan])
            finally:
                sys.path[:] = original_path
                sys.modules.pop('offline_timing_original_bag_reader', None)
        context = timing.read(context_pin['path'])
        events = [timing.loads(line) for line in Path(context['events']['path']).read_text().splitlines()]
        self.assertEqual([row['bag_sequence'] for row in events if row['stream'] == 'bag'], [0, 2, 3, 4])
        self.assertEqual([row['kind'] for row in events], ['clock', 'detector', 'decode_error', 'px4_setpoint', 'job_timing'])
        self.assertEqual(events[3]['message']['position'][1], {'nonfinite_native_float': 'NaN'})
        self.assertEqual(context['native_topic_counts']['/unselected'], 1)
        self.assertTrue(context['coverage']['native_bag_read_to_end'])
        timing.analyze_files(context['events']['path'], context_pin, self.base / 'native_report.json')

    def test_mocked_export_failure_preserves_partial_files_and_never_context(self):
        rows = [('/clock', {'clock': {'sec': 1, 'nanosec': 0}}, 10)]
        original_path = list(sys.path)
        with patch.dict(sys.modules, self.native_modules(rows, fail_after=1)):
            try:
                with self.assertRaises(RuntimeError):
                    timing.export_native(self.root, self.trial, self.base / 'failed_export', [], [self.plan])
            finally:
                sys.path[:] = original_path
                sys.modules.pop('offline_timing_original_bag_reader', None)
        output = self.base / 'failed_export'
        self.assertTrue((output / 'started.json').is_file())
        self.assertTrue((output / 'events.jsonl').is_file())
        self.assertTrue((output / 'failed.json').is_file())
        self.assertFalse((output / 'context.json').exists())

    def test_mocked_export_rechecks_original_source_after_read(self):
        rows = [('/clock', {'clock': {'sec': 1, 'nanosec': 0}}, 10)]
        source = self.root / timing.SOURCE_FILES[1]
        original_path = list(sys.path)
        with patch.dict(sys.modules, self.native_modules(rows, mutate=lambda: source.write_text('changed fixture', encoding='utf-8'))):
            try:
                with self.assertRaises(ValueError):
                    timing.export_native(self.root, self.trial, self.base / 'changed_export', [], [self.plan])
            finally:
                sys.path[:] = original_path
                sys.modules.pop('offline_timing_original_bag_reader', None)
        self.assertTrue((self.base / 'changed_export/failed.json').exists())
        self.assertFalse((self.base / 'changed_export/context.json').exists())


class InertEntryTests(unittest.TestCase):
    def test_import_and_describe_work_when_all_native_imports_are_forbidden(self):
        script = Path(timing.__file__).resolve()
        code = '''import builtins, importlib.util
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in ('rosbag2_py', 'rclpy', 'rosidl_runtime_py', 'ultralytics', 'torch'):
        raise AssertionError('Unexpected native import: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
spec = importlib.util.spec_from_file_location('fixture_inert_import', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.main(['describe'])
'''.replace('SCRIPT', repr(str(script)))
        completed = subprocess.run([sys.executable, '-I', '-B', '-c', code], capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertFalse(result['production_action_executed'])
        self.assertFalse(result['manifest']['physical_capture_to_px4_effect_observable'])

    def test_default_action_cannot_dispatch_export(self):
        with patch.object(timing, 'export_native', side_effect=AssertionError('must not export')), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(timing.main([]), 0)
        self.assertFalse(json.loads(output.getvalue())['production_action_executed'])


if __name__ == '__main__':
    unittest.main()
