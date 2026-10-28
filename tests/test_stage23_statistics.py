"""Paired CIs must retain failures and never inflate independent repeats."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_stage23_matrix as matrix
import summarize_stage23_matrix as statistics


def planned():
    return {"plan_sha256": "pre-registered", "slots": [
        {"trial": trial, "status": "PENDING"} for trial in matrix.plan_trials("study", list(range(10)))]}


def record_trial(manifest, root, seed, mode, center, *, status="PASS", category="person", missing_flight=False):
    slot = next(slot for slot in manifest["slots"] if slot["trial"]["stage"] == 3
                and slot["trial"]["seed"] == seed and slot["trial"]["gimbal_mode"] == mode
                and slot["trial"]["target_class"] == category)
    slot["status"] = status
    directory = root / "results" / slot["trial"]["name"]
    directory.mkdir(parents=True)
    gimbal = {"schema_version": 1, "mode": mode, "result": "PASS" if status == "PASS" else "FAIL_OR_INCOMPLETE",
              "centering_source": "all_detections_in_single_target_world",
              "metrics": {"detected_center_normalized_error": {"rmse": center},
                          "true_image_horizon_error_rad": {"rmse": center/10}},
              "physical_feedback": {"span_rad": [.1, .2, .3]},
              "interval": {"metric_start_s": 10, "recorded_end_s": 50}}
    flight = {"schema_version": 3, "target_class": category, "acceptance": {"result": "PASS" if status == "PASS" else "FAIL"},
              "controller": {"estimated_horizontal_distance_error_m": {"rmse": center*2}},
              "flight_evidence": {"vehicle_speed_mps": {"mean": .5, "rmse": .6}},
              "interval": {"start_s": 10, "recorded_end_s": 50}}
    slot["evaluations"] = []
    for kind, report in (("gimbal", gimbal), ("flight", flight)):
        path = directory / statistics.FILES[kind]
        if kind != "flight" or not missing_flight:
            path.write_text(json.dumps(report), encoding="utf-8")
        slot["evaluations"].append({"kind": kind, "report": str(path), "returncode": 0,
                                    "result": "PASS" if status == "PASS" else "FAIL"})
    return slot


def add_pair(manifest, root, seed, midpoint, active, **kwargs):
    first = record_trial(manifest, root, seed, "midpoint", midpoint)
    second = record_trial(manifest, root, seed, "active", active, **kwargs)
    return first, second


class Stage23StatisticsTests(unittest.TestCase):
    def test_default_bootstrap_is_10k_seed_pairs_and_single_pair_has_no_ci(self):
        result = statistics.bootstrap_mean([-1.])
        self.assertEqual(result["bootstrap_resamples"], 10_000)
        self.assertEqual(result["seed_pair_count"], 1)
        self.assertEqual(result["mean_active_minus_midpoint"], -1)
        self.assertIsNone(result["ci95_percentile"])
        self.assertFalse(result["recommended_ten_seed_pairs_met"])

    def test_bootstrap_ci_is_reproducible_and_samples_pair_differences(self):
        first = statistics.bootstrap_mean([-2., -1., 0., 1.], resamples=10_000, seed=5)
        second = statistics.bootstrap_mean([-2., -1., 0., 1.], resamples=10_000, seed=5)
        self.assertEqual(first, second)
        self.assertEqual(first["mean_active_minus_midpoint"], -.5)
        self.assertEqual(first["seed_pair_count"], 4)
        self.assertLessEqual(first["ci95_percentile"][0], -.5)
        self.assertGreaterEqual(first["ci95_percentile"][1], -.5)
        with self.assertRaises(ValueError):
            statistics.bootstrap_mean([float("nan")])

    def test_failed_measurements_are_separate_and_failure_denominator_is_all_66(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = planned()
            add_pair(manifest, root, 0, 2., 1.)
            add_pair(manifest, root, 1, 2., 8., status="FAIL")
            report = statistics.build_report(manifest, root, resamples=200)
            outcomes = report["outcomes"]["all_planned_slots"]
            self.assertEqual(outcomes["planned_slot_denominator"], 66)
            self.assertEqual(outcomes["failed_or_interrupted_slots"], 1)
            self.assertEqual(outcomes["failure_fraction_of_all_planned_slots"], 1/66)
            self.assertEqual(outcomes["pending_slots"], 62)
            cohorts = report["stage3_paired_comparisons"]["person"]["metrics"]["image_center_rmse"]
            self.assertEqual(cohorts["all_observed_pairs"]["mean_active_minus_midpoint"], 2.5)
            self.assertEqual(cohorts["all_observed_pairs"]["seed_pair_count"], 2)
            self.assertEqual(cohorts["both_successful_pairs"]["mean_active_minus_midpoint"], -1.)
            self.assertEqual(cohorts["failed_or_incomplete_observed_pairs"]["mean_active_minus_midpoint"], 6.)
            self.assertEqual(len(report["seed_pairs"]), 20)

    def test_seed_pair_with_different_resources_is_rejected_not_unpaired_pooled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = planned()
            _, active = add_pair(manifest, root, 0, 2., 1.)
            active["trial"]["inference_threads"] = 7
            report = statistics.build_report(manifest, root, resamples=20)
            pair = next(row for row in report["seed_pairs"] if row["target_class"] == "person" and row["seed"] == 0)
            self.assertFalse(pair["compatible"])
            self.assertIn("inference_threads", pair["issues"][0])
            self.assertIsNone(pair["differences"]["image_center_rmse"]["active_minus_midpoint"])

    def test_missing_report_is_not_zero_and_declared_pass_remains_unverified(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = planned()
            add_pair(manifest, root, 0, 2., 1., missing_flight=True)
            report = statistics.build_report(manifest, root, resamples=20)
            outcomes = report["outcomes"]["all_planned_slots"]
            self.assertEqual(outcomes["unverified_declared_passes"], 1)
            metric = report["stage3_paired_comparisons"]["person"]["metrics"]["estimated_follow_distance_rmse_m"]
            self.assertEqual(metric["all_observed_pairs"]["seed_pair_count"], 0)
            self.assertIsNone(metric["all_observed_pairs"]["mean_active_minus_midpoint"])

    def test_manifest_pending_does_not_adopt_existing_unreferenced_reports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = planned()
            slot = record_trial(manifest, root, 0, "active", 1.)
            slot.pop("evaluations")
            slot["status"] = "PENDING"
            loaded = statistics.load_slot(slot, root)
            self.assertIsNone(loaded["metrics"]["image_center_rmse"])
            self.assertFalse(loaded["verified_pass"])

    def test_missing_jitter_is_explicit_and_speed_rms_is_not_called_jitter_or_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = planned()
            add_pair(manifest, root, 0, 2., 1.)
            report = statistics.build_report(manifest, root, resamples=20)
            self.assertIn("control_command_jitter", report["requested_metrics_unavailable"])
            self.assertFalse(any("jitter" in row["name"] for row in report["metric_definitions"]))
            definition = next(row for row in report["metric_definitions"] if row["name"] == "vehicle_speed_rms_mps")
            self.assertIn("not speed RMSE", definition["scope"])
            self.assertIsNone(definition["preferred_direction"])

    def test_relocated_reports_use_only_slot_references_and_keep_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = planned()
            slot = record_trial(manifest, root, 0, "active", 1.)
            for entry in slot["evaluations"]:
                entry["report"] = "/old/root/results/old/" + Path(entry["report"]).name
            loaded = statistics.load_slot(slot, root)
            self.assertTrue(loaded["verified_pass"])
            self.assertTrue(all(item["relocated"] for item in loaded["report_provenance"].values()))
            self.assertTrue(all(len(item["sha256"]) == 64 for item in loaded["report_provenance"].values()))

    def test_malformed_or_wrong_schema_report_is_recorded_not_crash_or_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = planned()
            slot = record_trial(manifest, root, 0, "active", 1.)
            path = Path(slot["evaluations"][0]["report"])
            for raw in ("[]", "{broken", '{"schema_version": 2}'):
                path.write_text(raw, encoding="utf-8")
                loaded = statistics.load_slot(slot, root)
                self.assertFalse(loaded["verified_pass"])
                self.assertTrue(loaded["report_errors"])
                self.assertIsNone(loaded["metrics"]["image_center_rmse"])

    def test_summary_exports_every_planned_pair_including_unavailable_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = statistics.build_report(planned(), root, resamples=20)
            statistics.save_report(report, root / "statistics")
            parsed = json.loads((root / "statistics/statistics.json").read_text(encoding="utf-8"))
            self.assertEqual(len(parsed["seed_pairs"]), 20)
            csv_lines = (root / "statistics/seed_pair_differences.csv").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(csv_lines), 1 + 20 * len(statistics.METRICS))
            self.assertEqual(parsed["outcomes"]["all_planned_slots"]["pending_slots"], 66)


if __name__ == "__main__":
    unittest.main()
