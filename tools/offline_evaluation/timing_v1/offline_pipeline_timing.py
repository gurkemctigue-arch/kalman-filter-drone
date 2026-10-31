"""Offline observed timing only; never infer physical capture-to-PX4 effect.

Import/describe/analyze need only Python's standard library. The explicit export
action lazily reads a real bag/log under root's separate scheduling authority.
No online source, protocol, controller or message is changed.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
OWN = ('offline_pipeline_timing.py', 'test_offline_pipeline_timing.py')
MAX_SMALL = 128 * 1024**2
RECEIPT_FILES = ('run_config.json', 'bag_integrity.json', 'recording_closure.json', 'process_exit_codes.json')
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
CONTEXT_KIND = 'NATIVE_PIPELINE_TIMING_EXPORT_CONTEXT_NOT_ACCEPTANCE'
REPORT_KIND = 'OFFLINE_OBSERVED_PIPELINE_TIMING_NOT_CAUSAL_E2E'
TOPICS = {
    '/clock': 'clock', '/tracking/detection_diagnostics': 'detector',
    '/tracking/status': 'controller_status', '/tracking/command': 'controller_command',
    '/tracking/flight_command': 'flight_command', '/tracking/navigation_state': 'navigation_state',
    '/tracking/navigation_diagnostics': 'navigation_diagnostics',
    '/fmu/in/trajectory_setpoint': 'px4_setpoint',
}
JSON_TOPICS = {'detector', 'navigation_diagnostics'}
SOURCE_FILES = (
    'scripts/evaluate_stage1_flight.py', 'scripts/run_stage1_trial.py',
    'ros2_ws/src/uav_tracking_interfaces/msg/TrackingCommand.msg',
    'ros2_ws/src/uav_tracking_interfaces/msg/TargetState.msg',
    'ros2_ws/src/uav_tracking_interfaces/msg/TrackingStatus.msg',
    'ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/controller_node.py',
    'ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/state_estimator_node.py',
    'ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/detector_node.py',
    'ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/inference_timing.py',
    'ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter/flight_supervisor.py',
    'ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter/adapter_node.py',
)


def require(value, reason):
    if not value:
        raise ValueError(reason)


def finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 2**63 - 1


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def ordinary(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_SMALL,
            'Bounded ordinary metadata/source file required: ' + str(path))
    return path


def pin(path):
    path = ordinary(path)
    return {'path': str(path.resolve(strict=True)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def checked(value):
    require(isinstance(value, dict) and set(value) == {'path', 'sha256'}
            and pin(value['path']) == value, 'Changed or aliased original timing input')
    return Path(value['path'])


def loads(text):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'Duplicate JSON key: ' + key)
            value[key] = item
        return value
    def floating(token):
        value = float(token)
        require(math.isfinite(value), 'Nonfinite JSON number: ' + token)
        return value
    return json.loads(text, object_pairs_hook=pairs, parse_float=floating,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON token: ' + value)))


def read(path):
    return loads(ordinary(path).read_text(encoding='utf-8-sig'))


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def tool_manifest():
    return {'schema_version': 1, 'kind': REPORT_KIND,
            'files': {name: pin(HERE / name)['sha256'] for name in OWN},
            'online_files_changed': False, 'default_trial': None,
            'physical_capture_to_px4_effect_observable': False,
            'recorder_timestamp_clock_is_verified': False,
            'nearest_or_payload_causal_matching': False, 'formal_seed_use_authorized': False}


def statistics(values):
    values = sorted(values)
    if not values:
        return {'mean': None, 'median': None, 'p95': None, 'max': None}
    def quantile(q):
        index = (len(values) - 1) * q
        low, high = math.floor(index), math.ceil(index)
        return values[low] + (values[high] - values[low]) * (index - low)
    return {'mean': sum(value / len(values) for value in values), 'median': quantile(.5),
            'p95': quantile(.95), 'max': values[-1]}


def summarized(rows, total):
    known = [row['value'] for row in rows if row['reason'] is None]
    return {'total': total, 'known': len(known), 'unknown': total - len(known),
            'unknown_reasons': dict(Counter(row['reason'] for row in rows if row['reason'] is not None)),
            'statistics_s': statistics(known), 'samples': rows}


def key(message, job=False):
    value = message.get('job_key') if job else [message.get('clock_epoch'), message.get('acquisition_ns')]
    return tuple(value) if isinstance(value, (list, tuple)) and len(value) == 2 \
        and integer(value[0]) and integer(value[1], 1) else None


def analyze_events(events, coverage):
    """Pure normalized-event analysis. Input order is retained, never repaired."""
    require(isinstance(events, list) and isinstance(coverage, dict), 'Events and explicit coverage required')
    anomalies, kinds, detectors, statuses, jobs = [], Counter(), [], [], []
    prior_sequence = prior_recorder = prior_clock = None
    bag_order_invalid = recorder_reversed = sim_reversed = False
    for index, event in enumerate(events):
        require(isinstance(event, dict), 'Each timing event must be an object')
        kind, stream = event.get('kind'), event.get('stream')
        require(isinstance(kind, str) and stream in ('bag', 'job_log'), 'Explicit event kind/stream required')
        kinds[kind] += 1
        if stream == 'bag':
            sequence, recorder = event.get('bag_sequence'), event.get('record_timestamp_ns')
            if not integer(sequence) or (prior_sequence is not None and sequence <= prior_sequence):
                bag_order_invalid = True
                anomalies.append({'event_index': index, 'reason': 'bag_sequence_duplicate_or_reversed'})
            if integer(sequence):
                prior_sequence = sequence
            if not integer(recorder, 1) or (prior_recorder is not None and recorder < prior_recorder):
                recorder_reversed = True
                anomalies.append({'event_index': index, 'reason': 'recorder_timestamp_missing_or_reversed'})
            if integer(recorder, 1):
                prior_recorder = recorder
            require(event.get('topic') in TOPICS and (kind == TOPICS[event['topic']] or kind == 'decode_error'),
                    'Event kind must match its original selected topic')
            require(kind != 'decode_error' or event.get('failed_kind') == TOPICS[event['topic']],
                    'Bag decode errors must retain the original selected kind')
        else:
            require(kind == 'job_timing' or (kind == 'decode_error' and event.get('failed_kind') == 'job_timing'),
                    'Job logs may contain only original job-timing opportunities')
        message = event.get('message', {})
        require(isinstance(message, dict), 'Original normalized message must be an object')
        if kind == 'clock':
            clock = message.get('clock', {})
            clock = clock if isinstance(clock, dict) else {}
            sec, nano = clock.get('sec'), clock.get('nanosec')
            stamp = sec * 1_000_000_000 + nano if integer(sec) and integer(nano) and nano < 1_000_000_000 else None
            if stamp is None or (prior_clock is not None and stamp < prior_clock):
                sim_reversed = True
                anomalies.append({'event_index': index, 'reason': 'recorded_source_clock_invalid_or_reversed'})
            if stamp is not None:
                prior_clock = stamp
        failed_kind = event.get('failed_kind') if kind == 'decode_error' else None
        if kind == 'detector' or failed_kind == 'detector':
            detectors.append((index, event, message, kind == 'decode_error'))
        elif kind == 'controller_status' or failed_kind == 'controller_status':
            statuses.append((index, message, kind == 'decode_error'))
        elif kind == 'job_timing' or failed_kind == 'job_timing':
            jobs.append((index, event, message, kind == 'decode_error'))

    frequencies = Counter(key(message) for _, _, message, failed in detectors if not failed and key(message) is not None)
    prior_key, detector_source_reversed = None, False
    for index, _, message, failed in detectors:
        current = None if failed else key(message)
        if current is not None:
            if prior_key is not None and (current[0] != prior_key[0] or current[1] < prior_key[1]):
                detector_source_reversed = True
                anomalies.append({'event_index': index, 'reason': 'detector_source_epoch_changed_or_acquisition_reversed'})
            prior_key = current
    source_invalid = bag_order_invalid or sim_reversed or detector_source_reversed
    detector_rows, wall_rows, recorder_times, acquisition_times = [], [], [], []
    for index, event, message, failed in detectors:
        current = key(message)
        reason = ('decode_error' if failed else 'missing_source_key' if current is None else
                  'duplicate_source_key' if frequencies[current] != 1 else None)
        completed, wall = message.get('completed_s'), message.get('inference_wall_s')
        latency_reason = reason or ('source_clock_or_order_invalid' if source_invalid else None)
        if latency_reason is None and (not finite(completed) or completed < current[1] / 1e9):
            latency_reason = 'invalid_or_negative_source_latency'
        detector_rows.append({'event_index': index, 'source_key': current, 'reason': latency_reason,
                              'value': None if latency_reason else completed - current[1] / 1e9})
        wall_reason = reason or (None if finite(wall) and wall >= 0 else 'invalid_processing_wall_duration')
        wall_rows.append({'event_index': index, 'source_key': current, 'reason': wall_reason,
                          'value': None if wall_reason else wall})
        if reason is None:
            recorder_times.append(event.get('record_timestamp_ns'))
            acquisition_times.append(current[1])

    def rate(times, invalid, domain):
        total = len(detectors)
        valid = (not invalid and total >= 2 and len(times) == total
                 and all(integer(value, 1) for value in times)
                 and all(b > a for a, b in zip(times, times[1:])))
        return {'status': 'OBSERVED_IN_DECLARED_DOMAIN' if valid else 'UNKNOWN', 'time_domain': domain,
                'total_completion_messages': total, 'known_completion_messages': total if valid else 0,
                'unknown_completion_messages': 0 if valid else total,
                'hz': (total - 1) * 1e9 / (times[-1] - times[0]) if valid else None,
                'reason': None if valid else 'Need at least two complete unique ordered samples with strictly increasing timestamps'}

    status_rows = []
    for index, message, failed in statuses:
        age = message.get('time_since_measurement_s')
        reason = ('decode_error' if failed else 'source_clock_or_order_invalid' if source_invalid else
                  None if finite(age) and age >= 0 else 'invalid_reported_measurement_age')
        status_rows.append({'event_index': index, 'reason': reason, 'value': None if reason else age})

    job_frequencies = Counter(key(message, True) for _, _, message, failed in jobs if not failed and key(message, True) is not None)
    coordinate_frequencies = Counter((event['log_index'], event['line_number']) for _, event, _, _ in jobs
                                     if integer(event.get('log_index')) and integer(event.get('line_number'), 1))
    prior_job_line = {}
    job_order_invalid, duplicate_coordinates = set(), set()
    for index, event, _, _ in jobs:
        log_index, line = event.get('log_index'), event.get('line_number')
        if integer(log_index) and integer(line, 1) and coordinate_frequencies[(log_index, line)] > 1:
            duplicate_coordinates.add(index)
            anomalies.append({'event_index': index, 'reason': 'job_log_physical_coordinate_duplicate'})
        if not integer(log_index) or not integer(line, 1) or line <= prior_job_line.get(log_index, 0):
            job_order_invalid.add(index)
            anomalies.append({'event_index': index, 'reason': 'job_log_line_duplicate_or_reversed'})
        if integer(log_index) and integer(line, 1):
            prior_job_line[log_index] = line
    job_prefix_rows, predict_rows = [], []
    for index, _, message, failed in jobs:
        current = key(message, True)
        reason = ('decode_error' if failed else 'job_log_physical_coordinate_duplicate' if index in duplicate_coordinates else
                  'job_log_line_order_invalid' if index in job_order_invalid else
                  'missing_job_key' if current is None else 'duplicate_job_key' if job_frequencies[current] != 1 else
                  'job_not_completed' if message.get('status') != 'completed' else
                  'partial_or_unrecognized_timing_scope' if type(message.get('schema_version')) is not int
                  or message['schema_version'] != 1 or message.get('scope') != 'production_work_before_timing_log'
                  or message.get('stage_sum_excludes_inclusive_lock_holds') is not True else None)
        value = message.get('production_work_before_timing_log_wall_s')
        prefix_reason = reason or (None if finite(value) and value >= 0 else 'invalid_final_job_prefix_wall_duration')
        stages, measured = message.get('stages'), message.get('measured_prefix_wall_s')
        parts = list(stages.values()) if isinstance(stages, dict) else []
        partition_valid = (bool(parts) and finite(measured) and measured >= 0
                           and all(isinstance(part, dict) and finite(part.get('wall_s')) and part['wall_s'] >= 0
                                   and integer(part.get('count'), 1) for part in parts))
        if prefix_reason is None and (not partition_valid
                or not math.isclose(value, measured, rel_tol=1e-6, abs_tol=1e-6)
                or not math.isclose(sum(part['wall_s'] for part in parts), value, rel_tol=1e-6, abs_tol=1e-6)):
            prefix_reason = 'incomplete_or_inconsistent_exclusive_wall_partition'
        job_prefix_rows.append({'event_index': index, 'source_key': current, 'reason': prefix_reason,
                                'value': None if prefix_reason else value})
        stage = stages.get('yolo_predict', {}) if isinstance(stages, dict) else {}
        stage = stage if isinstance(stage, dict) else {}
        duration = stage.get('wall_s')
        predict_reason = prefix_reason or (None if type(stage.get('count')) is int and stage['count'] == 1
                                   and finite(duration) and duration >= 0 else 'missing_or_invalid_predict_stage')
        predict_rows.append({'event_index': index, 'source_key': current, 'reason': predict_reason,
                             'value': None if predict_reason else duration})
    detector_keys = {value for value in frequencies if frequencies[value] == 1}
    job_keys = {value for value in job_frequencies if job_frequencies[value] == 1}
    missing = sorted(detector_keys - job_keys)
    command_total = sum(event['kind'] == 'controller_command'
                        or event.get('failed_kind') == 'controller_command' for event in events)
    unknown_e2e = {'status': 'NOT_OBSERVED', 'known': 0,
                  'unknown': command_total, 'sample_unit': 'Recorded controller commands including decode errors',
                  'statistics_s': statistics([]),
                  'reason': 'TrackingCommand has no UUID/acquisition token; supervisor restamps and PX4 setpoint has a new publish timestamp. No causal consume/effect acknowledgement or physical capture wall-clock trace.'}
    return {'schema_version': 1, 'kind': REPORT_KIND, 'scope': 'OBSERVABLE_TIMING_ONLY_NOT_ACCEPTANCE',
            'event_counts': dict(kinds), 'event_count': len(events), 'anomalies': anomalies,
            'coverage': dict(coverage), 'tail_certification': 'NOT_CERTIFIED_BY_THIS_TOOL',
            'detector_completion_recorder_rate': rate(recorder_times, bag_order_invalid or recorder_reversed, 'UNVERIFIED_RECORDER_TIMESTAMP_DOMAIN'),
            'detector_processed_source_fps': rate(acquisition_times, source_invalid, 'DETECTOR_ROS_SOURCE_CLOCK'),
            'detector_acquisition_to_prepublication_source_s': summarized(detector_rows, len(detectors)),
            'detector_processing_prefix_wall_s': summarized(wall_rows, len(detectors)),
            'controller_reported_measurement_age_source_s': summarized(status_rows, len(statuses)),
            'completed_job_before_timing_log_wall_s': summarized(job_prefix_rows, len(jobs)),
            'completed_job_yolo_predict_wall_s': summarized(predict_rows, len(jobs)),
            'job_outcomes': dict(Counter(message['status'] if isinstance(message.get('status'), str)
                                        else 'UNKNOWN_INVALID_OR_MISSING_STATUS' for _, _, message, _ in jobs)),
            'job_log_coverage': {'unique_detector_keys': len(detector_keys), 'unique_job_keys': len(job_keys),
                                 'completed_detector_keys_missing_unique_job_log': missing},
            'actual_worker_processed_wall_fps': {'status': 'NOT_OBSERVED', 'hz': None,
                'reason': 'No absolute monotonic worker completion endpoints or independently verified recorder wall-clock contract; recorder receive rate is reported separately.'},
            'capture_to_controller_causal_source_s': dict(unknown_e2e),
            'capture_to_px4_setpoint_causal_source_s': dict(unknown_e2e),
            'physical_capture_to_px4_effect_wall_s': dict(unknown_e2e),
            'boundaries': ['Never subtract recorder ns from ROS/sim timestamps or scale by RTF.',
                'Source-clock quantities are simulation seconds only under the independently checked recorded ROS use_sim_time contract; this tool does not infer that contract.',
                'completed_s is the detector clock sample taken before frame publication; not the final diagnostic publication.',
                'inference_wall_s includes a processing/publication prefix; it is not pure network predict().',
                'Final job duration excludes its timing-log write and later delivery; inclusive lock holds are not summed into stages.',
                'Thread CPU covers the caller thread only, not all native inference workers.',
                'No nearest, first, repeated-value or track-only matching is used to claim causal image-to-command latency.',
                'Original failures, malformed events, missing job records and all denominators remain disclosed.'],
            'formal_seed_use_authorized': False, 'flight_acceptance_granted': False}


def clean_native(value):
    if isinstance(value, dict):
        return {str(name): clean_native(item) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_native(item) for item in value]
    if type(value) is float and not math.isfinite(value):
        return {'nonfinite_native_float': 'NaN' if math.isnan(value) else '+Infinity' if value > 0 else '-Infinity'}
    return value


def job_events(path, index):
    marker = 'INFERENCE_JOB_TIMING '
    for number, original in enumerate(ordinary(path).read_text(encoding='utf-8', errors='strict').split('\n'), 1):
        line = ANSI.sub('', original.rstrip('\r'))
        if marker not in line:
            continue
        event = {'stream': 'job_log', 'kind': 'job_timing', 'log_index': index, 'line_number': number}
        try:
            # Strip terminal control decoration, retaining genuine trailing junk as an error.
            message = loads(line.split(marker, 1)[1].strip())
            require(isinstance(message, dict), 'Job timing log payload is not an object')
            event['message'] = message
        except (ValueError, TypeError) as error:
            event.update(kind='decode_error', failed_kind='job_timing', message={}, error=str(error))
        yield event


def independent_output(output, root, trial, protected_roots=(), *, directory=False):
    requested = Path(output).absolute()
    require(not requested.exists() and not requested.is_symlink(), 'Exclusive new independent output required')
    resolved = requested.resolve()
    require(resolved.parent.is_dir() and not resolved.is_relative_to(trial),
            'Output parent must exist outside the original trial')
    require(not any(resolved.is_relative_to(value) for value in (root, (root / 'results').resolve(), *protected_roots)),
            'Do not write into frozen source/build/plan roots')
    require(directory or resolved.suffix == '.json', 'Exclusive new report JSON required')
    return resolved


def export_native(source_root, trial, output, logs, protected_roots=()):
    """Heavy explicit action: never called by describe/analyze or pure tests."""
    root, trial = Path(source_root).resolve(strict=True), Path(trial).resolve(strict=True)
    protected = [Path(value).resolve(strict=True) for value in protected_roots]
    require(bool(protected) and all(value.is_dir() for value in protected) and len(set(protected)) == len(protected),
            'At least one distinct existing immutable plan/output root required')
    source_results_root = str((root / 'results').resolve())
    output = independent_output(output, root, trial, protected, directory=True)
    sources = {name: pin(root / name) for name in SOURCE_FILES}
    receipts = {name: pin(trial / name) if (trial / name).is_file() else None
                for name in RECEIPT_FILES}
    bag_metadata = pin(trial / 'rosbag/metadata.yaml')
    log_pins = [pin(path) for path in logs]
    require(len({item['path'] for item in log_pins}) == len(log_pins), 'Duplicate job-log source')
    tools = tool_manifest()
    output.mkdir()
    write_new(output / 'started.json', {'schema_version': 1, 'kind': CONTEXT_KIND, 'source_root': str(root),
              'trial': str(trial), 'source_bindings': sources, 'receipt_bindings': receipts,
              'protected_roots': [str(value) for value in protected],
              'source_results_root': source_results_root,
              'bag_metadata': bag_metadata, 'job_logs': log_pins, 'tools': tools,
              'created_utc': datetime.now(timezone.utc).isoformat(), 'formal_seed_use_authorized': False})
    try:
        # Deliberately lazy: no native imports or reads occur in other actions.
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
        from rosidl_runtime_py.convert import message_to_ordereddict
        sys.path.insert(0, str(root))
        helper_path = root / 'scripts/evaluate_stage1_flight.py'
        spec = importlib.util.spec_from_file_location('offline_timing_original_bag_reader', helper_path)
        helper = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = helper
        spec.loader.exec_module(helper)
        require(Path(helper.__file__).resolve(strict=True) == helper_path, 'Wrong existing bag-reader origin')
        native_counts, selected_counts = Counter(), Counter()
        event_path = output / 'events.jsonl'
        with event_path.open('x', encoding='utf-8', newline='\n') as stream:
            with helper.open_bag_reader(trial / 'rosbag', rosbag2_py) as (reader, storage):
                types = {item.name: item.type for item in reader.get_all_topics_and_types()}
                classes = {topic: get_message(types[topic]) for topic in TOPICS if topic in types}
                sequence = 0
                while reader.has_next():
                    topic, data, timestamp = reader.read_next()
                    native_counts[topic] += 1
                    if topic in TOPICS:
                        event = {'stream': 'bag', 'bag_sequence': sequence, 'record_timestamp_ns': int(timestamp),
                                 'topic': topic, 'kind': TOPICS[topic]}
                        try:
                            message = deserialize_message(data, classes[topic])
                            payload = loads(message.data) if TOPICS[topic] in JSON_TOPICS else clean_native(message_to_ordereddict(message))
                            require(isinstance(payload, dict), 'Native timing payload must be an object')
                            event['message'] = payload
                        except Exception as error:
                            event.update(kind='decode_error', failed_kind=TOPICS[topic], message={}, error=type(error).__name__ + ':' + str(error))
                        selected_counts[topic] += 1
                        stream.write(json.dumps(event, allow_nan=False, separators=(',', ':')) + '\n')
                    sequence += 1
            for index, value in enumerate(log_pins):
                for event in job_events(checked(value), index):
                    stream.write(json.dumps(event, allow_nan=False, separators=(',', ':')) + '\n')
        for value in (*sources.values(), *(value for value in receipts.values() if value), bag_metadata, *log_pins):
            checked(value)
        require(tools == tool_manifest(), 'Timing exporter/test source changed during export')
        require(source_results_root == str((root / 'results').resolve()), 'Original results alias changed during export')
        context = {'schema_version': 1, 'kind': CONTEXT_KIND, 'created_utc': datetime.now(timezone.utc).isoformat(),
                   'source_root': str(root), 'trial': str(trial), 'tools': tools, 'source_bindings': sources,
                   'protected_roots': [str(value) for value in protected],
                   'source_results_root': source_results_root,
                   'receipt_bindings': receipts, 'bag_metadata': bag_metadata, 'job_logs': log_pins,
                   'events': pin(event_path), 'topic_kinds': TOPICS, 'message_types': types,
                   'native_topic_counts': dict(native_counts), 'selected_topic_counts': dict(selected_counts),
                   'storage': storage, 'coverage': {'native_bag_read_to_end': True,
                       'original_recording_closure_available': receipts['recording_closure.json'] is not None,
                       'original_bag_integrity_available': receipts['bag_integrity.json'] is not None,
                       'recording_health_and_tail_acceptance': 'NOT_VALIDATED_BY_THIS_MEASUREMENT_TOOL'},
                   'recorder_timestamp_clock': 'UNVERIFIED_RECORDER_TIMESTAMP_DOMAIN',
                   'no_bag_or_weight_payload_hashes': True, 'formal_seed_use_authorized': False}
        write_new(output / 'context.json', context)
        return pin(output / 'context.json')
    except BaseException as error:
        write_new(output / 'failed.json', {'kind': CONTEXT_KIND, 'error': type(error).__name__ + ':' + str(error),
                  'status': 'FAILED_RETAIN_PARTIAL_EXPORT_NO_OVERWRITE', 'formal_seed_use_authorized': False})
        raise


def analyze_files(events_path, context_pin, output):
    context = read(checked(context_pin))
    require(type(context.get('schema_version')) is int and context['schema_version'] == 1 and context.get('kind') == CONTEXT_KIND
            and context.get('tools') == tool_manifest() and context.get('topic_kinds') == TOPICS
            and context.get('recorder_timestamp_clock') == 'UNVERIFIED_RECORDER_TIMESTAMP_DOMAIN',
            'Original source-bound unverified-domain export context required')
    require(context.get('events') == pin(events_path), 'Normalized events differ from original export')
    require(set(context['source_bindings']) == set(SOURCE_FILES), 'Complete actual source bindings required')
    root, trial = Path(context['source_root']).resolve(strict=True), Path(context['trial']).resolve(strict=True)
    require(root.is_dir() and trial.is_dir() and str(root) == context['source_root'] and str(trial) == context['trial'],
            'Canonical existing original source/trial directories required')
    require(context['source_bindings'] == {name: pin(root / name) for name in SOURCE_FILES},
            'Each binding must be the named actual source under its original root')
    require(set(context['receipt_bindings']) == set(RECEIPT_FILES), 'Exact original receipt mapping required')
    require(context['receipt_bindings'] == {name: pin(trial / name) if (trial / name).is_file() else None
                                           for name in RECEIPT_FILES}, 'Receipt binding must match its original trial path')
    require(context['bag_metadata'] == pin(trial / 'rosbag/metadata.yaml'), 'Original bag metadata path required')
    require(isinstance(context['job_logs'], list) and len({value['path'] for value in context['job_logs']}) == len(context['job_logs']),
            'Distinct original job-log sources required')
    protected_values = context['protected_roots']
    require(isinstance(protected_values, list) and bool(protected_values) and all(isinstance(value, str) for value in protected_values),
            'Explicit immutable plan/output root list required')
    protected = [Path(value).resolve(strict=True) for value in protected_values]
    require(all(value.is_dir() and str(value) == original for value, original in zip(protected, protected_values))
            and len(set(protected)) == len(protected), 'Canonical distinct immutable plan/output roots required')
    require(context['source_results_root'] == str((root / 'results').resolve()), 'Original resolved results root required')
    output = independent_output(output, root, trial, protected)
    all_pins = [context_pin, context['events'], context['bag_metadata'], *context['source_bindings'].values(),
                *(value for value in context['receipt_bindings'].values() if value), *context['job_logs']]
    for value in all_pins:
        checked(value)
    lines = ordinary(events_path).read_text(encoding='utf-8-sig').splitlines()
    require(all(line.strip() for line in lines), 'Blank/malformed JSONL lines cannot be silently skipped')
    events = [loads(line) for line in lines]
    normalized_jobs = [event for event in events if isinstance(event, dict) and event.get('stream') == 'job_log']
    require(all(integer(event.get('log_index')) and event['log_index'] < len(context['job_logs'])
                for event in normalized_jobs), 'Normalized job event references an unbound original log')
    original_jobs = [event for index, value in enumerate(context['job_logs'])
                     for event in job_events(checked(value), index)]
    require(normalized_jobs == original_jobs,
            'Complete normalized job events must equal reparsed bound original logs in original order and content')
    require(isinstance(context['coverage'], dict), 'Original explicit coverage object required')
    coverage = dict(context['coverage'], bound_job_logs_reparsed=len(context['job_logs']),
                    bound_original_job_events_reconstructed=len(original_jobs),
                    normalized_job_events_equal_bound_original_logs=True)
    result = analyze_events(events, coverage)
    result.update(inputs={'context': context_pin, 'events': context['events']}, tools=tool_manifest())
    for value in all_pins:
        checked(value)
    require(output.resolve() not in {Path(value['path']) for value in all_pins}, 'Report must be independent of every original input')
    write_new(output, result)
    return pin(output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action')
    sub.add_parser('describe')
    export = sub.add_parser('export')
    for name in ('source-root', 'trial', 'output'):
        export.add_argument('--' + name, type=Path, required=True)
    export.add_argument('--job-log', type=Path, action='append', default=[])
    export.add_argument('--protected-root', type=Path, action='append', required=True)
    analyze = sub.add_parser('analyze')
    for name in ('events', 'context', 'output'):
        analyze.add_argument('--' + name, type=Path, required=True)
    analyze.add_argument('--context-sha256', required=True)
    args = parser.parse_args(argv)
    if args.action in (None, 'describe'):
        value = tool_manifest()
        result = {'manifest': value, 'canonical_sha256': canonical(value), 'production_action_executed': False}
    elif args.action == 'export':
        result = export_native(args.source_root, args.trial, args.output, args.job_log, args.protected_root)
    else:
        result = analyze_files(args.events, {'path': str(args.context), 'sha256': args.context_sha256}, args.output)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
