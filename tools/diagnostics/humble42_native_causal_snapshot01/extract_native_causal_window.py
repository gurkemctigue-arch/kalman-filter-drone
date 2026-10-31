"""Explicit closed-recording raw export; default describe opens no experiment.

One native bag traversal; compressed files are additionally hashed before and
after. No simulator, inference, filter replay, verdict repair or runtime GT use.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any

HERE = Path(__file__).resolve().parent
OWN = ('extract_native_causal_window.py', 'test_extract_native_causal_window.py')
LABELS = {'source_review', 'source_manifest', 'plan', 'slot', 'attempt', 'core_terminal', 'contract'}
MAX_SMALL = 2 * 1024**2
INTERFACES = ('TargetObservationArray', 'TargetObservation', 'NavigationOverlap', 'TargetState',
              'TargetSelection', 'TrackingStatus', 'TrackingCommand')
READER_SOURCE = 'scripts/evaluate_stage1_flight.py'
SOURCE_FILES = (READER_SOURCE, 'uav_tracking/core/target_manager.py',
                'ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/state_estimator_node.py',
                'ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/stage2_telemetry.py',
                'ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/navigation_estimator.py') + tuple(
                'ros2_ws/src/uav_tracking_interfaces/msg/' + name + '.msg' for name in INTERFACES)
RGB = '/camera/color/image_raw'
DEPTH = '/camera/aligned_depth_to_color/image_raw'
INFO = '/camera/color/camera_info'
GT = {'/ground_truth/poses', '/ground_truth/vehicle_poses'}
TOPICS = {'/clock', '/tracking/observation_frames', '/tracking/observations',
          '/tracking/detection_diagnostics', '/tracking/tracks', '/tracking/state',
          '/tracking/navigation_state', '/tracking/navigation_diagnostics', '/tracking/status',
          '/tracking/command', '/tracking/flight_command', '/tracking/supervisor_diagnostics',
          '/tracking/selection', '/tracking/flight_phase', '/scenario/stage2_profile',
          '/tf', '/tf_static', '/vehicle/odometry', '/fmu/in/trajectory_setpoint',
          '/fmu/in/offboard_control_mode', INFO}
BOUNDARY_TOPICS = {'/tracking/state', '/tracking/navigation_state', '/tracking/status',
                   '/tracking/command', '/tracking/flight_command', '/fmu/in/trajectory_setpoint',
                   '/fmu/in/offboard_control_mode', '/tf_static'}
GLOBAL_CONTEXT_TOPICS = {'/tf_static', '/scenario/stage2_profile', '/tracking/selection', '/tracking/flight_phase'}


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024**2):
            result.update(block)
    return result.hexdigest()


def small(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_SMALL, 'Bounded ordinary small file required')
    with path.open('rb') as stream:
        data = stream.read(MAX_SMALL + 1)
    require(len(data) <= MAX_SMALL, 'Small input grew beyond limit')
    return data


def pin(path):
    path = Path(path)
    return {'path': str(path.resolve(strict=True)), 'sha256': hashlib.sha256(small(path)).hexdigest()}


def checked(binding):
    require(isinstance(binding, dict) and set(binding) == {'path', 'sha256'}
            and isinstance(binding['path'], str) and Path(binding['path']).is_absolute()
            and isinstance(binding['sha256'], str) and len(binding['sha256']) == 64
            and all(char in '0123456789abcdef' for char in binding['sha256'])
            and pin(binding['path']) == binding, 'Exact original physical path/SHA required')
    return Path(binding['path'])


def decode(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda token: (_ for _ in ()).throw(ValueError('Nonfinite JSON token')))


def read(binding):
    value = decode(small(checked(binding)).decode('utf-8-sig'))
    require(isinstance(value, dict), 'Original JSON object required')
    return value


def ns(value):
    number = Decimal(str(value)) * Decimal(1000000000)
    require(number.is_finite() and number == number.to_integral_value(), 'Exact finite integer nanosecond time required')
    return int(number)


def stamp(header):
    try:
        value = header.stamp
        require(type(value.sec) is int and type(value.nanosec) is int and 0 <= value.nanosec < 1000000000, 'Invalid ROS stamp')
        return value.sec * 1000000000 + value.nanosec
    except AttributeError:
        return None


def same_path(value, path):
    return isinstance(value, str) and Path(value).is_absolute() and Path(value).resolve() == Path(path).resolve()


def same_binding(value, expected):
    return isinstance(value, dict) and value.get('sha256') == expected['sha256'] and same_path(value.get('path'), expected['path'])


def tool_manifest():
    return {'kind': 'RAW_NATIVE_CAUSAL_EXPORT_NOT_REPLAY_OR_ADMISSION', 'schema_version': 1,
            'files': {name: pin(HERE / name)['sha256'] for name in OWN},
            'default': 'describe', 'native_traversals': 1, 'compressed_payload_hash_passes': 2}


def validate(args):
    require(args.execute_after_core_idle is True, 'Root must explicitly schedule the closed recording in an idle window')
    require(canonical(tool_manifest()) == args.reviewed_tools_sha256, 'Reviewed new source identity required')
    for name, ceiling in (('max_archive_mib', 8192), ('max_cache_mib', 16384), ('max_output_mib', 512),
                          ('max_message_mib', 32), ('max_native_records', 2000000),
                          ('max_selected_records', 50000), ('max_tracks', 128)):
        require(type(getattr(args, name)) is int and 0 < getattr(args, name) <= ceiling, 'Resource limit exceeds reviewed bounds')
    pins = {label: {'path': path, 'sha256': sha} for label, path, sha in args.input}
    require(len(pins) == len(args.input) and set(pins) == LABELS, 'Exactly seven explicit unique original input pins required')
    values = {label: read(binding) for label, binding in pins.items()}
    review, manifest, plan, slot, attempt, terminal, contract = (values[key] for key in
        ('source_review', 'source_manifest', 'plan', 'slot', 'attempt', 'core_terminal', 'contract'))
    root = args.source_root.resolve(strict=True)
    trial = args.trial.resolve(strict=True)
    require(str(root) == str(args.source_root) and args.trial.is_absolute() and args.cache_parent.is_absolute()
            and root.is_dir() and trial.is_dir(), 'Actual canonical source root/trial required')
    require(review.get('status') == 'FINAL_SOURCE_AND_TOOLS_INDEPENDENTLY_REVIEWED'
            and review.get('frozen_root') == str(root) == manifest.get('source_root') == plan.get('frozen_root')
            and review.get('files') == manifest.get('files') and review.get('source_commit') == manifest.get('source_commit')
            and plan.get('source_hashes') == review.get('classified_source_hashes'), 'Original reviewed source/manifest/plan disagree')
    require(same_binding(manifest.get('final_review'), pins['source_review']), 'Original manifest must bind this final review')
    require(plan.get('plan_sha256') == canonical({key: value for key, value in plan.items() if key != 'plan_sha256'}), 'Original internal plan digest differs')
    output = Path(plan['output']).resolve(strict=True)
    results = (root / 'results').resolve(strict=True)
    require(output.is_relative_to(results) and pin(output / 'plan.json') == pins['plan'], 'Use the named original plan.json')
    trials = [row for row in plan['trials'] if row['id'] == args.slot_id]
    require(len(trials) == 1 and same_path(trials[0]['directory'], trial)
            and slot.get('id') == args.slot_id and slot.get('name') == trials[0]['name']
            and pin(output / 'slots' / (args.slot_id + '.json')) == pins['slot'], 'Actual selected original slot/trial differs')
    require(slot.get('status') not in {None, 'PENDING'} and slot.get('finished_utc')
            and slot.get('plan_sha256') == plan['plan_sha256']
            and slot.get('record_sha256') == canonical({key: value for key, value in slot.items() if key != 'record_sha256'}), 'Original closed slot/internal digest required')
    record = attempt.get('record', {}).get('record_binding', {})
    require(attempt.get('slot') == args.slot_id and type(attempt.get('number')) is int and attempt['number'] > 0
            and attempt.get('finished_utc') and same_binding(record, pins['slot'])
            and record.get('record_sha256') == slot['record_sha256'] and record.get('plan_sha256') == plan['plan_sha256'], 'Original attempt does not bind actual closed slot')
    require(terminal.get('action') == 'run-core' and terminal.get('finished_utc') and type(terminal.get('returncode')) is int
            and same_binding(terminal.get('plan', {}).get('plan'), pins['plan'])
            and same_binding(terminal.get('contract'), pins['contract']) and attempt in terminal.get('attempts', [])
            and terminal.get('actual_slot_statuses', {}).get(args.slot_id) == {
                'status': slot['status'], 'record_sha256': slot['record_sha256']}, 'Original stopped/closed core must preserve this actual attempt')
    require(same_binding(contract.get('candidate_manifest', {}), terminal.get('entry_binding_before', {}).get('candidate_manifest', {}))
            and same_binding(contract.get('entry_binding', {}).get('source_review'), pins['source_review']), 'Original source contract/driver binding differs')
    for binding in (record['started_marker'], attempt['started_marker']):
        actual = pin(Path(binding['path']).resolve(strict=True))
        require(same_binding(binding, actual), 'Original start marker changed')
        pins['started_' + str(len(pins))] = actual
    sources = {}
    for relative in SOURCE_FILES:
        binding = pin(root / relative)
        require(review['files'].get(relative) == binding['sha256'], 'Named frozen helper/message source changed: ' + relative)
        sources[relative] = binding
    pins.update({'source_' + str(index): binding for index, binding in enumerate(sources.values())})
    for relative in ('bag_integrity.json', 'recording_closure.json', 'summary.json', 'run_config.json',
                     'configuration/runtime_parameters.yaml', 'rosbag/metadata.yaml'):
        binding = pin(trial / relative)
        require(slot.get('artifact_hashes', {}).get(relative) == binding['sha256'], 'Original artifact pin differs: ' + relative)
        pins['artifact_' + relative] = binding
    integrity = read(pins['artifact_bag_integrity.json'])
    closure = read(pins['artifact_recording_closure.json'])
    summary = read(pins['artifact_summary.json'])
    require(integrity.get('status') == 'PASS' and integrity.get('recorder_exit_code') == 0
            and integrity.get('raw_validation', {}).get('status') == 'PASS'
            and integrity.get('native_reader_validation', {}).get('status') == 'PASS'
            and integrity['native_reader_validation'].get('full_stream_read') is True
            and same_path(integrity.get('destination'), trial / 'rosbag')
            and integrity.get('published_metadata_sha256') == pins['artifact_rosbag/metadata.yaml']['sha256']
            and closure.get('status') == 'PASS' and closure.get('finished_utc'), 'Original recording/native archive closure required')
    follow = ns(summary['follow_start_s'])
    start, end = (follow + ns(value) for value in args.window_follow_offset_s)
    require(0 <= start < end and end - start <= 10 * 1000000000, 'Explicit FOLLOW window must be increasing and at most ten seconds')
    requests = [ns(value) for value in args.frame_source_s]
    requests += [follow + ns(value) for value in args.frame_follow_offset_s]
    require(bool(requests) and len(requests) <= 20 and len(set(requests)) == len(requests)
            and all(start <= value <= end for value in requests), 'One to twenty exact unique frame stamps inside the declared window required')
    protected = (root, results, output, trial)
    destination = args.output.resolve()
    cache = args.cache_parent.resolve(strict=True)
    require(args.output.is_absolute() and not args.output.exists() and not args.output.is_symlink()
            and destination.parent.is_dir() and cache.is_dir()
            and not any(destination.is_relative_to(path) or cache.is_relative_to(path) for path in protected), 'Fresh output and cache parent must be external to original source/results')
    payloads = []
    for item in integrity.get('compressed_files', []):
        path = trial / 'rosbag' / item['path']
        require(path.resolve().is_relative_to((trial / 'rosbag').resolve()) and path.is_file() and not path.is_symlink()
                and path.stat().st_size == item['bytes'] and item['bytes'] <= args.max_archive_mib * 1024**2
                and item.get('zstd_test') == 'PASS', 'Original bounded ordinary compressed archive required')
        payloads.append({'path': str(path.resolve()), 'sha256': item['sha256'], 'bytes': item['bytes']})
    require(bool(payloads) and len(payloads) <= 16, 'Explicit original compressed storage map required')
    expected = integrity['native_reader_validation']['topic_counts']
    require(expected == integrity['raw_validation']['topic_counts'] and sum(expected.values()) == integrity['native_reader_validation']['message_count'], 'Original complete native topic counts disagree')
    return {'pins': pins, 'values': values, 'sources': sources, 'root': root, 'trial': trial,
            'output': destination, 'cache_parent': cache, 'payloads': payloads, 'expected_counts': expected,
            'raw_bytes': sum(item['raw_bytes'] for item in integrity['compressed_files']),
            'follow_ns': follow, 'start_ns': start, 'end_ns': end, 'requests': requests,
            'tools_sha256': args.reviewed_tools_sha256}


def plain(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {'nonfinite_float': repr(value)}
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if hasattr(value, 'get_fields_and_field_types'):
        return {key: plain(getattr(value, key)) for key in value.get_fields_and_field_types()}
    if hasattr(value, 'tolist'):
        return plain(value.tolist())
    if isinstance(value, (list, tuple)) or hasattr(value, '__iter__'):
        return [plain(item) for item in value]
    raise ValueError('Unsupported ROS field type: ' + type(value).__name__)


def borrowed_reader(binding):
    code = small(checked(binding)).decode('utf-8-sig')
    tree = ast.parse(code)
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'open_bag_reader']
    require(len(definitions) == 1, 'One original native reader function required')
    selected = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), definitions[0]], type_ignores=[])
    ast.fix_missing_locations(selected)
    namespace = dict(contextmanager=contextmanager, tempfile=tempfile, Path=Path, shutil=shutil, Any=Any)
    exec(compile(selected, binding['path'], 'exec'), namespace)
    return namespace['open_bag_reader']


def wire_type(value):
    """Normalize equivalent .msg / ROSIDL type spelling without type coercion."""
    value = value.replace(' ', '').replace('/msg/', '/')
    sequence = re.fullmatch(r'sequence<(.+?)(?:,([0-9]+))?>', value)
    if sequence:
        return 'sequence<' + wire_type(sequence[1]) + (',' + sequence[2] if sequence[2] else '') + '>'
    array = re.fullmatch(r'(.+)\[([0-9]*|<=[0-9]+)\]', value)
    if array:
        item, size = wire_type(array[1]), array[2]
        if not size or size.startswith('<='):
            return 'sequence<' + item + (',' + size[2:] if size else '') + '>'
        return item + '[' + size + ']'
    aliases = {'bool': 'boolean', 'float32': 'float', 'float64': 'double', 'byte': 'octet'}
    value = aliases.get(value, value)
    if value in {'boolean', 'octet', 'char', 'float', 'double', 'int8', 'uint8', 'int16', 'uint16',
                 'int32', 'uint32', 'int64', 'uint64', 'string', 'wstring'}:
        return value
    if re.fullmatch(r'(?:w?string)<=\d+', value):
        return value
    require(re.fullmatch(r'(?:[A-Za-z][A-Za-z0-9_]*/)?[A-Za-z][A-Za-z0-9_]*', value), 'Unsupported message type spelling')
    return value if '/' in value else 'uav_tracking_interfaces/' + value


def source_schema(binding):
    fields = {}
    for line in small(checked(binding)).decode().splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            parts = line.split()
            if len(parts) >= 2 and '=' in parts[1]:
                continue  # .msg constants, not bounded type declarations.
            require(len(parts) == 2 and parts[1] not in fields, 'Unsupported or duplicate original message field')
            fields[parts[1]] = wire_type(parts[0])
    return fields


def class_origin(cls, prefix):
    module = sys.modules.get(cls.__module__)
    filename = getattr(module, '__file__', None)
    require(isinstance(filename, str), 'Generated message module file is not observed')
    path = Path(filename).resolve(strict=True)
    require(path.is_relative_to(prefix), 'Generated message class imported from a foreign Python path')
    return pin(path)


def checked_class_schema(cls, binding):
    raw = dict(cls.get_fields_and_field_types())
    actual = {key: wire_type(value) for key, value in raw.items()}
    require(actual == source_schema(binding), 'Generated field types differ from pinned source: ' + binding['path'])
    return raw


class NativeRuntime:
    def __init__(self, context, args):
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
        from ament_index_python.packages import get_package_prefix
        require(os.environ.get('ROS_DISTRO') == 'humble', 'Actual Humble message environment required')
        interface_prefix = Path(get_package_prefix('uav_tracking_interfaces')).resolve(strict=True)
        require(interface_prefix.is_relative_to(context['root'] / 'ros2_ws'), 'Foreign generated custom message overlay')
        px4_prefix = Path(get_package_prefix('px4_msgs')).resolve(strict=True)
        require(args.px4_msgs_prefix is not None and px4_prefix == args.px4_msgs_prefix.resolve(strict=True), 'Explicit actual PX4 message overlay required')
        self.module, self.deserialize, self._get_message = rosbag2_py, deserialize_message, get_message
        # colcon --symlink-install may resolve generated Python into build/.
        # It must still belong to this exact frozen workspace, never another.
        self.message_prefixes = {'uav_tracking_interfaces': context['root'] / 'ros2_ws', 'px4_msgs': px4_prefix}
        self.open_original = borrowed_reader(context['sources'][READER_SOURCE])
        self.receipt = {'python_executable': sys.executable, 'python_version': sys.version,
                        'ROS_DISTRO': os.environ['ROS_DISTRO'], 'interface_prefix': str(interface_prefix),
                        'px4_msgs_prefix': str(px4_prefix), 'class_schemas': {}, 'generated_module_pins': {},
                        'px4_module_allowed_roots': [str(px4_prefix)],
                        'owned_native_caches': []}
        for name in INTERFACES:
            cls = self.get_message('uav_tracking_interfaces/msg/' + name)
            binding = context['sources']['ros2_ws/src/uav_tracking_interfaces/msg/' + name + '.msg']
            self.receipt['class_schemas'][name] = checked_class_schema(cls, binding)

    def get_message(self, name):
        cls = self._get_message(name)
        package = name.split('/')[0]
        if package in self.message_prefixes:
            origin = class_origin(cls, self.message_prefixes[package])
            existing = self.receipt['generated_module_pins'].setdefault(name, origin)
            require(existing == origin, 'Generated message module changed during native export')
        return cls

    @contextmanager
    def open(self, context):
        owned = tempfile.TemporaryDirectory(prefix='native_causal_owned_', dir=context['cache_parent'])
        previous = tempfile.tempdir
        receipt = {'owned_path': owned.name, 'removed': False, 'tempfile_tempdir_restored': False,
                   'reader_close_api': 'NOT_OBSERVED', 'reader_close_result': 'NOT_ATTEMPTED'}
        self.receipt['owned_native_caches'].append(receipt)
        tempfile.tempdir = owned.name
        try:
            with self.open_original(context['trial'] / 'rosbag', self.module) as native_pair:
                reader, metadata = native_pair
                try:
                    yield reader, metadata
                finally:
                    try:
                        close = getattr(reader, 'close', None)
                        receipt['reader_close_api'] = 'AVAILABLE' if callable(close) else 'NOT_AVAILABLE_REFERENCE_RELEASE_ONLY'
                        if callable(close):
                            receipt['reader_close_result'] = 'ATTEMPTED'
                            close()
                            receipt['reader_close_result'] = 'RETURNED'
                    finally:
                        close = reader = native_pair = None
        finally:
            # The borrowed context manager has now exited and released its
            # local references. The caller releases its export reader too.
            gc.collect()
            tempfile.tempdir = previous
            receipt['tempfile_tempdir_restored'] = tempfile.tempdir is previous
            try:
                owned.cleanup()
            except BaseException as error:
                receipt['cleanup_error'] = type(error).__name__ + ': ' + str(error)
                raise
            finally:
                receipt['removed'] = not Path(owned.name).exists()
            require(receipt['removed'] and receipt['tempfile_tempdir_restored'], 'Owned native cache cleanup/restoration incomplete')


class Writer:
    def __init__(self, root, limit):
        self.root, self.limit, self.bytes = root, limit, 0
        self.files = {}
        self.hashes = {}

    def write(self, name, data):
        require(self.bytes + len(data) <= self.limit, 'Explicit output budget exceeded')
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
        self.bytes += len(data)
        self.files[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        return self.files[name]

    def json(self, name, value):
        return self.write(name, (json.dumps(value, allow_nan=False, separators=(',', ':')) + '\n').encode())

    def append(self, name, data):
        require(self.bytes + len(data) <= self.limit, 'Explicit output budget exceeded')
        path = self.root / name
        if name not in self.hashes:
            with path.open('xb'):
                pass
            self.hashes[name] = hashlib.sha256()
            self.files[name] = {'bytes': 0, 'sha256': self.hashes[name].hexdigest()}
        with path.open('ab') as stream:
            stream.write(data)
        self.bytes += len(data)
        self.hashes[name].update(data)
        self.files[name] = {'bytes': self.files[name]['bytes'] + len(data), 'sha256': self.hashes[name].hexdigest()}


def times(message, payload):
    result = {'source_stamp_ns': stamp(getattr(message, 'header', None))}
    if hasattr(message, 'transforms'):
        result['transform_source_stamps_ns'] = [stamp(getattr(item, 'header', None)) for item in message.transforms]
    for key in ('acquisition_s', 'stamp_s', 'output_s', 'output_publication_s'):
        value = payload.get(key) if isinstance(payload, dict) else None
        if type(value) in (int, float) and math.isfinite(value):
            # Original floats remain untouched in payload/CDR. These integers
            # are only a window-comparison representation, not source stamps.
            result[key + '_derived_ns'] = round(value * 1000000000)
    for key in ('acquisition_ns', 'clock_epoch', 'acquisition_epoch'):
        if isinstance(payload, dict) and type(payload.get(key)) is int:
            result[key] = payload[key]
    return result


def export_stream(reader, runtime, context, args, writer):
    definitions = reader.get_all_topics_and_types()
    topic_types = {item.name: item.type for item in definitions}
    require(len(topic_types) == len(definitions) and set(context['expected_counts']) == set(topic_types), 'Native topic table differs from original validation')
    wanted = TOPICS | {RGB, DEPTH} | (GT if args.include_offline_gt else set())
    classes = {topic: runtime.get_message(type_name) for topic, type_name in topic_types.items() if topic in wanted}
    counts, selected = Counter(), Counter()
    received_clock, sequence = None, 0
    seen, prior, opened, next_boundary = set(), {}, set(), set()
    images = {str(value): {topic: [] for topic in (RGB, DEPTH, INFO)} for value in context['requests']}
    anchors, event_count = {}, 0
    start, end = context['start_ns'], context['end_ns']

    def emit(row, raw, tag):
        nonlocal event_count
        require(event_count < args.max_selected_records, 'Selected-record count exceeded')
        cdr = 'cdr/' + str(row['record_index']).zfill(9) + '.cdr'
        if cdr not in writer.files:
            writer.write(cdr, raw)
        event = {**row, 'selection': tag, 'cdr': cdr, 'cdr_sha256': writer.files[cdr]['sha256']}
        writer.append('events.jsonl', (json.dumps(event, allow_nan=False, separators=(',', ':')) + '\n').encode())
        event_count += 1
        selected[row['topic']] += 1

    while reader.has_next():
        topic, raw, recorder_ns = reader.read_next()
        sequence += 1
        require(sequence <= args.max_native_records and isinstance(raw, (bytes, bytearray))
                and len(raw) <= args.max_message_mib * 1024**2, 'Native record count/message bound exceeded')
        require(topic in topic_types and type(recorder_ns) is int, 'Unknown native topic/recorder timestamp')
        counts[topic] += 1
        if topic not in classes:
            continue
        message = runtime.deserialize(raw, classes[topic])
        if topic == '/clock':
            received_clock = stamp(type('ClockHeader', (), {'stamp': message.clock})())
        if topic in (RGB, DEPTH):
            acquisition = stamp(getattr(message, 'header', None))
            if acquisition not in context['requests']:
                continue
            image_data = bytes(message.data)
            require(type(message.height) is int and type(message.width) is int and type(message.step) is int
                    and message.height > 0 and message.width > 0 and message.step > 0
                    and len(image_data) == message.height * message.step, 'Incomplete image data/stride')
            bytes_per_pixel = {'rgb8': 3, 'bgr8': 3, 'rgba8': 4, 'bgra8': 4,
                               'mono8': 1, '8UC1': 1, '16UC1': 2, '32FC1': 4}.get(message.encoding)
            require(message.is_bigendian in (0, 1)
                    and (bytes_per_pixel is None or message.step >= message.width * bytes_per_pixel),
                    'Invalid image row stride or endianness')
            name = 'images/' + str(acquisition) + '_' + ('rgb' if topic == RGB else 'depth') + '_' + str(sequence)
            pixel_pin = writer.write(name + '.pixels.bin', image_data)
            cdr_pin = writer.write(name + '.cdr', bytes(raw))
            metadata = {'topic': topic, 'source_stamp_ns': acquisition, 'record_index': sequence,
                        'bag_record_ns': recorder_ns, 'recorded_clock_proxy_ns': received_clock,
                        'height': message.height, 'width': message.width, 'step': message.step,
                        'encoding': message.encoding, 'is_bigendian': message.is_bigendian,
                        'encoding_validation': 'SUPPORTED_BYTE_LAYOUT' if bytes_per_pixel is not None else 'NOT_OBSERVED_UNSUPPORTED_ENCODING',
                        'frame_id': message.header.frame_id, 'pixels': {'file': name + '.pixels.bin', **pixel_pin},
                        'cdr': {'file': name + '.cdr', **cdr_pin}, 'conversion': 'NONE_FULL_ORIGINAL_PIXELS_AND_CDR'}
            writer.json(name + '.json', metadata)
            images[str(acquisition)][topic].append(metadata)
            continue
        if hasattr(message, 'data') and isinstance(message.data, str):
            try:
                payload = decode(message.data)
            except (ValueError, TypeError) as error:
                payload = {'raw_text': message.data, 'json_decode_error': str(error)}
        else:
            payload = plain(message)
        require(isinstance(payload, dict), 'Decoded selected-topic payload must be an object')
        timing = times(message, payload)
        row = {'record_index': sequence, 'topic': topic, 'type': topic_types[topic],
               'bag_record_ns': recorder_ns, 'recorded_clock_proxy_ns': received_clock,
               'timing': timing, 'payload': payload}
        key = (topic, timing.get('acquisition_ns', timing.get('acquisition_s_derived_ns',
               timing.get('stamp_s_derived_ns', timing.get('source_stamp_ns')))),
               timing.get('clock_epoch'), timing.get('acquisition_epoch'),
               payload.get('target_uuid'), payload.get('track_id'), payload.get('candidate_id'),
               payload.get('measurement_processing_s'))
        if topic == '/tf':
            key += (tuple((stamp(getattr(item, 'header', None)), getattr(item, 'child_frame_id', None))
                          for item in message.transforms),)
        first_acquisition = key not in seen
        seen.add(key)
        require(len(seen) <= args.max_native_records, 'Acquisition identity budget exceeded')
        match = []
        if received_clock is not None and start <= received_clock <= end:
            match.append('recorded_clock_proxy')
        for field, value in timing.items():
            if field in {'clock_epoch', 'acquisition_epoch', 'transform_source_stamps_ns'}:
                continue
            acquisition_field = field in {'source_stamp_ns', 'acquisition_ns', 'acquisition_s_derived_ns', 'stamp_s_derived_ns'}
            # A late FIRST original acquisition may be selected. Timer updates
            # carrying an already observed source header are not fresh work.
            fresh = first_acquisition
            fresh = fresh and not (topic == '/tracking/tracks' and payload.get('projected') is True)
            if value is not None and start <= value <= end and (not acquisition_field or fresh):
                match.append(field)
        if topic == '/tf' and first_acquisition and any(value is not None and start <= value <= end
                for value in timing.get('transform_source_stamps_ns', [])):
            match.append('transform_source_stamps_ns')
        if topic in GLOBAL_CONTEXT_TOPICS:
            match.append('original_global_context')
        if topic == '/tracking/tracks' and isinstance(payload, dict):
            for track in payload.get('tracks', []):
                track_key = str(track['track_id'])
                anchor = anchors.setdefault(track_key, {'first_observed': row, 'last_before_window': None})
                if received_clock is not None and received_clock < start:
                    anchor['last_before_window'] = row
            require(len(anchors) <= args.max_tracks, 'Track anchor count exceeded')
        if topic == INFO and timing['source_stamp_ns'] in context['requests']:
            images[str(timing['source_stamp_ns'])][INFO].append(row)
            match.append('exact_camera_info_request')
        if match:
            if topic not in opened and topic in prior:
                emit(*prior[topic], 'last_record_before_window')
            emit(row, bytes(raw), match)
            opened.add(topic)
        elif topic in BOUNDARY_TOPICS:
            if topic not in opened:
                prior[topic] = (row, bytes(raw))
            elif topic not in next_boundary:
                emit(row, bytes(raw), 'first_record_after_window')
                next_boundary.add(topic)
    require(dict(counts) == context['expected_counts'], 'Single native traversal did not reproduce complete original topic counts')
    if 'events.jsonl' not in writer.files:
        writer.write('events.jsonl', b'')
    writer.json('track_anchors.json', {'tracks': anchors, 'true_birth_timestamp': 'NOT_OBSERVED_UNLESS_EXPLICIT_IN_ORIGINAL_PAYLOAD'})
    image_summary = []
    for requested, components in images.items():
        status = 'EXACT_COMPONENTS_EXPORTED' if all(len(rows) == 1 for rows in components.values()) else 'MISSING_OR_DUPLICATE_NO_SUBSTITUTION'
        image_summary.append({'requested_source_ns': int(requested), 'follow_offset_ns': int(requested) - context['follow_ns'],
                              'status': status, 'components': components})
    writer.json('image_requests.json', image_summary)
    return {'native_counts': dict(counts), 'selected_counts': dict(selected), 'native_records': sequence,
            'image_requests': [{key: value for key, value in row.items() if key != 'components'} for row in image_summary],
            'topic_types': topic_types, 'all_candidates_retained': True, 'single_track_filter': False,
            'private_association_predictor_state': 'NOT_OBSERVED', 'exact_association_replay': 'NOT_PERFORMED',
            'pairwise_rejected_association_scores': 'NOT_OBSERVED_UNLESS_RECORDED',
            'gt_scope': 'OFFLINE_ONLY_NEVER_RUNTIME' if args.include_offline_gt else 'NOT_DESERIALIZED'}


def execute(args, *, runtime_factory=NativeRuntime):
    context = validate(args)
    cache_need = context['raw_bytes'] + sum(item['bytes'] for item in context['payloads'])
    require(shutil.disk_usage(context['cache_parent']).free >= cache_need, 'Insufficient native temporary-cache space')
    require(cache_need <= args.max_cache_mib * 1024**2, 'Expanded native storage plus fallback copy exceeds explicit cache budget')
    output = context['output']
    output.mkdir(exist_ok=False)
    writer = Writer(output, args.max_output_mib * 1024**2)
    report = {'schema_version': 1, 'kind': 'RAW_NATIVE_CAUSAL_EXPORT_NOT_REPLAY_OR_ADMISSION',
              'started_utc': datetime.now(timezone.utc).isoformat(), 'status': 'STARTED',
              'original_input_pins': context['pins'], 'source_root': str(context['root']), 'trial': str(context['trial']),
              'follow_source_ns': context['follow_ns'], 'source_window_ns': [context['start_ns'], context['end_ns']],
              'original_slot_status': context['values']['slot']['status'],
              'original_core_status': context['values']['core_terminal'].get('status'),
              'original_core_counts': context['values']['core_terminal'].get('status_counts'),
              'original_attempt_error': context['values']['attempt'].get('error'),
              'original_owner': context['values']['core_terminal'].get('observer_owner_terminal'),
              'native_traversals': 0, 'compressed_hash_passes': 0, 'source_payloads': context['payloads'],
              'tools_sha256': context['tools_sha256'], 'error': None}
    error = None
    try:
        for label in LABELS:
            writer.write('inputs/' + label + '.json', small(checked(context['pins'][label])))
        for item in context['payloads']:
            require(digest(item['path']) == item['sha256'], 'Original compressed archive SHA differs before native read')
        report['compressed_hash_passes'] = 1
        runtime = runtime_factory(context, args)
        report['message_environment'] = runtime.receipt
        with runtime.open(context) as (reader, storage):
            try:
                report['native_traversals'] = 1
                report['native_storage'] = storage
                report['export'] = export_stream(reader, runtime, context, args, writer)
            finally:
                reader = None
        report['status'] = 'COMPLETE_RAW_EXPORT_ONLY_NOT_ALGORITHM_ACCEPTANCE'
    except BaseException as caught:
        error = caught
        report.update(status='ABORTED_PARTIAL_ORIGINALS_RETAINED', error=type(caught).__name__ + ': ' + str(caught))
    finally:
        try:
            for binding in context['pins'].values():
                checked(binding)
            for binding in report.get('message_environment', {}).get('generated_module_pins', {}).values():
                checked(binding)
            for item in context['payloads']:
                require(Path(item['path']).stat().st_size == item['bytes'] and digest(item['path']) == item['sha256'], 'Original compressed archive changed after native read')
            report['compressed_hash_passes'] += 1
            report['original_pins_and_compressed_payloads_unchanged'] = True
        except BaseException as caught:
            error = caught
            report.update(status='ABORTED_PARTIAL_ORIGINALS_RETAINED', original_pins_and_compressed_payloads_unchanged=False,
                          postcheck_error=type(caught).__name__ + ': ' + str(caught))
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report['files'] = writer.files
        # The terminal manifest remains possible even when the data budget is exhausted.
        with (output / 'manifest.json').open('x', encoding='utf-8') as stream:
            json.dump(report, stream, allow_nan=False, indent=2)
            stream.write('\n')
    if error is not None:
        raise RuntimeError('Raw export incomplete; preserve its manifest and original records') from error
    return report


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--execute-after-core-idle', action='store_true')
    result.add_argument('--describe', action='store_true')
    result.add_argument('--reviewed-tools-sha256')
    result.add_argument('--input', nargs=3, action='append', default=[], metavar=('LABEL', 'ABSOLUTE_PATH', 'SHA256'))
    result.add_argument('--source-root', type=Path)
    result.add_argument('--trial', type=Path)
    result.add_argument('--slot-id')
    result.add_argument('--output', type=Path)
    result.add_argument('--cache-parent', type=Path)
    result.add_argument('--px4-msgs-prefix', type=Path)
    result.add_argument('--window-follow-offset-s', nargs=2, default=['11.4', '14.9'])
    result.add_argument('--frame-source-s', action='append', default=[])
    result.add_argument('--frame-follow-offset-s', action='append', default=[])
    result.add_argument('--include-offline-gt', action='store_true')
    for name, default in (('max-archive-mib', 1024), ('max-cache-mib', 4096), ('max-output-mib', 128),
                          ('max-message-mib', 16), ('max-native-records', 1000000), ('max-selected-records', 20000), ('max-tracks', 64)):
        result.add_argument('--' + name, type=int, default=default)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.describe or not args.execute_after_core_idle:
            value = tool_manifest()
            print(json.dumps({'manifest': value, 'canonical_sha256': canonical(value), 'experimental_inputs_opened': False}))
            return 0
        require(all(getattr(args, name) is not None for name in ('source_root', 'trial', 'slot_id', 'output', 'cache_parent')), 'All actual paths and slot ID must be explicit')
        require(all(getattr(args, name.replace('-', '_')) > 0 for name in ('max-archive-mib', 'max-cache-mib', 'max-output-mib', 'max-message-mib', 'max-native-records', 'max-selected-records', 'max-tracks')), 'Explicit resource bounds must be positive')
        report = execute(args)
        print(json.dumps({'status': report['status'], 'output': str(args.output), 'original_slot_status': report['original_slot_status']}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, ImportError) as error:
        print(json.dumps({'status': 'REFUSED_OR_PARTIAL_NOT_REPLAY', 'error': type(error).__name__ + ': ' + str(error)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
