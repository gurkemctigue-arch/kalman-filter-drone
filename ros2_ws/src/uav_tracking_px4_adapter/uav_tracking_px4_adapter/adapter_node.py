"""PX4 Offboard adapter.

Only this node knows PX4's NED/FRD convention.  The controller publishes a
single active command in a ROS ENU local frame.  This adapter keeps publishing
an Offboard heartbeat and converts either velocity or position commands to a
``TrajectorySetpoint``.  If ``px4_msgs`` is unavailable, it fails at startup
with an actionable message instead of silently publishing a wrong frame.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

try:
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from uav_tracking_interfaces.msg import TrackingCommand
    from px4_msgs.msg import (
        OffboardControlMode,
        TrajectorySetpoint,
        VehicleCommandAck,
        VehicleOdometry,
        VehicleStatus,
    )
except ImportError:  # pragma: no cover - ROS/PX4 only.
    rclpy = None
    Node = object  # type: ignore[misc,assignment]
    # Keep pure frame-conversion helpers importable on development machines
    # that do not have ROS 2/PX4 installed.
    VehicleOdometry = None  # type: ignore[assignment,misc]
    VehicleStatus = None  # type: ignore[assignment,misc]
    VehicleCommandAck = None  # type: ignore[assignment,misc]


def enu_to_ned(vector: list[float] | tuple[float, float, float]) -> list[float]:
    """Convert a local ENU vector to PX4's local NED ordering."""

    if len(vector) != 3:
        raise ValueError("vector must contain three values")
    east, north, up = (float(value) for value in vector)
    return [north, east, -up]


def enu_yaw_to_ned(yaw_rad: float) -> float:
    """Convert REP-103 ENU yaw to PX4 local-NED yaw.

    ENU yaw is measured counter-clockwise from +East, whereas PX4 yaw is
    measured clockwise from +North.  The conversion is therefore
    ``pi/2 - yaw`` with a stable wrap to ``[-pi, pi)``.
    """

    yaw_ned = math.pi / 2.0 - float(yaw_rad)
    return (yaw_ned + math.pi) % (2.0 * math.pi) - math.pi


def enu_yaw_rate_to_ned(yaw_rate_radps: float) -> float:
    """Convert the positive-CCW ENU yaw rate to PX4's NED convention."""

    return -float(yaw_rate_radps)


def ned_to_enu(vector: list[float] | tuple[float, float, float]) -> list[float]:
    """Convert a PX4 local-NED vector to the ROS ENU ordering."""

    if len(vector) != 3:
        raise ValueError("vector must contain three values")
    north, east, down = (float(value) for value in vector)
    return [east, north, -down]


def _quaternion_wxyz_to_matrix(quaternion: Any) -> np.ndarray:
    """Return a body-to-world rotation matrix from a PX4 ``[w,x,y,z]`` q."""

    q = np.asarray(quaternion, dtype=float).reshape(-1)
    if q.size != 4 or not np.all(np.isfinite(q)):
        raise ValueError("quaternion must be a finite four-vector")
    norm = float(np.linalg.norm(q))
    if norm <= 1e-12:
        raise ValueError("quaternion norm must be positive")
    w, x, y, z = q / norm
    return np.array(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=float,
    )


def _matrix_to_quaternion_xyzw(matrix: np.ndarray) -> tuple[float, float, float, float]:
    """Convert a proper rotation matrix to a ROS ``(x,y,z,w)`` quaternion."""

    rotation = np.asarray(matrix, dtype=float)
    if rotation.shape != (3, 3) or not np.all(np.isfinite(rotation)):
        raise ValueError("rotation must be a finite 3x3 matrix")
    trace = float(np.trace(rotation))
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * scale
        x = (rotation[2, 1] - rotation[1, 2]) / scale
        y = (rotation[0, 2] - rotation[2, 0]) / scale
        z = (rotation[1, 0] - rotation[0, 1]) / scale
    elif rotation[0, 0] > rotation[1, 1] and rotation[0, 0] > rotation[2, 2]:
        scale = math.sqrt(max(1e-15, 1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2])) * 2.0
        w = (rotation[2, 1] - rotation[1, 2]) / scale
        x = 0.25 * scale
        y = (rotation[0, 1] + rotation[1, 0]) / scale
        z = (rotation[0, 2] + rotation[2, 0]) / scale
    elif rotation[1, 1] > rotation[2, 2]:
        scale = math.sqrt(max(1e-15, 1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2])) * 2.0
        w = (rotation[0, 2] - rotation[2, 0]) / scale
        x = (rotation[0, 1] + rotation[1, 0]) / scale
        y = 0.25 * scale
        z = (rotation[1, 2] + rotation[2, 1]) / scale
    else:
        scale = math.sqrt(max(1e-15, 1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1])) * 2.0
        w = (rotation[1, 0] - rotation[0, 1]) / scale
        x = (rotation[0, 2] + rotation[2, 0]) / scale
        y = (rotation[1, 2] + rotation[2, 1]) / scale
        z = 0.25 * scale
    quaternion = np.asarray([x, y, z, w], dtype=float)
    quaternion /= np.linalg.norm(quaternion)
    return tuple(float(value) for value in quaternion)


def px4_odometry_to_enu(message: Any) -> tuple[list[float], list[float], tuple[float, float, float, float]]:
    """Return ROS ENU position, body-FLU velocity and FLU-to-ENU attitude.

    PX4's normal output is a body-FRD orientation in a local-NED world frame;
    ROS ``nav_msgs/Odometry`` uses a body-FLU orientation in a local-ENU
    world frame.  Its twist must be expressed in ``child_frame_id`` (FLU),
    rather than the ENU pose frame.  The controller rotates that twist into
    its common world frame before using it.
    """

    pose_ned = int(getattr(message, "pose_frame", 1))
    velocity_ned = int(getattr(message, "velocity_frame", 1))
    ned_frame = int(getattr(VehicleOdometry, "POSE_FRAME_NED", 1))
    frd_frame = int(getattr(VehicleOdometry, "POSE_FRAME_FRD", 2))
    if pose_ned != ned_frame:
        raise ValueError("only PX4 VehicleOdometry pose_frame=NED is supported")
    position = ned_to_enu([float(value) for value in message.position])
    # NED -> ENU and FRD -> FLU are fixed proper rotations/reflections of the
    # coordinate bases.  Their product gives the ROS body/world orientation.
    ned_to_enu_matrix = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])
    frd_to_flu_matrix = np.diag([1.0, -1.0, -1.0])
    orientation = ned_to_enu_matrix @ _quaternion_wxyz_to_matrix(message.q) @ frd_to_flu_matrix
    quaternion = _matrix_to_quaternion_xyzw(orientation)
    velocity_raw = np.asarray([float(value) for value in message.velocity], dtype=float)
    if velocity_ned == int(getattr(VehicleOdometry, "VELOCITY_FRAME_NED", 1)):
        velocity = (orientation.T @ ned_to_enu_matrix @ velocity_raw).tolist()
    elif velocity_ned == int(getattr(VehicleOdometry, "VELOCITY_FRAME_FRD", frd_frame)):
        velocity = (frd_to_flu_matrix @ velocity_raw).tolist()
    else:
        raise ValueError("unsupported PX4 VehicleOdometry velocity frame")
    return position, velocity, quaternion


class Px4AdapterNode(Node):
    def __init__(self) -> None:
        super().__init__("uav_tracking_px4_adapter")
        self.declare_parameter("publish_rate_hz", 20.0)
        self.declare_parameter("command_timeout_s", 0.50)
        self.declare_parameter("command_topic", "/tracking/command")
        self.declare_parameter("offboard_control_mode_topic", "/fmu/in/offboard_control_mode")
        self.declare_parameter("trajectory_setpoint_topic", "/fmu/in/trajectory_setpoint")
        self.declare_parameter("vehicle_odometry_topic", "/fmu/out/vehicle_odometry")
        self.declare_parameter("vehicle_odom_topic", "/vehicle/odometry")
        # PX4 v1.17 / px4_msgs publishes VehicleStatus as ``vehicle_status_v1``.
        # Keep this as a parameter so older PX4 branches can override it.
        self.declare_parameter("vehicle_status_topic", "/fmu/out/vehicle_status_v1")
        self.declare_parameter("vehicle_command_ack_topic", "/fmu/out/vehicle_command_ack")
        # Keep this opt-in so a pure Gazebo/ROS bridge can use the adapter's
        # frame conversion without also running PX4.  SITL runs should enable
        # it to prevent motion commands before the vehicle is armed and in
        # OFFBOARD mode.
        self.declare_parameter("require_vehicle_status", False)
        self.declare_parameter("vehicle_status_timeout_s", 1.0)
        self._last_command: Any = None
        self._last_vehicle_status: Any = None
        self._last_vehicle_status_receipt_ns = 0
        self._last_ready_state: bool | None = None
        self._heartbeat_pub = self.create_publisher(
            OffboardControlMode, str(self.get_parameter("offboard_control_mode_topic").value), 10
        )
        self._setpoint_pub = self.create_publisher(
            TrajectorySetpoint, str(self.get_parameter("trajectory_setpoint_topic").value), 10
        )
        self._vehicle_odom_pub = self.create_publisher(
            Odometry, str(self.get_parameter("vehicle_odom_topic").value), 20
        )
        self.create_subscription(TrackingCommand, str(self.get_parameter("command_topic").value), self._on_command, 20)
        self.create_subscription(
            VehicleOdometry,
            str(self.get_parameter("vehicle_odometry_topic").value),
            self._on_vehicle_odometry,
            qos_profile_sensor_data,
        )
        self.create_subscription(
            VehicleStatus,
            str(self.get_parameter("vehicle_status_topic").value),
            self._on_vehicle_status,
            qos_profile_sensor_data,
        )
        # PX4 publishes an acknowledgement for each VehicleCommand.  The
        # adapter currently does not arm or change modes itself, but recording
        # this stream makes SITL handoff and any future command extension
        # auditable without coupling the controller to px4_msgs.
        if VehicleCommandAck is not None:
            self.create_subscription(
                VehicleCommandAck,
                str(self.get_parameter("vehicle_command_ack_topic").value),
                self._on_vehicle_command_ack,
                qos_profile_sensor_data,
            )
        self.create_timer(1.0 / float(self.get_parameter("publish_rate_hz").value), self._publish)

    def _on_command(self, message: TrackingCommand) -> None:
        self._last_command = message

    def _on_vehicle_odometry(self, message: Any) -> None:
        try:
            position, velocity, quaternion = px4_odometry_to_enu(message)
        except (TypeError, ValueError) as exc:
            self.get_logger().warning(
                f"PX4 vehicle odometry conversion failed: {exc}", throttle_duration_sec=2.0
            )
            return
        odometry = Odometry()
        # PX4 timestamps are in the flight controller's boot-time domain, so
        # use the ROS clock for the transport age used by the controller.
        odometry.header.stamp = self.get_clock().now().to_msg()
        odometry.header.frame_id = "map"
        odometry.child_frame_id = "base_link"
        odometry.pose.pose.position.x, odometry.pose.pose.position.y, odometry.pose.pose.position.z = position
        odometry.pose.pose.orientation.x, odometry.pose.pose.orientation.y = quaternion[:2]
        odometry.pose.pose.orientation.z, odometry.pose.pose.orientation.w = quaternion[2:]
        odometry.twist.twist.linear.x, odometry.twist.twist.linear.y, odometry.twist.twist.linear.z = velocity
        self._vehicle_odom_pub.publish(odometry)

    def _on_vehicle_status(self, message: Any) -> None:
        self._last_vehicle_status = message
        self._last_vehicle_status_receipt_ns = int(self.get_clock().now().nanoseconds)

    def _on_vehicle_command_ack(self, message: Any) -> None:
        """Log command acknowledgements for SITL audit trails.

        The generated PX4 message uses numeric result codes.  Keep the raw
        values in the log so a rosbag can be correlated with the exact PX4
        firmware and message definition used for a trial.
        """

        command = int(getattr(message, "command", -1))
        result = int(getattr(message, "result", -1))
        result_param1 = int(getattr(message, "result_param1", -1))
        result_param2 = int(getattr(message, "result_param2", -1))
        timestamp = int(getattr(message, "timestamp", 0))
        self.get_logger().info(
            "PX4 command acknowledgement: "
            f"command={command} result={result} "
            f"result_param1={result_param1} result_param2={result_param2} "
            f"timestamp_us={timestamp}"
        )

    def _vehicle_ready(self) -> bool:
        """Return whether PX4 allows motion setpoints to pass through.

        A status message is itself the connection/liveness signal.  The
        arming and navigation constants are read from the generated message
        so this remains compatible with the PX4 v1.17 ``px4_msgs`` branch and
        avoids hard-coding enum values in the control path.  The check is
        disabled for non-PX4 Gazebo bridge runs by ``require_vehicle_status``.
        """

        if not bool(self.get_parameter("require_vehicle_status").value):
            return True
        status = self._last_vehicle_status
        if status is None:
            return False
        now_ns = int(self.get_clock().now().nanoseconds)
        receipt_ns = self._last_vehicle_status_receipt_ns
        if now_ns > 0 and receipt_ns > 0:
            timeout_s = float(self.get_parameter("vehicle_status_timeout_s").value)
            if (now_ns - receipt_ns) * 1e-9 > timeout_s:
                return False
        armed = int(getattr(status, "arming_state", -1)) == int(
            getattr(VehicleStatus, "ARMING_STATE_ARMED", 2)
        )
        offboard = int(getattr(status, "nav_state", -1)) == int(
            getattr(VehicleStatus, "NAVIGATION_STATE_OFFBOARD", 14)
        )
        preflight = bool(getattr(status, "pre_flight_checks_pass", True))
        failsafe = bool(getattr(status, "failsafe", False))
        return armed and offboard and preflight and not failsafe

    def _publish(self) -> None:
        now = self.get_clock().now().nanoseconds // 1000
        command = self._last_command
        command_fresh = self._command_is_fresh(command)
        vehicle_ready = self._vehicle_ready()
        if self._last_ready_state is None or vehicle_ready != self._last_ready_state:
            if bool(self.get_parameter("require_vehicle_status").value):
                self.get_logger().info(
                    "PX4 motion gate: "
                    + (
                        "ready (armed + OFFBOARD)"
                        if vehicle_ready
                        else "holding (waiting for armed OFFBOARD)"
                    )
                )
            self._last_ready_state = vehicle_ready
        motion_allowed = command_fresh and command.valid and vehicle_ready
        position_mode = motion_allowed and command.mode == TrackingCommand.MODE_POSITION
        heartbeat = OffboardControlMode()
        heartbeat.timestamp = now
        heartbeat.position = position_mode
        heartbeat.velocity = not position_mode
        heartbeat.acceleration = False
        heartbeat.attitude = False
        heartbeat.body_rate = False
        heartbeat.thrust_and_torque = False
        heartbeat.direct_actuator = False
        self._heartbeat_pub.publish(heartbeat)

        setpoint = TrajectorySetpoint()
        setpoint.timestamp = now
        # PX4 interprets every finite TrajectorySetpoint field as active. ROS
        # message defaults are zero, so leaving position at its default in a
        # velocity hold can accidentally ask PX4 to return to the origin.
        setpoint.position = [float("nan")] * 3
        setpoint.velocity = [float("nan")] * 3
        setpoint.acceleration = [float("nan")] * 3
        setpoint.jerk = [float("nan")] * 3
        setpoint.yaw = float("nan")
        setpoint.yawspeed = float("nan")
        if not motion_allowed or command.mode in (TrackingCommand.MODE_HOLD, TrackingCommand.MODE_FAILSAFE):
            setpoint.velocity = [0.0, 0.0, 0.0]
            setpoint.yawspeed = 0.0
        elif command.mode == TrackingCommand.MODE_POSITION:
            setpoint.position = enu_to_ned([command.position_m.x, command.position_m.y, command.position_m.z])
            setpoint.velocity = [float("nan"), float("nan"), float("nan")]
            setpoint.yaw = enu_yaw_to_ned(command.yaw_rad)
            setpoint.yawspeed = enu_yaw_rate_to_ned(command.yaw_rate_radps)
        elif command.mode == TrackingCommand.MODE_VELOCITY:
            setpoint.velocity = enu_to_ned([command.linear_mps.x, command.linear_mps.y, command.linear_mps.z])
            setpoint.position = [float("nan"), float("nan"), float("nan")]
            setpoint.yaw = enu_yaw_to_ned(command.yaw_rad)
            setpoint.yawspeed = enu_yaw_rate_to_ned(command.yaw_rate_radps)
        else:
            # SEARCH and future modes have no PX4 semantics yet; hold until
            # a bounded mode-specific adapter is implemented.
            setpoint.velocity = [0.0, 0.0, 0.0]
            setpoint.yawspeed = 0.0
        self._setpoint_pub.publish(setpoint)

    def _command_is_fresh(self, command: Any) -> bool:
        """Reject stale commands before forwarding motion to PX4.

        Require a valid simulation clock and source stamp.  A small future
        skew of at most 50 ms is tolerated, matching the flight supervisor.
        """

        if command is None:
            return False
        stamp = command.header.stamp
        command_ns = int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
        now_ns = int(self.get_clock().now().nanoseconds)
        if command_ns <= 0 or now_ns <= 0 or command_ns - now_ns > 50_000_000:
            return False
        age_s = max(0, now_ns - command_ns) * 1e-9
        return age_s <= float(self.get_parameter("command_timeout_s").value)


def main(args: list[str] | None = None) -> None:
    if rclpy is None:
        raise RuntimeError("ROS 2 and px4_msgs are required to run px4_adapter")
    rclpy.init(args=args)
    node = None
    try:
        node = Px4AdapterNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            if node is not None:
                node.destroy_node()
        finally:
            rclpy.try_shutdown()


if __name__ == "__main__":
    main()
