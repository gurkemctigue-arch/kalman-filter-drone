#!/usr/bin/env bash
# Four serial real visual SITL trials. A unique prefix preserves all prior evidence.
set -euo pipefail
stage1_project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
stage1_prefix="${1:-stage1_acceptance}"
if [[ ! "$stage1_prefix" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "trial prefix must contain only letters, numbers, underscores or hyphens" >&2
  exit 2
fi
stage1_trials=()
for stage1_condition in person:velocity car:velocity person:position car:position; do
  stage1_class="${stage1_condition%:*}"
  stage1_mode="${stage1_condition#*:}"
  stage1_name="${stage1_prefix}_${stage1_class}_${stage1_mode}"
  stage1_trials+=("$stage1_name")
  bash "$stage1_project/scripts/run_stage1_trial.sh" --class "$stage1_class" \
    --name "$stage1_name" --command-mode "$stage1_mode" --duration 43 --wall-timeout 180 \
    --occlusions --short-occlusion-s 0.2 --reselect-after-loss
  stage1_distance=5
  if [ "$stage1_class" = car ]; then stage1_distance=9; fi
  bash "$stage1_project/scripts/evaluate_stage1_flight.sh" "$stage1_project/results/$stage1_name/rosbag" \
    --target-class "$stage1_class" --desired-distance-m "$stage1_distance" \
    --output "$stage1_project/results/$stage1_name/offline_evaluation.json" \
    --telemetry-jsonl "$stage1_project/results/$stage1_name/telemetry.jsonl" \
    --monitor-summary "$stage1_project/results/$stage1_name/summary.json"
done
python3 "$stage1_project/scripts/summarize_stage1_acceptance.py" \
  --results-root "$stage1_project/results" --trials "${stage1_trials[@]}" \
  --output "$stage1_project/results/${stage1_prefix}_report.json"
