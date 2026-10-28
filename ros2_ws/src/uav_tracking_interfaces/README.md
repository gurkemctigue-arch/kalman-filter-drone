# uav_tracking_interfaces

This package owns the stable, vehicle-neutral message contract for the UAV
tracking project. It deliberately has no dependency on `px4_msgs`, Gazebo, a
YOLO implementation, or a particular filter library.

Build it with `colcon` together with the workspace, then inspect the generated
interfaces with `ros2 interface show`. Frame, timestamp, QoS, and identity
semantics are documented in `docs/INTERFACES.md` at the repository root.

`TargetObservation` is a detector candidate and may not carry a persistent
identity. `TargetState` is the estimator output and may be measured or
predicted. `TrackingCommand` is vehicle-neutral; only the PX4 adapter converts
it to a flight-stack-specific message. `TargetSelection` is optional and
exists for the designated-instance extension.
