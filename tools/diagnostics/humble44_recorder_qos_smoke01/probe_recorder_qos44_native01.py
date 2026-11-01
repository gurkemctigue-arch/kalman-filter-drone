"""Single native Humble recorder-profile smoke; synthetic, never flight evidence.

No arguments, no retry, no default-profile comparison, no simulator or inference.
The real CLI consumes the exact main-tree YAML snapshot. Only this process's
five publishers and its own newly created recorder process group are managed.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time


EXTERNAL = Path('/mnt/d/WSL/UAVHumble22-validation')
OUTPUT = EXTERNAL / 'humble44_recorder_qos_native_smoke01'
SOURCE = Path('/mnt/d/基于yolo和卡尔曼滤波/config/recording_qos.yaml')
SOURCE_SHA = 'd56c368ecba5e77a7343a7832be4ec234a4cd4576e367aaa9a808c356cf76824'
SCOPE = 'SMOKE_SYNTHETIC_NOT_FLIGHT_NOT_ROOT_CAUSE'
RECORDER_NAME = 'qos44_smoke_recorder01'
LIMIT = 16 * 1024 * 1024
CLOCK, RAW, TIMING, ODOM, PHASE = ('/clock', '/fmu/out/vehicle_odometry',
                                 '/vehicle/odometry_timing', '/vehicle/odometry', '/tracking/flight_phase')
TOPICS = (CLOCK, RAW, TIMING, ODOM, PHASE)
TYPE_NAMES = {CLOCK: 'rosgraph_msgs/msg/Clock', RAW: 'px4_msgs/msg/VehicleOdometry',
              TIMING: 'std_msgs/msg/String', ODOM: 'nav_msgs/msg/Odometry', PHASE: 'std_msgs/msg/String'}
COUNTS = {CLOCK: 500, RAW: 250, TIMING: 250, ODOM: 250, PHASE: 40}
PERIOD_NS = {CLOCK: 4_000_000, RAW: 8_000_000, TIMING: 8_000_000, ODOM: 8_000_000, PHASE: 50_000_000}
BASE_NS = 10_000_000_000
OWNED = False
RECORDER = None
LOG = None
NODE = None
RCLPY = None
STATE = {'schema_version': 1, 'provenance': {'schema': SCOPE}, 'evidence_scope': SCOPE,
         'started_utc': datetime.now(timezone.utc).isoformat(), 'default_depth_failure_reproduced': False,
         'flight_validated': False, 'root_cause_proven': False, 'original_artifacts_modified': False,
         'requested_signals': []}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def size():
    # Only this fresh, owned smoke directory; never inspect unrelated trees.
    return sum(path.stat().st_size for path in OUTPUT.rglob('*') if path.is_file())


def write_new(name, value):
    data = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
    require(size() + len(data) < LIMIT, 'Owned smoke output exceeds 16 MiB; retain existing bag')
    with (OUTPUT / name).open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def process_stat(pid):
    try:
        text = Path('/proc', str(pid), 'stat').read_text()
    except FileNotFoundError:
        return None
    values = text.rsplit(')', 1)[1].split()
    return {'pid': pid, 'state': values[0], 'ppid': int(values[1]), 'pgid': int(values[2]),
            'session': int(values[3]), 'start_ticks': int(values[19])}


def owned_members():
    if RECORDER is None:
        return []
    identity = STATE.get('recorder_process')
    if identity is None:
        # An interrupt may arrive immediately after Popen returned, before the
        # normal receipt assignment. Recover only a still-verifiable own child.
        leader = process_stat(RECORDER.pid)
        if leader is not None:
            require(leader['ppid'] == os.getpid() and leader['pgid'] == leader['session'] == RECORDER.pid,
                    'Cannot recover ownership of recorder leader')
            identity = leader
            STATE['recorder_process'] = leader
            STATE['recorder_identity_recovered_during_cleanup'] = True
    members = []
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            item = process_stat(int(path.name))
            if item is not None and item['pgid'] == RECORDER.pid:
                require(identity is not None, 'Unobserved recorder leader exited; never signal an unverified residual group')
                require(item['session'] == RECORDER.pid and item['start_ticks'] >= identity['start_ticks'],
                        'Refuse to signal an unowned/reused process group')
                members.append(item)
    return members


def signal_owned(sig):
    members = owned_members()
    if members:
        require(RECORDER.pid != os.getpgrp(), 'Never signal caller process group')
        STATE['requested_signals'].append({'signal': signal.Signals(sig).name, 'utc': utc(), 'members': members})
        try:
            os.killpg(RECORDER.pid, sig)
        except ProcessLookupError:
            pass


def close_recorder():
    if RECORDER is None:
        return
    if RECORDER.poll() is None:
        signal_owned(signal.SIGINT)
        try:
            RECORDER.wait(timeout=12)
        except subprocess.TimeoutExpired:
            signal_owned(signal.SIGTERM)
            try:
                RECORDER.wait(timeout=3)
            except subprocess.TimeoutExpired:
                signal_owned(signal.SIGKILL)
                RECORDER.wait(timeout=3)
    else:
        RECORDER.wait()
    # Any children are still limited to the same owned session/group.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if not owned_members():
            break
        signal_owned(sig)
        deadline = time.monotonic() + 2
        while owned_members() and time.monotonic() < deadline:
            time.sleep(.05)
    STATE['recorder_returncode'] = RECORDER.returncode
    STATE['recorder_residual_processes'] = owned_members()
    STATE['recorder_direct_child_reaped'] = RECORDER.poll() is not None


def graph_snapshot(publishers, profiles):
    result, ready = {}, True
    for topic, publisher in publishers.items():
        infos = NODE.get_subscriptions_info_by_topic(topic)
        actual = []
        for endpoint in infos:
            qos = endpoint.qos_profile
            actual.append({'node_name': endpoint.node_name, 'node_namespace': endpoint.node_namespace,
                           'topic_type': endpoint.topic_type, 'endpoint_gid': list(endpoint.endpoint_gid),
                           'history': qos.history.name, 'depth': qos.depth,
                           'reliability': qos.reliability.name, 'durability': qos.durability.name})
        desired = profiles[topic]
        found = (len(actual) == 1 and actual[0]['node_name'] == RECORDER_NAME
                 and actual[0]['node_namespace'] == '/' and actual[0]['topic_type'] == TYPE_NAMES[topic]
                 and any(actual[0]['endpoint_gid']))
        compatible = found and all(actual[0][key].lower() in (desired[key], 'unknown', 'system_default')
                                   for key in ('reliability', 'durability'))
        matched = publisher.get_subscription_count()
        own_publishers = NODE.count_publishers(topic)
        ready &= found and compatible and matched == 1 and own_publishers == 1
        result[topic] = {'rmw_matched_subscriptions': matched, 'discovered_publishers': own_publishers,
                         'subscriptions': actual, 'known_policy_values_do_not_conflict': compatible,
                         'compatibility_basis': 'Unique typed recorder GID plus actual RMW match; UNKNOWN/SYSTEM_DEFAULT discovery values are preserved, never inferred as an observed depth.'}
    return bool(ready), result


def main():
    global OWNED, RECORDER, LOG, NODE, RCLPY
    require(len(sys.argv) == 1, 'This one-shot smoke has no CLI arguments')
    require(sys.platform == 'linux' and os.environ.get('WSL_DISTRO_NAME') == 'UAVHumble22'
            and os.environ.get('ROS_DISTRO') == 'humble', 'Actual native UAVHumble22/Humble required')
    require(Path(sys.executable) == Path('/root/uav_humble22/venv/bin/python'), 'Use native venv Python')
    require(EXTERNAL.resolve(strict=True) == EXTERNAL and not OUTPUT.exists() and not OUTPUT.is_symlink(),
            'Exclusive fresh external output required; never retry/reuse')
    require(SOURCE.is_file() and not SOURCE.is_symlink() and SOURCE.stat().st_size < 65536
            and sha(SOURCE) == SOURCE_SHA, 'New main-tree recording QoS bytes changed; review before execution')
    STATE['environment'] = {'previous_ROS_DOMAIN_ID': os.environ.get('ROS_DOMAIN_ID'), 'ROS_DOMAIN_ID': '74',
                            'ROS_DISTRO': os.environ['ROS_DISTRO'], 'python': sys.executable,
                            'RMW_IMPLEMENTATION': os.environ.get('RMW_IMPLEMENTATION')}
    os.environ['ROS_DOMAIN_ID'] = '74'
    import yaml
    import rclpy
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
    from rosgraph_msgs.msg import Clock
    from px4_msgs.msg import VehicleOdometry
    from nav_msgs.msg import Odometry
    from std_msgs.msg import String
    RCLPY = rclpy
    classes = {CLOCK: Clock, RAW: VehicleOdometry, TIMING: String, ODOM: Odometry, PHASE: String}
    type_names = TYPE_NAMES
    raw = SOURCE.read_bytes()
    profiles = yaml.safe_load(raw)
    require(set(profiles) == set(TOPICS), 'Exactly five reviewed QoS topics required')
    for topic, profile in profiles.items():
        expected_depth = 2048 if topic == CLOCK else 256 if topic == PHASE else 1024
        require(profile == {'history': 'keep_last', 'depth': expected_depth,
                            'reliability': 'best_effort' if topic == RAW else 'reliable',
                            'durability': 'transient_local' if topic == RAW else 'volatile'},
                'Unexpected requested recorder profile: ' + topic)
    ros2 = shutil.which('ros2')
    require(ros2 is not None and Path(ros2).resolve(strict=True).is_relative_to(Path('/opt/ros/humble')),
            'Native Humble ros2 CLI required')
    OUTPUT.mkdir(mode=0o700)
    OWNED = True
    snapshot = OUTPUT / 'recording_qos.yaml'
    with snapshot.open('xb') as stream:
        stream.write(raw)
    require(sha(snapshot) == sha(SOURCE) == SOURCE_SHA, 'QoS snapshot changed')
    STATE['qos_snapshot'] = {'source': str(SOURCE), 'snapshot': str(snapshot), 'sha256': SOURCE_SHA,
                             'bytes': len(raw), 'requested_profiles': profiles}
    STATE['code'] = {'path': str(Path(__file__).resolve()), 'sha256': sha(__file__)}
    STATE['native_imports'] = {'rclpy': rclpy.__file__, 'rosbag2_py': rosbag2_py.__file__,
                               'ros2_cli': str(Path(ros2).resolve())}
    rclpy.init()
    NODE = rclpy.create_node('qos44_smoke_publishers01', enable_rosout=False,
                            start_parameter_services=False, automatically_declare_parameters_from_overrides=False)
    rclpy.spin_once(NODE, timeout_sec=.2)
    require(all(NODE.count_publishers(topic) == 0 and NODE.count_subscribers(topic) == 0 for topic in TOPICS),
            'Domain 74 already has one of these topic endpoints; do not interfere')
    publishers, writer_profiles = {}, {}
    for topic in TOPICS:
        qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=20 if topic in (TIMING, ODOM) else 10,
                         reliability=ReliabilityPolicy.BEST_EFFORT if topic == RAW else ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL if topic == RAW else DurabilityPolicy.VOLATILE)
        publishers[topic] = NODE.create_publisher(classes[topic], topic, qos)
        writer_profiles[topic] = {'history': qos.history.name, 'depth': qos.depth,
                                  'reliability': qos.reliability.name, 'durability': qos.durability.name}
    STATE['writer_profiles'] = writer_profiles
    command = [ros2, 'bag', 'record', '--storage', 'sqlite3', '--node-name', RECORDER_NAME,
               '--qos-profile-overrides-path', str(snapshot), '-o', str(OUTPUT / 'rosbag'), *TOPICS]
    STATE['recorder_command'] = command
    LOG = (OUTPUT / 'recorder.log').open('xb')
    RECORDER = subprocess.Popen(command, cwd=OUTPUT, stdin=subprocess.DEVNULL, stdout=LOG,
                                stderr=subprocess.STDOUT, start_new_session=True, env=dict(os.environ))
    owner = process_stat(RECORDER.pid)
    require(owner is not None and owner['ppid'] == os.getpid() and owner['pgid'] == owner['session'] == RECORDER.pid,
            'Recorder process group not owned')
    STATE['recorder_process'] = owner
    write_new('started.json', {key: STATE[key] for key in ('schema_version', 'provenance', 'started_utc', 'environment',
                                                        'qos_snapshot', 'code', 'recorder_command', 'recorder_process')})
    deadline, stable_since, previous_signature = time.monotonic() + 30, None, None
    while time.monotonic() < deadline:
        require(RECORDER.poll() is None, 'Recorder exited before discovery completed')
        rclpy.spin_once(NODE, timeout_sec=.05)
        ready, graph = graph_snapshot(publishers, profiles)
        signature = json.dumps(graph, sort_keys=True)
        if ready:
            if signature != previous_signature:
                stable_since = time.monotonic()
            if stable_since is not None and time.monotonic() - stable_since >= 1.:
                break
        else:
            stable_since = None
        previous_signature = signature
    else:
        STATE['last_discovery'] = graph
        raise ValueError('Real compatible recorder matches did not remain stable for one second')
    STATE['stable_recorder_matches'] = {'stable_s': time.monotonic() - stable_since, 'graph': graph,
        'history_depth_scope': 'YAML requested histories are passed verbatim to CLI; graph history/depth are retained where exposed, not inferred when unavailable.'}

    def make_message(topic, index):
        message = classes[topic]()
        stamp_ns = BASE_NS + index * PERIOD_NS[topic]
        if topic == CLOCK:
            message.clock.sec, message.clock.nanosec = divmod(stamp_ns, 1_000_000_000)
        elif topic == RAW:
            message.timestamp_sample = message.timestamp = stamp_ns // 1000
            message.pose_frame = VehicleOdometry.POSE_FRAME_NED
            message.velocity_frame = VehicleOdometry.VELOCITY_FRAME_NED
            message.position = [float(index), .125, -3.]
            message.velocity = [1., 0., 0.]
            message.q = [1., 0., 0., 0.]
        elif topic == ODOM:
            message.header.stamp.sec, message.header.stamp.nanosec = divmod(stamp_ns, 1_000_000_000)
            message.header.frame_id, message.child_frame_id = 'map', 'base_link'
            message.pose.pose.position.x = float(index)
            message.pose.pose.orientation.w = 1.
            message.twist.twist.linear.x = 1.
        elif topic == TIMING:
            message.data = json.dumps({'schema': SCOPE, 'smoke_key': index, 'source_sample_ns': stamp_ns}, separators=(',', ':'))
        else:
            message.data = f'QOS_SMOKE; schema={SCOPE}; smoke_key={index}; source_sim_s={stamp_ns / 1e9:.9f}'
        return message

    events = sorted((index * PERIOD_NS[topic], order, topic, index)
                    for order, topic in enumerate(TOPICS) for index in range(COUNTS[topic]))
    sent = Counter()
    lateness = []
    origin = time.monotonic_ns()
    STATE['publication_started_utc'] = utc()
    for offset, _, topic, index in events:
        require(RECORDER.poll() is None, 'Recorder exited during known sequence')
        while time.monotonic_ns() < origin + offset:
            rclpy.spin_once(NODE, timeout_sec=max(0., min(.001, (origin + offset - time.monotonic_ns()) / 1e9)))
        lateness.append(max(0, time.monotonic_ns() - origin - offset))
        publishers[topic].publish(make_message(topic, index))
        sent[topic] += 1
    while time.monotonic_ns() < origin + 2_000_000_000:
        rclpy.spin_once(NODE, timeout_sec=.001)
    STATE['publication'] = {'requested_duration_s': 2., 'wall_s': (time.monotonic_ns() - origin) / 1e9,
                             'rates_hz': {topic: 1e9 / PERIOD_NS[topic] for topic in TOPICS}, 'sent': dict(sent),
                             'max_scheduler_lateness_s': max(lateness) / 1e9, 'total_messages': sum(sent.values())}
    require(dict(sent) == COUNTS, 'Known publication denominator changed')
    drain_end = time.monotonic() + 1.
    while time.monotonic() < drain_end:
        rclpy.spin_once(NODE, timeout_sec=.01)
    ready, graph_after = graph_snapshot(publishers, profiles)
    STATE['matches_after_drain'] = graph_after
    require(ready, 'Compatible matches changed during known sequence/drain')
    close_recorder()
    require(STATE['recorder_returncode'] == 0 and not STATE['recorder_residual_processes']
            and [item['signal'] for item in STATE['requested_signals']] == ['SIGINT'],
            'Recorder did not close normally after only owned SIGINT')
    LOG.close()
    LOG = None
    require(sha(SOURCE) == sha(snapshot) == SOURCE_SHA, 'Source/snapshot QoS changed during smoke')

    def key_for(topic, message):
        if topic == CLOCK:
            return message.clock.sec * 1_000_000_000 + message.clock.nanosec
        if topic == RAW:
            require(message.timestamp == message.timestamp_sample, 'Synthetic raw sample/publication key differs')
            return int(message.timestamp_sample)
        if topic == ODOM:
            require(message.header.frame_id == 'map' and message.child_frame_id == 'base_link', 'Synthetic odometry frames differ')
            return message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
        if topic == TIMING:
            value = json.loads(message.data)
            require(value.get('schema') == SCOPE and type(value.get('smoke_key')) is int, 'Unexpected synthetic timing payload')
            return value['smoke_key']
        match = re.fullmatch(r'QOS_SMOKE; schema=' + SCOPE + r'; smoke_key=(\d+); source_sim_s=\d+\.\d{9}', message.data)
        require(match is not None, 'Unexpected synthetic phase string')
        return int(match.group(1))

    expected = {topic: Counter(key_for(topic, make_message(topic, index)) for index in range(COUNTS[topic])) for topic in TOPICS}
    observed = {topic: Counter() for topic in TOPICS}
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(OUTPUT / 'rosbag'), storage_id='sqlite3'),
                rosbag2_py.ConverterOptions(input_serialization_format='cdr', output_serialization_format='cdr'))
    actual_types = {entry.name: entry.type for entry in reader.get_all_topics_and_types()}
    require(actual_types == type_names, 'Native bag topic/type set differs from exact five real types')
    while reader.has_next():
        topic, data, _ = reader.read_next()
        message = deserialize_message(data, classes[topic])
        observed[topic][key_for(topic, message)] += 1
    del reader
    comparisons = {}
    for topic in TOPICS:
        comparisons[topic] = {'expected_count': COUNTS[topic], 'observed_count': sum(observed[topic].values()),
            'expected_keys': sorted(expected[topic]), 'observed_keys': sorted(observed[topic]),
            'missing_keys': sorted((expected[topic] - observed[topic]).elements()),
            'unexpected_or_duplicate_keys': sorted((observed[topic] - expected[topic]).elements()),
            'exact_key_multiset_equal': observed[topic] == expected[topic]}
    STATE['native_reader'] = {'reader': 'rosbag2_py.SequentialReader', 'topic_types': actual_types,
                              'comparisons': comparisons, 'full_selected_bag_read': True}
    require(all(item['exact_key_multiset_equal'] for item in comparisons.values()), 'Native per-topic exact count/key comparison failed')
    files = []
    for path in sorted((OUTPUT / 'rosbag').iterdir()):
        require(path.is_file() and not path.is_symlink(), 'Unexpected smoke bag child')
        files.append({'path': str(path.relative_to(OUTPUT)), 'bytes': path.stat().st_size, 'sha256': sha(path)})
    STATE['retained_bag_files'] = files
    STATE['status'] = 'PASS_SYNTHETIC_CLI_PROFILE_AND_KNOWN_STREAMS_ONLY'
    STATE['claim_boundary'] = 'Only exact supplied YAML accepted by actual Humble recorder plus compatible matched writers and this low-volume known sequence. No default-depth failure reproduction, flight validation, source-clock repair, or common root-cause proof.'
    return 0


if __name__ == '__main__':
    exit_code = 2
    try:
        exit_code = main()
    except BaseException as error:
        STATE.update(status='FAIL_SYNTHETIC_SMOKE_ORIGINALS_UNCHANGED', error=type(error).__name__ + ': ' + str(error))
    finally:
        if RECORDER is not None:
            try:
                close_recorder()
            except BaseException as cleanup_error:
                STATE['cleanup_error'] = type(cleanup_error).__name__ + ': ' + str(cleanup_error)
                STATE['status'] = 'FAIL_SYNTHETIC_SMOKE_CLEANUP'
                exit_code = 2
        if LOG is not None:
            LOG.close()
        if NODE is not None:
            try:
                NODE.destroy_node()
            except BaseException as cleanup_error:
                STATE.setdefault('cleanup_errors', {})['destroy_node'] = type(cleanup_error).__name__ + ': ' + str(cleanup_error)
                STATE['status'] = 'FAIL_SYNTHETIC_SMOKE_CLEANUP'
                exit_code = 2
        if RCLPY is not None:
            try:
                if RCLPY.ok():
                    RCLPY.shutdown()
            except BaseException as cleanup_error:
                STATE.setdefault('cleanup_errors', {})['rclpy_shutdown'] = type(cleanup_error).__name__ + ': ' + str(cleanup_error)
                STATE['status'] = 'FAIL_SYNTHETIC_SMOKE_CLEANUP'
                exit_code = 2
        STATE['finished_utc'] = utc()
        if OWNED:
            try:
                write_new('result.json', STATE)
                require(size() < LIMIT, 'Owned smoke output exceeds 16 MiB')
            except BaseException as output_error:
                STATE['status'] = 'FAIL_SYNTHETIC_SMOKE_OUTPUT'
                STATE['error'] = type(output_error).__name__ + ': ' + str(output_error)
                exit_code = 2
        print(json.dumps({'status': STATE.get('status'), 'scope': SCOPE, 'output': str(OUTPUT),
                          'returncode': exit_code, 'error': STATE.get('error')}))
    raise SystemExit(exit_code)
