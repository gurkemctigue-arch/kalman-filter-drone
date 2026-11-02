"""Owned clock-only ELF/DDS mapping probe; no simulator, flight or bag access."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import signal
import subprocess
import time
import traceback

from uav_tracking.ros_gz_runtime import (
    create_registration, verify_registration, verify_live_process, parse_process_stat,
)
from uav_tracking.dds_runtime import verify_loaded_process

ROOT = Path('/root/uav_tracking_fullplan_v4_humble51')
OVERLAY = Path('/root/uav_humble22/ros_gz_shutdown_A01_ws')
OUT = Path('/mnt/d/WSL/UAVHumble22-validation/clock_isolation_candidate01/runtime_capture01')


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def identity(pid):
    return parse_process_stat(Path(f'/proc/{pid}/stat').read_text(), pid)


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    begin = time.monotonic()
    receipt = {'kind': 'OWNED_CLOCK_ONLY_NATIVE_CAPTURE', 'status': 'RUNNING',
               'started_utc': datetime.now(timezone.utc).isoformat(),
               'claim_limit': 'Standalone clock-only executable/dependency/DDS mapping and owned shutdown only; no Gazebo delivery or flight reliability claim.'}
    write('receipt.json', receipt)
    child = None
    child_identity = None
    forced = False
    log = (OUT / 'clock.log').open('wb')
    try:
        active = []
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                exe = os.readlink(proc / 'exe')
            except (FileNotFoundError, PermissionError):
                continue
            if Path(exe).name in ('parameter_bridge', 'px4', 'MicroXRCEAgent', 'gz-sim-server'):
                active.append({'pid': int(proc.name), 'exe': exe})
        write('preexisting_native_processes.json', active)
        if active:
            raise RuntimeError('Exclusive native probe refused: simulator/bridge/agent already active')
        old = json.loads((ROOT / 'config/ros_gz_runtime_humble22.json').read_text())
        patch = ROOT / 'patches/ros_gz_bridge_ownership_shutdown_A01.patch'
        reg = create_registration(OVERLAY, OVERLAY / 'src/ros_gz', patch_path=patch,
                                  expected_commit=old['source']['commit'], plugin_elf_paths=())
        write('ros_gz_clock_runtime_registration.json', reg)
        write('ros_gz_clock_preflight.json', verify_registration(reg, patch_path=patch))
        cmd = [reg['executable']['real_path'], '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
               '--ros-args', '-r', '__node:=uav_tracking_clock_bridge', '-p', 'use_sim_time:=true']
        child = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        child_identity = identity(child.pid)
        if child_identity['parent_pid'] != os.getpid():
            raise RuntimeError('Bridge is not an owned direct child')
        write('owned_process.json', {'command': cmd, 'owner': identity(os.getpid()), 'process': child_identity})
        time.sleep(0.75)
        if child.poll() is not None:
            raise RuntimeError(f'Clock-only bridge exited early: {child.returncode}')
        write('ros_gz_clock_runtime_actual.json', verify_live_process(
            reg, child.pid, expected_start_ticks=child_identity['start_ticks'], patch_path=patch))
        dds_path = ROOT / 'config/dds_runtime_humble22.json'
        write('dds_clock_runtime_actual.json', verify_loaded_process(dds_path, child.pid,
            role='bridge', expected_process=child_identity,
            expected_config_sha256=hashlib.sha256(dds_path.read_bytes()).hexdigest()))
        # Graph evidence describes actual endpoints and QoS, even without GZ clock samples.
        import rclpy
        rclpy.init()
        node = rclpy.create_node('uav_clock_capture_observer')
        try:
            deadline = time.monotonic() + 12.0
            endpoints = []
            while time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=0.2)
                endpoints = node.get_publishers_info_by_topic('/clock')
                if endpoints:
                    break
            rows = [{'node_name': p.node_name, 'node_namespace': p.node_namespace,
                     'topic_type': p.topic_type, 'gid': list(p.endpoint_gid),
                     'reliability': int(p.qos_profile.reliability),
                     'durability': int(p.qos_profile.durability),
                     'history': int(p.qos_profile.history), 'depth': p.qos_profile.depth}
                    for p in endpoints]
            write('clock_publishers.json', rows)
            if len(rows) != 1 or rows[0]['node_name'] != 'uav_tracking_clock_bridge':
                raise RuntimeError('Actual /clock publisher count or node identity is not unique')
            if rows[0]['depth'] != 10 or rows[0]['reliability'] != 1:
                raise RuntimeError('Clock publisher QoS differs from unchanged reliable depth10 contract')
        finally:
            node.destroy_node()
            rclpy.shutdown()
        receipt['checks'] = 'PASS'
    except Exception as exc:
        receipt['checks'] = 'FAIL'
        receipt['error'] = str(exc)
        receipt['traceback'] = traceback.format_exc()
    finally:
        if child is not None:
            if child.poll() is None:
                if identity(child.pid) != child_identity:
                    raise RuntimeError('Owned child identity changed before shutdown')
                child.send_signal(signal.SIGINT)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    forced = True
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
            receipt['child_exit_code'] = child.returncode
            receipt['child_reaped'] = child.poll() is not None
            receipt['owned_pid_absent_after_reap'] = not Path(f'/proc/{child.pid}').exists()
        log.close()
        receipt['forced_termination'] = forced
        receipt['status'] = ('PASS' if receipt.get('checks') == 'PASS' and not forced
                             and receipt.get('child_exit_code') == 0
                             and receipt.get('owned_pid_absent_after_reap') else 'FAIL')
        receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
        receipt['duration_wall_s'] = time.monotonic() - begin
        write('receipt.json', receipt)
        print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
