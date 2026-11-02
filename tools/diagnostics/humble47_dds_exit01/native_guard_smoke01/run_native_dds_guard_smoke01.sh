#!/usr/bin/env bash
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH PYTHONHOME LD_LIBRARY_PATH UAV_TRACKING_DDS_RUNTIME_CONFIG RMW_IMPLEMENTATION
export STAGE1_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble47 STAGE1_ROS_DISTRO=humble
export ROS_DOMAIN_ID=74 GZ_PARTITION=uav_dds_guard_probe_A01 GZ_IP=127.0.0.1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
set +u
source /opt/ros/humble/setup.bash
source /root/uav_humble22/venv/bin/activate
source /root/uav_humble22/ros_gz_ws/install/setup.bash
source /root/uav_humble22/ros_gz_shutdown_A01_ws/install/setup.bash
source /root/uav_humble22/px4_msgs_ws/install/setup.bash
source "$STAGE1_PROJECT_ROOT/ros2_ws/install/setup.bash"
set -u
export PYTHONPATH="/mnt/d/基于yolo和卡尔曼滤波:${PYTHONPATH:-}"
source /mnt/d/基于yolo和卡尔曼滤波/scripts/apply_humble22_dds_runtime.sh /mnt/d/基于yolo和卡尔曼滤波
exec /root/uav_humble22/venv/bin/python -B /mnt/d/WSL/UAVHumble22-validation/humble47_tf_exit_diagnosis01/native_dds_guard_smoke01.py
