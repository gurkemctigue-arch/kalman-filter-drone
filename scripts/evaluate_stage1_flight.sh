#!/usr/bin/env bash
# Read-only offline evaluation: no ROS node, bag playback or simulator.
set -eo pipefail
stage1_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
stage1_project="$(cd -- "$stage1_script_dir/.." && pwd -P)"
if [ -n "${STAGE1_PROJECT_ROOT:-}" ] && \
   [ "$(realpath -m -- "$STAGE1_PROJECT_ROOT")" != "$stage1_project" ]; then
  echo "STAGE1_PROJECT_ROOT conflicts with this script's project root: $stage1_project" >&2
  exit 2
fi
stage1_ros_distro="${STAGE1_ROS_DISTRO:-${ROS_DISTRO:-jazzy}}"
source "/opt/ros/$stage1_ros_distro/setup.bash"
source "${STAGE1_PX4_MSGS_WS:-/root/px4_msgs_ws}/install/setup.bash"
source "$stage1_project/ros2_ws/install/setup.bash"
export PYTHONPATH="$stage1_project:$stage1_project/scripts:${PYTHONPATH:-}"
exec python3 "$stage1_script_dir/evaluate_stage1_flight.py" "$@"
