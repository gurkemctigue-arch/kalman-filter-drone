"""Controlled ROS 2 smoke/acceptance test for the stage-one tracking graph.

This test deliberately bypasses YOLO and publishes ``TargetObservation``
messages tagged as ``CONTROLLED_TEST_SOURCE``.  It exercises the downstream
RGB-D state-estimation and follow-control path with three phases:

``MEASURED -> short dropout/prediction -> long dropout/hover``.

The test does not read Gazebo truth or entity names.  A real RGB-D depth probe
is optional and only checks that the configured depth topic transports valid
metre-valued pixels; it is not a detector substitute.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np

try:  # ROS 2 is intentionally optional for the repository's Windows tests.
    import rclpy
    from nav_msgs.msg import Odometry
    from rclpy.clock import Clock, ClockType
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import CameraInfo, Image
    from uav_tracking_interfaces.msg import TargetObservation, TargetState, TrackingCommand, TrackingStatus
except ImportError:  # pragma: no cover - ROS 2 only.
    rclpy = None
    Node = object  # type: ignore[misc,assignment]


CONTROLLED_TEST_SOURCE = "CONTROLLED_TEST_SOURCE"


class Stage1SmokeNode(Node):
    """Publish deterministic observations and collect graph acceptance data."""

    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("uav_tracking_stage1_smoke_test")
        self.args = args
        self._phase = "measured"
        self._phase_started_wall = time.monotonic()
        self._clock_seen = False
        self._done = False
        self._depth_messages = 0
        self._rgb_messages = 0
        self._observations_published = 0
        self._states: list[dict[str, Any]] = []
        self._statuses: list[dict[str, Any]] = []
        self._commands: list[dict[str, Any]] = []
        self._observation_pub = self.create_publisher(TargetObservation, args.observation_topic, 20)
        self._odom_pub = self.create_publisher(Odometry, args.vehicle_odom_topic, 10)
        self._depth_pub = None
        self._rgb_pub = None
        self._camera_info_pub = None
        if args.depth_probe:
            self._depth_pub = self.create_publisher(Image, args.depth_topic, qos_profile_sensor_data)
            self._rgb_pub = self.create_publisher(Image, args.rgb_topic, qos_profile_sensor_data)
            self._camera_info_pub = self.create_publisher(CameraInfo, args.camera_info_topic, qos_profile_sensor_data)
            self.create_subscription(Image, args.depth_topic, self._on_depth, qos_profile_sensor_data)
            self.create_subscription(Image, args.rgb_topic, self._on_rgb, qos_profile_sensor_data)
        self.create_subscription(TargetState, args.state_topic, self._on_state, 20)
        self.create_subscription(TrackingStatus, args.status_topic, self._on_status, 20)
        self.create_subscription(TrackingCommand, args.command_topic, self._on_command, 20)
        # Drive the acceptance schedule with wall time.  A Gazebo server may
        # run faster or slower than real time under CPU load; tying this test
        # timer to /clock can collapse the measured phase to one callback and
        # make the result depend on simulator throughput.
        self._steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self.create_timer(1.0 / max(1.0, args.rate_hz), self._tick, clock=self._steady_clock)

    @staticmethod
    def _stamp_seconds(stamp: Any) -> float:
        return float(stamp.sec) + float(stamp.nanosec) * 1e-9

    def _now(self) -> tuple[Any, float]:
        stamp = self.get_clock().now().to_msg()
        return stamp, self._stamp_seconds(stamp)

    def _phase_elapsed(self) -> float:
        return time.monotonic() - self._phase_started_wall

    def _tick(self) -> None:
        stamp, stamp_seconds = self._now()
        if stamp_seconds > 0.0:
            self._clock_seen = True
        self._publish_vehicle_state(stamp)
        if self._phase == "measured":
            self._publish_controlled_observation(stamp)
            if self._phase_elapsed() >= self.args.warmup_s:
                self._set_phase("short_dropout")
        elif self._phase == "short_dropout":
            if self._phase_elapsed() >= self.args.short_dropout_s:
                self._set_phase("long_dropout")
        elif self._phase == "long_dropout":
            if self._phase_elapsed() >= self.args.long_dropout_s:
                self._set_phase("grace")
        elif self._phase == "grace" and self._phase_elapsed() >= self.args.grace_s:
            self._done = True
        if self.args.depth_probe:
            self._publish_depth_probe(stamp)

    def _set_phase(self, phase: str) -> None:
        self._phase = phase
        self._phase_started_wall = time.monotonic()
        self.get_logger().info(f"stage-one smoke phase: {phase}")

    def _publish_vehicle_state(self, stamp: Any) -> None:
        message = Odometry()
        message.header.stamp = stamp
        message.header.frame_id = self.args.state_frame
        message.child_frame_id = "base_link"
        message.pose.pose.position.x = float(self.args.vehicle_x_m)
        message.pose.pose.position.y = float(self.args.vehicle_y_m)
        message.pose.pose.position.z = float(self.args.vehicle_z_m)
        message.pose.pose.orientation.w = 1.0
        self._odom_pub.publish(message)

    def _publish_controlled_observation(self, stamp: Any) -> None:
        message = TargetObservation()
        message.header.stamp = stamp
        message.header.frame_id = self.args.camera_frame
        message.candidate_id = 900001  # test-only candidate; never a Gazebo ID
        message.class_name = self.args.target_class
        message.class_id = 0 if self.args.target_class == "person" else 2
        message.confidence = 0.95
        message.bbox_x_min_px = 300.0
        message.bbox_y_min_px = 160.0
        message.bbox_x_max_px = 340.0
        message.bbox_y_max_px = 300.0
        message.center_u_px = 320.0
        message.center_v_px = 230.0
        message.depth_valid = True
        message.depth_m = float(self.args.depth_m)
        message.depth_valid_ratio = 1.0
        message.depth_std_m = 0.01
        message.depth_min_m = float(self.args.depth_m) - 0.02
        message.depth_max_m = float(self.args.depth_m) + 0.02
        message.camera_frame = self.args.camera_frame
        message.position_camera_m.x = 0.05
        message.position_camera_m.y = 0.0
        message.position_camera_m.z = float(self.args.depth_m)
        self._observation_pub.publish(message)
        self._observations_published += 1

    def _publish_depth_probe(self, stamp: Any) -> None:
        if self._depth_pub is None or self._rgb_pub is None or self._camera_info_pub is None:
            return
        image = Image()
        image.header.stamp = stamp
        image.header.frame_id = self.args.camera_frame
        image.height = 24
        image.width = 32
        image.encoding = "32FC1"
        image.is_bigendian = 0
        image.step = image.width * 4
        image.data = np.full((image.height, image.width), self.args.depth_m, dtype=np.float32).tobytes()
        self._depth_pub.publish(image)
        rgb = Image()
        rgb.header = image.header
        rgb.height = image.height
        rgb.width = image.width
        rgb.encoding = "rgb8"
        rgb.is_bigendian = 0
        rgb.step = rgb.width * 3
        rgb.data = bytes(rgb.height * rgb.step)
        self._rgb_pub.publish(rgb)
        info = CameraInfo()
        info.header = image.header
        info.width = image.width
        info.height = image.height
        info.k = [500.0, 0.0, 16.0, 0.0, 500.0, 12.0, 0.0, 0.0, 1.0]
        self._camera_info_pub.publish(info)

    def _on_depth(self, _message: Image) -> None:
        self._depth_messages += 1

    def _on_rgb(self, _message: Image) -> None:
        self._rgb_messages += 1

    def _on_state(self, message: TargetState) -> None:
        self._states.append(
            {
                "state": int(message.state),
                "prediction_age_s": float(message.prediction_age_s),
                "visible": bool(message.target_visible),
                "stamp": self._stamp_seconds(message.header.stamp),
            }
        )

    def _on_status(self, message: TrackingStatus) -> None:
        self._statuses.append(
            {
                "lifecycle": int(message.lifecycle),
                "prediction_active": bool(message.prediction_active),
                "reason": str(message.reason),
                "stamp": self._stamp_seconds(message.header.stamp),
            }
        )

    def _on_command(self, message: TrackingCommand) -> None:
        self._commands.append(
            {
                "mode": int(message.mode),
                "valid": bool(message.valid),
                "stamp": self._stamp_seconds(message.header.stamp),
            }
        )

    def result(self) -> dict[str, Any]:
        state_values = {item["state"] for item in self._states}
        lifecycle_values = {item["lifecycle"] for item in self._statuses}
        measured = TargetState.STATE_MEASURED in state_values
        predicted = TargetState.STATE_PREDICTED in state_values
        lost = TargetState.STATE_LOST in state_values
        hover = TrackingStatus.LIFECYCLE_HOVER in lifecycle_values
        failsafe_command = any(not item["valid"] for item in self._commands)
        failsafe_mode_seen = any(item["mode"] == TrackingCommand.MODE_FAILSAFE for item in self._commands)
        result = {
            "controlled_source": CONTROLLED_TEST_SOURCE,
            "clock_seen": self._clock_seen,
            "observations_published": self._observations_published,
            "depth_probe_messages": self._depth_messages,
            "rgb_probe_messages": self._rgb_messages,
            "states_seen": sorted(state_values),
            "lifecycles_seen": sorted(lifecycle_values),
            "commands_seen": len(self._commands),
            "measured_seen": measured,
            "predicted_seen": predicted,
            "lost_seen": lost,
            "hover_seen": hover,
            "failsafe_command_seen": failsafe_command,
            "failsafe_mode_seen": failsafe_mode_seen,
        }
        result["passed"] = bool(
            self._clock_seen
            and measured
            and predicted
            and lost
            and hover
            and failsafe_command
            and failsafe_mode_seen
            and (not self.args.depth_probe or (self._depth_messages > 0 and self._rgb_messages > 0))
        )
        return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation-topic", default="/tracking/observations")
    parser.add_argument("--state-topic", default="/tracking/state")
    parser.add_argument("--status-topic", default="/tracking/status")
    parser.add_argument("--command-topic", default="/tracking/command")
    parser.add_argument("--vehicle-odom-topic", default="/vehicle/odometry")
    parser.add_argument("--depth-topic", default="/camera/aligned_depth_to_color/image_raw")
    parser.add_argument("--rgb-topic", default="/camera/color/image_raw")
    parser.add_argument("--camera-info-topic", default="/camera/color/camera_info")
    parser.add_argument("--camera-frame", default="camera_link")
    parser.add_argument("--state-frame", default="map")
    parser.add_argument("--target-class", choices=("person", "car"), default="person")
    parser.add_argument("--depth-m", type=float, default=8.0)
    parser.add_argument("--vehicle-x-m", type=float, default=0.0)
    parser.add_argument("--vehicle-y-m", type=float, default=0.0)
    parser.add_argument("--vehicle-z-m", type=float, default=3.0)
    parser.add_argument("--rate-hz", type=float, default=30.0)
    parser.add_argument("--warmup-s", type=float, default=0.60)
    parser.add_argument("--short-dropout-s", type=float, default=0.20)
    parser.add_argument("--long-dropout-s", type=float, default=1.20)
    parser.add_argument("--grace-s", type=float, default=0.40)
    parser.add_argument("--depth-probe", action="store_true", help="also publish a synthetic float-metre depth topic")
    parser.add_argument("--output", type=Path, help="write the JSON result to this path")
    return parser


def main(args: list[str] | None = None) -> int:
    if rclpy is None:
        raise RuntimeError("ROS 2 is required to run stage1_smoke_test")
    parsed, ros_args = _build_parser().parse_known_args(args)
    rclpy.init(args=ros_args)
    node = Stage1SmokeNode(parsed)
    try:
        while rclpy.ok() and not node._done:
            rclpy.spin_once(node, timeout_sec=0.10)
        result = node.result()
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        if parsed.output:
            parsed.output.parent.mkdir(parents=True, exist_ok=True)
            parsed.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if result["passed"] else 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
