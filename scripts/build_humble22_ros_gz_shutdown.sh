#!/usr/bin/env bash
# Build the reviewed lifecycle patch in a NEW independent bridge overlay.
set -euo pipefail
if [[ "${WSL_DISTRO_NAME:-}" != UAVHumble22 ]]; then
  echo 'Use the isolated UAVHumble22 distribution.' >&2
  exit 2
fi
tracking_bridge_source_ws="${1:-/root/uav_humble22/ros_gz_ws}"
tracking_bridge_new_ws="${2:?Provide a new independent destination workspace}"
tracking_bridge_project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tracking_bridge_patch="$tracking_bridge_project/patches/ros_gz_bridge_ownership_shutdown_A01.patch"
if [[ -e "$tracking_bridge_new_ws" || -L "$tracking_bridge_new_ws" ]]; then
  echo 'Destination already exists; source and prior builds must be retained.' >&2
  exit 2
fi
if [[ "$(git -C "$tracking_bridge_source_ws/src/ros_gz" rev-parse HEAD)" != 856e319ee4da713609b3f6e58c74ac8db7662482 ||
      -n "$(git -C "$tracking_bridge_source_ws/src/ros_gz" status --porcelain)" ]]; then
  echo 'Expected the clean, pinned Humble 0.244.27 source.' >&2
  exit 2
fi
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH LD_LIBRARY_PATH
unset CMAKE_MODULE_PATH CPATH CPLUS_INCLUDE_PATH C_INCLUDE_PATH LIBRARY_PATH PKG_CONFIG_PATH
set +u
source /opt/ros/humble/setup.bash
source /root/uav_humble22/venv/bin/activate
source "$tracking_bridge_source_ws/install/setup.bash"
set -u
export GZ_VERSION=harmonic IGNITION_VERSION=''
# These are environment variables. A -D CMake cache setting does not constrain
# colcon's generated make command and would leave its CPU-count default active.
export CMAKE_BUILD_PARALLEL_LEVEL=2 MAKEFLAGS=-j2
mkdir -p "$tracking_bridge_new_ws/src"
git clone --no-hardlinks "$tracking_bridge_source_ws/src/ros_gz" "$tracking_bridge_new_ws/src/ros_gz"
git -C "$tracking_bridge_new_ws/src/ros_gz" apply --check "$tracking_bridge_patch"
git -C "$tracking_bridge_new_ws/src/ros_gz" apply "$tracking_bridge_patch"
cd "$tracking_bridge_new_ws"
/root/uav_humble22/venv/bin/python /usr/bin/colcon build \
  --merge-install --packages-select ros_gz_bridge --packages-ignore ros_gz_interfaces \
  --executor sequential --parallel-workers 1 \
  --cmake-args -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DPython3_EXECUTABLE=/root/uav_humble22/venv/bin/python \
  -DPYTHON_EXECUTABLE=/root/uav_humble22/venv/bin/python
echo 'Build only. Run independent data/service/lifecycle checks and register this overlay before any study.'
