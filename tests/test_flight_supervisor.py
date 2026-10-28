"""Flight-adapter safeguards that can run without a ROS installation."""

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


flight = load_module("flight_supervisor_under_test", "ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter/flight_supervisor.py")
flight_tf = load_module("flight_tf_under_test", "ros2_ws/src/uav_tracking_bringup/uav_tracking_bringup/flight_tf_node.py")


class FakeCommand:
    MODE_VELOCITY = 1
    MODE_POSITION = 2

    def __init__(self):
        self.header = SimpleNamespace(stamp=SimpleNamespace(sec=42, nanosec=0), frame_id="map")
        self.linear_mps = SimpleNamespace(x=0.0, y=0.0, z=0.0)
        self.position_m = SimpleNamespace(x=0.0, y=0.0, z=0.0)
        self.yaw_rad = self.yaw_rate_radps = 0.0
        self.mode = self.MODE_VELOCITY
        self.valid = True


class FlightMathTests(unittest.TestCase):
    def test_takeoff_feedback_limits_horizontal_norm_and_vertical_speed(self):
        velocity = flight.bounded_takeoff_velocity((0.0, 0.0, 0.0), (10.0, 10.0, 3.0))
        self.assertAlmostEqual(math.hypot(*velocity[:2]), 0.8)
        self.assertAlmostEqual(velocity[2], 0.7)
        self.assertEqual(flight.bounded_takeoff_velocity((0.0, 0.0, 3.0), (0.0, 0.0, 3.0)), (0.0, 0.0, 0.0))
        with self.assertRaises(ValueError):
            flight.bounded_takeoff_velocity((0.0, 0.0, float("nan")), (0.0, 0.0, 3.0))

    def test_optical_axis_points_forward_and_down_in_body_flu(self):
        pitch = 0.35
        x, y, z, w = flight_tf.optical_mount_quaternion(pitch)
        self.assertAlmostEqual(x*x + y*y + z*z + w*w, 1.0)
        # Rotate the optical +Z line of sight into the FLU body frame.
        forward = (2*(x*z + y*w), 2*(y*z - x*w), 1 - 2*(x*x + y*y))
        self.assertAlmostEqual(forward[0], math.cos(pitch))
        self.assertAlmostEqual(forward[1], 0.0)
        self.assertAlmostEqual(forward[2], -math.sin(pitch))


class FlightHandoffTests(unittest.TestCase):
    def supervisor(self, phase="HOLD"):
        node = flight.FlightSupervisor.__new__(flight.FlightSupervisor)
        node._phase, node._reason = phase, "test"
        node._yaw = 0.0
        node._goal = (0.0, 0.0, 3.0)
        node._odom = SimpleNamespace(pose=SimpleNamespace(pose=SimpleNamespace(position=SimpleNamespace(x=0.0, y=0.0, z=3.0), orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0))))
        node._status = SimpleNamespace(arming_state=2, nav_state=14, failsafe=False, pre_flight_checks_pass=True)
        node._odom_received = node._status_received = node._command_received = 100.0
        node._controller_command = FakeCommand()
        node._controller_command.linear_mps.x = 0.6
        node._flight_pub = SimpleNamespace(publish=lambda msg: setattr(node, "last_output", msg))
        node._phase_pub = SimpleNamespace(publish=lambda msg: None)
        params = {"odometry_timeout_s": 0.5, "status_timeout_s": 1.0, "command_timeout_s": 0.5}
        node.get_parameter = lambda name: SimpleNamespace(value=params[name])
        node.get_logger = lambda: SimpleNamespace(info=lambda message: None)
        node.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=42_000_000_000, to_msg=lambda: SimpleNamespace(sec=42, nanosec=0)))
        return node

    def tick(self, node):
        with patch.object(flight, "TrackingCommand", FakeCommand, create=True), patch.object(flight, "VehicleStatus", SimpleNamespace(ARMING_STATE_ARMED=2, NAVIGATION_STATE_OFFBOARD=14), create=True), patch.object(flight, "String", lambda: SimpleNamespace(data=""), create=True), patch.object(flight.time, "monotonic", return_value=100.1):
            node._tick()

    def test_fresh_command_forwarded_only_after_takeoff_phase(self):
        node = self.supervisor()
        self.tick(node)
        self.assertEqual(node._phase, "FOLLOW")
        self.assertAlmostEqual(node.last_output.linear_mps.x, 0.6)

    def test_stale_visual_command_becomes_zero_velocity_hover(self):
        node = self.supervisor("FOLLOW")
        node._command_received = 99.0
        self.tick(node)
        self.assertEqual(node._phase, "HOLD")
        self.assertTrue(node.last_output.valid)
        self.assertEqual(node.last_output.linear_mps.x, 0.0)

    def test_offboard_exit_latches_abort_and_does_not_forward(self):
        node = self.supervisor("FOLLOW")
        node._status.nav_state = 4
        self.tick(node)
        self.assertEqual(node._phase, "ABORTED")
        self.assertIn("flight guard: offboard_exited", node._reason)
        self.assertIn("nav_state=4", node._reason)
        self.assertIn("odom_age_wall_s=0.100", node._reason)
        self.assertFalse(node.last_output.valid)
        self.assertEqual(node.last_output.linear_mps.x, 0.0)

    def test_abort_distinguishes_stale_streams_and_latches_source_stamps(self):
        node = self.supervisor("FOLLOW")
        node._odom.header = SimpleNamespace(stamp=SimpleNamespace(sec=41, nanosec=500))
        node._status.timestamp = 41_500_000
        node._odom_received = 99.4
        node._status_received = 99.0
        self.tick(node)
        self.assertEqual(node._phase, "ABORTED")
        self.assertIn("flight guard: odometry_stale, status_stale", node._reason)
        self.assertIn("odom_age_wall_s=0.700", node._reason)
        self.assertIn("status_age_wall_s=1.100", node._reason)
        self.assertIn("odom_stamp_ns=41000000500", node._reason)
        self.assertIn("status_px4_stamp_us=41500000", node._reason)
        self.assertIn("odom_received_monotonic_s=99.400000", node._reason)
        self.assertIn("arming_state=2, nav_state=14, failsafe=False", node._reason)
        reason = node._reason
        node._odom_received = node._status_received = 100.0
        self.tick(node)
        self.assertEqual(node._reason, reason)
        self.assertFalse(node.last_output.valid)

    def test_slow_sim_status_cycle_survives_configured_wall_budget_but_missing_stream_aborts(self):
        node = self.supervisor("FOLLOW")
        params = {"odometry_timeout_s": .5, "status_timeout_s": 2., "command_timeout_s": .5}
        node.get_parameter = lambda name: SimpleNamespace(value=params[name])
        # At requested RTF .5, a normal 500 ms PX4 status period is 1 wall s.
        node._status_received = 99.0
        self.tick(node)
        self.assertEqual(node._phase, "FOLLOW")
        self.assertAlmostEqual(node.last_output.linear_mps.x, .6)
        node._status_received = 98.0
        self.tick(node)
        self.assertEqual(node._phase, "ABORTED")
        self.assertIn("status_stale", node._reason)
        self.assertFalse(node.last_output.valid)

    def test_default_real_wall_budget_still_aborts_after_one_second(self):
        node = self.supervisor("FOLLOW")
        node._status_received = 99.
        self.tick(node)
        self.assertEqual(node._phase, "ABORTED")
        self.assertIn("status_limit_s=1.000", node._reason)


if __name__ == "__main__":
    unittest.main()
