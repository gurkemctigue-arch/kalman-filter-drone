#!/usr/bin/env bash
# Run a project Python entry point with the exact installed ROS interfaces.
set -eo pipefail
tracking_project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source /opt/ros/jazzy/setup.bash
source /root/px4_msgs_ws/install/setup.bash
source "$tracking_project/ros2_ws/install/setup.bash"
export PYTHONPATH="$tracking_project:${PYTHONPATH:-}"
cd "$tracking_project"
exec /usr/bin/python3 "$@"
