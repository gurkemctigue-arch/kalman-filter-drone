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
        node._native_started_source_s, node._native_started_wall_s = 37., 95.
        node._native_last_source_s = 37.
        node._native_finished_source_s = node._native_finished_wall_s = None
        node._native_readiness_issues = lambda **kwargs: []
        node._phase_pub = SimpleNamespace(publish=lambda message: setattr(node, "last_phase", message.data))
        node._takeoff_started = 95.
        node._last_request = 0.
        node._attempts = 0
        node._ever_armed = False
        node._odom.twist = SimpleNamespace(twist=SimpleNamespace(linear=SimpleNamespace(x=0., y=0., z=0.)))
        node._status.nav_state = STATUS.NAVIGATION_STATE_AUTO_LOITER
        values = {"odometry_timeout_s": .5, "status_timeout_s": 1., "command_timeout_s": .5,
                  "takeoff_position_tolerance_m": .18, "native_settle_speed_mps": .2,
                  "native_settle_s": 1., "takeoff_timeout_s": 40., "command_retry_s": 1.,
                  "native_takeoff_timeout_sim_s": 40., "native_wall_timeout_s": 180.,
                  "max_command_attempts": 15}
        node.get_parameter = lambda key: SimpleNamespace(value=values[key])
        node.requests = []
        node._request = lambda *args: node.requests.append(args)
        return node

    def tick(self, node, ros_s=42., wall_s=100.1):
        node.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(
            nanoseconds=round(ros_s*1e9), to_msg=lambda: SimpleNamespace(sec=int(ros_s), nanosec=0)))
        with patch.object(flight, "TrackingCommand", FakeCommand, create=True), \
                patch.object(flight, "VehicleStatus", STATUS, create=True), \
                patch.object(flight, "VehicleCommand", COMMAND, create=True), \
                patch.object(flight, "String", lambda: SimpleNamespace(data=""), create=True), \
                patch.object(flight.time, "monotonic", return_value=wall_s):
            node._tick()

    def test_no_visual_command_or_offboard_before_final_alignment(self):
        node = self.node()
        node._native_readiness_issues = lambda **kwargs: ["final_yaw_alignment_incomplete"]
        self.tick(node)
        self.assertEqual(node._phase, "NATIVE_TAKEOFF")
        self.assertFalse(node.requests)
        self.assertEqual(node.last_output.linear_mps.x, 0.)
        self.assertTrue(node.last_phase.endswith("; source_sim_s=42.000000000"))

    def test_native_status_uses_source_age_for_humble04_person_failure_case(self):
        node = self.node()
        old_parameter = node.get_parameter
        node.get_parameter = lambda name: SimpleNamespace(value=10.) if name == "status_timeout_s" else old_parameter(name)
        node._status_timestamp_mode = "source_sim"
        node._status_clock = flight.OdometrySourceClock("source_sim", use_sim_time=True,
                                                     max_age_s=1., max_future_s=.05)
        node._status_last_ros_ns = None
        node._status_ros_regressed = False
        node._status_last_rejection = "none"
        node._native_started_source_s = node._native_last_source_s = 5.052
        node._native_started_wall_s = 97.580040458
        node.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=5_652_000_000))
        message = SimpleNamespace(timestamp=5_152_000, arming_state=2,
                                  nav_state=STATUS.NAVIGATION_STATE_AUTO_TAKEOFF,
                                  failsafe=False, pre_flight_checks_pass=True)
        with patch.object(flight.time, "monotonic", return_value=98.09):
            node._on_status(message)
        self.tick(node, ros_s=5.652, wall_s=100.1)
        self.assertEqual(node._phase, "NATIVE_TAKEOFF")
        self.assertAlmostEqual(100.1-node._status_received, 2.010)
        self.assertIn("native_elapsed_source_s=0.600000000", node.last_phase)
        self.assertFalse(node.requests)

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

    def test_slow_sim_native_flow_uses_source_budget_and_preserves_wall_cap(self):
        node=self.node();node._native_readiness_issues=lambda **kwargs:["still_aligning"]
        # 60 wall seconds may be only 12 seconds of actual PX4/source time.
        node._odom_received=node._status_received=155.
        self.tick(node,49.,155.)
        self.assertEqual(node._phase,"NATIVE_TAKEOFF")
        self.assertIn("native_elapsed_source_s=12.000000000",node.last_phase)
        self.assertIn("native_elapsed_wall_s=60.000000000",node.last_phase)
        node._odom_received=node._status_received=156.
        self.tick(node,77.000001,156.)
        self.assertEqual(node._phase,"ABORTED")
        self.assertIn("native_source_budget_exhausted",node._reason)
        self.assertFalse(node.last_output.valid)

    def test_wall_watchdog_runs_without_a_ros_tick_or_advancing_clock(self):
        node=self.node();node._native_readiness_issues=lambda **kwargs:["still_aligning"]
        # Do not call _tick: /clock is frozen at 42 while steady time advances.
        with patch.object(flight,"TrackingCommand",FakeCommand,create=True), \
                patch.object(flight,"String",lambda:SimpleNamespace(data=""),create=True), \
                patch.object(flight.time,"monotonic",return_value=275.000001):
            node._native_wall_watchdog()
        self.assertEqual(node._phase,"ABORTED")
        self.assertIn("native_wall_budget_exhausted",node._reason)
        self.assertIn("native_elapsed_wall_s=180.000001000",node.last_phase)
        self.assertFalse(node.last_output.valid)

    def test_source_regression_does_not_restart_or_extend_native_budget(self):
        node=self.node();node._native_last_source_s=43.
        self.tick(node,42.)
        self.assertEqual(node._phase,"ABORTED")
        self.assertIn("native_source_clock_regressed",node._reason)

    def test_budget_origins_are_taken_together_on_armed_native_entry(self):
        node=self.node("REQUEST_NATIVE_TAKEOFF")
        node._status.nav_state=STATUS.NAVIGATION_STATE_AUTO_TAKEOFF
        self.tick(node,42.,100.1)
        self.assertEqual(node._native_started_source_s,42.)
        self.assertEqual(node._native_started_wall_s,100.1)
        self.assertEqual(node._phase,"NATIVE_TAKEOFF")

    def test_completed_native_budget_stays_frozen_during_offboard_handoff(self):
        node=self.node();self.tick(node,42.);self.tick(node,43.1)
        self.assertEqual(node._phase,"REQUEST_OFFBOARD")
        elapsed=node._native_finished_source_s-node._native_started_source_s
        self.tick(node,44.)
        self.assertIn(f"native_elapsed_source_s={elapsed:.9f}",node.last_phase)


if __name__ == "__main__":
    unittest.main()
