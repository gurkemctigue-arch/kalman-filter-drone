#!/usr/bin/env bash
set -euo pipefail
export HUMBLE22_PROJECT_ROOT=/root/uav_tracking_fullplan_v4_humble54
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export TMPDIR=/tmp STAGE1_TRANSIENT_DIR=/tmp PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
source "$HUMBLE22_PROJECT_ROOT/scripts/humble22_env.sh"
tracking_safety_root="$HUMBLE22_PROJECT_ROOT"
tracking_safety_contract="$tracking_safety_root/results/snapshot_audit54_contract03.json"
tracking_safety_output="$tracking_safety_root/results/reliability_v4_humble54_safety03_audit"
test ! -e "$tracking_safety_output"
/root/uav_humble22/venv/bin/python -B - <<'PY'
from pathlib import Path
import json
p=Path('/mnt/d/WSL/UAVHumble22-validation/safety54_schema_recovery03/native_recovery03.json')
r=json.loads(p.read_bytes())
assert r['exit_code']==0 and r['status']=='NATIVE_SCHEMA_REPAIR_CONTRACT_AND_READ_ONLY_DIAGNOSTIC_COMPLETE_FRESH_SAFETY4_PENDING'
assert r['fixed_guard_helper_registrar_unchanged'] and r['original_failure_and_contract_unchanged'] and r['core_plan_unchanged']
assert r['original_schema_keyerror_reproduced'] == "KeyError: 'result'"
assert r['schema_specific_aggregation_diagnostic_result'] == 'PASS'
assert r['full_old_slot_reaudit_performed'] is False and r['original_registry_not_revalidated_or_rewritten'] is True
PY
tracking_safety_contract_sha="$(sha256sum "$tracking_safety_contract" | cut -d' ' -f1)"
exec /root/uav_humble22/venv/bin/python -B \
 /root/uav_tracking_snapshot_audit54_tools01/tools/run_reliability_v4_safety.py register \
 --core-plan "$tracking_safety_root/results/reliability_v4_humble54_core12_probe01_matrix/plan.json" \
 --core-owner "$tracking_safety_root/results/humble54_core12_owner01/owner_terminal.json" \
 --output "$tracking_safety_output" --prefix reliability_v4_humble54_safety03 \
 --snapshot-audit-contract "$tracking_safety_contract" --snapshot-audit-contract-sha256 "$tracking_safety_contract_sha"
