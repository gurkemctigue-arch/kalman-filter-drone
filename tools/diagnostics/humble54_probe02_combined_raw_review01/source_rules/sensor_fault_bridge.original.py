"""Seeded simulation sensor perturbations; never reads simulator truth."""

from __future__ import annotations

from collections import deque
import hashlib
import math

import numpy as np

from uav_tracking.ros_lifecycle import shutdown_requests


def perturb_depth(depth: np.ndarray, *, seed: int, stamp_ns: int,
                  noise_std_m: float = 0.0, hole_fraction: float = 0.0) -> np.ndarray:
    """Noise in metres, preserving pre-existing invalid samples and holes."""
    if not 0 <= hole_fraction <= 1 or not math.isfinite(noise_std_m) or noise_std_m < 0:
        raise ValueError("invalid depth perturbation parameters")
    generator = np.random.default_rng(np.random.SeedSequence([seed, stamp_ns & 0xffffffff, stamp_ns >> 32]))
    result = np.asarray(depth, dtype=np.float32).copy()
    valid = np.isfinite(result) & (result > 0)
    if noise_std_m:
        # Shared frame bias plus per-pixel noise models correlated depth errors.
        bias = generator.normal(0.0, noise_std_m)
        result[valid] += bias + generator.normal(0.0, noise_std_m, np.count_nonzero(valid))
    if hole_fraction:
        result[generator.random(result.shape) < hole_fraction] = np.nan
    result[valid & (result <= 0)] = np.nan
    return result


def frame_dropped(seed: int, stamp_ns: int, fraction: float) -> bool:
    if not 0 <= fraction <= 1:
        raise ValueError("drop fraction must be in [0,1]")
    # Whole 200 ms acquisition windows are shared by RGB and depth. The result
    # depends on source time, not callback order or wall-clock scheduling.
    window = stamp_ns // 200_000_000
    digest = hashlib.sha256(f"{seed}:{window}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < fraction


def main() -> None:
    import rclpy
    from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.parameter import Parameter
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from rclpy.signals import SignalHandlerOptions
    from sensor_msgs.msg import Image, CameraInfo
    from cv_bridge import CvBridge

    class FaultBridge(Node):
        def __init__(self):
            super().__init__("research_sensor_faults", parameter_overrides=[Parameter("use_sim_time", value=True)])
            for name, default in {"seed": 0, "noise_std_m": 0.0, "hole_fraction": 0.0,
                                  "drop_fraction": 0.0, "delay_s": 0.0}.items():
                self.declare_parameter(name, default)
            self.seed = int(self.get_parameter("seed").value)
            self.noise = float(self.get_parameter("noise_std_m").value)
            self.holes = float(self.get_parameter("hole_fraction").value)
            self.drop = float(self.get_parameter("drop_fraction").value)
            self.delay = float(self.get_parameter("delay_s").value)
            if self.seed < 0 or not 0 <= self.drop <= 1 or not 0 <= self.delay <= 1:
                raise ValueError("invalid seed/drop/delay")
            perturb_depth(np.ones((1, 1)), seed=self.seed, stamp_ns=0,
                          noise_std_m=self.noise, hole_fraction=self.holes)
            self.bridge = CvBridge()
            self.pending = deque(maxlen=120)
            qos = QoSProfile(depth=2, reliability=ReliabilityPolicy.RELIABLE)
            self.rgb = self.create_publisher(Image, "/research/camera/color/image_raw", qos)
            self.depth = self.create_publisher(Image, "/research/camera/aligned_depth_to_color/image_raw", qos)
            self.info = self.create_publisher(CameraInfo, "/research/camera/color/camera_info", qos)
            self.create_subscription(Image, "/camera/color/image_raw", self.on_rgb, qos)
            self.create_subscription(Image, "/camera/aligned_depth_to_color/image_raw", self.on_depth, qos)
            self.create_subscription(CameraInfo, "/camera/color/camera_info", self.info.publish, qos)
            self.create_timer(0.01, self.flush)

        def enqueue(self, publisher, message):
            stamp_ns = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
            if not frame_dropped(self.seed, stamp_ns, self.drop):
                self.pending.append((self.get_clock().now().nanoseconds + int(self.delay * 1e9), publisher, message))

        def on_rgb(self, message):
            self.enqueue(self.rgb, message)

        def on_depth(self, message):
            if self.noise or self.holes:
                stamp_ns = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
                data = self.bridge.imgmsg_to_cv2(message, desired_encoding="passthrough")
                changed = self.bridge.cv2_to_imgmsg(perturb_depth(data, seed=self.seed, stamp_ns=stamp_ns,
                    noise_std_m=self.noise, hole_fraction=self.holes), encoding="32FC1")
                changed.header = message.header
                message = changed
            self.enqueue(self.depth, message)

        def flush(self):
            now = self.get_clock().now().nanoseconds
            while self.pending and self.pending[0][0] <= now:
                _, publisher, message = self.pending.popleft()
                publisher.publish(message)

    with shutdown_requests() as requested:
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        node = None
        executor = None
        try:
            node = FaultBridge()
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
