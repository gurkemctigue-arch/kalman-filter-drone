#!/usr/bin/env bash
set -euo pipefail
task_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ASSETCHECK_OUTPUT="$task_repo/results/asset_validation/flight_viewpoints"
mkdir -p "$ASSETCHECK_OUTPUT"
read -r -a task_streams <<< "$(python3 "$task_repo/scripts/create_asset_viewpoint_world.py" "$ASSETCHECK_OUTPUT/world.sdf")"
exec bash "$task_repo/scripts/run_assetcheck.sh" "$ASSETCHECK_OUTPUT/world.sdf" "${task_streams[@]}"
