"""Frozen offline recorded-lineage method; no native imports or experiment action.

The endpoint is the controller's tick-start source-clock stamp, before update
and publication. A unique recorded constraint solution does not observe the
subscriber callback or prove complete causal lineage. It is never wall E2E,
publication completion, PX4 receipt/execution, or formal registration.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
KIND = 'OFFLINE_UNIQUE_RECORDED_CONTROL_TICK_LINEAGE_V1_NOT_CALLBACK_CAUSALITY'
ENDPOINT = '\u91c7\u96c6\u2192\u63a7\u5236\u5faa\u73af\u53d6\u65f6\uff08tick\u5f00\u59cb\uff09source_sim'
CONTEXT_KIND = 'NATIVE_PIPELINE_TIMING_EXPORT_CONTEXT_NOT_ACCEPTANCE'
MAX_SMALL = 128 * 1024**2
RECEIPTS = ('run_config.json', 'bag_integrity.json', 'recording_closure.json', 'process_exit_codes.json')
TOPICS = {
    '/clock': 'clock', '/tracking/detection_diagnostics': 'detector',
    '/tracking/status': 'controller_status', '/tracking/command': 'controller_command',
    '/tracking/flight_command': 'flight_command', '/tracking/navigation_state': 'navigation_state',
    '/tracking/navigation_diagnostics': 'navigation_diagnostics',
    '/fmu/in/trajectory_setpoint': 'px4_setpoint',
}
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
SUPPORTED_SOURCES = {
    'ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/controller_node.py': 'fa37a4de445896f8fd08b0bfa2c99a200623c39d98427ccedfe16cc9c6361959',
    'ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/state_estimator_node.py': '696184b13ebb21307f1091171f15f5f628e6b46b101c692f1dcacea77861fbd0',
    'ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/navigation_estimator.py': '8d1abef9fe9d623f4cd43b0874e7c7843238a79920f198b17942d6cc8ebe2114',
    'ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/detector_node.py': '2316a7f331afec55844da65f6d6b4bb76de551e1bad262bd26ad3728a4636510',
    'ros2_ws/src/uav_tracking_interfaces/msg/TrackingCommand.msg': 'f7156a45aae6000ef70178eb46d27f2830d98c3369b1114961bceef63c04f172',
    'ros2_ws/src/uav_tracking_interfaces/msg/TrackingStatus.msg': 'f9d29ba33ee852f1bb301fa42f7d6e57aac92159f73961098d08e5a8f65a2f79',
    'ros2_ws/src/uav_tracking_interfaces/msg/TargetState.msg': 'b1967b3f2a0f31f298c2205a1c3defd0dcbea892745d9a6f3ea1c2fd97d84271',
}
EXPORTER_FILES = {
    'offline_pipeline_timing.py': 'c6367a2dd7e7a733958a9c15bf6ee3bff6e2b1fa93205c303148f5523d39a4e2',
    'test_offline_pipeline_timing.py': 'be4390929c5caac80a50cdc6c53c5f10a2e0476cd594414eb45e0378b3387617',
}
REQUIRED_KINDS = ('clock', 'detector', 'controller_status', 'controller_command',
                  'navigation_state', 'navigation_diagnostics')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def number(value):
    try:
        return type(value) in (float, int) and math.isfinite(value)
    except OverflowError:
        return False


def integer(value, positive=False):
    return type(value) is int and (1 if positive else 0) <= value < 2**64


def f32(value):
    require(number(value), 'nonfinite_or_missing_number')
    try:
        result = struct.unpack('!f', struct.pack('!f', value))[0]
    except (OverflowError, struct.error):
        raise ValueError('binary32_overflow') from None
    require(math.isfinite(result), 'binary32_overflow')
    return result


def bits32(value):
    require(number(value) and f32(value) == value, 'not_exact_native_binary32')
    require(value != 0 or math.copysign(1, value) > 0, 'negative_zero_not_supported')
    return struct.pack('!f', value).hex()


def adjacent32(value, direction):
    require(value >= 0 and bits32(value), 'nonnegative_binary32_required')
    bits = struct.unpack('!I', struct.pack('!f', value))[0]
    if direction < 0 and bits == 0:
        return -struct.unpack('!f', struct.pack('!I', 1))[0]
    result = struct.unpack('!f', struct.pack('!I', bits + direction))[0]
    require(math.isfinite(result), 'unbounded_binary32_rounding_interval')
    return result


def seconds_ns(value, *, conversion='stamp_parts'):
    """Require one exact integer preimage of the actual source conversion.

    State/output/accepted-source and detector stamps use the node's
    float(sec) + float(nanosec) * 1e-9. Only publication_s uses ns * 1e-9.
    Both are nondecreasing for integer 0 <= ns < 2**53: the integer operands
    are exact binary64 values, multiplication/addition use positive operands,
    and the last fractional stamp of a second never exceeds the next second.
    A lower bound finds the first preimage over that complete supported domain;
    an equal next integer proves ambiguity. No rounded centre, local tolerance
    or presumed inverse window can discard another compatible source stamp.
    """
    require(number(value) and 0 <= value < 2**53 / 1e9
            and (value != 0 or math.copysign(1, value) > 0), 'invalid_source_seconds')
    require(conversion in ('stamp_parts', 'nanoseconds_product'), 'unsupported_source_seconds_conversion')
    def encode(ns):
        if conversion == 'nanoseconds_product':
            return ns * 1e-9
        sec, nano = divmod(ns, 1_000_000_000)
        return float(sec) + float(nano) * 1e-9
    lower, upper = 0, 2**53
    while lower < upper:
        middle = (lower + upper) // 2
        if encode(middle) < value:
            lower = middle + 1
        else:
            upper = middle
    require(lower < 2**53 and encode(lower) == value,
            'source_seconds_not_exact_nanosecond_roundtrip')
    require(lower + 1 == 2**53 or encode(lower + 1) != value,
            'source_seconds_ambiguous_nanosecond_inverse')
    return lower


def stamp_ns(message):
    header = message.get('header', {})
    stamp = header.get('stamp', {}) if isinstance(header, dict) else {}
    sec, nano = stamp.get('sec'), stamp.get('nanosec')
    require(integer(sec) and integer(nano) and nano < 1_000_000_000, 'invalid_native_header')
    return sec * 1_000_000_000 + nano


def control_key(message):
    stamp = stamp_ns(message)
    track = message.get('track_id')
    require(stamp > 0 and integer(track), 'missing_command_tick_or_track')
    require(message.get('header', {}).get('frame_id') == 'map', 'non_map_control_frame')
    return stamp, track


def native_key(message):
    stamp, track = control_key(message)
    uuid, state = message.get('target_uuid'), message.get('state')
    require(isinstance(uuid, str) and uuid and type(state) is int and state in (1, 2),
            'invalid_native_uuid_or_active_state')
    return stamp, track, uuid, state


def diag_key(message):
    stamp = seconds_ns(message.get('output_s'))
    track, uuid, state = (message.get('output_track_id'), message.get('output_target_uuid'),
                          message.get('output_state'))
    require(stamp > 0 and integer(track) and isinstance(uuid, str) and uuid
            and type(state) is int and state in (1, 2), 'invalid_diagnostic_identity')
    return stamp, track, uuid, state


def vector(message, field):
    value = message.get(field)
    require(isinstance(value, dict), 'missing_native_vector:' + field)
    values = [value.get(axis) for axis in ('x', 'y', 'z')]
    require(all(number(v) for v in values), 'nonfinite_native_vector:' + field)
    return values


def flatten(value, rows, columns=0):
    require(isinstance(value, list) and len(value) == rows, 'invalid_array_shape')
    if columns:
        require(all(isinstance(row, list) and len(row) == columns for row in value), 'invalid_array_shape')
        value = [v for row in value for v in row]
    require(all(number(v) for v in value), 'nonfinite_array')
    return value


def validate_pair(native, diagnostic):
    require(diagnostic.get('diagnostic_schema_version') == 2 and diagnostic.get('valid') is True,
            'unsupported_or_invalid_navigation_diagnostic')
    header, _, _, _ = native_key(native)
    require(native_key(native) == diag_key(diagnostic), 'native_diagnostic_key_mismatch')
    acquired = seconds_ns(diagnostic.get('output_measurement_source_s'))
    publication = seconds_ns(diagnostic.get('output_publication_s'), conversion='nanoseconds_product')
    require(0 < acquired <= header <= publication, 'invalid_measurement_header_publication_order')
    age = diagnostic.get('measurement_age_s')
    require(number(age) and age >= 0
            and age == diagnostic['output_s'] - diagnostic['output_measurement_source_s'],
            'diagnostic_age_not_exact_accepted_source_difference')
    require(bits32(native.get('prediction_age_s')) == bits32(f32(age)), 'native_age_binary32_mismatch')
    for nfield, dfield in (('position_m', 'output_position_world_m'),
                           ('velocity_mps', 'output_velocity_world_mps')):
        nvalues, dvalues = vector(native, nfield), flatten(diagnostic.get(dfield), 3)
        require(all(abs(a-b) <= 1e-8 for a, b in zip(nvalues, dvalues)),
                'native_diagnostic_payload_mismatch:' + nfield)
    nvalues = flatten(native.get('covariance'), 36)
    dvalues = flatten(diagnostic.get('output_covariance_world_6x6'), 6, 6)
    require(all(bits32(a) == bits32(f32(b)) for a, b in zip(nvalues, dvalues)),
            'native_covariance_binary32_mismatch')
    require(type(native.get('target_visible')) is bool, 'invalid_native_visibility')
    return acquired


def acquisition_window(tick, age):
    """Evidence-derived window, then exact formula filtering (never nearest).

    The status rounding bin bounds the binary64 sum. Native wire age is no
    larger than that nonnegative sum. One full binary32 spacing at the bin's
    upper bound conservatively bounds native-age quantization. Eight ulps at
    tick seconds and age bound the binary64 source conversion/subtraction,
    controller multiply/add, and window arithmetic. Two integer outward
    rounds retain boundaries. This is an arithmetic error bound, not latency.
    """
    bits32(age)
    require(age >= 0, 'negative_status_age')
    previous, following = adjacent32(age, -1), adjacent32(age, 1)
    low, high = (previous + age) / 2, (following + age) / 2
    upper_wire = f32(high)
    spacing = max(abs(adjacent32(upper_wire, 1) - upper_wire),
                  abs(upper_wire - adjacent32(upper_wire, -1)))
    error = spacing + 8 * math.ulp(max(tick * 1e-9, 1.0)) + 8 * math.ulp(max(high, 1.0))
    return math.floor(tick - (high + error) * 1e9), math.ceil(tick - (low - error) * 1e9)


def statistics(values):
    values = sorted(values)
    if not values:
        return {'mean': None, 'median': None, 'p95': None, 'max': None}
    def q(frac):
        point = (len(values)-1) * frac
        lo, hi = math.floor(point), math.ceil(point)
        return values[lo] + (values[hi]-values[lo]) * (point-lo)
    return {'mean': math.fsum(values)/len(values), 'median': q(.5), 'p95': q(.95), 'max': values[-1]}


def analyze_events(events, coverage):
    """Pure constrained recorded matching; every original command is retained."""
    require(isinstance(events, list) and isinstance(coverage, dict), 'explicit_events_and_coverage_required')
    groups, errors, anomalies = defaultdict(list), defaultdict(list), []
    global_reasons = set()
    prior_sequence = prior_clock = prior_detector = None
    for index, event in enumerate(events):
        require(isinstance(event, dict) and isinstance(event.get('message'), dict), 'malformed_event_object')
        kind, stream, message = event.get('kind'), event.get('stream'), event['message']
        if stream == 'job_log':
            require(kind == 'job_timing' or (kind == 'decode_error' and event.get('failed_kind') == 'job_timing'),
                    'invalid_job_event')
            continue
        require(stream == 'bag' and event.get('topic') in TOPICS, 'invalid_bag_event')
        original_kind = TOPICS[event['topic']]
        require(kind == original_kind or (kind == 'decode_error' and event.get('failed_kind') == original_kind),
                'kind_topic_mismatch')
        sequence = event.get('bag_sequence')
        if not integer(sequence) or (prior_sequence is not None and sequence <= prior_sequence):
            global_reasons.add('bag_sequence_duplicate_or_regressed')
        if integer(sequence):
            prior_sequence = sequence
        if kind == 'decode_error':
            errors[original_kind].append(index)
            groups[original_kind].append((index, None))
            if original_kind in REQUIRED_KINDS:
                global_reasons.add('required_stream_decode_error:' + original_kind)
            continue
        groups[kind].append((index, message))
        try:
            if kind == 'clock':
                clock = message.get('clock', {})
                value = stamp_ns({'header': {'stamp': clock}})
                require(prior_clock is None or value >= prior_clock, 'source_clock_reset_or_regression')
                prior_clock = value
            elif kind == 'detector':
                epoch, acquired = message.get('clock_epoch'), message.get('acquisition_ns')
                require(integer(epoch) and integer(acquired, True), 'invalid_detector_source_key')
                current = epoch, acquired
                require(prior_detector is None or (epoch == prior_detector[0] and acquired >= prior_detector[1]),
                        'detector_epoch_change_or_acquisition_regression')
                prior_detector = current
        except (TypeError, ValueError, OverflowError) as error:
            global_reasons.add(str(error))
            anomalies.append({'event_index': index, 'reason': str(error)})
    for kind in REQUIRED_KINDS:
        if not groups[kind]:
            global_reasons.add('missing_stream:' + kind)
    if coverage.get('native_bag_read_to_end') is not True:
        global_reasons.add('native_bag_read_to_end_not_proven')

    commands, statuses, natives, diagnostics, detectors = (defaultdict(list) for _ in range(5))
    for kind, destination, key_function in (
            ('controller_command', commands, control_key), ('controller_status', statuses, control_key),
            ('navigation_state', natives, native_key), ('navigation_diagnostics', diagnostics, diag_key)):
        for index, message in groups[kind]:
            if message is None:
                continue
            # Lost/uninitialized native states are ordinary, inactive outputs.
            if kind == 'navigation_state' and type(message.get('state')) is int and message['state'] in (0, 3, 4):
                continue
            if kind == 'navigation_diagnostics' and message.get('valid') is False:
                continue
            try:
                destination[key_function(message)].append((index, message))
            except (TypeError, ValueError, OverflowError) as error:
                if kind != 'controller_command':
                    global_reasons.add('unindexable_' + kind)
                anomalies.append({'event_index': index, 'reason': str(error)})
    for index, message in groups['detector']:
        if message is not None and integer(message.get('clock_epoch')) and integer(message.get('acquisition_ns'), True):
            detectors[message['acquisition_ns']].append((index, message))

    # Indexed only once: each native keeps every diagnostic candidate, including
    # duplicates. A malformed candidate is never silently dropped in favour of
    # another plausible lineage.
    by_track, unindexable_tracks, future_by_track = defaultdict(list), set(), defaultdict(list)
    for key, diagnostic_rows in diagnostics.items():
        if key not in natives:
            unindexable_tracks.add(key[1])
            anomalies.append({'diagnostic_event_indices': [i for i, _ in diagnostic_rows],
                              'reason': 'diagnostic_without_separate_native_state'})
    for key, native_rows in natives.items():
        ds = diagnostics.get(key, [])
        for ni, native in native_rows:
            pair = {'native_event_index': ni, 'diagnostic_event_indices': [i for i, _ in ds],
                    'native_candidate_count_at_key': len(native_rows), 'diagnostic_candidate_count': len(ds),
                    'header_ns': key[0], 'track_id': key[1], 'target_uuid': key[2], 'state': key[3],
                    'acquisition_ns': None, 'reason': None, 'native': native}
            try:
                require(len(ds) == 1, 'missing_or_duplicate_navigation_diagnostic')
                pair['acquisition_ns'] = seconds_ns(ds[0][1].get('output_measurement_source_s'))
                validate_pair(native, ds[0][1])
                require(len(native_rows) == 1, 'duplicate_native_navigation_state')
            except (TypeError, ValueError, OverflowError) as error:
                pair['reason'] = str(error)
                anomalies.append({'native_event_index': ni, 'diagnostic_event_indices': pair['diagnostic_event_indices'],
                                  'reason': pair['reason']})
            future_by_track[key[1]].append(pair)
            if pair['acquisition_ns'] is None or pair['reason']:
                unindexable_tracks.add(key[1])
            if pair['acquisition_ns'] is not None:
                by_track[key[1]].append(pair)
    acquisition_keys = {}
    for track, rows in by_track.items():
        rows.sort(key=lambda p: p['acquisition_ns'])
        acquisition_keys[track] = [p['acquisition_ns'] for p in rows]
    # Future evidence is queried by header; prefix minimum event index avoids
    # scanning full history for each tick. It is not a callback-order claim.
    future_keys, future_prefix_min = {}, {}
    for track, rows in future_by_track.items():
        rows.sort(key=lambda p: p['header_ns'], reverse=True)
        future_keys[track] = [-p['header_ns'] for p in rows]
        prefix, minimum = [], len(events)
        for pair in rows:
            minimum = min(minimum, pair['native_event_index'])
            prefix.append(minimum)
        future_prefix_min[track] = prefix

    rows = []
    for index, command in groups['controller_command']:
        row = {'command_event_index': index, 'status': 'UNKNOWN', 'reasons': sorted(global_reasons), 'value_s': None,
               'tick_ns': None, 'track_id': None, 'status_event_indices': [],
               'native_headers_after_tick_total': 0,
               'arithmetic_window_acquisition_ns': None, 'indexed_native_candidate_count': 0,
               'formula_native_candidate_count': 0, 'candidates': [], 'lineage': None}
        rows.append(row)
        reasons = row['reasons']
        if command is None:
            reasons.append('command_decode_error')
            continue
        try:
            tick, track = control_key(command)
            row.update(tick_ns=tick, track_id=track)
            require(len(commands[tick, track]) == 1, 'duplicate_command_tick_track')
            ss = statuses.get((tick, track), [])
            row['status_event_indices'] = [i for i, _ in ss]
            require(len(ss) == 1, 'missing_or_duplicate_status_tick_track')
            status = ss[0][1]
            require(command.get('valid') is True and type(command.get('mode')) is int
                    and command['mode'] in (1, 2), 'inactive_or_invalid_command')
            require(type(status.get('lifecycle')) is int and status['lifecycle'] in (2, 3), 'inactive_status')
            require(type(status.get('prediction_active')) is bool and type(status.get('target_visible')) is bool,
                    'invalid_status_flags')
            age = status.get('time_since_measurement_s')
            lower, upper = acquisition_window(tick, age)
            row['arithmetic_window_acquisition_ns'] = [lower, upper]
            if track in unindexable_tracks:
                reasons.append('unindexable_native_lineage_for_track')
            fkeys = future_keys.get(track, [])
            future_count = bisect_left(fkeys, -tick)
            row['native_headers_after_tick_total'] = future_count
            if future_count and future_prefix_min[track][future_count-1] < index:
                reasons.append('future_native_header_recorded_before_command')
            entries, keys = by_track.get(track, []), acquisition_keys.get(track, [])
            candidates = entries[bisect_left(keys, lower):bisect_right(keys, upper)]
            row['indexed_native_candidate_count'] = len(candidates)
            matched = []
            for pair in candidates:
                public = {k: v for k, v in pair.items() if k != 'native'}
                public['expected_status_age_binary32'] = None
                row['candidates'].append(public)
                native = pair['native']
                if pair['header_ns'] > tick:
                    public['formula_match'] = False
                    public['excluded_reason'] = 'future_native_header'
                    continue
                try:
                    expected = f32(float(native['prediction_age_s']) + max(0, tick-pair['header_ns']) * 1e-9)
                    public['expected_status_age_binary32'] = bits32(expected)
                    public['formula_match'] = bits32(expected) == bits32(age)
                    if public['formula_match']:
                        matched.append(pair)
                except (KeyError, TypeError, ValueError, OverflowError) as error:
                    public['formula_match'] = None
                    public['excluded_reason'] = str(error)
                    reasons.append('malformed_candidate_cannot_exclude')
            row['formula_native_candidate_count'] = len(matched)
            require(len(matched) == 1, 'no_unique_native_formula_candidate')
            pair = matched[0]
            if pair['reason']:
                reasons.append(pair['reason'])
            native = pair['native']
            require(status['prediction_active'] == (pair['state'] == 2)
                    and status['target_visible'] == native['target_visible']
                    and status['lifecycle'] == (3 if pair['state'] == 2 else 2),
                    'native_status_lifecycle_or_visibility_mismatch')
            drows = detectors.get(pair['acquisition_ns'], [])
            require(len(drows) == 1, 'missing_or_duplicate_detector_accepted_source')
            di, detector = drows[0]
            require(seconds_ns(detector.get('stamp_s')) == pair['acquisition_ns'], 'detector_acquisition_fields_disagree')
            lineage = {'clock_epoch': detector['clock_epoch'], 'acquisition_ns': pair['acquisition_ns'],
                       'target_uuid': pair['target_uuid'], 'track_id': track,
                       'native_event_index': pair['native_event_index'],
                       'diagnostic_event_indices': pair['diagnostic_event_indices'], 'detector_event_index': di}
            row['lineage'] = lineage
            require(pair['acquisition_ns'] <= tick, 'future_accepted_acquisition')
            if not reasons:
                row.update(status='UNIQUE_RECORDED_CONSTRAINT_SOLUTION',
                           value_s=(tick-pair['acquisition_ns']) * 1e-9)
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            reasons.append(str(error))
        row['reasons'] = sorted(set(reasons))
    known = [row['value_s'] for row in rows if row['status'] == 'UNIQUE_RECORDED_CONSTRAINT_SOLUTION']
    return {'schema_version': 1, 'kind': KIND, 'endpoint_label': ENDPOINT,
            'time_domain': 'RECORDED_ROS_SOURCE_SIM_CLOCK', 'coverage': coverage,
            'original_command_denominator': len(rows), 'known_commands': len(known),
            'unknown_commands': len(rows)-len(known),
            'known_command_coverage': len(known)/len(rows) if rows else None,
            'unknown_reasons': dict(Counter(reason for row in rows for reason in row['reasons'])),
            'statistics_s_known_subset_only': statistics(known), 'commands': rows,
            'stream_opportunities': {k: len(v) for k, v in groups.items()},
            'decode_errors_by_stream': {k: len(v) for k, v in errors.items()},
            'global_unknown_reasons': sorted(global_reasons), 'anomalies': anomalies,
            'not_observed': ['complete_callback_causality', 'controller_publish_completion',
                             'px4_receipt_or_execution', 'wall_capture_to_effect_e2e', 'worker_wall_fps'],
            'interpretation': [
                'Endpoint is tick-start before controller.update and publish; not publish completion.',
                'Only a unique recorded constraint solution is reported; subscriber consumption is unobserved.',
                'Every original command, including inactive/decode errors/duplicates, stays in the denominator.',
                'Multiple native candidates stay UNKNOWN even when they share the same image lineage.',
                'Unknown samples do not receive zero latency and known-subset quantiles are not whole-run quantiles.',
                'Recorder timestamp is not used as a verified source clock or callback causality proof.']}


def ordinary(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_SMALL,
            'bounded_ordinary_file_required:' + str(path))
    return path


def pin(path):
    path = ordinary(path)
    return {'path': str(path.resolve(strict=True)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def checked(value):
    require(isinstance(value, dict) and set(value) == {'path', 'sha256'} and pin(value['path']) == value,
            'changed_or_aliased_bound_input')
    return Path(value['path'])


def loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_json_key:' + key)
            result[key] = value
        return result
    def floating(token):
        value = float(token)
        require(math.isfinite(value), 'nonfinite_json_number:' + token)
        return value
    value = json.loads(text, object_pairs_hook=pairs, parse_float=floating,
        parse_constant=lambda s: (_ for _ in ()).throw(ValueError('nonfinite_json_token:' + s)))
    return value


def manifest():
    return {'schema_version': 1, 'kind': KIND, 'method_status': 'FROZEN_OFFLINE_METHOD_NOT_FORMAL_REGISTRATION',
            'files': {name: pin(HERE/name)['sha256'] for name in ('control_tick_lineage.py', 'test_control_tick_lineage.py')},
            'supported_semantic_source_sha256': SUPPORTED_SOURCES, 'supported_timing_v2_files': EXPORTER_FILES,
            'endpoint_label': ENDPOINT, 'native_execution': False, 'formal_registration_created': False,
            'callback_causality_observed': False, 'nearest_message_matching': False}


def independent_output(output, root, trial, protected):
    path = Path(output).absolute()
    require(not path.exists() and not path.is_symlink(), 'exclusive_new_output_required')
    path = path.resolve()
    require(path.suffix == '.json' and path.parent.is_dir(), 'existing_parent_and_json_output_required')
    require(not any(path.is_relative_to(p) for p in (root, trial, *protected)), 'output_in_protected_root')
    return path


def analyze_files(events_path, context_binding, output):
    context = loads(checked(context_binding).read_text(encoding='utf-8-sig'))
    require(context.get('kind') == CONTEXT_KIND and type(context.get('schema_version')) is int
            and context['schema_version'] == 1 and context.get('topic_kinds') == TOPICS
            and context.get('recorder_timestamp_clock') == 'UNVERIFIED_RECORDER_TIMESTAMP_DOMAIN',
            'original_timing_v2_context_required')
    exporter = context.get('tools', {})
    require(exporter == {'schema_version': 1, 'kind': 'OFFLINE_OBSERVED_PIPELINE_TIMING_NOT_CAUSAL_E2E',
            'files': EXPORTER_FILES, 'online_files_changed': False, 'default_trial': None,
            'physical_capture_to_px4_effect_observable': False, 'recorder_timestamp_clock_is_verified': False,
            'nearest_or_payload_causal_matching': False, 'formal_seed_use_authorized': False},
            'unsupported_original_exporter')
    require(context.get('events') == pin(events_path), 'original_events_binding_mismatch')
    root, trial = Path(context['source_root']).resolve(strict=True), Path(context['trial']).resolve(strict=True)
    require(root.is_dir() and trial.is_dir() and str(root) == context['source_root']
            and str(trial) == context['trial'], 'canonical_original_source_trial_required')
    require(context.get('source_bindings') == {name: pin(root/name) for name in SOURCE_FILES},
            'complete_original_source_bindings_required')
    semantic_bindings = {name: pin(root/name) for name in SUPPORTED_SOURCES}
    require({name: value['sha256'] for name, value in semantic_bindings.items()} == SUPPORTED_SOURCES,
            'unsupported_controller_estimator_or_message_source')
    require(context.get('receipt_bindings') == {name: pin(trial/name) if (trial/name).is_file() else None for name in RECEIPTS},
            'complete_original_receipt_bindings_required')
    require(context.get('bag_metadata') == pin(trial/'rosbag/metadata.yaml'), 'original_bag_metadata_required')
    protected_values = context.get('protected_roots')
    require(isinstance(protected_values, list) and protected_values, 'explicit_protected_roots_required')
    protected = [Path(p).resolve(strict=True) for p in protected_values]
    require(all(p.is_dir() and str(p) == s for p, s in zip(protected, protected_values))
            and len(set(protected)) == len(protected), 'canonical_distinct_protected_roots_required')
    require(context.get('source_results_root') == str((root/'results').resolve()), 'source_results_alias_changed')
    require(isinstance(context.get('job_logs'), list)
            and len({v['path'] for v in context['job_logs']}) == len(context['job_logs']), 'distinct_bound_job_logs_required')
    bindings = [context_binding, context['events'], context['bag_metadata'], *semantic_bindings.values(),
                *context['source_bindings'].values(), *(v for v in context['receipt_bindings'].values() if v),
                *context['job_logs']]
    for value in bindings:
        checked(value)
    output = independent_output(output, root, trial, protected)
    require(output not in {Path(v['path']) for v in bindings}, 'output_must_not_alias_input')
    tool_before = manifest()
    lines = ordinary(events_path).read_text(encoding='utf-8-sig').splitlines()
    require(all(line.strip() for line in lines), 'blank_event_lines_not_permitted')
    events = [loads(line) for line in lines]
    counts = Counter(e.get('topic') for e in events if isinstance(e, dict) and e.get('stream') == 'bag')
    require(dict(counts) == context.get('selected_topic_counts'), 'selected_topic_denominators_differ_from_export')
    native_counts = context.get('native_topic_counts')
    require(isinstance(native_counts, dict) and all(native_counts.get(topic) == count for topic, count in counts.items()),
            'native_selected_topic_denominators_disagree')
    result = analyze_events(events, context['coverage'])
    result.update(inputs={'context': context_binding, 'events': context['events'],
                         'additional_semantic_bindings': semantic_bindings}, tools=tool_before,
                  job_logs_used_for_lineage=False, job_log_content_semantics='NOT_ANALYZED_NOT_WALL_FPS',
                  bag_payload_revalidated_by_this_analyzer=False)
    for value in bindings:
        checked(value)
    require(manifest() == tool_before, 'tool_changed_during_analysis')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    return pin(output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action')
    sub.add_parser('describe')
    action = sub.add_parser('analyze')
    for name in ('events', 'context', 'output'):
        action.add_argument('--'+name, type=Path, required=True)
    action.add_argument('--context-sha256', required=True)
    args = parser.parse_args(argv)
    if args.action in (None, 'describe'):
        value = {'manifest': manifest(), 'production_action_executed': False}
    else:
        value = analyze_files(args.events, {'path': str(args.context), 'sha256': args.context_sha256}, args.output)
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
