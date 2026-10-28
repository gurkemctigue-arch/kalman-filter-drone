# uav_tracking_px4_adapter

This package is the only place where the portable ENU/FLU command is mapped to PX4 NED/FRD messages. It publishes `OffboardControlMode` continuously at the configured rate and emits either a velocity or position `TrajectorySetpoint`; the two modes are mutually exclusive per command.

The package must be built against the same PX4 `px4_msgs` branch as the selected PX4 firmware tag. The Windows host cannot validate this boundary; build it inside the locked Ubuntu 24.04/ROS 2 Jazzy environment described in `docs/VERSION_LOCK.md`.

In addition to command conversion, the node adapts PX4 `VehicleOdometry` on
`/fmu/out/vehicle_odometry` into ENU `nav_msgs/Odometry` on
`/vehicle/odometry`. The controller consumes that common ROS message and does
not import PX4 types. The output uses the ROS clock because PX4's odometry
timestamp is in the flight-controller boot-time domain; this keeps controller
staleness checks in one time domain.
