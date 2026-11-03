#!/usr/bin/env bash
set -euo pipefail
export HUMBLE22_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble54
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export TMPDIR=/tmp STAGE1_TRANSIENT_DIR=/tmp PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
source "$HUMBLE22_PROJECT_ROOT/scripts/humble22_env.sh"
tracking_logger_output=/mnt/d/WSL/UAVHumble22-validation/rcutils_prefix54_actual01
test ! -e "$tracking_logger_output"
mkdir -- "$tracking_logger_output"
set +e
bash "$HUMBLE22_PROJECT_ROOT/scripts/run_research_session.sh" \
 /mnt/d/WSL/UAVHumble22-validation/rcutils_prefix_clock_probe01.py \
 > "$tracking_logger_output/probe.jsonl" 2> "$tracking_logger_output/console.log"
tracking_logger_code=$?
set -e
printf '%s\n' "$tracking_logger_code" > "$tracking_logger_output/probe.exit_code.txt"
exit "$tracking_logger_code"
