#!/usr/bin/env bash
# One reviewed action, with build post-checks inside the same bounded window.
set -euo pipefail
[[ $# == 3 ]] || exit 2
freeze_action="$1"
freeze_review="$2"
freeze_review_sha="$3"
case "$freeze_action" in prepare|copy|build|validate) ;; *) exit 2;; esac
[[ "${WSL_DISTRO_NAME:-}" == UAVHumble22 && "${REVIEWED_FREEZE_ACTION:-}" == "$freeze_action" && "${REVIEWED_FREEZE_PARENT_PID:-}" == "$PPID" ]] || exit 2
freeze_external=/mnt/d/WSL/UAVHumble22-validation
set +u
if declare -F deactivate >/dev/null; then deactivate nondestructive; fi
set -u
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH CMAKE_MODULE_PATH CMAKE_FRAMEWORK_PATH CMAKE_APPBUNDLE_PATH CMAKE_INCLUDE_PATH CMAKE_LIBRARY_PATH CMAKE_PROGRAM_PATH
unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH CPATH CPLUS_INCLUDE_PATH C_INCLUDE_PATH LIBRARY_PATH PKG_CONFIG_PATH fastcdr_DIR FastCDR_DIR FASTCDR_ROOT FASTDDS_ROOT
# Validate/recover allowlisted fields only; never eval JSON or shell text.
freeze_root=$(/usr/bin/python3 -B -c 'import sys;sys.path.insert(0,sys.argv[1]);import reviewed_freeze_build as m;r=m.load_review(sys.argv[2],sys.argv[3],sys.argv[4]);print(r["frozen_root"])' "$freeze_external" "$freeze_review" "$freeze_review_sha" "$freeze_action")
freeze_source=$(/usr/bin/python3 -B -c 'import sys;sys.path.insert(0,sys.argv[1]);import reviewed_freeze_build as m;r=m.load_review(sys.argv[2],sys.argv[3],sys.argv[4]);print(r["source_root"])' "$freeze_external" "$freeze_review" "$freeze_review_sha" "$freeze_action")
export STAGE1_ROS_DISTRO=humble STAGE1_PROJECT_ROOT="$freeze_root" HUMBLE22_PROJECT_ROOT="$freeze_root"
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws STAGE1_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export STAGE1_PX4_MSGS_WS=/root/uav_humble22/px4_msgs_ws STAGE1_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export STAGE1_PYTHON_EXECUTABLE=/root/uav_humble22/venv/bin/python
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 MAKEFLAGS=-j2 CMAKE_BUILD_PARALLEL_LEVEL=2 PYTHONDONTWRITEBYTECODE=1
set +u
source /opt/ros/humble/setup.bash
source /root/uav_humble22/venv/bin/activate
source /root/uav_humble22/ros_gz_ws/install/setup.bash
source "$HUMBLE22_ROS_GZ_WS/install/setup.bash"
source "$STAGE1_PX4_MSGS_WS/install/setup.bash"
if [[ "$freeze_action" == validate ]]; then source "$freeze_root/ros2_ws/install/setup.bash"; fi
set -u
if [[ "$freeze_action" == build || "$freeze_action" == validate ]]; then
  export PYTHONPATH="$freeze_root:${PYTHONPATH:-}"
  cd "$freeze_root"
else
  export PYTHONPATH="$freeze_source:${PYTHONPATH:-}"
  cd "$freeze_source"
fi
"$STAGE1_PYTHON_EXECUTABLE" -B "$freeze_external/reviewed_freeze_build.py" "$freeze_action" --review "$freeze_review" --review-sha256 "$freeze_review_sha" --internal-phase action
if [[ "$freeze_action" == build ]]; then
  set +u
  source "$freeze_root/ros2_ws/install/setup.bash"
  set -u
  exec "$STAGE1_PYTHON_EXECUTABLE" -B "$freeze_external/reviewed_freeze_build.py" build --review "$freeze_review" --review-sha256 "$freeze_review_sha" --internal-phase post-build
fi
