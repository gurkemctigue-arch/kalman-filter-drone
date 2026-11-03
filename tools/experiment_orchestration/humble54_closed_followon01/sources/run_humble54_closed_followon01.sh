#!/usr/bin/env bash
# Prepared only. Root's Windows waiter must first close the original invocation.
# No retries: any failure preserves this receipt directory and partial outputs.
set -euo pipefail
test "${WSL_DISTRO_NAME:-}" = UAVHumble22
tracking_dev=/root/uav_tracking_fullplan_v4_humble54
tracking_base=/mnt/d/WSL/UAVHumble22-validation
tracking_receipt="$tracking_base/humble54_closed_followon01"
tracking_tools=/root/uav_tracking_storage_measure54_tools02
tracking_core="$tracking_dev/results/reliability_v4_humble54_core12_probe01_matrix/plan.json"
tracking_extension="$tracking_dev/results/reliability_v4_humble54_extension16_probe01_matrix/plan.json"
tracking_registry="$tracking_dev/results/reliability_v4_humble54_safety03_audit/registry.json"
tracking_native="$tracking_base/safety54_schema_recovery03/native_recovery03.json"
tracking_sizes="$tracking_dev/results/full28_storage_measurement_audit03"
tracking_calibration="$tracking_dev/results/reliability_v4_humble54_development_calibration01"
tracking_inventory="$tracking_receipt/physical_inventory03.json"
test ! -e "$tracking_receipt"
test ! -L "$tracking_receipt"
mkdir -- "$tracking_receipt"

python3 -B - "$tracking_receipt" "$0" <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, sys
folder, source = map(Path, sys.argv[1:])
with (folder/'started.json').open('x') as stream:
    json.dump({'kind':'ACTUAL_HUMBLE54_CLOSED_FOLLOWON_INVOCATION_NOT_ADMISSION',
        'started_utc':datetime.now(timezone.utc).isoformat(),
        'script':{'path':str(source.resolve(strict=True)), 'sha256':hashlib.sha256(source.read_bytes()).hexdigest()},
        'scope':'Actual invocation only; prerequisite checks and all task outcomes still pending.'}, stream, indent=2)
PY

tracking_finish() {
  tracking_rc=$?
  trap - EXIT
  python3 -B - "$tracking_receipt" "$tracking_rc" <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import json, sys
folder, code = Path(sys.argv[1]), int(sys.argv[2])
with (folder/'outcome.json').open('x') as stream:
    json.dump({'kind':'ACTUAL_HUMBLE54_CLOSED_FOLLOWON_TERMINAL',
        'finished_utc':datetime.now(timezone.utc).isoformat(), 'exit_code':code,
        'status':'COMPLETED' if code == 0 else 'STOPPED',
        'claim_boundary':'Only actual logged steps; no budget assumptions, final55 build, registration, admission or formal flight.'}, stream, indent=2)
PY
  exit "$tracking_rc"
}
trap tracking_finish EXIT

tracking_step() {
  local tracking_name=$1
  shift
  python3 -B - "$tracking_receipt" "$tracking_name" "$@" <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import json, sys
folder, name = Path(sys.argv[1]), sys.argv[2]
with (folder/(name+'.started.json')).open('x') as stream:
    json.dump({'started_utc':datetime.now(timezone.utc).isoformat(), 'argv':sys.argv[3:],
        'stdout':str(folder/(name+'.stdout.log')), 'stderr':str(folder/(name+'.stderr.log'))}, stream, indent=2)
PY
  local tracking_code=0
  set +e
  "$@" >"$tracking_receipt/$tracking_name.stdout.log" 2>"$tracking_receipt/$tracking_name.stderr.log"
  tracking_code=$?
  set -e
  python3 -B - "$tracking_receipt" "$tracking_name" "$tracking_code" <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import json, sys
folder, name, code = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
started = json.loads((folder/(name+'.started.json')).read_text())
with (folder/(name+'.terminal.json')).open('x') as stream:
    json.dump({**started, 'finished_utc':datetime.now(timezone.utc).isoformat(), 'exit_code':code}, stream, indent=2)
PY
  printf '%s\n' "followon_step=$tracking_name actual_exit=$tracking_code"
  return "$tracking_code"
}

# This inline program reads named small metadata only; no runtime/model import.
tracking_step 01_closed_metadata python3 -B - "$tracking_dev" "$tracking_base" "$tracking_tools" "$tracking_sizes" "$tracking_calibration" <<'PY'
from pathlib import Path
from collections import Counter
import hashlib, json, os, sys
dev, base, tools, sizes, calibration = map(Path, sys.argv[1:])
def require(ok, message):
    if not ok: raise RuntimeError(message)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def sealed(value, field):
    return hashlib.sha256(json.dumps({k:v for k,v in value.items() if k != field},
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
def bound(binding):
    path = Path(binding['path'])
    require(path.is_absolute() and path.is_file() and sha(path) == binding['sha256'], 'Changed saved binding: '+str(path))
    return read(path)
def no_live_owner(owner):
    pid = owner['pid']; current = Path('/proc')/str(pid)
    if current.is_dir():
        try:
            ticks = int((current/'stat').read_text().rsplit(')', 1)[1].split()[19])
            same = (Path('/proc/sys/kernel/random/boot_id').read_text().strip() == owner['boot_id']
                    and ticks == owner['start_ticks'])
        except FileNotFoundError: same = False
        require(not same, 'Original Linux owner is still alive')
pins = {
 'core':('reliability_v4_humble54_core12_probe01_matrix', 'ed88783162991c151ab3d537d4eb7d3546b3688339a06db6f35b7f2ef7c48d4b',
         '3e34bdfae710f7b518a5f5fd1506054b03d3275c89e2f827ae136bfa2f682a31',12,'PROBE','humble54_core12_owner01'),
 'extension':('reliability_v4_humble54_extension16_probe01_matrix', 'f32fb17a77670f5c774076ff9bf4b752b3e91eea4f28021efb826ed9b8520055',
         'ded5ab19b72f53c932cbea2044561a4e2fe937445cb07eb9525e9e0be5fc9761',16,'EXTENSION_PROBE','humble54_extension16_owner01')}
plans, records, observations = {}, {}, {}
for label, (matrix, file_sha, digest, count, mode, owner_name) in pins.items():
    path = dev/'results'/matrix/'plan.json'; plan = read(path)
    require(sha(path) == file_sha and plan['plan_sha256'] == digest == sealed(plan, 'plan_sha256'), 'Plan double SHA differs: '+label)
    require(plan['mode'] == mode and plan['frozen_root'] == str(dev) and len(plan['trials']) == count
            and plan['selected_seeds'] == [4], 'Canonical development matrix differs')
    owner = read(dev/'results'/owner_name/'owner_terminal.json')
    require(owner == read(dev/'results'/owner_name/'owner_state.json') and owner['status'] == 'COMPLETED'
            and owner['active_slot'] is None and owner['all_slots_terminal'] is True
            and owner['pending_ids'] == [] and owner['planned_count'] == count
            and owner['plan_file_sha256'] == file_sha and owner['plan_sha256'] == digest, 'Owner not closed: '+label)
    no_live_owner(owner['owner'])
    slots = Path(plan['output'])/'slots'; ids = {trial['id'] for trial in plan['trials']}
    starts = {p.name.removesuffix('.started.json') for p in slots.glob('*.started.json')}
    require(starts == ids, 'Missing/foreign/unclosed START denominator: '+label)
    rows = {}
    for trial in plan['trials']:
        record_path = slots/(trial['id']+'.json'); row = read(record_path)
        start = read(slots/(trial['id']+'.started.json'))
        require(row['record_sha256'] == sealed(row, 'record_sha256') and row['id'] == trial['id']
                and row['plan_sha256'] == digest and start['id'] == trial['id'] and start['plan_sha256'] == digest
                and row['started_utc'] == start['started_utc'], 'Original terminal/START binding differs')
        require(row['status'] in {'PASS','FAIL','INCOMPLETE_EVIDENCE','EVALUATION_PENDING'}
                and row['execution_status'] == 'COMPLETED' and row['infrastructure_stop'] is False
                and type(row['flight_exit_code']) is int and row['flight_exit_code'] == 0, 'Incomplete/INFRA flight: '+trial['id'])
        if label == 'core': require(row['status'] == 'PASS', 'Core development did not fully PASS')
        rows[trial['id']] = row
    require(owner['status_counts'] == dict(Counter(row['status'] for row in rows.values())), 'Owner terminal denominator differs')
    plans[label], records[label] = plan, rows
    observations[label] = {'plan_file_sha256':file_sha, 'plan_sha256':digest, 'terminal_count':len(rows),
                           'status_counts':dict(Counter(row['status'] for row in rows.values())), 'unclosed_started_ids':[]}
require(all(plans['core'][key] == plans['extension'][key] for key in ('source_hashes','model_hashes','frozen_root','results_root')), 'Core/extension source identity differs')
safety = dev/'results/reliability_v4_humble54_safety03_audit'
registry_path = safety/'registry.json'
require(sha(registry_path) == 'ee72b0151a924f7aad0b27459ad2784f7ad1d3d24af6a156d97fec80044332cf', 'Registry03 bytes differ')
registry = read(registry_path)
bound(registry['snapshot_audit_contract'])
native_path = base/'safety54_schema_recovery03/native_recovery03.json'
require(sha(native_path) == '155275816b1acb09c499b88075e83ffa9bb23195c844d1dbe595efe95a0d50bf', 'Native03 bytes differ')
owner = read(safety/'owner_terminal.json')
require(owner == read(safety/'owner_state.json') and owner['status'] == 'COMPLETED'
        and owner['active_slot'] is None and owner['all_engineering_pass'] is True
        and owner['planned_count'] == owner['attempted_count'] == 4 and owner['pending_count'] == 0, 'Safety03 owner not closed')
no_live_owner(owner['owner'])
terminal = bound(owner['execution_terminal'])
require(terminal['status'] == 'COMPLETED' and type(terminal['returncode']) is int and terminal['returncode'] == 0
        and terminal['planned_count'] == terminal['attempted_count'] == 4 and terminal['pending_count'] == 0
        and terminal['unclosed_started_ids'] == [] and terminal['cleanup']['residual_processes'] == [], 'Safety03 execution not closed')
require(terminal['registry'] == owner['registry'] == {'path':str(registry_path.resolve(strict=True)),
        'sha256':'ee72b0151a924f7aad0b27459ad2784f7ad1d3d24af6a156d97fec80044332cf'}, 'Safety03 registry chain differs')
facts = bound(terminal['facts']); guard = bound(terminal['guard_validation'])
require(facts['result'] == guard['result'] == 'PASS' and facts['planned_count'] == facts['attempted_count'] == 4
        and facts['pending_count'] == 0 and facts['unclosed_started_ids'] == [], 'Saved guard/facts incomplete')
require({s['id'] for s in terminal['slots']} == {t['id'] for t in registry['trials']} and len(terminal['slots']) == 4, 'Safety denominator differs')
for slot in terminal['slots']:
    row = bound(slot['terminal'])
    require(slot['status'] == row['status'] == 'PASS' and row['id'] == slot['id'] and row['infrastructure_stop'] is False
            and row['cleanup']['residual_processes'] == [], 'Safety original terminal did not PASS')
    require(set(row['executions']) == {'flight','source_clock','native_startup','specialized','terminal_speed'}
            and all(type(item['returncode']) is int and item['returncode'] == 0 and item.get('error') is None
                    for item in row['executions'].values()), 'Safety execution error')
for output in (tools, sizes, calibration):
    require(not output.exists() and not output.is_symlink(), 'New output already exists: '+str(output))
idle = base/'check_humble54_native_idle02.sh'
require(sha(idle) == '87c0d015a92eafc3211bd9d2fdb5cf9231332a761d5b656c78419cb002ca1e2b', 'Reviewed idle query changed')
for name, digest in {'scripts/export_estimator_replay_v4.py':'08edc1f57a5f1d8de4e93d3a00f8aefdc6b7fb72aab52f815c756d017d1a72ac',
                     'scripts/calibrate_estimator_replay_v4.py':'0a6f3982e395024d7abf3da43e2e685dc0d88157686496dd2cd3e0296f462fe9'}.items():
    require(plans['core']['source_hashes'][name] == sha(dev/name) == digest, 'Original export/calibrator source differs')
print(json.dumps({'kind':'ACTUAL_CLOSED_METADATA_PRECHECK_ONLY', 'development':observations, 'safety03':'FOUR_ORIGINAL_PASS_WITH_SAVED_GUARD_BINDINGS',
    'person_trial':next(t['directory'] for t in plans['core']['trials'] if t['id']=='person_stage1_velocity_seed004'),
    'car_trial':next(t['directory'] for t in plans['core']['trials'] if t['id']=='car_stage1_velocity_seed004'),
    'claim_boundary':'Small saved metadata checks only; no repeated validator, bag/model read or admission.'},ensure_ascii=False))
PY

# The existing query only reads /proc and never kills. Invoke by script path;
# this wrapper's argv contains no graph-name needles and is not mistaken for one.
tracking_step 02_native_idle bash "$tracking_base/check_humble54_native_idle02.sh"

tracking_repo=/mnt/d/基于yolo和卡尔曼滤波
tracking_step 03_stage_reviewed_tools bash -c '
set -euo pipefail
repo=$1; destination=$2; commit=eedd8d9abcd6890b0bd5d0155f76ac08253426b9
test "$(git -C "$repo" rev-parse "$commit^{commit}")" = "$commit"
test ! -e "$destination"; test ! -L "$destination"
mkdir -- "$destination"
git -C "$repo" archive --format=tar "$commit" tools | tar -xf - -C "$destination"
cd -- "$destination"
sha256sum -c - <<"PINS"
bea4c4ba80fe99991c5f13f91c2b00f375c94954af53ffbfa19e47d19f69bb6c  tools/measure_reliability_v4_storage.py
b6bb0f5a402ba1093d1c5d5061c5b2ac0d99b9153e7af73257ae5fdc873b2323  tools/reliability_v4_storage_snapshot_audit.py
e02424cc5df2e103c8994afca8fdeee7fba02c777e0bb50fd7e54576d3e6b4aa  tools/reliability_v4_storage_budget.py
e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e  tools/reliability_v4_guard.py
9339fe72a67b36f987b81a20833953a50ca59302b4157a1230424e8145497ba6  tools/reliability_v4_snapshot_audit.py
PINS
' _ "$tracking_repo" "$tracking_tools"

export HUMBLE22_PROJECT_ROOT="$tracking_dev"
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export TMPDIR=/tmp STAGE1_TRANSIENT_DIR=/tmp PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
# Source the existing environment per child; setup failures get the same logs/exit.
tracking_ros_step() {
  local tracking_name=$1
  shift
  tracking_step "$tracking_name" bash -c 'set -eo pipefail; source "$1/scripts/humble22_env.sh"; shift; exec bash "$@"' \
    _ "$tracking_dev" "$tracking_dev/scripts/run_research_session.sh" "$@"
}
tracking_ros_step 04_measure_all28 "$tracking_tools/tools/measure_reliability_v4_storage.py" \
  --core-development-plan "$tracking_core" --extension-development-plan "$tracking_extension" \
  --output "$tracking_sizes" --snapshot-audit-registry "$tracking_registry" \
  --snapshot-audit-registry-sha256 ee72b0151a924f7aad0b27459ad2784f7ad1d3d24af6a156d97fec80044332cf \
  --snapshot-audit-native-receipt "$tracking_native" \
  --snapshot-audit-native-receipt-sha256 155275816b1acb09c499b88075e83ffa9bb23195c844d1dbe595efe95a0d50bf
tracking_ros_step 05_physical_inventory /root/uav_tracking_snapshot_audit54_tools01/tools/reliability_v4_guard.py \
  storage-probe --distribution UAVHumble22 --mount /mnt/d --output "$tracking_inventory"

tracking_person_trial="$(python3 -B -c 'import json,sys; print(json.load(open(sys.argv[1]))["person_trial"])' "$tracking_receipt/01_closed_metadata.stdout.log")"
tracking_car_trial="$(python3 -B -c 'import json,sys; print(json.load(open(sys.argv[1]))["car_trial"])' "$tracking_receipt/01_closed_metadata.stdout.log")"
test ! -e "$tracking_calibration"
test ! -L "$tracking_calibration"
tracking_ros_step 06_person_export "$tracking_dev/scripts/export_estimator_replay_v4.py" "$tracking_person_trial" \
  --output "$tracking_calibration/person_export"
tracking_ros_step 07_car_export "$tracking_dev/scripts/export_estimator_replay_v4.py" "$tracking_car_trial" \
  --output "$tracking_calibration/car_export"
tracking_ros_step 08_R0_candidate "$tracking_dev/scripts/calibrate_estimator_replay_v4.py" \
  --plan "$tracking_core" --person-arrays "$tracking_calibration/person_export/arrays.json" \
  --car-arrays "$tracking_calibration/car_export/arrays.json" --output "$tracking_calibration/R0_candidate.json"
