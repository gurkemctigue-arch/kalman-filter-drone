"""Pure synthetic tests: no WSL, ROS import, bag, real result or model access."""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import struct
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('control_tick_lineage_under_test', Path(__file__).with_name('control_tick_lineage.py'))
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def native_stamp(ns):
    sec, nano = divmod(ns, 1_000_000_000)
    return {'sec': sec, 'nanosec': nano}


def native_header(ns):
    return {'stamp': native_stamp(ns), 'frame_id': 'map'}


def source_seconds(ns):
    sec, nano = divmod(ns, 1_000_000_000)
    return float(sec) + float(nano) * 1e-9


def pair(acquired=10_000_000_000, header=10_250_000_000, track=7, uuid='task-A'):
    age = source_seconds(header)-source_seconds(acquired)
    native = {'header': native_header(header), 'state': 2, 'track_id': track, 'target_uuid': uuid,
              'position_m': dict(x=1., y=2., z=3.), 'velocity_mps': dict(x=.1, y=.2, z=.3),
              'covariance': [m.f32(.1)]*36, 'prediction_age_s': m.f32(age), 'target_visible': False}
    diag = {'diagnostic_schema_version': 2, 'valid': True, 'output_s': source_seconds(header),
            'output_publication_s': source_seconds(header+1), 'output_track_id': track,
            'output_target_uuid': uuid, 'output_state': 2,
            'output_measurement_source_s': source_seconds(acquired),
            'measurement_age_s': age, 'output_position_world_m': [1., 2., 3.],
            'output_velocity_world_mps': [.1, .2, .3], 'output_covariance_world_6x6': [[.1]*6 for _ in range(6)]}
    return native, diag


def fixture():
    acquired, header, tick = 10_000_000_000, 10_250_000_000, 10_500_000_000
    native, diag = pair(acquired, header)
    age = m.f32(native['prediction_age_s'] + (tick-header)*1e-9)
    messages = [
        ('clock', {'clock': native_stamp(9_000_000_000)}),
        ('detector', {'clock_epoch': 0, 'acquisition_ns': acquired, 'acquisition_s': source_seconds(acquired)}),
        ('navigation_state', native), ('navigation_diagnostics', diag),
        ('controller_command', {'header': native_header(tick), 'track_id': 7, 'valid': True, 'mode': 1}),
        ('controller_status', {'header': native_header(tick), 'track_id': 7, 'lifecycle': 3,
                               'prediction_active': True, 'target_visible': False, 'time_since_measurement_s': age}),
        ('clock', {'clock': native_stamp(tick+1)}),
    ]
    reverse = {v: k for k, v in m.TOPICS.items()}
    return [{'stream': 'bag', 'bag_sequence': i, 'record_timestamp_ns': 1_000_000_000+i,
             'kind': kind, 'topic': reverse[kind], 'message': message} for i, (kind, message) in enumerate(messages)]


def normalize(events):
    for i, event in enumerate(events):
        event['bag_sequence'] = i
        event['record_timestamp_ns'] = 1_000_000_000+i
    return events


def analyze(events, **coverage):
    return m.analyze_events(events, dict(native_bag_read_to_end=True, **coverage))


def of_kind(events, kind):
    return next(event for event in events if event['kind'] == kind)


class RecordedLineageTests(unittest.TestCase):
    def test_valid_exact_chain_and_honest_endpoint(self):
        value = analyze(fixture())
        self.assertEqual((value['original_command_denominator'], value['known_commands']), (1, 1))
        self.assertEqual(value['commands'][0]['value_s'], .5)
        self.assertEqual(value['commands'][0]['lineage']['target_uuid'], 'task-A')
        self.assertIn('tick\u5f00\u59cb', value['endpoint_label'])
        self.assertIn('controller_publish_completion', value['not_observed'])
        self.assertIn('complete_callback_causality', value['not_observed'])

    def assert_unknown(self, events, reason=None):
        value = analyze(events)
        self.assertEqual(value['known_commands'], 0)
        self.assertTrue(all(r['value_s'] is None for r in value['commands']))
        if reason:
            self.assertTrue(any(reason in text for row in value['commands'] for text in row['reasons']), value)
        return value

    def test_each_duplicate_stream_keeps_unknown(self):
        for kind in ('controller_command', 'controller_status', 'navigation_state', 'navigation_diagnostics', 'detector'):
            with self.subTest(kind=kind):
                events = fixture()
                original = of_kind(events, kind)
                index = events.index(original)
                events.insert(index+1, copy.deepcopy(original))
                result = self.assert_unknown(normalize(events))
                self.assertEqual(result['original_command_denominator'], 2 if kind == 'controller_command' else 1)

    def test_second_uuid_is_not_silently_selected(self):
        events = fixture()
        native, diag = pair(uuid='task-B')
        more = [copy.deepcopy(of_kind(events, 'navigation_state')), copy.deepcopy(of_kind(events, 'navigation_diagnostics'))]
        more[0]['message'], more[1]['message'] = native, diag
        events[4:4] = more
        result = self.assert_unknown(normalize(events), 'no_unique_native_formula_candidate')
        self.assertEqual(result['commands'][0]['formula_native_candidate_count'], 2)

    def test_same_image_lineage_two_states_stays_unknown(self):
        events = fixture()
        native, diag = pair(header=10_125_000_000)
        more = [copy.deepcopy(of_kind(events, 'navigation_state')), copy.deepcopy(of_kind(events, 'navigation_diagnostics'))]
        more[0]['message'], more[1]['message'] = native, diag
        events[4:4] = more
        result = self.assert_unknown(normalize(events))
        self.assertEqual(result['commands'][0]['formula_native_candidate_count'], 2)

    def test_one_bit_status_age_is_not_tolerance_matched(self):
        events = fixture()
        status = of_kind(events, 'controller_status')['message']
        status['time_since_measurement_s'] = m.adjacent32(status['time_since_measurement_s'], 1)
        self.assert_unknown(events, 'no_unique_native_formula_candidate')

    def test_one_bit_native_covariance_cannot_be_ignored(self):
        events = fixture()
        native = of_kind(events, 'navigation_state')['message']
        native['covariance'][0] = m.adjacent32(native['covariance'][0], 1)
        self.assert_unknown(events, 'native_covariance_binary32_mismatch')

    def test_bad_native_age_outside_window_cannot_create_false_unique(self):
        events = fixture()
        native, diag = pair(acquired=1_000_000_000, header=10_000_000_000)
        native['prediction_age_s'] = 0.
        more = [copy.deepcopy(of_kind(events, 'navigation_state')), copy.deepcopy(of_kind(events, 'navigation_diagnostics'))]
        more[0]['message'], more[1]['message'] = native, diag
        events[4:4] = more
        self.assert_unknown(normalize(events), 'unindexable_native_lineage_for_track')

    def test_epoch_change_and_clock_regression_poison_trial(self):
        for clock in (True, False):
            events = fixture()
            if clock:
                events[-1]['message']['clock'] = native_stamp(8_000_000_000)
                expected = 'source_clock_reset_or_regression'
            else:
                detector = copy.deepcopy(of_kind(events, 'detector'))
                detector['message']['clock_epoch'] = 1
                events.insert(2, detector)
                expected = 'detector_epoch_change_or_acquisition_regression'
            self.assert_unknown(normalize(events), expected)

    def test_source_acquisition_regression_is_not_reordered(self):
        events = fixture()
        detector = copy.deepcopy(of_kind(events, 'detector'))
        detector['message'].update(acquisition_ns=9_000_000_000, acquisition_s=9.)
        events.insert(2, detector)
        self.assert_unknown(normalize(events), 'detector_epoch_change_or_acquisition_regression')

    def test_future_native_before_command_is_unknown(self):
        events = fixture()
        native, diag = pair(header=10_510_000_000)
        more = [copy.deepcopy(of_kind(events, 'navigation_state')), copy.deepcopy(of_kind(events, 'navigation_diagnostics'))]
        more[0]['message'], more[1]['message'] = native, diag
        events[4:4] = more
        self.assert_unknown(normalize(events), 'future_native_header_recorded_before_command')

    def test_ordinary_future_native_after_command_does_not_poison(self):
        events = fixture()
        native, diag = pair(acquired=11_000_000_000, header=11_250_000_000)
        more = [copy.deepcopy(of_kind(events, 'navigation_state')), copy.deepcopy(of_kind(events, 'navigation_diagnostics'))]
        more[0]['message'], more[1]['message'] = native, diag
        events.extend(more)
        self.assertEqual(analyze(normalize(events))['known_commands'], 1)

    def test_each_required_missing_stream_retains_command_denominator(self):
        for kind in m.REQUIRED_KINDS:
            if kind == 'controller_command':
                continue
            events = [e for e in fixture() if e['kind'] != kind]
            result = self.assert_unknown(normalize(events), 'missing_stream:' + kind)
            self.assertEqual(result['original_command_denominator'], 1)

    def test_decode_errors_retain_each_command_and_required_unknown(self):
        events = fixture()
        failed = copy.deepcopy(of_kind(events, 'controller_command'))
        failed.update(kind='decode_error', failed_kind='controller_command', message={}, error='synthetic')
        events.append(failed)
        value = self.assert_unknown(normalize(events))
        self.assertEqual(value['original_command_denominator'], 2)
        self.assertEqual(value['decode_errors_by_stream']['controller_command'], 1)
        self.assertIn('command_decode_error', value['commands'][-1]['reasons'])

    def test_every_required_decode_error_is_an_explicit_global_unknown(self):
        for kind in m.REQUIRED_KINDS:
            with self.subTest(kind=kind):
                events = fixture()
                failed = copy.deepcopy(of_kind(events, kind))
                failed.update(kind='decode_error', failed_kind=kind, message={}, error='synthetic')
                events.append(failed)
                self.assert_unknown(normalize(events), 'required_stream_decode_error:' + kind)

    def test_missing_separate_native_diagnostic_cannot_be_silently_discarded(self):
        events = fixture()
        _, diag = pair(header=10_125_000_000)
        more = copy.deepcopy(of_kind(events, 'navigation_diagnostics'))
        more['message'] = diag
        events.insert(4, more)
        self.assert_unknown(normalize(events), 'unindexable_native_lineage_for_track')

    def test_bag_sequence_duplicate_is_unknown_without_repair(self):
        events = fixture()
        events[-1]['bag_sequence'] = events[-2]['bag_sequence']
        self.assert_unknown(events, 'bag_sequence_duplicate_or_regressed')

    def test_native_nonfinite_and_negative_zero_unknown(self):
        for field, val in (('prediction_age_s', float('nan')), ('prediction_age_s', -0.0),
                           ('covariance', [{'nonfinite_native_float': 'NaN'}]*36)):
            events = fixture()
            of_kind(events, 'navigation_state')['message'][field] = val
            self.assert_unknown(events)

    def test_nonfinite_status_or_covariance_is_unknown(self):
        for value in (float('nan'), float('inf'), {'nonfinite_native_float': 'NaN'}, -0.0):
            events = fixture()
            of_kind(events, 'controller_status')['message']['time_since_measurement_s'] = value
            self.assert_unknown(events)

    def test_wrong_diagnostic_age_source_and_accepted_source(self):
        events = fixture()
        diag = of_kind(events, 'navigation_diagnostics')['message']
        diag['acquisition_s'] = 999.  # rejected/latest processed measurement is deliberately irrelevant
        self.assertEqual(analyze(events)['known_commands'], 1)
        diag['measurement_age_s'] += 1e-9
        self.assert_unknown(events, 'diagnostic_age_not_exact_accepted_source_difference')

    def test_status_visibility_and_prediction_flags_are_binding(self):
        for field in ('target_visible', 'prediction_active'):
            events = fixture()
            status = of_kind(events, 'controller_status')['message']
            status[field] = not status[field]
            self.assert_unknown(events, 'native_status_lifecycle_or_visibility_mismatch')

    def test_inactive_commands_are_in_denominator(self):
        events = fixture()
        original = copy.deepcopy(of_kind(events, 'controller_command'))
        original['message'].update(valid=False, mode=4, header=native_header(12_000_000_000))
        events.append(original)
        value = analyze(normalize(events))
        self.assertEqual((value['original_command_denominator'], value['known_commands'], value['unknown_commands']), (2, 1, 1))
        self.assertEqual(value['known_command_coverage'], .5)

    def test_incomplete_native_read_cannot_claim_known(self):
        value = m.analyze_events(fixture(), {'native_bag_read_to_end': False})
        self.assertEqual(value['known_commands'], 0)


class ArithmeticOracleTests(unittest.TestCase):
    def test_exact_nanosecond_roundtrip_without_tolerance(self):
        for ns in (1, 1_000_000_001, 10_000_000_123, 8_000_000_000_000_001):
            self.assertEqual(m.seconds_ns(source_seconds(ns)), ns)
        for value in (10.00000000025, float('nan'), -1., True, 2**1000):
            with self.assertRaises((ValueError, OverflowError)):
                m.seconds_ns(value)

    def test_rounding_midpoints_and_adjacent_ulp(self):
        for base in (0., 2**-20, .125, .25, .5, .75, 1., 8., 1000.):
            base = m.f32(base)
            following = m.adjacent32(base, 1)
            midpoint = (base+following)/2
            for value in (math.nextafter(midpoint, -math.inf), midpoint, math.nextafter(midpoint, math.inf)):
                expected = struct.unpack('!f', struct.pack('!f', value))[0]
                self.assertEqual(m.f32(value), expected)

    def test_index_contains_all_bruteforce_actual_formula_candidates(self):
        # Reference enumerates native/accepted/tick integer stamps and executes
        # actual original controller arithmetic directly. It does not derive
        # candidates from acquisition_window or reconstruct its error formula.
        rng = random.Random(20261103)
        observations = []
        for origin in (1, 10_000_000_000, 123_456_789_000_000, 8_000_000_000_000_000):
            for _ in range(200):
                acquired = origin+rng.randrange(0, 10_000_000)
                header = acquired+rng.choice((0, 1, 2, 3, 7, 125_000_000, 250_000_000,
                                              499_999_999, 500_000_000, 500_000_001, 750_000_000))
                tick = header+rng.choice((0, 1, 2, 3, 7, 50_000_000, 250_000_000))
                diagnostic_age = source_seconds(header)-source_seconds(acquired)
                wire_age = struct.unpack('!f', struct.pack('!f', diagnostic_age))[0]
                actual_double = float(wire_age)+max(0, tick-header)*1e-9
                status_age = struct.unpack('!f', struct.pack('!f', actual_double))[0]
                observations.append((acquired, header, tick, wire_age, status_age))
        # Query each distinct command against all same-origin candidates. This
        # checks non-own candidates too, including accidental float32 collisions.
        tested, matched = 0, 0
        for query in observations[::7]:
            _, _, tick, _, status_age = query
            original_bits = struct.unpack('!I', struct.pack('!f', status_age))[0]
            probes = {status_age, struct.unpack('!f', struct.pack('!I', original_bits+1))[0]}
            if original_bits > 0:
                probes.add(struct.unpack('!f', struct.pack('!I', original_bits-1))[0])
            for observed_age in probes:
                lower, upper = m.acquisition_window(tick, observed_age)
                expected_bits = struct.pack('!f', observed_age)
                for acquired, header, _, wire_age, _ in observations:
                    if header > tick:
                        continue
                    direct = struct.unpack('!f', struct.pack('!f', float(wire_age)+max(0, tick-header)*1e-9))[0]
                    tested += 1
                    if struct.pack('!f', direct) == expected_bits:
                        matched += 1
                        self.assertLessEqual(lower, acquired, (query, acquired, header, wire_age, lower, upper))
                        self.assertGreaterEqual(upper, acquired, (query, acquired, header, wire_age, lower, upper))
        self.assertGreater(tested, 10_000)
        self.assertGreater(matched, 100)


class FileBoundaryTests(unittest.TestCase):
    def test_strict_json_rejects_duplicates_and_nonfinite(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}'):
            with self.assertRaises(ValueError):
                m.loads(text)

    def test_source_bindings_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root, trial, protected, outside = (base/name for name in ('source', 'trial', 'protected', 'outputs'))
            for folder in (root, trial, protected, outside):
                folder.mkdir()
            (trial/'rosbag').mkdir()
            (trial/'rosbag/metadata.yaml').write_text('synthetic metadata', encoding='utf-8')
            for name in set(m.SOURCE_FILES) | set(m.SUPPORTED_SOURCES):
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('# synthetic source only\n', encoding='utf-8')
            supported = {name: m.pin(root/name)['sha256'] for name in m.SUPPORTED_SOURCES}
            events = fixture()
            event_path = outside/'events.jsonl'
            event_path.write_text(''.join(json.dumps(e)+'\n' for e in events), encoding='utf-8')
            counts = dict(Counter(e['topic'] for e in events))
            exporter = {'schema_version': 1, 'kind': 'OFFLINE_OBSERVED_PIPELINE_TIMING_NOT_CAUSAL_E2E',
                        'files': m.EXPORTER_FILES, 'online_files_changed': False, 'default_trial': None,
                        'physical_capture_to_px4_effect_observable': False, 'recorder_timestamp_clock_is_verified': False,
                        'nearest_or_payload_causal_matching': False, 'formal_seed_use_authorized': False}
            context = {'schema_version': 1, 'kind': m.CONTEXT_KIND, 'tools': exporter,
                       'topic_kinds': m.TOPICS, 'recorder_timestamp_clock': 'UNVERIFIED_RECORDER_TIMESTAMP_DOMAIN',
                       'events': m.pin(event_path), 'source_root': str(root.resolve()), 'trial': str(trial.resolve()),
                       'source_bindings': {name: m.pin(root/name) for name in m.SOURCE_FILES},
                       'receipt_bindings': dict.fromkeys(m.RECEIPTS), 'bag_metadata': m.pin(trial/'rosbag/metadata.yaml'),
                       'protected_roots': [str(protected.resolve())], 'source_results_root': str((root/'results').resolve()),
                       'job_logs': [], 'selected_topic_counts': counts, 'native_topic_counts': counts,
                       'coverage': {'native_bag_read_to_end': True}}
            context_path = outside/'context.json'
            context_path.write_text(json.dumps(context), encoding='utf-8')
            with patch.dict(m.SUPPORTED_SOURCES, supported, clear=True):
                report = outside/'report.json'
                binding = m.pin(context_path)
                receipt = m.analyze_files(event_path, binding, report)
                self.assertEqual(receipt, m.pin(report))
                self.assertEqual(json.loads(report.read_text(encoding='utf-8'))['known_commands'], 1)
                for output in (report, root/'bad.json', trial/'bad.json', protected/'bad.json'):
                    with self.assertRaises(ValueError):
                        m.analyze_files(event_path, binding, output)
                (root/m.SOURCE_FILES[0]).write_text('changed', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'source_bindings'):
                    m.analyze_files(event_path, binding, outside/'changed.json')
            with self.assertRaises(ValueError):
                m.checked({'path': str(context_path), 'sha256': '0'*64})


if __name__ == '__main__':
    unittest.main()
