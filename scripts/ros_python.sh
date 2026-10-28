#!/usr/bin/env bash
# Run a project Python entry point with the exact installed ROS interfaces.
set -eo pipefail
tracking_project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$tracking_project/scripts/source_ros_environment.sh"
source "$tracking_project/ros2_ws/install/setup.bash"
export PYTHONPATH="$tracking_project:${PYTHONPATH:-}"
cd "$tracking_project"
exec "${STAGE1_PYTHON_EXECUTABLE:-/usr/bin/python3}" "$@"
