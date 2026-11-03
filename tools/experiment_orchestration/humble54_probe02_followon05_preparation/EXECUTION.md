# Followon05: new probe02 closure to storage, calibration, and final55 preparation

Status: **CLI WIRING ONLY, NOT STARTED, NOT AN EXECUTABLE RUNNER**.
No command in this card was executed by its preparing agent. `manifest.json`
records actual current small-source hashes and the dependency graph. Future
output hashes, execution times, statuses, and the unfinished validator/staging
source hashes are deliberately absent or null.

## Entry dependency: actual complete new owner closure

Use the new probe02 plan, original core12, and original safety03. Never combine
old probe01 successes with selected new probe02 slots. The running collector04
has `HISTORY={}`: a new unknown short-window result stops collection. A STOPPED
owner or an incomplete 16-slot denominator blocks this entire card. Any proposed
prefix continuation requires a separately reviewed owner chain; this card does
not authorize it or reinterpret a stop as completion.

Candidate's actual validator CLI is:

```powershell
python -B tools/staging/final55_offline_overlay_profile02_20261103/validate_owner_closure.py --receipt-output 'D:/基于yolo和卡尔曼滤波/results/diagnostics/humble54_probe02_followon05/owner_closure_validation.json'
```

Its full production branch is currently disabled until real final owner files
and their fixed hashes are reviewed and bound. Do not bypass that branch or use
`--check-launch` as closure. The latter only reports
`PASS_ACTUAL_LAUNCH_ONLY_NOT_CLOSURE`. Full success must be
`PASS_OWNER_CLOSURE_ONLY_NOT_ENGINEERING_ADMISSION`, retaining 16 original slot
statuses and marker/terminal bindings. The output directory/file must be new.
The validator's finished source SHA must be captured after its implementation
is actually frozen; no future value is supplied here.

Required actual originals are the outer owner04 launch, early native/monitor
snapshots, terminal, actual monitor and WSL held-handle exit observations, final
generic monitor state/end summary, native collector state/terminal/events, and
all 16 new marker/terminal pairs. Verify original core12 closure and safety03
bindings as well. Owner source pins remain launcher `8f6ceb38...`, collector
`bf9168f2...`, monitor `759136d0...`, entry03 `d9cc1f18...`; full values are in
the manifest. The validator consumes real raw files, not a fabricated instance
of the earlier design schema.

The old external `humble54_followon04_closure.py` is reference only. It pins
collector03/old entry and requires at least six historical prefix slots, so it
is incompatible with this new full16/zero-prefix run. Do not edit or invoke it.
The old `run_humble54_closed_followon01.sh` and its outputs likewise remain
untouched.

## Exact new paths and native environment

Run these only after the entry dependencies pass, in the isolated UAVHumble22
window controlled by root. Each step is serial, logs its actual argv, start/end
UTC and exit code, and stops on any nonzero return. Retain partial outputs;
there is no automatic retry or replacement source recording.

```bash
tracking_dev=/root/uav_tracking_fullplan_v4_humble54
tracking_repo=/mnt/d/基于yolo和卡尔曼滤波
tracking_base=/mnt/d/WSL/UAVHumble22-validation
tracking_audit=/root/uav_tracking_snapshot_audit54_tools01
tracking_receipt="$tracking_base/humble54_probe02_closed_followon05"
tracking_tools=/root/uav_tracking_storage_measure54_probe02_tools05
tracking_core="$tracking_dev/results/reliability_v4_humble54_core12_probe01_matrix/plan.json"
tracking_extension="$tracking_dev/results/reliability_v4_humble54_extension16_probe02_matrix/plan.json"
tracking_registry="$tracking_dev/results/reliability_v4_humble54_safety03_audit/registry.json"
tracking_native="$tracking_base/safety54_schema_recovery03/native_recovery03.json"
tracking_sizes="$tracking_dev/results/full28_storage_measurement_probe02_followon05"
tracking_inventory="$tracking_receipt/physical_inventory05.json"
tracking_calibration="$tracking_dev/results/reliability_v4_humble54_development_calibration_probe02_05"
tracking_budget="$tracking_dev/results/full280_storage_budget_probe02_followon05/budget.json"
tracking_assumptions="$tracking_repo/planning/reliability-v4-humble54-storage-assumptions01.json"
```

All new paths must be absent before starting. The receipt directory may then be
created once. Do not pre-create the measurement or calibration directory. Do
not pre-create the budget's parent directory: the existing budget CLI explicitly
requires a new independent parent under results, and `write_new` creates it.

The authoritative plan paths recorded by tools resolve through the frozen
root's results symlink to `/mnt/d/.../results/frozen_fullplan_v4_humble54/...`.
Use canonical resolution when comparing receipt path bindings; preserve the
same raw plan hashes.

The existing native query remains the first native step:

```bash
bash "$tracking_base/check_humble54_native_idle02.sh"
```

It is a point-in-time read-only process query, not a substitute for outer held
handles or original exit receipts. Native cleanup and the real owner terminal
must already be closed.

## Reuse the original storage tools outside frozen54

Current Windows tool bytes were compared directly with commit
`eedd8d9abcd6890b0bd5d0155f76ac08253426b9`; all five below are identical. The
fresh native copy remains an action to perform later, not a claimed deployment.

```bash
test ! -e "$tracking_tools"
test ! -L "$tracking_tools"
mkdir -- "$tracking_tools"
git -C "$tracking_repo" archive --format=tar eedd8d9abcd6890b0bd5d0155f76ac08253426b9 tools | tar -xf - -C "$tracking_tools"
(cd "$tracking_tools" && sha256sum --check --strict - <<'PINS'
bea4c4ba80fe99991c5f13f91c2b00f375c94954af53ffbfa19e47d19f69bb6c  tools/measure_reliability_v4_storage.py
b6bb0f5a402ba1093d1c5d5061c5b2ac0d99b9153e7af73257ae5fdc873b2323  tools/reliability_v4_storage_snapshot_audit.py
e02424cc5df2e103c8994afca8fdeee7fba02c777e0bb50fd7e54576d3e6b4aa  tools/reliability_v4_storage_budget.py
e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e  tools/reliability_v4_guard.py
9339fe72a67b36f987b81a20833953a50ca59302b4157a1230424e8145497ba6  tools/reliability_v4_snapshot_audit.py
PINS
)
```

No original frozen54 source is changed. Keep the independent safety guard's
exact `/root/uav_tracking_snapshot_audit54_tools01/...` path for its own evidence
and downstream registrar; the copied guard is only the storage module's sibling
dependency.

Set the existing environment for each child, using the original wrappers:

```bash
export HUMBLE22_PROJECT_ROOT="$tracking_dev"
export HUMBLE22_ROS_GZ_WS=/root/uav_humble22/ros_gz_shutdown_A01_ws
export HUMBLE22_PX4_ROOT=/root/uav_humble22/PX4-Autopilot-v4mag
export TMPDIR=/tmp STAGE1_TRANSIENT_DIR=/tmp PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
tracking_ros() {
  bash -c 'set -eo pipefail; source "$1/scripts/humble22_env.sh"; shift; exec bash "$@"' \
    _ "$tracking_dev" "$tracking_dev/scripts/run_research_session.sh" "$@"
}
```

## Original actual28 measurement, then physical inventory

```bash
tracking_ros "$tracking_tools/tools/measure_reliability_v4_storage.py" \
  --core-development-plan "$tracking_core" --extension-development-plan "$tracking_extension" \
  --output "$tracking_sizes" --snapshot-audit-registry "$tracking_registry" \
  --snapshot-audit-registry-sha256 ee72b0151a924f7aad0b27459ad2784f7ad1d3d24af6a156d97fec80044332cf \
  --snapshot-audit-native-receipt "$tracking_native" \
  --snapshot-audit-native-receipt-sha256 155275816b1acb09c499b88075e83ffa9bb23195c844d1dbe595efe95a0d50bf
tracking_ros "$tracking_audit/tools/reliability_v4_guard.py" storage-probe \
  --distribution UAVHumble22 --mount /mnt/d --output "$tracking_inventory"
```

The measurement CLI permits original complete PASS/FAIL/INCOMPLETE verdicts but
rejects incomplete/infrastructure-stopped flights, missing independent evidence,
shortened exposure, or archive closure defects. It must measure all 28 distinct
75-second cells. Its saved-audit adapter binds the original canonical core and
safety03, not an old extension directory; new probe02 and core12 have exactly
equal source/model/root/results identities. Files are statted and named small
metadata/text is read; models, bags and VHD payloads are not opened. It does not
rerun evaluators. `summary.json` and 28 per-cell receipts are the outputs.

Inventory runs afterwards, so the earlier measurement intentionally omits the
optional `--physical-inventory` flag. Pass the actual inventory separately to
the budget CLI; do not rerun measurement merely to attach it. Inventory must
report the real host backing of both D-drive results and the WSL VHD without
double-counting one physical disk.

## The two named original velocity recordings, then R0

```bash
tracking_person_trial="$tracking_dev/results/reliability_v4_humble54_core12_probe01_person_stage1_velocity_seed004"
tracking_car_trial="$tracking_dev/results/reliability_v4_humble54_core12_probe01_car_stage1_velocity_seed004"
tracking_ros "$tracking_dev/scripts/export_estimator_replay_v4.py" "$tracking_person_trial" \
  --output "$tracking_calibration/person_export"
tracking_ros "$tracking_dev/scripts/export_estimator_replay_v4.py" "$tracking_car_trial" \
  --output "$tracking_calibration/car_export"
tracking_ros "$tracking_dev/scripts/calibrate_estimator_replay_v4.py" \
  --plan "$tracking_core" --person-arrays "$tracking_calibration/person_export/arrays.json" \
  --car-arrays "$tracking_calibration/car_export/arrays.json" \
  --output "$tracking_calibration/R0_candidate.json"
```

These are existing real CLIs. The future exports necessarily read the two
named bags and produce arrays plus online/native/truth sidecars. No bag was read
while preparing this card. Export non-PASS exits 2: stop and preserve it; do not
substitute another recording. The calibrator checks the named original plan,
records, arrays and sidecars. Its output remains `CANDIDATE_NOT_REGISTERED`,
`DEVELOPMENT_ONLY`, never a formal parameter registration.

## Existing physical budget, then the disabled stage55 boundary

```bash
tracking_ros "$tracking_tools/tools/reliability_v4_storage_budget.py" \
  --core-development-plan "$tracking_core" --extension-development-plan "$tracking_extension" \
  --size-evidence-dir "$tracking_sizes" --physical-inventory "$tracking_inventory" \
  --assumptions "$tracking_assumptions" --output "$tracking_budget"
```

The assumptions file is already real and fixed (`bc0ef3a6...`). It is applicable
only if actual inventory confirms the single `drive_D` backing. Preserve its
15-percent factors, three-raw/two-compressed bound, explicit remaining work and
delivery reserves. A budget command exit 0 only means successful assembly;
inspect every physical/logical `fits_declared_*` field. Insufficient capacity
blocks heavy final55 work and formal admission; do not reduce margins to force
a fit. Per-slot formal capacity guards still apply later.

**There is currently no enabled production profile02 stage CLI.** The real
profile01 `tools/staging/final55_offline_overlay_20261103/stage.py` hardcodes
probe01 and its old contract, and cannot stage this cohort. The real profile02
`check_preparation.py` rejects `--execute`; it is only a metadata checker.
Do not invoke profile01 as a workaround or invent a profile02 filename/hash.

A future reviewed profile02 implementation must bind the actual owner-validator
receipt and exact new plan/contract, reacquire the existing SITL lock, and run
its native idle guard. Reserve fresh paths
`/root/uav_tracking_final55_stage_probe02_05` and
`/mnt/d/WSL/UAVHumble22-validation/final55_stage_probe02_05`, but assign no future
source SHA or outcome. Its actual CLI and source SHA must be added to a new
manifest revision after implementation and review.

After that stage succeeds, the existing cold-build CLI remains:

```bash
/bin/bash /root/uav_tracking_final55_stage_probe02_05/tools/diagnostics/reliability54_build01/prepare_and_validate.sh \
  /root/uav_tracking_fullplan_v4_final55 \
  /mnt/d/基于yolo和卡尔曼滤波/results/frozen_fullplan_v4_final55 \
  /root/uav_tracking_fullplan_v4_humble54
```

This is a later exclusive heavy native window. Do not run the wrapper directly
from immutable frozen54 with its results symlink. Preserve the original cold
source maps and produce a new actual complete map for the new staged descriptor;
its future SHA is unknown. The existing final55 registration and post-admission
execution cards remain the downstream reference, including real target gates,
safety summary, restricted publication, formal plans, replay assembly and guard
seal. They are not executed or enabled by followon05 preparation.
