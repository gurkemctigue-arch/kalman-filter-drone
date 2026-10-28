#!/usr/bin/env bash
# Create an isolated source/build snapshot; never replace an earlier study.
set -eo pipefail
tracking_source="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tracking_frozen="${1:-/root/uav_tracking_fullplan_v2}"
tracking_results_store="${2:-}"
if ! [[ "$tracking_frozen" =~ ^/root/uav_tracking_fullplan_[a-zA-Z0-9_]+$ ]]; then
  echo "Expected a dedicated /root/uav_tracking_fullplan_NAME destination" >&2
  exit 2
fi
if [ -e "$tracking_frozen" ]; then
  echo "Refusing to overwrite an existing frozen study: $tracking_frozen" >&2
  exit 2
fi
if [ -n "$tracking_results_store" ]; then
  # Source/build stay on ext4. Large recordings may use a dedicated mounted
  # data-drive directory; never reuse or merge evidence from an earlier study.
  tracking_results_store="$(realpath -m -- "$tracking_results_store")"
  if ! [[ "$tracking_results_store" =~ ^/mnt/[a-z]/.+/results/frozen_fullplan_[a-zA-Z0-9_]+$ ]]; then
    echo "Expected a dedicated /mnt/DRIVE/.../results/frozen_fullplan_NAME store" >&2
    exit 2
  fi
  if [ -e "$tracking_results_store" ] || [ -L "$tracking_results_store" ]; then
    echo "Refusing to reuse a results store: $tracking_results_store" >&2
    exit 2
  fi
  if [ ! -d "$(dirname -- "$tracking_results_store")" ]; then
    echo "Results-store parent must already exist" >&2
    exit 2
  fi
fi
mkdir "$tracking_frozen"
rsync -a --exclude='__pycache__' --exclude='.pytest_cache' --exclude='results/' \
  --exclude='.git/' --exclude='node_modules/' --exclude='.test_temp/' --exclude='*.egg-info/' \
  --exclude='ros2_ws/build/' --exclude='ros2_ws/install/' --exclude='ros2_ws/log/' \
  "$tracking_source/" "$tracking_frozen/"
if [ -n "$tracking_results_store" ]; then
  mkdir "$tracking_results_store"
  ln -s "$tracking_results_store" "$tracking_frozen/results"
fi
mkdir -p "$tracking_frozen/results/recorded_estimator_research" "$tracking_frozen/results/freeze_validation"
printf '%s\n' "source_root=$tracking_frozen" "results_store=$(realpath -- "$tracking_frozen/results")" \
  > "$tracking_frozen/results/freeze_validation/storage_paths.txt"
df -P "$tracking_frozen" "$tracking_frozen/results" \
  > "$tracking_frozen/results/freeze_validation/storage_capacity.txt"
cp "$tracking_source/results/recorded_estimator_research/research_report.json" \
  "$tracking_frozen/results/recorded_estimator_research/research_report.json"
source "$tracking_frozen/scripts/source_ros_environment.sh"
tracking_python="${STAGE1_PYTHON_EXECUTABLE:-/usr/bin/python3}"
export PYTHONPATH="$tracking_frozen:${PYTHONPATH:-}"
cd "$tracking_frozen/ros2_ws"
"$tracking_python" "$(command -v colcon)" build --merge-install --symlink-install \
  --cmake-args "-DPython3_EXECUTABLE=$tracking_python" "-DPYTHON_EXECUTABLE=$tracking_python" \
  2>&1 | tee "$tracking_frozen/results/freeze_validation/colcon_build.log"
source "$tracking_frozen/ros2_ws/install/setup.bash"
# An inherited editable install can silently import an older project even when
# colcon succeeded. Verify real modules and ament prefixes before any research.
export PYTHONPATH="$tracking_frozen:${PYTHONPATH:-}"
TRACKING_FROZEN_ROOT="$tracking_frozen" "$tracking_python" - <<'PY_VERIFY_FROZEN' \
  | tee "$tracking_frozen/results/freeze_validation/import_isolation.json"
import importlib
import json
import os
from pathlib import Path
import subprocess

root = Path(os.environ["TRACKING_FROZEN_ROOT"]).resolve(strict=True)
paths = {}
for name in ("uav_tracking.core", "uav_tracking_nodes",
             "uav_tracking_interfaces.msg",
             "uav_tracking_interfaces.msg._target_observation_array",
             "uav_tracking_interfaces.msg._target_state"):
    module = importlib.import_module(name)
    location = Path(module.__file__).resolve(strict=True)
    if not location.is_relative_to(root):
        raise RuntimeError(f"Frozen import escaped {root}: {name} -> {location}")
    paths[name] = str(location)
prefixes = {}
for package in ("uav_tracking_nodes", "uav_tracking_interfaces",
                "uav_tracking_bringup", "uav_tracking_px4_adapter"):
    prefix = Path(subprocess.check_output(
        ["ros2", "pkg", "prefix", package], text=True).strip()).resolve(strict=True)
    if not prefix.is_relative_to(root):
        raise RuntimeError(f"Frozen ament prefix escaped {root}: {package} -> {prefix}")
    prefixes[package] = str(prefix)
print(json.dumps({"root": str(root), "module_files": paths,
                  "ros_package_prefixes": prefixes, "isolated": True}, indent=2))
PY_VERIFY_FROZEN
cd "$tracking_frozen"
find uav_tracking ros2_ws/src scripts planning config patches -type f \
  ! -path '*/__pycache__/*' -print0 | sort -z | xargs -0 sha256sum \
  > "$tracking_frozen/results/freeze_validation/source_sha256.txt"
"$tracking_python" -m unittest discover -s tests -q 2>&1 | tee "$tracking_frozen/results/freeze_validation/unittest.log"
printf '%s\n' "$tracking_frozen"
