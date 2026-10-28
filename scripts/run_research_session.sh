#!/usr/bin/env bash
# Scope large transient files and ROS logs to this study's results storage.
# Use for both the primary matrix and the independent engineering extension.
set -eo pipefail
tracking_project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tracking_runtime="$tracking_project/results/runtime"
mkdir -p "$tracking_runtime/tmp" "$tracking_runtime/ros_logs"
export TMPDIR="$tracking_runtime/tmp"
export ROS_LOG_DIR="$tracking_runtime/ros_logs"
exec bash "$tracking_project/scripts/ros_python.sh" "$@"
