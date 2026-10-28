#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
task_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$task_repo/scripts/compare_car_detectors.py" \
  --bag /root/uav_tracking_project/results/car_flight_v01/rosbag \
  --output "$task_repo/results/car_detector_comparison" \
  --weights "$task_repo/models/yolo11n.pt" "$task_repo/models/yolo11s.pt" \
  --views "$task_repo/results/asset_validation/flight_viewpoints" "$@"
