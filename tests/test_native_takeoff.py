"""Native takeoff and dual-source settle gates before Offboard handoff."""
import json
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_flight_supervisor as legacy_tests
from tests.test_native_startup_evaluator import evaluation as native_audit

FakeCommand, flight = legacy_tests.FakeCommand, legacy_tests.flight


STATUS = SimpleNamespace(ARMING_STATE_ARMED=2, NAVIGATION_STATE_OFFBOARD=14,
                         NAVIGATION_STATE_AUTO_TAKEOFF=17, NAVIGATION_STATE_AUTO_LOITER=4)
COMMAND = SimpleNamespace(VEHICLE_CMD_NAV_TAKEOFF=22, VEHICLE_CMD_COMPONENT_ARM_DISARM=400,
                          VEHICLE_CMD_DO_SET_MODE=176)


def stamp(source_s):
    sec, nsec = divmod(round(source_s * 1e9), 1_000_000_000)
    return SimpleNamespace(sec=sec, nanosec=nsec)


class NativeTakeoffTests(unittest.TestCase):
    def node(self, phase="NATIVE_TAKEOFF"):
        node = legacy_tests.FlightHandoffTests().supervisor(phase)
        node._native_takeoff = True
        node._native_settle_started_s = None
        node._native_started_source_s, node._native_started_wall_s = 37., 95.
        node._native_last_source_s = 37.
        node._native_finished_source_s = node._native_finished_wall_s = None
        node._native_readiness_issues = lambda **kwargs: []
        node._native_local = SimpleNamespace(x=0., y=0., z=-3., vx=0., vy=0., vz=0.,
                                             timestamp_sample=42_000_000, timestamp=42_000_000)
        node._odom.header = SimpleNamespace(stamp=stamp(42.))
        node._odom_received_source_s = None
        node._native_local_received_source_s = node._native_local_received_wall_s = None
        node._native_goal_anchor = node._native_settle_diagnostic = None
        node._phase_pub = SimpleNamespace(publish=lambda message: setattr(node, "last_phase", message.data))
        node._takeoff_started = 95.
        node._last_request = 0.
        node._attempts = 0
        node._ever_armed = False
        node._odom.twist = SimpleNamespace(twist=SimpleNamespace(linear=SimpleNamespace(x=0., y=0., z=0.)))
        node._status.nav_state = STATUS.NAVIGATION_STATE_AUTO_LOITER
        values = {"odometry_timeout_s": .5, "status_timeout_s": 1., "command_timeout_s": .5,
                  "takeoff_position_tolerance_m": .18, "native_settle_speed_mps": .2,
                  "native_settle_s": 1., "native_handoff_guard_s": .25,
                  "takeoff_timeout_s": 40., "command_retry_s": 1.,
                  "native_takeoff_timeout_sim_s": 40., "native_wall_timeout_s": 180.,
                  "takeoff_height_m": 3., "heartbeat_prestream_s": 1.2,
                  "max_command_attempts": 15}
        node._test_params = values
        node.get_parameter = lambda key: SimpleNamespace(value=values[key])
        node.requests = []
        node._request = lambda *args: node.requests.append(args)
        return node

    def publish_native_samples(self, node, source_s):
        """Explicitly deliver new fixture samples; stale cases skip this step."""
        node._odom.header.stamp = stamp(source_s)
        node._native_local.timestamp_sample = node._native_local.timestamp = round(source_s * 1e6)
        node._on_odom(node._odom)
        node._on_native_local(node._native_local)

    def tick(self, node, ros_s=42., wall_s=100.1, *, publish_samples=True):
        node.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(
            nanoseconds=round(ros_s*1e9), to_msg=lambda: stamp(ros_s)))
        with patch.object(flight, "TrackingCommand", FakeCommand, create=True), \
                patch.object(flight, "VehicleStatus", STATUS, create=True), \
                patch.object(flight, "VehicleCommand", COMMAND, create=True), \
                patch.object(flight, "String", lambda: SimpleNamespace(data=""), create=True), \
                patch.object(flight.time, "monotonic", return_value=wall_s):
            if publish_samples:
                self.publish_native_samples(node, ros_s)
            node._tick()

    def diagnostic(self, node):
        text = node.last_phase.split("native_diag=", 1)[1].rsplit("; source_sim_s=", 1)[0]
        return json.loads(text)

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
        self.tick(node, 44.25)
        self.assertEqual(node._phase, "REQUEST_OFFBOARD")
        self.assertEqual(node.last_output.linear_mps.x, 0.)

    def test_guard_requires_full_source_duration_and_reports_actual_timer(self):
        node = self.node()
        self.tick(node, 42.)
        observed = self.diagnostic(node)
        self.assertEqual(observed["settle_started_source_s"], 42.)
        self.assertEqual(observed["settle_timing_observed_source_s"], 42.)
        self.assertEqual(observed["settle_elapsed_source_s"], 0.)
        self.assertEqual(observed["settle_required_total_s"], 1.25)
        self.assertEqual(observed["native_handoff_guard_s"], .25)
        for source_s, elapsed in ((43., 1.), (43.249, 1.249)):
            self.tick(node, source_s)
            self.assertEqual(node._phase, "NATIVE_TAKEOFF")
            self.assertFalse(node.requests)
            self.assertAlmostEqual(self.diagnostic(node)["settle_elapsed_source_s"], elapsed)
        self.tick(node, 43.25)
        self.assertEqual(node._phase, "REQUEST_OFFBOARD")
        self.assertEqual(self.diagnostic(node)["settle_elapsed_source_s"], 1.25)
        self.assertFalse(node.requests)
        self.tick(node, 43.3)
        observed = self.diagnostic(node)
        self.assertAlmostEqual(observed["check_ros_s"], 43.3)
        self.assertEqual(observed["settle_timing_observed_source_s"], 43.25)
        self.assertEqual(observed["settle_elapsed_source_s"], 1.25)
        self.assertEqual(node.requests, [(COMMAND.VEHICLE_CMD_DO_SET_MODE, 1., 6.)])

    def test_guard_uses_source_time_during_slow_or_paused_simulation(self):
        node = self.node()
        self.tick(node, 42., 100.1)
        for source_s, wall_s in ((42., 130.), (43., 150.), (43.249, 150.1)):
            node._status_received = wall_s
            self.tick(node, source_s, wall_s)
            self.assertEqual(node._phase, "NATIVE_TAKEOFF")
            self.assertFalse(node.requests)
        node._status_received = 150.2
        self.tick(node, 43.25, 150.2)
        self.assertEqual(node._phase, "REQUEST_OFFBOARD")
        self.assertEqual(self.diagnostic(node)["settle_elapsed_source_s"], 1.25)

    def test_guard_does_not_require_an_additional_wall_duration(self):
        node = self.node()
        self.tick(node, 42., 100.1)
        self.tick(node, 43.25, 100.2)
        self.assertEqual(node._phase, "REQUEST_OFFBOARD")
        self.assertEqual(self.diagnostic(node)["settle_elapsed_source_s"], 1.25)

    def test_zero_guard_keeps_the_original_full_one_second_gate(self):
        node = self.node()
        node._test_params["native_handoff_guard_s"] = 0.
        self.tick(node, 42.)
        self.tick(node, 42.999)
        self.assertEqual(node._phase, "NATIVE_TAKEOFF")
        self.tick(node, 43.)
        self.assertEqual(node._phase, "REQUEST_OFFBOARD")
        self.assertEqual(self.diagnostic(node)["settle_required_total_s"], 1.)

    def test_invalid_guard_is_rejected_by_initialization_before_ros_entities(self):
        for invalid in (-.001, math.nan, math.inf, -math.inf, True, None, ".25"):
            with self.subTest(invalid=invalid):
                values = {}

                def declare(_node, name, default):
                    values[name] = invalid if name == "native_handoff_guard_s" else default

                with patch.object(flight, "super", return_value=SimpleNamespace(__init__=lambda *_args: None), create=True), \
                        patch.object(flight.FlightSupervisor, "declare_parameter", declare, create=True), \
                        patch.object(flight.FlightSupervisor, "get_parameter",
                                     lambda _node, name: SimpleNamespace(value=values[name]), create=True):
                    with self.assertRaisesRegex(ValueError, "native_handoff_guard_s"):
                        flight.FlightSupervisor()

    def test_guard_does_not_extend_the_original_source_or_wall_budgets(self):
        source_node = self.node()
        self.tick(source_node, 76.9)
        self.tick(source_node, 77.)
        self.assertEqual(source_node._phase, "NATIVE_TAKEOFF")
        self.assertEqual(source_node._test_params["native_takeoff_timeout_sim_s"], 40.)
        self.tick(source_node, 77.000001)
        self.assertEqual(source_node._phase, "ABORTED")
        self.assertIn("native_source_budget_exhausted", source_node._reason)
        self.assertFalse(source_node.requests)

        wall_node = self.node()
        wall_node._status_received = 274.8
        self.tick(wall_node, 42., 274.8)
        wall_node._status_received = 275.
        self.tick(wall_node, 42.1, 275.)
        self.assertEqual(wall_node._phase, "NATIVE_TAKEOFF")
        self.assertEqual(wall_node._test_params["native_wall_timeout_s"], 180.)
        wall_node._status_received = 275.000001
        self.tick(wall_node, 42.2, 275.000001)
        self.assertEqual(wall_node._phase, "ABORTED")
        self.assertIn("native_wall_budget_exhausted", wall_node._reason)
        self.assertFalse(wall_node.requests)

    def test_readiness_freshness_or_loiter_loss_restarts_the_guard_interval(self):
        for kind in ("local_readiness", "adapted_freshness", "loiter"):
            with self.subTest(kind=kind):
                node = self.node()
                self.tick(node, 42.)
                self.tick(node, 43.2)
                if kind == "local_readiness":
                    node._native_readiness_issues = lambda **kwargs: ["local_position_source_stale"]
                elif kind == "adapted_freshness":
                    node._odom.header.stamp = stamp(42.)
                else:
                    node._status.nav_state = STATUS.NAVIGATION_STATE_AUTO_TAKEOFF
                self.tick(node, 43.24, publish_samples=kind != "adapted_freshness")
                self.assertEqual(node._phase, "NATIVE_TAKEOFF")
                self.assertIsNone(node._native_settle_started_s)
                self.assertIsNone(self.diagnostic(node)["settle_elapsed_source_s"])
                node._native_readiness_issues = lambda **kwargs: []
                node._status.nav_state = STATUS.NAVIGATION_STATE_AUTO_LOITER
                self.tick(node, 43.25)
                self.tick(node, 44.499)
                self.assertEqual(node._phase, "NATIVE_TAKEOFF")
                self.tick(node, 44.5)
                self.assertEqual(node._phase, "REQUEST_OFFBOARD")

    def test_wall_watchdog_does_not_invent_new_settle_observations(self):
        node = self.node()
        self.tick(node, 42., 100.1)
        with patch.object(flight, "TrackingCommand", FakeCommand, create=True), \
                patch.object(flight, "String", lambda: SimpleNamespace(data=""), create=True), \
                patch.object(flight.time, "monotonic", return_value=275.000001):
            node._native_wall_watchdog()
        self.assertEqual(node._phase, "ABORTED")
        observed = self.diagnostic(node)
        self.assertEqual(observed["check_ros_s"], 42.)
        self.assertEqual(observed["settle_timing_observed_source_s"], 42.)
        self.assertEqual(observed["settle_elapsed_source_s"], 0.)
        self.assertFalse(node.requests)

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

    def test_confirmed_offboard_does_not_reapply_completed_native_physical_settle(self):
        node = self.node("REQUEST_OFFBOARD")
        node._status.nav_state = STATUS.NAVIGATION_STATE_OFFBOARD
        node._native_local.y = node._odom.pose.pose.position.x = .19
        node._native_local.vx = node._odom.twist.twist.linear.x = .21
        self.tick(node)
        self.assertEqual(node._phase, "HOLD")
        self.assertTrue(node.last_output.valid)
        self.assertEqual(node.last_output.linear_mps.x, 0.)
        self.assertFalse(node.requests)
        observed = node._native_settle_diagnostic
        self.assertFalse(observed["physical_settle_required"])
        self.assertTrue(observed["checks_ready"])
        for source in ("local", "adapted"):
            self.assertGreater(observed[source]["position_error_m"], .18)
            self.assertGreater(observed[source]["speed_mps"], .20)

    def test_confirmed_offboard_still_rejects_lost_final_ekf_readiness(self):
        node = self.node("REQUEST_OFFBOARD")
        node._status.nav_state = STATUS.NAVIGATION_STATE_OFFBOARD
        node._native_readiness_issues = lambda **kwargs: ["heading_not_good_for_control"]
        self.tick(node)
        self.assertEqual(node._phase, "ABORTED")
        self.assertFalse(node.requests)
        self.assertFalse(node.last_output.valid)
        self.assertIn("heading_not_good_for_control", node._native_settle_diagnostic["issues"])

    def test_confirmed_offboard_still_rejects_invalid_or_stale_adapted_state(self):
        for kind, issue in (("nonfinite", "native_adapted_physical_state_invalid"),
                            ("stale", "native_adapted_source_stale")):
            with self.subTest(kind=kind):
                node = self.node("REQUEST_OFFBOARD")
                node._status.nav_state = STATUS.NAVIGATION_STATE_OFFBOARD
                if kind == "nonfinite":
                    node._odom.twist.twist.linear.x = math.nan
                else:
                    node._odom.header.stamp = stamp(41.499999)
                self.tick(node, publish_samples=False)
                self.assertEqual(node._phase, "ABORTED")
                self.assertFalse(node.requests)
                self.assertFalse(node.last_output.valid)
                self.assertIn(issue, node._native_settle_diagnostic["issues"])

    def test_pending_mode_response_does_not_reapply_native_goal_before_retry(self):
        node = self.node("REQUEST_OFFBOARD")
        self.tick(node)
        node._native_local.y = node._odom.pose.pose.position.x = .19
        node._native_local.vx = node._odom.twist.twist.linear.x = .21
        self.tick(node, ros_s=42.1, wall_s=100.2)
        self.assertEqual(node._phase, "REQUEST_OFFBOARD")
        self.assertEqual(node.requests, [(COMMAND.VEHICLE_CMD_DO_SET_MODE, 1., 6.)])
        self.assertEqual(node._attempts, 1)
        self.assertTrue(node.last_output.valid)
        self.assertEqual(node.last_output.linear_mps.x, 0.)
        self.assertFalse(node._native_settle_diagnostic["physical_settle_required"])
        self.assertTrue(node._native_settle_diagnostic["checks_ready"])

    def test_retry_due_requires_original_dual_source_physical_settle_again(self):
        for source, issue in (("local", "native_local_position_not_settled"),
                              ("adapted", "native_adapted_speed_not_settled")):
            with self.subTest(source=source):
                node = self.node("REQUEST_OFFBOARD")
                self.tick(node)
                if source == "local":
                    node._native_local.y = .19
                else:
                    node._odom.twist.twist.linear.x = .2001
                node._status_received = 101.2
                self.tick(node, ros_s=43.1, wall_s=101.2)
                self.assertEqual(node._phase, "ABORTED")
                self.assertEqual(node.requests, [(COMMAND.VEHICLE_CMD_DO_SET_MODE, 1., 6.)])
                self.assertEqual(node._attempts, 1)
                self.assertFalse(node.last_output.valid)
                observed = node._native_settle_diagnostic
                self.assertTrue(observed["physical_settle_required"])
                self.assertIn(issue, observed["issues"])

    def test_native_mode_request_requires_armed_auto_loiter(self):
        for arming, mode in ((1, STATUS.NAVIGATION_STATE_AUTO_LOITER),
                             (STATUS.ARMING_STATE_ARMED, STATUS.NAVIGATION_STATE_AUTO_TAKEOFF)):
            with self.subTest(arming=arming, mode=mode):
                node = self.node("REQUEST_OFFBOARD")
                node._status.arming_state, node._status.nav_state = arming, mode
                self.tick(node)
                self.assertEqual(node._phase, "ABORTED")
                self.assertFalse(node.requests)
                self.assertFalse(node.last_output.valid)
                self.assertIn("requires armed AUTO_LOITER", node._reason)

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
        node=self.node();self.tick(node,42.);self.tick(node,43.25)
        self.assertEqual(node._phase,"REQUEST_OFFBOARD")
        elapsed=node._native_finished_source_s-node._native_started_source_s
        self.tick(node,44.)
        self.assertIn(f"native_elapsed_source_s={elapsed:.9f}",node.last_phase)

    def test_either_position_source_outside_limit_blocks_settle(self):
        for source in ("local", "adapted"):
            with self.subTest(source=source):
                node = self.node()
                if source == "local":
                    # Actual Humble18 boundary magnitude; this is a new fixture,
                    # not a reconstruction of that flight's callback cache.
                    node._native_local.y = .18053513528954684
                else:
                    node._odom.pose.pose.position.x = .19
                self.tick(node)
                self.assertEqual(node._phase, "NATIVE_TAKEOFF")
                self.assertIsNone(node._native_settle_started_s)
                self.assertFalse(node.requests)
                observed = self.diagnostic(node)
                self.assertIn("native_" + source + "_position_not_settled", observed["issues"])
                self.assertGreater(observed[source]["position_error_m"], .18)
                other = "adapted" if source == "local" else "local"
                self.assertEqual(observed[other]["position_error_m"], 0.)

    def test_nonzero_asymmetric_goal_uses_ned_to_enu_for_local_position(self):
        node = self.node()
        node._goal = (1.25, -2.5, 3.75)
        node._odom.pose.pose.position = SimpleNamespace(x=1.25, y=-2.5, z=3.75)
        node._native_local.x, node._native_local.y, node._native_local.z = -2.5, 1.25, -3.75
        self.tick(node, 42.)
        self.assertEqual(self.diagnostic(node)["local"]["position_enu_m"], [1.25, -2.5, 3.75])
        self.assertEqual(node._native_settle_started_s, 42.)
        self.tick(node, 43.25)
        self.assertEqual(node._phase, "REQUEST_OFFBOARD")
        self.assertFalse(node.requests, "phase transition itself must not send a mode command")

    def test_either_speed_source_over_original_limit_blocks_settle(self):
        for source in ("local", "adapted"):
            with self.subTest(source=source):
                node = self.node()
                if source == "local":
                    node._native_local.vx = .2001
                else:
                    node._odom.twist.twist.linear.x = .2001
                self.tick(node)
                self.assertEqual(node._phase, "NATIVE_TAKEOFF")
                self.assertIsNone(node._native_settle_started_s)
                self.assertIn("native_" + source + "_speed_not_settled", self.diagnostic(node)["issues"])

    def test_original_position_and_speed_limits_are_inclusive(self):
        node = self.node()
        node._native_local.y = node._odom.pose.pose.position.x = .18
        node._native_local.vx = node._odom.twist.twist.linear.x = .20
        self.tick(node, 42.)
        self.assertTrue(self.diagnostic(node)["checks_ready"])
        self.tick(node, 43.25)
        self.assertEqual(node._phase, "REQUEST_OFFBOARD")

    def test_either_source_failure_restarts_settle_and_independent_guard(self):
        for source in ("local", "adapted"):
            for kind in ("position", "speed"):
                with self.subTest(source=source, kind=kind):
                    self.check_guard_restart(source, kind)

    def check_guard_restart(self, source, kind):
        node = self.node()
        self.tick(node, 42.)
        self.tick(node, 43.2)
        self.assertEqual(node._native_settle_started_s, 42.)
        if kind == "position":
            sample = node._native_local if source == "local" else node._odom.pose.pose.position
            field, invalid = ("y" if source == "local" else "x"), .19
        else:
            sample = node._native_local if source == "local" else node._odom.twist.twist.linear
            field, invalid = ("vx" if source == "local" else "x"), .2001
        setattr(sample, field, invalid)
        self.tick(node, 43.24)
        self.assertIsNone(node._native_settle_started_s)
        observed = self.diagnostic(node)
        self.assertIsNone(observed["settle_started_source_s"])
        self.assertIsNone(observed["settle_elapsed_source_s"])
        setattr(sample, field, 0.)
        self.tick(node, 43.25)
        self.assertEqual(node._native_settle_started_s, 43.25)
        self.tick(node, 44.499)
        self.assertEqual(node._phase, "NATIVE_TAKEOFF")
        self.tick(node, 44.5)
        self.assertEqual(node._phase, "REQUEST_OFFBOARD")

    def test_either_source_loss_before_mode_command_aborts_without_request(self):
        for source in ("local", "adapted"):
            with self.subTest(source=source):
                node = self.node("REQUEST_OFFBOARD")
                if source == "local":
                    node._native_local.y = .19
                else:
                    node._odom.twist.twist.linear.x = .2001
                self.tick(node)
                self.assertEqual(node._phase, "ABORTED")
                self.assertFalse(node.requests)
                self.assertFalse(node.last_output.valid)

    def test_ready_dual_source_handoff_still_sends_the_original_mode_request(self):
        node = self.node("REQUEST_OFFBOARD")
        self.tick(node)
        self.assertEqual(node._phase, "REQUEST_OFFBOARD")
        self.assertEqual(node.requests, [(COMMAND.VEHICLE_CMD_DO_SET_MODE, 1., 6.)])
        self.assertTrue(self.diagnostic(node)["checks_ready"])

    def test_fresh_receipt_does_not_replace_adapted_source_freshness(self):
        cases = ((41.499999, "native_adapted_source_stale"),
                 (42.050001, "native_adapted_source_future"),
                 (None, "native_adapted_source_stamp_invalid"))
        for source_s, issue in cases:
            with self.subTest(source_s=source_s):
                node = self.node()
                node._odom.header.stamp = stamp(source_s) if source_s is not None else None
                self.tick(node, publish_samples=False)
                self.assertEqual(node._phase, "NATIVE_TAKEOFF")
                self.assertIsNone(node._native_settle_started_s)
                self.assertIn(issue, self.diagnostic(node)["issues"])
        for source_s in (41.5, 42.05):
            with self.subTest(allowed_boundary=source_s):
                node = self.node()
                node._odom.header.stamp = stamp(source_s)
                self.tick(node, publish_samples=False)
                self.assertEqual(node._native_settle_started_s, 42.)

    def test_invalid_physical_values_fail_closed_and_diagnostics_remain_json(self):
        cases = (("local_position", "x", math.nan), ("local_velocity", "vx", math.inf),
                 ("adapted_position", "x", math.inf), ("adapted_velocity", "y", math.nan),
                 ("local_position", "y", True), ("adapted_velocity", "z", True))
        for kind, field, value in cases:
            with self.subTest(kind=kind, field=field, value=value):
                node = self.node()
                target = (node._native_local if kind.startswith("local") else
                          node._odom.pose.pose.position if kind == "adapted_position" else
                          node._odom.twist.twist.linear)
                setattr(target, field, value)
                # Inspect an explicitly invalid cached-state input; do not have
                # the fixture publish fresh valid state over the intended case.
                self.tick(node, publish_samples=False)
                self.assertEqual(node._phase, "NATIVE_TAKEOFF")
                self.assertIsNone(node._native_settle_started_s)
                observed = self.diagnostic(node)
                self.assertFalse(observed["checks_ready"])
                self.assertIn("native_" + kind.split("_", 1)[0] + "_physical_state_invalid", observed["issues"])

    def test_diagnostics_preserve_actual_goal_anchor_callbacks_and_parser_suffix(self):
        node = self.node("WAITING")
        node._status.arming_state = 1
        node._heartbeat_started, node._heartbeat_received = 98., 100.
        node._odom.pose.pose.position = SimpleNamespace(x=1.25, y=-2.5, z=.25)
        self.tick(node, 42., 100.1)
        self.assertEqual(node._phase, "REQUEST_NATIVE_TAKEOFF")
        observed = self.diagnostic(node)
        self.assertIsNone(observed["settle_started_source_s"])
        self.assertIsNone(observed["settle_timing_observed_source_s"])
        self.assertIsNone(observed["settle_elapsed_source_s"])
        self.assertEqual(observed["settle_required_total_s"], 1.25)
        anchor = observed["ground_anchor"]
        self.assertEqual(node._goal, (1.25, -2.5, 3.25))
        self.assertEqual(anchor, {"position_enu_m": [1.25, -2.5, .25],
                                  "odom_header_stamp_ns": 42_000_000_000,
                                  "odom_callback_ros_s": 42., "odom_callback_wall_s": 100.1,
                                  "captured_ros_s": 42.})
        node._status.arming_state = 2
        node._status.nav_state = STATUS.NAVIGATION_STATE_AUTO_TAKEOFF
        self.tick(node, 42.05, 100.15)
        node._status.nav_state = STATUS.NAVIGATION_STATE_AUTO_LOITER
        node._odom.pose.pose.position.z = 3.25
        node._native_local.x, node._native_local.y, node._native_local.z = -2.5, 1.25, -3.25
        self.tick(node, 42.1, 100.2)
        observed = self.diagnostic(node)
        self.assertEqual(observed["goal_enu_m"], [1.25, -2.5, 3.25])
        self.assertEqual(observed["ground_anchor"], anchor)
        self.assertEqual(observed["local"]["timestamp_sample_us"], 42_100_000)
        self.assertEqual(observed["adapted"]["header_stamp_ns"], 42_100_000_000)
        for source in ("local", "adapted"):
            self.assertAlmostEqual(observed[source]["callback_ros_s"], 42.1, places=9)
            self.assertEqual(observed[source]["callback_wall_s"], 100.2)
            self.assertEqual(observed[source]["position_error_m"], 0.)
        self.assertAlmostEqual(observed["check_ros_s"], 42.1, places=9)
        self.assertEqual(observed["check_wall_s"], 100.2)
        message = SimpleNamespace(data=node.last_phase)
        self.assertEqual(node.last_phase.count("source_sim_s="), 1)
        self.assertTrue(node.last_phase.endswith("; source_sim_s=42.100000000"))
        self.assertEqual(native_audit.phase_source_time(message), 42.1)
        self.assertEqual(native_audit.phase_number(message, "native_started_source_s"), 42.05)

    def test_unobserved_callback_and_anchor_fields_remain_null(self):
        node = self.node()
        self.tick(node, publish_samples=False)
        observed = self.diagnostic(node)
        self.assertIsNone(observed["ground_anchor"])
        self.assertIsNone(observed["local"]["callback_ros_s"])
        self.assertIsNone(observed["local"]["callback_wall_s"])
        self.assertIsNone(observed["adapted"]["callback_ros_s"])
        self.assertTrue(observed["checks_ready"])


if __name__ == "__main__":
    unittest.main()
