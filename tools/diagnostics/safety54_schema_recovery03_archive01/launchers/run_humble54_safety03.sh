#!/usr/bin/env bash
set -euo pipefail
export HUMBLE22_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble54
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export TMPDIR=/tmp STAGE1_TRANSIENT_DIR=/tmp PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
source "$HUMBLE22_PROJECT_ROOT/scripts/humble22_env.sh"
test "$#" = 1
exec /root/uav_humble22/venv/bin/python -B \
 /root/uav_tracking_snapshot_audit54_tools01/tools/run_reliability_v4_safety.py run \
 --registry "$HUMBLE22_PROJECT_ROOT/results/reliability_v4_humble54_safety03_audit/registry.json" \
 --registry-sha256 "$1"
