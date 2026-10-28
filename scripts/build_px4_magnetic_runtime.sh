#!/usr/bin/env bash
# Build the separately prepared PX4 source, without starting any simulation.
set -eo pipefail
tracking_project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tracking_px4="$(realpath -e -- "${1:?isolated patched PX4 root required}")"
tracking_manifest="${2:?new runtime manifest path required}"
tracking_python="${STAGE1_PYTHON_EXECUTABLE:-/usr/bin/python3}"
if [ -e "$tracking_manifest" ]; then
  echo "Refusing to replace an earlier runtime manifest" >&2
  exit 2
fi
# WSL imports Windows PATH by default. In particular Anaconda/Library/include
# must never become a Linux CMake search prefix.
export PATH="$(dirname -- "$tracking_python"):/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
unset CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH PKG_CONFIG_PATH
unset CMAKE_PREFIX_PATH AMENT_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH PYTHONPATH PYTHONHOME
source "$tracking_project/scripts/source_ros_environment.sh"
"$tracking_python" - "$tracking_project" "$tracking_px4" <<'PY_CHECK_SOURCE'
from pathlib import Path
import sys
sys.path.insert(0, str(Path(sys.argv[1]) / 'scripts'))
from prepare_px4_magnetic_compatibility import check_source
check_source(Path(sys.argv[2]), patched=True)
print('Pinned isolated PX4 magnetic source verified')
PY_CHECK_SOURCE
export GZ_VERSION=harmonic CMAKE_BUILD_PARALLEL_LEVEL=2
tracking_log="$tracking_project/results/px4_magnetic_build_$(date -u +%Y%m%dT%H%M%S%N).log"
mkdir -p "$tracking_project/results"
echo "PX4 build log: $tracking_log"
# The pinned upstream GNU Make generator does not connect the event scanner's
# dependency on dds_topics.h across directories. Build its declared generator
# target first; never copy a generated header from an earlier firmware build.
make -C "$tracking_px4" px4_sitl_default topic_bridge_files PX4_MAKE_ARGS=-j2 PYTHON_EXECUTABLE="$tracking_python" 2>&1 | tee "$tracking_log"
make -C "$tracking_px4" px4_sitl_default PX4_MAKE_ARGS=-j2 PYTHON_EXECUTABLE="$tracking_python" 2>&1 | tee -a "$tracking_log"
mkdir -p "$(dirname -- "$tracking_manifest")"
"$tracking_python" "$tracking_project/scripts/prepare_px4_magnetic_compatibility.py" verify-runtime \
  --px4-root "$tracking_px4" --output "$tracking_manifest"
