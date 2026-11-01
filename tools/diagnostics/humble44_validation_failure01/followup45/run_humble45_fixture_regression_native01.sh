#!/usr/bin/env bash
set -euo pipefail
set -o noclobber
export HUMBLE22_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble44
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
source "$HUMBLE22_PROJECT_ROOT/scripts/humble22_env.sh"
export PYTHONDONTWRITEBYTECODE=1
cd '/mnt/d/基于yolo和卡尔曼滤波'
tracking45_log=/mnt/d/WSL/UAVHumble22-validation/humble45_fixture_regression_native01.log
tracking45_inputs=/mnt/d/WSL/UAVHumble22-validation/humble45_fixture_regression_native01.sha256
test ! -e "$tracking45_log"
test ! -e "$tracking45_inputs"
sha256sum -- tests/test_simulation_seed.py tests/test_recording_qos.py scripts/run_stage1_trial.py config/recording_qos.yaml > "$tracking45_inputs"
if /root/uav_humble22/venv/bin/python -B -m unittest \
    tests.test_simulation_seed tests.test_recording_qos -v > "$tracking45_log" 2>&1; then
    tail -n 5 "$tracking45_log"
else
    tracking45_rc=$?
    tail -n 40 "$tracking45_log"
    exit "$tracking45_rc"
fi
