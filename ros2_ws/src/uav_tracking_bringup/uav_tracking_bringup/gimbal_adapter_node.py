"""Three physical Gazebo joints, with independent command and feedback paths.

The runtime controller only consumes image-derived target state, PX4
odometry, and sensor joint feedback. No entity names or ground truth enter
the target selection or control path.
"""

from __future__ import annotations

import json
import math

import numpy as np

try:
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from geometry_msgs.msg import Vector3Stamped
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import JointState
    from std_msgs.msg import Float64, String
    from uav_tracking_interfaces.msg import TargetState
except ImportError:
    rclpy = None
    Node = object  # type: ignore[assignment,misc]

from uav_tracking.control.gimbal_geometry import (
    BodyYawReference, MOUNT_TRANSLATION, bounded_joint_command, camera_optical_quaternion,
    desired_joint_angles, ordered_joint_positions, quaternion_rotation,
)


def source_age_seconds(stamp: object, now_ns: int) -> float:
    source = int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
    if source <= 0 or now_ns <= 0 or source - now_ns > 50_000_000:
        raise ValueError("invalid source timestamp")
    return max(0, now_ns - source) * 1e-9


class GimbalAdapterNode(Node):
    def __init__(self) -> None:
        super().__init__("uav_tracking_gimbal")
        for key, value in {
            "gimbal_mode": "active", "control_rate_hz": 50.0,
            "joint_state_topic": "/gimbal/joint_states",
            "target_state_topic": "/tracking/state", "vehicle_odom_topic": "/vehicle/odometry",
            "joint_feedback_timeout_s": 0.20, "vehicle_timeout_s": 0.50,
            "target_timeout_s": 0.75, "max_command_lead_rad": 0.20,
            "max_joint_rate_radps": [1.0, 0.8, 1.0], "joint_position_gain": [4.0, 4.0, 5.0],
            "body_yaw_recenter_gain": 0.6, "max_body_yaw_rate_radps": 0.10,
            "max_body_yaw_reference_lead_rad": 0.20,
            "body_yaw_deadzone_rad": 0.15,
        }.items():
            self.declare_parameter(key, value)
        self._joint = self._target = self._vehicle = None
        self._last_command: np.ndarray | None = None
        self._last_tick_ns: int | None = None
        self._body_yaw = BodyYawReference(
            max_rate=float(self.get_parameter("max_body_yaw_rate_radps").value),
            gain=float(self.get_parameter("body_yaw_recenter_gain").value),
            deadzone=float(self.get_parameter("body_yaw_deadzone_rad").value),
            max_lead=float(self.get_parameter("max_body_yaw_reference_lead_rad").value),
        )
        self._commands = [self.create_publisher(Float64, f"/gimbal/{axis}/cmd_pos", 10) for axis in ("yaw", "pitch", "roll")]
        self._diagnostics = self.create_publisher(String, "/gimbal/diagnostics", 20)
        self._yaw_reference = self.create_publisher(Vector3Stamped, "/gimbal/body_yaw_reference", 10)
        self.create_subscription(JointState, str(self.get_parameter("joint_state_topic").value), self._on_joint, qos_profile_sensor_data)
        self.create_subscription(TargetState, str(self.get_parameter("target_state_topic").value), self._on_target, 20)
        self.create_subscription(Odometry, str(self.get_parameter("vehicle_odom_topic").value), self._on_vehicle, qos_profile_sensor_data)
        rate = float(self.get_parameter("control_rate_hz").value)
        if not math.isfinite(rate) or rate < 5.0:
            raise ValueError("gimbal control_rate_hz must be >=5")
        self.create_timer(1.0 / rate, self._step)

    def _on_joint(self, message: JointState) -> None:
        # Store malformed feedback as well, so it immediately invalidates an
        # earlier valid sample instead of silently prolonging its validity.
        self._joint = message

    def _on_target(self, message: TargetState) -> None:
        self._target = message

    def _on_vehicle(self, message: Odometry) -> None:
        self._vehicle = message

    def _step(self) -> None:
        tick = self.get_clock().now()
        now_ns = int(tick.nanoseconds)
        nominal_dt = 1.0 / float(self.get_parameter("control_rate_hz").value)
        dt = nominal_dt if self._last_tick_ns is None else (now_ns - self._last_tick_ns) * 1e-9
        self._last_tick_ns = now_ns
        reason, active = "", False
        measured = desired = rates = None
        detail: dict[str, object] = {"time_s": now_ns * 1e-9, "mode": str(self.get_parameter("gimbal_mode").value)}
        try:
            if not 0.0 < dt <= 0.2:
                self._last_command = None
                raise ValueError("invalid_control_dt")
            if self._joint is None:
                raise ValueError("missing_joint_feedback")
            measured = ordered_joint_positions(self._joint.name, self._joint.position)
            joint_age = source_age_seconds(self._joint.header.stamp, now_ns)
            detail["joint_age_s"] = joint_age
            if joint_age > float(self.get_parameter("joint_feedback_timeout_s").value):
                raise ValueError("stale_joint_feedback")
            mode = str(self.get_parameter("gimbal_mode").value)
            if mode == "midpoint":
                self._body_yaw.reset()
                desired = np.zeros(3)
                reason = "midpoint"
            elif mode == "active":
                if self._target is None or self._vehicle is None:
                    raise ValueError("missing_target_or_vehicle")
                target, vehicle = self._target, self._vehicle
                target_age = source_age_seconds(target.header.stamp, now_ns) + float(target.prediction_age_s)
                vehicle_age = source_age_seconds(vehicle.header.stamp, now_ns)
                if not math.isfinite(target_age) or target_age < 0 or target_age > float(self.get_parameter("target_timeout_s").value):
                    raise ValueError("stale_target")
                detail.update(target_age_s=target_age, vehicle_age_s=vehicle_age, target_uuid=str(target.target_uuid))
                if target.state not in (TargetState.STATE_MEASURED, TargetState.STATE_PREDICTED):
                    raise ValueError("invalid_target_state")
                if vehicle_age > float(self.get_parameter("vehicle_timeout_s").value):
                    raise ValueError("stale_vehicle")
                if target.header.frame_id != "map" or vehicle.header.frame_id != "map" or vehicle.child_frame_id != "base_link":
                    raise ValueError("invalid_frames")
                q, p = vehicle.pose.pose.orientation, vehicle.pose.pose.position
                rotation = quaternion_rotation([q.x, q.y, q.z, q.w])
                target_position = np.array([target.position_m.x, target.position_m.y, target.position_m.z], dtype=float)
                camera_position = np.array([p.x, p.y, p.z], dtype=float) + rotation @ MOUNT_TRANSLATION
                body_los = rotation.T @ (target_position - camera_position)
                desired = desired_joint_angles(body_los, rotation)
                actual_camera = rotation @ quaternion_rotation(camera_optical_quaternion(measured))
                # Optical x is right, hence image horizon roll is asin(dot
                # optical-right, world-up); zero means horizontal scanlines.
                horizon_error = math.asin(float(np.clip(actual_camera[2, 0], -1.0, 1.0)))
                detail.update(line_of_sight_body_m=body_los.tolist(), horizon_error_rad=horizon_error)
                body_yaw = math.atan2(float(rotation[1, 0]), float(rotation[0, 0]))
                reason, active = "tracking", True
            else:
                raise ValueError("invalid_gimbal_mode")
            previous = measured if self._last_command is None else self._last_command
            command, rates = bounded_joint_command(
                previous, desired, dt,
                self.get_parameter("joint_position_gain").value,
                self.get_parameter("max_joint_rate_radps").value,
            )
            lead = float(self.get_parameter("max_command_lead_rad").value)
            command = np.clip(command, measured - lead, measured + lead)
            self._publish_commands(command)
            if active:
                yaw, yaw_rate, reset = self._body_yaw.update(body_yaw, float(measured[0]), dt, str(target.target_uuid))
                reference = Vector3Stamped()
                reference.header.stamp, reference.header.frame_id = tick.to_msg(), "map"
                reference.vector.z = yaw
                self._yaw_reference.publish(reference)
                detail.update(body_yaw_reference_rad=yaw, body_yaw_recenter_rate_radps=yaw_rate, body_yaw_reference_reset=reset)
        except (TypeError, ValueError, OverflowError) as error:
            active = False
            self._body_yaw.reset()
            reason = str(error)
            # Freeze to the latest actual angle; do not keep integrating an
            # old command or fabricate feedback from the last setpoint.
            if measured is not None:
                self._publish_commands(measured)
            else:
                self._last_command = None
        detail.update(active=active, reason=reason, feedback_angles_rad=None if measured is None else measured.tolist(),
                      desired_angles_rad=None if desired is None else desired.tolist(),
                      command_angles_rad=None if self._last_command is None else self._last_command.tolist(),
                      commanded_rates_radps=None if rates is None else rates.tolist())
        diagnostic = String()
        diagnostic.data = json.dumps(detail, allow_nan=False, separators=(",", ":"))
        self._diagnostics.publish(diagnostic)

    def _publish_commands(self, angles: np.ndarray) -> None:
        self._last_command = angles.copy()
        for publisher, angle in zip(self._commands, angles):
            message = Float64()
            message.data = float(angle)
            publisher.publish(message)


def main(args: list[str] | None = None) -> None:
    if rclpy is None:
        raise RuntimeError("ROS 2 is required")
    rclpy.init(args=args)
    node = None
    try:
        node = GimbalAdapterNode()
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
