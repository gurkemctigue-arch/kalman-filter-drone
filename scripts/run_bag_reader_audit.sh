#!/usr/bin/env bash
# Read the same installed ROS environment without changing the frozen workspace.
set -eo pipefail
source /opt/ros/jazzy/setup.bash
source /root/uav_tracking_fullplan_v3/ros2_ws/install/setup.bash
exec python3 /mnt/d/基于yolo和卡尔曼滤波/scripts/audit_compressed_rosbag.py "$@"
