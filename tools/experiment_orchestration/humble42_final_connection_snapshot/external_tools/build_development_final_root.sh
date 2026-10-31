#!/usr/bin/env bash
# Launched only by the bounded external parent; no simulator or formal work.
set -euo pipefail
final_tools="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-}" in
  --build-internal) final_action=internal-build; shift;;
  --verify-internal) final_action=internal-verify; shift;;
  *) exit 2;;
esac
[[ "${WSL_DISTRO_NAME:-}" == UAVHumble22 ]] || exit 2
[[ -n "${DEVELOPMENT_FINAL_BUILD_PARENT_PID:-}" ]] || exit 2
final_root=$(/usr/bin/python3 -B "$final_tools/build_development_final_root.py" root "$@")
set +u
if declare -F deactivate >/dev/null; then deactivate nondestructive; fi
set -u
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH CMAKE_MODULE_PATH CMAKE_FRAMEWORK_PATH CMAKE_APPBUNDLE_PATH CMAKE_INCLUDE_PATH CMAKE_LIBRARY_PATH CMAKE_PROGRAM_PATH
unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH CPATH CPLUS_INCLUDE_PATH C_INCLUDE_PATH LIBRARY_PATH PKG_CONFIG_PATH fastcdr_DIR FastCDR_DIR FASTCDR_ROOT FASTDDS_ROOT
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS CC CXX CMAKE_TOOLCHAIN_FILE CMAKE_SYSROOT CMAKE_FIND_ROOT_PATH CMAKE_GENERATOR CMAKE_GENERATOR_PLATFORM CMAKE_GENERATOR_TOOLSET COLCON_DEFAULTS_FILE COLCON_HOME
export STAGE1_ROS_DISTRO=humble STAGE1_PROJECT_ROOT="$final_root" HUMBLE22_PROJECT_ROOT="$final_root"
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws STAGE1_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export STAGE1_PX4_MSGS_WS=/root/uav_humble22/px4_msgs_ws
export STAGE1_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export STAGE1_PYTHON_EXECUTABLE=/root/uav_humble22/venv/bin/python
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MAKEFLAGS=-j2 CMAKE_BUILD_PARALLEL_LEVEL=2 PYTHONDONTWRITEBYTECODE=1
set +u
if [[ "$final_action" == internal-build ]]; then
  source /root/uav_humble22/venv/bin/activate
  source "$final_root/scripts/source_ros_environment.sh"
  export PYTHONPATH="$final_root:${PYTHONPATH:-}"
else
  source "$final_root/scripts/humble22_env.sh"
fi
set -u
cd -- "$final_root"
exec "$STAGE1_PYTHON_EXECUTABLE" -B "$final_tools/build_development_final_root.py" "$final_action" "$@"
