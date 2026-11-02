#!/usr/bin/env bash
# Scope logs to results; retain an explicitly selected native temporary store.
# Use for both the primary matrix and the independent engineering extension.
set -eo pipefail
tracking_project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tracking_runtime="$tracking_project/results/runtime"
tracking_transient="${STAGE1_TRANSIENT_DIR:-${TMPDIR:-$tracking_runtime/tmp}}"
if [[ "$tracking_transient" != /* ]]; then
  echo 'Select an absolute temporary directory with STAGE1_TRANSIENT_DIR or TMPDIR.' >&2
  exit 2
fi
mkdir -p "$tracking_transient" "$tracking_runtime/ros_logs"
export TMPDIR="$tracking_transient"
export ROS_LOG_DIR="$tracking_runtime/ros_logs"
exec bash "$tracking_project/scripts/ros_python.sh" "$@"
