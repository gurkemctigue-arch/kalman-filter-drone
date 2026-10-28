#!/usr/bin/env bash
# Run each component in its own WSL terminal with the same environment.
# Usage: bash scripts/run_stage1_flight.sh {gazebo|px4|agent|ros|check} [person|car]
set -euo pipefail

stage1_component="${1:-check}"
stage1_class="${2:-person}"
case "$stage1_class" in person|car) ;; *) echo "class must be person or car" >&2; exit 2;; esac
stage1_project="${STAGE1_PROJECT_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
stage1_px4="${STAGE1_PX4_ROOT:-/root/PX4-Autopilot}"
# source scripts need unset-variable tolerance on both ROS Humble and Jazzy.
set +u
source "$stage1_project/scripts/source_ros_environment.sh"
source "$stage1_project/ros2_ws/install/setup.bash"
set -u
stage1_share="$(ros2 pkg prefix uav_tracking_bringup)/share/uav_tracking_bringup"
stage1_world="${STAGE_WORLD:-stage1_flight}"
stage1_world_file="${STAGE_WORLD_FILE:-$stage1_share/worlds/${stage1_world}_${stage1_class}.sdf}"
export GZ_PARTITION="${GZ_PARTITION:-stage1_flight}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export GZ_IP=127.0.0.1
export GZ_SIM_RESOURCE_PATH="$stage1_share/models:$stage1_px4/Tools/simulation/gz/models:${GZ_SIM_RESOURCE_PATH:-}"
export GZ_SIM_SYSTEM_PLUGIN_PATH="$stage1_px4/build/px4_sitl_default/src/modules/simulation/gz_plugins:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"

case "$stage1_component" in
  gazebo)
    # Gazebo 8.15 treats 0 as unspecified and does not seed its RNG.
    # The runner maps its zero-based registered seed to seed+1 explicitly.
    stage1_sim_seed="${STAGE_SIM_SEED:-1}"
    if [[ ! "$stage1_sim_seed" =~ ^[0-9]+$ ]] || [ "${#stage1_sim_seed}" -gt 10 ] || [ "$stage1_sim_seed" -lt 1 ] || [ "$stage1_sim_seed" -gt 4294967295 ]; then
      echo "STAGE_SIM_SEED must be a nonzero unsigned 32-bit integer" >&2
      exit 2
    fi
    stage1_run_args=(--seed "$stage1_sim_seed")
    if [ "${STAGE_START_PAUSED:-0}" != "1" ]; then stage1_run_args+=(-r); fi
    echo "Gazebo random seed: $stage1_sim_seed (explicit --seed)"
    if [ "${STAGE1_RENDER_BACKEND:-egl}" = "wslg" ]; then
      # WSLg's D3D12 backend exposes the Intel/AMD/NVIDIA Windows GPU.
      # Only the server runs; this does not open the Gazebo GUI.
      export MESA_LOADER_DRIVER_OVERRIDE=d3d12 GALLIUM_DRIVER=d3d12
      exec gz sim "${stage1_run_args[@]}" -s "$stage1_world_file"
    fi
    exec gz sim "${stage1_run_args[@]}" -s --headless-rendering "$stage1_world_file"
    ;;
  px4)
    # Attach to the model already included in the same world; never spawn a
    # second x500 or use the stock default world. The custom model inherits
    # the x500 actuator geometry and uses its normal 4001 airframe.
    export PX4_SYS_AUTOSTART=4001 PX4_SIM_MODEL=x500 PX4_GZ_STANDALONE=1
    export PX4_GZ_WORLD="$stage1_world" PX4_GZ_MODEL_NAME=stage1_uav HEADLESS=1
    # No RC/GCS is part of this simulation. These normal PX4 parameters make
    # that explicit; estimator, arming and Offboard checks remain active.
    export PX4_PARAM_COM_RC_IN_MODE=4 PX4_PARAM_NAV_DLL_ACT=0
    # rcS imports PX4_PARAM_* before it starts the XRCE client. Keep the
    # simulation clock contract explicit on every run, even when a prior
    # trial persisted the other value. This is never a real-vehicle setting.
    case "${STAGE1_PX4_TIME_MODE:-receipt}" in
      source_sim) export PX4_PARAM_UXRCE_DDS_SYNCT=0 ;;
      receipt) export PX4_PARAM_UXRCE_DDS_SYNCT=1 ;;
      *) echo "STAGE1_PX4_TIME_MODE must be receipt or source_sim" >&2; exit 2 ;;
    esac
    if [ "${STAGE1_PX4_MAG_CONTRACT:-}" = "gazebo_enu_flu_to_frd_v1" ]; then
      export PX4_PARAM_SENS_EN_MAGSIM=0
    fi
    if [ "${STAGE1_TAKEOFF_MODE:-offboard_velocity}" = "px4_native" ]; then
      # Normal native Takeoff uses current onboard AMSL + this height when
      # param7 is NaN, then stays in AUTO_LOITER instead of entering a mission.
      export PX4_PARAM_MIS_TAKEOFF_ALT="${STAGE1_TAKEOFF_HEIGHT_M:-3.0}"
      export PX4_PARAM_COM_TAKEOFF_ACT=0
      # The startup readiness topics are estimator instance zero. Use the
      # normal single-EKF selection explicitly rather than assuming that a
      # multi-EKF primary is always instance zero.
      export PX4_PARAM_SENS_IMU_MODE=1
    fi
    # An isolated compile has not necessarily run PX4's default launcher yet.
    # Explicitly provide its built startup data and working directory so PX4
    # creates rootfs/etc itself. A bare -s disables upstream default discovery
    # and otherwise works only if an earlier run happened to create that link.
    exec "$stage1_px4/build/px4_sitl_default/bin/px4" \
      "$stage1_px4/build/px4_sitl_default/etc" \
      -w "$stage1_px4/build/px4_sitl_default/rootfs" \
      -d -s "$stage1_project/scripts/px4_stage1_startup.sh"
    ;;
  agent)
    exec MicroXRCEAgent udp4 -p 8888
    ;;
  ros)
    # Explicit opt-in, default false. Main experiment runner sets
    # STAGE1_AUTO_START=true only for this simulated aircraft.
    exec ros2 launch uav_tracking_bringup "${STAGE_LAUNCH:-stage1_flight.launch.py}" \
      "params_file:=${STAGE_PARAMS_FILE:-$stage1_share/config/stage1_tracking_${stage1_class}.yaml}" \
      "auto_start:=${STAGE1_AUTO_START:-false}" \
      "takeoff_height_m:=${STAGE1_TAKEOFF_HEIGHT_M:-3.0}" \
      "command_mode:=${STAGE1_COMMAND_MODE:-velocity}" \
      "speed_mps:=${STAGE_SPEED_MPS:-0.5}" \
      "motion_profile_kind:=${STAGE_MOTION_PROFILE_KIND:-standard}"
    ;;
  check)
    test -x "$stage1_px4/build/px4_sitl_default/bin/px4"
    test -f "$stage1_share/models/x500_stage1/model.sdf"
    test -f "$stage1_share/worlds/stage1_flight_${stage1_class}.sdf"
    command -v gz
    command -v MicroXRCEAgent
    ros2 pkg executables uav_tracking_px4_adapter
    ros2 pkg executables uav_tracking_bringup
    ;;
  *) echo "usage: $0 {gazebo|px4|agent|ros|check} [person|car]" >&2; exit 2;;
esac
