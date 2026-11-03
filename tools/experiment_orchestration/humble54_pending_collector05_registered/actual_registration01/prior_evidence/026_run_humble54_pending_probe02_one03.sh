#!/usr/bin/env bash
# One supervised, previously unattempted slot of the unchanged original matrix.
# This entry does not retry a terminal slot or authorize formal experiments.
set -euo pipefail
test "${WSL_DISTRO_NAME:-}" = UAVHumble22
test "$#" -eq 1
tracking_next=$1
tracking_dev=/root/uav_tracking_fullplan_v4_humble54
tracking_plan="$tracking_dev/results/reliability_v4_humble54_extension16_probe02_matrix/plan.json"
python3 -B - "$tracking_plan" "$tracking_next" <<'PY'
from pathlib import Path
import hashlib, json, sys
plan_path, expected_id = Path(sys.argv[1]), sys.argv[2]
raw = plan_path.read_bytes()
assert hashlib.sha256(raw).hexdigest() == '1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54'
plan = json.loads(raw)
assert plan['mode'] == 'EXTENSION_PROBE' and plan['selected_seeds'] == [4]
slots = Path(plan['output']) / 'slots'
# This complete new matrix inherits no incomplete exception from the old matrix.
historical = {}
for slot_id, digest in historical.items():
    record_bytes = (slots/(slot_id+'.json')).read_bytes()
    assert hashlib.sha256(record_bytes).hexdigest() == digest
    assert json.loads(record_bytes)['status'] == 'INCOMPLETE_EVIDENCE'
pending = []
for trial in plan['trials']:
    terminal = slots/(trial['id']+'.json')
    if not terminal.exists():
        assert not (slots/(trial['id']+'.started.json')).exists()
        assert not Path(trial['directory']).exists()
        pending.append(trial)
        continue
    record = json.loads(terminal.read_bytes())
    assert record['execution_status'] == 'COMPLETED' and record['infrastructure_stop'] is False
    assert type(record['flight_exit_code']) is int and record['flight_exit_code'] == 0
    assert record['cleanup']['residual_processes'] == []
    entries = {entry['kind']: entry for entry in record['evaluations']}
    assert all(entries[kind]['result'] == 'PASS' for kind in ('source_clock', 'native_startup'))
    surface = json.loads(Path(entries['surface_flight']['report']).read_bytes())
    long = [row for row in surface['occlusions'] if row['kind'] == 'long']
    assert len(long) == 1
    safety = ('recorded_close_event', 'shutter_close_service_succeeded', 'shutter_open_service_succeeded',
              'shutter_close_ack_before_open_request', 'lost_observed_for_long_occlusion',
              'hover_observed_for_long_occlusion', 'sustained_low_speed_after_hover',
              'no_automatic_recovery_after_long_loss', 'no_tracking_control_before_reselection_after_long_loss')
    assert all(long[0]['checks'][key] is True for key in safety)
assert pending and pending[0]['id'] == expected_id
print(json.dumps({'scope': 'SUPERVISED_NEW_COMPLETE_DEVELOPMENT_MATRIX_NOT_READINESS',
                  'next_slot': expected_id, 'remaining_unattempted_before_start': len(pending),
                  'historical_incomplete_retained': sorted(historical), 'automatic_retry': False}))
PY
bash /mnt/d/WSL/UAVHumble22-validation/check_humble54_native_idle02.sh
export HUMBLE22_PROJECT_ROOT="$tracking_dev"
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export PYTHONDONTWRITEBYTECODE=1
export STAGE1_TRANSIENT_DIR=/tmp
source "$tracking_dev/scripts/humble22_env.sh"
exec bash "$tracking_dev/scripts/run_research_session.sh" \
  "$tracking_dev/scripts/run_reliability_v4.py" run --plan "$tracking_plan" --max-new-trials 1
