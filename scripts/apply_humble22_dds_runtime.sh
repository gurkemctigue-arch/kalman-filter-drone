#!/usr/bin/env bash
# Source after ROS underlays. Bind the declared runtime without shell eval.
tracking_dds_environment_root="${1:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
tracking_dds_environment_registration="$tracking_dds_environment_root/config/dds_runtime_humble22.json"
if [[ "${ROS_DISTRO:-${STAGE1_ROS_DISTRO:-}}" != humble ]]; then
  if [[ -n "${UAV_TRACKING_DDS_RUNTIME_CONFIG:-}" ]]; then
    echo 'The declared Humble DDS runtime requires ROS Humble.' >&2
    return 2 2>/dev/null || exit 2
  fi
  return 0 2>/dev/null || exit 0
fi
if [[ ! -f "$tracking_dds_environment_registration" ]]; then
  if [[ -n "${UAV_TRACKING_DDS_RUNTIME_CONFIG:-}" ]]; then
    echo 'The declared DDS registration is missing from this project root.' >&2
    return 2 2>/dev/null || exit 2
  fi
  return 0 2>/dev/null || exit 0
fi
if [[ -n "${UAV_TRACKING_DDS_RUNTIME_CONFIG:-}" && "$UAV_TRACKING_DDS_RUNTIME_CONFIG" != "$tracking_dds_environment_registration" ]]; then
  echo 'DDS registration must belong to the selected project root.' >&2
  return 2 2>/dev/null || exit 2
fi
if [[ -n "${RMW_IMPLEMENTATION:-}" && "$RMW_IMPLEMENTATION" != rmw_fastrtps_cpp ]]; then
  echo 'The declared DDS runtime requires rmw_fastrtps_cpp.' >&2
  return 2 2>/dev/null || exit 2
fi
tracking_dds_environment_library_path="$(/usr/bin/python3 -B "$tracking_dds_environment_root/scripts/dds_runtime.py" environment \
  --registration "$tracking_dds_environment_registration" --current-library-path "${LD_LIBRARY_PATH:-}")" || { return 2 2>/dev/null || exit 2; }
export LD_LIBRARY_PATH="$tracking_dds_environment_library_path"
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export UAV_TRACKING_DDS_RUNTIME_CONFIG="$tracking_dds_environment_registration"
unset tracking_dds_environment_library_path tracking_dds_environment_registration tracking_dds_environment_root
