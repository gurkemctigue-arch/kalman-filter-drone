#!/usr/bin/env bash
set -eo pipefail
export HUMBLE22_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble42
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export PYTHONDONTWRITEBYTECODE=1
source "$HUMBLE22_PROJECT_ROOT/scripts/humble22_env.sh"
set -u
stage_diag_tools=/mnt/d/WSL/UAVHumble22-validation/humble42_shutdown_diagnostic01
stage_diag_world="$HUMBLE22_PROJECT_ROOT/results/reliability_v4_humble42_probe01_car_stage2_crossing_seed004/configuration/runtime_world.sdf"
stage_diag_share="$(ros2 pkg prefix uav_tracking_bringup)/share/uav_tracking_bringup"
exec /usr/bin/python3 -B "$stage_diag_tools/owned_rgbd_shutdown.py" \
  --execute-owned-diagnostic \
  --source-root "$HUMBLE22_PROJECT_ROOT" \
  --runner-sha256 c49db44aba88249cbbafb27ab0d7de13be38419560466636a468a913071f2097 \
  --launcher-sha256 9b9f485f294110f74186abcf2cf48d1b09297927104a2fed42f1d1818ee6c319 \
  --probe-source "$HUMBLE22_PROJECT_ROOT/scripts/probe_gazebo_shutdown.py" \
  --probe-sha256 cb9e6d946cb31a6aa8b0af09ef283d07060bf3d2650f5b8915936491e805f61c \
  --tool-sha256 d088d1e93c5a86afd38de9ca2a3664f61b91cd7529a82d3006e21fd6a1983cb0 \
  --world "$stage_diag_world" \
  --world-sha256 587adf76dd76cfd538454103181969330cb3372458b895571058c76f76966d74 \
  --world-name stage2_flight \
  --output /mnt/d/WSL/UAVHumble22-validation/humble42_shutdown_diag_01 \
  --seed 5 --lp-threads 4 --omp-threads 2 --min-frames 2 \
  --sigint-grace 8 --sigterm-grace 5 --sigkill-grace 3 \
  --image-topic /camera/rgbd/image --image-topic /camera/rgbd/depth_image \
  --resource-path "$stage_diag_share/models" \
  --resource-path "$HUMBLE22_PX4_ROOT/Tools/simulation/gz/models" \
  --plugin-path "$HUMBLE22_PX4_ROOT/build/px4_sitl_default/src/modules/simulation/gz_plugins"
