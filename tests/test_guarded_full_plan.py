"""Pure fixtures for external one-slot frozen research continuation; no ROS."""
from __future__ import annotations

from contextlib import nullcontext
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("guarded_full_plan_fixture", ROOT / "scripts/run_guarded_full_plan.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def inputs():
    return {"clock_recorded": True, "clock_samples_read": 100,
            "topic_types": {"/clock": "Clock", "/vehicle/odometry": "Odometry"},
            "read_errors": {}, "unavailable_types": {}}


def healthy_trial(root, trial, *, sitl=0, verdict="FAIL", monitor_reason="wall_timeout"):
    trial.setdefault("target_class", "person")
    trial.setdefault("desired_distance_m", 5.0)
    trial.setdefault("terminal_expectation", "tracking")
    trial.setdefault("occlusions", False)
    trial.setdefault("gimbal_mode", "midpoint")
    directory = root / "results" / trial["name"]
    bag = directory / "rosbag"
    bag.mkdir(parents=True)
    write(bag / "metadata.yaml", {"rosbag2_bagfile_information": {
        "message_count": 200, "topics_with_message_count": [
            {"topic_metadata": {"name": name}, "message_count": 100}
            for name in ("/clock", "/vehicle/odometry")], "relative_file_paths": ["recording.db3.zstd"]}})
    (bag / "recording.db3.zstd").write_bytes(b"never-read-this-fixture-database")
    write(directory / "summary.json", {"termination_reason": monitor_reason, "max_vehicle_altitude_m": 3.,
          "monitor_exit_code": 1 if sitl else 0})
    write(directory / "process_exit_codes.json", {"bag": 0, "ros": 0, "px4": 0, "agent": -2, "monitor": sitl})
    (directory / "telemetry.jsonl").write_text(json.dumps({"kind": "telemetry", "time_s": 1.,
        "position": [0., 0., 3.], "phase": "FOLLOW"}) + "\n", encoding="utf-8")
    sitl_log = root / "results/study/stage23_matrix/logs" / f"{trial.get('id', trial['name'])}_sitl.log"
    sitl_log.parent.mkdir(parents=True, exist_ok=True)
    sitl_log.write_text("normal frozen trial invocation\n", encoding="utf-8")
    commands = [{"kind": "sitl", "returncode": sitl, "log": str(sitl_log)}]
    evaluations = []
    reports = ({"auto_unique": ("auto_unique_evaluation.json", {"schema_version": 2,
               "source": "OFFLINE_AUTO_UNIQUE_MULTIPLE_CANDIDATE_SAFETY", "result": verdict, "inputs": inputs()})}
               if trial["scenario"] == "auto_unique" else
               {"stage2_safety": ("stage2_evaluation.json", {"schema_version": 1,
                "source": "OFFLINE_STAGE2_SAFETY_EVALUATION", "result": verdict, "inputs": inputs()})}
               if trial["stage"] == 2 else
               {"flight": ("flight_evaluation.json", {"schema_version": 3,
                "acceptance": {"result": verdict}, "inputs": inputs()}),
                "gimbal": ("gimbal_evaluation.json", {"schema_version": 3,
                "evaluator_version": "3_audited_paused_startup_feedback", "result": "FAIL_OR_INCOMPLETE",
                "metadata": inputs()})})
    for kind, (filename, report) in reports.items():
        metadata = report.get("inputs", report.get("metadata"))
        metadata["bag"] = str(bag.resolve())
        if kind in {"flight", "stage2_safety"}:
            report["configuration"] = {"target_class": trial["target_class"]}
        if kind == "flight":
            report["configuration"].update(desired_distance_m=trial["desired_distance_m"], desired_height_m=2.0,
                                           start_s=None, end_s=None)
            report["topic_message_counts"] = {"/vehicle/odometry": 100}
        if kind == "stage2_safety":
            report["configuration"].update(terminal_expectation=trial["terminal_expectation"],
                require_occlusions=trial["occlusions"], require_ambiguity=trial["scenario"] == "ambiguity")
        if kind == "auto_unique":
            report["target_class"] = trial["target_class"]
        if kind == "gimbal":
            report["mode"] = trial["gimbal_mode"]
        path = directory / filename
        write(path, report)
        result = report["acceptance"]["result"] if kind == "flight" else report["result"]
        code = 2 if kind in {"stage2_safety", "auto_unique"} and result != "PASS" else 0
        log = root / "results/study/stage23_matrix/logs" / f"{trial.get('id', trial['name'])}_{kind}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps({"result": result}), encoding="utf-8")
        commands.append({"kind": kind, "returncode": code, "log": str(log)})
        evaluations.append({"kind": kind, "returncode": code, "result": result, "report": str(path), "error": None})
    return {"status": "FAIL", "matrix_kind": "stage23", "row": {
        "trial": trial, "status": "FAIL", "commands": commands, "evaluations": evaluations}}


class GuardedFullPlanTests(unittest.TestCase):
    def fixture(self, root):
        root = root.resolve()
        root.mkdir(exist_ok=True)
        write(root / "planning/online_estimator_preregistration.json", {"fixture": True})
        source = root / "scripts/frozen.py"
        source.parent.mkdir()
        source.write_text("# frozen fixture\n", encoding="utf-8")
        first = [{"name": f"old_{index:03d}", "stage": 1, "matrix": "first"} for index in range(100)]
        remaining = [{"name": f"pending_{index:03d}", "stage": 2, "scenario": "crossing",
                      "matrix": "stage23"} for index in range(66)]
        plan = {"schema_version": 1, "prefix": "fullplan_fixture", "wall_timeout_s": 300.,
                "frozen_root": str(root), "source_hashes": {"scripts/frozen.py": guard.sha(source)},
                "preregistration_sha256": guard.sha(root / "planning/online_estimator_preregistration.json"),
                "trials": first + remaining, "matrices": [
                    {"kind": "stage1", "trial_names": [trial["name"] for trial in first],
                     "report": "results/old.json"},
                    {"kind": "stage23", "trial_names": [trial["name"] for trial in remaining],
                     "report": "results/study/stage23_matrix/manifest.json"}]}
        plan["plan_sha256"] = guard.digest(plan)
        write(root / "results/study/plan.json", plan)
        write(root / "results/old.json", {"trials": [
            {"name": trial["name"], "result": "FAIL" if index == 0 else "PASS"}
            for index, trial in enumerate(first)]})
        return plan

    def test_relative_output_and_one_slot_master_command_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = self.fixture(root)
            _, actual = guard.read_plan(root, "results/study", plan["plan_sha256"])
            command = guard.frozen_command(root, "results/study", actual)
            self.assertEqual(command[command.index("--output") + 1], "results/study")
            self.assertEqual(command[command.index("--stop-after") + 1], "1")
            self.assertIn("--resume", command)
            self.assertEqual(command[command.index("--phase") + 1], "flights")
            with self.assertRaisesRegex(ValueError, "relative"):
                guard.read_plan(root, str(root / "results/study"), plan["plan_sha256"])
            with self.assertRaisesRegex(ValueError, "SHA"):
                guard.read_plan(root, "results/study", "0" * 64)

    def test_source_change_is_rejected_before_any_master_invocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = self.fixture(root)
            guard.verify_sources(root, plan)
            (root / "scripts/frozen.py").write_text("# changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Frozen source"):
                guard.verify_sources(root, plan)

    def test_snapshot_preserves_hundred_terminal_failures_and_only_sixtysix_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = self.fixture(root)
            rows = guard.snapshot(root, plan)
            self.assertEqual(sum(row["status"] in guard.TERMINAL for row in rows.values()), 100)
            self.assertEqual(sum(row["status"] == "PENDING" for row in rows.values()), 66)
            self.assertEqual(rows["old_000"]["status"], "FAIL")
            (root / "results/pending_000").mkdir()
            with self.assertRaisesRegex(ValueError, "Pending trial already has artifacts"):
                guard.snapshot(root, plan)

    def test_unresolved_stage_one_or_active_stage23_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = self.fixture(root)
            old = guard.load(root / "results/old.json")
            old["trials"].pop()
            write(root / "results/old.json", old)
            with self.assertRaisesRegex(ValueError, "100 stage-one"):
                guard.snapshot(root, plan)

    def test_transition_must_consume_exactly_one_selected_slot_and_preserve_old_rows(self):
        before = {"old": {"status": "FAIL", "row": {"result": "FAIL"}},
                  "one": {"status": "PENDING", "row": None}, "two": {"status": "PENDING", "row": None}}
        after = copy.deepcopy(before)
        after["one"] = {"status": "FAIL", "row": {"result": "FAIL"}}
        guard.validate_transition(before, after, "one")
        after["two"] = {"status": "PASS", "row": {"result": "PASS"}}
        with self.assertRaisesRegex(ValueError, "another trial"):
            guard.validate_transition(before, after, "one")

    def test_first_manifest_materialization_only_changes_the_selected_slot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = self.fixture(root)
            before = guard.snapshot(root, plan)
            trials = [{key: value for key, value in trial.items() if key != "matrix"}
                      for trial in plan["trials"] if trial["stage"] in {2, 3}]
            protocol = {"fixture": True}
            slots = [{"trial": trial, "status": "PENDING"} for trial in trials]
            slots[0].update(status="FAIL", evaluations=[])
            write(root / "results/study/stage23_matrix/manifest.json", {
                "protocol": protocol, "plan_sha256": guard.digest({"protocol": protocol, "trials": trials}),
                "slots": slots})
            after = guard.snapshot(root, plan)
            guard.validate_transition(before, after, "pending_000")
            self.assertEqual(before["pending_001"], after["pending_001"])

    def test_expected_completed_negative_reports_continue_with_sitl_zero_or_monitor_timeout(self):
        for stage, scenario, verdict in ((2, "crossing", "FAIL"), (2, "crossing", "INCOMPLETE_EVIDENCE"),
                                         (2, "auto_unique", "FAIL"), (3, "gimbal", "INCOMPLETE_EVIDENCE")):
            for sitl in (0, 1):
                with self.subTest(stage=stage, verdict=verdict, sitl=sitl), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    trial = {"name": "new_trial", "stage": stage, "scenario": scenario}
                    row = healthy_trial(root, trial, sitl=sitl, verdict=verdict)
                    result = guard.assess_slot(root, trial, row)
                    self.assertFalse(result["stop"], result)
                    self.assertEqual(result["ordinary_monitor_negative_result_permitted"], sitl == 1)
                    self.assertEqual(row["status"], "FAIL")

    def test_monitor_crash_abort_or_unknown_exit_never_becomes_ordinary_negative(self):
        for code, reason in ((-11, "wall_timeout"), (1, "flight_aborted"), (9, "wall_timeout")):
            with self.subTest(code=code, reason=reason), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                trial = {"name": "new_trial", "stage": 2, "scenario": "crossing"}
                row = healthy_trial(root, trial, sitl=code, monitor_reason=reason)
                self.assertTrue(guard.assess_slot(root, trial, row)["stop"])

    def test_completed_negative_with_decoder_errors_or_missing_clock_is_infrastructure(self):
        for mutate in (lambda report: report["inputs"].update(read_errors={"/tracking/state: ValueError": 1}),
                       lambda report: report["inputs"].update(clock_samples_read=0)):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                trial = {"name": "new_trial", "stage": 2, "scenario": "crossing"}
                row = healthy_trial(root, trial, sitl=1)
                path = root / "results/new_trial/stage2_evaluation.json"
                report = guard.load(path)
                mutate(report)
                write(path, report)
                self.assertTrue(guard.assess_slot(root, trial, row)["stop"])

    def test_missing_report_and_sqlite_exception_stop_without_modifying_terminal_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trial = {"name": "new_trial", "stage": 2, "scenario": "crossing"}
            row = healthy_trial(root, trial)
            (root / "results/new_trial/stage2_evaluation.json").unlink()
            command = row["row"]["commands"][1]
            command["returncode"] = 1
            Path(command["log"]).write_text("Traceback (most recent call last):\nRuntimeError: database disk image is malformed\n", encoding="utf-8")
            before = copy.deepcopy(row)
            result = guard.assess_slot(root, trial, row)
            self.assertTrue(result["stop"])
            self.assertTrue(result["infrastructure"]["stop"])
            self.assertEqual(row, before)

    def test_unknown_schema_or_unexpected_evaluator_returncode_fail_closed(self):
        for mutation in ("schema", "returncode"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                trial = {"name": "new_trial", "stage": 2, "scenario": "crossing"}
                row = healthy_trial(root, trial)
                if mutation == "schema":
                    path = root / "results/new_trial/stage2_evaluation.json"
                    report = guard.load(path)
                    report["schema_version"] = 999
                    write(path, report)
                else:
                    row["row"]["commands"][1]["returncode"] = 1
                    row["row"]["evaluations"][0]["returncode"] = 1
                self.assertTrue(guard.assess_slot(root, trial, row)["stop"])

    def test_matrix_log_and_report_paths_must_bind_exact_current_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trial = {"id": "s2_trial", "name": "new_trial", "stage": 2, "scenario": "crossing"}
            row = healthy_trial(root, trial)
            matrix_report = root / "results/study/stage23_matrix/manifest.json"
            self.assertFalse(guard.assess_slot(root, trial, row, matrix_report=matrix_report)["stop"])
            foreign = root / "results/foreign.log"
            foreign.write_text("ordinary completed report\n", encoding="utf-8")
            row["row"]["commands"][1]["log"] = str(foreign)
            self.assertTrue(guard.assess_slot(root, trial, row, matrix_report=matrix_report)["stop"])
            row["row"]["evaluations"][0].pop("report")
            self.assertTrue(guard.assess_slot(root, trial, row)["stop"])

    def test_foreign_bag_and_mismatched_class_or_mode_reports_fail_closed(self):
        for kind in ("bag", "class", "mode"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                trial = {"name": "new_trial", "stage": 3 if kind == "mode" else 2,
                         "scenario": "gimbal" if kind == "mode" else "crossing"}
                row = healthy_trial(root, trial)
                name = "gimbal_evaluation.json" if kind == "mode" else "stage2_evaluation.json"
                path = root / "results/new_trial" / name
                report = guard.load(path)
                if kind == "bag":
                    report["inputs"]["bag"] = str(root / "results/old_trial/rosbag")
                elif kind == "class":
                    report["configuration"]["target_class"] = "car"
                else:
                    report["mode"] = "active"
                write(path, report)
                self.assertTrue(guard.assess_slot(root, trial, row)["stop"])

    def test_terminal_status_tampering_and_missing_vehicle_evidence_are_rejected(self):
        for mutation in ("status", "runtime", "decoded"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                trial = {"name": "new_trial", "stage": 3, "scenario": "gimbal"}
                row = healthy_trial(root, trial)
                if mutation == "status":
                    row["status"] = "PASS"
                    row["row"]["status"] = "PASS"
                elif mutation == "runtime":
                    (root / "results/new_trial/telemetry.jsonl").write_text("", encoding="utf-8")
                else:
                    path = root / "results/new_trial/flight_evaluation.json"
                    report = guard.load(path)
                    report["topic_message_counts"]["/vehicle/odometry"] = 0
                    write(path, report)
                self.assertTrue(guard.assess_slot(root, trial, row)["stop"])

    def test_outer_master_nonzero_stops_after_one_frozen_invocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "frozen"
            plan = self.fixture(root)
            initial = guard.snapshot(root, plan)
            after = copy.deepcopy(initial)
            after["pending_000"] = {"status": "FAIL", "row": {"result": "FAIL"}, "matrix_kind": "stage23"}
            audit = Path(temporary) / "audit"
            with patch.object(guard, "idle_writer_window", side_effect=lambda unused: nullcontext()), \
                    patch.object(guard, "verify_sources"), \
                    patch.object(guard, "snapshot", side_effect=[initial, initial, after]), \
                    patch.object(guard, "assess_slot", return_value={"stop": False}), \
                    patch.object(guard.subprocess, "run", return_value=SimpleNamespace(returncode=1)) as runner:
                self.assertEqual(guard.execute_locked(root, "results/study", plan["plan_sha256"], audit, 0), 2)
            self.assertEqual(runner.call_count, 1)
            events = [json.loads(line) for line in (audit / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(events[-1]["event"], "STOP_BEFORE_NEXT_SLOT")


if __name__ == "__main__":
    unittest.main()
