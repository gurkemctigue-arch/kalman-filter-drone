#!/usr/bin/env bash
set -euo pipefail
export HUMBLE22_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble54
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export TMPDIR=/tmp STAGE1_TRANSIENT_DIR=/tmp PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
source "$HUMBLE22_PROJECT_ROOT/scripts/humble22_env.sh"
tracking_repair_log=/mnt/d/WSL/UAVHumble22-validation/safety54_schema_recovery03.log
test ! -e "$tracking_repair_log"
set +e
/root/uav_humble22/venv/bin/python -B /mnt/d/WSL/UAVHumble22-validation/safety54_schema_recovery03.py > "$tracking_repair_log" 2>&1
tracking_repair_code=$?
set -e
cat "$tracking_repair_log"
exit "$tracking_repair_code"
