#!/usr/bin/env bash
set -eo pipefail
[[ ( $# == 1 || $# == 2 || $# == 3 ) && ( "$1" == current2048 || "$1" == candidate1 ) ]] || exit 2
tracking_recorder_pause="${2:-0.6}"
tracking_producer_depth="${3:-10}"
case "$tracking_producer_depth" in
  10) tracking_proxy_tag= ;;
  1024) tracking_proxy_tag=_proxy1024 ;;
  *) exit 2 ;;
esac
case "$tracking_recorder_pause" in
  0.6) tracking_pause_tag=06 ;;
  1|1.0) tracking_pause_tag=10 ;;
  *) exit 2 ;;
esac
[[ "${WSL_DISTRO_NAME:-}" == UAVHumble22 ]] || exit 2
export HUMBLE22_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble53
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
source "$HUMBLE22_PROJECT_ROOT/scripts/humble22_env.sh"
export TMPDIR=/tmp PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
mkdir -p /root/uav_tracking_bag_spool/recorder_clock_candidate01
exec /root/uav_humble22/venv/bin/python -B \
  /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/recorder_clock_candidate01/probe_recorder_clock.py run \
  --source-root "$HUMBLE22_PROJECT_ROOT" \
  --base-probe /mnt/d/基于yolo和卡尔曼滤波/tools/diagnostics/clock_isolation_candidate01/probe_split_rgbd01.py \
  --condition "$1" \
  --output "/root/uav_tracking_bag_spool/recorder_clock_candidate01/${1}_pause${tracking_pause_tag}${tracking_proxy_tag}_01" \
  --stress-recorder-pause-wall-s "$tracking_recorder_pause" \
  --producer-evidence-depth "$tracking_producer_depth"
