#!/usr/bin/env bash
# Build only: isolated Fast DDS 2.6.12 with upstream listener lifecycle fixes.
# No installed ROS library or prior study is overwritten or activated.
set -euo pipefail
[[ "${WSL_DISTRO_NAME:-}" == UAVHumble22 ]] || { echo 'Use UAVHumble22.' >&2; exit 2; }
tracking_dds_archive="${1:?Provide the pinned ros-humble-fastrtps orig tar.gz}"
tracking_dds_root="${2:?Provide a NEW independent build/install root}"
tracking_dds_archive="$(realpath -e -- "$tracking_dds_archive")"
tracking_dds_root="$(realpath -m -- "$tracking_dds_root")"
tracking_dds_project="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tracking_dds_patch="$tracking_dds_project/patches/fastdds_2_6_12_listener_lifecycle_A01.patch"
[[ ! -e "$tracking_dds_root" && ! -L "$tracking_dds_root" ]] || { echo 'Destination must be new.' >&2; exit 2; }
[[ "$(sha256sum "$tracking_dds_archive" | cut -d ' ' -f1)" == 34384c79ad4902d5555a811956596b83c7da190bfa6142f2f09044f10cd2becb ]] || { echo 'Source archive differs.' >&2; exit 2; }
[[ "$(sha256sum "$tracking_dds_patch" | cut -d ' ' -f1)" == a1de559704415dd11045cc30b7b51720c2740bcf4baf23f44fd4da382f17bddc ]] || { echo 'Reviewed patch differs.' >&2; exit 2; }
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH CMAKE_MODULE_PATH
unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH CPATH CPLUS_INCLUDE_PATH C_INCLUDE_PATH LIBRARY_PATH PKG_CONFIG_PATH fastcdr_DIR FastCDR_DIR FASTCDR_ROOT FASTDDS_ROOT
set +u
source /opt/ros/humble/setup.bash
set -u
export CMAKE_BUILD_PARALLEL_LEVEL=2 MAKEFLAGS=-j2
mkdir -p "$tracking_dds_root/source" "$tracking_dds_root/tmp"
export TMPDIR="$tracking_dds_root/tmp"
tar --extract --gzip --file "$tracking_dds_archive" --directory "$tracking_dds_root/source" --strip-components=1
cd "$tracking_dds_root/source"
git apply --check "$tracking_dds_patch"
git apply "$tracking_dds_patch"
/usr/bin/python3 - "$tracking_dds_root" "$tracking_dds_archive" "$tracking_dds_patch" "$tracking_dds_project/scripts/build_humble22_fastdds_listener.sh" <<'PY'
import hashlib, json, pathlib, subprocess, sys
root, archive, patch, script = map(pathlib.Path, sys.argv[1:])
files = {name: {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
         for name, path in [('source_archive', archive), ('patch', patch), ('build_script', script)]}
versions = subprocess.run(['dpkg-query', '-W', '-f=${Package}=${Version}\n',
    'ros-humble-fastrtps', 'ros-humble-fastcdr', 'ros-humble-foonathan-memory-vendor',
    'libasio-dev', 'libssl-dev', 'libtinyxml2-dev'], check=True, text=True, capture_output=True).stdout
(root / 'build_inputs.json').write_text(json.dumps({'scope': 'ISOLATED_DEPENDENCY_BUILD_NOT_RUNTIME_ACCEPTANCE',
    'files': files, 'installed_build_dependencies': versions, 'upstream_commits': [
    '0014b017b3cd1f001b0b39b759120073b37ed283', '2078f7f7e7068651b003b83a2f4713342bf51e6b'],
    'activation_performed': False}, indent=2) + '\n', encoding='utf-8')
PY
cmake -S "$tracking_dds_root/source" -B "$tracking_dds_root/build" \
  -DCMAKE_INSTALL_PREFIX="$tracking_dds_root/install" \
  -DCMAKE_PREFIX_PATH=/opt/ros/humble -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DBUILD_SHARED_LIBS=ON -DBUILD_TESTING=OFF -DINSTALL_EXAMPLES=OFF -DSECURITY=ON \
  -DEPROSIMA_BUILD=OFF -DCOMPILE_TOOLS=OFF -DCOMPILE_EXAMPLES=OFF \
  -DCOMPILE_DOCUMENTATION=OFF -DTHIRDPARTY=OFF -DTHIRDPARTY_UPDATE=OFF \
  -DAPPEND_PROJECT_NAME_TO_INCLUDEDIR=ON
cmake --build "$tracking_dds_root/build" --parallel 2
cmake --install "$tracking_dds_root/build"
sha256sum "$tracking_dds_root/install/lib/libfastrtps.so.2.6.12"
echo 'Build complete. Activation, loaded-library provenance, teardown regression and fresh flight acceptance remain required.'
