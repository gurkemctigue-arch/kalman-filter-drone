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
cd "$HUMBLE22_PROJECT_ROOT"
exec /root/uav_humble22/venv/bin/python -B /mnt/d/WSL/UAVHumble22-validation/diagnose_humble43_extension_clock_boundary01.py
