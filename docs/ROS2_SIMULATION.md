# ROS 2 / PX4 / Gazebo simulation guide

The tested environment is Ubuntu 24.04.1 under WSL2, ROS 2 Jazzy, Gazebo
Harmonic and PX4 v1.17.0. Exact versions and the difference from the initial
Ubuntu 22.04/Humble proposal are recorded in [VERSION_LOCK.md](VERSION_LOCK.md).
This guide covers building and the stationary sensor/test graph. The integrated
onboard-camera flight graph is described in [STAGE1_FLIGHT.md](STAGE1_FLIGHT.md),
with current evidence in [STAGE1_ACCEPTANCE.md](STAGE1_ACCEPTANCE.md).

## Reference execution

Use a Linux environment (native Ubuntu or WSL2) for the simulator. After
installing the versions in `VERSION_LOCK.md`:

```bash
source /opt/ros/jazzy/setup.bash
# The ROS adapters import the middleware-independent ``uav_tracking.core``
# package from the repository root. Run this from the workspace so the parent
# directory (the repository root) is installed into the same Python environment.
cd /absolute/path/to/repository/ros2_ws
python3 -m pip install -e ..
# Required only when running the real YOLO detector node (the controlled
# stage-one smoke test does not need this optional dependency).
python3 -m pip install ultralytics
rosdep install --from-paths src --ignore-src -r -y
# Use a merged install so custom interface packages are discoverable by
# ``ros2 interface`` and ``ros2 bag`` from the same sourced workspace.
colcon build --merge-install --symlink-install
source install/setup.bash
ros2 interface show uav_tracking_interfaces/msg/TargetState
ros2 launch uav_tracking_bringup tracking_sim.launch.py start_pipeline:=false
```

The default `tracking_sim.launch.py` mode is an interface/build smoke test and
starts no algorithm nodes. The detector, estimator, controller and adapter
packages are implemented. To run their stationary sensor graph, select a world
and parameter file explicitly:

```bash
ros2 launch uav_tracking_bringup tracking_sim.launch.py \
  start_simulator:=true world:=/absolute/path/to/world.sdf \
  start_pipeline:=true params_file:=/absolute/path/to/tracking.yaml
```

`tracking_sim.launch.py` deliberately uses a stationary RGB-D rig and does not
spawn the flight vehicle. Its fake-vehicle option is for ROS smoke tests.
Flight trials instead use `stage1_flight.launch.py` through the runner below;
that graph connects the onboard camera, dynamic vehicle TF, PX4 odometry,
supervised takeoff and visual following in the same Gazebo world.

After building, run one isolated flight trial from the Linux project root:

```bash
bash scripts/run_stage1_trial.sh \
  --class person --name person_flight_trial_01 --duration 45 \
  --occlusions --short-occlusion-s 0.2
```

The runner owns Gazebo, the XRCE-DDS Agent, PX4, the ROS graph, recording and
the monitor. Each trial creates a new result directory and refuses to overwrite
an existing one. Run one Gazebo experiment at a time. Manual component commands
and frame/flight details are documented in [STAGE1_FLIGHT.md](STAGE1_FLIGHT.md).

The historical `person_flight_v06` report recorded PASS under its earlier
evaluator for 0.4 s/3.0 s shutter conditions. Its short event also recorded an
approximately 0.8 s valid-depth acquisition gap and LOST before the reported
recovery, so that old PASS does not certify the current fresh-recovery/no-loss
checks. Its `horizontal_vehicle_span_m` of about 12.486 m describes the UAV's
horizontal position range, not target displacement or path length; median
detection latency was about 0.1 s. Historical car trials such as
`car_flight_v02` and `car_flight_v04` retain their overall FAIL reports.
Preserve each original result and evaluator version, including old event-level
successes; do not promote those event labels into current trial acceptance.

Current trials use a default **0.2 s** short shutter and a **3.0 s** long shutter.
At a 5 Hz CPU inference cap, sampling and inference can extend a 0.4 s physical
occlusion to an approximately 0.8 s valid-depth gap, exceeding the fixed 0.75 s
prediction limit. LOST/HOVER is then correct; 0.4 s recovery cannot be promised.
A short pass requires a fresh MEASURED acquisition at/after opening, unchanged
track/task identity and no LOST until that fresh recovery. An older frame
delivered after opening is not recovery evidence. The person/car by
velocity/position conditions using 0.2 s/3.0 s require their own completed
recordings and evaluation; consult the acceptance record for actual results.

The bringup package now installs deterministic stage-one assets:

- `worlds/stage1_single_target.sdf`: one textured person and a stationary
  RGB-D rig for sensor/TF tests;
- `worlds/stage1_single_car.sdf`: the same rig with one textured car;
- `worlds/stage1_flight_person.sdf` and `stage1_flight_car.sdf`: the PX4 x500,
  onboard aligned RGB-D camera, one target and a rendering shutter;
- `config/stage1_bridge.yaml` and `config/stage1_car_bridge.yaml`: RGB image,
  aligned depth, camera info, simulated clock, and offline pose-vector to
  `tf2_msgs/TFMessage` bridges;
- `models/target_person` and `models/target_car`: wrappers around locally
  vendored CC0 Walking person v3 and Prius Hybrid v3 meshes and textures.
  Runtime requires no Fuel download; retain the complete resource hierarchy.
- repository `models/yolo11n.pt`: pinned YOLO11n baseline; its source and
  SHA-256 are recorded in `models/README.md` and installed with the bringup
  package.

The current car flight configuration uses `models/yolo11s.pt`, CPU inference
with `inference_image_size: 480`, and a 5 Hz inference cap. A callback enforces
two PyTorch threads after backend initialization, with the actual count in
diagnostics. A 50 Hz lightweight latest-image poll applies the 5 Hz
start-to-start cap without accumulating a queue. The RGB-D camera stays at
640x480 with its original calibration. This configuration follows a restored
640 probe that still lost tracking under measurement latency; the latest
480 candidate needs its own flight evidence. The checkpoint source, hash and
paired comparison against the
original nano checkpoint are recorded in
[CAR_DETECTOR_COMPARISON.md](CAR_DETECTOR_COMPARISON.md); an offline detector
gain is separate from flight/occlusion acceptance. Historical trial snapshots
retain the inference sizes actually used in those trials.
The optional isolated [OpenVINO CPU experiment](OPENVINO_CPU_COMPARISON.md)
showed only a small speed improvement and did not replace the PyTorch backend.

Source archives, licenses, hashes, detector evidence and visible-surface
measurement semantics are recorded in [VISUAL_ASSETS.md](VISUAL_ASSETS.md).
Targets now use Gazebo `VelocityControl`, start with zero velocity, and disable
target gravity and collisions for prescribed scene motion. `scenario_motion`
starts a repeatable 0.5 m/s trajectory after the flight supervisor first enters
`FOLLOW`. Stationary sensor worlds remain stationary unless motion commands
are explicitly supplied. This replaces the earlier force-driven
TrajectoryFollower targets; the flight vehicle retains PX4-controlled
rigid-body and motor dynamics.

The flight trial runner defaults to headless EGL, `LP_NUM_THREADS=4`, a 10 Hz
camera and disabled scene shadows on this machine. Its optional
`--render-backend wslg` selects server-only D3D12 rendering. Although the GPU
renderer was available, a solo D3D12 flight trial ran too slowly and aborted;
EGL remains the tested default. Do not run asset/viewpoint benchmarks alongside
flight trials. Source ROS before invoking `gz`, because Gazebo is supplied
through ROS vendor packages here. Backend diagnostics are retained under
`results/render_benchmark/`.

The stationary launch file uses the `ros_gz_sim` `gzserver` ROS component and
`ros_gz_bridge`. After installing the Linux dependencies, run the first sensor
smoke test with:

```bash
source /opt/ros/jazzy/setup.bash
cd /absolute/path/to/repository/ros2_ws
source install/setup.bash
ros2 launch uav_tracking_bringup tracking_sim.launch.py \
  start_simulator:=true start_bridge:=true start_static_tf:=true \
  start_pipeline:=true start_px4_adapter:=false \
  params_file:=$(ros2 pkg prefix uav_tracking_bringup)/share/uav_tracking_bringup/config/stage1_tracking_person.yaml
```

The static transform published by this launch maps the sensor's REP-103
optical `camera_link` (x right, y down, z forward) into the ENU `map` frame and
includes the rig's downward pitch. Keep the optical-axis convention when
changing mounts, but replace the fixed world-to-camera transform with a dynamic
vehicle transform for flight. `flight_tf` uses PX4 odometry and the fixed
physical camera mount. Never run the stationary map-to-camera publisher
alongside the flight TF tree.

For a ROS-only graph smoke test before PX4 SITL is available, add
`start_fake_vehicle:=true start_px4_adapter:=false`. The latter prevents the
graph from requiring `px4_msgs` while PX4 is not present. The fake vehicle
publishes a constant `/vehicle/odometry` at the camera rig pose so the
controller can exercise its measured/predicted/hover lifecycle. It is a test
stand-in, not flight validation, and must be disabled when PX4 publishes the
real odometry topic.

The old geometric proxies have been replaced by textured assets. Real Gazebo
RGB images are processed by YOLO11 in flight. Some car viewpoints and distances
still expose domain shift, as recorded in the asset and detector comparison
evidence. Detection availability does not establish Precision/Recall or mAP
without a labelled dataset.

For a separate TF/estimator/controller test, disable the detector with
`start_detector:=false`, use the fake-vehicle smoke graph, and run the explicit
controlled-observation publisher:

```bash
ros2 run uav_tracking_bringup stage1_smoke_test \
  --target-class person --depth-probe \
  --ros-args -p use_sim_time:=true
```

The test publishes only clearly marked `CONTROLLED_TEST_SOURCE`
`TargetObservation` messages on the detector output topic. With
`--depth-probe`, it also publishes a synthetic RGB image, float-metre depth
image, and `CameraInfo`, then verifies that both RGB and depth topics are
transported. It does not read Gazebo truth. Its schedule is measured, short
loss, and long loss; exit status 0 requires measured/predicted/lost estimator
states, `HOVER`, and a failsafe command. Use `--target-class car` for the car
parameter/world condition. This controlled test validates TF, the 3-D Kalman
lifecycle, RGB-D topic transport, and the outer controller; YOLO
precision/recall still requires a labelled, appearance-valid image set.

Check the bridge and sensor topics before starting the detector:

```bash
ros2 topic list | grep -E 'camera|ground_truth|clock'
ros2 topic hz /camera/color/image_raw
ros2 topic echo --once /camera/color/camera_info
```

For the car condition, start the corresponding world, bridge and parameters
together:

```bash
ros2 launch uav_tracking_bringup tracking_sim.launch.py \
  start_simulator:=true start_bridge:=true start_static_tf:=true \
  start_pipeline:=true start_px4_adapter:=false \
  world:=$(ros2 pkg prefix uav_tracking_bringup)/share/uav_tracking_bringup/worlds/stage1_single_car.sdf \
  bridge_config:=$(ros2 pkg prefix uav_tracking_bringup)/share/uav_tracking_bringup/config/stage1_car_bridge.yaml \
  params_file:=$(ros2 pkg prefix uav_tracking_bringup)/share/uav_tracking_bringup/config/stage1_tracking_car.yaml
```

Do not run both worlds in the same trial when evaluating `AUTO_UNIQUE`: each
acceptance trial must contain exactly one class-matched instance. Quantitative
detection results require labelled rendered or real images, with model hashes
and failure cases retained. Gazebo's depth image is float metres, so the
stage-one configs use `depth_scale: 1.0`; a uint16 millimetre camera must use
0.001.

The detector's `image_reliability` parameter accepts `reliable` or
`best_effort`, with KEEP_LAST depth 1. The flight launch explicitly selects
`reliable` for RGB, depth and CameraInfo to match the Gazebo bridge. In v05,
the reliable recorder received roughly 10 Hz RGB/depth while best-effort
perception readers received far fewer images; this must not be described as
a globally slow renderer. For a real camera offering only best effort,
configure its detector deployment to request `best_effort` and verify QoS
compatibility. The portable algorithm core is independent of this policy.

The target model's pose-publisher and the `/ground_truth/poses` bridge exist
only for offline evaluation and rosbag recording. Runtime detector, target
manager and controller nodes must consume RGB-D, TF and vehicle state; they
must never read the Gazebo pose vector, actor name, or model/entity ID.

If the chosen Gazebo release expands sensor topics under
`/world/.../model/.../sensor/...`, inspect `gz topic -l` and change only the
`gz_topic_name` values in the bridge YAML. ROS topic names and detector
parameters remain stable. `ros_gz_sim` and `ros_gz_bridge` are declared as
runtime dependencies; an unavailable bridge is an environment issue, not a
reason to silently report a closed-loop result.

## PX4 adapter responsibilities

The adapter is the only component allowed to depend directly on `px4_msgs`,
MAVLink, or a vehicle-specific offboard API. It must:

1. Convert the command frame from ENU/local convention to PX4 NED.
2. Publish the offboard heartbeat before and during setpoint publication.
3. Gate commands on vehicle connection, arming, and offboard mode.
4. Convert `MODE_HOLD` and `MODE_FAILSAFE` to a bounded hover/hold command.
5. Stop forwarding motion when the command age or heartbeat timeout expires.
6. Log PX4 timestamps and acknowledgement/state transitions.

No controller should publish a `px4_msgs` message directly. This keeps the
algorithm testable with a fake adapter and makes HIL or a future flight stack
replaceable.

The adapter provides heartbeat, ENU/NED conversion, hold-on-invalid and
command-age protection. Set `require_vehicle_status` to `true` for PX4 SITL to
gate motion on a fresh armed + OFFBOARD `VehicleStatus` with passing pre-flight
checks and no failsafe. With PX4 v1.17, the status input is
`/fmu/out/vehicle_status_v1`; older firmware branches can override the
`vehicle_status_topic` parameter. The default remains `false` for a Gazebo-only bridge.
The adapter does not automatically issue arm/mode `VehicleCommand` messages;
the SITL smoke test must arm and enter OFFBOARD through the selected PX4
procedure. It subscribes to `/fmu/out/vehicle_command_ack` and logs raw
command/result fields so those acknowledgements can be correlated with the
status and rosbag before claiming flight-stack validation.

## Gazebo/RGB-D adapter responsibilities

The simulator setup must provide RGB, aligned depth, camera info, TF, vehicle
odometry, and a ground-truth target pose for evaluation. The depth adapter
should compute the median of valid pixels in a target ROI and publish the
valid-pixel ratio. The experiment harness must record the ground truth and all
topics in one rosbag; frame-by-frame metrics are not independent trial samples.

## Safety states

The minimum lifecycle is `ACQUIRE -> FOLLOW -> PREDICT -> HOVER`. `SEARCH` is
disabled by default and must be enabled only in a bounded simulation world.
Prediction has a hard maximum duration; it must never continue indefinitely on
stale data. Any adapter disconnect or invalid command enters `FAILSAFE`.
