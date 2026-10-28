#!/usr/bin/env bash
set -euo pipefail
task_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
task_asset_root="$task_repo/ros2_ws/src/uav_tracking_bringup/models"
task_download_root="$task_repo/results/asset_validation/source_archives"
mkdir -p "$task_asset_root" "$task_download_root"
for task_entry in 'Walking%20person:3:fuel_walking_person' 'Prius%20Hybrid:3:fuel_prius_hybrid' 'Hatchback:3:fuel_hatchback' 'SUV:4:fuel_suv'; do
  IFS=: read -r task_name task_version task_dir <<< "$task_entry"
  task_url="https://fuel.gazebosim.org/1.0/OpenRobotics/models/$task_name/$task_version/$task_name.zip"
  curl --fail --location --retry 3 "$task_url" -o "$task_download_root/$task_dir.zip"
  mkdir -p "$task_asset_root/$task_dir"
  unzip -o -q "$task_download_root/$task_dir.zip" -d "$task_asset_root/$task_dir"
  curl --fail --location --retry 3 "https://fuel.gazebosim.org/1.0/OpenRobotics/models/$task_name" -o "$task_download_root/$task_dir.metadata.json"
  sha256sum "$task_download_root/$task_dir.zip"
done
