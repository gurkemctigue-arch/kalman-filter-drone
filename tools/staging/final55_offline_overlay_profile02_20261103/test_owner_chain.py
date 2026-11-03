"""Synthetic chain evidence only: no processes, WSL, bags, or real closure."""
from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch

import test_owner_closure as fixture_module


SPEC = importlib.util.spec_from_file_location("prepared_owner_chain_tests", Path(__file__).with_name("validate_owner_chain.py"))
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)
v = c.v
utc, NOW = fixture_module.utc, fixture_module.NOW


class ChainFixture:
    def __init__(self):
        self.a = fixture_module.Fixture()
        self.files = self.a.files
        self.plan = v.parse(self.a.read(self.a.profile["source_files"]["plan"]["path"]))
        self.original = deepcopy(self.a.native["collected"])
        self.profile = {name: deepcopy(self.a.profile[name]) for name in
                        ("plan_digest", "source_digest", "class_model_contract", "snapshot_audit_contract")}
        self.profile.update(plan=deepcopy(self.a.profile["source_files"]["plan"]), segments=[])
        a = self.a
        a.native_end = 113
        a.events = [a.events[0], *a.events[1:4], a.events[4],
                    {"event": "STOPPED_FAULT", "utc": utc(114), "scope": "SUPERVISED_PENDING_COLLECTION",
                     "slot": self.original[1]["slot_id"], "error": "KeyboardInterrupt: "}]
        a.native.update(status="STOPPED_FAULT", current_slot=self.original[1]["slot_id"],
                        collected=self.original[:1], returncode=2, finished_utc=utc(113),
                        error="KeyboardInterrupt: ", metadata_fault_child_exit_observed=True,
                        current_child={"pid": 2001, "identity": {"pid": 2001, "boot_id": a.boot, "start_ticks": 2001},
                                       "command": a.events[-2]["command"], "started_utc": utc(70),
                                       "finished_utc": utc(111), "returncode": 0})
        self.close_at(a, stopped=True)
        a.refresh()
        seg = self.segment(a, "synthetic04", "ROOT_REVIEWED_CONTROLLED_STOP", "__before_first__")
        self.profile["segments"].append(seg)
        child = {**deepcopy(a.native["current_child"]), "returncode": None}
        child.pop("finished_utc")
        before = {**deepcopy(a.first_native), "current_slot": self.original[1]["slot_id"],
                  "current_child": child, "collected": self.original[:1]}
        native_state = a.put(r"C:\fixture\stop\native_state.json", before)
        windows = a.put(r"C:\fixture\stop\windows_started.json", a.started)
        tool = a.put(r"C:\fixture\stop\signal_tool.py", b"SYNTHETIC INERT SIGNAL SOURCE")
        prepared = a.put(r"C:\fixture\prepared_collector05.py", b"SYNTHETIC PREPARED SOURCE")
        intent = {"schema_version": 1, "status": "INTENT_REGISTERED_NOT_SIGNALLED", "registered_utc": utc(80),
                  "scope": "CONTROLLED_COLLECTOR_ROLLOVER_WAIT_CURRENT_ORIGINAL_COMMAND_EXIT",
                  "reason": "SYNTHETIC class-specific capture correction", "signal": "SIGINT",
                  "signal_target": "POSITIVE_COLLECTOR_PID_ONLY", "signal_tool_sha256": tool["sha256"],
                  "native_state_snapshot_sha256": native_state["sha256"], "windows_started_snapshot_sha256": windows["sha256"],
                  "native_command": a.started["native_command"], "monitor_identity": a.monitor,
                  "native_owner": a.native_root,
                  "owner_identity": a.native["owner_identity"], "current_slot": self.original[1]["slot_id"],
                  "current_child": child, "closed_prefix": self.original[:1],
                  "pins": {"collector04": seg["source_files"]["collector"]["sha256"], "prepared05": prepared["sha256"],
                           "plan": self.profile["plan"]["sha256"]}}
        intent_binding = a.put(r"C:\fixture\stop\intent.json", intent)
        preflight = {"status": "IDENTITY_CHECKED_BEFORE_SINGLE_PID_SIGNAL", "utc": utc(81),
                     "intent_sha256": intent_binding["sha256"], "signal_tool_sha256": tool["sha256"],
                     "owner_identity": a.native["owner_identity"], "child_identity": child["identity"],
                     "child_ppid": a.native["owner_pid"], "signal_target_pid": a.native["owner_pid"], "signal": "SIGINT",
                     "actual_owner_argv": ["python3", *intent["native_command"][5:]]}
        pre_binding = a.put(r"C:\fixture\stop\preflight.json", preflight)
        receipt = a.put(r"C:\fixture\stop\signal_receipt.json", {
            "status": "SINGLE_PID_SIGINT_REQUEST_SENT", "utc": utc(82), "signal": "SIGINT", "os_kill_returned": True,
            "signal_target_pid": a.native["owner_pid"], "intent_sha256": intent_binding["sha256"], "preflight_sha256": pre_binding["sha256"]})
        seg["stop_evidence"] = {"intent": intent_binding, "native_state": native_state, "windows_started": windows,
                                "signal_tool": tool, "preflight": pre_binding, "signal_receipt": receipt, "prepared_source": prepared}
        self.refresh_review()

    @staticmethod
    def close_at(a, *, stopped):
        code, n = (2 if stopped else 0), a.native_end
        task = {**deepcopy(a.first_monitor["task"]), "returncode": code, "finished_utc": utc(n + 5)}
        a.final_monitor = {**deepcopy(a.first_monitor), "task": task, "tasks": [task], "heartbeat_utc": utc(n + 5)}
        a.end.update(status="STOPPED_FAULT" if stopped else "COMPLETED", task=task, tasks=[task],
                     generated_utc=utc(n + 6), evidence_sources=a.first_monitor["sources"])
        a.outer = {**deepcopy(a.started), "status": "STOPPED_FAULT" if stopped else "COLLECTION_ENDED", "closure_verified": True,
                   "wsl_identity": a.wsl, "wsl_handle_acquired_utc": a.first_monitor["heartbeat_utc"],
                   "first_native_owner_identity": a.first_native["owner_identity"],
                   "first_native_owner_source": a.first_native["owner_source"], "first_native_started_utc": a.first_native["started_utc"],
                   "first_native_state_observed_utc": a.first_native["heartbeat_utc"], "native_owner_identity": a.native["owner_identity"],
                   "native_collection_status": a.native["status"], "collected_slots": len(a.native["collected"]),
                   "monitor_exit_code": code, "wsl_exit_code": code, "monitor_popen_wait_exit_code": code,
                   "monitor_final_popen_wait_exit_code": code, "monitor_final_handle_exit_code": code, "wsl_final_handle_exit_code": code,
                   "wsl_first_exit_observed_utc": utc(n + 3), "monitor_first_exit_observed_utc": utc(n + 7),
                   "windows_handles_closed_observation_utc": utc(n + 8), "wsl_final_exit_observed_utc": utc(n + 9),
                   "monitor_final_exit_observed_utc": utc(n + 10), "finished_utc": utc(n + 12)}
        a.outer["power_lease"].update(release_return=0x80000003, released_utc=utc(n + 11))

    @staticmethod
    def segment(a, segment_id, disposition, after):
        return {"segment_id": segment_id, "disposition": disposition, "after_slot": after,
                **{name: deepcopy(a.profile[name]) for name in ("source_files", "description", "native_plan_alias", "launch_files", "closure_files")}}

    def refresh_review(self):
        seg = self.profile["segments"][0]
        review = {"schema_version": 1, "status": "ROOT_REVIEWED_CLOSED_FRONTIER_PRESERVED",
                  "kind": "CONTROLLED_SIGINT_COLLECTOR_ROLLOVER", "segment_id": seg["segment_id"], "reviewed_utc": utc(130),
                  "plan": {**self.profile["plan"], "plan_sha256": self.plan["plan_sha256"]},
                  **{name: seg["closure_files"][name] for name in ("outer_terminal", "native_terminal", "events")},
                  "intent": seg["stop_evidence"]["intent"], "signal_receipt": seg["stop_evidence"]["signal_receipt"],
                  "frontier": c.stable_row(self.original[1]), "frontier_record": deepcopy(self.original[1]),
                  "original_error": "KeyboardInterrupt: ", "original_engineering_verdict_preserved": True}
        seg["stop_evidence"]["root_review"] = self.a.put(r"C:\fixture\stop\root_review.json", review)

    def add_registered_completion(self):
        prior = deepcopy(self.profile)
        audit = c.validate_continuation_profile(prior, self.a.read, now=NOW)
        with patch.object(fixture_module, "utc", lambda seconds: utc(seconds + 1000)):
            b = fixture_module.Fixture()
        # Preserve actual first-owner attempts; later synthetic attempts have a
        # distinct collection window. All data remains in this memory map.
        for key, value in b.files.items():
            if key not in self.files or any(f"trial_{index}/" in key or f"synthetic_slot_{index:02}." in key for index in range(2, 16)):
                self.files[key] = value
        b.files = self.files
        self.b = b
        b.outer_root, b.monitor_root, b.native_root = r"C:\fixture\outer05", r"C:\fixture\monitor05", "/root/synthetic_owner05"
        sources = deepcopy(b.profile["source_files"])
        for key in ("launcher", "collector", "gate", "chain_validator"):
            sources[key] = b.put("C:/fixture/owner05/" + key + ".py", ("SYNTHETIC INERT " + key).encode())
        sources["registered_profile"] = b.put("C:/fixture/owner05/registered_profile.json", prior)
        b.profile["source_files"] = sources
        desc = deepcopy(b.profile["description"])
        desc.update(scope="WINDOWS_OWNER_OF_REGISTERED_PRESERVED_PREFIX_CONTINUATION", task_id="synthetic_owner05",
                    native_owner=b.native_root, owner_unc=r"\\wsl.localhost\UAVHumble22\root\synthetic_owner05",
                    monitor_output=b.monitor_root, receipt_output=b.outer_root,
                    pins={key: value for key, value in sources.items() if key != "launcher"})
        desc["registered_admission_unc"] = desc["owner_unc"] + ".admission.json"
        desc["sources"] = {"events": v.join(desc["owner_unc"], "events.jsonl"), "ledger": v.join(desc["owner_unc"], "state.json"), "plan": sources["plan"]["path"]}
        desc["native_command"] = ["wsl.exe", "--distribution", "UAVHumble22", "--exec", "python3", "-B", v.mounted(sources["gate"]["path"]),
                                  "--profile", v.mounted(sources["registered_profile"]["path"]), "--output", b.native_root, "--execute"]
        b.profile["description"] = desc
        b.launcher, b.monitor, b.wsl = (fixture_module.win(pid, 1000 + second) for pid, second in ((110, 0), (111, 2), (112, 4)))
        b.started.update(**desc, launcher_identity=b.launcher, monitor_identity=b.monitor, launcher_source=sources["launcher"])
        b.started["power_lease"]["monitor_identity"] = b.monitor
        task = b.first_monitor["task"]
        task.update(id=desc["task_id"], label=desc["task_id"], process=b.wsl)
        b.first_monitor.update(monitor_process=b.monitor, sources=desc["sources"], task=task, tasks=[task])
        prefix = deepcopy(self.original[:2])
        for index, row in enumerate(prefix):
            trial = self.plan["trials"][index]
            model = self.profile["class_model_contract"][trial["target_class"]]
            row["capture_binding"] = {"target_class": trial["target_class"], "model": trial["model"], "model_sha256": model["model_sha256"],
                                      "capture_sha256": model["capture_sha256"], "entries": 204,
                                      "path": v.join(trial["directory"], "configuration/source_sha256.json")}
        b.first_native.update(owner_pid=113, owner_identity={"pid": 113, "boot_id": b.boot, "start_ticks": 9000}, initial_closed=prefix,
                              owner_source={"path": v.mounted(sources["collector"]["path"]), "sha256": sources["collector"]["sha256"]})
        collected = b.native["collected"][2:]
        b.native = {**deepcopy(b.native), **deepcopy(b.first_native), "status": "COLLECTION_FINISHED", "current_slot": None,
                    "collected": collected, "returncode": 0, "finished_utc": utc(b.native_end + 1000)}
        b.native_end += 1000
        b.events[0]["pending_ids"] = [trial["id"] for trial in self.plan["trials"][2:]]
        derived = []
        for index, row in enumerate(prefix):
            for kind in ("START_SLOT", "COMPLETE_SLOT"):
                derived.append({"event": kind, "utc": utc(1010 + len(derived)), "scope": "SUPERVISED_PENDING_COLLECTION",
                                "slot": row["slot_id"], "status": row["original_status"], "executed_by_this_owner": False,
                                "event_semantics": "DERIVED_OBSERVATION_OF_ORIGINAL_CLOSED_PREFIX", "total": 16,
                                **{name: row[name] for name in ("original_marker", "original_terminal", "original_started_utc", "original_finished_utc")}})
        b.events = [b.events[0], *derived, *b.events[7:]]
        b.events[-1]["collected_slots"] = 14
        self.close_at(b, stopped=False)
        b.refresh()
        seg = self.segment(b, "synthetic05", "COMPLETED", prefix[-1]["slot_id"])
        self.profile["segments"].append(seg)
        self.admission = {"scope": "REGISTERED_PREFIX_ADMISSION_BEFORE_NEW_OWNER05_CHILDREN", "utc": utc(1006),
                          "owner_identity": b.native["owner_identity"], "plan": audit["plan"], "after_slot": audit["after_slot"],
                          "closed_ids": audit["closed_ids"], "pending_ids": audit["pending_ids"], "chain_admission": c.stable_chain(audit),
                          "unknown_evidence_exceptions": {}, "automatic_retry": False}
        for key, field in (("gate", "gate_source"), ("registered_profile", "profile"), ("chain_validator", "chain_validator"), ("collector", "collector")):
            self.admission[field] = {"path": v.mounted(sources[key]["path"]), "sha256": sources[key]["sha256"]}
        self.refresh_b()
        return self

    def refresh_b(self):
        b, seg = self.b, self.profile["segments"][1]
        admission_binding = b.put(b.native_root + ".admission.json", self.admission)
        b.refresh()
        gate = {"finished_utc": utc(b.native_end + 2), "gate_source": self.admission["gate_source"], "profile": self.admission["profile"],
                "admission": admission_binding, "native_terminal": b.profile["closure_files"]["native_terminal"],
                "status": b.native["status"], "returncode": b.native["returncode"]}
        gate_binding = b.put(v.join(b.native_root, "registered_entry_terminal.json"), gate)
        for name, value in (("first_registered_admission.json", self.admission), ("registered_entry_terminal.json", gate)):
            b.outer["artifacts"][name] = b.put(v.join(b.outer_root, name), value)["sha256"]
        b.outer.update(first_registered_admission_sha256=admission_binding["sha256"],
                       first_registered_admission_owner_identity=b.native["owner_identity"],
                       first_registered_admission_observed_utc=utc(1008), registered_entry_terminal_sha256=gate_binding["sha256"])
        b.profile["closure_files"]["outer_terminal"] = b.put(v.join(b.outer_root, "terminal.json"), b.outer)
        seg["closure_files"] = {**deepcopy(b.profile["closure_files"]), "registered_entry_terminal": gate_binding}
        seg["launch_files"] = {**deepcopy(b.profile["launch_files"]), "registered_admission": admission_binding}


class OwnerChainTests(unittest.TestCase):
    def test_controlled_unappended_frontier_qualifies_only_original_prefix(self):
        f = ChainFixture()
        result = c.validate_continuation_profile(f.profile, f.a.read, now=NOW)
        self.assertEqual(result["closed_ids"], [row["slot_id"] for row in f.original[:2]])
        self.assertEqual(result["after_slot"], f.original[1]["slot_id"])
        self.assertEqual(result["closed"][1]["original_status"], "FAIL")
        self.assertEqual(result["segments"][0]["original_native_status"], "STOPPED_FAULT")
        self.assertEqual(result["segments"][0]["actual_collected_count"], 1)
        self.assertEqual(len(result["pending_ids"]), 14)
        self.assertIsInstance(result["input_bindings"], list)
        self.assertIn(c.reviewed_slot_source(), result["input_bindings"])
        self.assertEqual(result, c.validate_continuation_profile(f.profile, f.a.read, now=NOW))

    def test_new_pending_outputs_do_not_mutate_old_prefix_admission(self):
        f = ChainFixture()
        before = c.validate_continuation_profile(f.profile, f.a.read, now=NOW)
        f.a.put(v.join(self.plan_path(f), "slots/synthetic_slot_02.started.json"), {"id": "SYNTHETIC NEW PENDING OUTPUT"})
        self.assertEqual(before, c.validate_continuation_profile(f.profile, f.a.read, now=NOW))

    @staticmethod
    def plan_path(f):
        return f.plan["output"]

    def test_separate_gate_continuation_closes_only_remaining_slice(self):
        f = ChainFixture().add_registered_completion()
        result = c.validate_chain(f.profile, f.a.read, now=NOW)
        self.assertEqual(result["status"], "OWNER_CHAIN_COMPLETED_NOT_ENGINEERING_ADMISSION")
        self.assertEqual(len(result["closed"]), 16)
        self.assertEqual(result["pending_ids"], [])
        self.assertEqual(result["segments"][1]["derived_prefix_count"], 2)
        self.assertEqual(result["segments"][1]["actual_collected_count"], 14)
        self.assertEqual([row["original_status"] for row in result["closed"][:3]], ["PASS", "FAIL", "INCOMPLETE_EVIDENCE"])
        with self.assertRaises(v.Refused):
            c.validate_continuation_profile(f.profile, f.a.read, now=NOW)

    def test_missing_review_rejected(self):
        f = ChainFixture()
        del f.profile["segments"][0]["stop_evidence"]["root_review"]
        with self.assertRaises((v.Refused, KeyError)):
            c.validate_chain(f.profile, f.a.read, now=NOW)

    def test_signal_request_without_actual_handle_closure_rejected(self):
        f = ChainFixture()
        f.a.outer["wsl_final_handle_exit_code"] = None
        f.a.refresh()
        f.profile["segments"][0].update(closure_files=deepcopy(f.a.profile["closure_files"]), launch_files=deepcopy(f.a.profile["launch_files"]))
        f.refresh_review()
        with self.assertRaises(v.Refused):
            c.validate_chain(f.profile, f.a.read, now=NOW)

    def test_wsl_handle_cannot_be_acquired_after_observed_exit(self):
        f = ChainFixture()
        f.a.outer["wsl_handle_acquired_utc"] = utc(126)
        f.a.refresh()
        f.profile["segments"][0].update(closure_files=deepcopy(f.a.profile["closure_files"]), launch_files=deepcopy(f.a.profile["launch_files"]))
        f.refresh_review()
        with self.assertRaisesRegex(v.Refused, "held-handle closure chronology"):
            c.validate_chain(f.profile, f.a.read, now=NOW)

    def test_unappended_frontier_must_not_get_invented_complete_event(self):
        f = ChainFixture()
        f.a.events.insert(-1, {"event": "COMPLETE_SLOT", "utc": utc(112), "scope": "SUPERVISED_PENDING_COLLECTION"})
        f.a.refresh()
        f.profile["segments"][0]["closure_files"] = deepcopy(f.a.profile["closure_files"])
        f.refresh_review()
        with self.assertRaises(v.Refused):
            c.validate_chain(f.profile, f.a.read, now=NOW)

    def test_raw_closed_evidence_tamper_rejected(self):
        f = ChainFixture()
        f.files[v.path_key(f.original[0]["original_terminal"]["path"])] += b" "
        with self.assertRaises(v.Refused):
            c.validate_chain(f.profile, f.a.read, now=NOW)

    def test_unknown_behavior_rejected_even_empty_unknown_list(self):
        f = ChainFixture()
        trial = f.plan["trials"][1]
        binding = trial["evaluations"][2]["report"]
        report = v.parse(f.a.read(binding))
        report["occlusions"][0]["checks"]["prediction_observed"] = None
        report_binding = f.a.put(binding, report)
        row = f.original[1]
        terminal = v.parse(f.a.read(row["original_terminal"]["path"]))
        terminal["evaluations"][2]["report_sha256"] = report_binding["sha256"]
        terminal["artifact_hashes"]["surface_flight.json"] = report_binding["sha256"]
        terminal["record_sha256"] = v.content_digest(terminal, "record_sha256")
        row.update(original_terminal=f.a.put(row["original_terminal"]["path"], terminal), record_sha256=terminal["record_sha256"])
        row["terminal_sha256"] = row["original_terminal"]["sha256"]
        f.refresh_review()
        with self.assertRaisesRegex(v.Refused, "Unknown behavior evidence"):
            c.validate_chain(f.profile, f.a.read, now=NOW)

    def test_completed_final_child_must_match_actual_last_invocation(self):
        for changed in ({"pid": 9999}, {"command": ["SYNTHETIC WRONG CHILD"]}, {"finished_utc": utc(1010)}):
            f = ChainFixture().add_registered_completion()
            f.b.native["current_child"].update(changed)
            f.refresh_b()
            with self.assertRaisesRegex(v.Refused, "actual last original invocation"):
                c.validate_chain(f.profile, f.a.read, now=NOW)

    def test_registered_gate_source_tamper_rejected(self):
        f = ChainFixture().add_registered_completion()
        f.files[v.path_key(f.profile["segments"][1]["source_files"]["gate"]["path"])] += b"changed"
        with self.assertRaises(v.Refused):
            c.validate_chain(f.profile, f.a.read, now=NOW)

    def test_next_owner_cannot_overlap_previous_root_review(self):
        f = ChainFixture().add_registered_completion()
        # This remains after the actual old command exit, but precedes the
        # required named review. No source output claims are synthesized.
        f.b.started["started_utc"] = utc(129)
        f.b.launcher = fixture_module.win(110, 126)
        f.b.monitor = fixture_module.win(111, 129)
        f.b.started.update(launcher_identity=f.b.launcher, monitor_identity=f.b.monitor, monitor_handle_acquired_utc=utc(129))
        f.b.started["power_lease"].update(monitor_identity=f.b.monitor, accepted_utc=utc(129))
        f.b.first_monitor["monitor_process"] = f.b.monitor
        f.close_at(f.b, stopped=False)
        f.refresh_b()
        with self.assertRaisesRegex(v.Refused, "before previous closure and root review"):
            c.validate_chain(f.profile, f.a.read, now=NOW)

    def test_derived_prefix_cannot_claim_new_actual_invocation(self):
        f = ChainFixture().add_registered_completion()
        f.b.events[1]["executed_by_this_owner"] = True
        f.refresh_b()
        with self.assertRaisesRegex(v.Refused, "Derived prefix"):
            c.validate_chain(f.profile, f.a.read, now=NOW)

    def test_registered_admission_cannot_replace_prefix_or_allow_unknown(self):
        for key, value in (("unknown_evidence_exceptions", {"made_up": True}), ("closed_ids", ["wrong"])):
            f = ChainFixture().add_registered_completion()
            f.admission[key] = value
            f.refresh_b()
            with self.assertRaises(v.Refused, msg=key):
                c.validate_chain(f.profile, f.a.read, now=NOW)

    def test_exact_after_slot_required(self):
        f = ChainFixture().add_registered_completion()
        f.profile["segments"][1]["after_slot"] = f.original[0]["slot_id"]
        with self.assertRaises(v.Refused):
            c.validate_chain(f.profile, f.a.read, now=NOW)

    def test_slot_library_dependency_rechecked_after_import(self):
        f = ChainFixture()
        original_read = Path.read_bytes
        def changed(path):
            raw = original_read(path)
            return raw + b"changed" if path.name == "validate_owner_closure.py" else raw
        with patch.object(Path, "read_bytes", changed), self.assertRaises(v.Refused):
            c.validate_chain(f.profile, f.a.read, now=NOW)

    def test_disabled_default_never_creates_receipt(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(c.main([]), 2)
        self.assertIn("REFUSED_NO_NATIVE_TASK_OR_OUTPUT", output.getvalue())
        self.assertFalse(c.PRODUCTION_ENABLED)
        self.assertEqual(c.PRODUCTION_PROFILE, {})


if __name__ == "__main__":
    unittest.main()
