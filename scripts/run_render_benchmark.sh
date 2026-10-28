#!/usr/bin/env bash
# Compare the same flight world with WSLg D3D12 vs software headless rendering.
# This starts a Gazebo server and RGB-D bridge only, never PX4 or a GUI.
set -eo pipefail
source /opt/ros/jazzy/setup.bash
set -u
task_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
task_mode="${1:-d3d12}"
task_px4=/root/PX4-Autopilot
task_assets="$task_repo/ros2_ws/src/uav_tracking_bringup"
task_results="$task_repo/results/render_benchmark/$task_mode"
mkdir -p "$task_results"
export GZ_PARTITION="renderbench_$task_mode"
export ROS_DOMAIN_ID=74
export GZ_IP=127.0.0.1
export GZ_SIM_RESOURCE_PATH="$task_assets/models:$task_px4/Tools/simulation/gz/models"
export GZ_SIM_SYSTEM_PLUGIN_PATH="$task_px4/build/px4_sitl_default/src/modules/simulation/gz_plugins:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"
task_render_args=()
case "$task_mode" in
  d3d12)
    export DISPLAY="${DISPLAY:-:0}"
    export MESA_LOADER_DRIVER_OVERRIDE=d3d12 GALLIUM_DRIVER=d3d12
    unset LIBGL_ALWAYS_SOFTWARE
    ;;
  software)
    unset MESA_LOADER_DRIVER_OVERRIDE GALLIUM_DRIVER
    task_render_args=(--headless-rendering)
    ;;
  *) echo "usage: $0 {d3d12|software}" >&2; exit 2;;
esac
for task_variable in DISPLAY WAYLAND_DISPLAY GZ_PARTITION ROS_DOMAIN_ID GZ_IP GZ_SIM_RESOURCE_PATH GZ_SIM_SYSTEM_PLUGIN_PATH MESA_LOADER_DRIVER_OVERRIDE GALLIUM_DRIVER LIBGL_ALWAYS_SOFTWARE; do
  printf '%s=%s\n' "$task_variable" "${!task_variable:-}"
done > "$task_results/environment.txt"
glxinfo -B > "$task_results/glxinfo.txt" 2>&1 || true
if [ -f /root/.gz/rendering/ogre2.log ]; then
  cp /root/.gz/rendering/ogre2.log "$task_results/ogre2_before.log"
fi
setsid gz sim -r -s -v 3 "${task_render_args[@]}" "$task_assets/worlds/stage1_flight_person.sdf" > "$task_results/gazebo.log" 2>&1 &
task_sim_pid=$!
setsid ros2 run ros_gz_bridge parameter_bridge /camera/rgbd/image@sensor_msgs/msg/Image@gz.msgs.Image /camera/rgbd/depth_image@sensor_msgs/msg/Image@gz.msgs.Image > "$task_results/bridge.log" 2>&1 &
task_bridge_pid=$!
cleanup_render_benchmark() {
  kill -- -"$task_bridge_pid" -"$task_sim_pid" 2>/dev/null || true
  wait "$task_bridge_pid" "$task_sim_pid" 2>/dev/null || true
  if [ -f /root/.gz/rendering/ogre2.log ]; then cp /root/.gz/rendering/ogre2.log "$task_results/ogre2.log"; fi
}
trap cleanup_render_benchmark EXIT
timeout 55 python3 "$task_repo/scripts/measure_camera_rate.py" --output "$task_results/camera_rate.json" --warmup 5 --seconds 20
