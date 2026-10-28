# UAV tracking ROS 2 workspace

This workspace is the ROS 2 integration boundary for the UAV target-following
project. Detector, estimator, controller, and PX4 adapter nodes are separated
into packages and consume `uav_tracking_interfaces` rather than reaching into
each other directly.

## Scope

The pipeline is:

```
camera -> detector -> TargetObservation -> state estimator -> TargetState
                                                        -> controller
                                                        -> TrackingCommand
PX4/Gazebo adapter <------------------------------------+
```

The `TargetSelection` message is reserved for the later designated-instance
extension. It does not turn a detector into an identity tracker by itself.

## Packages

- `uav_tracking_interfaces`: ROS 2 message contracts and frame/timestamp
  semantics.
- `uav_tracking_nodes`: YOLO/RGB-D detector, TF-aware state estimator, and
  bounded outer-loop controller.
- `uav_tracking_px4_adapter`: PX4 Offboard heartbeat and ENU/NED adapter.
- `uav_tracking_bringup`: parameters, stage-one Gazebo worlds, local target
  proxy meshes, RGB-D bridge maps and launch files.

## Build when ROS 2 is available

From the workspace directory:

```bash
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -r -y
# Needed for the real detector node; stage1_smoke_test bypasses YOLO.
python3 -m pip install ultralytics
colcon build --symlink-install
source install/setup.bash
ros2 interface show uav_tracking_interfaces/msg/TargetObservation
ros2 launch uav_tracking_bringup tracking_sim.launch.py start_pipeline:=false
```

The launch template defaults to `start_pipeline:=false` so interfaces can be
inspected before starting a simulator. Set `start_pipeline:=true` after the
implementation packages and their dependencies are built. See
`docs/ROS2_SIMULATION.md` for the adapter contract and version-lock procedure.

For the stage-one sensor smoke test, use the installed person world and
float-metre depth parameters:

```bash
ros2 launch uav_tracking_bringup tracking_sim.launch.py \
  start_simulator:=true start_bridge:=true start_static_tf:=true \
  start_pipeline:=true start_px4_adapter:=false \
  params_file:=$(ros2 pkg prefix uav_tracking_bringup)/share/uav_tracking_bringup/config/stage1_tracking_person.yaml
```

The car condition uses `stage1_single_car.sdf`,
`stage1_car_bridge.yaml`, and `stage1_tracking_car.yaml`. The ground-truth
pose bridge is for rosbag/offline metrics only; runtime association uses RGB-D
observations and TF.
