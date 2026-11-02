#!/usr/bin/env bash
# Read a stopped recording with its own installed message types; no ROS nodes.
set -eo pipefail
[[ "${WSL_DISTRO_NAME:-}" == UAVHumble22 ]] || exit 2
export HUMBLE22_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble53
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
source "$HUMBLE22_PROJECT_ROOT/scripts/humble22_env.sh"
export TMPDIR=/tmp PYTHONDONTWRITEBYTECODE=1
exec /root/uav_humble22/venv/bin/python -B \
  /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/humble53_clock_window01/extract_clock_window.py \
  --root "$HUMBLE22_PROJECT_ROOT" \
  --trial "$HUMBLE22_PROJECT_ROOT/results/reliability_v4_humble53_probe01_car_stage1_position_seed004" \
  --output /mnt/d/WSL/UAVHumble22-validation/candidate53_clock_raw01 \
  --cache-parent /tmp
