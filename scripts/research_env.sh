#!/usr/bin/env bash
# Offline only: no simulator, ROS node, bag playback, or parameter mutation.
set -eo pipefail
research_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [ -n "${STAGE1_PROJECT_ROOT:-}" ] && \
   [ "$(realpath -m -- "$STAGE1_PROJECT_ROOT")" != "$research_root" ]; then
  echo "STAGE1_PROJECT_ROOT conflicts with this script's project root: $research_root" >&2
  exit 2
fi
source "$research_root/scripts/source_ros_environment.sh"
source "$research_root/ros2_ws/install/setup.bash"
export PYTHONPATH="$research_root:$research_root/scripts:${PYTHONPATH:-}"
exec "${STAGE1_PYTHON_EXECUTABLE:-/usr/bin/python3}" "$@"
