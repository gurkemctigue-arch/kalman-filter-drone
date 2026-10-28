"""Pure PX4 frame-boundary tests that do not require ROS 2 or px4_msgs."""

from __future__ import annotations

from types import SimpleNamespace
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_SOURCE = ROOT / "ros2_ws" / "src" / "uav_tracking_px4_adapter"
if str(ADAPTER_SOURCE) not in sys.path:
    sys.path.insert(0, str(ADAPTER_SOURCE))

from uav_tracking_px4_adapter import adapter_node  # noqa: E402


class Px4FrameConversionTests(unittest.TestCase):
    def test_inactive_setpoint_fields_are_nan_in_follow_and_hold(self) -> None:
        constants = SimpleNamespace(MODE_POSITION=1, MODE_VELOCITY=2, MODE_HOLD=3, MODE_FAILSAFE=4)
        for mode, allowed, position_active in [(1, True, True), (2, True, False), (1, False, False)]:
            with self.subTest(mode=mode, allowed=allowed):
                heartbeats, setpoints = [], []
                command = SimpleNamespace(
                    valid=allowed, mode=mode,
                    linear_mps=SimpleNamespace(x=1.0, y=2.0, z=3.0),
                    position_m=SimpleNamespace(x=4.0, y=5.0, z=6.0),
                    yaw_rad=0.0, yaw_rate_radps=0.0,
                )
                node = SimpleNamespace(
                    get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=1_000_000_000)),
                    _last_command=command, _last_ready_state=True,
                    _command_is_fresh=lambda _: True, _vehicle_ready=lambda: True,
                    _heartbeat_pub=SimpleNamespace(publish=heartbeats.append),
                    _setpoint_pub=SimpleNamespace(publish=setpoints.append),
                )
                with patch.object(adapter_node, "TrackingCommand", constants, create=True), \
                     patch.object(adapter_node, "TrajectorySetpoint", SimpleNamespace, create=True), \
                     patch.object(adapter_node, "OffboardControlMode", SimpleNamespace, create=True):
                    adapter_node.Px4AdapterNode._publish(node)
                sp = setpoints[0]
                self.assertEqual(heartbeats[0].position, position_active)
                self.assertEqual(heartbeats[0].velocity, not position_active)
                self.assertTrue(all(math.isnan(v) for v in sp.acceleration + sp.jerk))
                if position_active:
                    self.assertEqual(sp.position, [5.0, 4.0, -6.0])
                    self.assertTrue(all(math.isnan(v) for v in sp.velocity))
                else:
                    self.assertTrue(all(math.isnan(v) for v in sp.position))
                    self.assertEqual(sp.velocity, [2.0, 1.0, -3.0] if allowed else [0.0, 0.0, 0.0])
                if not allowed:
                    self.assertTrue(math.isnan(sp.yaw))

    def test_vector_and_yaw_conversions(self) -> None:
        self.assertEqual(adapter_node.enu_to_ned([1.0, 2.0, 3.0]), [2.0, 1.0, -3.0])
        self.assertEqual(adapter_node.ned_to_enu([2.0, 1.0, -3.0]), [1.0, 2.0, 3.0])
        self.assertAlmostEqual(adapter_node.enu_yaw_to_ned(0.0), 1.5707963267948966)
        self.assertAlmostEqual(adapter_node.enu_yaw_rate_to_ned(0.4), -0.4)

    def test_ned_odometry_is_published_in_enu_and_flu(self) -> None:
        class VehicleOdometryConstants:
            POSE_FRAME_NED = 1
            VELOCITY_FRAME_NED = 1
            VELOCITY_FRAME_FRD = 2

        original = adapter_node.VehicleOdometry
        adapter_node.VehicleOdometry = VehicleOdometryConstants
        try:
            message = SimpleNamespace(
                pose_frame=1,
                velocity_frame=1,
                position=[1.0, 2.0, -3.0],
                velocity=[4.0, 5.0, -6.0],
                # Identity body-FRD to world-NED attitude: vehicle forward is
                # North and the ROS output must be body-FLU in world-ENU.
                q=[1.0, 0.0, 0.0, 0.0],
            )
            position, velocity, quaternion = adapter_node.px4_odometry_to_enu(message)
        finally:
            adapter_node.VehicleOdometry = original
        self.assertEqual(position, [2.0, 1.0, 3.0])
        self.assertEqual(velocity, [4.0, -5.0, 6.0])
        self.assertAlmostEqual(quaternion[0], 0.0, places=9)
        self.assertAlmostEqual(quaternion[1], 0.0, places=9)
        self.assertAlmostEqual(abs(quaternion[2]), 2**-0.5, places=9)
        self.assertAlmostEqual(abs(quaternion[3]), 2**-0.5, places=9)

    def test_world_and_body_px4_velocity_frames_produce_same_flu_twist(self) -> None:
        # With a 90-degree PX4 body roll, FRD [1,2,3] is NED [1,-3,2].
        # Both inputs must produce the same body-FLU twist [1,-2,-3].
        for velocity_frame, velocity in ((1, [1.0, -3.0, 2.0]), (2, [1.0, 2.0, 3.0])):
            with self.subTest(velocity_frame=velocity_frame):
                message = SimpleNamespace(
                    pose_frame=1, velocity_frame=velocity_frame,
                    position=[0.0, 0.0, 0.0], velocity=velocity,
                    q=[2**-0.5, 2**-0.5, 0.0, 0.0],
                )
                _, flu_velocity, _ = adapter_node.px4_odometry_to_enu(message)
                for actual, expected in zip(flu_velocity, [1.0, -2.0, -3.0]):
                    self.assertAlmostEqual(actual, expected, places=9)

    def test_published_odometry_twist_is_in_declared_child_frame(self) -> None:
        published = []
        def odometry():
            return SimpleNamespace(
                header=SimpleNamespace(),
                pose=SimpleNamespace(pose=SimpleNamespace(
                    position=SimpleNamespace(), orientation=SimpleNamespace())),
                twist=SimpleNamespace(twist=SimpleNamespace(linear=SimpleNamespace())),
            )
        node = SimpleNamespace(
            get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(to_msg=lambda: "stamp")),
            _vehicle_odom_pub=SimpleNamespace(publish=published.append),
        )
        message = SimpleNamespace(
            pose_frame=1, velocity_frame=1, position=[1.0, 2.0, -3.0],
            velocity=[4.0, 5.0, -6.0], q=[1.0, 0.0, 0.0, 0.0],
        )
        with patch.object(adapter_node, "Odometry", odometry, create=True):
            adapter_node.Px4AdapterNode._on_vehicle_odometry(node, message)
        output = published[0]
        self.assertEqual(output.header.frame_id, "map")
        self.assertEqual(output.child_frame_id, "base_link")
        self.assertEqual(vars(output.twist.twist.linear), dict(x=4.0, y=-5.0, z=6.0))

    def test_motion_command_requires_valid_bounded_source_timestamp(self) -> None:
        now_ns = 10_000_000_000
        node = SimpleNamespace(
            get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=now_ns)),
            get_parameter=lambda _: SimpleNamespace(value=0.50),
        )
        for source_ns, expected in (
            (0, False), (10_000_000_000, True), (10_050_000_000, True),
            (10_050_000_001, False), (9_500_000_000, True), (9_499_999_999, False),
        ):
            with self.subTest(source_ns=source_ns):
                command = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(
                    sec=source_ns // 1_000_000_000, nanosec=source_ns % 1_000_000_000)))
                self.assertEqual(adapter_node.Px4AdapterNode._command_is_fresh(node, command), expected)
        self.assertFalse(adapter_node.Px4AdapterNode._command_is_fresh(node, None))
        now_ns = 0
        command = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=0, nanosec=1)))
        self.assertFalse(adapter_node.Px4AdapterNode._command_is_fresh(node, command))

    def test_unsupported_pose_frame_is_rejected(self) -> None:
        class VehicleOdometryConstants:
            POSE_FRAME_NED = 1
            VELOCITY_FRAME_NED = 1
            VELOCITY_FRAME_FRD = 2

        original = adapter_node.VehicleOdometry
        adapter_node.VehicleOdometry = VehicleOdometryConstants
        try:
            message = SimpleNamespace(
                pose_frame=2,
                velocity_frame=1,
                position=[0.0, 0.0, 0.0],
                velocity=[0.0, 0.0, 0.0],
                q=[1.0, 0.0, 0.0, 0.0],
            )
            with self.assertRaises(ValueError):
                adapter_node.px4_odometry_to_enu(message)
        finally:
            adapter_node.VehicleOdometry = original


if __name__ == "__main__":
    unittest.main()
