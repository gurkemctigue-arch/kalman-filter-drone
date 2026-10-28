#!/usr/bin/env bash
# Read-only debugger for bridge construction failures; does not start a world.
set -eo pipefail
source /opt/ros/jazzy/setup.bash
source /root/px4_msgs_ws/install/setup.bash
source /root/uav_tracking_project/ros2_ws/install/setup.bash
export GZ_PARTITION=stage1_flight GZ_IP=127.0.0.1 ROS_DOMAIN_ID=0
exec timeout -s INT 25 gdb -batch -ex run -ex 'thread apply all bt 10' --args \
  /opt/ros/jazzy/lib/ros_gz_bridge/parameter_bridge \
  /world/stage2_flight/set_pose@ros_gz_interfaces/srv/SetEntityPose \
  --ros-args -p use_sim_time:=true \
  -p config_file:=/root/uav_tracking_project/ros2_ws/src/uav_tracking_bringup/config/stage2_bridge.yaml
