#!/usr/bin/env bash
set -eo pipefail
benchmark_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == "--execute" ]]; then
  source /opt/ros/humble/setup.bash
fi
export PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1
exec /usr/bin/python3 -B "$benchmark_dir/benchmark.py" "$@"
