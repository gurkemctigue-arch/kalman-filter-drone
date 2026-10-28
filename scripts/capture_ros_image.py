"""Capture one ROS Image message as a PNG for simulator diagnostics."""

from pathlib import Path

import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image


class ImageCapture(Node):
    def __init__(self, topic: str, output: Path) -> None:
        super().__init__("stage1_image_capture")
        self._output = output
        self._bridge = CvBridge()
        self.done = False
        self.create_subscription(Image, topic, self._on_image, 10)

    def _on_image(self, message: Image) -> None:
        image = self._bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
        self._output.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(self._output), image):
            raise RuntimeError(f"could not write {self._output}")
        self.get_logger().info(f"saved {self._output}")
        self.done = True


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("topic")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rclpy.init()
    node = ImageCapture(args.topic, args.output)
    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=1.0)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
