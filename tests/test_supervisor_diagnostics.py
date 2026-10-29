"""Pure callback observations, preserved guards and steady-clock wiring; no ROS."""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_flight_supervisor as fixtures

flight = fixtures.flight
ROOT = Path(__file__).resolve().parents[1]


class SupervisorDiagnosticsTests(unittest.TestCase):
    def node(self):
        case = fixtures.FlightHandoffTests("test_fresh_command_forwarded_only_after_takeoff_phase")
        return case.source_supervisor()

    def receive(self, node, stamp, wall):
        message = SimpleNamespace(timestamp=stamp, arming_state=2, nav_state=14,
                                  failsafe=False, pre_flight_checks_pass=True)
        with patch.object(flight.time, "monotonic", return_value=wall):
            node._on_status(message)
        return message

    def publish(self, node, wall):
        node._diagnostics_pub = SimpleNamespace(publish=lambda message: setattr(node, "diagnostic", message.data))
        with patch.object(flight, "String", lambda: SimpleNamespace(data=""), create=True), \
             patch.object(flight.time, "monotonic", return_value=wall), \
             patch.object(flight.time, "time_ns", return_value=1_800_000_000_000_000_000):
            node._publish_supervisor_diagnostics()
        return json.loads(node.diagnostic)

    def tick(self, node, wall):
        with patch.object(flight, "TrackingCommand", fixtures.FakeCommand, create=True), \
             patch.object(flight, "VehicleStatus", SimpleNamespace(ARMING_STATE_ARMED=2, NAVIGATION_STATE_OFFBOARD=14), create=True), \
             patch.object(flight, "String", lambda: SimpleNamespace(data=""), create=True), \
             patch.object(flight.time, "monotonic", return_value=wall):
            node._tick()

    def test_received_but_rejected_callbacks_do_not_refresh_accepted_control_state(self):
        node = self.node()
        accepted = self.receive(node, 41_500_000, 100.)
        self.receive(node, 41_500_000, 101.)
        self.receive(node, 42_100_000, 102.)
        self.receive(node, None, 103.)
        report = self.publish(node, 104.)
        self.assertIs(node._status, accepted)
        self.assertEqual(node._status_received, 100.)
        self.assertEqual(report["status_counts"], {"raw_received": 4, "accepted": 1, "rejected": 3,
                                                  "raw_without_recorded_outcome": 0})
        self.assertEqual(report["status_rejections_by_reason"], {
            "duplicate_source_sample": 1, "future_or_wrong_domain_source_timestamp": 1,
            "invalid_source_timestamp": 1})
        self.assertEqual(report["last_raw_status"]["wall_monotonic_s"], 103.)
        self.assertIsNone(report["last_raw_status"]["source_stamp_ns"])
        self.assertEqual(report["last_accepted_status"]["source_stamp_ns"], 41_500_000_000)
        self.assertEqual(report["last_accepted_status"]["age_wall_s"], 4.)
        self.assertEqual(report["completed_max_wall_gaps_s"]["raw_status_callbacks"], 1.)
        self.assertIsNone(report["completed_max_wall_gaps_s"]["accepted_status_callbacks"])

    def test_new_valid_status_records_actual_acceptance_time_without_changing_gate(self):
        node = self.node()
        self.receive(node, 41_500_000, 100.)
        accepted = self.receive(node, 42_000_000, 100.8)
        report = self.publish(node, 100.9)
        self.assertIs(node._status, accepted)
        self.assertEqual(node._status_received, 100.8)
        self.assertEqual(report["status_counts"]["accepted"], 2)
        self.assertAlmostEqual(report["completed_max_wall_gaps_s"]["accepted_status_callbacks"], .8)
        self.assertEqual(report["guard_limits"]["status_wall_s"], 10.)
        self.assertEqual(report["guard_limits"]["status_source_age_s"], 1.)
        self.assertEqual(report["guard_limits"]["status_source_future_s"], .05)

    def test_diagnostics_during_ros_pause_observe_wall_age_and_do_not_run_guard(self):
        node = self.node()
        self.receive(node, 41_500_000, 100.)
        before_clock = copy.deepcopy(node._status_clock.__dict__)
        first = self.publish(node, 101.)
        second = self.publish(node, 121.)
        self.assertEqual(first["sample_ros_ns"], second["sample_ros_ns"])
        self.assertEqual(second["diagnostic_clock"]["wall_delta_s"], 20.)
        self.assertEqual(second["diagnostic_clock"]["ros_delta_s"], 0.)
        self.assertEqual(second["diagnostic_clock"]["observed_ros_progress_per_wall"], 0.)
        self.assertEqual(second["diagnostic_clock"]["wall_since_observed_ros_change_s"], 20.)
        self.assertEqual(second["control_tick"]["count"], 0)
        self.assertEqual(second["accepted_control_status"]["age_wall_s"], 21.)
        self.assertEqual(node._phase, "FOLLOW", "diagnostic timer does not become a new flight guard")
        self.assertEqual(node._status_received, 100.)
        self.assertEqual(node._status_clock.__dict__, before_clock)

    def test_timer_is_one_hz_steady_time_and_reports_same_executor_limit(self):
        node = self.node()
        created = []
        node.create_timer = lambda period, callback, *, clock: created.append((period, callback, clock))
        with patch.object(flight, "ClockType", SimpleNamespace(STEADY_TIME="STEADY"), create=True), \
             patch.object(flight, "Clock", lambda *, clock_type: SimpleNamespace(clock_type=clock_type), create=True):
            node._create_diagnostics_timer()
        self.assertEqual(created[0][0], 1.0)
        self.assertEqual(created[0][2].clock_type, "STEADY")
        self.assertEqual(created[0][1].__func__, node._publish_supervisor_diagnostics.__func__)
        report = self.publish(node, 101.)
        self.assertEqual(report["timer_contract"]["executor"], "SAME_SINGLE_THREADED_EXECUTOR_AS_CONTROL")

    def test_completed_tick_gap_and_current_tick_silence_are_separate(self):
        node = self.node()
        self.receive(node, 41_500_000, 100.)
        self.tick(node, 100.1)
        self.tick(node, 100.4)
        report = self.publish(node, 102.4)
        self.assertEqual(report["control_tick"]["count"], 2)
        self.assertAlmostEqual(report["control_tick"]["age_wall_s"], 2.)
        self.assertAlmostEqual(report["completed_max_wall_gaps_s"]["control_ticks"], .3)

    def test_observed_clock_regression_does_not_mutate_existing_control_latch(self):
        node = self.node()
        self.receive(node, 41_500_000, 100.)
        self.publish(node, 100.1)
        node._test_source_s = 41.9
        report = self.publish(node, 100.2)
        self.assertEqual(report["diagnostic_clock"]["observed_ros_regressions"], 1)
        self.assertFalse(node._status_ros_regressed)
        self.assertFalse(node._status_clock.latched)
        self.assertEqual(node._status_last_ros_ns, 42_000_000_000)
        self.tick(node, 100.3)
        self.assertTrue(node._status_ros_regressed, "existing control tick still applies the original latch")
        self.assertEqual(node._phase, "ABORTED")

    def test_raw_and_rejected_counts_preserve_clock_regression_latch(self):
        node = self.node()
        accepted = self.receive(node, 41_500_000, 100.)
        self.receive(node, 41_400_000, 100.1)
        self.receive(node, 42_000_000, 100.2)
        report = self.publish(node, 100.3)
        self.assertEqual(report["status_counts"]["raw_received"], 3)
        self.assertEqual(report["status_counts"]["accepted"], 1)
        self.assertEqual(report["status_counts"]["rejected"], 2)
        self.assertEqual(report["status_rejections_by_reason"], {"source_clock_regression_restart_required": 2})
        self.assertIs(node._status, accepted)
        self.assertEqual(node._status_received, 100.)

    def test_never_observed_values_remain_null_instead_of_boot_age_or_zero(self):
        node = self.node()
        node._odom = None
        report = self.publish(node, 101.)
        self.assertIsNone(report["last_raw_status"])
        self.assertIsNone(report["last_accepted_status"])
        self.assertIsNone(report["control_tick"]["age_wall_s"])
        self.assertIsNone(report["accepted_control_status"]["age_wall_s"])
        self.assertIsNone(report["odometry"]["age_wall_s"])
        self.assertIsNone(report["completed_max_wall_gaps_s"]["raw_status_callbacks"])

    def test_runner_records_and_declares_the_actual_default_diagnostic_topic(self):
        supervisor = ast.parse((ROOT / "ros2_ws/src/uav_tracking_px4_adapter/uav_tracking_px4_adapter/flight_supervisor.py").read_text(encoding="utf-8"))
        defaults = next(node for node in ast.walk(supervisor) if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == "defaults" for target in node.targets))
        topic = ast.literal_eval(defaults.value)["supervisor_diagnostics_topic"]
        runner = ast.parse((ROOT / "scripts/run_stage1_trial.py").read_text(encoding="utf-8"))
        declared = [keyword.value.value for node in ast.walk(runner) if isinstance(node, ast.Call)
                    for keyword in node.keywords if keyword.arg == "supervisor_diagnostics_topic"]
        recorded = [element.value for node in ast.walk(runner) if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "topics" for target in node.targets)
                    for element in node.value.elts if isinstance(element, ast.Constant)]
        self.assertEqual(declared, [topic])
        self.assertEqual(recorded.count(topic), 1)


if __name__ == "__main__":
    unittest.main()
