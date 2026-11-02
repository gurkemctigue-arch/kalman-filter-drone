"""Read the stopped original recording once; retain clock evidence, no regrade."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path('/root/uav_tracking_fullplan_v4_humble51')
TRIAL = ROOT / 'results/reliability_v4_humble51_probe01_person_stage3_midpoint_seed004'
OUTPUT = Path('/mnt/d/WSL/UAVHumble22-validation/humble51_clock_stop01/native_raw01')
TOPICS = ('/clock', '/fmu/out/vehicle_odometry', '/vehicle/odometry_timing',
          '/vehicle/odometry', '/tracking/flight_phase')


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            value.update(block)
    return value.hexdigest()


def main():
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    sys.path.insert(0, str(ROOT / 'scripts'))
    from evaluate_stage1_flight import open_bag_reader
    from evaluate_native_startup import phase_source_time
    started = datetime.now(timezone.utc).isoformat()
    tick = time.monotonic()
    integrity = json.loads((TRIAL / 'bag_integrity.json').read_bytes())
    assert integrity['status'] == 'PASS'
    protected = [TRIAL / name for name in ('bag_integrity.json', 'run_config.json',
                 'px4_source_clock_report.json', 'native_startup_report.json')]
    protected += list((TRIAL / 'rosbag').glob('*.zstd'))
    protected += [TRIAL / 'rosbag/metadata.yaml']
    before = {str(p): {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in protected}
    assert shutil.disk_usage(OUTPUT.parent).free > 12 * 1024**3
    OUTPUT.mkdir(exist_ok=False)
    counts, rows, clock, raw, diagnostics, bad_phase = Counter(), [], None, [], [], []
    with open_bag_reader(TRIAL / 'rosbag', rosbag2_py) as (reader, metadata):
        types = {t.name: t.type for t in reader.get_all_topics_and_types() if t.name in TOPICS}
        assert set(types) == set(TOPICS)
        reader.set_filter(rosbag2_py.StorageFilter(topics=list(TOPICS)))
        classes = {t: get_message(name) for t, name in types.items()}
        while reader.has_next():
            topic, data, recorded_ns = reader.read_next()
            message = deserialize_message(data, classes[topic])
            row = {'filtered_sequence': len(rows), 'topic': topic,
                   'bag_record_timestamp_ns': int(recorded_ns)}
            counts[topic] += 1
            if topic == '/clock':
                clock = int(message.clock.sec) + int(message.clock.nanosec) * 1e-9
                row['clock_sim_s'] = clock
            elif topic == '/fmu/out/vehicle_odometry':
                row.update(sample_us=int(message.timestamp_sample), publication_us=int(message.timestamp),
                           reset_counter=int(message.reset_counter))
                raw.append(row)
            elif topic == '/vehicle/odometry_timing':
                row['diagnostic'] = json.loads(message.data)
                diagnostics.append(row)
            elif topic == '/vehicle/odometry':
                row['header_ns'] = int(message.header.stamp.sec) * 10**9 + int(message.header.stamp.nanosec)
            else:
                row.update(phase_text=message.data, phase_source_s=phase_source_time(message))
            row['latest_recorded_clock_sim_s'] = clock
            if topic == '/tracking/flight_phase' and row['phase_source_s'] is not None:
                row['phase_age_s'] = clock - row['phase_source_s'] if clock is not None else None
                if row['phase_age_s'] is None or not -.050000001 <= row['phase_age_s'] <= .500000001:
                    bad_phase.append(row)
            rows.append(row)
    expected = integrity['native_reader_validation']['topic_counts'] if 'native_reader_validation' in integrity else integrity['raw_validation']['topic_counts']
    assert all(counts[t] == expected[t] for t in TOPICS), 'Original topic counts differ'
    diagnostic_pairs = Counter((round(r['diagnostic']['source_sample_s'] * 10**6),
                                round(r['diagnostic']['source_publication_s'] * 10**6))
                               for r in diagnostics)
    unmatched = []
    for row in raw:
        key = (row['sample_us'], row['publication_us'])
        if diagnostic_pairs[key]:
            diagnostic_pairs[key] -= 1
        else:
            unmatched.append(row)
    bad_diagnostics = [r for r in diagnostics if not r['diagnostic'].get('accepted')
                       or r['latest_recorded_clock_sim_s'] - r['diagnostic']['receipt_ros_s'] < -.050000001
                       or r['latest_recorded_clock_sim_s'] - r['diagnostic']['receipt_ros_s'] > .500000001]
    anchors = [r['filtered_sequence'] for r in unmatched + bad_phase + bad_diagnostics]
    selected = [r for r in rows if (r['latest_recorded_clock_sim_s'] is not None
                and 83.75 <= r['latest_recorded_clock_sim_s'] <= 84.50)
                or any(abs(r['filtered_sequence'] - a) <= 12 for a in anchors)]
    clocks = [r for r in rows if r['topic'] == '/clock']
    clock_gaps = [{'before': a, 'after': b, 'source_gap_s': b['clock_sim_s'] - a['clock_sim_s'],
                   'record_timestamp_gap_s': (b['bag_record_timestamp_ns'] - a['bag_record_timestamp_ns']) * 1e-9}
                  for a, b in zip(clocks, clocks[1:]) if b['clock_sim_s'] - a['clock_sim_s'] > .020000001]
    with (OUTPUT / 'window_records.jsonl').open('x', encoding='utf-8') as stream:
        for row in selected:
            stream.write(json.dumps(row, allow_nan=False) + '\n')
    after = {str(p): {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in protected}
    assert before == after, 'Original protected bytes changed'
    report = {'kind': 'READONLY_STOPPED51_CLOCK_DIAGNOSTIC_NOT_REGRADING',
              'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
              'elapsed_wall_s': time.monotonic() - tick, 'topic_counts': dict(counts),
              'filtered_records': len(rows), 'selected_records': len(selected),
              'unmatched_raw': unmatched, 'unconsumed_diagnostic_pairs': sum(diagnostic_pairs.values()),
              'bad_diagnostics': bad_diagnostics, 'bad_phase': bad_phase,
              'clock_source_gaps_over_20ms': clock_gaps,
              'protected_before': before, 'protected_after': after,
              'reader': metadata, 'source_unchanged': True,
              'record_timestamp_scope': 'Original recorder timestamps; not mixed with simulation seconds.',
              'tool_sha256': sha(Path(__file__))}
    with (OUTPUT / 'summary.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps({'event': 'READONLY_NATIVE_CLOCK_DIAGNOSTIC_COMPLETED',
                      'records': len(rows), 'unmatched_raw': len(unmatched),
                      'bad_phase': len(bad_phase), 'bad_diagnostics': len(bad_diagnostics),
                      'source_unchanged': True, 'output': str(OUTPUT)}), flush=True)


if __name__ == '__main__':
    main()
