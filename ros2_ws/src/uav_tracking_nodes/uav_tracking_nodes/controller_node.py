"""ROS 2 outer-loop controller adapter."""

from __future__ import annotations

import math

import numpy as np

from uav_tracking.ros_lifecycle import shutdown_requests

try:
    import rclpy
    from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
    from rclpy.signals import SignalHandlerOptions
    from nav_msgs.msg import Odometry
    from geometry_msgs.msg import Vector3Stamped
    from rclpy.node import Node
    from uav_tracking_interfaces.msg import TargetState, TrackingCommand, TrackingStatus
except ImportError:  # pragma: no cover
    rclpy = None
    Node = object  # type: ignore[misc,assignment]

from uav_tracking.control import FollowConfig, FollowController, TargetState as CoreTargetState, VehicleState


def _rotation_from_quaternion(q: object) -> np.ndarray:
    """Return the Odometry child-to-header rotation, normalizing ROS xyzw."""

    values = np.asarray([q.x, q.y, q.z, q.w], dtype=float)
    norm = float(np.linalg.norm(values))
    if not np.all(np.isfinite(values)) or norm <= 1e-12:
        raise ValueError("vehicle orientation must be a finite nonzero quaternion")
    x, y, z, w = values / norm
    return np.array([
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
        [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
        [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
    ])


def _yaw_from_quaternion(q: object) -> float:
    rotation = _rotation_from_quaternion(q)
    return math.atan2(float(rotation[1, 0]), float(rotation[0, 0]))


def fresh_gimbal_yaw(reference: object, now_ns: int, frame: str, timeout_s: float = 0.3) -> float | None:
    if reference is None or reference.header.frame_id != frame:
        return None
    stamp = reference.header.stamp.sec * 1_000_000_000 + reference.header.stamp.nanosec
    age = (now_ns - stamp) * 1e-9
    value = float(reference.vector.z)
    if stamp <= 0 or not 0 <= age <= timeout_s or not math.isfinite(value):
        return None
    return value


class ControllerNode(Node):
    def __init__(self) -> None:
        super().__init__("uav_tracking_controller")
        self.declare_parameter("command_mode", "velocity")
        self.declare_parameter("control_rate_hz", 20.0)
        self.declare_parameter("desired_distance_m", 5.0)
        self.declare_parameter("desired_height_m", 2.0)
        self.declare_parameter("max_velocity_mps", [2.0, 2.0, 1.0])
        self.declare_parameter("position_gain", [0.60, 0.60, 0.50])
        self.declare_parameter("integral_gain", [0.02, 0.02, 0.02])
        self.declare_parameter("integral_limit", 2.0)
        self.declare_parameter("max_acceleration_mps2", [3.0, 3.0, 3.0])
        self.declare_parameter("slew_position", True)
        self.declare_parameter("max_position_lead_m", [1.0, 1.0, 0.5])
        self.declare_parameter("desired_offset_m", [0.0, 0.0, 0.0])
        self.declare_parameter("deadzone_m", 0.0)
        self.declare_parameter("failsafe_mode", "hold")
        self.declare_parameter("prediction_timeout_s", 0.75)
        self.declare_parameter("vehicle_timeout_s", 0.50)
        self.declare_parameter("state_topic", "/tracking/state")
        self.declare_parameter("command_topic", "/tracking/command")
        self.declare_parameter("status_topic", "/tracking/status")
        self.declare_parameter("vehicle_odom_topic", "/vehicle/odometry")
        self.declare_parameter("enable_gimbal_yaw_reference", False)
        self.declare_parameter("gimbal_yaw_reference_topic", "/gimbal/body_yaw_reference")
        self._gimbal_yaw_enabled = bool(self.get_parameter("enable_gimbal_yaw_reference").value)
        self._gimbal_yaw_reference = None
        mode = str(self.get_parameter("command_mode").value).lower()
        self._controller = FollowController(
            config=FollowConfig(
                mode=mode,
                desired_distance=float(self.get_parameter("desired_distance_m").value),
                desired_height=float(self.get_parameter("desired_height_m").value),
                desired_offset=np.asarray(self.get_parameter("desired_offset_m").value, dtype=float),
                position_gain=np.asarray(self.get_parameter("position_gain").value, dtype=float),
                integral_gain=np.asarray(self.get_parameter("integral_gain").value, dtype=float),
                integral_limit=float(self.get_parameter("integral_limit").value),
                max_acceleration=np.asarray(self.get_parameter("max_acceleration_mps2").value, dtype=float),
                slew_position=bool(self.get_parameter("slew_position").value),
                max_position_lead=np.asarray(self.get_parameter("max_position_lead_m").value, dtype=float),
                deadzone=float(self.get_parameter("deadzone_m").value),
                max_speed=np.asarray(self.get_parameter("max_velocity_mps").value, dtype=float),
                target_timeout=float(self.get_parameter("prediction_timeout_s").value),
                vehicle_timeout=float(self.get_parameter("vehicle_timeout_s").value),
                failsafe_mode=str(self.get_parameter("failsafe_mode").value),
            )
        )
        self._target: TargetState | None = None
        self._vehicle: Odometry | None = None
        self._command_pub = self.create_publisher(TrackingCommand, str(self.get_parameter("command_topic").value), 20)
        self._status_pub = self.create_publisher(TrackingStatus, str(self.get_parameter("status_topic").value), 20)
        self.create_subscription(TargetState, str(self.get_parameter("state_topic").value), self._on_target, 20)
        self.create_subscription(Odometry, str(self.get_parameter("vehicle_odom_topic").value), self._on_vehicle, 20)
        if self._gimbal_yaw_enabled:
            self.create_subscription(Vector3Stamped, str(self.get_parameter("gimbal_yaw_reference_topic").value), self._on_gimbal_yaw, 10)
        rate = float(self.get_parameter("control_rate_hz").value)
        self.create_timer(1.0 / rate, self._step)

    def _on_target(self, message: TargetState) -> None:
        self._target = message

    def _on_vehicle(self, message: Odometry) -> None:
        self._vehicle = message

    def _on_gimbal_yaw(self, message) -> None:
        self._gimbal_yaw_reference = message

    def _step(self) -> None:
        tick = self.get_clock().now()
        now = tick.to_msg()
        if self._target is None or self._vehicle is None:
            self._publish_failsafe(now, "missing_state")
            return
        target = self._target
        vehicle = self._vehicle
        # Only measured and short-term predicted states are valid controller
        # inputs.  An uninitialized/lost message carries zero-valued geometry
        # for transport compatibility and must never be treated as a target.
        target_valid = target.state in (TargetState.STATE_MEASURED, TargetState.STATE_PREDICTED)
        target_age = float(target.prediction_age_s)
        target_stamp = int(target.header.stamp.sec) * 1_000_000_000 + int(target.header.stamp.nanosec)
        now_ns = int(tick.nanoseconds)
        if now_ns <= 0:
            self._publish_failsafe(now, "invalid_clock")
            return
        vehicle_stamp = int(vehicle.header.stamp.sec) * 1_000_000_000 + int(vehicle.header.stamp.nanosec)
        # A missing or invalid source time cannot become a fresh command by
        # restamping it here.  Allow at most 50 ms of clock skew, as in the
        # flight supervisor; tolerated future times contribute zero age.
        if target_stamp <= 0 or target_stamp - now_ns > 50_000_000:
            self._publish_failsafe(now, "invalid_target_timestamp")
            return
        if vehicle_stamp <= 0 or vehicle_stamp - now_ns > 50_000_000:
            self._publish_failsafe(now, "invalid_vehicle_timestamp")
            return
        # Combine prediction and transport age so a silent estimator stream
        # cannot leave the controller using an old message forever.
        target_age += max(0, now_ns - target_stamp) * 1e-9
        vehicle_age = max(0, now_ns - vehicle_stamp) * 1e-9
        try:
            rotation = _rotation_from_quaternion(vehicle.pose.pose.orientation)
        except (TypeError, ValueError):
            self._publish_failsafe(now, "invalid_vehicle_orientation")
            return
        # nav_msgs/Odometry twist is in child_frame_id (body FLU), while the
        # portable controller requires velocity in the pose/world frame.
        linear = vehicle.twist.twist.linear
        vehicle_velocity = rotation @ np.asarray([linear.x, linear.y, linear.z], dtype=float)
        target_frame = str(target.header.frame_id or vehicle.header.frame_id or "map")
        vehicle_frame = str(vehicle.header.frame_id or target.header.frame_id or "map")
        core_target = CoreTargetState(
            position=[target.position_m.x, target.position_m.y, target.position_m.z],
            velocity=[target.velocity_mps.x, target.velocity_mps.y, target.velocity_mps.z],
            valid=target_valid,
            age=target_age,
            covariance=np.asarray(target.covariance, dtype=float).reshape(6, 6),
            confidence=1.0,
            frame=target_frame,
            timestamp=(target_stamp * 1e-9 if target_stamp > 0 else None),
        )
        core_vehicle = VehicleState(
            position=[vehicle.pose.pose.position.x, vehicle.pose.pose.position.y, vehicle.pose.pose.position.z],
            velocity=vehicle_velocity,
            yaw=math.atan2(float(rotation[1, 0]), float(rotation[0, 0])),
            age=vehicle_age,
            frame=vehicle_frame,
            timestamp=(vehicle_stamp * 1e-9 if vehicle_stamp > 0 else None),
        )
        command = self._controller.update(core_target, core_vehicle, dt=1.0 / float(self.get_parameter("control_rate_hz").value))
        message = TrackingCommand()
        message.header.stamp = now
        message.header.frame_id = target_frame
        message.track_id = int(target.track_id)
        message.valid = bool(command.valid and not command.failsafe)
        if command.mode == "velocity":
            message.mode = TrackingCommand.MODE_VELOCITY if message.valid else TrackingCommand.MODE_FAILSAFE
            message.linear_mps.x, message.linear_mps.y, message.linear_mps.z = command.value
        else:
            message.mode = TrackingCommand.MODE_POSITION if message.valid else TrackingCommand.MODE_FAILSAFE
            message.position_m.x, message.position_m.y, message.position_m.z = command.value
        message.yaw_rad = float(command.yaw or 0.0)
        message.yaw_rate_radps = float(command.yaw_rate or 0.0)
        if getattr(self, "_gimbal_yaw_enabled", False) and message.valid:
            reference_yaw = fresh_gimbal_yaw(self._gimbal_yaw_reference, now_ns, target_frame)
            if reference_yaw is not None:
                message.yaw_rad = reference_yaw
        self._command_pub.publish(message)
        status = TrackingStatus()
        status.header = message.header
        status.track_id = message.track_id
        status.target_visible = bool(target.target_visible)
        status.prediction_active = target.state == TargetState.STATE_PREDICTED
        status.time_since_measurement_s = float(target_age)
        if target_valid:
            horizontal_distance = math.hypot(
                float(target.position_m.x - vehicle.pose.pose.position.x),
                float(target.position_m.y - vehicle.pose.pose.position.y),
            )
            desired_distance = float(self.get_parameter("desired_distance_m").value)
            desired_height = float(self.get_parameter("desired_height_m").value)
            status.distance_error_m = float(horizontal_distance - desired_distance)
            status.height_error_m = float(
                (vehicle.pose.pose.position.z - target.position_m.z) - desired_height
            )
        if message.valid and target.state == TargetState.STATE_PREDICTED:
            status.lifecycle = TrackingStatus.LIFECYCLE_PREDICT
            status.reason = "coasting_prediction"
        elif message.valid:
            status.lifecycle = TrackingStatus.LIFECYCLE_FOLLOW
            status.reason = "tracking"
        else:
            status.lifecycle = TrackingStatus.LIFECYCLE_HOVER
            status.reason = (
                "target_ambiguous" if target.state == TargetState.STATE_AMBIGUOUS
                else command.reason or "controller_failsafe"
            )
        self._status_pub.publish(status)

    def _publish_failsafe(self, stamp: object, reason: str) -> None:
        message = TrackingCommand()
        message.header.stamp = stamp
        message.header.frame_id = "map"
        message.mode = TrackingCommand.MODE_FAILSAFE
        message.valid = False
        self._command_pub.publish(message)
        status = TrackingStatus()
        status.header = message.header
        status.lifecycle = TrackingStatus.LIFECYCLE_FAILSAFE
        status.reason = reason
        self._status_pub.publish(status)


def main(args: list[str] | None = None) -> None:
    if rclpy is None:
        raise RuntimeError("ROS 2 and this node's message dependencies are required")
    with shutdown_requests() as requested:
        # The default rclpy signal handler can invalidate the context during
        # subscription.take_message. Stop the executor before the context.
        rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
        node = None
        executor = None
        try:
            node = ControllerNode()
            executor = SingleThreadedExecutor(context=node.context)
            executor.add_node(node)
            while node.context.ok() and not requested.is_set():
                executor.spin_once(timeout_sec=0.2)
        except (KeyboardInterrupt, ExternalShutdownException):
            pass
        finally:
            try:
                try:
                    if executor is not None:
                        executor.shutdown()
                finally:
                    if node is not None:
                        node.destroy_node()
            finally:
                rclpy.try_shutdown()


if __name__ == "__main__":
    main()
