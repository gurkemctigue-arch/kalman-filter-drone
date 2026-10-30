"""Behavioral contracts for the supplementary JSON-only task appendix."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("task_phase_appendix_v4",
    Path(__file__).resolve().parents[1] / "scripts/analyze_task_phases_v4.py")
appendix = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(appendix)


def fixture():
    """75 s task plus real-grid pre-FOLLOW and partial recording-tail cells."""
    follow, end, cutoff = 10., 85.2, 10.2
    rows = []
    for index in range(753):
        stamp = follow + index * .1
        valid = not 35.8 <= stamp < 42.2
        row = {"time_s": stamp, "navigation_valid": valid,
            "navigation_state": 1 if valid else 3, "navigation_reason": "valid" if valid else "lost",
            "active": valid, "target_uuid": "first" if stamp < 42.1 else "second",
            "reference_task_uuid": "first" if stamp < 42.1 else "second",
            "expected_physical_id": "actor0", "base_link_distance_error_m": 1. if stamp < 55. else 2.,
            "base_link_height_error_m": .2, "model_origin_distance_error_m": 1.,
            "model_origin_height_error_m": -.04}
        if index == 752:
            row.update(base_link_distance_error_m=None, base_link_height_error_m=None,
                model_origin_distance_error_m=None, model_origin_height_error_m=None)
        if stamp >= cutoff - 1e-9 and valid:
            row.update(kf_position_error_m=.3, kf_velocity_error_mps=.1)
        rows.append(row)
    report = {"schema_version": 1, "evaluation_status": "RECORDED_WITH_CENSORED_FAILURES",
        "evaluation_source": {"script": "/frozen/evaluator.py", "script_sha256": "a" * 64},
        "interval": {"start_s": follow, "end_s": end, "navigation_evaluation_start_s": cutoff, "sample_period_s": .1},
        "whole_interval": {"scheduled_samples": 753, "matched_truth_samples": 752,
            "metrics": {key: appendix.metrics(row.get(key) for row in rows) for key in appendix.METRICS[:4]}},
        "kf_navigation": {"counts": {"scheduled_samples": 751,
            "valid_navigation_samples": sum(row["navigation_valid"] for row in rows[2:])},
            "metrics": {key: appendix.metrics(row.get(key) for row in rows) for key in appendix.METRICS[4:]}}}
    start, identity_end = 9.95, 85.28
    timeline = []
    total = 754
    for index in range(total):
        left = start + index * .1
        outcome = "unknown" if index in {0, 321, 753} else "wrong" if index == 450 else "correct"
        timeline.append({"time_s": left, "end_s": min(identity_end, start + (index + 1) * .1),
            "outcome": outcome, "reason": {"correct": "all_observed_identity_evidence_correct",
                "wrong": "observed_wrong_physical_actor", "unknown": "no_identity_evidence_in_time_cell"}[outcome],
            "target_uuid": "first" if left < 42.1 else "second", "identity_evidence_frames": 0 if outcome == "unknown" else 1})
    identity = {"schema_version": 1, "evaluation_status": "RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS",
        "conservative_task_time_identity": {"schema_version": 1, "sample_period_s": .1,
            "coverage_basis": "fixed_10hz_request_to_recorded_clock_end",
            "interval": {"start_s": start, "end_s": identity_end}, "scheduled_samples": total,
            "correct": total - 4, "wrong": 1, "unknown": 3, "timeline": timeline,
            "tasks": {"first": {"request_time_s": start, "confirmation_time_s": 9.98},
                      "second": {"request_time_s": 42.1, "confirmation_time_s": 42.18}}},
        "selected_identity_timeline": [{"time_s": 9.97, "target_uuid": "first", "status": "NOT_OBSERVED",
            "matching": {"reason": "no_fresh_selected_detection"}}]}
    events = [{"time_s": 10., "kind": "phase", "phase": "FOLLOW"},
        {"time_s": 22., "kind": "shutter", "request_id": 1, "active": True},
        {"time_s": 22.25, "kind": "shutter", "request_id": 2, "active": False},
        {"time_s": 22.28, "kind": "shutter_hold_finished", "name": "short", "close_request_id": 1, "open_request_id": 2},
        {"time_s": 35., "kind": "shutter", "request_id": 3, "active": True},
        {"time_s": 38.05, "kind": "shutter", "request_id": 4, "active": False},
        {"time_s": 38.1, "kind": "shutter_hold_finished", "name": "long", "close_request_id": 3, "open_request_id": 4},
        {"time_s": 42.1, "kind": "explicit_reselection_requested", "target_uuid": "second"},
        {"time_s": 42.18, "kind": "explicit_reselection_confirmed", "target_uuid": "second"}]
    summary = {"follow_start_s": follow, "end_sim_s": 85.05}
    return report, rows, identity, summary, events


def write_fixture(directory, *, mode="specified"):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    report, rows, identity, summary, events = fixture()
    paths = {}
    for name, content in (("identity", identity), ("summary", summary)):
        path = directory / (name + ".json")
        path.write_text(json.dumps(content, allow_nan=False), encoding="utf-8")
        paths[name] = path
    report["physical_identity_sha256"] = appendix.file_sha(paths["identity"]) if mode == "specified" else None
    path = directory / "navigation.json"
    path.write_text(json.dumps(report, allow_nan=False), encoding="utf-8")
    paths["navigation"] = path
    for name, content in (("frames", rows), ("telemetry", events)):
        path = directory / (name + ".jsonl")
        path.write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in content), encoding="utf-8")
        paths[name] = path
    paths["output"] = directory / "appendix"
    args = ["--mode", mode, "--navigation-report", str(paths["navigation"]),
            "--navigation-frames", str(paths["frames"]), "--summary", str(paths["summary"]),
            "--telemetry", str(paths["telemetry"]), "--occlusions", "expected",
            "--output-dir", str(paths["output"])]
    if mode == "specified":
        args.extend(("--identity-report", str(paths["identity"])))
    return args, paths


class TaskPhaseAnalysisTests(unittest.TestCase):
    def analyze(self, *, mode="specified", change=None):
        report, rows, identity, summary, events = fixture()
        if change:
            change(report, rows, identity, summary, events)
        inputs = appendix.Inputs()
        inputs.bindings["identity_report"] = {"sha256": "b" * 64}
        report["physical_identity_sha256"] = "b" * 64
        result = appendix.analyze(inputs, mode, report, rows, identity if mode == "specified" else None,
                                  summary, events, occlusions="expected")
        return result

    def test_two_views_conserve_every_primary_denominator_and_error_energy(self):
        result = self.analyze()
        self.assertEqual(result["status"], "COMPLETE_AUXILIARY_ANALYSIS")
        self.assertEqual(result["conservation"]["status"], "PASS")
        self.assertTrue(all(result["conservation"]["checks"].values()))
        self.assertEqual(result["navigation"]["whole"]["physical_scheduled_samples"], 753)
        self.assertEqual(result["navigation"]["whole"]["navigation_scheduled_samples"], 751)
        self.assertEqual(result["identity"]["whole"]["scheduled_cells"], 754)
        self.assertGreater(result["bands"]["pre_follow"]["identity"]["scheduled_cells"], 0)
        self.assertGreater(result["bands"]["after_75_recording_tail"]["identity"]["unknown"], 0)

    def test_left_endpoint_assignment_keeps_wrong_and_partial_boundary_cells(self):
        result = self.analyze()
        first = result["bands"]["follow_0_45"]["identity"]
        second = result["bands"]["follow_45_75"]["identity"]
        self.assertEqual(first["wrong"], 1)
        self.assertEqual(second["wrong"], 0)
        self.assertGreater(first["crosses_boundary_cells"], 0)
        self.assertEqual(result["identity"]["whole"]["wrong"], 1)
        self.assertAlmostEqual(result["identity"]["whole"]["cell_duration_s"], 85.28 - 9.95)
        self.assertEqual(result["bands"]["follow_45_75"]["navigation"]["physical_scheduled_samples"], 301)

    def test_event_partition_uses_original_task_confirmations_and_reports_resolution(self):
        result = self.analyze()
        self.assertEqual(result["event_partition"]["status"], "RESOLVED_RECORDED_EVENTS")
        self.assertAlmostEqual(result["event_partition"]["details"]["confirmation_delay_s"], .08)
        self.assertAlmostEqual(result["event_partition"]["details"]["short_recovery_s"], 22.3)
        self.assertIn("recording_tail", result["phases"])
        self.assertIn("confirmed_first_5s", result["phases"])
        self.assertEqual(result["navigation"]["post_confirmation_continuity"]["first_5s_scheduled_points"], 50)

    def test_initial_confirmation_after_follow_is_retained_as_its_actual_phase(self):
        def change(report, rows, identity, summary, events):
            identity["conservative_task_time_identity"]["tasks"]["first"]["confirmation_time_s"] = 10.1
        result = self.analyze(change=change)
        self.assertEqual(result["event_partition"]["status"], "RESOLVED_RECORDED_EVENTS")
        self.assertEqual(result["phases"]["initial_confirmation"]["navigation"]["physical_scheduled_samples"], 1)

    def test_monitor_tolerance_does_not_invent_a_complete_five_second_recording(self):
        def change(report, rows, identity, summary, events):
            identity["conservative_task_time_identity"]["tasks"]["second"]["confirmation_time_s"] = 80.25
            events[-1]["time_s"] = 80.25
            summary["end_sim_s"] = 85.3
        result = self.analyze(change=change)
        self.assertEqual(result["event_partition"]["status"], "UNRESOLVED_EVENTS")
        self.assertIn("five-second", result["event_partition"]["reasons"][0])

    def test_missing_or_reversed_events_are_unresolved_without_dropping_any_samples(self):
        for change in (lambda r, n, i, s, e: e.pop(),
                       lambda r, n, i, s, e: e.pop(3),
                       lambda r, n, i, s, e: e.reverse()):
            result = self.analyze(mode="auto_unique", change=change)
            self.assertEqual(result["status"], "INCOMPLETE_EVIDENCE")
            self.assertEqual(result["event_partition"]["status"], "UNRESOLVED_EVENTS")
            self.assertEqual(result["phases"]["UNRESOLVED_EVENTS"]["navigation"]["physical_scheduled_samples"], 753)
            self.assertEqual(result["conservation"]["status"], "PASS")

    def test_unique_instance_identity_is_na_and_never_fabricated_perfect_coverage(self):
        result = self.analyze(mode="auto_unique")
        self.assertEqual(result["identity"]["status"], "NOT_APPLICABLE")
        self.assertNotIn("whole", result["identity"])
        self.assertTrue(all(group["identity"] is None for group in result["bands"].values()))

    def test_wrong_or_missing_sidecars_cannot_rewrite_primary_metrics(self):
        changes = (lambda r, n, i, s, e: n.pop(10),
                   lambda r, n, i, s, e: n[5].update(base_link_distance_error_m=999.),
                   lambda r, n, i, s, e: n[5].update(time_s=True),
                   lambda r, n, i, s, e: n[5].update(kf_position_error_m=float("nan")))
        for change in changes:
            result = self.analyze(change=change)
            self.assertEqual(result["status"], "INCOMPLETE_EVIDENCE")
            self.assertIsNone(result["navigation"])

    def test_unknown_overlap_flags_do_not_exonerate_unknown_or_wrong_outcomes(self):
        result = self.analyze()
        first = result["bands"]["pre_follow"]["identity"]
        self.assertEqual(first["unknown"], 1)
        self.assertEqual(first["overlap_flags_unknown_cells"]["no_fresh_selected"], 1)
        self.assertTrue(any("Snapshot missing" in item and "UNAVAILABLE" in item for item in result["limitations"]))

    def test_cli_binds_actual_bytes_writes_reviewable_outputs_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            args, paths = write_fixture(Path(temporary) / "inputs")
            self.assertEqual(appendix.main(args), 0)
            output = paths["output"]
            manifest = json.loads((output / "input_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["inputs"]["navigation_frames"]["sha256"], appendix.file_sha(paths["frames"]))
            self.assertEqual(manifest["analyzer_source"]["sha256"], appendix.file_sha(Path(appendix.__file__)))
            saved = manifest.pop("manifest_sha256")
            self.assertEqual(saved, appendix.canonical(manifest))
            for name in ("analysis.json", "segments.csv", "index.html"):
                self.assertTrue((output / name).stat().st_size > 0)
            original = appendix.file_sha(output / "analysis.json")
            with self.assertRaises(SystemExit):
                appendix.main(args)
            self.assertEqual(original, appendix.file_sha(output / "analysis.json"))

    def test_missing_input_yields_incomplete_output_with_null_navigation(self):
        with tempfile.TemporaryDirectory() as temporary:
            args, paths = write_fixture(Path(temporary) / "inputs")
            paths["frames"].unlink()
            self.assertEqual(appendix.main(args), 2)
            result = json.loads((paths["output"] / "analysis.json").read_text(encoding="utf-8"))
            self.assertIsNone(result["navigation"])
            self.assertEqual(result["bands"], {})
            self.assertTrue(result["errors"])

    def test_nonfinite_json_exponents_and_constants_are_rejected_even_in_unused_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            for token in ("NaN", "Infinity", "1e400"):
                path = Path(temporary) / "bad.jsonl"
                path.write_text('{"kind":"ignored","unused":' + token + '}\n', encoding="utf-8")
                inputs = appendix.Inputs()
                self.assertIsNone(inputs.read("telemetry", path, lines=True, select=appendix.select_event))
                self.assertTrue(inputs.errors)

    def test_identity_sha_mismatch_is_incomplete_and_keeps_original_conclusion(self):
        report, rows, identity, summary, events = fixture()
        inputs = appendix.Inputs()
        inputs.bindings["identity_report"] = {"sha256": "b" * 64}
        report["physical_identity_sha256"] = "c" * 64
        result = appendix.analyze(inputs, "specified", report, rows, identity, summary, events, occlusions="expected")
        self.assertEqual(result["status"], "INCOMPLETE_EVIDENCE")
        self.assertEqual(result["primary_conclusions"]["identity"], "RECORDED_WITH_EXPLICIT_UNKNOWN_INTERVALS")


if __name__ == "__main__":
    unittest.main()
