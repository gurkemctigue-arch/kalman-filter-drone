#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
set -u
export GZ_PARTITION=assetcheck
export ROS_DOMAIN_ID=73
task_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GZ_SIM_RESOURCE_PATH="$task_repo/ros2_ws/src/uav_tracking_bringup/models"
task_world="${1:-$task_repo/scripts/assetcheck.world.sdf}"
task_results="${ASSETCHECK_OUTPUT:-$task_repo/results/asset_validation}"
task_streams=("${@:2}")
if [ "${#task_streams[@]}" -eq 0 ]; then
  task_streams=(person=/asset/person/image car=/asset/car/image hatchback=/asset/hatchback/image suv=/asset/suv/image)
fi
task_bridges=()
task_validator_args=()
for task_stream in "${task_streams[@]}"; do
  task_bridges+=("${task_stream#*=}@sensor_msgs/msg/Image@gz.msgs.Image")
  task_validator_args+=(--stream "$task_stream")
done
mkdir -p "$task_results"
setsid ros2 run ros_gz_sim gzserver --ros-args -p "world_sdf_file:=$task_world" > "$task_results/gazebo.log" 2>&1 &
task_sim_pid=$!
setsid ros2 run ros_gz_bridge parameter_bridge "${task_bridges[@]}" > "$task_results/bridge.log" 2>&1 &
task_bridge_pid=$!
trap 'kill -- -"$task_bridge_pid" -"$task_sim_pid" 2>/dev/null || true; wait "$task_bridge_pid" "$task_sim_pid" 2>/dev/null || true' EXIT
timeout 90 python3 "$task_repo/scripts/validate_visual_assets.py" --output "$task_results" --weights "$task_repo/models/yolo11n.pt" "${task_validator_args[@]}"
