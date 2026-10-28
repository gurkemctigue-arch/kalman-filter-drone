#!/usr/bin/env bash
# Component checks supplement recorded flights; they do not certify flight by themselves.
set -eo pipefail
stage1_project="${STAGE1_PROJECT_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
source /opt/ros/jazzy/setup.bash
source /root/px4_msgs_ws/install/setup.bash
source "$stage1_project/ros2_ws/install/setup.bash"
export PYTHONPATH="$stage1_project:${PYTHONPATH:-}"
cd "$stage1_project"
python3 -m unittest discover -s tests -p 'test*.py' -v
python3 -m compileall -q uav_tracking ros2_ws/src scripts launch tests
