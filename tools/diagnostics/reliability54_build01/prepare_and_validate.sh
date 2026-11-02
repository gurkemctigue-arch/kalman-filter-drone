#!/usr/bin/env bash
# One new Humble source/build snapshot. Never source or write the reference root.
set -eo pipefail

if [[ "${1:-}" != --clean-environment ]]; then
  # Inherited old colcon, CMake, Python, compiler and DDS prefixes must not
  # influence the source copy or the new compiler configuration.
  exec env -i HOME="$HOME" USER="${USER:-root}" LOGNAME="${LOGNAME:-root}" \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 TMPDIR=/tmp WSL_DISTRO_NAME="${WSL_DISTRO_NAME:-}" \
    /bin/bash --noprofile --norc "${BASH_SOURCE[0]}" --clean-environment "$@"
fi
shift
if [[ $# -ne 3 ]]; then
  echo 'Usage: prepare_and_validate.sh /root/uav_tracking_fullplan_NEW /mnt/d/.../results/frozen_fullplan_NEW /root/REVIEWED_REFERENCE' >&2
  exit 2
fi
tracking_frozen="$1"
tracking_results_store="$2"
tracking_reference="$(realpath -e -- "$3")"
tracking_source="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
if [[ "${WSL_DISTRO_NAME:-}" != UAVHumble22 ]]; then
  echo 'Run in the isolated UAVHumble22 distribution.' >&2
  exit 2
fi
if ! [[ "$tracking_frozen" =~ ^/root/uav_tracking_fullplan_[a-zA-Z0-9_]+$ ]] \
    || [[ -e "$tracking_frozen" || -L "$tracking_frozen" ]]; then
  echo 'Expected a new dedicated frozen root.' >&2
  exit 2
fi
tracking_results_store="$(realpath -m -- "$tracking_results_store")"
if ! [[ "$tracking_results_store" =~ ^/mnt/d/.+/results/frozen_fullplan_[a-zA-Z0-9_]+$ ]] \
    || [[ -e "$tracking_results_store" || -L "$tracking_results_store" ]]; then
  echo 'Expected a new dedicated D-drive results store.' >&2
  exit 2
fi
tracking_registrations=(config/dds_runtime_humble22.json config/ros_gz_runtime_humble22.json \
  config/ros_gz_clock_runtime_humble22.json config/px4_magnetic_runtime.json \
  config/gazebo_magnetic_runtime_humble22.json)
for tracking_registration in "${tracking_registrations[@]}"; do
  if ! cmp -s -- "$tracking_source/$tracking_registration" "$tracking_reference/$tracking_registration"; then
    echo "Reviewed runtime registration missing or differs: $tracking_registration" >&2
    exit 2
  fi
done

export STAGE1_ROS_DISTRO=humble STAGE1_PROJECT_ROOT="$tracking_frozen" HUMBLE22_PROJECT_ROOT="$tracking_frozen"
export STAGE1_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export STAGE1_PX4_MSGS_WS=/root/uav_humble22/px4_msgs_ws
export STAGE1_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export STAGE1_PYTHON_EXECUTABLE=/root/uav_humble22/venv/bin/python
export STAGE1_FASTCDR_CMAKE_DIR=/opt/ros/humble/lib/cmake/fastcdr
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export MAKEFLAGS=-j2 CMAKE_BUILD_PARALLEL_LEVEL=2 PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp
source /opt/ros/humble/setup.bash
source /root/uav_humble22/venv/bin/activate
source /root/uav_humble22/ros_gz_ws/install/setup.bash
source "$STAGE1_ROS_GZ_WS/install/setup.bash"
source "$STAGE1_PX4_MSGS_WS/install/setup.bash"
for tracking_prefix_name in AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH PYTHONPATH; do
  if [[ "${!tracking_prefix_name:-}" == *"/root/uav_tracking_fullplan_"* ]]; then
    echo "A ROS underlay reintroduced an old project prefix: $tracking_prefix_name" >&2
    exit 2
  fi
done
# Select the reviewed runtime libraries separately from the system FastCDR
# compiler package. The target registration will exist after the public copy.
tracking_runtime_libraries="$("$STAGE1_PYTHON_EXECUTABLE" -B "$tracking_source/scripts/dds_runtime.py" environment \
  --registration "$tracking_source/config/dds_runtime_humble22.json" --current-library-path "${LD_LIBRARY_PATH:-}")"
export LD_LIBRARY_PATH="$tracking_runtime_libraries" RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export UAV_TRACKING_DDS_RUNTIME_CONFIG="$tracking_frozen/config/dds_runtime_humble22.json"
tracking_integrity_script="$tracking_source/tools/diagnostics/reliability54_build01/source_integrity.py"
tracking_integrity_dir="$(mktemp -d /tmp/uav_freeze_integrity.XXXXXX)"
"$STAGE1_PYTHON_EXECUTABLE" -B "$tracking_integrity_script" snapshot \
  --source "$tracking_source" --output "$tracking_integrity_dir/source_before.json"
tracking_build_returncode=0
/bin/bash "$tracking_source/scripts/freeze_full_plan_workspace.sh" "$tracking_frozen" "$tracking_results_store" \
  || tracking_build_returncode=$?
tracking_integrity_returncode=0
"$STAGE1_PYTHON_EXECUTABLE" -B "$tracking_integrity_script" verify \
  --before "$tracking_integrity_dir/source_before.json" --source "$tracking_source" --frozen "$tracking_frozen" \
  --output-dir "$tracking_integrity_dir" --build-returncode "$tracking_build_returncode" --results-store "$tracking_results_store" \
  || tracking_integrity_returncode=$?
if [[ -d "$tracking_frozen/results/freeze_validation" ]]; then
  "$STAGE1_PYTHON_EXECUTABLE" -B "$tracking_integrity_script" publish \
    --source-dir "$tracking_integrity_dir" --output-dir "$tracking_frozen/results/freeze_validation/source_integrity"
fi
if [[ "$tracking_build_returncode" -ne 0 ]]; then
  exit "$tracking_build_returncode"
fi
if [[ "$tracking_integrity_returncode" -ne 0 ]]; then
  exit "$tracking_integrity_returncode"
fi

# Public freeze already executed colcon, module/ament isolation and the full
# real suite. This supplement records actual compiler choice and a small CDR
# receipt in a fresh interpreter, without test doubles from the suite.
source "$tracking_frozen/ros2_ws/install/setup.bash"
source "$tracking_frozen/scripts/apply_humble22_dds_runtime.sh" "$tracking_frozen"
export PYTHONPATH="$tracking_frozen:${PYTHONPATH:-}"
cd "$tracking_frozen"
"$STAGE1_PYTHON_EXECUTABLE" -B "$tracking_frozen/tools/diagnostics/reliability54_build01/record_native_validation.py" \
  --root "$tracking_frozen" --reference "$tracking_reference"
