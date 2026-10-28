"""A recorded abort must fail the runner; intentional hover stays testable."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


monitor = load("monitor_completion", "scripts/stage1_flight_monitor.py")
runner = load("trial_status_watchdog", "scripts/run_stage1_trial.py")


class CompletionTests(unittest.TestCase):
    def summary(self):
        return {"armed_seen": True, "offboard_seen": True,
                "max_vehicle_altitude_m": 3.0, "basic_flight_passed": True,
                "counts": {"px4_setpoints": 200, "classified_px4_setpoints": 200,
                           "invalid_setpoints": 0, "simultaneous_position_velocity_setpoints": 0}}

    def test_completed_follow_requires_basic_flight_evidence(self):
        summary = self.summary()
        self.assertEqual(monitor.flight_monitor_outcome(summary, "follow_duration_reached")["monitor_exit_code"], 0)
        summary["basic_flight_passed"] = False
        self.assertEqual(monitor.flight_monitor_outcome(summary, "follow_duration_reached")["monitor_exit_code"], 1)

    def test_abort_timeout_interrupt_or_context_stop_cannot_pass_prior_good_flight(self):
        for reason in ["flight_aborted", "wall_timeout", "interrupted", "ros_context_stopped"]:
            with self.subTest(reason=reason):
                result = monitor.flight_monitor_outcome(self.summary(), reason)
                self.assertFalse(result["monitor_success"])
                self.assertNotEqual(result["monitor_exit_code"], 0)

    def test_explicit_no_follow_allows_hover_without_visual_commands_or_travel(self):
        summary = self.summary()
        summary["basic_flight_passed"] = False
        result = monitor.flight_monitor_outcome(summary, "no_follow_duration_reached")
        self.assertTrue(result["monitor_success"])
        self.assertEqual(result["completion_criteria"], "hover_flight_stream")
        self.assertTrue(result["offline_evaluation_required"])

    def test_no_follow_cannot_hide_failure_to_takeoff_or_malformed_px4_stream(self):
        for field, value in [("max_vehicle_altitude_m", .047), ("armed_seen", False), ("offboard_seen", False)]:
            with self.subTest(field=field):
                summary = self.summary()
                summary[field] = value
                self.assertFalse(monitor.flight_monitor_outcome(summary, "no_follow_duration_reached")["monitor_success"])
        for field, value in [("px4_setpoints", 2), ("invalid_setpoints", 1),
                             ("simultaneous_position_velocity_setpoints", 1), ("classified_px4_setpoints", 199)]:
            with self.subTest(counter=field):
                summary = self.summary()
                summary["counts"][field] = value
                self.assertFalse(monitor.flight_monitor_outcome(summary, "no_follow_duration_reached")["monitor_success"])

    def node(self):
        node = monitor.FlightMonitor.__new__(monitor.FlightMonitor)
        node.args = SimpleNamespace(duration=45., wall_timeout=300., no_follow_duration_s=60.)
        node.started_wall, node.follow_start, node.start_sim = 0., 5., .1
        node.aborted_wall, node.phase = None, "FOLLOW"
        node.now_s = lambda: 55.
        return node

    def test_abort_wins_over_follow_endpoint_and_preserves_two_second_tail(self):
        node = self.node()
        node.aborted_wall, node.phase = 99., "ABORTED"
        with patch.object(monitor.time, "monotonic", return_value=100.):
            self.assertEqual(node.termination_reason(), "flight_aborted")
            self.assertFalse(node.finished())
        with patch.object(monitor.time, "monotonic", return_value=101.1):
            self.assertTrue(node.finished())

    def test_wall_timeout_wins_over_duration_endpoint(self):
        with patch.object(monitor.time, "monotonic", return_value=301.):
            self.assertEqual(self.node().termination_reason(), "wall_timeout")

    def test_sim_only_wall_budget_matches_px4_two_hz_source_without_changing_real_default(self):
        self.assertEqual(runner.simulation_status_watchdog_s(1.), 1.)
        self.assertEqual(runner.simulation_status_watchdog_s(.5), 2.)
        self.assertAlmostEqual(runner.simulation_status_watchdog_s(.7), 1 / .7)
        for value in [0., -1., 1.01, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                runner.simulation_status_watchdog_s(value)

    def test_main_returns_failed_monitor_exit_code_and_always_destroys_node(self):
        node = Mock()
        node.finished.return_value = True
        node.finish.return_value = {"monitor_exit_code": 1}
        ros = SimpleNamespace(init=Mock(), ok=Mock(return_value=True), shutdown=Mock(), spin_once=Mock())
        with patch.object(monitor, "rclpy", ros), patch.object(monitor, "FlightMonitor", return_value=node), \
                patch("sys.argv", ["monitor", "--output", "unused_test_output"]):
            self.assertEqual(monitor.main(), 1)
        node.finish.assert_called_once_with(interrupted=False)
        node.destroy_node.assert_called_once()
        ros.shutdown.assert_called_once()

    def test_main_records_keyboard_interrupt_as_failed_completion_and_cleans_up(self):
        node = Mock()
        node.finished.return_value = False
        node.finish.return_value = {"monitor_exit_code": 1}
        ros = SimpleNamespace(init=Mock(), ok=Mock(return_value=True), shutdown=Mock(),
                              spin_once=Mock(side_effect=KeyboardInterrupt))
        with patch.object(monitor, "rclpy", ros), patch.object(monitor, "FlightMonitor", return_value=node), \
                patch("sys.argv", ["monitor", "--output", "unused_test_output"]):
            self.assertEqual(monitor.main(), 1)
        node.finish.assert_called_once_with(interrupted=True)
        node.destroy_node.assert_called_once()
        ros.shutdown.assert_called_once()


if __name__ == "__main__":
    unittest.main()
