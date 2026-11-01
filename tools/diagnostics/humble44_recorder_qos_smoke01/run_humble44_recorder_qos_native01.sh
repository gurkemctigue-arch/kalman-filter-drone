#!/usr/bin/env bash
set -euo pipefail
export HUMBLE22_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble43
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
source "$HUMBLE22_PROJECT_ROOT/scripts/humble22_env.sh"
export TMPDIR=/root/uav_humble22/native_causal_cache
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
tracking44_probe=/mnt/d/WSL/UAVHumble22-validation/probe_recorder_qos44_native01.py
tracking44_actual=$(sha256sum -- "$tracking44_probe")
test "${tracking44_actual%% *}" = d3794f9952febcf304a0488d4075e89f3e7af5ad215c5236a023a8184458375d
exec /root/uav_humble22/venv/bin/python -B "$tracking44_probe"
