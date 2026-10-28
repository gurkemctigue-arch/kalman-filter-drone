"""Pure fixtures for final JSON postprocessing; no ROS/bag/inference imports."""
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("metric_supplement", ROOT / "scripts/build_metric_supplement.py")
supplement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supplement)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    return path


def summary(path, rows):
    return write(path, {"schema_version": 1, "planned_flights": 166, "plan_sha256": "frozen", "trials": rows})


class MetricSupplementTests(unittest.TestCase):
    def test_online_velocity_p95_and_failures_remain_flight_units(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [{"name": name, "stage": 1, "target_class": "car", "command_mode": "velocity", "estimator_method": "raw", "result": status}
                    for name, status in (("pass", "PASS"), ("fail", "FAIL"), ("pending", "PENDING"))]
            source = summary(root / "summary.json", rows)
            for name, value in (("pass", .2), ("fail", .6), ("pending", 99.)):
                write(root / name / "online_state_accuracy_v2.json", {"schema_version": 2, "online_state_accuracy": {"metrics": {
                    "state_stamp_velocity_error_mps": {"rmse": value, "p95": value * 2}}}})
            before = source.read_bytes()
            data = supplement.build(source, root)
            group = data["groups"]["main166/s1/car/velocity/raw"]
            metric = group["metrics"]["online_velocity_rmse_mps"]
            self.assertEqual((metric["valid_flights"], metric["missing_flights"]), (2, 1))
            self.assertAlmostEqual(metric["mean"], .4)
            self.assertAlmostEqual(group["metrics"]["online_velocity_p95_mps"]["mean"], .8)
            self.assertEqual(data["flights"][2]["metrics"], {})
            self.assertEqual(source.read_bytes(), before)
            self.assertIn("逐飞行 p95 的均值不是合并帧 p95", supplement.markdown(data))

    def test_missing_stage2_timing_and_censored_settling_are_not_zero(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = summary(root / "summary.json", [{"name": "crossing", "stage": 2, "target_class": "person", "scenario": "crossing", "result": "PASS"}])
            write(root / "crossing/stage2_evaluation.json", {"result": "PASS", "occlusions": []})
            write(root / "crossing/follow_dynamics.json", {"windows": [
                {"kind": "initial_follow_before_first_shutter", "distance": {"settling_right_censored": True, "settling_time_s": 0., "opposite_side_overshoot_m": .3}},
                {"kind": "explicit_selection", "first_measured_confirmation_after_request_s": None, "confirmation_censored": True}]})
            data = supplement.build(source, root)
            flight = data["flights"][0]
            self.assertIsNone(flight["metrics"]["detector_processed_sim_fps"])
            self.assertIsNone(flight["metrics"]["initial_distance_settling_s"])
            self.assertEqual(flight["settling_evidence"]["distance"], "RIGHT_CENSORED")
            self.assertEqual(flight["metrics"]["explicit_selection_confirmation_fraction"], 0.)
            self.assertIsNone(flight["metrics"]["explicit_selection_confirmation_mean_s"])
            self.assertEqual(flight["explicit_selection_evidence"]["confirmation_censored"], 1)

    def test_prediction_error_requires_short_window_predicted_fresh_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "state.frames.jsonl"
            rows = [
                {"time_s": .9, "state": 2, "prediction_age_s": .2, "state_stamp_position_error_m": 100.},
                {"time_s": 1.1, "state": 1, "prediction_age_s": 0., "state_stamp_position_error_m": 100.},
                {"time_s": 1.2, "state": 2, "prediction_age_s": .2, "state_stamp_position_error_m": .3, "state_stamp_velocity_error_mps": .4},
                {"time_s": 1.3, "state": 2, "prediction_age_s": .3, "state_stamp_position_error_m": .4},
                {"time_s": 1.4, "state": 2, "prediction_age_s": .8, "state_stamp_position_error_m": 100.},
                {"time_s": 1.5, "state": 2, "prediction_age_s": .4},
                {"time_s": 3.1, "state": 2, "prediction_age_s": .2, "state_stamp_position_error_m": 100.}]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            sources = []
            metrics, counts = supplement.short_prediction_metrics(path, [
                {"kind": "short", "start_s": 1., "end_s": 1.6},
                {"kind": "long", "start_s": 3., "end_s": 4.}], sources)
            self.assertAlmostEqual(metrics["short_shutter_predicted_position_rmse_m"], math.sqrt(.125))
            self.assertAlmostEqual(metrics["short_shutter_predicted_position_p95_m"], .395)
            self.assertEqual(counts["state_opportunities"], 5)
            self.assertEqual(counts["predicted_state_opportunities"], 3)
            self.assertEqual(counts["position_reference_samples"], 2)
            self.assertEqual(counts["velocity_reference_samples"], 1)
            self.assertIn("sha256", sources[0])

    def test_no_short_prediction_reference_keeps_rmse_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.frames.jsonl"
            path.write_text(json.dumps({"time_s": 1.1, "state": 2, "prediction_age_s": .1}) + "\n")
            metrics, counts = supplement.short_prediction_metrics(path, [{"kind": "short", "start_s": 1., "end_s": 1.2}], [])
            self.assertIsNone(metrics["short_shutter_predicted_position_rmse_m"])
            self.assertEqual(counts["predicted_state_opportunities"], 1)

    def test_duplicate_trial_names_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = summary(root / "summary.json", [{"name": "same"}, {"name": "same"}])
            with self.assertRaises(ValueError):
                supplement.build(source, root)
            source = summary(root / "summary.json", [{"name": "../outside"}])
            with self.assertRaises(ValueError):
                supplement.build(source, root)

    def test_frozen_incomplete_identity_null_and_null_sections_keep_failure_and_missing_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = summary(root / "summary.json", [{"name": "failed", "stage": 2, "target_class": "car", "scenario": "crossing", "result": "FAIL"}])
            write(root / "failed/physical_identity.json", {
                "schema_version": 1, "evaluation_status": "INCOMPLETE_EVIDENCE", "reason": "Missing independent GT",
                "selected_physical_identity_all": None, "tasks": None})
            write(root / "failed/follow_dynamics.json", {"windows": None})
            before = (root / "failed/physical_identity.json").read_bytes()
            data = supplement.build(source, root)
            flight = data["flights"][0]
            self.assertEqual(flight["result"], "FAIL")
            self.assertEqual(flight["selected_physical_identity_counts"], {})
            self.assertIsNone(flight["metrics"]["physical_retention_lower_bound"])
            self.assertIsNone(flight["metrics"]["task_mean_amodal_simulation_mot_id_switches"])
            self.assertTrue(any("Incomplete physical report" in note for note in flight["evidence_notes"]))
            self.assertEqual((root / "failed/physical_identity.json").read_bytes(), before)
            self.assertFalse(data["all_main_flights_terminal"])

    def test_empty_mot_zero_switches_are_missing_but_observed_failed_tracking_zero_is_retained(self):
        reports = {key: {} for key in ("basic", "online", "dynamics", "physical")}
        reports["physical"] = {"selected_physical_identity_all": {"counts": None}, "tasks": {
            "empty": {"amodal_simulation_mot": {"frames": 0, "gt_detections": 0, "predicted_detections": 0, "id_switches": 0, "hota": None}},
            "unavailable": None}}
        metrics, _, _, counts = supplement.extract_metrics(reports)
        self.assertEqual(counts, {})
        self.assertIsNone(metrics["task_mean_amodal_simulation_mot_id_switches"])
        reports["physical"]["tasks"]["measured_failure"] = {"amodal_simulation_mot": {
            "frames": 3, "gt_detections": 5, "predicted_detections": 0, "id_switches": 0, "hota": 0., "idf1": 0.}}
        metrics, _, _, _ = supplement.extract_metrics(reports)
        self.assertEqual(metrics["task_mean_amodal_simulation_mot_id_switches"], 0.)
        self.assertEqual(metrics["task_mean_amodal_simulation_mot_hota"], 0.)

    def test_short_recovery_uses_known_identity_condition_and_retains_unknown_and_unobserved_windows(self):
        windows = [{"kind": "short", "recovery_after_open_s": latency,
                    "checks": {"identity_preserved_on_observed_recovery": identity}}
                   for latency, identity in ((.2, True), (.3, False), (.4, None), (None, None), (None, True))]
        windows.append({"kind": "long", "recovery_after_open_s": 99.,
                        "checks": {"identity_preserved_on_observed_recovery": True}})
        metrics, evidence = supplement.short_same_task_recovery({"result": "FAIL", "occlusions": windows})
        self.assertEqual(evidence["short_requested_windows"], 5)
        self.assertEqual(evidence["observed_recovery_windows"], 3)
        self.assertEqual(evidence["conditional_identity_denominator_windows"], 2)
        self.assertEqual(evidence["same_track_and_task_confirmed_windows"], 1)
        self.assertEqual(evidence["changed_track_or_task_windows"], 1)
        self.assertEqual(evidence["unknown_identity_on_observed_recovery_windows"], 1)
        self.assertEqual(evidence["unobserved_or_untimed_recovery_windows"], 2)
        self.assertEqual(evidence["identity_flag_without_valid_timing_windows"], 1)
        self.assertAlmostEqual(metrics["short_post_open_measured_recovery_fraction"], .6)
        self.assertAlmostEqual(metrics["short_same_task_identity_preserved_fraction"], .5)
        self.assertAlmostEqual(metrics["short_same_task_recovery_mean_s"], .2)
        self.assertAlmostEqual(metrics["short_same_task_recovery_p95_s"], .2)
        self.assertEqual(evidence["source_report_result"], "FAIL")
        self.assertIn("not independent physical identity", evidence["definition"])

    def test_short_unknown_identity_never_becomes_zero_error_or_same_task_success(self):
        metrics, evidence = supplement.short_same_task_recovery({"occlusions": [
            {"kind": "short", "recovery_after_open_s": .1, "checks": None},
            {"kind": "short", "recovery_after_open_s": -1., "checks": {"identity_preserved_on_observed_recovery": True}}]})
        self.assertEqual(evidence["observed_recovery_windows"], 1)
        self.assertEqual(evidence["conditional_identity_denominator_windows"], 0)
        self.assertIsNone(metrics["short_same_task_identity_preserved_fraction"])
        self.assertIsNone(metrics["short_same_task_recovery_mean_s"])
        self.assertIsNone(metrics["short_same_task_recovery_p95_s"])

    def test_short_recovery_missing_report_differs_from_no_requested_window(self):
        for basic in ({}, {"occlusions": None}, {"occlusions": [None]}):
            metrics, evidence = supplement.short_same_task_recovery(basic)
            self.assertIsNone(evidence["short_requested_windows"])
            self.assertEqual(evidence["evidence_status"], "MISSING_OR_INVALID_OCCLUSION_REPORT")
            self.assertTrue(all(value is None for value in metrics.values()))
        metrics, evidence = supplement.short_same_task_recovery({"occlusions": []})
        self.assertEqual(evidence["short_requested_windows"], 0)
        self.assertEqual(evidence["evidence_status"], "NO_SHORT_REQUESTED_WINDOW_RECORDED")
        self.assertTrue(all(value is None for value in metrics.values()))

    def test_group_short_recovery_is_separate_from_explicit_new_task_and_keeps_applicability(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [{"name": name, "stage": 1, "target_class": "person", "estimator_method": "raw", "result": status}
                    for name, status in (("failed", "FAIL"), ("pending", "PENDING"))]
            source = summary(root / "summary.json", rows)
            write(root / "failed/offline_evaluation.json", {"occlusions": [{"kind": "short", "recovery_after_open_s": .25,
                "checks": {"identity_preserved_on_observed_recovery": True}}]})
            write(root / "failed/follow_dynamics.json", {"windows": [{"kind": "explicit_selection",
                "first_measured_confirmation_after_request_s": .8, "confirmation_censored": False}]})
            data = supplement.build(source, root)
            flight = data["flights"][0]
            self.assertEqual(flight["result"], "FAIL")
            self.assertEqual(flight["metrics"]["short_same_task_recovery_mean_s"], .25)
            self.assertEqual(flight["metrics"]["explicit_selection_confirmation_mean_s"], .8)
            group = next(iter(data["groups"].values()))
            evidence = group["short_same_task_recovery_evidence"]
            self.assertEqual(evidence["short_requested_windows"], 1)
            self.assertEqual(evidence["listed_flights"], 2)
            self.assertEqual(evidence["flights_missing_or_nonterminal"], 1)
            self.assertEqual(group["metrics"]["short_same_task_recovery_mean_s"]["valid_flights"], 1)
            self.assertEqual(group["metrics"]["short_same_task_recovery_mean_s"]["missing_flights"], 1)
            self.assertEqual(group["metric_evidence_status_counts"]["physical_retention_lower_bound"], {
                "NOT_APPLICABLE_NO_SELECTED_PHYSICAL_IDENTITY_TASK": 1, "NONTERMINAL": 1})
            self.assertIn("原任务短遮挡恢复条件分母", supplement.markdown(data))

    def test_missing_basic_report_and_nonapplicable_short_or_identity_tasks_have_distinct_statuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [{"name": name, "stage": 2, "target_class": "person", "scenario": scenario, "result": "FAIL"}
                    for name, scenario in (("no_short", "crossing"), ("missing", "crossing"), ("auto_unique", "auto_unique"))]
            source = summary(root / "summary.json", rows)
            write(root / "no_short/stage2_evaluation.json", {"result": "FAIL", "occlusions": []})
            write(root / "missing/online_state_accuracy_v2.json", {"schema_version": 2})
            write(root / "auto_unique/auto_unique_evaluation.json", {"result": "FAIL", "occlusions": []})
            data = supplement.build(source, root, include_state_frames=True)
            by_name = {row["name"]: row for row in data["flights"]}
            key = "short_same_task_recovery_mean_s"
            self.assertEqual(by_name["no_short"]["metric_evidence_statuses"][key], "NOT_APPLICABLE_NO_SHORT_REQUESTED_WINDOW")
            self.assertEqual(by_name["missing"]["metric_evidence_statuses"][key], "MISSING_OR_INVALID_BASIC_REPORT")
            self.assertEqual(by_name["auto_unique"]["metric_evidence_statuses"]["physical_retention_lower_bound"], "NOT_APPLICABLE_NO_SELECTED_PHYSICAL_IDENTITY_TASK")
            self.assertEqual(by_name["no_short"]["metric_evidence_statuses"]["short_shutter_predicted_position_rmse_m"], "NOT_APPLICABLE_NO_SHORT_REQUESTED_WINDOW")
            self.assertTrue(all(row["result"] == "FAIL" for row in data["flights"]))


if __name__ == "__main__":
    unittest.main()
