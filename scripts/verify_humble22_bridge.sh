#!/usr/bin/env bash
# Independent small RGB-D/clock/service integration gate; no PX4 or inference.
set -euo pipefail
if [[ "${WSL_DISTRO_NAME:-}" != UAVHumble22 ]]; then
  echo 'Run only inside isolated WSL UAVHumble22.' >&2; exit 2
fi
# This independent gate uses standard sensor/clock messages and ros_gz only;
# it must not require an unbuilt project overlay or silently ignore one.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH
unset CMAKE_MODULE_PATH CPATH CPLUS_INCLUDE_PATH C_INCLUDE_PATH LIBRARY_PATH PKG_CONFIG_PATH
set +u
source /opt/ros/humble/setup.bash
source /root/uav_humble22/venv/bin/activate
source /root/uav_humble22/ros_gz_ws/install/setup.bash
set -u
export GZ_VERSION=harmonic IGNITION_VERSION=''
humble22_output="/root/uav_humble22/logs/bridge_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$humble22_output"
export HUMBLE22_BRIDGE_OUTPUT="$humble22_output"
export ROS_DOMAIN_ID=73 GZ_PARTITION="uav_humble22_bridge_$$" GZ_IP=127.0.0.1
cat > "$humble22_output/world.sdf" <<'SDF'
<?xml version="1.0"?>
<sdf version="1.9"><world name="humble_validation">
  <physics name="physics" type="ignored"><max_step_size>0.004</max_step_size><real_time_factor>0.5</real_time_factor></physics>
  <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
  <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
  <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>
  <scene><ambient>1 1 1 1</ambient><background>0.1 0.1 0.1 1</background></scene>
  <model name="camera"><static>true</static><pose>0 0 1 0 0 0</pose><link name="camera_link">
    <sensor name="rgbd" type="rgbd_camera"><always_on>true</always_on><update_rate>5</update_rate><topic>/humble22/rgbd</topic>
      <camera><horizontal_fov>1.047</horizontal_fov><image><width>160</width><height>120</height><format>R8G8B8</format></image>
        <clip><near>0.1</near><far>20</far></clip><depth_camera><clip><near>0.1</near><far>20</far></clip></depth_camera>
      </camera>
    </sensor>
  </link></model>
  <model name="validation_box"><static>true</static><pose>3 0 1 0 0 0</pose><link name="link">
    <collision name="collision"><geometry><box><size>1.5 1.5 1.5</size></box></geometry></collision>
    <visual name="visual"><geometry><box><size>1.5 1.5 1.5</size></box></geometry><material><ambient>0.9 0.1 0.1 1</ambient><diffuse>0.9 0.1 0.1 1</diffuse></material></visual>
  </link></model>
</world></sdf>
SDF
cat > "$humble22_output/bridge.yaml" <<'YAML'
- ros_topic_name: /clock
  gz_topic_name: /world/humble_validation/clock
  ros_type_name: rosgraph_msgs/msg/Clock
  gz_type_name: gz.msgs.Clock
  direction: GZ_TO_ROS
- ros_topic_name: /humble22/rgb
  gz_topic_name: /humble22/rgbd/image
  ros_type_name: sensor_msgs/msg/Image
  gz_type_name: gz.msgs.Image
  direction: GZ_TO_ROS
- ros_topic_name: /humble22/depth
  gz_topic_name: /humble22/rgbd/depth_image
  ros_type_name: sensor_msgs/msg/Image
  gz_type_name: gz.msgs.Image
  direction: GZ_TO_ROS
- ros_topic_name: /humble22/camera_info
  gz_topic_name: /humble22/rgbd/camera_info
  ros_type_name: sensor_msgs/msg/CameraInfo
  gz_type_name: gz.msgs.CameraInfo
  direction: GZ_TO_ROS
YAML
humble22_pids=()
humble22_cleanup() {
  local pid retry still_running
  for pid in "${humble22_pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done
  for retry in {1..40}; do
    still_running=false
    for pid in "${humble22_pids[@]}"; do
      if kill -0 -- "-$pid" 2>/dev/null; then still_running=true; fi
    done
    if ! "$still_running"; then break; fi
    sleep 0.1
  done
  for pid in "${humble22_pids[@]}"; do kill -KILL -- "-$pid" 2>/dev/null || true; done
  for pid in "${humble22_pids[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap humble22_cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
setsid gz sim -s -r --headless-rendering "$humble22_output/world.sdf" > "$humble22_output/gazebo.log" 2>&1 &
humble22_pids+=("$!")
setsid ros2 run ros_gz_bridge parameter_bridge \
  '/world/humble_validation/set_pose@ros_gz_interfaces/srv/SetEntityPose' \
  --ros-args -p "config_file:=$humble22_output/bridge.yaml" > "$humble22_output/bridge.log" 2>&1 &
humble22_pids+=("$!")
python -B - <<'PY'
from collections import Counter
import json
import os
from pathlib import Path
import time
import numpy as np
import rclpy
from rclpy.qos import qos_profile_sensor_data
from cv_bridge import CvBridge
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import CameraInfo, Image
from ros_gz_interfaces.msg import Entity
from ros_gz_interfaces.srv import SetEntityPose

rclpy.init()
node = rclpy.create_node('humble22_rgbd_bridge_probe')
counts = Counter()
stamps = {'rgb': set(), 'depth': set(), 'info': set()}
latest = {}
def stamp(msg):
    return msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
def receive(name, msg):
    counts[name] += 1
    latest[name] = msg
    if name in stamps:
        stamps[name].add(stamp(msg))
subscriptions = [
    node.create_subscription(Clock, '/clock', lambda m: receive('clock', m), qos_profile_sensor_data),
    node.create_subscription(Image, '/humble22/rgb', lambda m: receive('rgb', m), qos_profile_sensor_data),
    node.create_subscription(Image, '/humble22/depth', lambda m: receive('depth', m), qos_profile_sensor_data),
    node.create_subscription(CameraInfo, '/humble22/camera_info', lambda m: receive('info', m), qos_profile_sensor_data),
]
client = node.create_client(SetEntityPose, '/world/humble_validation/set_pose')
future = None
deadline = time.monotonic() + 45
passed = False
depth_ratio = 0.0
result = {'schema_version': 1, 'ros_distro': os.environ.get('ROS_DISTRO'), 'status': 'FAIL'}
try:
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
        if future is None and client.service_is_ready():
            request = SetEntityPose.Request()
            request.entity.name, request.entity.type = 'validation_box', Entity.MODEL
            request.pose.position.x, request.pose.position.z = 3.5, 1.0
            request.pose.orientation.w = 1.0
            future = client.call_async(request)
        synced = stamps['rgb'] & stamps['depth'] & stamps['info']
        if future is None or not future.done() or not synced or min(counts.values(), default=0) < 3:
            continue
        response = future.result()
        if response is None or not response.success:
            raise RuntimeError('SetEntityPose returned no success')
        rgb = CvBridge().imgmsg_to_cv2(latest['rgb'], desired_encoding='rgb8')
        depth = CvBridge().imgmsg_to_cv2(latest['depth'], desired_encoding='passthrough')
        info = latest['info']
        valid = np.isfinite(depth) & (depth > 0) & (depth < 20)
        depth_ratio = float(valid.mean())
        passed = (counts['clock'] >= 3 and rgb.shape == (120, 160, 3)
                  and depth.shape == (120, 160) and info.width == 160 and info.height == 120
                  and info.k[0] > 0 and depth_ratio > 0.05 and max(synced) > 0)
        if passed:
            result.update(status='PASS', synchronized_frames=len(synced), rgb_shape=list(rgb.shape),
                          depth_shape=list(depth.shape), depth_encoding=latest['depth'].encoding,
                          depth_valid_fraction=depth_ratio, depth_median_m=float(np.median(depth[valid])),
                          set_entity_pose_success=True, latest_synchronized_stamp_ns=max(synced))
            break
    if not passed:
        result['reason'] = 'Timed out waiting for clock, synchronized RGB-D/CameraInfo, and successful SetEntityPose'
except Exception as exc:
    result['reason'] = f'{type(exc).__name__}: {exc}'
finally:
    result['received'] = dict(counts)
    output = Path(os.environ['HUMBLE22_BRIDGE_OUTPUT']) / 'bridge_smoke.json'
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    node.destroy_node()
    rclpy.shutdown()
if not passed:
    raise SystemExit(1)
PY
echo "RGB-D/service bridge gate passed: $humble22_output/bridge_smoke.json"
