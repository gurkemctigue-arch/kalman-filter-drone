#!/usr/bin/env bash
# Isolated Jammy setup. Each phase must be invoked explicitly; no phase runs
# import or terminates another WSL distribution. Run only after the coordinator
# has released the current simulation's resources.
set -euo pipefail
humble22_phase="${1:-help}"
humble22_prefix=/root/uav_humble22
humble22_project="${HUMBLE22_PROJECT_ROOT:-$humble22_prefix/project}"
if [[ "$humble22_project" != "$humble22_prefix/project" && ! "$humble22_project" =~ ^/root/uav_tracking_fullplan_[a-zA-Z0-9_]+$ ]]; then
  echo 'HUMBLE22_PROJECT_ROOT must identify the prepared project or an independent frozen study.' >&2; exit 2
fi
humble22_px4_root="${HUMBLE22_PX4_ROOT:-$humble22_prefix/PX4-Autopilot}"
case "$humble22_px4_root" in
  "$humble22_prefix/PX4-Autopilot"|"$humble22_prefix/PX4-Autopilot-v4mag") ;;
  *) echo 'HUMBLE22_PX4_ROOT must identify an independent Humble PX4 checkout.' >&2; exit 2;;
esac
humble22_source="${2:-}"
humble22_ros_gz_commit=856e319ee4da713609b3f6e58c74ac8db7662482
humble22_px4_commit=d6f12ad1c4f70ad3230afd7d86e971421e02fef4
humble22_msgs_commit=86d8239e962f6939e05c3737784f60c02fa884db
humble22_agent_commit=73622810d984349b80bbac0ef55fc0b694d62222
if [[ "$humble22_phase" == help ]]; then
  echo 'Usage: setup_humble22.sh {packages|repositories|python|build|build-ros|build-agent|build-px4|build-project|verify} [source project path]'
  echo 'repositories requires the Windows project source path, e.g. /mnt/d/... .'
  exit 0
fi
case "$humble22_phase" in packages|repositories|python|build|build-ros|build-agent|build-px4|build-project|verify) ;; *) exit 2;; esac
source /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 22.04 || "${WSL_DISTRO_NAME:-}" != UAVHumble22 ]]; then
  echo 'Refusing setup outside Ubuntu 22.04 / WSL UAVHumble22.' >&2
  exit 2
fi
if [[ "$EUID" != 0 ]]; then echo 'Run as root in the isolated distribution.' >&2; exit 2; fi
if [[ -d /opt/ros/jazzy || ( -n "${ROS_DISTRO:-}" && "$ROS_DISTRO" != humble ) ]]; then
  echo 'Unexpected Jazzy/mixed ROS environment; start from the isolated Jammy rootfs.' >&2
  exit 2
fi
# WSL appends Windows PATH entries by default. CMake can otherwise discover
# Windows Anaconda protobuf/gflags headers under /mnt/d before Linux packages.
# Limit only this setup process; do not modify global WSL/Windows settings.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset CMAKE_PREFIX_PATH CMAKE_MODULE_PATH CPATH CPLUS_INCLUDE_PATH C_INCLUDE_PATH LIBRARY_PATH PKG_CONFIG_PATH
humble22_evidence=/mnt/d/WSL/UAVHumble22-validation/logs
mkdir -p "$humble22_prefix" "$humble22_evidence"
if [[ ! -e "$humble22_prefix/logs" ]]; then
  ln -s "$humble22_evidence" "$humble22_prefix/logs"
elif [[ "$(readlink -f "$humble22_prefix/logs")" != "$humble22_evidence" ]]; then
  echo 'Unexpected evidence directory; do not overwrite prior installation logs.' >&2; exit 2
fi
humble22_log="$humble22_prefix/logs/${humble22_phase}_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$humble22_log") 2>&1
echo "Phase=$humble22_phase UTC=$(date -u --iso-8601=seconds) distro=$WSL_DISTRO_NAME"
export DEBIAN_FRONTEND=noninteractive
export GZ_VERSION=harmonic IGNITION_VERSION=''
humble22_jobs="${HUMBLE22_BUILD_JOBS:-2}"
if [[ "$humble22_jobs" != 1 && "$humble22_jobs" != 2 ]]; then
  echo 'HUMBLE22_BUILD_JOBS must be 1 or 2.' >&2; exit 2
fi
export MAKEFLAGS="-j$humble22_jobs" CMAKE_BUILD_PARALLEL_LEVEL="$humble22_jobs"
export LANG=C.UTF-8 LC_ALL=C.UTF-8
if [[ -f "$humble22_prefix/rosdep.env" ]]; then source "$humble22_prefix/rosdep.env"; fi

humble22_source_ros() {
  set +u
  source /opt/ros/humble/setup.bash
  source "$humble22_prefix/venv/bin/activate"
  set -u
}
humble22_repo() {
  local url="$1" tag="$2" expected="$3" destination="$4"
  if [[ ! -d "$destination/.git" ]]; then
    if [[ -e "$destination" ]]; then echo "Refusing non-repository destination $destination" >&2; exit 2; fi
    git clone --depth 1 --branch "$tag" "$url" "$destination"
  fi
  if [[ "$(git -C "$destination" rev-parse HEAD)" != "$expected" ]]; then
    echo "Repository commit mismatch at $destination; no automatic reset is allowed." >&2
    exit 2
  fi
  if [[ -n "$(git -C "$destination" status --porcelain --untracked-files=no)" ]]; then
    echo "Repository has local modifications: $destination" >&2
    exit 2
  fi
  printf '%s %s\n' "$expected" "$url"
}

case "$humble22_phase" in
  packages)
    apt-get update
    apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg lsb-release locales git build-essential cmake ninja-build \
      pkg-config rsync unzip zip zstd ripgrep python3-dev python3-pip python3-venv \
      python3-numpy python3-opencv python3-matplotlib python3-scipy python3-yaml python3-cairo \
      python3-jinja2 python3-empy python3-packaging python3-serial python3-toml \
      protobuf-compiler libeigen3-dev libasio-dev libtinyxml2-dev libxml2-utils \
      libssl-dev libxml2-dev libgflags-dev libgl1-mesa-dri mesa-utils
    locale-gen en_US.UTF-8
    curl -fL --retry 4 https://repo.ros2.org/repos.key -o "$humble22_prefix/ros.key"
    humble22_ros_fingerprint="$(gpg --batch --show-keys --with-colons "$humble22_prefix/ros.key" | awk -F: '$1=="fpr" {print $10; exit}')"
    if [[ "$humble22_ros_fingerprint" != C1CF6E31E6BADE8868B172B4F42ED6FBAB17C654 ]]; then
      echo 'Unexpected ROS signing key fingerprint.' >&2; exit 2
    fi
    gpg --batch --yes --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg "$humble22_prefix/ros.key"
    # HTTP transport follows ROS's documented repository layout. Signed Release
    # metadata and package hashes remain mandatory; there is no trusted=yes.
    printf 'deb [arch=amd64 signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu jammy main\n' > /etc/apt/sources.list.d/uav-humble22-ros2.list
    curl -fL --retry 4 https://packages.osrfoundation.org/gazebo.gpg -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
    gpg --batch --show-keys --with-fingerprint /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
    printf 'deb [arch=amd64 signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] https://packages.osrfoundation.org/gazebo/ubuntu-stable jammy main\n' > /etc/apt/sources.list.d/uav-humble22-gazebo.list
    apt-get update
    apt-get install -y --no-install-recommends \
      ros-humble-ros-base ros-humble-tf2-ros ros-humble-tf2-geometry-msgs \
      ros-humble-cv-bridge ros-humble-image-transport ros-humble-rosbag2 \
      ros-humble-rosbag2-storage-default-plugins ros-humble-rosbag2-storage-mcap \
      ros-humble-rosidl-default-generators ros-humble-rosidl-default-runtime \
      ros-humble-ament-cmake ros-humble-ament-cmake-python \
      python3-colcon-common-extensions python3-rosdep python3-vcstool \
      gz-harmonic libgz-sim8-dev libgz-transport13-dev libgz-msgs10-dev libgz-math7-dev
    # No ros-humble-ros-gz* binary is installed: that default pairing is Fortress.
    if dpkg-query -W -f='${binary:Package}\n' 'ros-humble-ros-gz*' 2>/dev/null | rg '^ros-humble-ros-gz'; then
      echo 'Unexpected default/binary ros_gz package; do not mix it with the source overlay.' >&2; exit 2
    fi
    dpkg-query -W -f='${binary:Package}\t${Version}\n' > "$humble22_prefix/logs/packages.tsv"
    humble22_rosdep_cache=/mnt/d/WSL/UAVHumble22-validation/official-rosdep
    if [[ -f "$humble22_rosdep_cache/download_manifest.json" && -f "$humble22_rosdep_cache/local-sources.list" ]]; then
      install -D -m 644 "$humble22_rosdep_cache/local-sources.list" /etc/ros/rosdep/sources.list.d/20-default.list
      printf 'export ROSDISTRO_INDEX_URL=file://%s/index-v4.yaml\n' "$humble22_rosdep_cache" > "$humble22_prefix/rosdep.env"
      source "$humble22_prefix/rosdep.env"
      echo 'Using unchanged official rosdep metadata cached by the Windows HTTPS transport; see download_manifest.json.'
    elif [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
      rosdep init
    fi
    rosdep update --rosdistro humble
    ;;
  repositories)
    if [[ -z "$humble22_source" || ! -f "$humble22_source/pyproject.toml" ]]; then
      echo 'Supply the mounted project source path as the second argument.' >&2; exit 2
    fi
    if [[ -e "$humble22_prefix/project" && ! -f "$humble22_prefix/project/.humble22-snapshot" ]]; then
      echo 'Unmarked project directory exists; refusing to overwrite it.' >&2; exit 2
    fi
    mkdir -p "$humble22_prefix/ros_gz_ws/src" "$humble22_prefix/px4_msgs_ws/src" "$humble22_prefix/project"
    if [[ ! -f "$humble22_prefix/project/.humble22-snapshot" ]]; then
      rsync -a --exclude='.git' --exclude='results' --exclude='build' --exclude='install' \
        --exclude='log' --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv*' \
        "$humble22_source/" "$humble22_prefix/project/"
      printf 'isolated-humble22-v1\nsource=%s\ncreated_utc=%s\n' "$humble22_source" "$(date -u --iso-8601=seconds)" > "$humble22_prefix/project/.humble22-snapshot"
    fi
    humble22_repo https://github.com/gazebosim/ros_gz.git 0.244.27 "$humble22_ros_gz_commit" "$humble22_prefix/ros_gz_ws/src/ros_gz"
    humble22_repo https://github.com/PX4/px4_msgs.git v1.17.0 "$humble22_msgs_commit" "$humble22_prefix/px4_msgs_ws/src/px4_msgs"
    humble22_repo https://github.com/PX4/PX4-Autopilot.git v1.17.0 "$humble22_px4_commit" "$humble22_prefix/PX4-Autopilot"
    # This validation targets Gazebo/PX4 SITL, not NuttX or legacy simulators.
    git -C "$humble22_prefix/PX4-Autopilot" submodule update --init --recursive --depth 1 -- \
      Tools/simulation/gz src/drivers/gps/devices src/lib/events/libevents \
      src/lib/heatshrink/heatshrink src/modules/mavlink/mavlink \
      src/modules/uxrce_dds_client/Micro-XRCE-DDS-Client
    humble22_repo https://github.com/eProsima/Micro-XRCE-DDS-Agent.git v2.4.3 "$humble22_agent_commit" "$humble22_prefix/Micro-XRCE-DDS-Agent"
    ;;
  python)
    test -f "$humble22_prefix/project/pyproject.toml"
    python3 -m venv --system-site-packages "$humble22_prefix/venv"
    source "$humble22_prefix/venv/bin/activate"
    printf 'numpy==1.26.4\nsetuptools==75.8.2\npackaging==24.2\n' > "$humble22_prefix/python-constraints.txt"
    python -m pip install 'pip==25.1.1' 'setuptools==75.8.2' 'wheel==0.45.1'
    # Install the CPU wheels before packages such as ultralytics-thop can ask
    # pip for an unpinned PyTorch/CUDA build from the default index.
    python -m pip install 'torch==2.5.1+cpu' 'torchvision==0.20.1+cpu' --index-url https://download.pytorch.org/whl/cpu
    python -m pip install -c "$humble22_prefix/python-constraints.txt" \
      'numpy==1.26.4' 'packaging==24.2' 'matplotlib==3.8.4' 'pytest==8.3.5' 'PyYAML==6.0.2' \
      'opencv-python==4.11.0.86' colcon-common-extensions pillow requests psutil polars scipy tqdm ultralytics-thop nvidia-ml-py
    # Jammy's system OpenCV is older than Ultralytics' declared Python minimum.
    # Pin the venv Python binding and verify cv_bridge conversion below rather
    # than replacing Ubuntu's C++ OpenCV libraries or allowing NumPy 2.x.
    python -m pip install 'ultralytics==8.4.188' --no-deps
    python -m pip install -c "$humble22_prefix/python-constraints.txt" -r "$humble22_prefix/PX4-Autopilot/Tools/setup/requirements.txt"
    python -m pip install -c "$humble22_prefix/python-constraints.txt" -e "$humble22_prefix/project"
    python -m pip freeze > "$humble22_prefix/logs/python-requirements.txt"
    ;;
  build|build-ros|build-agent|build-px4|build-project)
    humble22_source_ros
    if [[ "$humble22_phase" == build || "$humble22_phase" == build-ros ]]; then
      rosdep install -y --ignore-src --rosdistro humble \
      --from-paths "$humble22_prefix/ros_gz_ws/src/ros_gz/ros_gz_interfaces" \
                   "$humble22_prefix/ros_gz_ws/src/ros_gz/ros_gz_bridge" \
                   "$humble22_prefix/ros_gz_ws/src/ros_gz/ros_gz_sim" \
      --skip-keys 'gz-msgs10 gz-transport13 gz-math7 gz-sim8'
      cd "$humble22_prefix/ros_gz_ws"
      "$humble22_prefix/venv/bin/python" /usr/bin/colcon build --cmake-clean-cache --executor sequential --parallel-workers 1 --packages-up-to ros_gz_bridge ros_gz_sim \
      --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=OFF \
      -DPython3_EXECUTABLE="$humble22_prefix/venv/bin/python" -DPYTHON_EXECUTABLE="$humble22_prefix/venv/bin/python"
      set +u
      source "$humble22_prefix/ros_gz_ws/install/setup.bash"
      set -u
      cd "$humble22_prefix/px4_msgs_ws"
      "$humble22_prefix/venv/bin/python" /usr/bin/colcon build --executor sequential --parallel-workers 1 \
      --cmake-args -DBUILD_TESTING=OFF -DPython3_EXECUTABLE="$humble22_prefix/venv/bin/python" -DPYTHON_EXECUTABLE="$humble22_prefix/venv/bin/python"
    fi
    set +u
    source "$humble22_prefix/ros_gz_ws/install/setup.bash"
    source "$humble22_prefix/px4_msgs_ws/install/setup.bash"
    set -u
    if [[ "$humble22_phase" == build || "$humble22_phase" == build-agent ]]; then
      cmake -S "$humble22_prefix/Micro-XRCE-DDS-Agent" -B "$humble22_prefix/agent_build" \
      -DCMAKE_INSTALL_PREFIX="$humble22_prefix/agent_install" -DCMAKE_BUILD_TYPE=Release
      cmake --build "$humble22_prefix/agent_build" --parallel "$humble22_jobs"
      cmake --install "$humble22_prefix/agent_build"
    fi
    if [[ "$humble22_phase" == build || "$humble22_phase" == build-px4 ]]; then
      if [[ "$humble22_px4_root" == "$humble22_prefix/PX4-Autopilot-v4mag" ]]; then
        test -f "$humble22_prefix/logs/px4_v4mag_patch.json"
        env STAGE1_ROS_DISTRO=humble STAGE1_PX4_MSGS_WS="$humble22_prefix/px4_msgs_ws" \
          STAGE1_ROS_GZ_WS="$humble22_prefix/ros_gz_ws" \
          STAGE1_PYTHON_EXECUTABLE="$humble22_prefix/venv/bin/python" \
          PX4_BUILD_JOBS="$humble22_jobs" \
          bash "$humble22_prefix/project/scripts/build_px4_magnetic_runtime.sh" \
          "$humble22_px4_root" "$humble22_prefix/logs/px4_v4mag_runtime_$(date -u +%Y%m%dT%H%M%SZ).json"
      else
        make -C "$humble22_px4_root" "-j$humble22_jobs" px4_sitl_default
      fi
    fi
    if [[ "$humble22_phase" == build || "$humble22_phase" == build-project ]]; then
      cd "$humble22_project/ros2_ws"
      "$humble22_prefix/venv/bin/python" /usr/bin/colcon build --symlink-install --executor sequential --parallel-workers 1 \
      --cmake-args -DPython3_EXECUTABLE="$humble22_prefix/venv/bin/python" -DPYTHON_EXECUTABLE="$humble22_prefix/venv/bin/python"
    fi
    ;;
  verify)
    # This phase only checks build/import boundaries. The independent bridge
    # smoke and an actual closed-loop flight remain separate runtime gates.
    source "$humble22_project/scripts/humble22_env.sh"
    cd "$humble22_project"
    python -B -m unittest discover -s tests -v
    ros2 interface show px4_msgs/msg/VehicleOdometry
    ros2 interface show ros_gz_interfaces/srv/SetEntityPose
    ros2 pkg executables ros_gz_bridge
    ros2 pkg executables ros_gz_sim
    gz sim --version
    python -c 'import cv_bridge, cv2, rclpy, torch, torchvision, ultralytics, numpy as np; from px4_msgs.msg import VehicleOdometry; from ros_gz_interfaces.srv import SetEntityPose; b=cv_bridge.CvBridge(); a=np.arange(60,dtype=np.uint8).reshape(4,5,3); assert np.array_equal(a,b.imgmsg_to_cv2(b.cv2_to_imgmsg(a,encoding="bgr8"),desired_encoding="bgr8")); print("Humble Python imports and cv_bridge roundtrip OK", torch.__version__, ultralytics.__version__, cv2.__version__)'
    python -m pip check
    humble22_detector="$humble22_project/ros2_ws/install/uav_tracking_nodes/lib/uav_tracking_nodes/detector"
    test -x "$humble22_detector"
    head -n 1 "$humble22_detector"
    if [[ "$(head -n 1 "$humble22_detector")" != "#!$humble22_prefix/venv/bin/python" ]]; then
      echo 'Detector was built with the wrong Python interpreter; rebuild with the venv colcon entry.' >&2; exit 2
    fi
    python -c 'import sys,torch,uav_tracking_nodes.detector_node; print("detector interpreter:",sys.executable,"torch:",torch.__file__)'
    humble22_bridge="$(ros2 pkg prefix ros_gz_bridge)/lib/ros_gz_bridge/parameter_bridge"
    ldd "$humble22_bridge" | tee "$humble22_prefix/logs/bridge-ldd.txt"
    if rg 'not found|/opt/ros/jazzy|libignition-(transport|msgs|gazebo)' "$humble22_prefix/logs/bridge-ldd.txt"; then
      echo 'Bridge ABI/dependency gate failed.' >&2; exit 2
    fi
    test -x "$humble22_px4_root/build/px4_sitl_default/bin/px4"
    test -x "$humble22_prefix/agent_install/bin/MicroXRCEAgent"
    python scripts/capture_environment.py --project-root "$PWD" \
      --px4-root "$humble22_px4_root" \
      --px4-msgs-root "$humble22_prefix/px4_msgs_ws/src/px4_msgs" \
      --agent-root "$humble22_prefix/Micro-XRCE-DDS-Agent" \
      --skip-gl-probe --output "$humble22_prefix/logs/environment_manifest.json"
    echo 'Build/import gates passed. RGB-D/service bridge and PX4 SITL flight are still required.'
    ;;
esac
echo "Completed phase=$humble22_phase UTC=$(date -u --iso-8601=seconds) log=$humble22_log"
