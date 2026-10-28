"""PX4 map/body TF and fixed or feedback-driven optical camera mount."""

from __future__ import annotations

import math

try:
    import rclpy
    from rclpy.executors import ExternalShutdownException
    from geometry_msgs.msg import TransformStamped
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import JointState
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster
except ImportError:
    rclpy = None
    Node = object  # type: ignore[assignment,misc]

from uav_tracking.control.gimbal_geometry import camera_optical_quaternion, ordered_joint_positions


def optical_mount_quaternion(pitch_rad: float) -> tuple[float, float, float, float]:
    """Body FLU <- downward-pitched camera optical (right, down, forward)."""

    if not math.isfinite(pitch_rad):
        raise ValueError("camera pitch must be finite")
    # q_y(pitch) * q_optical_to_flu(-.5,.5,-.5,.5), ROS xyzw order.
    sine, cosine = math.sin(pitch_rad / 2.0), math.cos(pitch_rad / 2.0)
    return (-(cosine + sine) / 2.0, (cosine + sine) / 2.0, (sine - cosine) / 2.0, (cosine - sine) / 2.0)


class FlightTfNode(Node):
    def __init__(self) -> None:
        super().__init__("uav_tracking_flight_tf")
        for name, value in {
            "vehicle_odom_topic": "/vehicle/odometry",
            "state_frame": "map", "base_frame": "base_link", "camera_frame": "camera_link",
            "camera_x_m": 0.13233, "camera_y_m": 0.0, "camera_z_m": 0.26078,
            "camera_pitch_rad": 0.35,
            "camera_mount_mode": "fixed", "joint_state_topic": "/gimbal/joint_states",
        }.items():
            self.declare_parameter(name, value)
        self._dynamic = TransformBroadcaster(self)
        self._static = StaticTransformBroadcaster(self)
        mount_mode = str(self.get_parameter("camera_mount_mode").value)
        self._joint_stamp_ns = -1
        if mount_mode == "fixed":
            transform = self._camera_transform(self.get_clock().now().to_msg())
            q = optical_mount_quaternion(float(self.get_parameter("camera_pitch_rad").value))
            transform.transform.rotation.x, transform.transform.rotation.y = q[:2]
            transform.transform.rotation.z, transform.transform.rotation.w = q[2:]
            self._static.sendTransform(transform)
        elif mount_mode == "gimbal":
            self.create_subscription(JointState, str(self.get_parameter("joint_state_topic").value), self._on_joint, qos_profile_sensor_data)
        else:
            raise ValueError("camera_mount_mode must be fixed or gimbal")
        self.create_subscription(Odometry, str(self.get_parameter("vehicle_odom_topic").value), self._on_odom, qos_profile_sensor_data)

    def _camera_transform(self, stamp: object) -> "TransformStamped":
        transform = TransformStamped()
        transform.header.stamp = stamp
        transform.header.frame_id = str(self.get_parameter("base_frame").value)
        transform.child_frame_id = str(self.get_parameter("camera_frame").value)
        transform.transform.translation.x = float(self.get_parameter("camera_x_m").value)
        transform.transform.translation.y = float(self.get_parameter("camera_y_m").value)
        transform.transform.translation.z = float(self.get_parameter("camera_z_m").value)
        return transform

    def _on_joint(self, message: "JointState") -> None:
        """Broadcast source-time feedback, never command-time setpoints.

        tf2 retains these dynamic samples and interpolates them for each
        image's original timestamp. Missing samples cause the estimator's
        existing lookup to fail instead of silently using a commanded pose.
        """

        stamp_ns = int(message.header.stamp.sec) * 1_000_000_000 + int(message.header.stamp.nanosec)
        now_ns = int(self.get_clock().now().nanoseconds)
        if stamp_ns <= 0 or stamp_ns - now_ns > 50_000_000 or now_ns - stamp_ns > 200_000_000:
            return
        # A reset is a new simulation epoch; do not block all new samples
        # behind the previous run's larger source timestamps.
        if now_ns < self._joint_stamp_ns:
            self._joint_stamp_ns = -1
        if stamp_ns <= self._joint_stamp_ns:
            return
        try:
            angles = ordered_joint_positions(message.name, message.position)
            q = camera_optical_quaternion(angles, float(self.get_parameter("camera_pitch_rad").value))
        except (TypeError, ValueError):
            return
        transform = self._camera_transform(message.header.stamp)
        transform.transform.rotation.x, transform.transform.rotation.y = q[:2]
        transform.transform.rotation.z, transform.transform.rotation.w = q[2:]
        self._dynamic.sendTransform(transform)
        self._joint_stamp_ns = stamp_ns

    def _on_odom(self, message: "Odometry") -> None:
        position, rotation = message.pose.pose.position, message.pose.pose.orientation
        if not all(math.isfinite(float(v)) for v in (position.x, position.y, position.z, rotation.x, rotation.y, rotation.z, rotation.w)):
            return
        norm = math.sqrt(sum(float(v) ** 2 for v in (rotation.x, rotation.y, rotation.z, rotation.w)))
        if norm < 1e-9 or message.header.frame_id != str(self.get_parameter("state_frame").value):
            return
        transform = TransformStamped()
        transform.header = message.header
        transform.child_frame_id = str(self.get_parameter("base_frame").value)
        transform.transform.translation.x, transform.transform.translation.y, transform.transform.translation.z = position.x, position.y, position.z
        transform.transform.rotation.x, transform.transform.rotation.y = rotation.x / norm, rotation.y / norm
        transform.transform.rotation.z, transform.transform.rotation.w = rotation.z / norm, rotation.w / norm
        self._dynamic.sendTransform(transform)


def main(args: list[str] | None = None) -> None:
    if rclpy is None:
        raise RuntimeError("ROS 2 is required")
    rclpy.init(args=args)
    node = None
    try:
        node = FlightTfNode()
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
