#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
cd '/mnt/d/基于yolo和卡尔曼滤波'
tracking_link_test_log=/mnt/d/WSL/UAVHumble22-validation/safety54_schema_native03.log
test ! -e "$tracking_link_test_log"
set +e
/root/uav_humble22/venv/bin/python -B -m unittest \
 tests.test_reliability_v4_safety.PublicSafetyLifecycleTests.test_four_original_slots_pass_actual_full_guard_and_readonly_check \
 tests.test_reliability_v4_safety.RawEvaluatorSchemaSafetyTests \
 tests.test_reliability_v4_safety.ResultsSymlinkSafetyTests -v > "$tracking_link_test_log" 2>&1
tracking_link_code=$?
set -e
cat "$tracking_link_test_log"
printf '%s\n' "$tracking_link_code" > /mnt/d/WSL/UAVHumble22-validation/safety54_schema_native03.exit_code.txt
exit "$tracking_link_code"
