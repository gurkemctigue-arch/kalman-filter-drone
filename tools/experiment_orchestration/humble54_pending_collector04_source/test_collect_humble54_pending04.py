"""Small synthetic records and short fake subprocesses; never WSL/ROS/bags."""
import importlib.util
import errno
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("collector", Path(__file__).with_name("collect_humble54_pending04.py"))
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class FrozenFixture:
    @staticmethod
    def source_hashes(root):
        return {"source.py": c.sha(root / "source.py")}

    @staticmethod
    def read_evaluation(spec, execution, plan):
        report = c.load(spec["report"])
        value = report["acceptance"]["result"] if spec["kind"] == "surface_flight" else report["evaluation_status"]
        return {"result": value, "reported_verdict": value}

    @staticmethod
    def navigation_verdict(report, gates):
        return "PASS", {"fixture_navigation": True}

    @staticmethod
    def engineering_verdict(plan, trial, flight, entries):
        surface = next(row for row in entries if row["kind"] == "surface_flight")
        if surface["result"] == "FAIL":
            return "FAIL", {"negative_evaluators": ["surface_flight"], "pending": [], "incomplete": []}
        if surface["result"] == "INCOMPLETE_EVIDENCE":
            return "INCOMPLETE_EVIDENCE", {"incomplete": ["surface_flight"], "pending": []}
        return "PASS", {"fixture_navigation": True}


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.frozen = self.root / "frozen"
        self.frozen.mkdir()
        (self.frozen / "source.py").write_text("# synthetic source\n", encoding="utf-8")
        self.matrix = self.root / "matrix"
        self.matrix.mkdir()
        self.results = self.root / "results"
        self.results.mkdir()
        self.entry = self.root / "entry.sh"
        self.entry.write_text("# synthetic entry, never executed\n", encoding="utf-8")
        trials = []
        for slot in ("closed", "next", "last"):
            directory = self.results / slot
            trials.append({"id": slot, "name": slot, "directory": str(directory), "flight_command": ["fixture", slot],
                           "evaluations": [{"kind": kind, "report": str(directory / filename), "command": ["evaluate", slot, kind]}
                                           for kind, filename in (("source_clock", "clock.json"), ("native_startup", "native.json"),
                                                                  ("surface_flight", "surface.json"), ("navigation", "navigation.json"))]})
        self.plan = {"mode": "EXTENSION_PROBE", "selected_seeds": [4], "frozen_root": str(self.frozen),
                     "output": str(self.matrix), "trials": trials,
                     "source_hashes": FrozenFixture.source_hashes(self.frozen), "protocol": {"navigation_acceptance": {}}}
        self.plan["plan_sha256"] = c.digest(self.plan, "plan_sha256")
        self.plan_path = self.matrix / "plan.json"
        save(self.plan_path, self.plan)
        self.module = FrozenFixture()
        self.fake = self.root / "fake.py"
        self.fake.write_text('''import json, pathlib, shutil, sys
root, slot, mode = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
plan = json.loads((root/'matrix/plan.json').read_text())
trial = next(row for row in plan['trials'] if row['id'] == slot)
with (root/'calls.txt').open('a') as f: f.write(slot+'\\n')
if mode == 'exit_before': raise SystemExit(7)
shutil.copytree(root/'templates'/slot/'trial', trial['directory'])
shutil.copy2(root/'templates'/slot/'marker.json', root/'matrix/slots'/(slot+'.started.json'))
shutil.copy2(root/'templates'/slot/'terminal.json', root/'matrix/slots'/(slot+'.json'))
raise SystemExit(7 if mode == 'exit_after' else 0)
''', encoding="utf-8")
        for trial in trials:
            self.template(trial)
        closed = trials[0]
        shutil.copytree(self.root / "templates/closed/trial", closed["directory"])
        (self.matrix / "slots").mkdir()
        shutil.copy2(self.root / "templates/closed/marker.json", self.matrix / "slots/closed.started.json")
        shutil.copy2(self.root / "templates/closed/terminal.json", self.matrix / "slots/closed.json")
        capture = Path(closed["directory"]) / "configuration/source_sha256.json"
        self.pins = {"plan": c.sha(self.plan_path), "entry": c.sha(self.entry), "capture": c.sha(capture),
                     "history": {"closed": c.sha(self.matrix / "slots/closed.json")}, "minimum_prefix": 1}

    def template(self, trial, *, behavior_false=False, safety_false=False, unknown=False):
        root = self.root / "templates" / trial["id"]
        directory = root / "trial"
        directory.mkdir(parents=True, exist_ok=True)
        for name in ("recording_closure.json", "bag_integrity.json"):
            save(directory / name, {"status": "PASS"})
        save(directory / "configuration/source_sha256.json", {"fixture": "1" * 64})
        save(directory / "run_config.json", {"fixture": True})
        parameters = directory / "configuration/runtime_parameters.yaml"
        parameters.write_text("fixture: true\n", encoding="utf-8")
        short_checks = {key: True for key in (*c.SHUTTER, *c.SHORT_ALGORITHM)}
        long_checks = {key: True for key in (*c.SHUTTER, *c.LONG_SAFE, *c.LONG_ALGORITHM)}
        if behavior_false:
            long_checks["prediction_observed"] = False
        if safety_false:
            long_checks["hover_observed_for_long_occlusion"] = False
        if unknown:
            short_checks["detector_interruption_observed"] = None
        status = "FAIL" if behavior_false or safety_false else "INCOMPLETE_EVIDENCE" if unknown else "PASS"
        surface = {"acceptance": {"result": status, "missing_topics": [], "input_read_error_count": 0,
                                  "clock_timebase_available": True, "short_occlusion_recorded": True,
                                  "long_occlusion_recorded": True, "failed_events_retained": True},
                   "flight_evidence": {"armed_seen": True, "offboard_seen": True},
                   "detector": {"invalid_diagnostic_messages": 0},
                   "occlusions": [{"kind": "short", "complete": True, "checks": short_checks},
                                  {"kind": "long", "complete": True, "checks": long_checks}]}
        reports = {"source_clock": {"evaluation_status": "PASS"}, "native_startup": {"evaluation_status": "PASS"},
                   "surface_flight": surface, "navigation": {"evaluation_status": "RECORDED_WITH_CENSORED_FAILURES"}}
        record = {"id": trial["id"], "name": trial["name"], "plan_sha256": self.plan["plan_sha256"],
                  "started_utc": "2026-11-03T00:00:00+00:00", "finished_utc": "2026-11-03T00:01:00+00:00",
                  "status": status, "engineering_result": status, "execution_status": "COMPLETED", "infrastructure_stop": False,
                  "flight_exit_code": 0, "cleanup": {"residual_processes": []}, "infrastructure": {"stop": False},
                  "runtime_configuration": {"errors": [], "run_config_sha256": c.sha(directory / "run_config.json"),
                                            "runtime_parameters_sha256": c.sha(parameters)},
                  "commands": [{"kind": "flight", "command": trial["flight_command"], "returncode": 0, "error": None}], "evaluations": []}
        for spec in trial["evaluations"]:
            report = reports[spec["kind"]]
            path = directory / Path(spec["report"]).name
            save(path, report)
            verdict = report["acceptance"]["result"] if spec["kind"] == "surface_flight" else report["evaluation_status"]
            record["evaluations"].append({"kind": spec["kind"], "report": spec["report"], "report_sha256": c.sha(path),
                "result": verdict, "reported_verdict": verdict, "error": None,
                "execution": {"command": spec["command"], "returncode": 0, "error": None}})
        _, record["engineering_evidence"] = self.module.engineering_verdict(self.plan, trial, record["commands"][0], record["evaluations"])
        record["artifact_hashes"] = {path.relative_to(directory).as_posix(): c.sha(path) for path in directory.rglob("*") if path.is_file()}
        record["record_sha256"] = c.digest(record, "record_sha256")
        save(root / "terminal.json", record)
        save(root / "marker.json", {"id": trial["id"], "plan_sha256": self.plan["plan_sha256"],
                                    "started_utc": record["started_utc"], "flight_command": trial["flight_command"]})

    def collect(self, modes=None, output="owner"):
        modes = modes or {}
        return c.collect(self.plan_path, self.entry, "closed", self.root / output, self.pins, self.module,
                         command_factory=lambda trial: [sys.executable, "-B", str(self.fake), str(self.root), trial["id"], modes.get(trial["id"], "ok")], poll_s=.01)

    def test_continues_two_pending_slots_with_real_fake_child_exits(self):
        original = (self.matrix / "slots/closed.json").read_bytes()
        state = self.collect()
        self.assertEqual(state["status"], "COLLECTION_FINISHED", state)
        self.assertEqual([row["slot_id"] for row in state["collected"]], ["next", "last"])
        self.assertEqual((self.matrix / "slots/closed.json").read_bytes(), original)
        events = [json.loads(line) for line in (self.root / "owner/events.jsonl").read_text().splitlines()]
        self.assertEqual([row["returncode"] for row in events if row["event"] == "CHILD_EXIT"], [0, 0])
        self.assertTrue(all(row["utc"].endswith("+00:00") and row["scope"] == c.SCOPE for row in events))

    def test_known_algorithm_fail_is_retained_and_collection_continues(self):
        self.template(self.plan["trials"][1], behavior_false=True)
        state = self.collect()
        self.assertEqual(state["status"], "COLLECTION_FINISHED", state)
        self.assertEqual(state["collected"][0]["original_status"], "FAIL")
        self.assertIn("surface:long:prediction_observed=FAIL", state["collected"][0]["known_algorithm_failures"])

    def test_historical_null_is_unobserved_not_a_known_algorithm_failure(self):
        self.template(self.plan["trials"][0], unknown=True)
        shutil.copytree(self.root / "templates/closed/trial", self.results / "closed", dirs_exist_ok=True)
        shutil.copy2(self.root / "templates/closed/terminal.json", self.matrix / "slots/closed.json")
        self.pins["history"]["closed"] = c.sha(self.matrix / "slots/closed.json")
        with patch.object(c, "OLD_SHORT_NULL", "closed"):
            state = self.collect()
        self.assertEqual(state["status"], "COLLECTION_FINISHED", state)
        original = state["initial_closed"][0]
        self.assertEqual(original["original_status"], "INCOMPLETE_EVIDENCE")
        self.assertEqual(original["known_algorithm_failures"], [])
        self.assertEqual(original["unobserved_checks"], ["surface:short:detector_interruption_observed=HISTORICAL_UNKNOWN_RETAINED"])

    def test_derived_prefix_and_actual_children_count_full_plan_without_old_fault_events(self):
        self.template(self.plan["trials"][1], behavior_false=True)
        state = self.collect()
        self.assertEqual(state["status"], "COLLECTION_FINISHED", state)
        events = [json.loads(line) for line in (self.root / "owner/events.jsonl").read_text().splitlines()]
        starts = {row["slot"]: row for row in events if row["event"] == "START_SLOT"}
        complete = {row["slot"]: row for row in events if row["event"] == "COMPLETE_SLOT"}
        self.assertEqual(set(starts), {"closed", "next", "last"})
        self.assertEqual(set(complete), set(starts))
        self.assertEqual([complete[slot]["status"] for slot in ("closed", "next", "last")], ["PASS", "FAIL", "PASS"])
        self.assertTrue(all(row["total"] == 3 for row in starts.values()))
        old = complete["closed"]
        self.assertEqual(old["event_semantics"], "DERIVED_OBSERVATION_OF_ORIGINAL_CLOSED_PREFIX")
        self.assertFalse(old["executed_by_this_owner"])
        self.assertEqual(old["original_started_utc"], "2026-11-03T00:00:00+00:00")
        self.assertEqual(old["original_finished_utc"], "2026-11-03T00:01:00+00:00")
        self.assertEqual(old["original_marker"]["sha256"], c.sha(self.matrix / "slots/closed.started.json"))
        self.assertEqual(old["original_terminal"]["sha256"], c.sha(self.matrix / "slots/closed.json"))
        self.assertTrue(starts["next"]["executed_by_this_owner"])
        self.assertNotIn("STOPPED_FAULT", [row["event"] for row in events])

    def test_new_short_null_stops_before_following_slot(self):
        self.template(self.plan["trials"][1], unknown=True)
        state = self.collect()
        self.assertEqual(state["status"], "STOPPED_FAULT")
        self.assertEqual((self.root / "calls.txt").read_text().splitlines(), ["next"])
        self.assertFalse((self.results / "last").exists())

    def test_long_safety_failure_stops(self):
        self.template(self.plan["trials"][1], safety_false=True)
        self.assertEqual(self.collect()["status"], "STOPPED_FAULT")
        self.assertFalse((self.results / "last").exists())

    def test_nonzero_cli_exit_stops_even_if_it_wrote_a_terminal(self):
        state = self.collect({"next": "exit_after"})
        self.assertEqual(state["status"], "STOPPED_FAULT")
        self.assertEqual(state["current_child"]["returncode"], 7)
        self.assertFalse((self.results / "last").exists())
        with self.assertRaises(ValueError):
            self.collect(output="new_owner")
        self.assertEqual((self.root / "calls.txt").read_text().splitlines(), ["next"])

    def test_started_record_and_existing_directory_each_prevent_retry(self):
        started = self.matrix / "slots/next.started.json"
        save(started, {"fixture": True})
        with self.assertRaises(ValueError):
            self.collect()
        started.unlink()
        (self.results / "next").mkdir()
        with self.assertRaises(ValueError):
            self.collect()
        self.assertFalse((self.root / "calls.txt").exists())

    def test_source_change_refuses_before_any_child(self):
        (self.frozen / "source.py").write_text("changed", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.collect()
        self.assertFalse((self.root / "calls.txt").exists())

    def test_original_history_change_refuses_before_any_child(self):
        path = self.matrix / "slots/closed.json"
        path.write_text(path.read_text() + " ", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.collect()
        self.assertFalse((self.root / "calls.txt").exists())

    def test_changed_report_hash_stops_after_command(self):
        path = self.root / "templates/next/trial/surface.json"
        path.write_text(path.read_text() + " ", encoding="utf-8")
        self.assertEqual(self.collect()["status"], "STOPPED_FAULT")
        self.assertFalse((self.results / "last").exists())

    def test_metadata_fault_waits_for_real_child_exit_and_never_starts_next_slot(self):
        text = self.fake.read_text(encoding="utf8")
        self.fake.write_text("import time\ntime.sleep(.2)\n" + text, encoding="utf8")
        real_write = c.write_json
        failed = []

        def fail_live_metadata_once(path, value):
            if (not failed and path.name == "state.json" and
                    value.get("current_child", {}).get("returncode", "absent") is None):
                failed.append(True)
                raise PermissionError(errno.EACCES, "fixture metadata sharing conflict")
            return real_write(path, value)

        with patch.object(c, "write_json", side_effect=fail_live_metadata_once):
            state = self.collect()
        self.assertEqual(state["status"], "STOPPED_FAULT")
        self.assertTrue(state["metadata_fault_child_exit_observed"])
        self.assertEqual(state["current_child"]["returncode"], 0)
        self.assertGreaterEqual(state["finished_utc"], state["current_child"]["finished_utc"])
        self.assertEqual((self.root / "calls.txt").read_text().splitlines(), ["next"])
        self.assertTrue((self.matrix / "slots/next.json").is_file())
        self.assertFalse((self.results / "last").exists())

    def test_explicit_zero_prefix_checks_all_initial_slots(self):
        shutil.rmtree(self.results / "closed")
        (self.matrix / "slots/closed.json").unlink()
        (self.matrix / "slots/closed.started.json").unlink()
        pins = {**self.pins, "minimum_prefix": 0, "history": {}}
        _, closed, pending = c.initial_check(self.plan_path, self.entry, "__before_first__", pins, self.module)
        self.assertEqual(closed, [])
        self.assertEqual(len(pending), 3)

    def test_changed_marker_started_time_is_rejected(self):
        path = self.matrix / "slots/closed.started.json"
        value = json.loads(path.read_text())
        value["started_utc"] = "2026-11-02T23:59:59+00:00"
        save(path, value)
        with self.assertRaisesRegex(ValueError, "started marker"):
            self.collect()

    def test_non_os_supervisor_error_also_waits_for_owned_child(self):
        text = self.fake.read_text(encoding="utf8")
        self.fake.write_text("import time\ntime.sleep(.2)\n" + text, encoding="utf8")
        real_write = c.write_json
        failed = []

        def fail_metadata_once(path, value):
            if (not failed and path.name == "state.json" and
                    value.get("current_child", {}).get("returncode", "absent") is None):
                failed.append(True)
                raise ValueError("fixture JSON persistence error")
            return real_write(path, value)

        with patch.object(c, "write_json", side_effect=fail_metadata_once):
            state = self.collect()
        self.assertEqual(state["status"], "STOPPED_FAULT")
        self.assertTrue(state["metadata_fault_child_exit_observed"])
        self.assertEqual(state["current_child"]["returncode"], 0)
        self.assertEqual((self.root / "calls.txt").read_text().splitlines(), ["next"])


class AtomicWriterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "state.json"
        self.path.write_text('{"original": true}', encoding="utf8")

    def test_transient_eacces_retries_and_keeps_unique_temporary(self):
        real_replace = Path.replace
        attempts = []

        def replace(path, target):
            attempts.append(path)
            if len(attempts) == 1:
                raise PermissionError(errno.EACCES, "fixture reader open")
            return real_replace(path, target)

        with patch.object(Path, "replace", new=replace), patch.object(c.time, "sleep"):
            c.write_json(self.path, {"new": True})
        self.assertEqual(json.loads(self.path.read_text()), {"new": True})
        self.assertEqual(len(attempts), 2)
        self.assertNotEqual(attempts[0].name, "state.json.tmp")
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_broken_stderr_does_not_bypass_owned_child_wait(self):
        child = Mock(pid=123, returncode=0)
        child.poll.side_effect = [None, None, 0]
        state = {"current_child": {"pid": 123, "returncode": None}}
        broken_stream = Mock()
        broken_stream.write.side_effect = OSError(errno.EPIPE, "fixture closed diagnostics")
        with patch.object(c.sys, "stderr", broken_stream), patch.object(c.time, "sleep") as pause:
            c.wait_owned_child_after_metadata_fault(state, child)
        self.assertTrue(pause.called)
        self.assertTrue(state["metadata_fault_child_exit_observed"])
        self.assertEqual(state["current_child"]["returncode"], 0)

    def test_child_exit_before_fault_handler_is_still_recorded(self):
        child = Mock(pid=123, returncode=7)
        child.poll.return_value = 7
        state = {}
        c.wait_owned_child_after_metadata_fault(state, child)
        self.assertEqual(state["current_child"]["returncode"], 7)
        self.assertTrue(state["metadata_fault_child_exit_observed"])

    def test_nonsharing_error_is_not_retried_and_original_survives(self):
        with patch.object(Path, "replace", side_effect=OSError(errno.ENOSPC, "fixture full")) as replace:
            with self.assertRaises(OSError):
                c.write_json(self.path, {"new": True})
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(json.loads(self.path.read_text()), {"original": True})
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_persistent_eacces_has_a_bound_and_preserves_original(self):
        with patch.object(Path, "replace", side_effect=PermissionError(errno.EACCES, "fixture persistent")) as replace:
            with patch.object(c.time, "monotonic", side_effect=[0., 4.]):
                with self.assertRaises(PermissionError):
                    c.write_json(self.path, {"new": True})
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(json.loads(self.path.read_text()), {"original": True})
        self.assertFalse(list(self.root.glob("*.tmp")))


class UlpTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"source_hashes": c.NAV_PINS, "protocol": {"navigation_acceptance": {}}}
        transient = {"scheduled_samples": 751, "valid_truth_samples": 751, "truth_coverage": 1.0}
        self.report = {"evaluation_status": "RECORDED_WITH_CENSORED_FAILURES", "incomplete_reasons": [],
                       "malformed_input_counts": {"fixture": 0},
                       "interval": {"start_s": 19., "end_s": 94.1, "sample_period_s": .1},
                       "whole_interval": {"scheduled_samples": 752, "matched_truth_samples": 752,
                           "transients": {"base_link": {"distance": dict(transient), "height": dict(transient)}}}}

    class Module:
        @staticmethod
        def navigation_verdict(report, gates):
            if any(row["scheduled_samples"] != report["whole_interval"]["scheduled_samples"]
                   for row in report["whole_interval"]["transients"]["base_link"].values()):
                return "INCOMPLETE_EVIDENCE", {"reason": "Transient denominator differs from the whole interval"}
            if report.get("second_error"):
                return "INCOMPLETE_EVIDENCE", {"reason": "a second unrelated defect"}
            return "PASS", {}

    def test_only_known_ulp_is_disclosed_without_modifying_original(self):
        before = json.dumps(self.report, sort_keys=True)
        outcome = c.nav_audit(self.Module(), self.plan, self.report)
        self.assertEqual(outcome["original_navigation_verdict"], "INCOMPLETE_EVIDENCE")
        self.assertEqual(json.dumps(self.report, sort_keys=True), before)

    def test_second_structure_error_is_not_hidden(self):
        self.report["second_error"] = True
        with self.assertRaises(ValueError):
            c.nav_audit(self.Module(), self.plan, self.report)

    def test_non_ulp_grid_difference_is_rejected(self):
        self.report["interval"]["end_s"] = 94.15
        with self.assertRaises(ValueError):
            c.nav_audit(self.Module(), self.plan, self.report)


if __name__ == "__main__":
    unittest.main()
