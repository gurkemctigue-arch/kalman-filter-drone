#!/usr/bin/env bash
set -eo pipefail
stage1_project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source /opt/ros/jazzy/setup.bash
source /root/px4_msgs_ws/install/setup.bash
source "$stage1_project/ros2_ws/install/setup.bash"
export PYTHONPATH="$stage1_project:${PYTHONPATH:-}"
exec python3 "$stage1_project/scripts/run_stage1_trial.py" "$@"
