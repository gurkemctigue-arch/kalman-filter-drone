#!/usr/bin/env bash
# New descriptive exports only; original terminal/report/review files are immutable.
set -euo pipefail
test "${WSL_DISTRO_NAME:-}" = UAVHumble22
tracking_dev=/root/uav_tracking_fullplan_v4_humble54
tracking_project='/mnt/d/基于yolo和卡尔曼滤波'
tracking_tool="$tracking_project/tools/diagnostics/humble54_dropout_gap01/extract_short_window.py"
tracking_plan="$tracking_dev/results/reliability_v4_humble54_extension16_probe01_matrix/plan.json"
python3 -B - "$tracking_tool" "$tracking_plan" <<'PY'
from pathlib import Path
import hashlib, sys
assert hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest() == '364156694a5db1777b7b3615614ae32b5cc128a7f8bbc09e213e1a168854fbf4'
assert hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest() == 'f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055'
PY
bash /mnt/d/WSL/UAVHumble22-validation/check_humble54_native_idle02.sh
export HUMBLE22_PROJECT_ROOT="$tracking_dev"
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export PYTHONDONTWRITEBYTECODE=1
export STAGE1_TRANSIENT_DIR=/tmp
source "$tracking_dev/scripts/humble22_env.sh"
for tracking_condition in dropout combined; do
  bash "$tracking_dev/scripts/run_research_session.sh" "$tracking_tool" \
    --source-root "$tracking_dev" --plan "$tracking_plan" \
    --slot-id "person_extension_${tracking_condition}_seed004" \
    --output "$tracking_project/results/diagnostics/humble54_person_${tracking_condition}_input_extract02"
done
