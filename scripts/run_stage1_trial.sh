#!/usr/bin/env bash
set -eo pipefail
stage1_project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$stage1_project/scripts/source_ros_environment.sh"
source "$stage1_project/ros2_ws/install/setup.bash"
export PYTHONPATH="$stage1_project:${PYTHONPATH:-}"
exec "${STAGE1_PYTHON_EXECUTABLE:-/usr/bin/python3}" "$stage1_project/scripts/run_stage1_trial.py" "$@"
