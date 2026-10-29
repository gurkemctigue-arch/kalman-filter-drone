"""Immutable JSON-only fixtures; no ROS, bags, simulator or real outcomes."""
from copy import deepcopy
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from tests import test_reliability_v4_runner as fixtures
from tests import test_reliability_v4_extensions as extensions

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("v4_lightweight_summary", ROOT / "scripts/summarize_reliability_v4.py")
summarizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summarizer)
v4 = fixtures.v4


def terminal(plan, trial, status="PASS", *, distance=.4, censored=False, reports=True):
    entries = []
    if reports:
        fake = fixtures.FakeCommands()
        for evaluation in trial["evaluations"]:
            execution = fake(evaluation["command"], Path(plan["frozen_root"]) / "fake_evaluation.log", Path(plan["frozen_root"]), 1.)
            path = Path(evaluation["report"])
            report = v4.load(path)
            if evaluation["kind"] == "navigation":
                report["whole_interval"]["metrics"]["base_link_distance_error_m"]["rmse"] = distance
                report["kf_navigation"].update(metrics={"kf_position_error_m": {"rmse": .2, "p95": .4},
                                                         "kf_velocity_error_mps": {"rmse": .1, "p95": .3}},
                                                  position_truth_coverage=.99, velocity_truth_coverage=.98)
                report["whole_interval"]["transients"]["base_link"]["distance"].update(
                    settling_time_s=None if censored else .2,
                    settled_through_interval_end=not censored, settling_right_censored=censored,
                    opposite_side_overshoot_m=.1)
            elif evaluation["kind"] == "surface_flight":
                report["detector"] = {"processed_fps_in_sim_time": 8., "inference_wall_s": {"mean": .04, "p95": .08},
                                      "acquisition_to_completed_sim_latency_s": {"mean": .1, "p95": .2}}
            elif evaluation["kind"] == "gimbal":
                report.update(metrics={"detected_center_normalized_error": {"rmse": .2},
                                       "true_image_horizon_error_rad": {"rmse": .03}},
                              geometry={"image_timestamp_tf_coverage": .9})
            elif evaluation["kind"] == "physical_identity":
                report["tasks"] = {"fixture-task": {"amodal_simulation_mot": {
                    "frames": 10, "gt_detections": 20, "predicted_detections": 15,
                    "hota": .6, "idf1": .7, "id_switches": 2}, "unoccluded_geometry_mot": {
                    "frames": 0, "gt_detections": 0, "predicted_detections": 0,
                    "hota": None, "idf1": None, "id_switches": 0}}}
            fixtures.write(path, report)
            entry = v4.read_evaluation(evaluation, execution, plan)
            if entry.get("error"):
                raise AssertionError(entry)
            entries.append(entry)
    record = {"status": status, "engineering_result": status, "evaluations": entries,
              "infrastructure_stop": status == "INFRASTRUCTURE_ERROR", "flight_exit_code": 0,
              "execution_status": "COMPLETED"}
    v4.finalize(plan, trial, record)


class ReliabilitySummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        extensions.extension_fixture(self.root)

    def core(self, *, groups=None, classes=None, seeds=None, suffix="summary_core"):
        return fixtures.plan(self.root, groups=groups, classes=classes, seeds=[4, 5] if seeds is None else seeds, suffix=suffix)

    def extension(self, **options):
        plan = extensions.make(self.root, **options)
        v4.persist_plan(plan)
        return plan

    def summarize(self, core, extension=None):
        return summarizer.summary(Path(core["output"]) / "plan.json",
                                  Path(extension["output"]) / "plan.json" if extension else None,
                                  resamples=128, seed=42)

    def test_pending_denominator_and_zero_are_not_missing(self):
        core = self.core()
        terminal(core, core["trials"][0], "FAIL", distance=0.)
        result = self.summarize(core)
        self.assertEqual(result["evaluation_status"], "PARTIAL_EXECUTION_RETAINED")
        self.assertEqual(result["cohorts"]["core"]["status_counts"], {"FAIL": 1, "PENDING": 1})
        value = result["groups"][0]["metrics"]["base_link_distance_rmse_m"]
        self.assertEqual((value["n"], value["n_missing"], value["mean"]), (1, 1, 0.))
        self.assertFalse(result["all_engineering_pass"])

    def test_metric_sample_counts_do_not_substitute_trials_for_error_samples(self):
        reports = {"navigation": {"control_jitter": {"velocity_command_delta_over_dt_mps2": {"rmse": .2, "count": 45}},
                                   "position_control_jitter": {"position_setpoint_delta_over_dt_mps": {"rmse": .3, "count": 12},
                                       "position_setpoint_second_difference_mps2": {"rmse": .4, "count": 10}},
                                   "kf_navigation": {"metrics": {"kf_position_error_m": {"rmse": None, "count": 0}}}}}
        counts = summarizer.metric_sample_counts(reports)
        self.assertEqual(counts["velocity_command_jitter_rms_mps2"], 45)
        self.assertEqual(counts["kf_position_rmse_m"], 0)
        self.assertEqual(counts["position_command_rate_rms_mps"], 12)
        self.assertEqual(counts["position_command_second_difference_rms_mps2"], 10)
        metrics, _ = summarizer.extract_metrics(reports)
        self.assertEqual(metrics["position_command_rate_rms_mps"], .3)
        self.assertEqual(metrics["position_command_second_difference_rms_mps2"], .4)
        self.assertIsNone(counts["navigation_valid_coverage"])
        self.assertIsNone(counts["image_to_first_command_sim_mean_s"])

    def test_operational_short_recovery_keeps_known_denominator_and_unobserved_distinct(self):
        windows = [{"kind": "short", "recovery_after_open_s": latency,
                    "checks": {"identity_preserved_on_observed_recovery": identity}}
                   for latency, identity in ((0., True), (.4, True), (.3, False), (.2, None),
                                             (None, None), (None, True), (None, True))]
        windows.append({"kind": "long", "recovery_after_open_s": 99.,
                        "checks": {"identity_preserved_on_observed_recovery": True}})
        metrics, evidence = summarizer.recovery_evidence({"surface_flight": {"occlusions": windows}})
        short = evidence["short_requested_shutter"]
        self.assertEqual(short["requested_windows"], 7)
        self.assertEqual(short["observed_recovery_windows"], 4)
        self.assertEqual(short["same_track_task_recovery_windows"], 2)
        self.assertEqual(short["changed_track_or_task_recovery_windows"], 1)
        self.assertEqual(short["known_identity_on_observed_recovery_windows"], 3)
        self.assertEqual(short["unknown_identity_on_observed_recovery_windows"], 1)
        self.assertEqual(short["unobserved_or_untimed_recovery_windows"], 3)
        self.assertEqual(short["identity_flag_without_valid_timing_windows"], 2)
        self.assertAlmostEqual(metrics["short_post_open_measured_recovery_observed_fraction"], 4 / 7)
        self.assertAlmostEqual(metrics["short_same_track_task_observed_recovery_fraction"], 2 / 7)
        self.assertAlmostEqual(metrics["short_same_track_task_recovery_fraction_given_known_recovery"], 2 / 3)
        self.assertAlmostEqual(metrics["short_same_track_task_recovery_mean_s"], .2)
        self.assertAlmostEqual(metrics["short_same_track_task_recovery_p95_s"], .38)
        self.assertIn("not independent physical identity", short["definition"])
        self.assertEqual(short["windows"][-1]["status"], "UNOBSERVED_OR_UNTIMED_NOT_FAILURE")
        counts = summarizer.metric_sample_counts({"surface_flight": {"occlusions": windows}})
        self.assertEqual(counts["short_same_track_task_recovery_mean_s"], 2)
        self.assertIsNone(counts["short_same_track_task_observed_recovery_fraction"])

    def test_signed_follow_error_uses_absolute_p95_and_original_sample_count(self):
        reports = {"navigation": {"whole_interval": {"metrics": {
            "base_link_distance_error_m": {"p95": -.1, "p95_absolute": 1.7, "count": 21},
            "base_link_height_error_m": {"p95": -.2, "p95_absolute": 2.3, "count": 19}}}}}
        metrics, _ = summarizer.extract_metrics(reports)
        self.assertEqual(metrics["base_link_distance_p95_m"], 1.7)
        self.assertEqual(metrics["base_link_height_p95_m"], 2.3)
        counts = summarizer.metric_sample_counts(reports)
        self.assertEqual(counts["base_link_distance_p95_m"], 21)
        self.assertEqual(counts["base_link_height_p95_m"], 19)
        del reports["navigation"]["whole_interval"]["metrics"]["base_link_distance_error_m"]["p95_absolute"]
        self.assertIsNone(summarizer.extract_metrics(reports)[0]["base_link_distance_p95_m"])

    def test_explicit_selection_confirmation_keeps_censoring_and_invalid_windows(self):
        windows = [{"kind": "explicit_selection", "start_s": 1., "end_s": 2.,
                    "first_measured_confirmation_after_request_s": latency, "confirmation_censored": flag}
                   for latency, flag in ((0., False), (None, True), (.2, None), (.2, True), (1.5, False))]
        metrics, evidence = summarizer.recovery_evidence({"navigation": {"windows": windows}})
        selections = evidence["explicit_selection"]
        self.assertEqual(selections["requested_windows"], 5)
        self.assertEqual(selections["observed_confirmation_windows"], 1)
        self.assertEqual(selections["confirmation_right_censored_windows"], 1)
        self.assertEqual(selections["missing_or_inconsistent_windows"], 3)
        self.assertEqual(selections["classified_confirmation_windows"], 2)
        self.assertEqual(metrics["explicit_selection_observed_confirmation_fraction"], .5)
        self.assertEqual(metrics["explicit_selection_observed_confirmation_mean_s"], 0.)
        self.assertEqual(selections["windows"][1]["status"], "RIGHT_CENSORED_NOT_FAILURE")
        self.assertIn("initial selection and reselection", selections["definition"])
        counts = summarizer.metric_sample_counts({"navigation": {"windows": windows}})
        self.assertEqual(counts["explicit_selection_observed_confirmation_mean_s"], 1)

    def test_missing_empty_and_unobserved_recovery_never_imply_zero_time_or_failure(self):
        missing_metrics, missing = summarizer.recovery_evidence({})
        self.assertTrue(all(value is None for value in missing_metrics.values()))
        self.assertIsNone(missing["short_requested_shutter"]["requested_windows"])
        empty_metrics, empty = summarizer.recovery_evidence({"surface_flight": {"occlusions": []}, "navigation": {"windows": []}})
        self.assertTrue(all(value is None for value in empty_metrics.values()))
        self.assertEqual(empty["short_requested_shutter"]["requested_windows"], 0)
        metrics, evidence = summarizer.recovery_evidence({"surface_flight": {"occlusions": [{"kind": "short"}]},
            "navigation": {"windows": [{"kind": "explicit_selection", "start_s": 1., "end_s": 2.,
                "first_measured_confirmation_after_request_s": None, "confirmation_censored": True}]}})
        self.assertIsNone(metrics["short_same_track_task_recovery_fraction_given_known_recovery"])
        self.assertIsNone(metrics["short_same_track_task_observed_recovery_fraction"])
        self.assertIsNone(metrics["short_post_open_measured_recovery_observed_fraction"])
        self.assertIsNone(metrics["short_same_track_task_recovery_mean_s"])
        self.assertEqual(metrics["explicit_selection_observed_confirmation_fraction"], 0.)
        self.assertIsNone(metrics["explicit_selection_observed_confirmation_mean_s"])
        grouped = summarizer.grouped_recovery_evidence([{"recovery_evidence": value} for value in (missing, empty, evidence)])
        self.assertEqual(grouped["short_requested_shutter"]["requested_windows"], 1)
        self.assertEqual(grouped["short_requested_shutter"]["source_status_counts"],
            {"MISSING_OR_MALFORMED_SOURCE": 1, "NO_APPLICABLE_WINDOWS": 1, "AVAILABLE": 1})
        self.assertIsNone(summarizer.grouped_recovery_evidence([{"recovery_evidence": missing}])["explicit_selection"]["requested_windows"])
        for invalid in (-1., True, float("nan")):
            invalid_metrics, invalid_evidence = summarizer.recovery_evidence({"surface_flight": {"occlusions": [
                {"kind": "short", "recovery_after_open_s": invalid}]}})
            self.assertIsNone(invalid_metrics["short_post_open_measured_recovery_observed_fraction"])
            self.assertEqual(invalid_evidence["short_requested_shutter"]["missing_or_invalid_timing_windows"], 1)

    def test_native_navigation_detector_and_censoring_use_new_schema(self):
        core = self.core(seeds=[4])
        terminal(core, core["trials"][0], censored=True)
        result = self.summarize(core)
        row = result["trials"][0]
        self.assertEqual(row["metrics"]["kf_position_rmse_m"], .2)
        self.assertEqual(row["metrics"]["kf_velocity_rmse_mps"], .1)
        self.assertEqual(row["metrics"]["physical_follow_truth_coverage"], 1.)
        self.assertEqual(row["metrics"]["detector_processed_sim_fps"], 8.)
        self.assertEqual(row["metrics"]["image_to_detector_sim_mean_s"], .1)
        self.assertEqual(row["evaluation_status"]["source_clock"], "PASS")
        self.assertEqual(row["evaluation_status"]["native_startup"], "PASS")
        self.assertIsNone(row["metrics"]["base_link_distance_settling_s"])
        self.assertEqual(row["settling"]["distance"], "RIGHT_CENSORED")
        self.assertEqual(result["groups"][0]["settling"]["distance"], {"RIGHT_CENSORED": 1})

    def test_terminal_execution_never_changes_failed_or_missing_evidence_verdict(self):
        core = self.core(seeds=list(range(4, 10)))
        statuses = ["PASS", "FAIL", "INTERRUPTED", "INFRASTRUCTURE_ERROR", "INCOMPLETE_EVIDENCE", "EVALUATION_PENDING"]
        for trial, status in zip(core["trials"], statuses):
            terminal(core, trial, status, reports=False)
        result = self.summarize(core)
        self.assertEqual(result["evaluation_status"], "ALL_PLANNED_SLOTS_TERMINAL")
        self.assertEqual([row["status"] for row in result["trials"]], statuses)
        self.assertEqual(result["cohorts"]["core"]["status_category_counts"]["INFRA"], 1)
        self.assertEqual(result["cohorts"]["core"]["status_category_counts"]["INCOMPLETE"], 1)
        self.assertEqual(result["cohorts"]["core"]["report_issues_slots"], 6)
        self.assertTrue(all(row["metrics"]["base_link_distance_rmse_m"] is None for row in result["trials"]))
        self.assertFalse(result["all_engineering_pass"])

    def test_running_marker_is_not_a_completed_or_measured_trial(self):
        core = self.core(seeds=[4])
        trial = core["trials"][0]
        fixtures.write(v4.record_path(core, trial, "started.json"), {"id": trial["id"], "plan_sha256": core["plan_sha256"]})
        result = self.summarize(core)
        self.assertEqual(result["trials"][0]["status"], "RUNNING")
        self.assertEqual(result["cohorts"]["core"]["terminal_slots"], 0)
        self.assertIsNone(result["trials"][0]["metrics"]["kf_position_rmse_m"])

    def test_gimbal_and_task_mot_metrics_never_turn_empty_geometry_into_zero(self):
        core = self.core(groups=["stage3_multi_active"], seeds=[4])
        terminal(core, core["trials"][0])
        metrics = self.summarize(core)["trials"][0]["metrics"]
        self.assertEqual(metrics["gimbal_detected_center_normalized_rmse"], .2)
        self.assertEqual(metrics["gimbal_true_horizon_rmse_rad"], .03)
        self.assertEqual(metrics["physical_task_time_known_coverage"], .6)
        self.assertEqual(metrics["task_mean_amodal_simulation_mot_id_switches"], 2)
        self.assertEqual(metrics["task_mean_amodal_simulation_mot_hota"], .6)
        self.assertIsNone(metrics["task_mean_unoccluded_geometry_mot_id_switches"])

    def test_position_velocity_pairs_keep_failure_metrics_and_success_subset(self):
        core = self.core(groups=["stage1_velocity", "stage1_position"])
        for trial in core["trials"]:
            position = trial["group"] == "stage1_position"
            distance = ({4: .8, 5: 1.1} if position else {4: .4, 5: .5})[trial["seed"]]
            status = "FAIL" if position and trial["seed"] == 5 else "PASS"
            terminal(core, trial, status, distance=distance)
        result = self.summarize(core)
        comparison = result["paired_comparisons"][0]
        self.assertEqual(comparison["planned_pairs_in_matrix"], 2)
        metric = comparison["metrics"]["base_link_distance_rmse_m"]
        self.assertEqual(metric["all_finite_pairs"]["n"], 2)
        self.assertAlmostEqual(metric["all_finite_pairs"]["mean"], .5)
        self.assertIsNotNone(metric["all_finite_pairs"]["ci95"])
        self.assertEqual(metric["both_pass_pairs"]["n"], 1)
        self.assertAlmostEqual(metric["both_pass_pairs"]["mean"], .4)
        self.assertIsNone(metric["both_pass_pairs"]["ci95"])
        self.assertEqual(metric["pairs"][1]["left_status"], "FAIL")

    def test_active_midpoint_pairs_by_same_class_and_seed(self):
        core = self.core(groups=["stage3_midpoint", "stage3_active"], classes=["person", "car"], seeds=[4])
        for trial in core["trials"]:
            terminal(core, trial, distance=.2 if trial["group"] == "stage3_active" else .7)
        comparisons = self.summarize(core)["paired_comparisons"]
        self.assertEqual({row["target_class"] for row in comparisons}, {"person", "car"})
        for comparison in comparisons:
            self.assertAlmostEqual(comparison["metrics"]["base_link_distance_rmse_m"]["all_finite_pairs"]["mean"], -.5)

    def test_extensions_use_declared_clean_reference_and_preserve_missing_pairs(self):
        core = self.core(seeds=[4, 5])
        extension = self.extension(conditions=["latency"], classes=["person"], seeds=[4, 5])
        terminal(core, core["trials"][0], distance=.2)
        terminal(extension, extension["trials"][0], "FAIL", distance=.7)
        result = self.summarize(core, extension)
        comparison = result["paired_comparisons"][0]
        metric = comparison["metrics"]["base_link_distance_rmse_m"]
        self.assertEqual((metric["all_finite_pairs"]["n"], metric["all_finite_pairs"]["n_missing"]), (1, 1))
        self.assertAlmostEqual(metric["all_finite_pairs"]["mean"], .5)
        self.assertEqual(metric["both_pass_pairs"]["n"], 0)
        self.assertEqual(metric["pairs"][1]["right_status"], "PENDING")
        self.assertEqual(result["cohorts"]["core"]["planned_slots"], 2)
        self.assertEqual(result["cohorts"]["extension"]["planned_slots"], 2)

    def test_full_synthetic_matrices_keep_120_and_160_separate(self):
        seeds = list(range(10, 20))  # Development fixtures, never consume held-out seeds.
        core = self.core(groups=list(v4.GROUPS), classes=list(v4.CLASSES), seeds=seeds)
        extension = self.extension(seeds=seeds)
        result = self.summarize(core, extension)
        self.assertEqual(result["cohorts"]["core"]["planned_slots"], 120)
        self.assertEqual(result["cohorts"]["extension"]["planned_slots"], 160)
        self.assertEqual(len(result["trials"]), 280)
        self.assertEqual(len(result["paired_comparisons"]), 20)
        self.assertEqual(result["evaluation_status"], "PARTIAL_EXECUTION_RETAINED")
        self.assertTrue(all(group["planned_slots"] == 10 for group in result["groups"]))

    def test_plan_slot_and_report_tampering_are_rejected(self):
        for defect in ("plan", "slot", "report"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixtures.fixture(root)
                core = fixtures.plan(root, seeds=[4])
                terminal(core, core["trials"][0])
                target = (Path(core["output"]) / "plan.json" if defect == "plan" else
                          v4.record_path(core, core["trials"][0]) if defect == "slot" else
                          Path(core["trials"][0]["evaluations"][-1]["report"]))
                value = v4.load(target)
                value["TAMPER"] = True
                fixtures.write(target, value)
                with self.assertRaises(ValueError):
                    self.summarize(core)

    def test_wrong_cohort_and_changed_model_bindings_are_rejected(self):
        core = self.core(seeds=[4])
        extension = self.extension(conditions=["latency"], classes=["person"], seeds=[4])
        with self.assertRaisesRegex(ValueError, "wrong cohort"):
            summarizer.summary(Path(extension["output"]) / "plan.json", resamples=128)
        extension["model_hashes"]["models/yolo11n.pt"] = "a" * 64
        extension["plan_sha256"] = v4.digest(extension, ("plan_sha256",))
        fixtures.write(Path(extension["output"]) / "plan.json", extension)
        with self.assertRaisesRegex(ValueError, "model binding differs"):
            self.summarize(core, extension)

    def test_reference_requires_the_actual_core_artifact_and_keeps_development_failures(self):
        core = self.core(seeds=[4])
        extension = self.extension(conditions=["latency"], classes=["person"], seeds=[4])
        path = Path(core["output"]) / "plan.json"
        explicit_fixture = deepcopy(extension)
        explicit_fixture["mode"] = "EXTENSION_FORMAL"  # Binding function only, not a runnable/validated formal plan.
        with self.assertRaisesRegex(ValueError, "actual frozen"):
            summarizer.require_reference_binding(explicit_fixture, core, path)
        explicit_fixture["core_reference_binding"] = {"path": str(path), "sha256": v4.sha(path),
            "plan_sha256": core["plan_sha256"], "reference_ids": sorted({trial["comparison_reference_id"] for trial in extension["trials"]})}
        summarizer.require_reference_binding(explicit_fixture, core, path)
        explicit_fixture["core_reference_binding"]["plan_sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "actual frozen"):
            summarizer.require_reference_binding(explicit_fixture, core, path)
        failures = [{"slot_id": "DEVELOPMENT_FIXTURE_ONLY", "failures": ["short_prediction_missing"]}]
        explicit_fixture["extension_protocol_binding"]["protocol"]["development_readiness"] = {"evidence": {"known_algorithm_failures": failures}}
        self.assertEqual(summarizer.extension_context(explicit_fixture)["development_known_algorithm_failures"], failures)

    def test_publication_uses_new_directory_null_csv_and_escaped_html(self):
        core = self.core(seeds=[4])
        result = self.summarize(core)
        output = self.root / "new_summary"
        summarizer.write_report(result, output)
        self.assertEqual({path.name for path in output.iterdir()}, {"summary.json", "trials.csv", "group_metrics.csv", "paired_differences.csv", "paired_trial_differences.csv", "index.html"})
        with (output / "trials.csv").open(encoding="utf-8-sig", newline="") as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row["base_link_distance_rmse_m"], "")
        self.assertIn("PARTIAL_EXECUTION_RETAINED", (output / "index.html").read_text(encoding="utf-8"))
        changed = deepcopy(result)
        changed["trials"][0]["group"] = "<script>alert(1)</script>"
        self.assertNotIn("<script>", summarizer.render_html(changed))
        with self.assertRaises(FileExistsError):
            summarizer.write_report(result, output)

    def test_changed_small_input_during_summary_prevents_publication(self):
        core = self.core(seeds=[4])
        result = self.summarize(core)
        with (Path(core["output"]) / "plan.json").open("a", encoding="utf-8") as stream:
            stream.write(" ")
        with self.assertRaisesRegex(ValueError, "changed during"):
            summarizer.write_report(result, self.root / "refused_output")
        self.assertFalse((self.root / "refused_output").exists())

    def test_invalid_stats_do_not_create_zero_or_frame_weighted_trials(self):
        value = summarizer.stats([1., None, False, float("nan"), 3.])
        self.assertEqual((value["n"], value["n_missing"], value["mean"]), (2, 3, 2.))
        self.assertAlmostEqual(value["sample_sd"], 2 ** .5)
        for bad in (0, True, 100001):
            with self.assertRaises(ValueError):
                summarizer.summary("unused.json", resamples=bad)
        self.assertIsNone(summarizer.paired_estimate([None, 1., 1.], 128, 42)["ci95"])

    def test_invalid_negative_rmse_and_coverage_are_missing_and_optional_reports_are_na(self):
        reports = {"navigation": {"whole_interval": {"metrics": {"base_link_distance_error_m": {"rmse": -1.}}},
                                   "kf_navigation": {"valid_state_coverage": 1.1}}}
        metrics, _ = summarizer.extract_metrics(reports)
        self.assertIsNone(metrics["base_link_distance_rmse_m"])
        self.assertIsNone(metrics["navigation_valid_coverage"])
        core = self.core(seeds=[4])
        result = self.summarize(core)
        self.assertEqual(result["groups"][0]["evaluator_status_counts"]["gimbal"], {"NOT_APPLICABLE": 1})


if __name__ == "__main__":
    unittest.main()
