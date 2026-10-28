"""Tiny JSON fixtures check report honesty without importing research runtimes."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("full_plan_report", ROOT / "scripts/build_full_plan_report.py")
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return path


def summary(rows):
    from collections import Counter
    return {"schema_version": 1, "planned_flights": 166, "plan_sha256": "main-plan",
            "status_counts": dict(Counter(row["result"] for row in rows)), "trials": rows,
            "offline_status_counts": {}, "all_offline_slots_attempted": False}


def extra_manifest():
    trials = [{"name": f"extra_{index}", "id": str(index), "coverage": "online_fault",
               "target_class": "person", "command_mode": "velocity", "seed": 0} for index in range(16)]
    plan = {"expected_trials": 16, "primary_166_included": False, "trials": trials,
            "source_hashes": {"core": "source"}, "preregistration_sha256": "prereg"}
    return {"schema_version": 1, "source": "EXTENDED_ENGINEERING_16_FLIGHTS", "plan_sha256": reporter.digest(plan),
            "plan": plan,
            "slots": [{"trial": trial, "status": "PASS"} for trial in trials]}


def completed_inputs(root, rows=None):
    if rows is None:
        rows = [{"name": f"trial_{index}", "stage": 1, "target_class": "person", "result": "PASS"} for index in range(166)]
    plan = {"schema_version": 1, "frozen_root": str(root / "frozen"), "source_hashes": {"core": "source"},
            "preregistration_sha256": "prereg", "trials": [{key: row[key] for key in ("name", "stage", "target_class") if key in row} for row in rows]}
    plan["plan_sha256"] = reporter.digest(plan)
    data = summary(rows)
    data.update(plan_sha256=plan["plan_sha256"], offline_status_counts={"RECORDED": 164, "INCOMPLETE_EVIDENCE": 2},
                all_offline_slots_attempted=True)
    source = write(root / "study/summary.json", data)
    plan_path = write(root / "study/plan.json", plan)
    offline = write(root / "study/offline_manifest.json", {"schema_version": 1, "plan_sha256": plan["plan_sha256"],
        "trials": {row["name"]: {"name": row["name"], "status": "RECORDED" if index < 164 else "INCOMPLETE_EVIDENCE"}
                   for index, row in enumerate(rows)}})
    extra = extra_manifest()
    extra_path = write(root / "extra/manifest.json", extra)
    bindings = []
    for path in (source, plan_path, offline, extra_path):
        raw = path.read_bytes()
        bindings.append({"path": str(path.resolve()), "exists": True, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    supplement_plan = {"source_main_plan_sha256": plan["plan_sha256"], "source_engineering_plan_sha256": extra["plan_sha256"],
                       "frozen_root": plan["frozen_root"], "trials": extra["plan"]["trials"], "sources": bindings}
    slots = [{"trial": trial, "status": "RECORDED", "tasks": [
                 {"kind": "online_state_accuracy", "status": "RECORDED", "returncode": 0},
                 {"kind": "follow_dynamics", "status": "PREEXISTING_RECORDED_REPORT"}]}
             for trial in extra["plan"]["trials"]]
    slots[-2]["status"], slots[-1]["status"] = "INCOMPLETE_EVIDENCE", "INTERRUPTED"
    supplement = write(root / "supplement/manifest.json", {"schema_version": 1, "source": "POST_FLIGHT_ENGINEERING_16_SUPPLEMENT",
        "plan_sha256": reporter.digest(supplement_plan), "plan": supplement_plan, "slots": slots})
    labels = {key: key for key in sorted(reporter.REQUIRED_METRIC_KEYS)}
    metric_data = {"schema_version": 1, "source": "PER_FLIGHT_JSON_METRIC_SUPPLEMENT",
        "source_plan_sha256": plan["plan_sha256"], "main_planned_flights": 166, "main_listed_flights": 166,
        "engineering_listed_flights": 16, "all_main_flights_terminal": True, "include_state_frames": True,
        "metric_labels": labels, "sources": bindings,
        "flights": [{"cohort": "main166", **row} for row in rows]
                   + [{"cohort": "engineering16", **slot["trial"], "result": slot["status"]} for slot in extra["slots"]],
        "groups": {"main166/s1/person/velocity/fixture": {"planned_or_listed_flights": 166,
            "status_counts": data["status_counts"], "metrics": {key: {"valid_flights": 165, "missing_flights": 1,
                "mean": .25, "sample_sd": .1} for key in labels},
            "metric_evidence_status_counts": {key: {"RECORDED": 165, "MISSING_OR_UNOBSERVED_CONDITIONAL_EVIDENCE": 1} for key in labels},
            "short_same_task_recovery_evidence": {"short_requested_windows": 10, "same_track_and_task_confirmed_windows": 8,
                "unknown_identity_on_observed_recovery_windows": 1, "unobserved_or_untimed_recovery_windows": 1}},
            "engineering16/s1/person/velocity/fixture": {"planned_or_listed_flights": 16, "status_counts": {"PASS": 16},
                "metric_evidence_status_counts": {key: {"RECORDED": 16} for key in labels},
                "metrics": {key: {"valid_flights": 16, "missing_flights": 0, "mean": .5, "sample_sd": .2} for key in labels}}}}
    for group in metric_data["groups"].values():
        for key in labels:
            if key == "physical_retention_lower_bound" or key.startswith("task_mean_"):
                size = group["planned_or_listed_flights"]
                group["metrics"][key] = {"valid_flights": 0, "missing_flights": size, "mean": None, "sample_sd": None}
                group["metric_evidence_status_counts"][key] = {"NOT_APPLICABLE_NO_SELECTED_PHYSICAL_IDENTITY_TASK": size}
    metric = write(root / "metric.json", metric_data)
    return source, {"plan_path": plan_path, "offline_manifest_path": offline,
                    "engineering_manifest": extra_path, "supplement_manifest_path": supplement, "metric_supplement_path": metric}


class FullPlanReportTests(unittest.TestCase):
    def fixture(self):
        return tempfile.TemporaryDirectory(dir=ROOT / "results", prefix="test_report_")

    def test_partial_snapshot_cannot_claim_completion_or_replace_missing_with_zero(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            path = write(root / "study/summary.json", summary([
                {"name": "first", "stage": 1, "target_class": "person", "result": "FAIL"},
                {"name": "next", "stage": 1, "target_class": "person", "result": "PENDING"}]))
            original = path.read_bytes()
            text, provenance = reporter.build_report(path, root / "report.md")
            self.assertIn("报告状态：未完成", text)
            self.assertFalse(provenance["execution_ledger_complete"])
            self.assertIn("当前报告不能复核历史 132 标签", text)
            self.assertIn("未显式提供演示视频", text)
            self.assertIn("缺失", text)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((root / "report.md").exists())
            self.assertEqual(provenance["inputs"][0]["sha256"], hashlib.sha256(original).hexdigest())

    def test_completed_ledger_still_retains_failures_and_relative_video_json_links(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            rows = [{"name": f"trial_{index}", "stage": 1, "target_class": "person", "result": "FAIL" if index == 0 else "PASS",
                     "flight_phase_evidence": {"error": "bad depth | no rewrite"} if index == 0 else {}} for index in range(166)]
            source, inputs = completed_inputs(root, rows)
            raw = write(root / "trial_0/offline_evaluation.json", {"acceptance": {"result": "FAIL"}})
            video = root / "preview video.mp4"
            video.touch() # Never read/decode video bytes.
            text, provenance = reporter.build_report(source, root / "reports/report.md", **inputs, videos=[video])
            self.assertTrue(provenance["execution_ledger_complete"])
            self.assertEqual(provenance["completion_contract_version"], 2)
            self.assertTrue(provenance["supplement_ledger"]["complete"])
            self.assertTrue(provenance["metric_supplement"]["complete"])
            self.assertEqual(provenance["supplement_ledger"]["status_counts"], {"RECORDED": 14, "INCOMPLETE_EVIDENCE": 1, "INTERRUPTED": 1})
            self.assertEqual({item["role"] for item in provenance["completion_sources"]}, set(reporter.COMPLETION_ROLES))
            self.assertTrue(all(item["report_relative_path"].startswith("../") for item in provenance["completion_sources"]))
            self.assertIn("执行台账已覆盖全部 182 槽", text)
            self.assertIn("INCOMPLETE_EVIDENCE", text)
            self.assertIn("| trial_0 | FAIL |", text)
            self.assertIn("bad depth \\| no rewrite", text)
            self.assertIn("../preview%20video.mp4", text)
            self.assertIn("../trial_0/offline_evaluation.json", text)
            self.assertTrue(raw.exists())
            self.assertIn("| online_velocity_rmse_mps | 165 | 1 | 0 | 0.25 | 0.1 |", text)
            self.assertIn("| physical_retention_lower_bound | 0 | 0 | 166 | 缺失 | 缺失 |", text)
            self.assertIn("unknown_identity_on_observed_recovery_windows", text)

    def test_legacy_complete_counts_without_supplement_inputs_are_incomplete(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            source, inputs = completed_inputs(root)
            text, provenance = reporter.build_report(source, root / "report.md", engineering_manifest=inputs["engineering_manifest"])
            self.assertFalse(provenance["execution_ledger_complete"])
            self.assertIn("supplement_manifest", text)
            self.assertIn("报告状态：未完成", text)

    def test_supplement_nonterminal_duplicate_wrong_binding_and_incomplete_recorded_tasks(self):
        for fault in ("pending", "running", "duplicate", "wrong_plan", "bad_digest", "missing_task"):
            with self.subTest(fault=fault), self.fixture() as temporary:
                root = Path(temporary)
                source, inputs = completed_inputs(root)
                path = inputs["supplement_manifest_path"]
                data = json.loads(path.read_text(encoding="utf-8"))
                if fault == "pending":
                    data["slots"][0]["status"] = "PENDING"
                elif fault == "running":
                    data["slots"][0]["status"] = "RUNNING_ANALYSIS"
                elif fault == "duplicate":
                    data["slots"][1]["trial"] = data["slots"][0]["trial"]
                elif fault == "wrong_plan":
                    data["plan"]["source_main_plan_sha256"] = "foreign"
                    data["plan_sha256"] = reporter.digest(data["plan"])
                elif fault == "bad_digest":
                    data["plan"]["scope"] = "changed"
                else:
                    data["slots"][0]["tasks"].pop()
                write(path, data)
                _, provenance = reporter.build_report(source, root / "report.md", **inputs)
                self.assertFalse(provenance["execution_ledger_complete"])
                self.assertFalse(provenance["supplement_ledger"]["complete"])

    def test_supplement_checks_current_bytes_of_all_four_bound_source_ledgers(self):
        for role in ("summary", "plan_path", "offline_manifest_path", "engineering_manifest"):
            with self.subTest(role=role), self.fixture() as temporary:
                root = Path(temporary)
                source, inputs = completed_inputs(root)
                path = source if role == "summary" else inputs[role]
                # Whitespace preserves canonical plan IDs but changes saved bytes.
                path.write_bytes(path.read_bytes() + b"\n")
                text, provenance = reporter.build_report(source, root / "report.md", **inputs)
                self.assertFalse(provenance["execution_ledger_complete"])
                self.assertIn("补充输入 SHA/大小绑定不匹配", text)

    def test_supplement_source_sha_binding_allows_linux_windows_path_aliases(self):
        """A WSL-produced ledger can be checked from the Windows worktree."""
        with self.fixture() as temporary:
            root = Path(temporary)
            source, inputs = completed_inputs(root)
            path = inputs["supplement_manifest_path"]
            data = json.loads(path.read_text(encoding="utf-8"))
            for item in data["plan"]["sources"]:
                item["path"] = "/mnt/d/project/results/" + Path(item["path"]).name
            data["plan_sha256"] = reporter.digest(data["plan"])
            write(path, data)
            _, provenance = reporter.build_report(source, root / "report.md", **inputs)
            self.assertTrue(provenance["execution_ledger_complete"])
            self.assertTrue(provenance["supplement_ledger"]["complete"])

    def test_source_binding_is_bidirectional_and_still_requires_exact_sha(self):
        windows = {"path": r"D:\project\results\manifest.json", "exists": True, "bytes": 128, "sha256": "a" * 64}
        linux = {**windows, "path": "/mnt/d/project/results/manifest.json"}
        for source, record in ((windows, linux), (linux, windows)):
            with self.subTest(source=source["path"]):
                self.assertTrue(reporter.source_matches(source, record))
                self.assertFalse(reporter.source_matches({**source, "sha256": "b" * 64}, record))
                self.assertFalse(reporter.source_matches({**source, "bytes": 129}, record))
                self.assertFalse(reporter.source_matches({**source, "path": "/other/summary.json"}, record))

    def test_duplicate_source_binding_rejected_even_with_cross_system_path_alias(self):
        for family in ("supplement", "metric"):
            for first_path in ("local", "linux_alias"):
                with self.subTest(family=family, first_path=first_path), self.fixture() as temporary:
                    root = Path(temporary)
                    source, inputs = completed_inputs(root)
                    path = inputs["supplement_manifest_path" if family == "supplement" else "metric_supplement_path"]
                    data = json.loads(path.read_text(encoding="utf-8"))
                    bindings = data["plan"]["sources"] if family == "supplement" else data["sources"]
                    duplicate = dict(bindings[0])
                    duplicate["path"] = "/mnt/d/project/results/" + Path(duplicate["path"]).name
                    if first_path == "linux_alias":
                        bindings[0] = dict(duplicate)
                    bindings.append(duplicate)
                    if family == "supplement":
                        data["plan_sha256"] = reporter.digest(data["plan"])
                    write(path, data)
                    _, provenance = reporter.build_report(source, root / "report.md", **inputs)
                    validation = provenance["supplement_ledger" if family == "supplement" else "metric_supplement"]
                    self.assertFalse(provenance["execution_ledger_complete"])
                    self.assertFalse(validation["complete"])
                    self.assertTrue(any("重复" in problem for problem in validation["problems"]))

    def test_offline_task_names_and_engineering_canonical_digest_are_required(self):
        for fault in ("offline_name", "engineering_digest"):
            with self.subTest(fault=fault), self.fixture() as temporary:
                root = Path(temporary)
                source, inputs = completed_inputs(root)
                path = inputs["offline_manifest_path" if fault == "offline_name" else "engineering_manifest"]
                data = json.loads(path.read_text(encoding="utf-8"))
                if fault == "offline_name":
                    data["trials"]["foreign"] = data["trials"].pop("trial_0")
                else:
                    data["plan_sha256"] = "forged"
                write(path, data)
                _, provenance = reporter.build_report(source, root / "report.md", **inputs)
                self.assertFalse(provenance["execution_ledger_complete"])

    def test_matching_trial_names_with_wrong_summary_classification_are_incomplete(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            source, inputs = completed_inputs(root)
            data = json.loads(source.read_text(encoding="utf-8"))
            data["trials"][0]["stage"] = 3
            write(source, data)
            text, provenance = reporter.build_report(source, root / "report.md", **inputs)
            self.assertFalse(provenance["execution_ledger_complete"])
            self.assertIn("主汇总的逐任务阶段、类别、seed 或配置与计划不一致", text)

    def test_metric_supplement_requires_current_sources_complete_names_and_plan_metrics(self):
        for fault in ("stale_source", "wrong_plan", "wrong_name", "wrong_grouping", "not_terminal", "missing_metric", "missing_denominators", "missing_input"):
            with self.subTest(fault=fault), self.fixture() as temporary:
                root = Path(temporary)
                source, inputs = completed_inputs(root)
                path = inputs["metric_supplement_path"]
                data = json.loads(path.read_text(encoding="utf-8"))
                if fault == "missing_input":
                    inputs.pop("metric_supplement_path")
                else:
                    if fault == "stale_source":
                        data["sources"][0]["sha256"] = "stale"
                    elif fault == "wrong_plan":
                        data["source_plan_sha256"] = "foreign"
                    elif fault == "wrong_name":
                        data["flights"][0]["name"] = "foreign"
                    elif fault == "wrong_grouping":
                        data["flights"][0]["stage"] = 3
                    elif fault == "not_terminal":
                        data["all_main_flights_terminal"] = False
                    elif fault == "missing_denominators":
                        next(iter(data["groups"].values())).pop("metric_evidence_status_counts")
                    else:
                        data["metric_labels"].pop("online_velocity_rmse_mps")
                    write(path, data)
                text, provenance = reporter.build_report(source, root / "report.md", **inputs)
                self.assertFalse(provenance["execution_ledger_complete"])
                self.assertFalse(provenance["metric_supplement"]["complete"])
                self.assertIn("不能复报过期或其它研究的数值", text)
                self.assertNotIn("| online_velocity_rmse_mps | 165", text)

    def test_pairs_unknown_identity_and_censoring_keep_their_actual_denominators(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            data = summary([{"name": "bad", "stage": 2, "target_class": "car", "result": "FAIL"}])
            comparison = {"pairs": 8, "excluded_pairs": 2, "mean_difference": .2, "ci95": [-.1, .5]}
            conditional = {"pairs": 5, "excluded_pairs": 5, "mean_difference": -.3, "ci95": [-.7, .1]}
            data["stage1_joined_statistics"] = {"paired_comparisons": {"car_adaptive_minus_raw": {"outcomes": {
                "online_state_anchor_position_rmse_m": {"all_measurable_recorded_pairs": comparison, "conditional_both_flight_pass": conditional}}}}}
            data["stage2_crossing_statistics"] = {"car": {"recorded_trials": 3, "planned_seeds": list(range(10)),
                "all_detection_opportunities": 80, "all_task_opportunities": 70, "physical_reports_missing_or_incomplete": 1,
                "selected_physical_counts": {"CORRECT": 20, "WRONG_PHYSICAL_ACTOR": 0, "UNKNOWN_GEOMETRY": 40, "NO_FRESH_MATCH": 10}}}
            data["stage3_paired_statistics"] = {"car": {"active_minus_midpoint": {"online_state_coverage": {
                "seed_units": list(range(10)), "all_measurable_recorded_pairs": comparison, "conditional_both_flight_pass": conditional}}}}
            data["follow_dynamics_statistics"] = {"s3_car_velocity_active": {"flight_units": 10, "dynamics_recorded": 9,
                "initial_distance_settling": {"observed_settled": 0, "right_censored": 9, "missing_window": 1,
                    "observed_settling_time_s": {"mean": None, "std": None, "valid_count": 0, "missing_count": 10}}}}
            source = write(root / "study/summary.json", data)
            text, _ = reporter.build_report(source, root / "report.md")
            self.assertIn("全部可测配对（含失败飞行） | 8 | 2 | 0.2 | [-0.1, 0.5]", text)
            self.assertIn("双方 PASS 的条件配对 | 5 | 5 | -0.3 | [-0.7, 0.1]", text)
            self.assertIn("| car | 3 | 10 | 80 | 70 | 20 | 0 | 10 | 40 | 1 |", text)
            self.assertIn("| s3_car_velocity_active | 距离 | 10 | 9 | 0 | 9 | 1 | 缺失", text)
            self.assertIn("差值方向为 active − midpoint", text)
            self.assertIn("不能认证 unknown 或无新鲜匹配区间", text)
            self.assertNotIn("自适应 KF 已胜出", text)

    def test_duplicate_extensions_or_pending_offline_prevent_false_completion(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            data = summary([{"name": f"t_{i}", "stage": 1, "target_class": "person", "result": "PASS"} for i in range(166)])
            data.update(offline_status_counts={"PENDING": 166}, all_offline_slots_attempted=True)
            source = write(root / "study/summary.json", data)
            extra = extra_manifest()
            extra["slots"][1]["trial"] = extra["slots"][0]["trial"]
            path = write(root / "extra.json", extra)
            text, provenance = reporter.build_report(source, root / "report.md", engineering_manifest=path)
            self.assertFalse(provenance["execution_ledger_complete"])
            self.assertIn("扩展槽重复", text)
            self.assertIn("离线评价仍有运行中、待执行", text)

    def test_stage1_terminal_denominator_preserves_existing_performance_statistics(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            statuses = ["PASS", "FAIL", "INCOMPLETE", "INTERRUPTED", "PENDING", "RUNNING", "UNKNOWN"]
            rows = [{"name": f"estimate_{i}", "stage": 1, "target_class": "person", "command_mode": "velocity",
                     "estimator_method": "adaptive_kf", "result": status} for i, status in enumerate(statuses)]
            rows.append({"name": "raw", "stage": 1, "target_class": "person", "command_mode": "velocity", "estimator_method": "raw", "result": "FAIL"})
            rows.append({"name": "position", "stage": 1, "target_class": "person", "command_mode": "position", "estimator_method": "adaptive_kf", "result": "FAIL"})
            rows.append({"name": "car", "stage": 1, "target_class": "car", "command_mode": "velocity", "estimator_method": "adaptive_kf", "result": "FAIL"})
            data = summary(rows)
            data["stage1_joined_statistics"] = {"groups": {"person_velocity_adaptive_kf": {
                "planned_or_started": 6, "pass": 1,
                "failure_rate": {"failures": 5, "total": 6, "rate": 5 / 6, "ci95": [.4, .97]},
                "horizontal_distance_error_rmse_m": {"mean": .3, "std": .2, "valid_count": 4, "missing_count": 2}}}}
            source = write(root / "summary.json", data)
            text, _ = reporter.build_report(source, root / "report.md")
            self.assertIn("| person_velocity_adaptive_kf | 7 | 4 | 1 | 3 | 1 | 2 | 0.75 [0.300642, 0.954413] | 0.3 ± 0.2（有效 4，缺失 2） |", text)
            self.assertIn("| person_velocity_adaptive_kf | 5/6 | 缺失 | 缺失 |", text)
            self.assertNotIn("0.833333", text)

    def test_stage1_zero_terminal_and_completed_saved_rate(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            rows = [{"name": "pending", "stage": 1, "target_class": "person", "command_mode": "velocity", "estimator_method": "raw", "result": "PENDING"},
                    {"name": "running", "stage": 1, "target_class": "person", "command_mode": "velocity", "estimator_method": "raw", "result": "RUNNING"}]
            rows += [{"name": f"car_{i}", "stage": 1, "target_class": "car", "command_mode": "velocity", "estimator_method": "raw",
                      "result": "FAIL" if i < 2 else "PASS"} for i in range(10)]
            data = summary(rows)
            data["stage1_joined_statistics"] = {"groups": {"car_velocity_raw": {
                "failure_rate": {"failures": 2, "total": 10, "rate": .2, "ci95": [.05668215145437519, .5098375284633583]}}}}
            source = write(root / "summary.json", data)
            text, _ = reporter.build_report(source, root / "report.md")
            self.assertIn("| person_velocity_raw | 2 | 0 | 0 | 0 | 1 | 1 | 缺失 缺失 |", text)
            self.assertIn("| car_velocity_raw | 10 | 10 | 8 | 2 | 0 | 0 | 0.2 [0.0566822, 0.509838] |", text)
            self.assertIn("| car_velocity_raw | 2/10 | 0.2 | [0.0566822, 0.509838] |", text)

    def test_stage2_preserves_saved_failure_denominator_and_wilson_interval(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            rows = [{"name": f"crossing_{i}", "stage": 2, "scenario": "crossing", "target_class": "car",
                     "result": "FAIL" if i < 2 else "PASS"} for i in range(10)]
            rows.append({"name": "engineering", "stage": 2, "scenario": "ambiguity", "target_class": "car", "result": "FAIL"})
            data = summary(rows)
            data["stage2_crossing_statistics"] = {"car": {
                "recorded_trials": 10, "planned_seeds": list(range(10)),
                "failure_rate": {"failures": 2, "total": 10, "rate": .2,
                                 "ci95": [.05668215145437519, .5098375284633583]}}}
            source = write(root / "summary.json", data)
            text, _ = reporter.build_report(source, root / "report.md")
            self.assertIn("| car | 10 | 10 | 8 | 2 | 0 | 0 | 0.2 | [0.0566822, 0.509838] |", text)
            self.assertIn("| car | 2/10 | 0.2 | [0.0566822, 0.509838] |", text)
            self.assertIn("该分母不含另外 6 次工程安全检查", text)

    def test_stage2_pending_running_unknown_are_not_failures(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            statuses = ["PASS", "FAIL", "INCOMPLETE", "INTERRUPTED", "PENDING", "RUNNING", "UNKNOWN"]
            rows = [{"name": f"crossing_{i}", "stage": 2, "scenario": "crossing", "target_class": "person",
                     "result": status} for i, status in enumerate(statuses)]
            data = summary(rows)
            data["stage2_crossing_statistics"] = {"person": {
                "failure_rate": {"failures": 5, "total": 6, "rate": 5 / 6, "ci95": [.4, .97]},
                "per_seed": [{"name": "stale", "result": "PASS"}]}}
            source = write(root / "summary.json", data)
            text, _ = reporter.build_report(source, root / "report.md")
            self.assertIn("| person | 7 | 4 | 1 | 3 | 1 | 2 | 0.75 | [0.300642, 0.954413] |", text)
            self.assertIn("| person | 5/6 | 缺失 | 缺失 |", text)
            self.assertNotIn("0.833333", text)

    def test_stage2_per_seed_zero_terminal_keeps_rate_missing(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            data = summary([])
            data["stage2_crossing_statistics"] = {"person": {
                "failure_rate": {"failures": 2, "total": 2, "rate": 1., "ci95": [.342, 1.]},
                "per_seed": [{"name": "pending", "result": "PENDING"}, {"name": "running", "result": "RUNNING"},
                             {"name": "unknown", "result": "UNKNOWN"}]}}
            source = write(root / "summary.json", data)
            text, _ = reporter.build_report(source, root / "report.md")
            self.assertIn("| person | 3 | 0 | 0 | 0 | 1 | 2 | 缺失 | 缺失 |", text)
            self.assertIn("| person | 2/2 | 缺失 | 缺失 |", text)

    def test_stage3_failure_rate_excludes_pending_running_and_unknown(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            statuses = ["PASS", "FAIL", "INCOMPLETE", "INTERRUPTED", "PENDING", "RUNNING", "UNKNOWN"]
            rows = [{"name": f"gimbal_{i}", "stage": 3, "target_class": "car",
                     "gimbal_mode": "active", "result": status} for i, status in enumerate(statuses)]
            rows.append({"name": "other_stage", "stage": 1, "target_class": "car", "gimbal_mode": "active", "result": "FAIL"})
            rows.append({"name": "other_mode", "stage": 3, "target_class": "car", "gimbal_mode": "midpoint", "result": "PASS"})
            rows.append({"name": "other_class", "stage": 3, "target_class": "person", "gimbal_mode": "active", "result": "FAIL"})
            source = write(root / "summary.json", summary(rows))
            text, _ = reporter.build_report(source, root / "report.md")
            self.assertIn("| car | active | 7 | 4 | 1 | 3 | 1 | 2 | 0.75 | [0.300642, 0.954413] |", text)
            self.assertIn("| car | midpoint | 1 | 1 | 1 | 0 | 0 | 0 | 0 |", text)
            self.assertIn("| person | active | 1 | 1 | 0 | 1 | 0 | 0 | 1 |", text)
            from collections import Counter
            rate = reporter.terminal_failure_rate(Counter(statuses))
            self.assertEqual((rate["failures"], rate["total"], rate["rate"]), (3, 4, .75))
            self.assertAlmostEqual(rate["ci95"][0], .300641842582402, places=12)
            self.assertAlmostEqual(rate["ci95"][1], .954412739190299, places=12)

    def test_stage3_zero_terminal_keeps_failure_rate_missing(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            rows = [{"name": "pending", "stage": 3, "target_class": "person", "gimbal_mode": "midpoint", "result": "PENDING"},
                    {"name": "running", "stage": 3, "target_class": "person", "gimbal_mode": "midpoint", "result": "RUNNING"}]
            source = write(root / "summary.json", summary(rows))
            text, _ = reporter.build_report(source, root / "report.md")
            self.assertIn("| person | midpoint | 2 | 0 | 0 | 0 | 1 | 1 | 缺失 | 缺失 |", text)
            self.assertIn("零终态时失败率及区间保持缺失", text)

    def test_reviewed_subset_uses_supplied_counts_and_never_averages_ap(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            source = write(root / "study/summary.json", summary([]))
            review = write(root / "review.json", {"approved_frames": {"one": ["1", "2"]}})
            detection = write(root / "detection.json", {"review_file_sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
                "recordings": [{"source_trial": "/old/one", "target_class": "car", "approved_eligible": 2,
                "reviewed_metrics": {"classes": {"car": {"confidence_threshold": .45, "precision": 1., "recall": .5, "fn": 1, "ap50": 1., "ap50_95": .8}}}}]})
            text, _ = reporter.build_report(source, root / "report.md", review_path=review, detection_path=detection)
            self.assertIn("当前审核清单列出 2 个批准帧", text)
            self.assertNotIn("当前审核清单列出 132 个批准帧", text)
            self.assertIn("| one | car | 2 | 0.45 | 1 | 0.5 | 1 | 1 | 0.8 |", text)
            self.assertIn("不能把逐录制 AP 简单平均", text)
            self.assertIn("mAP 缺失", text)

    def test_pooled_reviewed_map_uses_saved_aggregate_and_explicit_denominators(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            source = write(root / "study/summary.json", summary([]))
            review = write(root / "review.json", {"approved_frames": {"one": ["1", "2"]}})
            detection = write(root / "detection.json", {"recordings": [], "review_file_sha256": hashlib.sha256(review.read_bytes()).hexdigest(), "reviewed_aggregate": {
                "frames": 2, "map50": .85, "map50_95": .65, "classes": {
                    "car": {"ground_truth_objects": 3, "confidence_threshold": .45, "tp": 2, "fp": 1, "fn": 1,
                            "precision": 2/3, "recall": 2/3, "ap50": .8, "ap50_95": .6},
                    "person": {"ground_truth_objects": 1, "confidence_threshold": .45, "tp": 1, "fp": 0, "fn": 0,
                               "precision": 1., "recall": 1., "ap50": .9, "ap50_95": .7},
                    "predicted_only": {"ground_truth_objects": 0, "predicted_objects": 2, "ap50": None, "ap50_95": None}}}})
            text, _ = reporter.build_report(source, root / "report.md", review_path=review, detection_path=detection)
            self.assertIn("| 2 | 2 | 2 | 0.85 | 0.65 |", text)
            self.assertIn("| car | 3 | 0.45 | 2 | 1 | 1 | 0.666667 | 0.666667 | 0.8 | 0.6 |", text)
            self.assertIn("不能外推为正式 166 次或多目标遮挡检测 mAP", text)

    def test_same_frame_count_different_review_ids_cannot_reuse_old_map(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            source, inputs = completed_inputs(root)
            review = write(root / "review.json", {"approved_frames": {"one": ["1", "2"]}})
            detection = write(root / "detection.json", {"recordings": [], "review_file_sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
                "reviewed_aggregate": {"frames": 2, "map50": .987654, "map50_95": .876543, "classes": {}}})
            write(review, {"approved_frames": {"one": ["other1", "other2"]}})
            text, provenance = reporter.build_report(source, root / "report.md", **inputs, review_path=review, detection_path=detection)
            self.assertFalse(provenance["execution_ledger_complete"])
            self.assertIn("同样的帧数量不能证明相同帧ID", text)
            self.assertNotIn("0.987654", text)

    def test_plan_mismatch_and_source_manifest_do_not_hide_input_changes(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            source = write(root / "summary.json", summary([]))
            plan = write(root / "plan.json", {"plan_sha256": "other-plan"})
            text, provenance = reporter.build_report(source, root / "report.md", plan_path=plan)
            self.assertIn("主汇总与冻结计划 SHA 不一致", text)
            self.assertFalse(provenance["execution_ledger_complete"])
            self.assertTrue(all("sha256" in row for row in provenance["inputs"] if row["exists"]))

    def test_cli_writes_only_markdown_and_sources_manifest(self):
        with self.fixture() as temporary:
            root = Path(temporary)
            source = write(root / "summary.json", summary([]))
            output = root / "report.md"
            args = ["report", "--summary", str(source), "--output", str(output), "--detection", str(root / "missing.json"), "--review", str(root / "missing_review.json")]
            with patch.object(sys, "argv", args), redirect_stdout(io.StringIO()):
                reporter.main()
            manifest = json.loads(output.with_suffix(".sources.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["report_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertFalse(manifest["execution_ledger_complete"])
            self.assertEqual({path.name for path in root.iterdir()}, {"summary.json", "report.md", "report.sources.json"})


if __name__ == "__main__":
    unittest.main()
