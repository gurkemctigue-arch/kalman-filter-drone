#!/usr/bin/env bash
# Explicit same-source41 extension16 after core12/safety4 PASS; never auto-next or retry.
set -euo pipefail
# Describe reads only external tool identities and needs no ROS environment.
if [[ "${1:-}" == describe ]]; then
    exec /usr/bin/python3 -B "$(dirname -- "$0")/extension_runner41.py" "$@"
fi
[[ "${WSL_DISTRO_NAME:-}" == UAVHumble22 ]] || exit 2
probe_external=/mnt/d/WSL/UAVHumble22-validation
set +u
if declare -F deactivate >/dev/null; then deactivate nondestructive; fi
set -u
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH CMAKE_MODULE_PATH CMAKE_FRAMEWORK_PATH CMAKE_APPBUNDLE_PATH CMAKE_INCLUDE_PATH CMAKE_LIBRARY_PATH CMAKE_PROGRAM_PATH
unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH CPATH CPLUS_INCLUDE_PATH C_INCLUDE_PATH LIBRARY_PATH PKG_CONFIG_PATH fastcdr_DIR FastCDR_DIR FASTCDR_ROOT FASTDDS_ROOT
probe_root=$(/usr/bin/python3 -B -c 'import sys;sys.path.insert(0,sys.argv[1]);import extension_runner41 as m;print(m.shell_root(sys.argv[2:]))' "$probe_external" "$@")
export STAGE1_ROS_DISTRO=humble STAGE1_PROJECT_ROOT="$probe_root" HUMBLE22_PROJECT_ROOT="$probe_root"
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws STAGE1_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export STAGE1_PX4_MSGS_WS=/root/uav_humble22/px4_msgs_ws STAGE1_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export STAGE1_PYTHON_EXECUTABLE=/root/uav_humble22/venv/bin/python
export ROS_DOMAIN_ID=73 GZ_PARTITION=uav_humble22_validation GZ_IP=127.0.0.1 GZ_VERSION=harmonic IGNITION_VERSION=''
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
set +u
source /opt/ros/humble/setup.bash
source /root/uav_humble22/venv/bin/activate
source /root/uav_humble22/ros_gz_ws/install/setup.bash
source "$HUMBLE22_ROS_GZ_WS/install/setup.bash"
source "$STAGE1_PX4_MSGS_WS/install/setup.bash"
source "$probe_root/ros2_ws/install/setup.bash"
set -u
export PATH="/root/uav_humble22/agent_install/bin:$PATH"
export LD_LIBRARY_PATH="/root/uav_humble22/agent_install/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$probe_root:${PYTHONPATH:-}"
cd "$probe_root"
exec "$STAGE1_PYTHON_EXECUTABLE" -B "$probe_external/extension_runner41.py" "$@"
