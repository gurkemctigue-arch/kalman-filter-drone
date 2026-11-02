"""Saved v4 display must retain missing opportunities and its limited authority.

Pure JSON fixtures only. These tests do not import the v4 runner/reporter,
read bags, run inference, or start the simulator.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "acceptance_dashboard_v4", Path(__file__).resolve().parents[1] / "scripts/build_acceptance_dashboard.py")
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class V4DeliveryDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs"
        self.package_dir = self.inputs / "documents"
        self.output = self.root / "delivery" / "index.html"
        self.plans = {}
        self.plan_pins = {}
        for cohort, count, mode in (("core", 120, "FORMAL"), ("extension", 160, "EXTENSION_FORMAL")):
            trials = [{"id": f"{cohort}_{i:03d}", "target_class": "person" if i % 2 else "car",
                       "group": "stage2_crossing" if i < 40 else "stage1_follow", "seed": 1000 + i % 10,
                       "directory": str(self.inputs / "recordings" / f"{cohort}_{i:03d}")}
                      for i in range(count)]
            plan = {"schema_version": 1, "mode": mode, "trials": trials,
                    "frozen_root": str(self.inputs / "frozen"), "output": str(self.inputs / (cohort + "_slots"))}
            if cohort == "extension":
                plan["core_reference_binding"] = {**self.plan_pins["core"], "plan_sha256": self.plans["core"]["plan_sha256"]}
            plan["plan_sha256"] = digest(plan)
            self.plans[cohort] = plan
            self.plan_pins[cohort] = self.write_json(self.inputs / (cohort + "_plan.json"), plan)
        self.summary = {"schema_version": 1, "cohorts": {
            name: {"planned_slots": len(plan["trials"]), "plan_sha256": plan["plan_sha256"]}
            for name, plan in self.plans.items()}, "trials": []}
        for trial, status in zip(self.plans["core"]["trials"], ("PASS", "FAIL", "INCOMPLETE_EVIDENCE", "UNKNOWN_EXTERNAL_STATUS")):
            self.summary["trials"].append({**trial, "slot_id": trial["id"], "cohort": "core", "status": status,
                "metrics": {"base_link_distance_rmse_m": None, "physical_task_time_known_coverage": .2,
                            "physical_task_time_retention_lower_bound": .1, "physical_task_time_wrong_samples": 2,
                            "physical_task_time_unknown_samples": 80}, "report_issues": []})
        self.save_package()

    def tearDown(self):
        self.temp.cleanup()

    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return self.pin(path)

    @staticmethod
    def pin(path):
        return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def save_package(self, *, schema=1):
        summary_pin = self.write_json(self.inputs / "summary.json", self.summary)
        sources = [{**pin, "role": "engineering_plan", "exists": True, "bytes": Path(pin["path"]).stat().st_size}
                   for pin in self.plan_pins.values()]
        sources.append({**summary_pin, "role": "engineering_summary", "exists": True,
                        "bytes": Path(summary_pin["path"]).stat().st_size})
        package = {"schema_version": schema, "kind": "RELIABILITY_V4_DOCUMENT_PACKAGE", "mode": "draft",
                   "scope": "DEVELOPMENT_ONLY", "cohorts": self.summary["cohorts"], "sources": sources,
                   "request": {"core_path": self.plan_pins["core"]["path"],
                               "extension_path": self.plan_pins["extension"]["path"], "summary_path": summary_pin["path"]}}
        package["document_package_sha256"] = digest(package)
        self.package = self.package_dir / "documents.json"
        self.write_json(self.package, package)
        outputs = []
        for name in ("plan.md", "report.md", "plan.html", "report.html", "documents.json"):
            path = self.package_dir / name
            if name != "documents.json":
                path.write_text("saved fixture " + name, encoding="utf-8")
            outputs.append({**self.pin(path), "path": name, "bytes": path.stat().st_size})
        self.write_json(self.package_dir / "sources.json", {"schema_version": 1, "kind": "RELIABILITY_V4_REPORT_SOURCES",
            "mode": package["mode"], "scope": package["scope"], "sources": sources, "outputs": outputs,
            "document_package_sha256": package["document_package_sha256"]})

    def detection(self):
        protocol = {"schema_version": 1, "kind": "PROSPECTIVE_ALL_ACTOR_DYNAMIC_CAMERA_DETECTION_V1",
                    "original_planned_slots": 280, "plans": self.plan_pins,
                    "slots": [{"slot_id": t["id"]} for plan in self.plans.values() for t in plan["trials"]]}
        protocol_pin = self.write_json(self.inputs / "detection" / "protocol.json", protocol)
        review_pin = self.write_json(self.inputs / "detection" / "review.json",
            {"schema_version": 1, "kind": "INDEPENDENT_ALL_ACTOR_VISIBLE_LABEL_REVIEW_V1"})
        recording_pin = {"path": str(self.inputs / "large_not_opened" / "recording.json"), "sha256": "a" * 64}
        record = {"slot_id": "core_000", "protocol": protocol_pin, "recording": recording_pin,
                  "prediction_cache": None, "independent_visible_label_review_valid": True,
                  "reviewed_metrics": {"map50_95": .731}, "publication_status": "REVIEWED_SUBSET_ONLY"}
        report = {"schema_version": 1, "kind": "PROSPECTIVE_ALL_ACTOR_DYNAMIC_DETECTION_REPORT_V1",
                  "protocol": protocol_pin, "original_planned_slots": 280, "recordings": [record],
                  "recording_slots_supplied": 1, "missing_original_slot_ids": [s["slot_id"] for s in protocol["slots"][1:]],
                  "all280_recordings_supplied": False, "scheduled_opportunities": 10,
                  "review_file": review_pin, "reviewed_aggregate": {"map50_95": .731}}
        path = self.inputs / "detection" / "detection_report.json"
        self.write_json(path, report)
        return path, report

    def recovery(self):
        slots = [{"slot_id": t["id"], "opportunities": [
            {"id": t["id"] + ":" + kind, "kind": kind} for kind in ("short", "long_explicit_reselection")]}
            for t in self.plans["core"]["trials"][:40]]
        protocol = {"schema_version": 1, "kind": "PROSPECTIVE_PHYSICAL_RECOVERY_APPENDIX_V1",
                    "core_plan": self.plan_pins["core"], "slots": slots, "registered_slots": 40,
                    "registered_opportunities": 80, "original_core_denominator": 120}
        protocol_pin = self.write_json(self.inputs / "recovery" / "protocol.json", protocol)
        summary = {name: {"registered_opportunities": count,
                         "supported_original_without_observed_different": 0, "descriptive_lower_bound": 0,
                         "right_censored": 0, "missing_or_invalid_events": count,
                         "original_confirmation_delay_s": {"n": 0, "N": count, "mean": None}}
                   for name, count in (("short", 40), ("long_explicit_reselection", 40), ("all", 80))}
        report = {"schema_version": 1, "kind": "PROSPECTIVE_PHYSICAL_RECOVERY_APPENDIX_V1",
                  "scope": "INDEPENDENT_PHYSICAL_RECOVERY_APPENDIX_NOT_ORIGINAL_VERDICTS",
                  "evaluation_status": "DESCRIPTIVE_APPENDIX_WITH_EXPLICIT_UNKNOWN_AND_MISSING_OPPORTUNITIES",
                  "protocol_binding": protocol_pin, "slots": slots, "summary": summary}
        path = self.inputs / "recovery" / "physical_recovery.json"
        self.write_json(path, report)
        return path, report

    def timing(self):
        events = {"path": str(self.inputs / "large_not_opened" / "events.jsonl"), "sha256": "b" * 64}
        context = {"schema_version": 1, "kind": "NATIVE_PIPELINE_TIMING_EXPORT_CONTEXT_NOT_ACCEPTANCE", "events": events,
                   "source_root": self.plans["core"]["frozen_root"], "trial": self.plans["core"]["trials"][0]["directory"]}
        context_pin = self.write_json(self.inputs / "timing" / "context.json", context)
        report = {"schema_version": 1, "kind": "OFFLINE_OBSERVED_PIPELINE_TIMING_NOT_CAUSAL_E2E",
                  "scope": "OBSERVABLE_TIMING_ONLY_NOT_ACCEPTANCE", "inputs": {"context": context_pin, "events": events},
                  "actual_worker_processed_wall_fps": {"status": "NOT_OBSERVED", "hz": None}}
        for key in ("capture_to_controller_causal_source_s", "capture_to_px4_setpoint_causal_source_s", "physical_capture_to_px4_effect_wall_s"):
            report[key] = {"status": "NOT_OBSERVED", "known": 0, "unknown": 3}
        for key in ("detector_acquisition_to_prepublication_source_s", "detector_processing_prefix_wall_s",
                    "completed_job_yolo_predict_wall_s", "controller_reported_measurement_age_source_s"):
            report[key] = {"known": 0, "unknown": 3, "total": 3, "statistics_s": {"mean": None, "p95": None}}
        path = self.inputs / "timing" / "timing.json"
        self.write_json(path, report)
        return path, report

    def test_original_280_retains_failed_unknown_and_missing_without_legacy_verdicts(self):
        with patch.object(dashboard, "discover_trials", side_effect=AssertionError("legacy discovery forbidden")), \
             patch.object(dashboard, "evidence_status", side_effect=AssertionError("legacy verdict forbidden")):
            result = dashboard.build_v4_dashboard(self.package, self.output)
        self.assertEqual(result["slot_counts"], {"PASS": 1, "FAIL": 1, "INCOMPLETE_EVIDENCE": 1,
                                              "UNKNOWN_EXTERNAL_STATUS": 1, "MISSING_SUMMARY_ROW": 276})
        index = json.loads(Path(result["source_index"]).read_text(encoding="utf-8"))
        self.assertEqual(index["displayed_slot_rows"], 280)
        self.assertFalse(index["project_acceptance_claimed"])
        self.assertFalse(index["original_evaluator_rerun"])
        page = self.output.read_text(encoding="utf-8")
        self.assertIn("extension_159", page)
        self.assertIn("未知 / 缺失（null）", page)
        self.assertIn("UNKNOWN_EXTERNAL_STATUS", page)

    def test_tampered_package_output_and_unknown_package_schema_are_rejected(self):
        (self.package_dir / "report.html").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "绑定文件已改变"):
            dashboard.build_v4_dashboard(self.package, self.output)
        self.assertFalse(self.output.exists())
        self.save_package(schema=99)
        with self.assertRaisesRegex(ValueError, "schema/kind"):
            dashboard.build_v4_dashboard(self.package, self.output)

    def test_changed_summary_binding_hides_metrics_and_keeps_280_missing(self):
        altered = copy.deepcopy(self.summary)
        altered["trials"][0]["metrics"]["base_link_distance_rmse_m"] = 98765
        self.write_json(self.inputs / "summary.json", altered)
        result = dashboard.build_v4_dashboard(self.package, self.output)
        self.assertEqual(result["slot_counts"], {"MISSING_FORMAL_EVIDENCE": 280})
        self.assertNotIn("98765", self.output.read_text(encoding="utf-8"))

    def test_reviewed_detection_stays_subset_and_deferred_sources_are_explicit(self):
        path, _ = self.detection()
        result = dashboard.build_v4_dashboard(self.package, self.output, prospective_detection=[path])
        self.assertIn("SAVED_REPORT_SMALL_BINDINGS_CHECKED_NOT_REVERIFIED", result["attachment_statuses"])
        index = json.loads(Path(result["source_index"]).read_text(encoding="utf-8"))
        self.assertEqual(index["deferred_bindings_not_reread"][0]["validation"], "NOT_REREAD")
        page = self.output.read_text(encoding="utf-8")
        self.assertIn("0.731", page)
        self.assertIn("已批准的可见仿真子集", page)

    def test_unknown_attachment_schema_and_broken_review_do_not_publish_metrics(self):
        path, report = self.detection()
        report["schema_version"] = 99
        self.write_json(path, report)
        result = dashboard.build_v4_dashboard(self.package, self.output, prospective_detection=[path])
        self.assertIn("REJECTED_OR_MISSING", result["attachment_statuses"])
        self.assertNotIn("0.731", self.output.read_text(encoding="utf-8"))
        path, report = self.detection()
        Path(report["review_file"]["path"]).write_text("changed", encoding="utf-8")
        result = dashboard.build_v4_dashboard(self.package, self.root / "second" / "index.html", prospective_detection=[path])
        self.assertIn("REJECTED_OR_MISSING", result["attachment_statuses"])

    def test_recovery_null_times_and_all_80_opportunities_have_no_false_verification(self):
        path, _ = self.recovery()
        result = dashboard.build_v4_dashboard(self.package, self.output, physical_recovery=[path])
        self.assertIn("SAVED_REPORT_SMALL_BINDINGS_CHECKED_NOT_REVERIFIED", result["attachment_statuses"])
        page = self.output.read_text(encoding="utf-8")
        self.assertIn("此工具没有 verify-report", page)
        self.assertIn("未知与未恢复机会保留在80机会分母中", page)
        self.assertIn("不是自动ReID", page)

    def test_timing_does_not_read_events_or_claim_causal_latency(self):
        path, report = self.timing()
        result = dashboard.build_v4_dashboard(self.package, self.output, timing=[path])
        self.assertIn("SAVED_REPORT_SMALL_BINDINGS_CHECKED_NOT_REVERIFIED", result["attachment_statuses"])
        page = self.output.read_text(encoding="utf-8")
        self.assertIn("NOT_OBSERVED（未观察）", page)
        self.assertIn("不得跨时钟相减或按RTF换算", page)
        report["capture_to_controller_causal_source_s"]["status"] = "MEASURED"
        self.write_json(path, report)
        result = dashboard.build_v4_dashboard(self.package, self.root / "second" / "index.html", timing=[path])
        self.assertIn("REJECTED_OR_MISSING", result["attachment_statuses"])

    def test_independent_output_cannot_overwrite_or_write_into_input_directory(self):
        with self.assertRaisesRegex(ValueError, "禁止在输入"):
            dashboard.build_v4_dashboard(self.package, self.package_dir / "new_dashboard.html")
        dashboard.build_v4_dashboard(self.package, self.output)
        original = self.output.read_bytes()
        with self.assertRaisesRegex(ValueError, "新的独立文件"):
            dashboard.build_v4_dashboard(self.package, self.output)
        self.assertEqual(self.output.read_bytes(), original)

    def test_timing_from_a_development_trial_cannot_enter_formal_attachment(self):
        path, report = self.timing()
        context_path = Path(report["inputs"]["context"]["path"])
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["trial"] = str(self.inputs / "development_trial")
        report["inputs"]["context"] = self.write_json(context_path, context)
        self.write_json(path, report)
        result = dashboard.build_v4_dashboard(self.package, self.output, timing=[path])
        self.assertIn("REJECTED_OR_MISSING", result["attachment_statuses"])
        self.assertIn("不是本轮原始120+160计划", self.output.read_text(encoding="utf-8"))

    def test_small_json_rejects_overflow_and_duplicate_metrics(self):
        path = self.inputs / "invalid_metrics.json"
        for raw in ('{"metric": 1e999}', '{"metric": NaN}', '{"metric": 1, "metric": 2}'):
            with self.subTest(raw=raw):
                path.write_text(raw, encoding="utf-8")
                with self.assertRaises(ValueError):
                    dashboard._V4Inputs().bound(self.pin(path), "malformed_metric_fixture")


if __name__ == "__main__":
    unittest.main()
