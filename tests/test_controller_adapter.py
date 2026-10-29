"""ROS-free regression checks at the controller's message boundary."""

from __future__ import annotations

import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from uav_tracking.control import FollowConfig, FollowController

ROOT = Path(__file__).resolve().parents[1]
NODES_SOURCE = ROOT / "ros2_ws" / "src" / "uav_tracking_nodes"
if str(NODES_SOURCE) not in sys.path:
    sys.path.insert(0, str(NODES_SOURCE))

from uav_tracking_nodes import controller_node as controller  # noqa: E402


def stamp(seconds: float) -> SimpleNamespace:
    value = round(seconds * 1e9)
    return SimpleNamespace(sec=value // 1_000_000_000, nanosec=value % 1_000_000_000)


def vector(x=0.0, y=0.0, z=0.0) -> SimpleNamespace:
    return SimpleNamespace(x=x, y=y, z=z)


class FakeTargetState:
    STATE_MEASURED, STATE_PREDICTED = 1, 2
    STATE_AMBIGUOUS = 4


class FakeCommand:
    MODE_VELOCITY, MODE_POSITION, MODE_FAILSAFE = 1, 2, 3

    def __init__(self) -> None:
        self.header = SimpleNamespace()
        self.linear_mps, self.position_m = vector(), vector()


class FakeStatus:
    LIFECYCLE_PREDICT, LIFECYCLE_FOLLOW, LIFECYCLE_HOVER, LIFECYCLE_FAILSAFE = range(4)


class ControllerMessageBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.time = 10.0
        self.commands, self.statuses, self.inputs = [], [], []
        self.node = controller.ControllerNode.__new__(controller.ControllerNode)
        parameters = dict(control_rate_hz=20.0, desired_distance_m=5.0, desired_height_m=2.0)
        self.node.get_parameter = lambda key: SimpleNamespace(value=parameters[key])
        self.node.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(
            nanoseconds=round(self.time * 1e9), to_msg=lambda: stamp(self.time)))
        self.node._command_pub = SimpleNamespace(publish=self.commands.append)
        self.node._status_pub = SimpleNamespace(publish=self.statuses.append)
        self.node._target = SimpleNamespace(
            state=FakeTargetState.STATE_MEASURED, prediction_age_s=0.0,
            header=SimpleNamespace(stamp=stamp(10.0), frame_id="map"),
            position_m=vector(10.0), velocity_mps=vector(),
            covariance=np.eye(6).reshape(-1), track_id=7, target_visible=True,
        )
        self.node._vehicle = SimpleNamespace(
            header=SimpleNamespace(stamp=stamp(10.0), frame_id="map"), child_frame_id="base_link",
            pose=SimpleNamespace(pose=SimpleNamespace(
                position=vector(z=2.0), orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0))),
            twist=SimpleNamespace(twist=SimpleNamespace(linear=vector())),
        )
        portable = FollowController(config=FollowConfig(
            desired_distance=5.0, desired_height=2.0, target_timeout=0.75, vehicle_timeout=0.50))
        def update(target, vehicle, dt):
            self.inputs.append((target, vehicle))
            return portable.update(target, vehicle, dt=dt)
        self.node._controller = SimpleNamespace(update=update, reset=portable.reset)
        for name, value in (
            ("TargetState", FakeTargetState), ("TrackingCommand", FakeCommand), ("TrackingStatus", FakeStatus),
        ):
            patcher = patch.object(controller, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_zero_and_excessive_future_target_stamps_fail_safe(self) -> None:
        for timestamp in (0.0, 10.050000001, 100.0):
            with self.subTest(timestamp=timestamp):
                self.node._target.header.stamp = stamp(timestamp)
                self.node._step()
                self.assertFalse(self.commands[-1].valid)
                self.assertEqual(self.statuses[-1].reason, "invalid_target_timestamp")
        self.assertEqual(self.inputs, [])

    def test_zero_and_excessive_future_odometry_stamps_fail_safe(self) -> None:
        for timestamp in (0.0, 10.050000001, 100.0):
            with self.subTest(timestamp=timestamp):
                self.node._vehicle.header.stamp = stamp(timestamp)
                self.node._step()
                self.assertFalse(self.commands[-1].valid)
                self.assertEqual(self.statuses[-1].reason, "invalid_vehicle_timestamp")
        self.assertEqual(self.inputs, [])

    def test_fifty_millisecond_future_skew_is_tolerated_without_negative_age(self) -> None:
        self.node._target.header.stamp = stamp(10.05)
        self.node._vehicle.header.stamp = stamp(10.05)
        self.node._target.prediction_age_s = 0.2
        self.node._step()
        self.assertTrue(self.commands[-1].valid)
        target, vehicle = self.inputs[-1]
        self.assertEqual(target.age, 0.2)
        self.assertEqual(vehicle.age, 0.0)

    def test_prediction_and_transport_age_still_add_up_to_existing_timeout(self) -> None:
        self.node._target.header.stamp = stamp(9.6)
        self.node._target.prediction_age_s = 0.4
        self.node._step()
        self.assertFalse(self.commands[-1].valid)
        self.assertEqual(self.statuses[-1].reason, "stale_target")
        self.assertAlmostEqual(self.inputs[-1][0].age, 0.8)

    def test_existing_vehicle_age_limit_still_applies(self) -> None:
        self.node._vehicle.header.stamp = stamp(9.499999999)
        self.node._step()
        self.assertFalse(self.commands[-1].valid)
        self.assertEqual(self.statuses[-1].reason, "stale_vehicle")

    def test_body_twist_uses_full_attitude_to_restore_world_velocity(self) -> None:
        # This attitude cycles body axes: x -> North, y -> Up, z -> East.
        # The physical body-FLU velocity [1,-2,-3] is world ENU [-3,1,-2].
        self.node._vehicle.pose.pose.orientation = SimpleNamespace(x=0.5, y=0.5, z=0.5, w=0.5)
        self.node._vehicle.twist.twist.linear = vector(1.0, -2.0, -3.0)
        self.node._step()
        self.assertTrue(self.commands[-1].valid)
        np.testing.assert_allclose(self.inputs[-1][1].velocity, [-3.0, 1.0, -2.0], atol=1e-12)
        self.assertAlmostEqual(self.inputs[-1][1].yaw, math.pi / 2.0)

    def test_orientation_is_normalized_and_zero_quaternion_fails_safe(self) -> None:
        self.node._vehicle.pose.pose.orientation.w = 2.0
        self.node._vehicle.twist.twist.linear = vector(1.0, 2.0, 3.0)
        self.node._step()
        np.testing.assert_allclose(self.inputs[-1][1].velocity, [1.0, 2.0, 3.0])
        self.node._vehicle.pose.pose.orientation.w = 0.0
        self.node._step()
        self.assertFalse(self.commands[-1].valid)
        self.assertEqual(self.statuses[-1].reason, "invalid_vehicle_orientation")

    def test_clock_must_be_initialized(self) -> None:
        self.time = 0.0
        self.node._step()
        self.assertFalse(self.commands[-1].valid)
        self.assertEqual(self.statuses[-1].reason, "invalid_clock")

    def test_invalid_timestamp_discards_position_reference_before_recovery(self) -> None:
        self.node._controller = FollowController(config=FollowConfig(
            mode="position", slew_position=True, desired_distance=5.0,
            desired_height=2.0, max_acceleration=3.0, max_position_lead=2.0,
            target_timeout=0.75, vehicle_timeout=0.5))
        for _ in range(20):
            self.node._step()
        self.assertGreater(self.commands[-1].position_m.x, 0.1)
        self.node._target.header.stamp = stamp(0.0)
        self.node._step()
        self.assertFalse(self.commands[-1].valid)
        self.node._target.header.stamp = stamp(self.time)
        self.node._step()
        restarted = self.commands[-1]
        self.assertTrue(restarted.valid)
        self.assertEqual(restarted.mode, FakeCommand.MODE_POSITION)
        self.assertLessEqual(abs(restarted.position_m.x), 3.0 * 0.05 ** 2 + 1e-12)

    def test_explicit_target_ambiguity_produces_hover_and_zero_motion(self) -> None:
        self.node._target.state = FakeTargetState.STATE_AMBIGUOUS
        self.node._step()
        self.assertFalse(self.commands[-1].valid)
        self.assertEqual(self.commands[-1].mode, FakeCommand.MODE_FAILSAFE)
        self.assertEqual(vars(self.commands[-1].linear_mps), dict(x=0.0, y=0.0, z=0.0))
        self.assertEqual(self.statuses[-1].lifecycle, FakeStatus.LIFECYCLE_HOVER)
        self.assertEqual(self.statuses[-1].reason, "target_ambiguous")


if __name__ == "__main__":
    unittest.main()
