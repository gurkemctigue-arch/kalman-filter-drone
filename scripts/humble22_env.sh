#!/usr/bin/env bash
# Source only in the independently imported UAVHumble22 distribution.
if [[ "${WSL_DISTRO_NAME:-}" != UAVHumble22 ]]; then
  echo 'This environment belongs exclusively to WSL UAVHumble22.' >&2
  return 2 2>/dev/null || exit 2
fi
if [[ -n "${ROS_DISTRO:-}" && "$ROS_DISTRO" != humble ]]; then
  echo 'Start a clean shell; a different ROS distribution is already sourced.' >&2
  return 2 2>/dev/null || exit 2
fi
humble22_prefix=/root/uav_humble22
humble22_project="${HUMBLE22_PROJECT_ROOT:-$humble22_prefix/project}"
if [[ "$humble22_project" != "$humble22_prefix/project" && ! "$humble22_project" =~ ^/root/uav_tracking_fullplan_[a-zA-Z0-9_]+$ ]]; then
  echo 'HUMBLE22_PROJECT_ROOT must identify the prepared project or an independent frozen study.' >&2
  return 2 2>/dev/null || exit 2
fi
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset CMAKE_PREFIX_PATH CMAKE_MODULE_PATH CPATH CPLUS_INCLUDE_PATH C_INCLUDE_PATH LIBRARY_PATH PKG_CONFIG_PATH
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH PYTHONPATH PYTHONHOME LD_LIBRARY_PATH
humble22_restore_nounset=false
case $- in *u*) humble22_restore_nounset=true;; esac
set +u
source /opt/ros/humble/setup.bash
source "$humble22_prefix/venv/bin/activate"
source "$humble22_prefix/ros_gz_ws/install/setup.bash"
source "$humble22_prefix/px4_msgs_ws/install/setup.bash"
source "$humble22_project/ros2_ws/install/setup.bash"
export STAGE1_ROS_DISTRO=humble
export STAGE1_PROJECT_ROOT="$humble22_project"
export STAGE1_PX4_ROOT="${HUMBLE22_PX4_ROOT:-$humble22_prefix/PX4-Autopilot}"
export STAGE1_PX4_MSGS_WS="$humble22_prefix/px4_msgs_ws"
export STAGE1_ROS_GZ_WS="$humble22_prefix/ros_gz_ws"
export STAGE1_PYTHON_EXECUTABLE="$humble22_prefix/venv/bin/python"
export PYTHONPATH="$humble22_project:${PYTHONPATH:-}"
export ROS_DOMAIN_ID=73
export GZ_PARTITION=uav_humble22_validation
export GZ_IP=127.0.0.1
export GZ_VERSION=harmonic
export IGNITION_VERSION=''
export PATH="$humble22_prefix/agent_install/bin:$PATH"
export LD_LIBRARY_PATH="$humble22_prefix/agent_install/lib:${LD_LIBRARY_PATH:-}"
if "$humble22_restore_nounset"; then set -u; fi
unset humble22_restore_nounset
