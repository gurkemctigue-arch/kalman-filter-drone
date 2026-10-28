# uav_tracking_bringup

This package installs the launch, parameter and stage-one Gazebo assets. The
algorithm node packages are intentionally not bundled here. With the default
arguments the launch file starts no simulator, bridge or placeholder nodes,
which makes the package safe to build before the detector, estimator,
controller, and PX4 adapter are implemented.

Use `start_pipeline:=true` only after those packages and their executables have
been added. Keep the installed `config/tracking.yaml` and the repository-level
`config/tracking.yaml` synchronized until the project moves to one canonical
configuration source.

The first sensor smoke test uses:

```bash
ros2 launch uav_tracking_bringup tracking_sim.launch.py \
  start_simulator:=true start_bridge:=true start_static_tf:=true \
  params_file:=$(ros2 pkg prefix uav_tracking_bringup)/share/uav_tracking_bringup/config/stage1_tracking_person.yaml
```

The default world is `worlds/stage1_single_target.sdf` (one moving person
proxy). Use `worlds/stage1_single_car.sdf` with
`config/stage1_car_bridge.yaml` and `stage1_tracking_car.yaml` for the
single-car condition. Ground-truth pose topics are for offline evaluation;
runtime nodes must use only detector observations, TF and vehicle state.
The stage-one configs set `depth_scale: 1.0` because Gazebo publishes float
depth in metres; use `stage1_tracking_car.yaml` and
`stage1_car_bridge.yaml` for the car condition.
The launcher's `map -> camera_link` transform treats `camera_link` as the
REP-103 optical frame (right/down/forward), including the rig's downward
pitch. Keep this convention when changing the sensor mount.
`start_fake_vehicle:=true` is available for a pre-PX4 static odometry smoke
test only; disable it as soon as PX4 publishes `/vehicle/odometry`.

For a controlled downstream acceptance test that does not require YOLO
weights, run `ros2 run uav_tracking_bringup stage1_smoke_test --depth-probe`
after the graph is started. When PX4 is not installed, start the graph with
`start_px4_adapter:=false`; the smoke test publishes a tagged observation
stream and creates its own static vehicle odometry, so do not run
`start_fake_vehicle` at the same time. It creates short and long detection
dropouts and exits non-zero unless measured,
predicted, lost, hover, and failsafe states are all observed.
