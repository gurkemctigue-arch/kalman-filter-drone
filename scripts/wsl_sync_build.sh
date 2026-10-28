#!/usr/bin/env bash
set -eo pipefail
stage1_source="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
stage1_dest=/root/uav_tracking_project
# This preserves installed/build artifacts and previous experiment evidence.
rsync -a --exclude='__pycache__' --exclude='.pytest_cache' --exclude='results/' \
  --exclude='ros2_ws/build/' --exclude='ros2_ws/install/' --exclude='ros2_ws/log/' \
  "$stage1_source/" "$stage1_dest/"
source /opt/ros/jazzy/setup.bash
source /root/px4_msgs_ws/install/setup.bash
export PYTHONPATH="$stage1_dest:${PYTHONPATH:-}"
cd "$stage1_dest/ros2_ws"
colcon build --merge-install --symlink-install
