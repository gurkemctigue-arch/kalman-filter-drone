#!/usr/bin/env bash
# Supervised continuation of the original plan: exactly one still-PENDING slot.
# Original failed owner, waiter, marker, reports and terminal remain untouched.
set -euo pipefail
test "${WSL_DISTRO_NAME:-}" = UAVHumble22
tracking_dev=/root/uav_tracking_fullplan_v4_humble54
tracking_base=/mnt/d/WSL/UAVHumble22-validation
tracking_plan="$tracking_dev/results/reliability_v4_humble54_extension16_probe01_matrix/plan.json"
python3 -B - "$tracking_plan" "$tracking_base" <<'PY'
from pathlib import Path
import hashlib, json, sys
plan_path, base = map(Path, sys.argv[1:])
def checked(path, digest):
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest, str(path)
    return json.loads(raw)
plan = checked(plan_path, 'f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055')
assert plan['mode'] == 'EXTENSION_PROBE' and plan['selected_seeds'] == [4]
slots = Path(plan['output']) / 'slots'
old = checked(slots/'person_extension_dropout_seed004.json', '1369693a3b95abe1a2dad3feff9baf0bfd0354208c4ad90029bb2c6d0c5b3074')
assert old['status'] == 'INCOMPLETE_EVIDENCE' and old['infrastructure_stop'] is False
assert old['execution_status'] == 'COMPLETED' and type(old['flight_exit_code']) is int and old['flight_exit_code'] == 0
assert old['cleanup']['residual_processes'] == []
waiter = checked(base/'wait_humble54_extension_followon01/state.json', '05635cb35ba98446fb428a95c71a60fff712a87c218c72dea555d1fd9df70d0e')
assert waiter['status'] == 'STOPPED_REFUSED_NO_RETRY' and waiter['followon_launched'] is False
assert waiter['original_handle_exit_codes'] == {'monitor': 2, 'wsl': 2}
pending = [trial for trial in plan['trials'] if not (slots/(trial['id']+'.json')).exists()]
assert len(pending) == 13 and pending[0]['id'] == 'person_extension_latency_seed004'
assert all(not (slots/(trial['id']+'.started.json')).exists() and not Path(trial['directory']).exists() for trial in pending)
print(json.dumps({'scope': 'ORIGINAL_PLAN_ONE_PENDING_SLOT_ONLY_NOT_READINESS_OR_FORMAL_ADMISSION',
                  'retained_original_status': old['status'], 'next_slot': pending[0]['id'],
                  'automatic_retry': False, 'old_followon_reused': False}))
PY
bash "$tracking_base/check_humble54_native_idle02.sh"
export HUMBLE22_PROJECT_ROOT="$tracking_dev"
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export PYTHONDONTWRITEBYTECODE=1
export STAGE1_TRANSIENT_DIR=/tmp
source "$tracking_dev/scripts/humble22_env.sh"
exec bash "$tracking_dev/scripts/run_research_session.sh" \
  "$tracking_dev/scripts/run_reliability_v4.py" run --plan "$tracking_plan" --max-new-trials 1
