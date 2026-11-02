"""Real runtime wrappers plus real DDS preflight; no flight or real Agent."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

source = Path('/mnt/d/基于yolo和卡尔曼滤波')
fixture = Path('/root/uav_humble22/dds_wrapper_order_actual02')
output = Path('/mnt/d/WSL/UAVHumble22-validation/humble47_tf_exit_diagnosis01/wrapper_order_actual02')
fixture.mkdir(exist_ok=False)
output.mkdir(exist_ok=False)
names = ['scripts/ros_python.sh', 'scripts/run_stage1_flight.sh', 'scripts/source_ros_environment.sh',
         'scripts/apply_humble22_dds_runtime.sh', 'scripts/dds_runtime.py',
         'uav_tracking/__init__.py', 'uav_tracking/dds_runtime.py', 'uav_tracking/ros_gz_runtime.py',
         'config/dds_runtime_humble22.json']
inputs = {}
for name in names:
    raw = (source / name).read_bytes()
    target = fixture / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    inputs[name] = hashlib.sha256(raw).hexdigest()
(fixture / 'ros2_ws').mkdir()
(fixture / 'ros2_ws/install').symlink_to('/root/uav_tracking_fullplan_v4_humble47/ros2_ws/install', target_is_directory=True)
checker = fixture / 'check_real_preflight.py'
checker.write_text('''import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from uav_tracking.dds_runtime import preflight
report=preflight(os.environ["UAV_TRACKING_DDS_RUNTIME_CONFIG"])
print(json.dumps({"status":report["status"],"ld_prefix":os.environ["LD_LIBRARY_PATH"].split(":")[:2],"registration":report["registration_path"]}))
''', encoding='utf-8')
fakebin = fixture / 'fakebin'
fakebin.mkdir()
agent = fakebin / 'MicroXRCEAgent'
agent.write_text('#!/usr/bin/env bash\nexec /root/uav_humble22/venv/bin/python -B "' + str(checker) + '"\n', encoding='utf-8')
agent.chmod(0o755)
environment = {key: value for key, value in os.environ.items() if key not in {
    'AMENT_PREFIX_PATH', 'COLCON_PREFIX_PATH', 'CMAKE_PREFIX_PATH', 'PYTHONPATH', 'PYTHONHOME',
    'LD_LIBRARY_PATH', 'ROS_DISTRO', 'UAV_TRACKING_DDS_RUNTIME_CONFIG', 'RMW_IMPLEMENTATION'}}
environment.update(PATH=str(fakebin) + ':/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
    STAGE1_PROJECT_ROOT=str(fixture), STAGE1_ROS_DISTRO='humble',
    STAGE1_PX4_MSGS_WS='/root/uav_humble22/px4_msgs_ws',
    STAGE1_ROS_GZ_WS='/root/uav_humble22/ros_gz_shutdown_A01_ws',
    STAGE1_PYTHON_EXECUTABLE='/root/uav_humble22/venv/bin/python', PYTHONDONTWRITEBYTECODE='1')
cases = []
for name, command in [
    ('parent_ros_python', ['bash', str(fixture / 'scripts/ros_python.sh'), '-B', str(checker)]),
    ('component_wrapper_fake_agent', ['bash', str(fixture / 'scripts/run_stage1_flight.sh'), 'agent', 'person']),
]:
    result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=45)
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    clean = result.returncode == 0 and len(rows) == 1 and rows[0]['status'] == 'PASS'
    cases.append({'name': name, 'argv': command, 'returncode': result.returncode,
                  'stdout': result.stdout, 'stderr': result.stderr, 'actual_real_preflight_passed': clean})
report = {'scope': 'REAL_WRAPPERS_REAL_DDS_PREFLIGHT_WITH_EXISTING_MERGE_INSTALL_AND_FAKE_ENDPOINT_NOT_FLIGHT',
          'input_source_sha256': inputs, 'cases': cases,
          'status': 'PASS' if all(case['actual_real_preflight_passed'] for case in cases) else 'FAIL',
          'claim_limit': 'The actual production wrapper bytes are copied into a thin fixture. Existing immutable47 setup provides real colcon prepend behavior. The Agent executable is replaced by a real library-file preflight; no Agent, Gazebo, PX4 or flight starts.'}
(output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2))
raise SystemExit(0 if report['status'] == 'PASS' else 2)
