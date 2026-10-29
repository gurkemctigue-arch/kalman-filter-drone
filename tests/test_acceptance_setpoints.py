"""Acceptance requires actual setpoint classifications, including partial fields."""

from collections import Counter
import importlib.util
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


monitor = load("acceptance_flight_monitor", "stage1_flight_monitor.py")
summary = load("acceptance_summary", "summarize_stage1_acceptance.py")
NAN = float("nan")


class SetpointEvidenceTests(unittest.TestCase):
    def make_node(self, phase="FOLLOW"):
        node = monitor.FlightMonitor.__new__(monitor.FlightMonitor)
        node.counts = Counter({key: 0 for key in monitor.SETPOINT_COUNTER_KEYS})
        node.phase = phase
        node.events = []
        node.event = lambda kind, **fields: node.events.append({"kind": kind, **fields})
        return node

    @staticmethod
    def report(node):
        return {"counts": dict(node.counts), "setpoint_evidence": {
            "counter_schema_version": 1, "topic": "/fmu/in/trajectory_setpoint",
            "classified_samples": node.counts["classified_px4_setpoints"],
            "required_counters_present": True,
        }}

    def valid_trial(self):
        node = self.make_node()
        for _ in range(20):
            node.on_setpoint(NS(position=[1., 2., 3.], velocity=[NAN] * 3))
        # A braking callback may arrive before the HOLD phase callback. It
        # remains a valid exclusive velocity setpoint in a position trial.
        node.on_setpoint(NS(position=[NAN] * 3, velocity=[0.] * 3))
        node.phase = "HOLD"
        for _ in range(100):
            node.on_setpoint(NS(position=[NAN] * 3, velocity=[0.] * 3))
        return node

    def test_partial_mixed_fields_are_invalid_and_logged(self):
        node = self.make_node()
        node.on_setpoint(NS(position=[1., NAN, NAN], velocity=[NAN, 2., NAN]))
        self.assertEqual(node.counts["simultaneous_position_velocity_setpoints"], 1)
        self.assertEqual(node.counts["malformed_partial_setpoints"], 1)
        self.assertEqual(node.counts["partial_position_setpoints"], 1)
        self.assertEqual(node.counts["partial_velocity_setpoints"], 1)
        self.assertEqual(node.counts["follow_invalid_setpoints"], 1)
        self.assertEqual(node.counts["follow_position_setpoints"], 0)
        self.assertEqual(node.counts["follow_velocity_setpoints"], 0)
        self.assertEqual(node.events[0]["kind"], "invalid_px4_setpoint")
        self.assertEqual(node.events[0]["position"], [1., "nan", "nan"])

    def test_inactive_infinite_partial_and_wrong_dimension_fields_are_invalid(self):
        cases = [([NAN] * 3, [NAN] * 3), ([1., 2., 3.], [math.inf, NAN, NAN]),
                 ([NAN] * 3, [1., NAN, NAN]), ([1., 2.], [NAN] * 3)]
        for position, velocity in cases:
            with self.subTest(position=position, velocity=velocity):
                node = self.make_node()
                node.on_setpoint(NS(position=position, velocity=velocity))
                self.assertEqual(node.counts["invalid_setpoints"], 1)
                self.assertEqual(node.counts["position_only_setpoints"], 0)
                self.assertEqual(node.counts["velocity_only_setpoints"], 0)

    def test_position_trial_can_brake_with_exclusive_zero_velocity(self):
        node = self.valid_trial()
        evidence = summary.setpoint_evidence(self.report(node))
        self.assertTrue(evidence["complete"])
        self.assertTrue(evidence["counter_conservation_valid"])
        self.assertTrue(evidence["exclusive_fields"])
        self.assertEqual(node.counts["follow_position_setpoints"], 20)
        self.assertEqual(node.counts["follow_velocity_setpoints"], 1)
        self.assertEqual(set(monitor.SETPOINT_COUNTER_KEYS), set(summary.SETPOINT_COUNTER_KEYS))

    def test_missing_counter_or_schema_cannot_be_treated_as_observed_zero(self):
        for omitted in ("simultaneous_position_velocity_setpoints", "malformed_partial_setpoints"):
            with self.subTest(omitted=omitted):
                report = self.report(self.valid_trial())
                del report["counts"][omitted]
                evidence = summary.setpoint_evidence(report)
                self.assertFalse(evidence["complete"])
                self.assertFalse(evidence["exclusive_fields"])
                self.assertIn(omitted, evidence["missing_counters"])
        self.assertFalse(summary.setpoint_evidence({"counts": {}})["exclusive_fields"])
        report = self.report(self.valid_trial())
        del report["setpoint_evidence"]
        self.assertFalse(summary.setpoint_evidence(report)["complete"])

    def test_zero_samples_wrong_counter_types_and_unclassified_samples_do_not_pass(self):
        self.assertFalse(summary.setpoint_evidence(self.report(self.make_node()))["exclusive_fields"])
        report = self.report(self.valid_trial())
        report["counts"]["invalid_setpoints"] = False
        self.assertFalse(summary.setpoint_evidence(report)["complete"])
        report = self.report(self.valid_trial())
        report["counts"]["classified_px4_setpoints"] -= 1
        self.assertFalse(summary.setpoint_evidence(report)["counter_conservation_valid"])


class ShutterCorrelationTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("Time", lambda: NS()), ("Duration", lambda **kwargs: NS()),
                            ("TransformException", RuntimeError)):
            patcher = patch.object(monitor, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_node(self, future):
        node = monitor.FlightMonitor.__new__(monitor.FlightMonitor)
        node.shutter_future, node.shutter_pending = None, None
        node.shutter_request_seq, node.shutter_requested = 0, False
        node.shutter_events, node.events = [], []
        node.clock_s = 10.
        node.now_s = lambda: node.clock_s
        node.event = lambda kind, **fields: node.events.append({"time_s": node.now_s(), "kind": kind, **fields})
        node.odom = NS(pose=NS(pose=NS(position=NS(x=0., y=0., z=3.), orientation=NS(x=0., y=0., z=0., w=1.))))
        node.shutter_client = NS(service_is_ready=lambda: True, call_async=lambda request: future)
        node.shutter_last_pose_update_s = -math.inf
        def measured_camera_tf(*args, **kwargs):
            stamp_ns = round(node.clock_s * 1e9)
            return NS(header=NS(stamp=NS(sec=stamp_ns // 1_000_000_000,
                                        nanosec=stamp_ns % 1_000_000_000), frame_id="map"),
                      child_frame_id="camera_link",
                      transform=NS(translation=NS(x=0., y=0., z=3.),
                                   rotation=NS(x=0., y=0., z=0., w=1.)))
        node.shutter_tf_buffer = NS(lookup_transform=measured_camera_tf)
        return node

    @staticmethod
    def request():
        return NS(entity=NS(MODEL=2), pose=NS(position=NS(), orientation=NS()))

    def test_request_and_receipt_are_correlated_without_inventing_response_time(self):
        future = NS(done=lambda: True, result=lambda: NS(success=True))
        node = self.make_node(future)
        with patch.object(monitor, "SetEntityPose", NS(Request=self.request), create=True):
            node.set_shutter(True)
            node.clock_s = 10.3
            node.set_shutter(True)
            node.set_shutter(False)
        request, response, refresh, refresh_response, opened = node.events
        self.assertEqual([row["kind"] for row in node.events],
                         ["shutter", "shutter_service_result", "shutter_pose_update",
                          "shutter_pose_update_result", "shutter"])
        self.assertEqual(request["request_id"], response["request_id"])
        self.assertTrue(response["active"])
        self.assertEqual(response["request_time_s"], 10.)
        self.assertEqual(response["time_s"], 10.3)
        self.assertTrue(response["success"])
        self.assertEqual(refresh["request_id"], refresh_response["request_id"])
        self.assertNotEqual(request["request_id"], refresh["request_id"])
        self.assertEqual(refresh_response["request_time_s"], 10.3)
        self.assertEqual(refresh_response["time_s"], 10.3)
        self.assertTrue(refresh_response["success"])
        self.assertEqual(opened["request_id"], 3)
        self.assertFalse(opened["active"])

    def test_failed_future_records_failed_response_for_the_exact_action(self):
        def failed():
            raise RuntimeError("bridge unavailable")

        node = self.make_node(NS(done=lambda: True, result=failed))
        with patch.object(monitor, "SetEntityPose", NS(Request=self.request), create=True):
            node.set_shutter(True)
            node.clock_s = 10.2
            node.set_shutter(True)
        self.assertEqual(node.events[1]["kind"], "shutter_service_result")
        self.assertFalse(node.events[1]["success"])
        self.assertEqual(node.events[1]["request_id"], 1)
        self.assertEqual(node.events[1]["error"], "bridge unavailable")


class OfflineAcceptanceEvidenceTests(unittest.TestCase):
    @staticmethod
    def evidence():
        return {"schema_version": 3,
                "interval": {"start_s": 1., "end_s": 16., "recorded_end_s": 16.,
                             "covers_recorded_trial_end": True},
                "occlusions": [{
            "kind": "long", "shutter_execution": {"close_success": True, "open_success": True,
                                                     "close_ack_before_open_request": True},
            "explicit_reselection": {"confirmed": True, "original_target_uuid": "original-task",
                                     "confirmed_target_uuid": "new-task", "requested_target_uuid": "new-task",
                                     "action": "SELECT", "confirmation_time_s": 10.},
            "post_reselection_tracking": {
                "result": "PASS", "checks": {key: True for key in summary.POST_RESELECTION_CHECK_KEYS},
                "confirmed_target_uuid": "new-task", "confirmation_time_s": 10.,
                "minimum_duration_s": 5., "tail_freshness_s": .5,
                "maximum_evidence_gap_s": .5, "maximum_measurement_age_s": .75, "control_grace_s": .1,
                "observed_duration_s": 6., "state_span_s": 5.9, "control_span_s": 5.85,
                "last_state_age_to_trial_end_s": .05, "last_control_age_to_trial_end_s": .05,
                "last_state_measurement_age_at_trial_end_s": .1,
            },
        }]}

    def test_current_schema_requires_action_responses_and_a_different_confirmed_uuid(self):
        self.assertTrue(all(summary.offline_acceptance_evidence(self.evidence()).values()))
        old = self.evidence()
        old["schema_version"] = 2
        self.assertFalse(summary.offline_acceptance_evidence(old)["current_schema"])
        self.assertFalse(summary.offline_acceptance_evidence(old)["sustained_tracking_after_reselection"])
        no_response = self.evidence()
        del no_response["occlusions"][0]["shutter_execution"]["open_success"]
        self.assertFalse(summary.offline_acceptance_evidence(no_response)["shutter_operations_confirmed"])
        for changed in ({"confirmed_target_uuid": "original-task"}, {"requested_target_uuid": "other-task"},
                        {"confirmed": False}, {"action": "CLEAR"}):
            with self.subTest(changed=changed):
                wrong = self.evidence()
                wrong["occlusions"][0]["explicit_reselection"].update(changed)
                self.assertFalse(summary.offline_acceptance_evidence(wrong)["new_task_confirmed_from_bag"])

    def test_reset_can_authorize_a_new_uuid_without_requesting_that_uuid(self):
        reset = self.evidence()
        reset["occlusions"][0]["explicit_reselection"].update(action="RESET", requested_target_uuid="")
        self.assertTrue(summary.offline_acceptance_evidence(reset)["new_task_confirmed_from_bag"])

    def test_reselection_requires_sustained_recorded_tracking_not_one_new_measurement(self):
        valid = self.evidence()
        self.assertTrue(summary.offline_acceptance_evidence(valid)["sustained_tracking_after_reselection"])
        missing = self.evidence()
        del missing["occlusions"][0]["post_reselection_tracking"]
        self.assertFalse(summary.offline_acceptance_evidence(missing)["sustained_tracking_after_reselection"])
        for changed in ({"result": "FAIL"}, {"result": "INCOMPLETE"},
                        {"observed_duration_s": 1.05}, {"state_span_s": 1.05}, {"control_span_s": 1.05},
                        {"confirmed_target_uuid": "original-task"}, {"confirmed_target_uuid": "other-task"},
                        {"confirmation_time_s": 10.1}):
            with self.subTest(changed=changed):
                invalid = self.evidence()
                invalid["occlusions"][0]["post_reselection_tracking"].update(changed)
                self.assertFalse(summary.offline_acceptance_evidence(invalid)["sustained_tracking_after_reselection"])

    def test_every_tracking_check_requires_explicit_true(self):
        for key in summary.POST_RESELECTION_CHECK_KEYS:
            for value in (None, False, 1, "true"):
                with self.subTest(key=key, value=value):
                    invalid = self.evidence()
                    checks = invalid["occlusions"][0]["post_reselection_tracking"]["checks"]
                    if value is None:
                        del checks[key]
                    else:
                        checks[key] = value
                    self.assertFalse(summary.offline_acceptance_evidence(invalid)["sustained_tracking_after_reselection"])

    def test_relaxed_thresholds_stale_tails_and_nonfinite_values_cannot_pass(self):
        for changed in ({"minimum_duration_s": 1.}, {"tail_freshness_s": 1.},
                        {"maximum_evidence_gap_s": 1.}, {"control_grace_s": .2},
                        {"maximum_measurement_age_s": 1.}, {"maximum_measurement_age_s": 0.},
                        {"tail_freshness_s": 0.}, {"maximum_evidence_gap_s": 0.},
                        {"control_grace_s": -.1}, {"last_state_age_to_trial_end_s": .51},
                        {"last_control_age_to_trial_end_s": .51}, {"last_state_age_to_trial_end_s": -.1},
                        {"last_state_measurement_age_at_trial_end_s": -.1}, {"observed_duration_s": math.nan},
                        {"last_state_measurement_age_at_trial_end_s": .76},
                        {"state_span_s": math.inf}, {"control_span_s": True}):
            with self.subTest(changed=changed):
                invalid = self.evidence()
                invalid["occlusions"][0]["post_reselection_tracking"].update(changed)
                self.assertFalse(summary.offline_acceptance_evidence(invalid)["sustained_tracking_after_reselection"])

    def test_all_long_windows_need_sustained_tracking_evidence(self):
        invalid = self.evidence()
        invalid["occlusions"].append({"kind": "long"})
        self.assertFalse(summary.offline_acceptance_evidence(invalid)["sustained_tracking_after_reselection"])
        self.assertFalse(summary.offline_acceptance_evidence({"schema_version": 3, "occlusions": []})[
            "sustained_tracking_after_reselection"])

    def test_report_must_cover_the_full_recorded_trial_end(self):
        self.assertTrue(summary.offline_acceptance_evidence(self.evidence())["full_recorded_trial_end"])
        missing = self.evidence()
        del missing["interval"]
        self.assertFalse(summary.offline_acceptance_evidence(missing)["full_recorded_trial_end"])
        for changed in ({"covers_recorded_trial_end": False}, {"covers_recorded_trial_end": 1},
                        {"end_s": 15.9}, {"end_s": math.nan}, {"recorded_end_s": math.inf},
                        {"end_s": True}):
            with self.subTest(changed=changed):
                invalid = self.evidence()
                invalid["interval"].update(changed)
                self.assertFalse(summary.offline_acceptance_evidence(invalid)["full_recorded_trial_end"])
        for omitted in ("covers_recorded_trial_end", "end_s", "recorded_end_s"):
            with self.subTest(omitted=omitted):
                invalid = self.evidence()
                del invalid["interval"][omitted]
                self.assertFalse(summary.offline_acceptance_evidence(invalid)["full_recorded_trial_end"])


if __name__ == "__main__":
    unittest.main()
