# Validated environment and version lock

This is the installed WSL environment inspected on 2026-10-26 (Asia/Shanghai).
Installed versions and repository signatures were checked on Linux; this file
does not assert that every flight acceptance test has passed. Archive a fresh
manifest with each experimental trial because source, models and launch
parameters are still being developed.

| Component | Actual locked version |
| --- | --- |
| Host OS | Windows 11 Home China, build `22621` (`10.0.22621`) |
| Linux | Ubuntu `24.04.1 LTS`, Noble, x86_64, WSL2 |
| Kernel | `6.6.114.1-microsoft-standard-WSL2` |
| Python | `3.12.3` |
| ROS 2 | Jazzy Jalisco; `ros-jazzy-ros-base=0.11.0-1noble.20261006.035407` |
| rclpy | `ros-jazzy-rclpy=7.1.12-1noble.20260912.162354` |
| RMW package | `ros-jazzy-rmw-fastrtps-cpp=8.4.4-1noble.20260911.100940` |
| Gazebo Sim | Harmonic `8.15.0`, installed through ROS vendor packages |
| Gazebo vendor | `ros-jazzy-gz-sim-vendor=0.0.13-1noble.20260905.073557` |
| RGB-D bridge | `ros-jazzy-ros-gz-bridge=1.0.24-1noble.20260920.234644` |
| PX4 | tag `v1.17.0`, commit `d6f12ad1c4f70ad3230afd7d86e971421e02fef4` |
| px4_msgs | branch `release/1.17`, tag `v1.17.0`, commit `86d8239e962f6939e05c3737784f60c02fa884db` |
| Micro XRCE-DDS Agent | tag `v2.4.3`, commit `73622810d984349b80bbac0ef55fc0b694d62222` |
| Ultralytics | `8.4.188` |
| PyTorch / torchvision | `2.5.1+cpu` / `0.20.1+cpu` |
| NumPy | `1.26.4` |
| Matplotlib (offline evaluation/plots) | Ubuntu `python3-matplotlib=3.6.3-1ubuntu5`; installed before the full-plan freeze |
| OpenCV | Ubuntu package `python3-opencv=4.6.0+dfsg-13.1ubuntu1` |
| colcon core | `0.21.3+upstream-1` |
| CPU | Intel Core i5-13500H; WSL exposes 16 logical CPUs |
| Host GPU | Intel Iris Xe Graphics, Windows driver `31.0.101.5522` |

The current detector uses CPU inference; this PyTorch build provides no CUDA
backend. WSL exposes `/dev/dxg`, but that alone does not establish Gazebo's
active renderer or acceleration. Record each rendering process's configuration
and renderer evidence separately. The environment audit does not change
`LIBGL_ALWAYS_SOFTWARE`, Mesa/D3D12 settings, or any global GPU environment.

The full research test suite also imports the plotting tools. On this Ubuntu
installation their dependency is provided by `apt-get install python3-matplotlib`;
the portable Python package declares the corresponding `research` extra. This
offline dependency was added without upgrading ROS, NumPy, Torch, PX4 or Gazebo.
Capture a fresh environment manifest for the frozen study; older manifests
describe the earlier package inventory.

`models/yolo11n.pt` contains 5,613,764 bytes with SHA-256:

```text
0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1
```

The three dependency repositories above were clean at inspection. The project
directory has no Git repository, so the manifest records individual source,
configuration, world/model, mesh/texture and weight hashes instead of inventing
a project commit. Runtime parameter files and generated launch arguments must
also remain with each trial.

## Isolated optional OpenVINO experiment

OpenVINO is not a dependency of the main ROS/PyTorch detector path. The
optional CPU performance investigation installed OpenVINO `2025.4.1` and
openvino-telemetry `2025.2.0` only in
`/root/uav_tracking_project/.venv-openvino`, a venv exposing the existing system
site packages. The final pip dry-run and install added only those two packages;
NumPy `1.26.4`, Torch `2.5.1+cpu`, ROS, PX4 and Gazebo were not upgraded.

FP32 rectangular exports, model/input hashes, actual two-thread CPU settings,
per-image timings and licenses are retained under
`results/openvino_car_comparison/`; see
[OPENVINO_CPU_COMPARISON.md](OPENVINO_CPU_COMPARISON.md). The small measured
speed improvement did not justify replacing PyTorch. Keep this venv inventory
and exported-artifact provenance separate from the main runtime dependency
lock and retain the comparison JSON with any reuse of these artifacts.

## Difference from the initial plan

The original proposal named Ubuntu 22.04, ROS 2 Humble and Python 3.10. The
available machine runs Ubuntu 24.04, so the tested implementation uses its
supported ROS pairing, Jazzy, with Python 3.12. Gazebo Harmonic and PX4 1.17
remain the chosen simulation/flight stack. Do not label these results as a
Humble validation, mix Humble binary packages into this installation, or claim
that the Ubuntu 22.04 migration has already been tested. Portable core
algorithms retain the ROS/Gazebo/PX4 adapter boundary; a future Humble port
needs its own clean build and integration checks.

The current installation does not include the separate `gz-harmonic` apt
metapackage or standalone `libgz-sim8` apt package. Gazebo is supplied by
`ros-jazzy-gz-*-vendor`; source `/opt/ros/jazzy/setup.bash` before invoking
`gz sim --version` so its vendor paths are available.

## ROS APT signatures restored

The temporary `trusted=yes` setup workaround has been removed. The current
source is:

```text
deb [arch=amd64 signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu noble main
```

The refreshed key was downloaded from the official HTTPS endpoint
`https://repo.ros2.org/repos.key`. Its existing Open Robotics primary
fingerprint was verified as:

```text
C1CF6E31E6BADE8868B172B4F42ED6FBAB17C654
```

The refreshed key expires at `2030-06-01T12:39:34Z`. Before installation,
`gpgv` verified the current Noble `InRelease` against that key. After replacing
the expired key and enabling `signed-by`, a ROS-source-only `apt-get update`
completed with `GOODSIG` and `VALIDSIG` for the same fingerprint. No packages
were installed or upgraded. HTTP repository transport retains mandatory
OpenPGP metadata/package-hash authentication; TLS and APT signature checks
were not disabled.

The old key/source, downloaded public key and verified `InRelease` are retained
under `/root/uav_tracking_project/results/environment_20261026/`. The manifest
independently re-verifies cached ROS repository metadata and records
`ros_signature_verification_ready=true`. The previous expired key is retained
only as audit evidence, outside APT's active key/source paths.

## Capture an experiment manifest

```bash
source /opt/ros/jazzy/setup.bash
source /root/px4_msgs_ws/install/setup.bash
source /root/uav_tracking_project/ros2_ws/install/setup.bash
python3 scripts/capture_environment.py \
  --project-root /root/uav_tracking_project \
  --output results/TRIAL/environment_manifest.json
```

The script records exact apt/Python package inventories, source tags/commits
and dirty state, source-built Agent libraries, binary hashes, model/weight
hashes, CPU/kernel information, an allowlist of relevant ROS/rendering
variables, and cached ROS repository signature evidence. It contacts no ROS
graph, installs nothing and changes no environment variables. Only the JSON
artifact is written. `--skip-gl-probe` skips creation of a temporary GL context
when another rendering experiment is running; it still records GPU device and
environment evidence. A current-shell `glxinfo` result must not be substituted
for the renderer used by a different Gazebo process.

The audited manifest is at
`/root/uav_tracking_project/results/environment_20261026/environment_manifest.json`.
Capture again after final code/model changes and keep that per-trial artifact
with the rosbag, metrics, random seed, command arguments and failed-run records.

The final validated runtime inventory is archived at
[stage1_final_validation/environment_manifest.json](../results/stage1_final_validation/environment_manifest.json).
It was captured after the final four-condition flight matrix and copied into
each `stage1_final_v2_*` trial directory as a shared final-environment record;
its timestamp does not represent a separate capture during each flight. The
trial-specific runtime arguments, configuration and source hashes remain in
each trial archive.
