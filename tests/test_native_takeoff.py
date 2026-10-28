"""Native takeoff owns startup resets; Offboard starts after final alignment."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_flight_supervisor as legacy_tests

FakeCommand, flight = legacy_tests.FakeCommand, legacy_tests.flight


STATUS = SimpleNamespace(ARMING_STATE_ARMED=2, NAVIGATION_STATE_OFFBOARD=14,
                         NAVIGATION_STATE_AUTO_TAKEOFF=17, NAVIGATION_STATE_AUTO_LOITER=4)
COMMAND = SimpleNamespace(VEHICLE_CMD_NAV_TAKEOFF=22, VEHICLE_CMD_COMPONENT_ARM_DISARM=400,
                          VEHICLE_CMD_DO_SET_MODE=176)


class NativeTakeoffTests(unittest.TestCase):
    def node(self, phase="NATIVE_TAKEOFF"):
        node = legacy_tests.FlightHandoffTests().supervisor(phase)
        node._native_takeoff = True
        node._native_settle_started_s = None
        node._native_readiness_issues = lambda **kwargs: []
        node._takeoff_started = 95.
        node._last_request = 0.
        node._attempts = 0
        node._ever_armed = False
        node._odom.twist = SimpleNamespace(twist=SimpleNamespace(linear=SimpleNamespace(x=0., y=0., z=0.)))
        node._status.nav_state = STATUS.NAVIGATION_STATE_AUTO_LOITER
        values = {"odometry_timeout_s": .5, "status_timeout_s": 1., "command_timeout_s": .5,
                  "takeoff_position_tolerance_m": .18, "native_settle_speed_mps": .2,
                  "native_settle_s": 1., "takeoff_timeout_s": 40., "command_retry_s": 1.,
                  "max_command_attempts": 15}
        node.get_parameter = lambda key: SimpleNamespace(value=values[key])
        node.requests = []
        node._request = lambda *args: node.requests.append(args)
        return node

    def tick(self, node, ros_s=42.):
        node.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(
            nanoseconds=round(ros_s*1e9), to_msg=lambda: SimpleNamespace(sec=int(ros_s), nanosec=0)))
        with patch.object(flight, "TrackingCommand", FakeCommand, create=True), \
                patch.object(flight, "VehicleStatus", STATUS, create=True), \
                patch.object(flight, "VehicleCommand", COMMAND, create=True), \
                patch.object(flight, "String", lambda: SimpleNamespace(data=""), create=True), \
                patch.object(flight.time, "monotonic", return_value=100.1):
            node._tick()

    def test_no_visual_command_or_offboard_before_final_alignment(self):
        node = self.node()
        node._native_readiness_issues = lambda **kwargs: ["final_yaw_alignment_incomplete"]
        self.tick(node)
        self.assertEqual(node._phase, "NATIVE_TAKEOFF")
        self.assertFalse(node.requests)
        self.assertEqual(node.last_output.linear_mps.x, 0.)

    def test_alignment_loiter_and_continuous_settle_precede_offboard_request(self):
        node = self.node()
        self.tick(node, 42.)
        self.assertEqual(node._phase, "NATIVE_TAKEOFF")
        node._native_readiness_issues = lambda **kwargs: ["local_position_stale"]
        self.tick(node, 42.5)
        self.assertIsNone(node._native_settle_started_s)
        node._native_readiness_issues = lambda **kwargs: []
        self.tick(node, 43.)
        self.tick(node, 44.1)
        self.assertEqual(node._phase, "REQUEST_OFFBOARD")
        self.assertEqual(node.last_output.linear_mps.x, 0.)

    def test_native_takeoff_accepted_mode_only_requests_arm(self):
        node = self.node("REQUEST_NATIVE_TAKEOFF")
        node._status.nav_state = STATUS.NAVIGATION_STATE_AUTO_TAKEOFF
        node._status.arming_state = 1
        self.tick(node)
        self.assertEqual(node.requests, [(COMMAND.VEHICLE_CMD_COMPONENT_ARM_DISARM, 1.)])

    def test_armed_native_takeoff_never_reissues_relative_takeoff_command(self):
        node = self.node("REQUEST_NATIVE_TAKEOFF")
        node._status.nav_state = STATUS.NAVIGATION_STATE_AUTO_TAKEOFF
        self.tick(node)
        self.assertEqual(node._phase, "NATIVE_TAKEOFF")
        self.assertFalse(node.requests)

    def test_native_readiness_temporarily_stale_defers_request(self):
        node = self.node("REQUEST_NATIVE_TAKEOFF")
        node._status.arming_state = 1
        node._native_readiness_issues = lambda **kwargs: ["estimator_flags_stale"]
        self.tick(node)
        self.assertEqual(node._phase, "REQUEST_NATIVE_TAKEOFF")
        self.assertFalse(node.requests)

    def test_armed_offboard_after_native_handoff_enters_hold(self):
        node = self.node("REQUEST_OFFBOARD")
        node._status.nav_state = STATUS.NAVIGATION_STATE_OFFBOARD
        self.tick(node)
        self.assertEqual(node._phase, "HOLD")
        self.assertEqual(node.last_output.linear_mps.x, 0.)

    def test_offboard_handoff_fails_closed_if_final_readiness_is_lost(self):
        node = self.node("REQUEST_OFFBOARD")
        node._native_readiness_issues = lambda **kwargs: ["heading_not_good_for_control"]
        self.tick(node)
        self.assertEqual(node._phase, "ABORTED")
        self.assertFalse(node.requests)
        self.assertFalse(node.last_output.valid)

    def test_takeoff_coordinates_and_altitude_are_nan_not_zero(self):
        node = self.node()
        node._vehicle_command_pub = SimpleNamespace(publish=lambda message: setattr(node, "sent", message))
        with patch.object(flight, "VehicleCommand", type("Request", (), {"VEHICLE_CMD_NAV_TAKEOFF":22}), create=True):
            flight.FlightSupervisor._request(node, 22, 0.)
        import math
        self.assertTrue(all(math.isnan(getattr(node.sent, "param"+str(index))) for index in range(4, 8)))
        self.assertTrue(node.sent.from_external)


if __name__ == "__main__":
    unittest.main()
