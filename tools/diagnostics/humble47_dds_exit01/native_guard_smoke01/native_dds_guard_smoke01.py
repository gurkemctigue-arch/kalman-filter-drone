"""Actual three-process DDS contract diagnostic; no Gazebo, PX4 or flight."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

PROJECT = Path('/mnt/d/基于yolo和卡尔曼滤波')
PRODUCTION = Path('/root/uav_tracking_fullplan_v4_humble47')
BASE = Path('/mnt/d/WSL/UAVHumble22-validation/humble47_tf_exit_diagnosis01')
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / 'scripts'))

def launch():
    from launch import LaunchDescription, LaunchService
    from launch_ros.actions import Node
    service = LaunchService(argv=[])
    service.include_launch_description(LaunchDescription([
        Node(package='uav_tracking_bringup', executable='flight_tf',
             parameters=[{'use_sim_time': True, 'camera_mount_mode': 'gimbal'}]),
        Node(package='ros_gz_bridge', executable='parameter_bridge', arguments=[
            '/dds_guard_probe/string@std_msgs/msg/String@gz.msgs.StringMsg',
            '/dds_guard_probe/control@ros_gz_interfaces/srv/ControlWorld']),
    ]))
    return service.run()

def run():
    import run_stage1_trial as trial
    config = PROJECT / 'config/dds_runtime_humble22.json'
    directory = BASE / 'native_guard_smoke01'
    directory.mkdir(exist_ok=False)
    context = trial.prepare_dds_runtime(PRODUCTION, str(config))
    trial.snapshot_dds_runtime(context, directory)
    procs, streams = {}, {}
    report = {'scope': 'THREE_ACTOR_DDS_GUARD_DIAGNOSTIC_NOT_FLIGHT_ACCEPTANCE',
              'production_node_root': str(PRODUCTION), 'guard_source_root': str(PROJECT),
              'explicit_registration': str(config), 'errors': [], 'forced_kills': []}
    def start(name, command):
        streams[name] = (directory / (name + '.log')).open('x', encoding='utf-8')
        procs[name] = subprocess.Popen(command, stdout=streams[name], stderr=subprocess.STDOUT,
            env={**os.environ, 'PYTHONUNBUFFERED': '1'}, start_new_session=True)
    def alive():
        failed = {name: proc.poll() for name, proc in procs.items() if proc.poll() is not None}
        if failed:
            raise RuntimeError('A diagnostic process ended early: ' + str(failed))
    try:
        start('agent', ['/root/uav_humble22/agent_install/bin/MicroXRCEAgent', 'udp4', '-p', '8889'])
        start('ros', [sys.executable, '-B', __file__, 'ros-launch'])
        start('feeder', [sys.executable, '-B', str(BASE / 'probe_actual_flight_tf_teardown02.py'),
                         'feeder', '--min-tf-count', '5'])
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            alive()
            if '"event": "ready"' in (directory / 'feeder.log').read_text(encoding='utf-8'):
                break
            time.sleep(.05)
        else:
            raise TimeoutError('Production TF routes were not observed')
        report['actual'] = trial.capture_owned_dds_runtime(context, directory, procs['ros'].pid,
            procs['agent'].pid, check_alive=alive, timeout_s=8)
        bridge = trial.prepare_ros_gz_runtime(PRODUCTION)
        trial.snapshot_ros_gz_runtime(bridge, directory)
        report['bridge_source_and_closure'] = trial.capture_owned_ros_gz_runtime(bridge, directory,
            procs['ros'].pid, check_alive=alive, timeout_s=8)
    except Exception as exc:
        report['errors'].append(type(exc).__name__ + ':' + str(exc))
    finally:
        for proc in procs.values():
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGINT)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and any(proc.poll() is None for proc in procs.values()):
            time.sleep(.05)
        for name, proc in procs.items():
            if proc.poll() is None:
                report['forced_kills'].append(name)
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
        for stream in streams.values():
            stream.close()
        report['raw_exit_codes'] = {name: proc.returncode for name, proc in procs.items()}
    try:
        trial.verify_dds_runtime_after(context, directory, ros_exit_code=procs['ros'].returncode,
            agent_exit_code=procs['agent'].returncode,
            ros_log=(directory / 'ros.log').read_text(encoding='utf-8'))
    except Exception as exc:
        report['errors'].append(type(exc).__name__ + ':' + str(exc))
    report['claim_limit'] = 'Dependency files and real owned mappings only. No simulated flight, recording or core PASS.'
    report['status'] = 'DIAGNOSTIC_CLOSED' if not report['errors'] and not report['forced_kills'] else 'DIAGNOSTIC_FAILED'
    (directory / 'diagnostic.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'errors': report['errors'],
                      'raw_exit_codes': report['raw_exit_codes'], 'forced_kills': report['forced_kills']}), flush=True)
    return 0 if report['status'] == 'DIAGNOSTIC_CLOSED' else 2

if __name__ == '__main__':
    raise SystemExit(launch() if sys.argv[1:] == ['ros-launch'] else run())
