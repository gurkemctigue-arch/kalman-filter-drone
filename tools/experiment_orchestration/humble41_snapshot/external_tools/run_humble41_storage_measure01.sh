#!/usr/bin/env bash
set -euo pipefail
storage41_external=/mnt/d/WSL/UAVHumble22-validation
if [[ $# -eq 0 ]]; then set -- describe; fi
case "$1" in
  describe) exec /usr/bin/python3 -B "$storage41_external/measure_humble41_completed_storage01.py" "$@";;
  measure) ;;
  *) echo 'Only describe or explicitly reviewed metadata measure is supported.' >&2; exit 2;;
esac
[[ "${WSL_DISTRO_NAME:-}" == UAVHumble22 ]] || exit 2
set +u
if declare -F deactivate >/dev/null; then deactivate nondestructive; fi
set -u
export PATH=/root/uav_humble22/agent_install/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH CMAKE_MODULE_PATH CMAKE_FRAMEWORK_PATH CMAKE_APPBUNDLE_PATH CMAKE_INCLUDE_PATH CMAKE_LIBRARY_PATH CMAKE_PROGRAM_PATH
unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH CPATH CPLUS_INCLUDE_PATH C_INCLUDE_PATH LIBRARY_PATH PKG_CONFIG_PATH fastcdr_DIR FastCDR_DIR FASTCDR_ROOT FASTDDS_ROOT
unset HUMBLE41_ACTION_ENV HUMBLE41_BOUNDED_ACTION HUMBLE41_BOUNDED_LAUNCHER_PID HUMBLE41_DEVELOPMENT_ACTION HUMBLE41_REVIEWED_HELPERS_SHA256 HUMBLE41_FOLLOWON_ACTION HUMBLE41_FOLLOWON_REVIEWED_SHA256
export STAGE1_ROS_DISTRO=humble STAGE1_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble41
export HUMBLE22_PROJECT_ROOT="$STAGE1_PROJECT_ROOT"
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws STAGE1_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export STAGE1_PX4_MSGS_WS=/root/uav_humble22/px4_msgs_ws
export STAGE1_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export STAGE1_PYTHON_EXECUTABLE=/root/uav_humble22/venv/bin/python
export ROS_DOMAIN_ID=73 GZ_PARTITION=uav_humble22_validation GZ_IP=127.0.0.1 GZ_VERSION=harmonic IGNITION_VERSION=''
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
export HUMBLE41_STORAGE_ACTION=measure
set +u
source /opt/ros/humble/setup.bash
source /root/uav_humble22/venv/bin/activate
source /root/uav_humble22/ros_gz_ws/install/setup.bash
source "$HUMBLE22_ROS_GZ_WS/install/setup.bash"
source "$STAGE1_PX4_MSGS_WS/install/setup.bash"
source "$STAGE1_PROJECT_ROOT/ros2_ws/install/setup.bash"
set -u
export PATH="/root/uav_humble22/agent_install/bin:$PATH"
export LD_LIBRARY_PATH="/root/uav_humble22/agent_install/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$STAGE1_PROJECT_ROOT:${PYTHONPATH:-}"
cd "$STAGE1_PROJECT_ROOT"
exec /root/uav_humble22/venv/bin/python -B "$storage41_external/measure_humble41_completed_storage01.py" "$@"
