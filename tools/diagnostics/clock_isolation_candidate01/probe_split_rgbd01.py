"""Bounded two-process bridge smoke with original production RGB-D model.

This is not a flight, not a formal experiment, and not an inference load test.
All new configuration/world copies and evidence live in one external directory.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import signal
import subprocess
import time
import traceback
import xml.etree.ElementTree as ET

from uav_tracking.ros_gz_runtime import verify_live_process, parse_process_stat
from uav_tracking.dds_runtime import verify_loaded_process

ROOT = Path('/root/uav_tracking_fullplan_v4_humble51')
BASE = Path('/mnt/d/WSL/UAVHumble22-validation/clock_isolation_candidate01')
OUT = BASE / 'rgbd_probe01'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def process(pid):
    return parse_process_stat(Path(f'/proc/{pid}/stat').read_text(), pid)


def group_members(group):
    rows = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            row = process(int(entry.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
        except ValueError as exc:
            if 'no longer alive' in str(exc):
                continue
            raise
        if row['process_group'] == group:
            rows.append(row)
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    receipt = {'kind': 'BOUNDED_SPLIT_BRIDGE_PRODUCTION_RGBD_SMOKE', 'status': 'RUNNING',
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'COMPONENT_SMOKE_NO_PX4_NO_YOLO_NO_BAG_NO_FLIGHT_ACCEPTANCE',
        'original_runtime': str(ROOT), 'rtf': 0.125, 'step_s': 0.004,
        'observation_source_s': 20.0, 'camera': {'width': 640, 'height': 480, 'update_rate_hz': 10},
        'claim_limit': 'A bounded component smoke cannot establish the repair of rare clock delivery pauses or flight reliability.'}
    write('receipt.json', receipt)
    owned, logs = {}, []
    node = None
    begin = time.monotonic()
    try:
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():
                continue
            try:
                exe = os.readlink(entry / 'exe')
            except (FileNotFoundError, PermissionError):
                continue
            if Path(exe).name in ('parameter_bridge', 'px4', 'MicroXRCEAgent', 'gz-sim-server'):
                raise RuntimeError('Native simulation/bridge task already running: ' + str(entry))
        source = Path(os.environ['SPLIT_PROBE_CANDIDATE_SOURCE'])
        config = source / 'ros2_ws/src/uav_tracking_bringup/config'
        protected = [ROOT / 'ros2_ws/src/uav_tracking_bringup/worlds/stage3_flight_person.sdf',
                     ROOT / 'ros2_ws/src/uav_tracking_bringup/models/x500_stage3/model.sdf',
                     ROOT / 'config/ros_gz_runtime_humble22.json', ROOT / 'config/dds_runtime_humble22.json',
                     config / 'clock_bridge.yaml', config / 'stage3_data_bridge.yaml']
        before = {str(p): sha(p) for p in protected}
        write('inputs_before.json', before)
        for src, dst in [(config / 'clock_bridge.yaml', OUT / 'clock.yaml'),
                         (config / 'stage3_data_bridge.yaml', OUT / 'data.yaml')]:
            dst.write_bytes(src.read_bytes())
        tree = ET.parse(protected[0])
        tree.find('world/physics/real_time_factor').text = '0.125'
        tree.write(OUT / 'world.sdf', encoding='utf-8', xml_declaration=True)
        env = dict(os.environ)
        model_path = ROOT / 'ros2_ws/install/share/uav_tracking_bringup/models'
        px4 = Path('/root/uav_humble22/PX4-Autopilot-v4mag')
        env.update(GZ_PARTITION='uav_clock_isolation_probe01', GZ_IP='127.0.0.1',
            GZ_SIM_RESOURCE_PATH=str(model_path) + ':' + str(px4 / 'Tools/simulation/gz/models'),
            GZ_SIM_SYSTEM_PLUGIN_PATH=str(px4 / 'build/px4_sitl_default/src/modules/simulation/gz_plugins'),
            LIBGL_ALWAYS_SOFTWARE='1', MESA_LOADER_DRIVER_OVERRIDE='swrast', GALLIUM_DRIVER='llvmpipe',
            OMP_NUM_THREADS='2', LP_NUM_THREADS='4')
        os.environ['GZ_PARTITION'] = env['GZ_PARTITION']
        old_reg = json.loads(protected[2].read_text())
        clock_reg = json.loads((BASE / 'runtime_capture01/ros_gz_clock_runtime_registration.json').read_text())
        exe = old_reg['executable']['real_path']
        commands = {
            'data': [exe, '/world/stage3_flight/set_pose@ros_gz_interfaces/srv/SetEntityPose',
                     '--ros-args', '-r', '__node:=uav_tracking_gz_bridge',
                     '-p', 'config_file:=' + str(OUT / 'data.yaml'), '-p', 'use_sim_time:=true'],
            'clock': [exe, '--ros-args', '-r', '__node:=uav_tracking_clock_bridge',
                      '-p', 'config_file:=' + str(OUT / 'clock.yaml'), '-p', 'use_sim_time:=true'],
            'gazebo': ['gz', 'sim', '--seed', '5', '-s', '-r', '--headless-rendering', str(OUT / 'world.sdf')],
        }
        for role, command in commands.items():
            log = (OUT / (role + '.log')).open('wb')
            logs.append(log)
            child = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
            owned[role] = {'child': child, 'identity': process(child.pid), 'command': command}
        write('owned_processes.json', {role: {k: v for k, v in row.items() if k != 'child'} for role, row in owned.items()})
        time.sleep(1.0)
        dds_path = protected[3]
        for role, reg in [('data', old_reg), ('clock', clock_reg)]:
            row = owned[role]
            if row['child'].poll() is not None:
                raise RuntimeError(role + ' bridge exited before native capture')
            write(role + '_ros_gz_actual.json', verify_live_process(reg, row['identity']['pid'],
                expected_start_ticks=row['identity']['start_ticks'],
                patch_path=ROOT / 'patches/ros_gz_bridge_ownership_shutdown_A01.patch'))
            write(role + '_dds_actual.json', verify_loaded_process(dds_path, row['identity']['pid'],
                role='bridge', expected_process=row['identity'], expected_config_sha256=sha(dds_path)))
        import rclpy
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, qos_profile_sensor_data
        from sensor_msgs.msg import Image, CameraInfo
        from rosgraph_msgs.msg import Clock
        from ros_gz_interfaces.msg import Entity
        from ros_gz_interfaces.srv import SetEntityPose
        rclpy.init()
        node = rclpy.create_node('uav_split_rgbd_probe')
        counts = Counter()
        last = {}
        clock_rows, anomaly_rows = [], []
        shapes = {}
        stamps = {'rgb': set(), 'depth': set(), 'info': set()}
        def on_clock(label, msg):
            now = time.monotonic()
            ns = msg.clock.sec * 10**9 + msg.clock.nanosec
            counts[label] += 1
            previous = last.get(label)
            if previous:
                row = {'topic': label, 'source_ns': ns, 'source_step_ns': ns - previous[0],
                       'wall_gap_s': now - previous[1]}
                clock_rows.append(row)
                if row['source_step_ns'] < 0 or row['wall_gap_s'] > 0.2:
                    anomaly_rows.append(row)
            last[label] = (ns, now)
        def on_image(label, msg):
            counts[label] += 1
            shapes[label] = {'width': msg.width, 'height': msg.height, 'encoding': getattr(msg, 'encoding', None)}
            ns = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
            stamps[label].add(ns)
            if 'clock_reliable' in last:
                excess = ns - last['clock_reliable'][0]
                if excess > 50_000_000:
                    anomaly_rows.append({'topic': label, 'source_ns': ns,
                                         'last_clock_ns': last['clock_reliable'][0], 'future_excess_ns': excess})
        reliable = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE,
                              durability=DurabilityPolicy.VOLATILE)
        image_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE,
                               durability=DurabilityPolicy.VOLATILE)
        timesource_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT,
                                    durability=DurabilityPolicy.VOLATILE)
        subscriptions = [
            node.create_subscription(Clock, '/clock', lambda m: on_clock('clock_reliable', m), reliable),
            node.create_subscription(Clock, '/clock', lambda m: on_clock('clock_best_effort', m), timesource_qos),
            node.create_subscription(Image, '/camera/color/image_raw', lambda m: on_image('rgb', m), image_qos),
            node.create_subscription(Image, '/camera/aligned_depth_to_color/image_raw', lambda m: on_image('depth', m), image_qos),
            node.create_subscription(CameraInfo, '/camera/color/camera_info', lambda m: on_image('info', m), image_qos),
        ]
        client = node.create_client(SetEntityPose, '/world/stage3_flight/set_pose')
        future = None
        first_source = None
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if any(row['child'].poll() is not None for row in owned.values()):
                raise RuntimeError('Owned Gazebo/bridge process exited during observation')
            if future is None and client.service_is_ready():
                request = SetEntityPose.Request()
                request.entity.name, request.entity.type = 'target_person', Entity.MODEL
                request.pose.position.x, request.pose.orientation.w = 5.0, 1.0
                future = client.call_async(request)
            if min((counts[x] for x in ('clock_reliable', 'clock_best_effort', 'rgb', 'depth', 'info')), default=0) >= 3:
                first_source = first_source if first_source is not None else last['clock_reliable'][0]
            if first_source is not None and last['clock_reliable'][0] - first_source >= 20_000_000_000:
                break
        publishers = node.get_publishers_info_by_topic('/clock')
        graph = [{'node_name': p.node_name, 'namespace': p.node_namespace, 'gid': list(p.endpoint_gid),
            'reliability': int(p.qos_profile.reliability), 'durability': int(p.qos_profile.durability),
            'history': int(p.qos_profile.history), 'depth': p.qos_profile.depth} for p in publishers]
        write('clock_publishers.json', graph)
        service_ok = future is not None and future.done() and future.result() is not None and future.result().success
        counts_ok = all(counts[x] >= 100 for x in ('rgb', 'depth', 'info'))
        sync_count = len(stamps['rgb'] & stamps['depth'] & stamps['info'])
        shape_ok = all(shapes.get(x, {}).get('width') == 640 and shapes[x]['height'] == 480 for x in stamps)
        graph_ok = len(graph) == 1 and graph[0]['node_name'] == 'uav_tracking_clock_bridge' and graph[0]['reliability'] == 1
        duration_ok = first_source is not None and last['clock_reliable'][0] - first_source >= 20_000_000_000
        receipt.update(counts=dict(counts), shapes=shapes, synchronized_stamp_count=sync_count,
            service_success=bool(service_ok), unique_clock_publisher=graph_ok,
            observed_source_s=(last.get('clock_reliable', (0,))[0] - (first_source or 0)) / 1e9,
            checks='PASS' if service_ok and counts_ok and shape_ok and graph_ok and duration_ok and sync_count >= 100 else 'FAIL',
            clock_summary={label: {'samples': counts[label],
                'max_callback_wall_gap_s': max((r['wall_gap_s'] for r in clock_rows if r['topic'] == label), default=None),
                'max_source_step_ns': max((r['source_step_ns'] for r in clock_rows if r['topic'] == label), default=None)}
                for label in ('clock_reliable', 'clock_best_effort')},
            delivery_anomaly_count=len(anomaly_rows),
            graph_history_depth_claim='UNKNOWN_RMW_GRAPH_VALUES_ARE_NOT_ACTUAL_PUBLISHER_QUEUE_DEPTH')
        write('delivery_observations.json', {'anomalies': anomaly_rows, 'clock_summary': receipt['clock_summary']})
        after = {str(p): sha(p) for p in protected}
        write('inputs_after.json', after)
        if after != before:
            raise RuntimeError('Original or candidate probe inputs changed during native observation')
    except Exception as exc:
        receipt.update(checks='FAIL', error=str(exc), traceback=traceback.format_exc())
    finally:
        if node is not None:
            node.destroy_node()
            rclpy.shutdown()
        cleanup = {}
        for role in ('data', 'clock', 'gazebo'):
            if role not in owned:
                continue
            row = owned[role]
            child = row['child']
            forced = False
            if child.poll() is None:
                if process(child.pid) != row['identity']:
                    raise RuntimeError('Owned identity changed before cleanup')
                os.killpg(row['identity']['process_group'], signal.SIGINT)
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    forced = True
                    os.killpg(row['identity']['process_group'], signal.SIGTERM)
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(row['identity']['process_group'], signal.SIGKILL)
                        child.wait(timeout=5)
            cleanup[role] = {'exit_code': child.returncode, 'forced': forced,
                             'direct_child_reaped': child.poll() is not None,
                             'residual_group_members': group_members(row['identity']['process_group'])}
        for log in logs:
            log.close()
        receipt['cleanup'] = cleanup
        receipt['status'] = ('PASS' if receipt.get('checks') == 'PASS' and len(cleanup) == 3
            and all(r['exit_code'] == 0 and not r['forced'] and r['direct_child_reaped']
                    and not r['residual_group_members'] for r in cleanup.values()) else 'FAIL')
        receipt['duration_wall_s'] = time.monotonic() - begin
        receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
        write('receipt.json', receipt)
        print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
