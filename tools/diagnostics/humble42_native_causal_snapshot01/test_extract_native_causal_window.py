"""Small fabricated records only: no ROS, WSL, bags, images or inference."""
from __future__ import annotations
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import extract_native_causal_window as tool


class Message:
    def __init__(self, **values):
        self.__dict__.update(values)

    def get_fields_and_field_types(self):
        return {name: 'synthetic' for name in self.__dict__}


def header(seconds):
    value = tool.ns(seconds)
    return Message(stamp=Message(sec=value // 1000000000, nanosec=value % 1000000000), frame_id='camera_optical')


class FakeReader:
    def __init__(self, rows):
        self.rows = rows
        self.index = 0
        self.filter_called = False

    def get_all_topics_and_types(self):
        return [SimpleNamespace(name=name, type='synthetic/' + str(index))
                for index, name in enumerate(dict.fromkeys(row[0] for row in self.rows))]

    def has_next(self):
        return self.index < len(self.rows)

    def read_next(self):
        row = self.rows[self.index]
        self.index += 1
        return row[0], row[1], row[2]

    def set_filter(self, value):
        raise AssertionError('The complete native stream must not be filtered')


class FakeRuntime:
    def __init__(self, fixture):
        self.fixture = fixture
        self.receipt = {'synthetic_runtime_only': True}
        self.deserialize_calls = []
        self.opens = 0
        self.closed = False

    def get_message(self, name):
        return name

    def deserialize(self, raw, cls):
        self.deserialize_calls.append(raw)
        return self.fixture.messages[raw]

    @contextmanager
    def open(self, context):
        self.opens += 1
        self.reader = FakeReader(self.fixture.rows)
        try:
            yield self.reader, {'reader': 'SYNTHETIC_NO_NATIVE_BAG_OPENED'}
        finally:
            self.closed = True
            if self.fixture.on_close:
                self.fixture.on_close()


class Fixture:
    def __init__(self, base):
        self.base = Path(base).resolve()
        self.root = self.base / 'frozen_any_version'
        self.root.mkdir()
        self.results = self.root / 'results'
        self.results.mkdir()
        self.matrix = self.results / 'original_matrix'
        self.matrix.mkdir()
        self.trial = self.results / 'original_car_crossing'
        self.trial.mkdir()
        self.bag = self.trial / 'rosbag'
        self.bag.mkdir()
        (self.trial / 'configuration').mkdir()
        (self.matrix / 'slots').mkdir()
        self.driver = self.matrix / 'observed_driver01'
        self.driver.mkdir()
        self.cache = self.base / 'external_cache'
        self.cache.mkdir()
        self.output = self.base / 'new_output'
        self.messages, self.rows, self.on_close = {}, [], None
        self.make_records()
        self.payload = self.bag / 'recording.db3.zstd'
        self.payload.write_bytes(b'FAKE ARCHIVE; NEVER DECOMPRESSED')
        (self.bag / 'metadata.yaml').write_text('# synthetic metadata only\n')
        self.sources = {}
        for relative in tool.SOURCE_FILES:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# tiny synthetic pinned source, never imported\n')
            self.sources[relative] = tool.pin(path)['sha256']
        self.review_path = self.base / 'review.json'
        self.review = {'status': 'FINAL_SOURCE_AND_TOOLS_INDEPENDENTLY_REVIEWED', 'frozen_root': str(self.root),
                       'source_commit': 'synthetic', 'files': deepcopy(self.sources), 'classified_source_hashes': deepcopy(self.sources)}
        self.save(self.review_path, self.review)
        self.manifest_path = self.results / 'source_manifest.json'
        self.save(self.manifest_path, {'source_root': str(self.root), 'source_commit': 'synthetic',
            'files': deepcopy(self.sources), 'final_review': tool.pin(self.review_path)})
        self.candidate_path = self.base / 'candidate.json'
        self.save(self.candidate_path, {'synthetic': True})
        self.contract_path = self.base / 'contract.json'
        self.contract = {'candidate_manifest': tool.pin(self.candidate_path),
                         'entry_binding': {'source_review': tool.pin(self.review_path)}}
        self.save(self.contract_path, self.contract)
        self.identity = 'car_stage2_crossing_seed004'
        self.plan_path = self.matrix / 'plan.json'
        self.plan = {'mode': 'PROBE', 'frozen_root': str(self.root), 'source_hashes': deepcopy(self.sources),
                     'output': str(self.matrix), 'trials': [{'id': self.identity, 'name': self.trial.name, 'directory': str(self.trial)}]}
        self.save_sealed(self.plan_path, self.plan, 'plan_sha256')
        self.summary_path = self.trial / 'summary.json'
        self.save(self.summary_path, {'follow_start_s': 18.1})
        self.save(self.trial / 'run_config.json', {'target_class': 'car', 'stage': 2})
        (self.trial / 'configuration/runtime_parameters.yaml').write_text('max_prediction_duration_s: 0.75\n')
        self.integrity = {'status': 'PASS', 'recorder_exit_code': 0, 'destination': str(self.bag),
            'published_metadata_sha256': tool.pin(self.bag / 'metadata.yaml')['sha256'],
            'raw_validation': {'status': 'PASS', 'topic_counts': dict(tool.Counter(row[0] for row in self.rows))},
            'native_reader_validation': {'status': 'PASS', 'full_stream_read': True,
                'topic_counts': dict(tool.Counter(row[0] for row in self.rows)), 'message_count': len(self.rows)},
            'compressed_files': [{'path': self.payload.name, 'sha256': tool.digest(self.payload),
                'bytes': self.payload.stat().st_size, 'raw_bytes': 64, 'zstd_test': 'PASS'}]}
        self.save(self.trial / 'bag_integrity.json', self.integrity)
        self.save(self.trial / 'recording_closure.json', {'status': 'PASS', 'finished_utc': '2020-01-02T00:00:00+00:00'})
        self.slot_path = self.matrix / 'slots' / (self.identity + '.json')
        self.started = self.matrix / 'slots' / (self.identity + '.started.json')
        self.save(self.started, {'id': self.identity, 'plan_sha256': self.plan['plan_sha256']})
        self.driver_started = self.driver / '09.started.json'
        self.save(self.driver_started, {'slot': self.identity})
        self.slot = {'id': self.identity, 'name': self.trial.name, 'status': 'FAIL', 'engineering_result': 'FAIL',
            'finished_utc': '2020-01-02T00:00:00+00:00', 'plan_sha256': self.plan['plan_sha256'],
            'cleanup': {'process_exit_codes': {'gazebo': -9}}, 'artifact_hashes': {}}
        self.attempt_path = self.driver / '09.attempt_terminal.json'
        self.terminal_path = self.driver / 'execution_terminal.json'
        self.refresh()
        self.args = tool.parser().parse_args([])
        self.args.execute_after_core_idle = True
        self.args.source_root, self.args.trial = self.root, self.trial
        self.args.slot_id, self.args.output, self.args.cache_parent = self.identity, self.output, self.cache
        self.args.frame_source_s = ['31.4']
        self.args.reviewed_tools_sha256 = tool.canonical(tool.tool_manifest())
        self.pin_args()

    @staticmethod
    def save(path, value):
        path.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')

    def save_sealed(self, path, value, field):
        value[field] = tool.canonical({key: item for key, item in value.items() if key != field})
        self.save(path, value)

    def refresh(self):
        for relative in ('bag_integrity.json', 'recording_closure.json', 'summary.json', 'run_config.json',
                         'configuration/runtime_parameters.yaml', 'rosbag/metadata.yaml'):
            self.slot['artifact_hashes'][relative] = tool.pin(self.trial / relative)['sha256']
        self.save_sealed(self.slot_path, self.slot, 'record_sha256')
        self.attempt = {'slot': self.identity, 'number': 9, 'finished_utc': '2020-01-02T00:01:00+00:00',
            'error': 'Owned process cleanup failed: gazebo', 'started_marker': tool.pin(self.driver_started),
            'record': {'record_binding': {**tool.pin(self.slot_path), 'record_sha256': self.slot['record_sha256'],
                 'plan_sha256': self.plan['plan_sha256'], 'started_marker': tool.pin(self.started)}}}
        self.save(self.attempt_path, self.attempt)
        self.terminal = {'action': 'run-core', 'finished_utc': '2020-01-02T00:02:00+00:00', 'returncode': 2,
            'status': 'STOPPED_ORIGINAL_ATTEMPTS_RETAINED', 'status_counts': {'PASS': 8, 'FAIL': 1, 'PENDING': 3},
            'plan': {'plan': tool.pin(self.plan_path)}, 'contract': tool.pin(self.contract_path),
            'entry_binding_before': {'candidate_manifest': tool.pin(self.candidate_path)}, 'attempts': [deepcopy(self.attempt)],
            'actual_slot_statuses': {self.identity: {'status': 'FAIL', 'record_sha256': self.slot['record_sha256']}},
            'observer_owner_terminal': {'status': 'STOPPED_FAULT', 'healthy_cleanup': False, 'bad_owner_evidence': 'RETAIN THIS'}}
        self.save(self.terminal_path, self.terminal)

    def pin_args(self):
        self.args.input = [[name, *tool.pin(path).values()] for name, path in (
            ('source_review', self.review_path), ('source_manifest', self.manifest_path), ('plan', self.plan_path),
            ('slot', self.slot_path), ('attempt', self.attempt_path), ('core_terminal', self.terminal_path), ('contract', self.contract_path))]

    def refresh_record_counts(self):
        counts = dict(tool.Counter(row[0] for row in self.rows))
        self.integrity['raw_validation']['topic_counts'] = counts
        self.integrity['native_reader_validation'].update(topic_counts=counts, message_count=len(self.rows))
        self.save(self.trial / 'bag_integrity.json', self.integrity)
        self.refresh()
        self.pin_args()

    def add(self, topic, message):
        raw = ('synthetic CDR ' + str(len(self.rows))).encode()
        self.messages[raw] = message
        self.rows.append((topic, raw, 1700000000000000000 + len(self.rows)))

    def clock(self, seconds):
        self.add('/clock', Message(clock=header(seconds).stamp))

    def make_records(self):
        self.clock('29.0')
        self.add('/tracking/state', Message(header=header('29.0'), state=2, track_id=3, target_uuid='task', covariance=[1.0] * 36))
        self.add('/tracking/tracks', Message(data=json.dumps({'acquisition_s': 29.0, 'output_s': 29.0,
            'target_uuid': 'task', 'target_track_id': 3, 'projected': False,
            'tracks': [{'track_id': 3, 'last_measurement_s': 29.0, 'matched': True}]})))
        self.clock('31.4')
        self.add('/tracking/state', Message(header=header('31.4'), state=4, track_id=3, target_uuid='task', prediction_age_s=.1))
        self.add('/tracking/observation_frames', Message(header=header('31.4'), observations=[
            Message(candidate_id=index, position_camera_m=Message(x=float(index), y=0., z=8.)) for index in (1, 2, 3)]))
        self.add('/tracking/tracks', Message(data=json.dumps({'acquisition_s': 31.4, 'output_s': 31.4,
            'target_uuid': 'task', 'target_track_id': 3, 'projected': False,
            'ambiguous_track_ids': [3, 4], 'spawn_deferred_reasons': [{'detection_index': 2, 'reason': 'overlap_birth_requires_second_supported_acquisition'}],
            'tracks': [{'track_id': 3, 'last_measurement_s': 31.3, 'matched': False}, {'track_id': 4, 'last_measurement_s': 31.4, 'matched': True}]})))
        self.add('/tracking/navigation_diagnostics', Message(data=json.dumps({'acquisition_s': 31.4,
            'output_s': 31.4, 'output_publication_s': 31.400000000000002,
            'target_uuid': 'task', 'track_id': 3, 'measurement_processing_s': 31.54,
            'state_reason': 'surface_ambiguous', 'measurement_age_s': .14})))
        self.add(tool.RGB, Message(header=header('31.4'), height=2, width=3, step=12,
            encoding='rgb8', is_bigendian=0, data=bytearray(range(24))))
        self.add(tool.DEPTH, Message(header=header('31.4'), height=2, width=3, step=16,
            encoding='32FC1', is_bigendian=1, data=bytearray(range(32))))
        self.add(tool.INFO, Message(header=header('31.4'), height=2, width=3, k=[1., 0., 1., 0., 1., 1., 0., 0., 1.]))
        self.add('/ground_truth/poses', Message(transforms=[]))
        self.add('/unselected/topic', Message(secret='only counted, never decoded'))
        self.clock('34.0')
        self.add('/tracking/observation_frames', Message(header=header('32.2'), observations=[Message(candidate_id=99)]))
        self.add('/tracking/state', Message(header=header('34.0'), state=3, track_id=3, target_uuid='task'))
        self.clock('50.0')
        self.add('/tracking/navigation_diagnostics', Message(data=json.dumps({'acquisition_s': 31.4,
            'output_s': 50.0, 'output_publication_s': 50.0, 'target_uuid': 'task', 'track_id': 3,
            'measurement_processing_s': 31.54, 'state_reason': 'surface_lost'})))

    def run(self):
        self.runtime = FakeRuntime(self)
        return tool.execute(self.args, runtime_factory=lambda context, args: self.runtime)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='native_causal_synthetic_')
        self.addCleanup(self.temp.cleanup)
        self.fixture = Fixture(self.temp.name)

    def events(self):
        return [json.loads(line) for line in (self.fixture.output / 'events.jsonl').read_text().splitlines()]

    def test_closed_fail_stopped_owner_and_three_pending_are_preserved(self):
        result = self.fixture.run()
        self.assertEqual(result['original_slot_status'], 'FAIL')
        self.assertEqual(result['original_core_counts'], {'PASS': 8, 'FAIL': 1, 'PENDING': 3})
        self.assertFalse(result['original_owner']['healthy_cleanup'])
        self.assertIn('gazebo', result['original_attempt_error'])
        self.assertTrue(result['original_pins_and_compressed_payloads_unchanged'])

    def test_exact_stride_endian_full_pixels_and_cdr_are_preserved(self):
        self.fixture.run()
        requests = json.loads((self.fixture.output / 'image_requests.json').read_text())
        self.assertEqual(requests[0]['status'], 'EXACT_COMPONENTS_EXPORTED')
        depth = requests[0]['components'][tool.DEPTH][0]
        self.assertEqual(depth['is_bigendian'], 1)
        self.assertEqual((self.fixture.output / depth['pixels']['file']).read_bytes(), bytes(range(32)))
        self.assertEqual(depth['step'], 16)

    def test_all_candidates_and_tracks_and_original_measurement_age_remain(self):
        self.fixture.run()
        frames = [row for row in self.events() if row['topic'] == '/tracking/observation_frames']
        self.assertEqual([row['candidate_id'] for row in frames[0]['payload']['observations']], [1, 2, 3])
        tracks = [row for row in self.events() if row['topic'] == '/tracking/tracks'][-1]
        self.assertEqual([row['track_id'] for row in tracks['payload']['tracks']], [3, 4])
        self.assertEqual(tracks['payload']['tracks'][0]['last_measurement_s'], 31.3)

    def test_late_acquisition_is_included_without_equating_clock_domains(self):
        self.fixture.run()
        late = [row for row in self.events() if row['topic'] == '/tracking/observation_frames'][-1]
        self.assertEqual(late['recorded_clock_proxy_ns'], 34000000000)
        self.assertEqual(late['timing']['source_stamp_ns'], 32200000000)
        self.assertGreater(late['bag_record_ns'], 1000000000000000000)

    def test_cached_late_navigation_is_not_new_window_acquisition(self):
        self.fixture.run()
        nav = [row for row in self.events() if row['topic'] == '/tracking/navigation_diagnostics']
        self.assertEqual(len(nav), 1)
        self.assertEqual(nav[0]['payload']['output_publication_s'], 31.400000000000002)

    def test_cached_old_headers_do_not_expand_surface_or_navigation_window(self):
        for value in ('40', '41', '42'):
            self.fixture.clock(value)
            for topic in ('/tracking/state', '/tracking/navigation_state'):
                self.fixture.add(topic, Message(header=header('31.4'), state=3, track_id=3, target_uuid='task'))
        # Add an in-window navigation state before these later cached records.
        raw = b'synthetic in-window navigation state'
        self.fixture.messages[raw] = Message(header=header('31.4'), state=1, track_id=3, target_uuid='task')
        index = next(i for i, row in enumerate(self.fixture.rows) if row[0] == tool.RGB)
        self.fixture.rows.insert(index, ('/tracking/navigation_state', raw, 1700000000000000100))
        self.fixture.refresh_record_counts()
        self.fixture.run()
        for topic in ('/tracking/state', '/tracking/navigation_state'):
            rows = [row for row in self.events() if row['topic'] == topic]
            late = [row for row in rows if row['recorded_clock_proxy_ns'] > 33000000000]
            self.assertEqual(len(late), 1)
            self.assertEqual(late[0]['selection'], 'first_record_after_window')

    def test_source_header_identity_keeps_distinct_candidates_and_new_epoch(self):
        for epoch, candidate in ((0, 80), (0, 81), (1, 80)):
            self.fixture.add('/tracking/observations', Message(header=header('32.2'), acquisition_epoch=epoch,
                candidate_id=candidate, confidence=.8))
        self.fixture.refresh_record_counts()
        self.fixture.run()
        rows = [row for row in self.events() if row['topic'] == '/tracking/observations']
        self.assertEqual(len(rows), 3)
        self.assertEqual([row['timing']['acquisition_epoch'] for row in rows], [0, 0, 1])

    def test_nonobject_diagnostic_json_is_partial_and_not_false_success(self):
        self.fixture.add('/tracking/tracks', Message(data='[1,2,3]'))
        self.fixture.refresh_record_counts()
        with self.assertRaises(RuntimeError):
            self.fixture.run()
        result = json.loads((self.fixture.output / 'manifest.json').read_text())
        self.assertEqual(result['status'], 'ABORTED_PARTIAL_ORIGINALS_RETAINED')
        self.assertIn('payload must be an object', result['error'])
        self.assertTrue(self.fixture.runtime.closed)

    def test_original_static_selection_and_profile_context_and_late_tf_are_retained(self):
        self.fixture.clock('60')
        self.fixture.add('/tf_static', Message(transforms=[Message(header=header('0'), child_frame_id='camera')]))
        self.fixture.add('/tracking/selection', Message(header=header('18'), action=0, target_uuid='task'))
        self.fixture.add('/scenario/stage2_profile', Message(data='{"occlusion_start_s":30.1}'))
        self.fixture.add('/tracking/flight_phase', Message(data='FOLLOW:source_sim_s=18.1'))
        self.fixture.add('/tf', Message(transforms=[Message(header=header('31.6'), child_frame_id='gimbal')]))
        self.fixture.refresh_record_counts()
        self.fixture.run()
        rows = self.events()
        for topic in tool.GLOBAL_CONTEXT_TOPICS:
            self.assertIn('original_global_context', next(row['selection'] for row in rows if row['topic'] == topic))
        tf = next(row for row in rows if row['topic'] == '/tf')
        self.assertIn('transform_source_stamps_ns', tf['selection'])
        self.assertEqual(tf['timing']['transform_source_stamps_ns'], [31600000000])

    def test_generated_schema_compares_types_and_rejects_same_names_wrong_wire_type(self):
        path = self.fixture.base / 'synthetic_schema.msg'
        path.write_text('bool valid\nfloat32[] samples\nfloat32[4] bbox\nTargetObservation[] observations\nuint8 FLAG=1\n')
        expected = {'valid': 'boolean', 'samples': 'sequence<float>', 'bbox': 'float[4]',
                    'observations': 'sequence<uav_tracking_interfaces/msg/TargetObservation>'}
        cls = type('SyntheticSchema', (), {'get_fields_and_field_types': classmethod(lambda cls: expected)})
        self.assertEqual(tool.checked_class_schema(cls, tool.pin(path)), expected)
        expected['samples'] = 'sequence<double>'
        with self.assertRaisesRegex(ValueError, 'field types differ'):
            tool.checked_class_schema(cls, tool.pin(path))

    def test_generated_class_module_must_be_inside_actual_overlay(self):
        path = self.fixture.base / 'generated_fake.py'
        path.write_text('# synthetic generated module\n')
        cls = type('FakeGenerated', (), {'__module__': 'synthetic_generated_module'})
        with patch.dict(sys.modules, {'synthetic_generated_module': SimpleNamespace(__file__=str(path))}):
            self.assertEqual(tool.class_origin(cls, self.fixture.base), tool.pin(path))
            with self.assertRaisesRegex(ValueError, 'foreign Python path'):
                tool.class_origin(cls, self.fixture.root)

    def test_owned_native_cache_cleanup_and_tempdir_restoration_on_success_and_error(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                runtime = tool.NativeRuntime.__new__(tool.NativeRuntime)
                runtime.module, runtime.receipt = None, {'owned_native_caches': []}
                reader = SimpleNamespace(close_calls=0)
                def close():
                    reader.close_calls += 1
                reader.close = close
                @contextmanager
                def original(path, module):
                    with tempfile.TemporaryDirectory(prefix='borrowed_synthetic_') as nested:
                        self.assertTrue(Path(nested).is_relative_to(self.fixture.cache))
                        (Path(nested) / 'synthetic.sqlite').write_bytes(b'not a bag')
                        yield reader, {'synthetic': True}
                runtime.open_original = original
                before = tempfile.tempdir
                if fail:
                    with self.assertRaisesRegex(ValueError, 'synthetic export failure'):
                        with runtime.open({'cache_parent': self.fixture.cache, 'trial': self.fixture.trial}):
                            raise ValueError('synthetic export failure')
                else:
                    with runtime.open({'cache_parent': self.fixture.cache, 'trial': self.fixture.trial}):
                        pass
                receipt = runtime.receipt['owned_native_caches'][0]
                self.assertTrue(receipt['removed'])
                self.assertTrue(receipt['tempfile_tempdir_restored'])
                self.assertIs(tempfile.tempdir, before)
                self.assertEqual(reader.close_calls, 1)
                self.assertEqual(receipt['reader_close_result'], 'RETURNED')
                self.assertFalse(list(self.fixture.cache.iterdir()))

    def test_reader_close_error_still_restores_tempdir_and_removes_cache(self):
        runtime = tool.NativeRuntime.__new__(tool.NativeRuntime)
        runtime.module, runtime.receipt = None, {'owned_native_caches': []}
        def bad_close():
            raise OSError('synthetic reader close failure')
        @contextmanager
        def original(path, module):
            yield SimpleNamespace(close=bad_close), {}
        runtime.open_original = original
        before = tempfile.tempdir
        with self.assertRaisesRegex(OSError, 'reader close failure'):
            with runtime.open({'cache_parent': self.fixture.cache, 'trial': self.fixture.trial}):
                pass
        receipt = runtime.receipt['owned_native_caches'][0]
        self.assertTrue(receipt['removed'])
        self.assertTrue(receipt['tempfile_tempdir_restored'])
        self.assertIs(tempfile.tempdir, before)
        self.assertEqual(receipt['reader_close_result'], 'ATTEMPTED')

    def test_native_counts_every_topic_once_without_filter_or_default_gt_decode(self):
        result = self.fixture.run()
        self.assertEqual(self.fixture.runtime.opens, 1)
        self.assertTrue(self.fixture.runtime.closed)
        self.assertEqual(result['export']['native_counts'], self.fixture.integrity['raw_validation']['topic_counts'])
        gt_raw = next(row[1] for row in self.fixture.rows if row[0] in tool.GT)
        self.assertNotIn(gt_raw, self.fixture.runtime.deserialize_calls)

    def test_missing_exact_frames_are_kept_without_nearest_replacement(self):
        self.fixture.args.frame_source_s = ['31.5']
        self.fixture.run()
        request = json.loads((self.fixture.output / 'image_requests.json').read_text())[0]
        self.assertEqual(request['status'], 'MISSING_OR_DUPLICATE_NO_SUBSTITUTION')
        self.assertTrue(all(not rows for rows in request['components'].values()))

    def test_duplicate_exact_rgb_is_retained_as_unknown(self):
        original = next(row for row in self.fixture.rows if row[0] == tool.RGB)
        self.fixture.rows.insert(9, original)
        self.fixture.integrity['raw_validation']['topic_counts'][tool.RGB] += 1
        self.fixture.integrity['native_reader_validation']['topic_counts'][tool.RGB] += 1
        self.fixture.integrity['native_reader_validation']['message_count'] += 1
        self.fixture.save(self.fixture.trial / 'bag_integrity.json', self.fixture.integrity)
        self.fixture.refresh(); self.fixture.pin_args()
        self.fixture.run()
        request = json.loads((self.fixture.output / 'image_requests.json').read_text())[0]
        self.assertEqual(len(request['components'][tool.RGB]), 2)
        self.assertEqual(request['status'], 'MISSING_OR_DUPLICATE_NO_SUBSTITUTION')

    def test_count_mismatch_preserves_partial_and_closes_reader(self):
        self.fixture.rows.append(self.fixture.rows[-1])
        with self.assertRaises(RuntimeError):
            self.fixture.run()
        self.assertTrue(self.fixture.runtime.closed)
        manifest = json.loads((self.fixture.output / 'manifest.json').read_text())
        self.assertEqual(manifest['status'], 'ABORTED_PARTIAL_ORIGINALS_RETAINED')
        self.assertEqual(manifest['native_traversals'], 1)

    def test_payload_drift_after_native_read_is_refused(self):
        self.fixture.on_close = lambda: self.fixture.payload.write_bytes(b'changed')
        with self.assertRaises(RuntimeError):
            self.fixture.run()
        manifest = json.loads((self.fixture.output / 'manifest.json').read_text())
        self.assertFalse(manifest['original_pins_and_compressed_payloads_unchanged'])

    def test_private_state_is_not_fabricated_as_exact_replay(self):
        result = self.fixture.run()['export']
        self.assertEqual(result['private_association_predictor_state'], 'NOT_OBSERVED')
        self.assertEqual(result['exact_association_replay'], 'NOT_PERFORMED')

    def test_output_and_cache_inside_original_tree_are_refused(self):
        self.fixture.args.output = self.fixture.trial / 'new'
        with self.assertRaises(ValueError):
            tool.validate(self.fixture.args)
        self.fixture.args.output = self.fixture.output
        self.fixture.args.cache_parent = self.fixture.results
        with self.assertRaises(ValueError):
            tool.validate(self.fixture.args)

    def test_existing_output_and_metadata_tampering_are_refused(self):
        self.fixture.output.mkdir()
        with self.assertRaises(ValueError):
            tool.validate(self.fixture.args)
        self.assertEqual(list(self.fixture.output.iterdir()), [])

    def test_changed_original_closed_metadata_is_refused_before_runtime(self):
        self.fixture.slot_path.write_text('{"status":"PASS"}')
        with self.assertRaises(ValueError):
            self.fixture.run()
        self.assertFalse(self.fixture.output.exists())

    def test_partial_output_budget_retains_error_manifest_and_originals(self):
        original = tool.Writer.write
        def limited(writer, name, data):
            if name.startswith('images/'):
                writer.limit = writer.bytes
            return original(writer, name, data)
        with patch.object(tool.Writer, 'write', limited), self.assertRaises(RuntimeError):
            self.fixture.run()
        result = json.loads((self.fixture.output / 'manifest.json').read_text())
        self.assertEqual(result['status'], 'ABORTED_PARTIAL_ORIGINALS_RETAINED')
        self.assertTrue(result['original_pins_and_compressed_payloads_unchanged'])
        self.assertTrue((self.fixture.output / 'events.jsonl').exists())

    def test_full_image_missing_bytes_is_not_declared_exported(self):
        raw = next(row[1] for row in self.fixture.rows if row[0] == tool.DEPTH)
        self.fixture.messages[raw].data = bytearray(1)
        with self.assertRaises(RuntimeError):
            self.fixture.run()
        self.assertEqual(json.loads((self.fixture.output / 'manifest.json').read_text())['status'], 'ABORTED_PARTIAL_ORIGINALS_RETAINED')

    def test_offline_gt_requires_explicit_option_and_has_no_runtime_feedback(self):
        self.fixture.args.include_offline_gt = True
        report = self.fixture.run()
        self.assertEqual(report['export']['gt_scope'], 'OFFLINE_ONLY_NEVER_RUNTIME')
        self.assertTrue(any(row['topic'] in tool.GT for row in self.events()))

    def test_nonfinite_ros_fields_are_explicitly_encoded(self):
        self.assertEqual(tool.plain(Message(x=float('nan'), y=float('inf'))),
                         {'x': {'nonfinite_float': 'nan'}, 'y': {'nonfinite_float': 'inf'}})

    def test_hard_resource_ceilings_cannot_silently_expand(self):
        self.fixture.args.max_cache_mib = 99999999
        with self.assertRaises(ValueError):
            tool.validate(self.fixture.args)

    def test_identical_plan_copy_cannot_replace_named_original(self):
        copy = self.fixture.base / 'copy.json'
        copy.write_bytes(self.fixture.plan_path.read_bytes())
        self.fixture.args.input = [[label, str(copy), tool.pin(copy)['sha256']] if label == 'plan' else [label, path, sha]
                                  for label, path, sha in self.fixture.args.input]
        with self.assertRaises(ValueError):
            tool.validate(self.fixture.args)

    def test_follow_offsets_use_original_follow_not_assumed_absolute_scene_time(self):
        self.fixture.save(self.fixture.summary_path, {'follow_start_s': 17.652})
        self.fixture.refresh(); self.fixture.pin_args()
        self.fixture.args.frame_source_s = []
        self.fixture.args.frame_follow_offset_s = ['13.3']
        context = tool.validate(self.fixture.args)
        self.assertEqual(context['start_ns'], 29052000000)
        self.assertEqual(context['requests'], [30952000000])

    def test_source_change_and_oversized_small_input_are_refused(self):
        (self.fixture.root / tool.SOURCE_FILES[0]).write_text('# changed\n')
        with self.assertRaises(ValueError):
            tool.validate(self.fixture.args)
        with patch.object(tool, 'MAX_SMALL', 1):
            with self.assertRaises(ValueError):
                tool.validate(self.fixture.args)

    def test_no_actual_execute_without_idle_schedule_and_reviewed_tool_identity(self):
        self.fixture.args.execute_after_core_idle = False
        with self.assertRaises(ValueError):
            tool.validate(self.fixture.args)
        self.fixture.args.execute_after_core_idle = True
        self.fixture.args.reviewed_tools_sha256 = '0' * 64
        with self.assertRaises(ValueError):
            tool.validate(self.fixture.args)

    def test_boundary_control_records_are_retained(self):
        self.fixture.run()
        states = [row for row in self.events() if row['topic'] == '/tracking/state']
        self.assertEqual(states[0]['selection'], 'last_record_before_window')
        self.assertEqual(states[-1]['selection'], 'first_record_after_window')
        self.assertEqual([row['payload']['state'] for row in states], [2, 4, 3])

    def test_default_and_describe_open_no_experiment_or_ros(self):
        with (patch.object(tool, 'validate', side_effect=AssertionError('no actual input')),
              patch.object(tool, 'NativeRuntime', side_effect=AssertionError('no ROS')),
              redirect_stdout(io.StringIO()) as output):
            self.assertEqual(tool.main([]), 0)
        self.assertFalse(json.loads(output.getvalue())['experimental_inputs_opened'])

    def test_borrowed_reader_selects_only_pinned_function_not_top_level_actions(self):
        path = self.fixture.base / 'reader_source.py'
        path.write_text("raise AssertionError('top level must not execute')\n@contextmanager\ndef open_bag_reader(path, rosbag2_py):\n    yield path, {'synthetic': True}\n")
        function = tool.borrowed_reader(tool.pin(path))
        with function('tiny', None) as result:
            self.assertEqual(result, ('tiny', {'synthetic': True}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
