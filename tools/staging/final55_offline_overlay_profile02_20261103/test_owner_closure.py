"""In-memory synthetic owner04 receipts only; no processes, native trees or bags."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("owner04_closure_tests", Path(__file__).with_name("validate_owner_closure.py"))
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)
BASE = datetime(2020, 1, 1, tzinfo=timezone.utc)
NOW = BASE + timedelta(days=1)


def utc(seconds):
    return (BASE + timedelta(seconds=seconds)).isoformat()


def win(pid, seconds):
    stamp = BASE + timedelta(seconds=seconds)
    filetime = int(stamp.timestamp()) * 10000000 + 116444736000000000
    return {"pid": pid, "alive": True, "start_token": "windows_filetime:" + str(filetime), "created_utc": stamp.isoformat()}


class Fixture:
    def __init__(self):
        self.files = {}
        self.outer_root = r"C:\fixture\outer"
        self.monitor_root = r"C:\fixture\monitor"
        self.native_root = "/root/synthetic_owner"
        self.boot = "12345678-1234-1234-1234-123456789abc"
        self.launcher = win(100, 0)
        self.monitor = win(101, 2)
        self.wsl = win(102, 4)
        source = {name: self.put("C:\\fixture\\" + name + ".py", ("SYNTHETIC INERT SOURCE " + name).encode())
                  for name in ("launcher", "monitor", "collector", "entry")}
        scanner = {f"scripts/synthetic_flight_{index:03}.py": "1" * 64 for index in range(185)}
        model_info = {"person": {"model": "models/synthetic_person.pt", "model_sha256": "3" * 64},
                      "car": {"model": "models/synthetic_car.pt", "model_sha256": "7" * 64}}
        model_hashes = {row["model"]: row["model_sha256"] for row in model_info.values()}
        source_map = {**scanner, "config/dds_runtime_humble22.json": "2" * 64, **model_hashes,
                      **{f"config/synthetic_{index:03}.json": "4" * 64 for index in range(120)}}
        capture_maps = {model: {**scanner, **{name: "5" * 64 for name in v.APPROVED_NESTED17},
                               "config/dds_runtime_humble22.json": "2" * 64, model: model_sha}
                        for model, model_sha in model_hashes.items()}
        captured_by_model = {model: self.encoded(value) for model, value in capture_maps.items()}
        trials = [{"id": f"synthetic_slot_{index:02}", "name": f"synthetic_trial_{index:02}",
                   "flight_command": ["SYNTHETIC_NO_COMMAND_EXECUTION", str(index)],
                   "directory": "/mnt/c/fixture/results/trial_" + str(index), "target_class": "person" if index < 8 else "car",
                   "model": model_info["person" if index < 8 else "car"]["model"]} for index in range(16)]
        for trial in trials:
            trial["evaluations"] = [{"kind": kind, "report": v.join(trial["directory"], kind + ".json"),
                                     "command": ["SYNTHETIC_NO_EVALUATOR_EXECUTION", kind, trial["id"]]}
                                    for kind in ("source_clock", "native_startup", "surface_flight", "navigation")]
        plan = {"mode": "EXTENSION_PROBE", "selected_seeds": [4], "trials": trials, "frozen_root": "/root/synthetic_frozen",
                "source_hashes": source_map, "results_root": "/mnt/c/fixture/results", "output": "/mnt/c/fixture/results/matrix", "model_hashes": model_hashes,
                "protocol": {"resources": {target: {"model": row["model"]} for target, row in model_info.items()}}}
        plan["plan_sha256"] = v.content_digest(plan, "plan_sha256")
        source["plan"] = self.put(r"C:\fixture\results\matrix\plan.json", plan)
        self.profile = {"source_files": source, "plan_digest": plan["plan_sha256"],
                        "source_digest": v.sha(v.canonical(source_map)),
                        "class_model_contract": {target: {**row, "capture_sha256": v.sha(captured_by_model[row["model"]])} for target, row in model_info.items()},
                        "native_plan_alias": "/root/synthetic_source/results/matrix/plan.json"}
        core = {**deepcopy(plan), "mode": "PROBE", "trials": deepcopy(trials[:12])}
        core["plan_sha256"] = v.content_digest(core, "plan_sha256")
        core_binding = self.put(r"C:\fixture\core_plan.json", core)
        before_entries = {name: {"kind": "file", "bytes": 1, "sha256": value}
                          for name, value in {**source_map, **{name: "5" * 64 for name in v.APPROVED_NESTED17}}.items()}
        before_entries.update({f"docs/ignored_{index:04}.md": {"kind": "file", "bytes": 1, "sha256": "6" * 64} for index in range(1260)})
        before_binding = self.put(r"C:\fixture\source_before.json", {"entries": before_entries})
        self.profile["snapshot_audit_contract"] = self.put(r"C:\fixture\snapshot_audit_contract.json", {
            "kind": "RELIABILITY_V4_FROZEN_SNAPSHOT_AUDIT_CONTRACT", "frozen_root": plan["frozen_root"],
            "rule": "ORIGINAL_RUN_STAGE1_PY_SH_MSG_SCAN_PLUS_SELECTED_MODEL_AND_EXPLICIT_DDS",
            "core_plan": {**core_binding, "plan_sha256": core["plan_sha256"]}, "source_before": before_binding})
        sources = {"events": r"\\wsl.localhost\UAVHumble22\root\synthetic_owner\events.jsonl",
                   "ledger": r"\\wsl.localhost\UAVHumble22\root\synthetic_owner\state.json", "plan": source["plan"]["path"]}
        native_command = ["wsl.exe", "--distribution", "UAVHumble22", "--exec", "python3", "-B",
                          v.mounted(source["collector"]["path"]), "--plan", self.profile["native_plan_alias"],
                          "--entry", v.mounted(source["entry"]["path"]), "--after-slot", "__before_first__",
                          "--output", self.native_root, "--execute"]
        desc = {"scope": "WINDOWS_OWNER_OF_PINNED_NEW_COMPLETE_DEVELOPMENT_MATRIX", "claim_boundary": "SYNTHETIC FIXTURE ONLY",
                "pins": {key: value for key, value in source.items() if key != "launcher"}, "task_id": "synthetic_owner04",
                "native_owner": self.native_root, "owner_unc": r"\\wsl.localhost\UAVHumble22\root\synthetic_owner",
                "canonical_native_plan": v.mounted(source["plan"]["path"]), "monitor_output": self.monitor_root,
                "receipt_output": self.outer_root, "sources": sources, "native_command": native_command,
                "monitor_command": ["SYNTHETIC_NO_COMMAND_EXECUTION"], "power_flags": 0x80000003,
                "power_scope": "TEMPORARY_SYSTEM_AND_DISPLAY_REQUEST_ON_THIS_OWNER_THREAD", "global_power_policy_changed": False,
                "automatic_retry": False}
        self.profile["description"] = deepcopy(desc)
        lease = {"monitor_identity": self.monitor, "accepted_utc": utc(3), "request_return": 0x80000000,
                 "flags": 0x80000003, "global_power_policy_changed": False}
        self.started = {**desc, "status": "STARTING", "started_utc": utc(1), "launcher_source": source["launcher"],
                        "launcher_identity": self.launcher, "monitor_identity": self.monitor, "errors": [],
                        "monitor_handle_acquired_utc": utc(3), "power_lease": lease}
        task = {"id": desc["task_id"], "label": desc["task_id"], "phase": "simulation", "started_utc": utc(5),
                "process": self.wsl, "finished_utc": None, "returncode": None, "monitor_kind": "owned_child"}
        self.first_monitor = {"monitor_process": self.monitor, "sources": sources, "task": task,
                              "tasks": [task], "heartbeat_utc": utc(6)}
        owner = {"pid": 103, "boot_id": self.boot, "start_ticks": 1000}
        self.first_native = {"scope": "SUPERVISED_PENDING_COLLECTION", "status": "RUNNING", "started_utc": utc(7),
                             "plan": desc["canonical_native_plan"], "plan_sha256": plan["plan_sha256"],
                             "plan_file_sha256": source["plan"]["sha256"], "entry_sha256": source["entry"]["sha256"],
                             "owner_source": {"path": v.mounted(source["collector"]["path"]), "sha256": source["collector"]["sha256"]},
                             "owner_pid": 103, "owner_identity": owner, "initial_closed": [], "collected": [],
                             "automatic_retry": False, "heartbeat_utc": utc(8)}
        self.markers, self.terminals, collected = [], [], []
        events = [{"event": "COLLECTION_STARTED", "utc": utc(9), "scope": "SUPERVISED_PENDING_COLLECTION",
                   "pending_ids": [trial["id"] for trial in trials]}]
        for index, trial in enumerate(trials):
            second = 10 + index * 60
            marker = {"id": trial["id"], "plan_sha256": plan["plan_sha256"], "started_utc": utc(second + 1),
                      "flight_command": trial["flight_command"]}
            marker_binding = self.put(v.join(plan["output"], "slots/" + trial["id"] + ".started.json"), marker)
            artifacts = {}
            for name in ("recording_closure.json", "bag_integrity.json", "configuration/source_sha256.json"):
                artifacts[name] = self.put(v.join(trial["directory"], name), captured_by_model[trial["model"]] if "source_sha" in name else {"status": "PASS"})["sha256"]
            status = ("PASS", "FAIL", "INCOMPLETE_EVIDENCE")[index % 3]
            runtime = {"errors": []}
            for name, field, payload in (("run_config.json", "run_config_sha256", {}),
                                          ("configuration/runtime_parameters.yaml", "runtime_parameters_sha256", b"SYNTHETIC_INERT_PARAMETERS\n")):
                artifacts[name] = self.put(v.join(trial["directory"], name), payload)["sha256"]
                runtime[field] = artifacts[name]
            evaluations = []
            for eval_index, spec in enumerate(trial["evaluations"]):
                if spec["kind"] == "surface_flight":
                    verdict = "FAIL" if status == "FAIL" else "PASS"
                    windows = [{"kind": kind, "complete": True,
                                "checks": {key: True for key in (*v.SHUTTER_CHECKS, *v.LONG_SAFE_CHECKS, *v.BEHAVIOR_CHECKS[kind])}}
                               for kind in ("short", "long")]
                    if status == "FAIL":
                        windows[0]["checks"]["prediction_observed"] = False
                    report = {"acceptance": {"result": verdict, "missing_topics": [], "input_read_error_count": 0,
                                              "clock_timebase_available": True, "short_occlusion_recorded": True,
                                              "long_occlusion_recorded": True, "failed_events_retained": True},
                              "flight_evidence": {"armed_seen": True, "offboard_seen": True},
                              "detector": {"invalid_diagnostic_messages": 0}, "occlusions": windows}
                else:
                    verdict = "INCOMPLETE_EVIDENCE" if spec["kind"] == "navigation" and status == "INCOMPLETE_EVIDENCE" else "PASS"
                    report = {"evaluation_status": verdict}
                binding = self.put(spec["report"], report)
                artifacts[Path(spec["report"]).name] = binding["sha256"]
                evaluations.append({"kind": spec["kind"], "report": spec["report"], "report_sha256": binding["sha256"],
                                    "error": None, "result": verdict, "reported_verdict": verdict,
                                    "execution": {"command": spec["command"], "returncode": 0, "error": None,
                                                  "started_utc": utc(second + 31 + eval_index), "finished_utc": utc(second + 31.5 + eval_index)}})
            terminal = {"id": trial["id"], "name": trial["name"], "plan_sha256": plan["plan_sha256"],
                        "started_utc": marker["started_utc"], "finished_utc": utc(second + 40), "status": status,
                        "engineering_result": status, "execution_status": "COMPLETED", "infrastructure_stop": False,
                        "infrastructure": {"stop": False}, "cleanup": {"residual_processes": []},
                        "runtime_configuration": runtime, "flight_exit_code": 0, "artifact_hashes": artifacts, "evaluations": evaluations,
                        "commands": [{"kind": "flight", "command": trial["flight_command"], "returncode": 0,
                                      "error": None, "started_utc": utc(second + 2), "finished_utc": utc(second + 30)}]}
            terminal["record_sha256"] = v.content_digest(terminal, "record_sha256")
            terminal_binding = self.put(v.join(plan["output"], "slots/" + trial["id"] + ".json"), terminal)
            row = {"slot_id": trial["id"], "original_status": status, "terminal_sha256": terminal_binding["sha256"],
                   "original_terminal": terminal_binding, "original_marker": marker_binding,
                   "original_started_utc": marker["started_utc"], "original_finished_utc": terminal["finished_utc"],
                   "record_sha256": terminal["record_sha256"], "known_algorithm_failures": [], "unobserved_checks": []}
            collected.append(row)
            self.markers.append(marker)
            self.terminals.append(terminal)
            command = ["bash", v.mounted(source["entry"]["path"]), trial["id"]]
            events.extend([
                {"event": "START_SLOT", "utc": utc(second), "scope": "SUPERVISED_PENDING_COLLECTION", "slot": trial["id"],
                 "pid": 2000 + index, "command": command, "executed_by_this_owner": True,
                 "event_semantics": "ACTUAL_CHILD_INVOCATION", "total": 16},
                {"event": "CHILD_EXIT", "utc": utc(second + 42), "scope": "SUPERVISED_PENDING_COLLECTION",
                 "slot": trial["id"], "returncode": 0},
                {"event": "COMPLETE_SLOT", "utc": utc(second + 43), "scope": "SUPERVISED_PENDING_COLLECTION", "slot": trial["id"],
                 "status": status, "terminal_sha256": terminal_binding["sha256"], "executed_by_this_owner": True,
                 "event_semantics": "ACTUAL_CHILD_EXIT_AND_ORIGINAL_TERMINAL_VERIFIED", "total": 16}])
        self.native_end = 10 + 15 * 60 + 44
        events.append({"event": "COLLECTION_FINISHED", "utc": utc(self.native_end + 1), "scope": "SUPERVISED_PENDING_COLLECTION", "collected_slots": 16})
        self.events = events
        self.native = {**deepcopy(self.first_native), "status": "COLLECTION_FINISHED", "current_slot": None,
                       "collected": collected, "returncode": 0, "finished_utc": utc(self.native_end),
                       "current_child": {"pid": 2015, "returncode": 0, "command": command, "started_utc": utc(second),
                                         "finished_utc": utc(second + 41),
                                         "identity": {"pid": 2015, "start_ticks": 2000, "boot_id": self.boot}}}
        final_task = {**deepcopy(task), "returncode": 0, "finished_utc": utc(self.native_end + 5)}
        self.final_monitor = {**deepcopy(self.first_monitor), "task": final_task, "tasks": [final_task],
                              "heartbeat_utc": utc(self.native_end + 5)}
        self.end = {"status": "COMPLETED", "completion_scope": "monitored_command", "task": final_task,
                    "tasks": [final_task], "evidence_sources": sources, "generated_utc": utc(self.native_end + 6),
                    "monitor_check": {"verified_alive": True}, "evidence": {"last_slot": None}}
        self.outer = {**deepcopy(self.started), "status": "COLLECTION_ENDED", "closure_verified": True,
                      "wsl_identity": self.wsl, "wsl_handle_acquired_utc": utc(6), "first_native_owner_identity": owner,
                      "first_native_owner_source": self.native["owner_source"], "first_native_started_utc": utc(7),
                      "first_native_state_observed_utc": utc(8), "native_owner_identity": owner,
                      "native_collection_status": "COLLECTION_FINISHED", "collected_slots": 16,
                      "monitor_exit_code": 0, "wsl_exit_code": 0, "monitor_popen_wait_exit_code": 0,
                      "monitor_final_popen_wait_exit_code": 0, "monitor_final_handle_exit_code": 0, "wsl_final_handle_exit_code": 0,
                      "wsl_first_exit_observed_utc": utc(self.native_end + 3),
                      "monitor_first_exit_observed_utc": utc(self.native_end + 7),
                      "windows_handles_closed_observation_utc": utc(self.native_end + 8),
                      "wsl_final_exit_observed_utc": utc(self.native_end + 9),
                      "monitor_final_exit_observed_utc": utc(self.native_end + 10), "finished_utc": utc(self.native_end + 12)}
        self.outer["power_lease"].update(release_return=0x80000003, released_utc=utc(self.native_end + 11))
        self.refresh()

    @staticmethod
    def encoded(value):
        return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()

    def put(self, path, value):
        payload = value if isinstance(value, bytes) else self.encoded(value)
        self.files[v.path_key(path)] = payload
        return {"path": path, "sha256": v.sha(payload)}

    def read(self, path):
        return self.files[v.path_key(path)]

    def refresh(self):
        artifacts = {}
        for name, value in (("started.json", self.started), ("first_monitor_state.json", self.first_monitor),
                            ("first_native_state.json", self.first_native), ("native_terminal.json", self.native),
                            ("final_monitor_state.json", self.final_monitor), ("state.json", self.started),
                            ("monitor_stdout.log", b"SYNTHETIC\n"), ("monitor_stderr.log", b"")):
            artifacts[name] = self.put(v.join(self.outer_root, name), value)["sha256"]
        self.profile["launch_files"] = {key: {"path": v.join(self.outer_root, name), "sha256": artifacts[name]}
                                         for key, name in (("started", "started.json"), ("first_monitor", "first_monitor_state.json"),
                                                           ("first_native", "first_native_state.json"))}
        self.outer["artifacts"] = artifacts
        self.outer["native_owner_terminal_sha256"] = artifacts["native_terminal.json"]
        self.profile["closure_files"] = {
            "outer_terminal": self.put(v.join(self.outer_root, "terminal.json"), self.outer),
            "native_terminal": self.put(v.join(self.native_root, "terminal.json"), self.native),
            "monitor_final": self.put(v.join(self.monitor_root, "monitor_state.json"), self.final_monitor),
            "monitor_end": self.put(v.join(self.monitor_root, "end_summary.json"), self.end),
            "events": self.put(v.join(self.native_root, "events.jsonl"), b"\n".join(v.canonical(row) for row in self.events) + b"\n")}


class OwnerClosureTests(unittest.TestCase):
    def test_mounted_windows_drive_conversion_uses_exact_canonical_segments(self):
        self.assertEqual(v.windows_mounted_reference("/mnt/d/a/b.json"), "D:/a/b.json")
        self.assertEqual(v.windows_mounted_reference("/mnt/c/x.json"), "C:/x.json")
        with self.assertRaises(v.Refused):
            v.windows_mounted_reference("/mnt/dd/x.json")

    def test_independent_slot_uses_exact_capture204_separately_from_source308(self):
        fixture = Fixture()
        inputs = v.Inputs(fixture.read)
        plan = inputs.json(fixture.profile["source_files"]["plan"])
        captures = v.snapshot_capture_contract(fixture.profile, inputs, plan)
        self.assertEqual(len(plan["source_hashes"]), 308)
        self.assertEqual(len(captures), 2)
        for expected in captures.values():
            self.assertEqual(len(expected["entries"]), 204)
            self.assertEqual(set(expected["entries"]) - set(plan["source_hashes"]), set(v.APPROVED_NESTED17))
        # Does not consume any outer, full16 events or fabricated continuation.
        result = v.validate_slot(inputs, plan, plan["trials"][8], fixture.native["collected"][8], captures, NOW)
        self.assertEqual(result["id"], plan["trials"][8]["id"])
        self.assertEqual(result["original_status"], "INCOMPLETE_EVIDENCE")

    def test_actual_launch_and_both_named_original_capture_shapes_match(self):
        project = Path(__file__).resolve().parents[3]
        actual_root = project / "results/frozen_fullplan_v4_humble54"
        if not (actual_root / "reliability_v4_humble54_core12_probe01_matrix/plan.json").is_file():
            self.skipTest("Named actual small metadata is unavailable; synthetic tests remain independent")
        profile = v.load_production()
        context = v.validate_launch(profile)
        captures = v.snapshot_capture_contract(profile, context["inputs"], context["plan"])
        for target in ("person", "car"):
            path = actual_root / ("reliability_v4_humble54_core12_probe01_" + target + "_stage1_velocity_seed004") / "configuration/source_sha256.json"
            raw = path.read_bytes()
            model = profile["class_model_contract"][target]["model"]
            self.assertEqual(v.sha(raw), captures[model]["sha256"])
            self.assertEqual(v.parse(raw), captures[model]["entries"])
            self.assertEqual(len(captures[model]["entries"]), 204)
        # The production Inputs reader must map only the authenticated plan's
        # results alias. No custom test reader may hide a symlink traversal bug.
        core = v.parse((actual_root / "reliability_v4_humble54_core12_probe01_matrix/plan.json").read_bytes())
        for target in ("person", "car"):
            trial = next(row for row in core["trials"] if row["target_class"] == target)
            marker_path = v.join(core["output"], "slots/" + trial["id"] + ".started.json")
            terminal_path = v.join(core["output"], "slots/" + trial["id"] + ".json")
            marker_raw, terminal_raw = v.local_small_read(marker_path), v.local_small_read(terminal_path)
            marker, terminal = v.parse(marker_raw), v.parse(terminal_raw)
            row = {"original_marker": {"path": marker_path, "sha256": v.sha(marker_raw)},
                   "original_terminal": {"path": terminal_path, "sha256": v.sha(terminal_raw)},
                   "terminal_sha256": v.sha(terminal_raw), "record_sha256": terminal["record_sha256"],
                   "original_status": terminal["status"], "original_started_utc": marker["started_utc"],
                   "original_finished_utc": terminal["finished_utc"], "unobserved_checks": []}
            result = v.validate_slot(v.Inputs(v.local_small_read), core, trial, row, captures, datetime.now(timezone.utc))
            self.assertEqual(result["original_status"], terminal["status"])
        context["inputs"].unchanged()

    def test_default_reader_real_new_probe02_first_slot(self):
        project = Path(__file__).resolve().parents[3]
        matrix = project / "results/frozen_fullplan_v4_humble54/reliability_v4_humble54_extension16_probe02_matrix"
        if not (matrix / "slots/person_extension_depth_noise_seed004.json").is_file():
            self.skipTest("Named actual first terminal not available; no future result is assumed")
        profile = v.load_production()
        inputs = v.Inputs(v.local_small_read)
        plan = inputs.json(profile["source_files"]["plan"])
        captures = v.snapshot_capture_contract(profile, inputs, plan)
        trial = plan["trials"][0]
        marker_path = v.join(plan["output"], "slots/" + trial["id"] + ".started.json")
        terminal_path = v.join(plan["output"], "slots/" + trial["id"] + ".json")
        marker_raw, terminal_raw = v.local_small_read(marker_path), v.local_small_read(terminal_path)
        marker, terminal = v.parse(marker_raw), v.parse(terminal_raw)
        row = {"original_marker": {"path": marker_path, "sha256": v.sha(marker_raw)},
               "original_terminal": {"path": terminal_path, "sha256": v.sha(terminal_raw)},
               "terminal_sha256": v.sha(terminal_raw), "record_sha256": terminal["record_sha256"],
               "original_status": terminal["status"], "original_started_utc": marker["started_utc"],
               "original_finished_utc": terminal["finished_utc"], "unobserved_checks": []}
        result = v.validate_slot(inputs, plan, trial, row, captures, datetime.now(timezone.utc))
        self.assertEqual(result["original_status"], terminal["status"])
        self.assertIn(plan["frozen_root"] + "/results", inputs.results_aliases)

    def test_authenticated_results_alias_preserves_references_and_external_owner(self):
        calls = []
        def read(reference):
            calls.append(reference)
            return b"SMALL_SYNTHETIC_BYTES"
        plan = {"frozen_root": "/root/known_frozen", "results_root": "/mnt/d/known/results", "output": "/mnt/d/known/results/matrix"}
        plan["plan_sha256"] = v.content_digest(plan, "plan_sha256")
        inputs = v.Inputs(read)
        inputs.bind_plan_results_alias(plan)
        original = "/root/known_frozen/results/trial/recording_closure.json"
        external = "/root/external_owner/terminal.json"
        unrelated = "/root/different_frozen/results/other.json"
        for reference in (original, external, unrelated):
            inputs.bound({"path": reference, "sha256": v.sha(b"SMALL_SYNTHETIC_BYTES")})
        self.assertEqual(calls, ["/mnt/d/known/results/trial/recording_closure.json", external, unrelated])
        self.assertEqual(inputs.seen[v.path_key(original)]["path"], original)
        invalid = {**plan, "results_root": "/mnt/d/UNAUTHENTICATED"}
        with self.assertRaises(v.Refused):
            inputs.bind_plan_results_alias(invalid)

    def test_snapshot_contract_rejects_unknown_model_and_unapproved_nested_copy(self):
        for defect in ("class", "model", "nested"):
            with self.subTest(defect=defect):
                fixture = Fixture()
                inputs = v.Inputs(fixture.read)
                plan = inputs.json(fixture.profile["source_files"]["plan"])
                if defect == "class":
                    plan["trials"][0]["target_class"] = "unknown"
                elif defect == "model":
                    plan["trials"][0]["model"] = plan["trials"][8]["model"]
                else:
                    contract = v.parse(fixture.read(fixture.profile["snapshot_audit_contract"]["path"]))
                    before = v.parse(fixture.read(contract["source_before"]["path"]))
                    before["entries"].pop("docs/ignored_0000.md")
                    before["entries"]["ros2_ws/src/unknown/build/UNAPPROVED.py"] = {"kind": "file", "bytes": 1, "sha256": "8" * 64}
                    contract["source_before"] = fixture.put(contract["source_before"]["path"], before)
                    fixture.profile["snapshot_audit_contract"] = fixture.put(fixture.profile["snapshot_audit_contract"]["path"], contract)
                    inputs = v.Inputs(fixture.read)
                with self.assertRaises(v.Refused):
                    v.snapshot_capture_contract(fixture.profile, inputs, plan)

    def test_child_marker_can_precede_delayed_start_event_publication(self):
        fixture = Fixture()
        fixture.events[1]["utc"] = utc(12)  # Marker is 11; Popen happened before the event write.
        fixture.refresh()
        self.assertEqual(v.validate(fixture.profile, fixture.read, now=NOW)["slot_count"], 16)

    def test_independent_slot_cannot_mask_unknown_behavior_with_empty_owner_list(self):
        fixture = Fixture()
        inputs = v.Inputs(fixture.read)
        plan = inputs.json(fixture.profile["source_files"]["plan"])
        captures = v.snapshot_capture_contract(fixture.profile, inputs, plan)
        terminal = fixture.terminals[0]
        entry = next(row for row in terminal["evaluations"] if row["kind"] == "surface_flight")
        report = v.parse(fixture.read(entry["report"]))
        report["occlusions"][0]["checks"]["detector_interruption_observed"] = None
        binding = fixture.put(entry["report"], report)
        entry["report_sha256"] = binding["sha256"]
        terminal["artifact_hashes"]["surface_flight.json"] = binding["sha256"]
        terminal["record_sha256"] = v.content_digest(terminal, "record_sha256")
        row = fixture.native["collected"][0]
        row.update(original_terminal=fixture.put(row["original_terminal"]["path"], terminal), record_sha256=terminal["record_sha256"])
        row["terminal_sha256"] = row["original_terminal"]["sha256"]
        with self.assertRaisesRegex(v.Refused, "Unknown behavior evidence"):
            v.validate_slot(inputs, plan, plan["trials"][0], row, captures, NOW)

    def test_complete_actual_shape_preserves_engineering_failures_and_static_alive(self):
        fixture = Fixture()
        before = deepcopy(fixture.files)
        report = v.validate(fixture.profile, fixture.read, now=NOW)
        self.assertEqual(report["status"], "PASS_OWNER_CLOSURE_ONLY_NOT_ENGINEERING_ADMISSION")
        self.assertEqual(report["slot_count"], 16)
        self.assertEqual(report["preserved_engineering_counts"], {"PASS": 6, "FAIL": 5, "INCOMPLETE_EVIDENCE": 5})
        self.assertEqual(fixture.files, before)

    def test_pending_missing_future_nonzero_boolean_or_unheld_closure_rejects(self):
        changes = {
            "running": lambda f: f.outer.update(status="RUNNING"),
            "unverified": lambda f: f.outer.update(closure_verified=False),
            "errors": lambda f: f.outer["errors"].append({"error": "publication fault"}),
            "boolean_exit": lambda f: f.outer.update(wsl_exit_code=False),
            "nonzero_exit": lambda f: f.outer.update(monitor_final_handle_exit_code=2),
            "missing_handle": lambda f: f.outer.pop("wsl_handle_acquired_utc"),
            "late_handle": lambda f: f.outer.update(wsl_handle_acquired_utc=utc(100)),
            "future": lambda f: f.outer.update(finished_utc=(NOW + timedelta(seconds=1)).isoformat()),
            "early_release": lambda f: f.outer["power_lease"].update(released_utc=utc(20)),
            "pending_native": lambda f: f.native.update(status="RUNNING"),
            "active_child": lambda f: f.native.update(child_may_still_be_active={"pid": 999}),
            "old_prefix": lambda f: f.native.update(initial_closed=[{"slot_id": "OLD"}]),
            "wrong_native_owner": lambda f: f.native["owner_identity"].update(start_ticks=99999),
            "fifteen_slots": lambda f: f.native["collected"].pop(),
            "duplicate_slot": lambda f: f.native["collected"].__setitem__(1, deepcopy(f.native["collected"][0])),
            "unknown_behavior": lambda f: f.native["collected"][0].update(unobserved_checks=["UNKNOWN"]),
            "duplicate_event": lambda f: f.events.insert(2, deepcopy(f.events[1])),
            "derived_start": lambda f: f.events[1].update(executed_by_this_owner=False),
            "boolean_child_event": lambda f: f.events[2].update(returncode=False),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                fixture = Fixture()
                change(fixture)
                fixture.refresh()
                with self.assertRaises((v.Refused, KeyError)):
                    v.validate(fixture.profile, fixture.read, now=NOW)

    def test_source_manifest_raw_hash_and_primitive_json_tampering_reject(self):
        for defect in ("source", "marker", "terminal", "capture", "duplicate_json_key", "nan"):
            with self.subTest(defect=defect):
                fixture = Fixture()
                if defect == "source":
                    path = fixture.profile["source_files"]["collector"]["path"]
                    fixture.files[v.path_key(path)] += b"UNREVIEWED"
                elif defect in {"marker", "terminal"}:
                    path = fixture.native["collected"][0]["original_" + defect]["path"]
                    fixture.files[v.path_key(path)] += b"UNREVIEWED"
                elif defect == "capture":
                    path = "/mnt/c/fixture/results/trial_0/configuration/source_sha256.json"
                    fixture.files[v.path_key(path)] = b"{}"
                else:
                    binding = fixture.profile["closure_files"]["outer_terminal"]
                    payload = b'{"status":"COLLECTION_ENDED","status":"COLLECTION_ENDED"}' if defect == "duplicate_json_key" else b'{"x":NaN}'
                    fixture.files[v.path_key(binding["path"])] = payload
                    binding["sha256"] = v.sha(payload)
                with self.assertRaises(v.Refused):
                    v.validate(fixture.profile, fixture.read, now=NOW)

    def test_full_validation_disabled_before_read_or_output(self):
        output = io.StringIO()
        with patch.object(v, "load_production", side_effect=AssertionError("Must not read inputs")), redirect_stdout(output):
            self.assertEqual(v.main([]), 2)
            self.assertEqual(v.main(["--receipt-output", "/unused/closure.json"]), 2)
        self.assertIn("Production full validation disabled", output.getvalue())

    def test_missing_actual_closure_bindings_rejects_before_any_read(self):
        with self.assertRaises(v.Refused):
            v.validate({}, lambda path: self.fail("Must not read"), now=NOW)

    def test_concurrent_evidence_change_rejects(self):
        fixture = Fixture()
        target = fixture.profile["source_files"]["entry"]["path"]
        seen = 0
        def read(path):
            nonlocal seen
            payload = fixture.read(path)
            if path == target:
                seen += 1
                if seen > 1:
                    return payload + b"CONCURRENT_CHANGE"
            return payload
        with self.assertRaises(v.Refused):
            v.validate(fixture.profile, read, now=NOW)


if __name__ == "__main__":
    unittest.main()
