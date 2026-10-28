"""One source-preserving, filtered audit of a completed status-only abort.

No simulation, scores, images or flight commands. Installs pyulog without
dependencies into a fresh temporary directory, never the ROS environment.
Only the disposable decompressed SQLite cache is removed on completion.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

from audit_compressed_rosbag import ZstdStream, fingerprint
from observe_ros_link import mount_information
from run_guarded_full_plan import exclusive_guard, idle_writer_window

FROZEN = Path('/root/uav_tracking_fullplan_v3')
TRIAL = 'fullplan_v3_stage23_s3_person_gimbal_midpoint_seed000'
ULOG = Path('/root/PX4-Autopilot/build/px4_sitl_default/rootfs/log/2026-10-27/11_34_50.ulg')
TOPICS = ('/fmu/out/vehicle_status_v1', '/fmu/out/vehicle_odometry',
          '/vehicle/odometry', '/clock', '/tracking/flight_phase')
ULOG_TOPICS = ('vehicle_status', 'vehicle_odometry', 'timesync_status')
ABORT_EPOCH_NS = 1793100999132603500
STATUS_STAMP = 1793100995466084


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def scalar(value):
    if hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def gaps(rows, field, divisor):
    values = [row[field] for row in rows if row.get(field) is not None]
    if not values:
        return {'samples': 0}
    delta = [(values[index] - values[index - 1]) / divisor for index in range(1, len(values))]
    ordered = sorted(delta)
    return {'samples': len(values), 'first': values[0], 'last': values[-1],
            'min_gap_s': min(delta) if delta else None,
            'median_gap_s': ordered[len(ordered) // 2] if ordered else None,
            'max_gap_s': max(delta) if delta else None,
            'nonpositive_gaps': sum(value <= 0 for value in delta),
            'largest_gaps': sorted(({'previous': rows[index - 1].get(field),
                                    'next': rows[index].get(field),
                                    'gap_s': (rows[index][field] - rows[index - 1][field]) / divisor}
                                   for index in range(1, len(rows))
                                   if rows[index].get(field) is not None and rows[index - 1].get(field) is not None),
                                  key=lambda row: row['gap_s'], reverse=True)[:10]}


def ulog_audit(path, local):
    dependencies = local / 'python_dependencies'
    install = subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                              '--no-deps', '--target', str(dependencies), 'pyulog==1.2.2'],
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, timeout=120)
    (local / 'pyulog_install.log').write_text(install.stdout, encoding='utf-8')
    if install.returncode:
        raise RuntimeError('Could not install isolated ULog parser; source evidence unchanged')
    sys.path.insert(0, str(dependencies))
    from pyulog import ULog
    started = time.monotonic()
    parsed = ULog(str(path), message_name_filter_list=list(ULOG_TOPICS))
    datasets = {}
    for dataset in parsed.data_list:
        wanted = [name for name in dataset.data if name in {
            'timestamp', 'timestamp_sample', 'arming_state', 'nav_state', 'failsafe',
            'pre_flight_checks_pass', 'remote_timestamp', 'observed_offset',
            'estimated_offset', 'round_trip_time', 'source_protocol'}]
        values = [{name: scalar(dataset.data[name][index]) for name in wanted}
                  for index in range(len(dataset.data.get('timestamp', [])))]
        key = dataset.name + ':' + str(dataset.multi_id)
        save(local / ('ulog_' + dataset.name + '_' + str(dataset.multi_id) + '.json'), values)
        datasets[key] = {'fields': list(dataset.data), 'timestamp_statistics': gaps(values, 'timestamp', 1e6),
                         'around_sim_45_to_57s': [row for row in values if 45e6 <= row.get('timestamp', -1) <= 57e6]}
    dropouts = [{'timestamp_us': int(item.timestamp), 'duration_ms': int(item.duration)}
                for item in parsed.dropouts]
    return {'parser': 'pyulog 1.2.2, filtered during parsing', 'wall_s': time.monotonic() - started,
            'start_timestamp_us': int(parsed.start_timestamp), 'last_timestamp_us': int(parsed.last_timestamp),
            'file_corruption': bool(parsed.file_corruption), 'dropouts': dropouts,
            'info_keys': sorted(parsed.msg_info_dict),
            'logged_messages': [{'timestamp_us': int(item.timestamp), 'message': item.message}
                                for item in parsed.logged_messages], 'datasets': datasets,
            'limits': ['ULog is a logger subscriber; its subscription interval and dropout must be checked',
                       'A logged source timestamp gap alone does not prove missing uORB publication',
                       'DDS timestamps include a dynamic XRCE offset; no direct subtraction from this clock']}


def ros_message(topic, payload, timestamp, classes, deserialize):
    message = deserialize(payload, classes[topic])
    row = {'topic': topic, 'bag_storage_timestamp_ns': int(timestamp)}
    if topic == '/clock':
        row['clock_sim_ns'] = int(message.clock.sec) * 1000000000 + int(message.clock.nanosec)
    elif topic == '/fmu/out/vehicle_status_v1':
        row.update(dds_px4_timestamp_us=int(message.timestamp), arming_state=int(message.arming_state),
                   nav_state=int(message.nav_state), failsafe=bool(message.failsafe),
                   preflight_pass=bool(message.pre_flight_checks_pass))
    elif topic == '/fmu/out/vehicle_odometry':
        row.update(dds_px4_timestamp_us=int(message.timestamp),
                   dds_px4_timestamp_sample_us=int(message.timestamp_sample))
    elif topic == '/vehicle/odometry':
        row['adapter_ros_header_stamp_ns'] = int(message.header.stamp.sec) * 1000000000 + int(message.header.stamp.nanosec)
    else:
        row['phase_text'] = str(message.data)
    return row


def bag_audit(database_path, local):
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    # SQLite mode is explicitly immutable and readonly. Topic selection occurs
    # in SQL before loading blobs; image/depth blobs are never selected.
    with sqlite3.connect(database_path.as_uri() + '?mode=ro&immutable=1', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA temp_store=MEMORY')
        db.execute('PRAGMA cache_size=-8192')
        topic_rows = db.execute('SELECT id,name,type FROM topics').fetchall()
        chosen = [(identifier, topic, typename) for identifier, topic, typename in topic_rows if topic in TOPICS]
        if {topic for _, topic, _ in chosen} != set(TOPICS):
            raise RuntimeError('Required diagnostic topics are missing from the original bag')
        mapping = {identifier: topic for identifier, topic, _ in chosen}
        classes = {topic: get_message(typename) for _, topic, typename in chosen}
        ids = tuple(mapping)
        placeholders = ','.join('?' for _ in ids)
        cursor = db.execute('SELECT topic_id,timestamp,data FROM messages WHERE topic_id IN ('
                            + placeholders + ') ORDER BY timestamp,id', ids)
        latest_clock = None
        grouped = {topic: [] for topic in TOPICS}
        aborts, window, count = [], [], 0
        with (local / 'selected_topics.jsonl').open('x', encoding='utf-8') as output:
            for identifier, timestamp, payload in cursor:
                row = ros_message(mapping[identifier], payload, timestamp, classes, deserialize_message)
                if row['topic'] == '/clock':
                    latest_clock = row['clock_sim_ns']
                row['latest_preceding_bag_clock_sim_ns'] = latest_clock
                grouped[row['topic']].append(row)
                count += 1
                output.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
                if abs(timestamp - ABORT_EPOCH_NS) <= 5e9:
                    window.append(row)
                if 'ABORTED' in row.get('phase_text', ''):
                    aborts.append(row)
    summary = {'records': count, 'selected_topics_before_blob_read': list(TOPICS),
               'reader': 'immutable mode=ro SQLite SELECT with topic-id filter before blob load',
               'topics': {}, 'first_aborted_phase': aborts[0] if aborts else None,
               'matching_saved_status': [row for row in grouped['/fmu/out/vehicle_status_v1']
                                        if row.get('dds_px4_timestamp_us') == STATUS_STAMP],
               'status_in_log_abort_window': [row for row in window if row['topic'] == '/fmu/out/vehicle_status_v1'],
               'limits': ['Recorder storage timestamps are not supervisor monotonic timestamps',
                          'DDS PX4 stamps include changing XRCE offset; adjacent differences are not raw source periods',
                          'Recorder misses do not prove publisher misses; no scoring or flight verdict']}
    for topic, rows in grouped.items():
        active = [row for row in rows if row.get('latest_preceding_bag_clock_sim_ns') is not None
                  and 45000000000 <= row['latest_preceding_bag_clock_sim_ns'] <= 53000000000]
        summary['topics'][topic] = {'storage_intervals': gaps(rows, 'bag_storage_timestamp_ns', 1e9),
                                    'sim45_to_53_storage_intervals': gaps(active, 'bag_storage_timestamp_ns', 1e9)}
    save(local / 'abort_window.json', window)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--physical-host-free-bytes', type=int, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(FROZEN):
        parser.error('Use a fresh output outside the frozen checkout')
    bag = FROZEN / 'results' / TRIAL / 'rosbag'
    source = bag / 'rosbag_0.db3.zstd'
    with exclusive_guard(FROZEN), idle_writer_window(FROZEN):
        local = Path(tempfile.mkdtemp(prefix='status_source_audit_'))
        if mount_information(local)['filesystem'] != 'ext4':
            raise RuntimeError('Independent source copies require local ext4')
        before = {str(path): fingerprint(path) for path in (ULOG, source, bag / 'metadata.yaml')}
        save(local / 'source_before.json', before)
        header = ZstdStream().header(source)
        maximum = header['first_frame_content_size'] or (2300 * 1024**2)
        fixed = ULOG.stat().st_size + source.stat().st_size
        # WSL df reports the virtual filesystem limit, so also apply the
        # independently measured free space of its Windows backing volume.
        if maximum + fixed + 1024**3 > args.physical_host_free_bytes:
            raise RuntimeError('Physical Windows backing capacity is insufficient for isolated copies/decompression')
        if shutil.disk_usage(local).free < maximum + fixed + 1024**3:
            raise RuntimeError('Local ext4 capacity is insufficient')
        shutil.copy2(ULOG, local / ULOG.name)
        ulog = ulog_audit(local / ULOG.name, local)
        save(local / 'ulog_summary.json', ulog)
        print(json.dumps({'event': 'ULOG_AUDIT_RECORDED', 'local': str(local), 'datasets': list(ulog['datasets']),
                          'dropouts': ulog['dropouts'], 'corruption': ulog['file_corruption']}), flush=True)
        shutil.copy2(source, local / source.name)
        database = local / 'selected_source.db3'
        def guard(remaining):
            if database.exists() and database.stat().st_size > maximum:
                raise RuntimeError('Bounded decompression capacity reached')
            if shutil.disk_usage(local).free < remaining + 512 * 1024**2:
                raise RuntimeError('ext4 free space guard reached')
        decoded = ZstdStream().decompress(local / source.name, database,
                                          header['first_frame_content_size'], guard)
        if decoded['stream_test'] != 'COMPLETE':
            raise RuntimeError('Incomplete zstd source; preserve original failure')
        if decoded['decompressed_bytes'] > maximum:
            raise RuntimeError('Decoded source exceeds independently reserved capacity')
        bag_result = bag_audit(database, local)
        save(local / 'bag_summary.json', bag_result)
        after = {str(path): fingerprint(path) for path in (ULOG, source, bag / 'metadata.yaml')}
        save(local / 'source_after.json', after)
        if before != after:
            raise RuntimeError('Source bytes or metadata changed during read-only audit')
        copy_hashes = {ULOG.name: fingerprint(local / ULOG.name), source.name: fingerprint(local / source.name)}
        if (copy_hashes[ULOG.name]['sha256'] != before[str(ULOG)]['sha256']
                or copy_hashes[source.name]['sha256'] != before[str(source)]['sha256']):
            raise RuntimeError('Independent copies differ from the original source bytes')
        # Delete only the exact new cache created by this invocation. Preserve
        # independent source copies and all diagnostic JSON below /tmp.
        database.unlink()
        report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'trial': TRIAL,
                  'local_ext4': str(local), 'source_unchanged': before == after,
                  'physical_host_free_before_bytes': args.physical_host_free_bytes,
                  'zstd_header': header, 'zstd_decode': decoded, 'independent_copies': copy_hashes,
                  'decompressed_cache_removed': True, 'ulog': ulog, 'bag': bag_result,
                  'status': 'DIAGNOSTIC_ONLY_NO_ACCEPTANCE_OR_ROOT_CAUSE_VERDICT'}
        save(local / 'summary.json', report)
        output.mkdir(parents=True)
        # Archive only small diagnostics; no compressed inputs, database, or
        # temporary package dependencies are copied to the evidence volume.
        for path in local.iterdir():
            if path.is_file() and path.suffix in {'.json', '.jsonl', '.log'}:
                shutil.copy2(path, output / path.name)
        print(json.dumps({'event': 'SOURCE_AUDIT_COMPLETED', 'output': str(output),
                          'source_unchanged': True, 'local_ext4': str(local)}), flush=True)


if __name__ == '__main__':
    main()
