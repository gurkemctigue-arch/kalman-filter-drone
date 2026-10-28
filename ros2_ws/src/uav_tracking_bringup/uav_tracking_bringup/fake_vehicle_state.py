"""Static vehicle odometry publisher for the stage-one sensor smoke test.

This node is deliberately a test-only stand-in for PX4's vehicle odometry.
It keeps the stationary RGB-D rig's controller graph alive while Gazebo/PX4
SITL is being installed.  It never publishes target state or reads Gazebo
truth, and it must be disabled for PX4 flight-stack trials.
"""

from __future__ import annotations

import math

try:
    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
except ImportError:  # pragma: no cover - ROS 2 only.
    rclpy = None
    Node = object  # type: ignore[misc,assignment]


class FakeVehicleStateNode(Node):
    def __init__(self) -> None:
        super().__init__("uav_tracking_fake_vehicle_state")
        self.declare_parameter("publish_rate_hz", 30.0)
        self.declare_parameter("odom_topic", "/vehicle/odometry")
        self.declare_parameter("frame_id", "map")
        self.declare_parameter("child_frame_id", "base_link")
        self.declare_parameter("position_m", [0.0, 0.0, 3.0])
        self.declare_parameter("yaw_rad", 0.0)
        self._publisher = self.create_publisher(
            Odometry, str(self.get_parameter("odom_topic").value), 10
        )
        rate = max(1.0, float(self.get_parameter("publish_rate_hz").value))
        self.create_timer(1.0 / rate, self._publish)

    def _publish(self) -> None:
        position = [float(value) for value in self.get_parameter("position_m").value]
        if len(position) != 3:
            self.get_logger().error("position_m must contain three values")
            return
        yaw = float(self.get_parameter("yaw_rad").value)
        message = Odometry()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = str(self.get_parameter("frame_id").value)
        message.child_frame_id = str(self.get_parameter("child_frame_id").value)
        message.pose.pose.position.x, message.pose.pose.position.y, message.pose.pose.position.z = position
        message.pose.pose.orientation.z = math.sin(yaw / 2.0)
        message.pose.pose.orientation.w = math.cos(yaw / 2.0)
        message.twist.twist.linear.x = 0.0
        message.twist.twist.linear.y = 0.0
        message.twist.twist.linear.z = 0.0
        self._publisher.publish(message)


def main(args: list[str] | None = None) -> None:
    if rclpy is None:
        raise RuntimeError("ROS 2 is required to run fake_vehicle_state")
    rclpy.init(args=args)
    node = FakeVehicleStateNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
