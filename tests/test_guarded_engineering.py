"""Pure independent-flight guard fixtures; never launch ROS or open a bag."""
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
SPEC = importlib.util.spec_from_file_location("guarded_engineering_fixture", ROOT / "scripts/run_guarded_engineering.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(root):
    # Windows TEMP may use an 8.3 spelling. Frozen roots use canonical paths,
    # so fixtures must use the same contract as read_plan().
    root = root.resolve()
    write(root / "planning/online_estimator_preregistration.json", {"fixture": True})
    source = root / "scripts/frozen.py"
    source.parent.mkdir()
    source.write_text("# frozen fixture\n", encoding="utf-8")
    first = [{"name": f"old_{i:03d}", "stage": 1, "matrix": "first"} for i in range(100)]
    later = [{"name": f"stage23_{i:03d}", "stage": 2, "matrix": "stage23"} for i in range(66)]
    main = {"schema_version": 1, "prefix": "main_fixture", "frozen_root": str(root),
            "source_hashes": {"scripts/frozen.py": guard.shared.sha(source)},
            "preregistration_sha256": guard.shared.sha(root / "planning/online_estimator_preregistration.json"),
            "resources": {"real_time_factor": .5, "fixture": True}, "wall_timeout_s": 300.,
            "trials": first + later, "matrices": [
                {"kind": "stage1", "trial_names": [trial["name"] for trial in first], "report": "results/first.json"},
                {"kind": "stage23", "trial_names": [trial["name"] for trial in later], "report": "results/study/stage23/manifest.json"}]}
    main["plan_sha256"] = guard.shared.digest(main)
    write(root / "results/study/plan.json", main)
    write(root / "results/first.json", {"trials": [
        {"name": trial["name"], "result": "FAIL" if i == 0 else "PASS"} for i, trial in enumerate(first)]})
    trials23 = [{key: value for key, value in trial.items() if key != "matrix"} for trial in later]
    child = {"protocol": "fixture", "slots": [{"trial": trial, "status": "PASS"} for trial in trials23]}
    child["plan_sha256"] = guard.shared.digest({"protocol": child["protocol"], "trials": trials23})
    write(root / "results/study/stage23/manifest.json", child)
    rows = [{"name": trial["name"], "result": "FAIL" if i == 0 else "PASS"} for i, trial in enumerate(main["trials"])]
    write(root / "results/study/summary.json", {"schema_version": 1, "plan_sha256": main["plan_sha256"],
        "planned_flights": 166, "all_flight_slots_terminal": True, "all_offline_slots_attempted": True,
        "status_counts": {"PASS": 165, "FAIL": 1}, "offline_status_counts": {"RECORDED": 166}, "trials": rows})
    write(root / "results/study/offline_manifest.json", {"schema_version": 1, "plan_sha256": main["plan_sha256"],
        "trials": {trial["name"]: {"name": trial["name"], "status": "RECORDED"} for trial in main["trials"]}})
    trials = []
    for i in range(16):
        trials.append({"id": f"condition_{i:03d}", "name": f"engineering_condition_{i:03d}", "stage": 1,
            "target_class": "car" if i % 2 else "person", "seed": 0, "speed_mps": .5, "condition": "clean",
            "command_mode": "velocity", "estimator_method": "adaptive_kf", "target_mode": "auto_unique",
            "motion_profile_kind": "standard", "duration_s": 45., "desired_distance_m": 5.,
            "desired_height_m": 2., "takeoff_height_m": 3., "real_time_factor": .5, "inference_image_size": 320,
            "inference_threads": 2, "weights": "models/fixture.pt", "occlusions": True,
            "reselect_after_loss": True, "scope": "single_flight_engineering_extension", "independent_repeats_per_condition": 1})
    plan = {"prefix": "engineering", "trials": trials, "expected_trials": 16, "primary_166_included": False,
            "source_hashes": main["source_hashes"], "preregistration_sha256": main["preregistration_sha256"],
            "resources": main["resources"], "wall_timeout_s": 300., "render_backend": "egl"}
    manifest = {"schema_version": 1, "source": "EXTENDED_ENGINEERING_16_FLIGHTS", "plan": plan,
                "plan_sha256": guard.shared.digest(plan), "slots": [{"trial": trial, "status": "PENDING"} for trial in trials]}
    write(root / "results/engineering/manifest.json", manifest)
    return main, manifest


def healthy_slot(root, manifest, index, *, verdict="FAIL", sitl=0):
    slot = manifest["slots"][index]
    trial, plan = slot["trial"], manifest["plan"]
    directory = root / "results" / trial["name"]
    bag = directory / "rosbag"
    write(bag / "metadata.yaml", {"rosbag2_bagfile_information": {"message_count": 200,
        "topics_with_message_count": [{"topic_metadata": {"name": name}, "message_count": 100}
                                      for name in ("/clock", "/vehicle/odometry")],
        "relative_file_paths": ["fixture.db3.zstd"]}})
    (bag / "fixture.db3.zstd").write_bytes(b"fixture-never-to-be-opened-by-guard")
    write(directory / "summary.json", {"termination_reason": "wall_timeout", "monitor_exit_code": sitl,
                                       "max_vehicle_altitude_m": 3.})
    write(directory / "process_exit_codes.json", {"ros": 0, "px4": 0, "bag": 0, "agent": -2, "monitor": sitl})
    (directory / "telemetry.jsonl").write_text(json.dumps({"kind": "telemetry", "time_s": 1.,
        "position": [0., 0., 3.], "phase": "FOLLOW"}) + "\n", encoding="utf-8")
    runtime = {key: value for key, value in trial.items()}
    runtime.update(duration=trial["duration_s"], wall_timeout=plan["wall_timeout_s"], render_backend=plan["render_backend"],
                   no_bag=False, multi_target=False, gazebo_seed=1, model_path=str(root / trial["weights"]))
    write(directory / "run_config.json", runtime)
    report = {"schema_version": 3, "source": "OFFLINE_STAGE1_ROSBAG_EVALUATION", "acceptance": {"result": verdict},
        "configuration": {"target_class": trial["target_class"], "desired_distance_m": trial["desired_distance_m"],
                          "desired_height_m": trial["desired_height_m"], "start_s": None, "end_s": None},
        "topic_message_counts": {"/vehicle/odometry": 100}, "inputs": {
            "clock_recorded": True, "clock_samples_read": 100, "read_errors": {}, "unavailable_types": {},
            "topic_types": {"/clock": "Clock", "/vehicle/odometry": "Odometry"}, "bag": str(bag.resolve()),
            "telemetry_jsonl": str((directory / "telemetry.jsonl").resolve()),
            "monitor_summary": str((directory / "summary.json").resolve())}}
    report_path = directory / "offline_evaluation.json"
    write(report_path, report)
    commands = []
    for kind, code in (("sitl", sitl), ("flight_eval", 0)):
        log = root / "results/engineering/logs" / f"{trial['id']}_{kind}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("normal completed invocation\n", encoding="utf-8")
        commands.append({"kind": kind, "returncode": code, "log": str(log)})
    slot.update(status="PASS" if verdict == "PASS" and sitl == 0 else "FAIL", commands=commands,
        evaluations=[{"kind": "schema3_flight", "returncode": 0, "result": verdict, "report": str(report_path),
                      "sha256": guard.shared.sha(report_path), "error": None}])
    return slot, report_path


class GuardedEngineeringTests(unittest.TestCase):
    def test_all_actual_main_flights_and_offline_rows_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            main, _ = fixture(root)
            _, protected = guard.main_readiness(root, "results/study", main["plan_sha256"])
            self.assertEqual(len(protected), 5)
            path = root / "results/study/stage23/manifest.json"
            child = guard.shared.load(path)
            child["slots"][0]["status"] = "PENDING"
            write(path, child)
            with self.assertRaisesRegex(ValueError, "166 flight"):
                guard.main_readiness(root, "results/study", main["plan_sha256"])

    def test_missing_foreign_or_active_offline_evidence_rejected(self):
        for fault in ("missing", "foreign", "RUNNING_ANALYSIS", "UNKNOWN", "counts"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                main, _ = fixture(root)
                path = root / "results/study/offline_manifest.json"
                value = guard.shared.load(path)
                if fault == "missing":
                    del value["trials"]["old_000"]
                elif fault == "foreign":
                    value["trials"]["foreign"] = value["trials"].pop("old_000")
                elif fault == "counts":
                    value["trials"]["old_000"]["status"] = "INCOMPLETE_EVIDENCE"
                else:
                    value["trials"]["old_000"]["status"] = fault
                write(path, value)
                with self.assertRaisesRegex(ValueError, "offline"):
                    guard.main_readiness(root, "results/study", main["plan_sha256"])

    def test_main_summary_cannot_invent_terminal_status_or_counts(self):
        for field, value in (("all_flight_slots_terminal", False), ("status_counts", {"PASS": 166}),
                             ("all_offline_slots_attempted", False), ("plan_sha256", "foreign")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                main, _ = fixture(root)
                path = root / "results/study/summary.json"
                summary = guard.shared.load(path)
                summary[field] = value
                write(path, summary)
                with self.assertRaisesRegex(ValueError, "summary"):
                    guard.main_readiness(root, "results/study", main["plan_sha256"])

    def test_engineering_source_plan_and_slot_bindings_checked(self):
        for fault in ("digest", "sources", "resources", "preregistration", "slot", "active", "sixteen", "artifact"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                main, manifest = fixture(root)
                if fault == "digest":
                    manifest["plan_sha256"] = "invalid"
                elif fault in {"sources", "resources", "preregistration"}:
                    key = {"sources": "source_hashes", "resources": "resources", "preregistration": "preregistration_sha256"}[fault]
                    manifest["plan"][key] = "foreign"
                    manifest["plan_sha256"] = guard.shared.digest(manifest["plan"])
                elif fault == "slot":
                    manifest["slots"][1]["trial"] = manifest["slots"][0]["trial"]
                elif fault == "active":
                    manifest["slots"][0]["status"] = "RUNNING_FLIGHT"
                elif fault == "sixteen":
                    manifest["slots"].pop()
                else:
                    (root / "results" / manifest["plan"]["trials"][0]["name"]).mkdir()
                write(root / "results/engineering/manifest.json", manifest)
                with self.assertRaises(ValueError):
                    guard.read_engineering(root, "results/engineering", main)

    def test_exact_frozen_command_keeps_relative_output_and_single_slot_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, manifest = fixture(root)
            command = guard.frozen_command(root, "results/engineering", manifest)
            self.assertEqual(command[command.index("--output") + 1], "results/engineering")
            self.assertEqual(command[command.index("--stop-after") + 1], "1")
            self.assertEqual(Path(command[2]), root / "scripts/run_extended_engineering.py")
            self.assertIn("--resume", command)
            with self.assertRaisesRegex(ValueError, "relative"):
                guard.relative_output(root, str(root / "results/engineering"))

    def test_only_one_selected_row_can_change_and_old_failures_remain(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, before = fixture(Path(temporary))
            before["slots"][0]["status"] = "FAIL"
            after = copy.deepcopy(before)
            after["slots"][1]["status"] = "PASS"
            selected = before["slots"][1]["trial"]["name"]
            guard.validate_transition(before, after, selected)
            self.assertEqual(guard.expected_outer_returncode(after), 2)
            after["slots"][0]["status"] = "PASS"
            with self.assertRaisesRegex(ValueError, "Only the selected"):
                guard.validate_transition(before, after, selected)

    def test_completed_negative_report_is_not_an_execution_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, manifest = fixture(root)
            for index, sitl in enumerate((0, 1)):
                slot, _ = healthy_slot(root, manifest, index, sitl=sitl)
                result = guard.assess_slot(root, slot["trial"], slot, manifest, root / "results/engineering/manifest.json")
                self.assertFalse(result["stop"], result)
                self.assertEqual(result["ordinary_monitor_negative_result_permitted"], sitl == 1)

    def test_foreign_report_inputs_references_and_runtime_config_stop(self):
        faults = ("bag", "telemetry_jsonl", "monitor_summary", "class", "distance", "height", "window", "runtime", "sha", "decoded")
        for fault in faults:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, manifest = fixture(root)
                slot, path = healthy_slot(root, manifest, 0)
                report = guard.shared.load(path)
                if fault in {"bag", "telemetry_jsonl", "monitor_summary"}:
                    report["inputs"][fault] = str(root / "results/foreign")
                elif fault in {"class", "distance", "height", "window"}:
                    key = {"class": "target_class", "distance": "desired_distance_m", "height": "desired_height_m", "window": "start_s"}[fault]
                    report["configuration"][key] = "foreign" if fault == "class" else 99.
                elif fault == "runtime":
                    config = guard.shared.load(path.parent / "run_config.json")
                    config["real_time_factor"] = 1.
                    write(path.parent / "run_config.json", config)
                elif fault == "sha":
                    slot["evaluations"][0]["sha256"] = "foreign"
                else:
                    report["topic_message_counts"]["/vehicle/odometry"] = 0
                write(path, report)
                if fault != "sha":
                    slot["evaluations"][0]["sha256"] = guard.shared.sha(path)
                self.assertTrue(guard.assess_slot(root, slot["trial"], slot, manifest,
                    root / "results/engineering/manifest.json")["stop"])

    def test_missing_report_external_sqlite_log_and_unexpected_codes_stop(self):
        for fault in ("missing", "sqlite", "exception", "eval_code", "sitl_code", "status", "log"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, manifest = fixture(root)
                slot, report = healthy_slot(root, manifest, 0)
                bag = report.parent / "rosbag/fixture.db3.zstd"
                before = bag.read_bytes()
                if fault == "missing":
                    report.unlink()
                elif fault in {"sqlite", "exception"}:
                    Path(slot["commands"][1]["log"]).write_text("SQLite error (11): database disk image is malformed\n"
                        if fault == "sqlite" else "Traceback (most recent call last):\nValueError: unexpected\n", encoding="utf-8")
                elif fault == "eval_code":
                    slot["commands"][1]["returncode"] = 2
                    slot["evaluations"][0]["returncode"] = 2
                elif fault == "sitl_code":
                    slot["commands"][0]["returncode"] = 139
                elif fault == "status":
                    slot["status"] = "PASS"
                else:
                    slot["commands"][1]["log"] = slot["commands"][0]["log"]
                self.assertTrue(guard.assess_slot(root, slot["trial"], slot, manifest,
                    root / "results/engineering/manifest.json")["stop"])
                self.assertEqual(bag.read_bytes(), before)

    def test_protected_main_file_change_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            main, _ = fixture(root)
            _, protected = guard.main_readiness(root, "results/study", main["plan_sha256"])
            path = root / "results/first.json"
            write(path, {"unexpected": True})
            with self.assertRaisesRegex(ValueError, "Protected main ledger"):
                guard.verify_unchanged(protected, {})

    def test_historical_failure_outer_code_two_allows_next_completed_slot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            main, manifest = fixture(root)
            _, protected = guard.main_readiness(root, "results/study", main["plan_sha256"])
            manifest["slots"][0]["status"] = "FAIL"
            path = root / "results/engineering/manifest.json"
            write(path, manifest)
            audit = root / "audit"
            audit.mkdir()
            names = []

            def runner(*args, **kwargs):
                current = guard.shared.load(path)
                index = next(i for i, slot in enumerate(current["slots"]) if slot["status"] == "PENDING")
                names.append(current["slots"][index]["trial"]["name"])
                healthy_slot(root, current, index, verdict="FAIL" if index == 1 else "PASS")
                write(path, current)
                return SimpleNamespace(returncode=2)

            with patch.object(guard.shared, "idle_writer_window", lambda _: nullcontext()), patch.object(guard.subprocess, "run", runner):
                code = guard.continue_slots(root, main, "results/engineering", manifest["plan_sha256"], protected, {},
                                            ["frozen-one-slot-command"], audit, 2)
            self.assertEqual(code, 0)
            self.assertEqual(names, [manifest["slots"][i]["trial"]["name"] for i in (1, 2)])
            self.assertEqual(guard.shared.load(path)["slots"][0]["status"], "FAIL")

    def test_external_evaluator_io_error_stops_before_another_slot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            main, manifest = fixture(root)
            _, protected = guard.main_readiness(root, "results/study", main["plan_sha256"])
            path = root / "results/engineering/manifest.json"
            audit = root / "audit"
            audit.mkdir()
            calls = []

            def runner(*args, **kwargs):
                calls.append(True)
                current = guard.shared.load(path)
                slot, _ = healthy_slot(root, current, 0)
                Path(slot["commands"][1]["log"]).write_text("SQLite error (11): database disk image is malformed\n", encoding="utf-8")
                write(path, current)
                return SimpleNamespace(returncode=2)

            with patch.object(guard.shared, "idle_writer_window", lambda _: nullcontext()), patch.object(guard.subprocess, "run", runner):
                code = guard.continue_slots(root, main, "results/engineering", manifest["plan_sha256"], protected, {},
                                            ["frozen-one-slot-command"], audit, 0)
            self.assertEqual(code, 2)
            self.assertEqual(len(calls), 1)
            remaining = guard.shared.load(path)["slots"]
            self.assertEqual(sum(slot["status"] == "PENDING" for slot in remaining), 15)

    def test_unexpected_outer_returncode_stops_even_with_a_clean_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            main, manifest = fixture(root)
            _, protected = guard.main_readiness(root, "results/study", main["plan_sha256"])
            path = root / "results/engineering/manifest.json"
            audit = root / "audit"
            audit.mkdir()
            calls = []

            def runner(*args, **kwargs):
                calls.append(True)
                current = guard.shared.load(path)
                healthy_slot(root, current, 0, verdict="PASS")
                write(path, current)
                return SimpleNamespace(returncode=137)

            with patch.object(guard.shared, "idle_writer_window", lambda _: nullcontext()), patch.object(guard.subprocess, "run", runner):
                code = guard.continue_slots(root, main, "results/engineering", manifest["plan_sha256"], protected, {},
                                            ["frozen-one-slot-command"], audit, 0)
            self.assertEqual(code, 2)
            self.assertEqual(len(calls), 1)
            events = [json.loads(line) for line in (audit / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            finish = next(event for event in events if event["event"] == "ONE_SLOT_FINISHED")
            self.assertFalse(finish["assessment"]["stop"])
            self.assertEqual(finish["expected_runner_returncode"], 0)


if __name__ == "__main__":
    unittest.main()
