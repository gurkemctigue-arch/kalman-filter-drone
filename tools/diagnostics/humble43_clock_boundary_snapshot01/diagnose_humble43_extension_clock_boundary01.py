"""One original Humble43 failed extension slot; diagnostic only, no rerun.

Run once, without arguments, in the already sourced native Humble43 environment.
The two original readers retain their own topic filters and sequence spaces.
No ROS node, image/depth/truth deserialization, inference, or verdict edit occurs.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import gc
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time


ROOT = Path('/root/uav_tracking_fullplan_v4_humble43')
RESULTS = Path('/mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v4_humble43')
EXTERNAL = Path('/mnt/d/WSL/UAVHumble22-validation')
CACHE = Path('/root/uav_humble22/native_causal_cache')
OUTPUT = EXTERNAL / 'humble43_extension_clock_boundary_native01'
PLAN_DIR = RESULTS / 'reliability_v4_humble43_extensions_probe01_seed004_matrix'
SLOT_ID = 'car_extension_far_distance_seed004'
TRIAL = ROOT / ('results/reliability_v4_humble43_extensions_probe01_' + SLOT_ID)
SMALL = 16 * 1024 * 1024
OUTPUT_LIMIT = 16 * 1024 * 1024
PINS = {}
READS = []
OUTPUT_BYTES = 0
OUTPUT_OWNED = False
STATE = {'schema_version': 1, 'kind': 'HUMBLE43_EXTENSION_CLOCK_BOUNDARY_DIAGNOSTIC_ONLY',
         'original_verdicts_changed': False, 'formal_attempts_started': 0,
         'readers': READS, 'input_pins': PINS}
FIXED = {
    'plan': (PLAN_DIR / 'plan.json', '954baf82accd5a227faaa6b57776736c93fb6a23c937025afa112616f71e5ada'),
    'slot': (PLAN_DIR / 'slots' / (SLOT_ID + '.json'), 'd696b0063b220e37c4bb981ecc95231d36cc673519e5115ec9da0d5459bd59e6'),
    'slot_started': (PLAN_DIR / 'slots' / (SLOT_ID + '.started.json'), 'faf072dfab9d5b5037cc7b9267c29ce9f7354a817504d9a9e864c5a86fe302f9'),
    'source_manifest': (RESULTS / 'freeze_validation/source_freeze_manifest.json', 'b60ef5583bb8cd22ec76c3ccdb5b1e6b00b935f7115eeb552bb3e73cb4e4c23c'),
    'owner_attempt': (PLAN_DIR / 'observed_driver01/16_car_extension_far_distance_seed004.attempt_terminal.json', '85b9c0f3160211fb9997170bedc81d8c2b1c214f3c0388646803590e399414f7'),
    'owner_execution': (PLAN_DIR / 'observed_driver01/execution_terminal.json', '691c651a37a41c43e501a16309acf704628be8f428d65c6663a8c5acba932e04'),
    'producer_end': (RESULTS.parent / 'project_progress/humble43_extension01/end_summary.json', '194331674ce8b30bfddb4bdcec71a55764c1f754bcec88113d8391ebf3574153'),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def pin(label, path, expected=None):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= SMALL,
            'Missing, linked or oversized metadata/source: ' + str(path))
    result = {'path': str(path.resolve(strict=True)), 'bytes': path.stat().st_size, 'sha256': sha(path)}
    require(expected is None or result['sha256'] == expected, 'Changed original input: ' + label)
    require(label not in PINS or PINS[label] == result, 'Conflicting input pin: ' + label)
    PINS[label] = result
    return result


def document(label, path, expected=None):
    bound = pin(label, path, expected)
    return json.loads(Path(bound['path']).read_text(encoding='utf-8'),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def digest(value, excluded):
    # Exact original run_reliability_v4.digest JSON convention; no source import.
    clean = {key: item for key, item in value.items() if key not in excluded}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_new(name, value):
    global OUTPUT_BYTES
    encoded = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    require(OUTPUT_BYTES + len(encoded) <= OUTPUT_LIMIT, 'Diagnostic output would exceed 16 MiB; nothing is truncated')
    with (OUTPUT / name).open('xb') as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    OUTPUT_BYTES += len(encoded)


def cache_snapshot():
    # Direct entries only. Never recurse into or delete anyone else's cache.
    return {path.name: {'mode': path.lstat().st_mode, 'ino': path.lstat().st_ino,
                        'bytes': path.lstat().st_size, 'mtime_ns': path.lstat().st_mtime_ns}
            for path in CACHE.iterdir()}


def json_fields(value):
    """JSON message fields only; explicitly preserve nonfinite numeric values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {'nonfinite_float': repr(value)}
    if isinstance(value, dict):
        return {str(key): json_fields(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_fields(item) for item in value]
    if hasattr(value, 'tolist'):
        return json_fields(value.tolist())
    if hasattr(value, 'item'):
        return json_fields(value.item())
    if hasattr(value, 'get_fields_and_field_types'):
        return {name: json_fields(getattr(value, name)) for name in value.get_fields_and_field_types()}
    if hasattr(value, '__iter__') and not isinstance(value, (bytes, bytearray)):
        return [json_fields(item) for item in value]
    raise TypeError('Unsupported message field, never serialize CDR/pickle: ' + type(value).__name__)


def shown(row, space):
    return {'sequence_space': space, 'topic': row.topic, 'record_sequence': row.record_sequence,
            'time_s': json_fields(row.time_s), 'received_sim_s': json_fields(row.received_sim_s),
            'message': json_fields(row.message)}


def exact_header_ns(message):
    stamp = message.header.stamp
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


def stream_summary(rows, topics, space):
    result = {}
    for topic in topics:
        selected = [row for row in rows if row.topic == topic]
        result[topic] = {'count': len(selected), 'first': shown(selected[0], space) if selected else None,
                         'last': shown(selected[-1], space) if selected else None}
    first_clock = next((row.record_sequence for row in rows if row.topic == '/clock'), None)
    return {'sequence_space': space, 'rows': len(rows), 'streams': result,
            'first_clock_sequence': first_clock,
            'all_records_before_first_clock': [shown(row, space) for row in rows
                                               if first_clock is None or row.record_sequence < first_clock]}


def surrounding_clocks(rows, row, space):
    before = [clock for clock in rows if clock.topic == '/clock' and clock.record_sequence < row.record_sequence]
    after = next((clock for clock in rows if clock.topic == '/clock' and clock.record_sequence > row.record_sequence), None)
    return {'previous_clock': shown(before[-1], space) if before else None,
            'next_clock': shown(after, space) if after is not None else None}


def check_archive(files, phase):
    result = []
    for path, item in files:
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == item['bytes'],
                'Original compressed file metadata changed')
        actual = sha(path)
        require(actual == item['sha256'], 'Original compressed SHA changed: ' + phase)
        result.append({'path': str(path), 'bytes': item['bytes'], 'sha256': actual,
                       'matches_original_integrity': True, 'checked_utc': utc()})
    return result


def read_once(module, label, archive_files, baseline):
    require(cache_snapshot() == baseline, 'Native cache differs from baseline before ' + label)
    receipt = {'reader': module.__name__ + '.read_records', 'invocation': len(READS) + 1,
               'original_topics': list(module.TOPICS), 'started_utc': utc(), 'call_count': 0,
               'cache_before': baseline, 'archive_before': check_archive(archive_files, label + ':before')}
    READS.append(receipt)
    started = time.monotonic()
    try:
        receipt['call_count'] = 1
        rows, metadata = module.read_records(TRIAL / 'rosbag')
        receipt['metadata'] = metadata
        require(not metadata.get('read_errors'), 'Original reader reported errors: ' + label)
        require(metadata.get('source_bag_read_only') is True and metadata.get('reader') == 'SequentialCompressionReader',
                'Original native compressed read-only reader required')
        require(all(row.topic in module.TOPICS for row in rows), 'Reader filter escaped original topics')
        require([row.record_sequence for row in rows] == list(range(len(rows))), 'Original filtered reader sequence changed')
        return rows, metadata
    except BaseException as error:
        receipt['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        gc.collect()
        receipt['finished_utc'] = utc()
        receipt['wall_s'] = time.monotonic() - started
        receipt['archive_after'] = check_archive(archive_files, label + ':after')
        receipt['cache_after'] = cache_snapshot()
        receipt['cache_restored_to_baseline'] = receipt['cache_after'] == baseline
        require(receipt['cache_restored_to_baseline'], 'Original reader left native cache children; retain them, do not delete')


def main():
    global OUTPUT_OWNED
    require(len(sys.argv) == 1, 'This single-use diagnostic has no CLI arguments')
    require(sys.platform == 'linux' and os.environ.get('WSL_DISTRO_NAME') == 'UAVHumble22'
            and os.environ.get('ROS_DISTRO') == 'humble', 'Use actual native UAVHumble22/Humble')
    require(Path(sys.executable) == Path('/root/uav_humble22/venv/bin/python'), 'Use selected native venv Python')
    require(ROOT.is_dir() and not ROOT.is_symlink() and ROOT.resolve(strict=True) == ROOT
            and Path.cwd().resolve(strict=True) == ROOT, 'Run from actual immutable Humble43 source root')
    for key in ('HUMBLE22_PROJECT_ROOT', 'STAGE1_PROJECT_ROOT'):
        require(os.environ.get(key) == str(ROOT), 'Incorrect selected native project: ' + key)
    require(CACHE.is_dir() and not CACHE.is_symlink() and CACHE.resolve(strict=True) == CACHE
            and os.environ.get('TMPDIR') == str(CACHE) and Path(tempfile.gettempdir()).resolve(strict=True) == CACHE,
            'Explicit existing native_causal_cache TMPDIR required; never use default /tmp')
    require(EXTERNAL.resolve(strict=True) == EXTERNAL and RESULTS.resolve(strict=True) == RESULTS
            and TRIAL.resolve(strict=True).parent == RESULTS, 'Actual external/D physical paths required')
    require(not OUTPUT.exists() and not OUTPUT.is_symlink(), 'Exclusive new output required; no retry/reuse')
    own = pin('diagnostic_script', Path(__file__))
    originals = {name: document(name, path, expected) for name, (path, expected) in FIXED.items()}
    plan, record, marker, manifest = (originals[name] for name in ('plan', 'slot', 'slot_started', 'source_manifest'))
    require(plan.get('plan_sha256') == digest(plan, ('plan_sha256',))
            and record.get('record_sha256') == digest(record, ('record_sha256',)), 'Original plan/slot digest mismatch')
    require(plan.get('frozen_root') == str(ROOT) and plan.get('mode') == 'EXTENSION_PROBE'
            and record.get('id') == marker.get('id') == SLOT_ID
            and record.get('plan_sha256') == marker.get('plan_sha256') == plan['plan_sha256'], 'Original slot/plan relationship changed')
    trials = [trial for trial in plan['trials'] if trial['id'] == SLOT_ID]
    require(len(trials) == 1 and Path(trials[0]['directory']) == TRIAL
            and marker.get('flight_command') == trials[0]['flight_command'], 'Original trial directory/argv changed')
    require(record.get('execution_status') == 'COMPLETED' and record.get('infrastructure_stop') is False
            and record.get('flight_exit_code') == 0 and record.get('engineering_result') == record.get('status') == 'FAIL',
            'Expected exact original completed failed trial; never relabel it')
    require(manifest.get('source_root') == str(ROOT)
            and plan['source_hashes'] == manifest['classified_source_hashes'], 'Original frozen source maps differ')
    needed = ('px4_source_clock_report.json', 'native_startup_report.json', 'summary.json', 'bag_integrity.json',
              'recording_closure.json', 'recording_closure_observer.json', 'process_exit_codes.json', 'run_config.json',
              'configuration/runtime_parameters.yaml', 'configuration/px4_parameters.json', 'px4.log',
              'configuration/source_sha256.json', 'rosbag/metadata.yaml',
              'px4_source_clock_report.frames.jsonl', 'native_startup_report.frames.jsonl')
    for name in needed:
        require(name in record['artifact_hashes'], 'Original slot missing required artifact pin: ' + name)
        pin('trial:' + name, TRIAL / name, record['artifact_hashes'][name])
    source_report = document('trial:px4_source_clock_report.json', TRIAL / 'px4_source_clock_report.json')
    native_report = document('trial:native_startup_report.json', TRIAL / 'native_startup_report.json')
    integrity = document('trial:bag_integrity.json', TRIAL / 'bag_integrity.json')
    closure = document('trial:recording_closure.json', TRIAL / 'recording_closure.json')
    observer = document('trial:recording_closure_observer.json', TRIAL / 'recording_closure_observer.json')
    require(integrity.get('status') == integrity.get('raw_validation', {}).get('status') ==
            integrity.get('native_reader_validation', {}).get('status') == 'PASS'
            and integrity.get('native_reader_validation', {}).get('full_stream_read') is True
            and integrity.get('recorder_exit_code') == 0 and closure.get('status') == 'PASS'
            and observer.get('status') == 'CLOSED', 'Original source archive/closure must already be intact')
    require(integrity['published_metadata_sha256'] == record['artifact_hashes']['rosbag/metadata.yaml'], 'Archive metadata binding changed')
    raw_files = {item['path']: item for item in integrity['raw_validation']['files']}
    archive_files = []
    for item in integrity['compressed_files']:
        relative = Path(item['path'])
        require(not relative.is_absolute() and relative.suffix == '.zstd', 'Unexpected original compressed name')
        path = (TRIAL / 'rosbag' / relative).resolve(strict=True)
        require(path.is_relative_to((TRIAL / 'rosbag').resolve(strict=True)), 'Archive path escaped original bag')
        raw = raw_files[str(relative)[:-5]]
        require(item['zstd_test'] == 'PASS' and item['raw_sha256'] == raw['sha256'] and item['raw_bytes'] == raw['bytes']
                and raw['sqlite_integrity'] == 'ok', 'Original lossless archive relationship changed')
        archive_files.append((path, item))
    require(archive_files and len(archive_files) == len(raw_files), 'Missing original archive files')
    required_free = sum(item['bytes'] + item['raw_bytes'] for _, item in archive_files) + 8 * 1024**3
    STATE['storage_preflight'] = {'required_free_bytes': required_free, 'basis': 'original raw + compressed + 8 GiB', 'locations': {}}
    for label, path in (('native_root', ROOT), ('native_cache', CACHE), ('D_physical_results', RESULTS)):
        free = shutil.disk_usage(path).free
        STATE['storage_preflight']['locations'][label] = {'path': str(path), 'free_bytes': free}
        require(free >= required_free, 'Insufficient actual free space: ' + label)
    source_names = {'scripts/evaluate_px4_source_clock.py', 'scripts/evaluate_native_startup.py',
                    'scripts/evaluate_stage1_flight.py', 'scripts/humble22_env.sh', 'scripts/source_ros_environment.sh',
                    'scripts/run_reliability_v4.py', 'uav_tracking/ros_lifecycle.py'}
    for report in (source_report, native_report):
        provenance = report['evaluation_source']
        source_names.add(str(Path(provenance['script']).relative_to(ROOT)))
        for path, expected in {provenance['script']: provenance['script_sha256'], **provenance['dependencies']}.items():
            relative = str(Path(path).relative_to(ROOT))
            require(manifest['files'].get(relative) == expected, 'Original report/freeze source pin mismatch')
            source_names.add(relative)
    for relative in sorted(source_names):
        pin('source:' + relative, ROOT / relative, manifest['files'][relative])
    end = originals['producer_end']
    require(end.get('task', {}).get('finished_utc') and end.get('process_check', {}).get('verified_alive') is False
            and end['process_check'].get('identity_matches') is True and end['process_check']['observation'].get('alive') is False,
            'Original producer closure evidence required; healthy completion is not required')
    attempt = originals['owner_attempt']
    require(attempt['record']['record_binding']['sha256'] == PINS['slot']['sha256']
            and attempt['record']['record_binding']['record_sha256'] == record['record_sha256'], 'Original failed owner binds another slot')
    STATE['original_execution'] = {'slot': {key: record.get(key) for key in ('id', 'status', 'engineering_result', 'execution_status',
                                                                                       'infrastructure_stop', 'flight_exit_code', 'record_sha256')},
        'producer_saved_closure': {key: end.get(key) for key in ('status', 'task', 'process_check', 'evidence')},
        'owner_attempt': attempt,
        'owner_execution': {key: originals['owner_execution'].get(key) for key in ('status', 'returncode', 'error', 'finished_utc',
                                                                                 'attempt_count', 'terminal_count', 'status_counts', 'final_errors')},
        'interpretation': 'Original producer closed; original owner audit failed. Neither is promoted to healthy/PASS.'}
    sys.path.insert(0, str(ROOT / 'scripts'))
    source = importlib.import_module('evaluate_px4_source_clock')
    sys.path.insert(0, str(ROOT / 'scripts'))
    native = importlib.import_module('evaluate_native_startup')
    require(Path(source.__file__).resolve(strict=True) == ROOT / 'scripts/evaluate_px4_source_clock.py'
            and Path(native.__file__).resolve(strict=True) == ROOT / 'scripts/evaluate_native_startup.py', 'Evaluator import escaped frozen root')
    require(source.TOPICS == ('/clock', '/fmu/out/vehicle_odometry', '/vehicle/odometry_timing', '/vehicle/odometry')
            and native.TOPICS == ('/clock', '/fmu/out/vehicle_local_position_v1', '/fmu/out/estimator_status_flags',
                                  '/fmu/out/vehicle_status_v1', '/fmu/in/vehicle_command', '/vehicle/odometry',
                                  '/tracking/flight_phase', '/tracking/state', '/tracking/command'),
            'Original topic-filter definitions differ')
    # ROS metadata topic order is not a reader sequence; check its set separately.
    require(set(native.TOPICS) == set(native_report['bag']['topic_types']), 'Original native topic set changed')
    baseline = cache_snapshot()
    STATE['native_cache_baseline'] = baseline
    STATE['started_utc'] = utc()
    STATE['diagnostic_code'] = own
    OUTPUT.mkdir(mode=0o700)
    OUTPUT_OWNED = True
    write_new('started.json', {'schema_version': 1, 'started_utc': STATE['started_utc'], 'diagnostic_code': own,
                               'slot': PINS['slot'], 'plan': PINS['plan'], 'source_manifest': PINS['source_manifest'],
                               'storage_preflight': STATE['storage_preflight'], 'native_cache_baseline': baseline})
    rows, metadata = read_once(source, 'source_clock_four_topic_space', archive_files, baseline)
    require(metadata['topic_types'] == source_report['bag']['topic_types'], 'Source reader type metadata changed')
    source_space = 'original_source_clock_four_topic_filtered_sequence'
    STATE['source_streams'] = stream_summary(rows, source.TOPICS, source_space)
    for topic in source.TOPICS:
        require(STATE['source_streams']['streams'][topic]['count'] == integrity['raw_validation']['topic_counts'][topic], 'Source filtered count differs from original archive')
    recomputed = source.evaluate(rows, source.recorded_configuration(TRIAL))
    for key in ('counts', 'failures', 'incomplete_evidence', 'clock_domain_failures', 'vehicle_frame_failures',
                'evaluation_status', 'source_clock_pass', 'independent_reason_counts'):
        require(recomputed[key] == source_report[key], 'Source recomputation differs from original report: ' + key)
    STATE['source_recomputed'] = {key: recomputed[key] for key in ('counts', 'failures', 'incomplete_evidence',
                                                                  'clock_domain_failures', 'vehicle_frame_failures', 'evaluation_status', 'source_clock_pass')}
    by_sequence = {row.record_sequence: row for row in rows}
    used, used_raw, used_diagnostics = set(), set(), set()
    frame_count = 0
    with (TRIAL / 'px4_source_clock_report.frames.jsonl').open(encoding='utf-8') as stream:
        for frame_count, line in enumerate(stream, 1):
            frame = json.loads(line)
            require(frame_count <= len(recomputed['frames']) and frame == recomputed['frames'][frame_count - 1], 'Original source frame sidecar differs from exact original reevaluation')
            require(by_sequence[frame['record_sequence']].topic == source.TIMING_TOPIC, 'Original diagnostic sequence references another topic')
            used_diagnostics.add(frame['record_sequence'])
            if frame.get('raw_matched'):
                used_raw.add(frame['raw_record_sequence'])
            if frame.get('odometry_matched'):
                sequence = frame['odometry_record_sequence']
                require(sequence not in used and by_sequence[sequence].topic == source.ODOMETRY_TOPIC
                        and by_sequence[frame['raw_record_sequence']].topic == source.RAW_TOPIC
                        and source._odom_matches(by_sequence[frame['raw_record_sequence']].message, by_sequence[sequence].message),
                        'Original matched odometry sequence/header/frame content disagrees')
                used.add(sequence)
    require(frame_count == len(recomputed['frames']) == source_report['counts']['timing_diagnostics'], 'Original source frame denominator changed')
    STATE['original_source_frames_validation'] = {'full_frame_dicts_equal': True, 'frames': frame_count,
        'matched_original_odometry_sequences': len(used), 'sequence_space': source_space,
        'sidecar': PINS['trial:px4_source_clock_report.frames.jsonl']}
    orphan_rows = [row for row in rows if row.topic == source.ODOMETRY_TOPIC and row.record_sequence not in used]
    require(len(orphan_rows) == source_report['failures'].get('adapted_odometry_without_valid_raw_diagnostic_correspondence') == 1,
            'Expected exactly the original one unconsumed adapted message')
    STATE['unconsumed_adapted'] = []
    for row in orphan_rows:
        entry = {'original_message': shown(row, source_space), **surrounding_clocks(rows, row, source_space), 'neighborhoods': []}
        header_source = source.stamp_s(row.message.header.stamp)
        header_ns = exact_header_ns(row.message)
        # Exact-key candidates are context only. The consumed set remains solely
        # the original sidecar's assignment; no extra pairing is introduced.
        same_header, raw_sample, diagnostic_sample = [], [], []
        for other in rows:
            if other.topic == source.ODOMETRY_TOPIC and exact_header_ns(other.message) == header_ns:
                same_header.append({'original_message': shown(other, source_space),
                                    'consumed_by_original_frames': other.record_sequence in used})
            elif other.topic == source.RAW_TOPIC and source._source_ns(other.message.timestamp_sample) == header_ns:
                raw_sample.append({'original_message': shown(other, source_space),
                                   'consumed_by_original_frames': other.record_sequence in used_raw})
            elif other.topic == source.TIMING_TOPIC:
                original_diagnostic = json.loads(other.message.data)
                if source._seconds_ns(original_diagnostic.get('source_sample_s')) == header_ns:
                    diagnostic_sample.append({'original_message': shown(other, source_space),
                                              'consumed_by_original_frames': other.record_sequence in used_diagnostics})
        entry['exact_header_key_context'] = {'context_only': True, 'header_source_ns': header_ns,
            'rule': 'Exact integer header sec*1e9+nanosec versus original PX4 integer timestamp_sample*1000; diagnostic seconds use original _seconds_ns. No nearest matching; context only',
            'adapted_same_header': same_header, 'raw_same_sample': raw_sample, 'diagnostic_same_sample': diagnostic_sample}
        anchors = [('recorded_delivery_s', row.received_sim_s), ('original_header_source_s', header_source)]
        for label, center in anchors:
            if source._finite(center) is None:
                entry['neighborhoods'].append({'anchor': label, 'center_s': None, 'rows': [], 'reason': 'No recorded value; never inferred'})
                continue
            neighbors = [other for other in rows if other.topic in source.TOPICS
                         and source._finite(other.received_sim_s) is not None and abs(other.received_sim_s - center) <= .2 + 1e-9]
            entry['neighborhoods'].append({'anchor': label, 'center_s': center, 'half_window_s': .2,
                'selection': 'Original recorded delivery clock only; context, never a new correspondence match',
                'counts': dict(Counter(other.topic for other in neighbors)), 'rows': [shown(other, source_space) for other in neighbors]})
        STATE['unconsumed_adapted'].append(entry)
    del by_sequence, recomputed, orphan_rows, rows, used, used_raw, used_diagnostics
    gc.collect()
    native_rows, native_metadata = read_once(native, 'native_startup_nine_topic_space', archive_files, baseline)
    native_space = 'original_native_startup_nine_topic_filtered_sequence_never_source_clock_sequence'
    require(native_metadata['topic_types'] == native_report['bag']['topic_types'], 'Native reader type metadata changed')
    STATE['native_streams'] = stream_summary(native_rows, native.TOPICS, native_space)
    for topic in native.TOPICS:
        count = STATE['native_streams']['streams'][topic]['count']
        expected = native_report['recorded_clock']['messages'] if topic == '/clock' else native_report['counts'][topic]
        require(count == expected == integrity['raw_validation']['topic_counts'][topic], 'Native original filtered count changed: ' + topic)
    violations, missing_sources = [], []
    for row in native_rows:
        if row.topic != native.PHASE:
            continue
        source_time = native.phase_source_time(row.message)
        delivery = native.finite(row.received_sim_s)
        if source_time is None or delivery is None:
            missing_sources.append(shown(row, native_space))
            continue
        age = delivery - source_time
        if not -.05 - native.EPS <= age <= .50 + native.EPS:
            violations.append({'phase_string': row.message.data, 'source_s': source_time, 'source_repr': repr(source_time),
                'delivery_s': delivery, 'delivery_repr': repr(delivery), 'age_s': age, 'age_repr': repr(age),
                'direction': 'future' if age < -.05 - native.EPS else 'stale',
                'bounds_s': [-.05, .50], 'original_EPS': native.EPS, 'row': shown(row, native_space),
                **surrounding_clocks(native_rows, row, native_space)})
    require(not missing_sources and len(violations) == native_report['failures']['phase_source_time_stale_or_future'] == 1,
            'Phase source-clock violation denominator differs from original native report')
    STATE['phase_boundary'] = {'phase_messages': STATE['native_streams']['streams'][native.PHASE]['count'],
        'original_failures': native_report['failures'], 'original_incomplete_evidence': native_report['incomplete_evidence'],
        'missing_source_or_delivery': missing_sources, 'violations': violations,
        'rule': 'Original phase_source_time and EPS; delivery-source outside [-.05-EPS,.50+EPS]',
        'sequence_space': native_space}
    del native_rows
    gc.collect()
    require(len(READS) == 2 and [item['call_count'] for item in READS] == [1, 1], 'Exactly two original reader invocations required')
    for bound in PINS.values():
        require(sha(bound['path']) == bound['sha256'], 'Original metadata/source changed during diagnosis')
    require(cache_snapshot() == baseline, 'Native cache did not return to exact direct-entry baseline')
    STATE.update(status='DIAGNOSTIC_COMPLETE_ORIGINAL_FAILURES_RETAINED', finished_utc=utc(),
                 source_reader_invocations=1, native_reader_invocations=1,
                 claim_boundary='Context only. Original engineering/source/native FAIL and owner failure remain unchanged; no repair, rerun, new acceptance, or inferred missing match.')
    write_new('diagnostic.json', STATE)
    print(json.dumps({'status': STATE['status'], 'original_unconsumed_adapted': 1, 'original_phase_age_violations': 1,
                      'original_reader_calls': 2, 'output': str(OUTPUT), 'output_bytes': OUTPUT_BYTES}))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        STATE.update(status='DIAGNOSTIC_FAILED_ORIGINALS_RETAINED', finished_utc=utc(), error=type(error).__name__ + ': ' + str(error))
        if OUTPUT_OWNED:
            try:
                write_new('failed.json', STATE)
            except Exception as write_error:
                STATE['error'] += '; failure receipt: ' + type(write_error).__name__ + ': ' + str(write_error)
        print(json.dumps({'status': STATE['status'], 'error': STATE['error'], 'output': str(OUTPUT), 'original_reader_calls': sum(item['call_count'] for item in READS)}))
        raise SystemExit(2)
