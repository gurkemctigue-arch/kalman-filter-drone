"""Batch policy uses real immutable slot/report readers with a fixture executor."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import monitor_project_progress as monitor
from scripts import run_reliability_v4 as normal
from scripts import run_reliability_v4_batch as batch


class FixtureRunner:
    ROOT = batch.ROOT
    __file__ = str(batch.RUNNER_PATH)
    load = staticmethod(normal.load)
    required_evaluators = staticmethod(normal.required_evaluators)
    read_evaluation = staticmethod(normal.read_evaluation)
    read_slots = staticmethod(normal.read_slots)

    def __init__(self, outcomes):
        self.outcomes, self.calls, self.verify_calls = outcomes, [], 0

    def validate_plan(self, plan, path=None):
        if path is not None:
            assert path == (Path(plan["output"]) / "plan.json").resolve()

    def verify_sources(self, plan):
        self.verify_calls += 1

    def run_plan(self, plan, *, max_new_trials):
        self.calls.append(max_new_trials)
        rows = self.read_slots(plan)
        trial = next(trial for trial in plan["trials"] if rows[trial["id"]]["status"] == "PENDING")
        outcome = self.outcomes[len(self.calls) - 1]
        if outcome.get("delay"):
            time.sleep(outcome["delay"])
        directory = Path(trial["directory"])
        directory.mkdir()
        marker = normal.record_path(plan, trial, "started.json")
        normal.write_new(marker, {"id": trial["id"], "plan_sha256": plan["plan_sha256"], "started_utc": normal.utc_now()})
        if outcome.get("raise"):
            (directory / "original_failure.log").write_text("retained original command evidence\n", encoding="utf-8")
            raise RuntimeError("fixture original command failed")
        evaluations = []
        for spec in trial["evaluations"]:
            kind = spec["kind"]
            if kind == outcome.get("missing"):
                continue
            result = outcome.get(kind, "PASS") if kind in {"source_clock", "native_startup"} else (
                "FAIL" if kind == "surface_flight" and outcome.get("status") == "FAIL" else
                "RECORDED_WITH_CENSORED_FAILURES" if kind == "navigation" else "PASS")
            provenance = {"script_sha256": plan["source_hashes"].get(spec["script"]),
                          "dependencies": {str(batch.ROOT / name): plan["source_hashes"][name]
                                           for name in normal.REPORT_PROVENANCE_HELPERS.get(kind, ())}}
            if kind == "source_clock":
                report = {"schema_version": 1, "trial": str(directory), "evaluation_status": result,
                          "source_clock_pass": result == "PASS", "clock_domain_valid": result == "PASS",
                          "vehicle_frame_continuity_valid": True, "failures": {} if result == "PASS" else {"fixture_clock_fault": 1},
                          "incomplete_evidence": {}, "counts": {"raw_px4": 3, "timing_diagnostics": 3,
                          "adapted_odometry": 3, "claimed_accepted": 3, "claimed_rejected": 0,
                          "independently_matched_triplets": 3}, "evaluation_source": provenance}
            elif kind == "native_startup":
                report = {"schema_version": 1, "trial": str(directory), "evaluation_status": result,
                          "native_startup_pass": result == "PASS", "checks": {key: result == "PASS" for key in normal.NATIVE_STARTUP_CHECKS},
                          "failures": {} if result == "PASS" else {"fixture_native_fault": 1},
                          "incomplete_evidence": {}, "evaluation_source": provenance}
            else:
                report = {"fixture_only": True, "result": result}
            normal.write_new(spec["report"], report)
            evaluations.append({"kind": kind, "report": spec["report"], "result": result,
                                "reported_verdict": result, "report_sha256": normal.sha(spec["report"]),
                                "error": None, "execution": {"returncode": 0 if result == "PASS" or kind not in
                                {"source_clock", "native_startup"} else 2, "error": None}})
        if outcome.get("tamper_clock"):
            clock = next(spec for spec in trial["evaluations"] if spec["kind"] == "source_clock")
            data = normal.load(clock["report"])
            data["evaluation_source"]["script_sha256"] = "0" * 64
            Path(clock["report"]).write_text(json.dumps(data), encoding="utf-8")
        record = {"status": outcome.get("status", "PASS"), "engineering_result": outcome.get("status", "PASS"),
                  "execution_status": "COMPLETED", "infrastructure_stop": outcome.get("infrastructure_stop", False),
                  "flight_exit_code": 0, "runtime_configuration": {"errors": []},
                  "cleanup": {"residual_processes": []}, "evaluations": evaluations}
        normal.finalize(plan, trial, record)
        return {"started_this_invocation": 1, "stop": "INFRASTRUCTURE_STOP" if outcome.get("infrastructure_stop") else None,
                "all_engineering_pass": record["status"] == "PASS"}


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.output = self.directory / "owner"

    def tearDown(self):
        self.temporary.cleanup()

    def plan(self, count=2, mode="PROBE"):
        output = self.directory / "matrix"
        output.mkdir()
        helpers = {"scripts/run_reliability_v4.py", "scripts/run_reliability_v4_batch.py",
                   "scripts/evaluate_px4_source_clock.py", "scripts/evaluate_native_startup.py",
                   *normal.SOURCE_CLOCK_HELPERS}
        for kind in ("source_clock", "native_startup", "surface_flight", "navigation"):
            helpers.update(normal.REPORT_PROVENANCE_HELPERS.get(kind, ()))
        hashes = {name: normal.sha(batch.ROOT / name) for name in helpers}
        trials = []
        for i in range(count):
            identifier = f"fixture_slot_{i}"
            trial_dir = self.directory / identifier
            evaluations = [{"kind": kind, "script": "scripts/" + script,
                            "report": str(trial_dir / (kind + ".json"))}
                           for kind, script in [("source_clock", "evaluate_px4_source_clock.py"),
                                                ("native_startup", "evaluate_native_startup.py"),
                                                ("surface_flight", "evaluate_stage1_flight.py"),
                                                ("navigation", "evaluate_navigation_reference.py")]]
            trials.append({"id": identifier, "name": identifier, "group": "stage1_position",
                           "directory": str(trial_dir), "evaluations": evaluations})
        plan = {"frozen_root": str(batch.ROOT), "output": str(output), "mode": mode,
                "source_hashes": hashes, "trials": trials}
        plan["plan_sha256"] = normal.digest(plan)
        normal.write_new(output / "plan.json", plan)
        return plan, output / "plan.json"

    def run_fixture(self, outcomes, *, policy="core", mode="PROBE", limit=0):
        plan, path = self.plan(len(outcomes), mode)
        runner = FixtureRunner(outcomes)
        with patch.object(batch, "load_runner", return_value=runner):
            result = batch.run_batch(path, self.output, policy, limit)
        return result, runner, plan

    def test_normal_runner_import_is_fixed_to_same_root(self):
        runner = batch.load_runner()
        self.assertEqual(Path(runner.__file__).resolve(), batch.RUNNER_PATH.resolve())
        self.assertEqual(runner.ROOT.resolve(), batch.ROOT)

    def test_exit_zero_with_core_slot_fail_stops_without_consuming_next(self):
        result, runner, plan = self.run_fixture([{"status": "FAIL"}, {}])
        self.assertEqual(result["status"], "STOPPED_FAULT")
        self.assertEqual(result["reason"], "core_slot_not_passed")
        self.assertEqual(runner.calls, [1])
        self.assertFalse(result["all_engineering_pass"])
        self.assertEqual(normal.read_slots(plan)[plan["trials"][1]["id"]]["status"], "PENDING")

    def test_extension_algorithm_failure_can_continue_and_completion_is_not_all_pass(self):
        result, runner, plan = self.run_fixture([{"status": "FAIL"}, {}], policy="extension", mode="EXTENSION_PROBE")
        self.assertEqual(result["status"], "COMPLETED")
        self.assertTrue(result["all_slots_terminal"])
        self.assertFalse(result["all_engineering_pass"])
        self.assertEqual(result["status_counts"], {"FAIL": 1, "PASS": 1})
        self.assertEqual(runner.calls, [1, 1])
        events = [json.loads(line) for line in (self.output / "events.jsonl").read_text().splitlines()]
        self.assertEqual([row["active_slot"] for row in events if row["event"] == "slot_invocation_started"],
                         [trial["id"] for trial in plan["trials"]])

    def test_formal_plans_are_rejected_by_every_policy_without_execution(self):
        self.assertEqual(set(batch.POLICY_MODES), {"core", "extension"})
        for mode in ("FORMAL", "EXTENSION_FORMAL"):
            for policy in (*batch.POLICY_MODES, "formal"):
                with self.subTest(mode=mode, policy=policy), tempfile.TemporaryDirectory() as directory:
                    self.directory, self.output = Path(directory), Path(directory) / "owner"
                    _, path = self.plan(mode=mode)
                    runner = FixtureRunner([{}, {}])
                    with patch.object(batch, "load_runner", return_value=runner):
                        with self.assertRaises(ValueError):
                            batch.run_batch(path, self.output, policy)
                    self.assertEqual(runner.calls, [])
                    self.assertFalse(self.output.exists())

    def test_clock_and_native_failure_stop_extension_even_when_algorithm_fail_is_allowed(self):
        for kind in ("source_clock", "native_startup"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                self.directory, self.output = Path(directory), Path(directory) / "owner"
                result, runner, _ = self.run_fixture([{"status": "FAIL", kind: "FAIL"}, {}],
                                                    policy="extension", mode="EXTENSION_PROBE")
                self.assertEqual(result["status"], "STOPPED_FAULT")
                self.assertEqual(result["reason"], kind + "_not_independently_passed")
                self.assertEqual(runner.calls, [1])

    def test_missing_clock_evidence_and_invalid_source_hash_stop(self):
        for outcome, reason in [({"missing": "source_clock"}, "missing_or_duplicate_required_evaluators"),
                                ({"tamper_clock": True}, "source_clock_report_binding_or_contract_invalid")]:
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as directory:
                self.directory, self.output = Path(directory), Path(directory) / "owner"
                result, runner, _ = self.run_fixture([outcome, {}])
                self.assertEqual(result["reason"], reason)
                self.assertEqual(runner.calls, [1])

    def test_infrastructure_stop_stops_and_original_fail_is_retained(self):
        result, runner, plan = self.run_fixture([{"status": "FAIL", "infrastructure_stop": True}, {}],
                                                policy="extension", mode="EXTENSION_PROBE")
        self.assertEqual(result["reason"], "infrastructure_stop_or_missing_evidence")
        self.assertEqual(runner.calls, [1])
        self.assertEqual(normal.read_slots(plan)[plan["trials"][0]["id"]]["status"], "FAIL")

    def test_exception_retains_original_running_marker_and_command_evidence(self):
        result, runner, plan = self.run_fixture([{"raise": True}, {}])
        self.assertEqual(result["status"], "STOPPED_FAULT")
        trial = plan["trials"][0]
        self.assertTrue(normal.record_path(plan, trial, "started.json").is_file())
        self.assertFalse(normal.record_path(plan, trial).exists())
        self.assertEqual((Path(trial["directory"]) / "original_failure.log").read_text(), "retained original command evidence\n")
        self.assertEqual(result["status_counts"], {"RUNNING": 1, "PENDING": 1})
        self.assertTrue((self.output / "exception.json").is_file())
        self.assertEqual(runner.calls, [1])

    def test_existing_failed_slot_is_not_retried_or_skipped_by_new_core_owner(self):
        result, runner, plan = self.run_fixture([{"status": "FAIL"}, {}])
        slot = normal.record_path(plan, plan["trials"][0])
        before = slot.read_bytes()
        other_output = self.directory / "owner_second"
        with patch.object(batch, "load_runner", return_value=runner):
            second = batch.run_batch(Path(plan["output"]) / "plan.json", other_output, "core")
        self.assertEqual(second["status"], "STOPPED_FAULT")
        self.assertEqual(runner.calls, [1])
        self.assertEqual(slot.read_bytes(), before)

    def test_existing_interrupted_or_incomplete_slot_is_never_retried(self):
        for status in ("INTERRUPTED", "INCOMPLETE_EVIDENCE", "EVALUATION_PENDING", "INFRASTRUCTURE_ERROR"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                self.directory, self.output = Path(directory), Path(directory) / "owner"
                _, runner, plan = self.run_fixture([{"status": status}, {}],
                                                   policy="extension", mode="EXTENSION_PROBE")
                slot = normal.record_path(plan, plan["trials"][0])
                before = slot.read_bytes()
                with patch.object(batch, "load_runner", return_value=runner):
                    result = batch.run_batch(Path(plan["output"]) / "plan.json",
                                             self.directory / "second_owner", "extension")
                self.assertEqual(result["status"], "STOPPED_FAULT")
                self.assertEqual(result["reason"], "non_algorithm_terminal_status:" + status)
                self.assertEqual(runner.calls, [1])
                self.assertEqual(slot.read_bytes(), before)

    def test_running_original_attempt_is_retained_and_blocks_a_new_owner(self):
        _, runner, plan = self.run_fixture([{"raise": True}, {}])
        marker = normal.record_path(plan, plan["trials"][0], "started.json")
        before = marker.read_bytes()
        with patch.object(batch, "load_runner", return_value=runner):
            result = batch.run_batch(Path(plan["output"]) / "plan.json",
                                     self.directory / "second_owner", "core")
        self.assertEqual(result["status"], "STOPPED_FAULT")
        self.assertEqual(runner.calls, [1])
        self.assertEqual(marker.read_bytes(), before)
        self.assertFalse(normal.record_path(plan, plan["trials"][0]).exists())

    def test_registered_owner_source_hash_is_required_before_creating_output(self):
        plan, path = self.plan()
        plan["source_hashes"]["scripts/run_reliability_v4_batch.py"] = "0" * 64
        path.write_text(json.dumps(plan), encoding="utf-8")
        runner = FixtureRunner([{}, {}])
        with patch.object(batch, "load_runner", return_value=runner):
            with self.assertRaisesRegex(ValueError, "source hashes differ"):
                batch.run_batch(path, self.output, "core")
        self.assertEqual(runner.calls, [])
        self.assertFalse(self.output.exists())

    def test_limit_is_terminal_for_owner_but_not_complete_for_plan(self):
        result, runner, _ = self.run_fixture([{}, {}], limit=1)
        self.assertEqual(result["status"], "LIMIT_REACHED")
        self.assertFalse(result["all_slots_terminal"])
        self.assertFalse(result["all_engineering_pass"])
        self.assertEqual(runner.calls, [1])

    def test_heartbeat_and_terminal_identity_are_written_without_extending_runner(self):
        with patch.object(batch, "HEARTBEAT_S", .01):
            result, runner, _ = self.run_fixture([{"delay": .06}])
        events = [json.loads(line) for line in (self.output / "events.jsonl").read_text().splitlines()]
        self.assertTrue(any(event["event"] == "heartbeat" for event in events))
        self.assertEqual(events[-1]["event"], "owner_terminal")
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["owner"]["pid"], __import__("os").getpid())
        self.assertEqual(json.loads((self.output / "owner_started.json").read_text())["status"], "RUNNING")
        self.assertEqual(json.loads((self.output / "owner_terminal.json").read_text())["status"], "COMPLETED")
        self.assertGreaterEqual(runner.verify_calls, 1)

    def test_existing_monitor_reads_sidecar_without_losing_failures_or_unattempted_slots(self):
        for policy, mode, terminals, unattempted, state in (
                ("core", "PROBE", 1, 1, "STOPPED_FAULT"),
                ("extension", "EXTENSION_PROBE", 2, 0, "COMPLETED")):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as directory:
                self.directory, self.output = Path(directory), Path(directory) / "owner"
                result, _, plan = self.run_fixture([{"status": "FAIL"}, {}], policy=policy, mode=mode)
                records = monitor.source_records({"events": str(self.output / "monitor_events.jsonl"),
                                                  "plan": str(Path(plan["output"]) / "plan.json")})
                records["ledger"] = {"returncode": 0, "finished_utc": result["finished_utc"]}
                summary = monitor.evidence_summary(records)
                self.assertEqual(summary["errors"], [])
                self.assertEqual(summary["state"], state)
                self.assertEqual(summary["planned_slots"], 2)
                self.assertEqual(summary["attempted_slots"], terminals)
                self.assertEqual(summary["recorded_terminal_slots"], terminals)
                self.assertEqual(summary["unattempted_slots"], unattempted)
                self.assertEqual(summary["attempted_without_terminal"], [])
                self.assertEqual(summary["status_counts"].get("FAIL"), 1)
                self.assertEqual(summary["status_counts"].get("PASS", 0), terminals - 1)
                self.assertFalse(result["all_engineering_pass"])
                self.assertTrue(all(monitor.timestamp(row["utc"]) is not None for row in records["events"]))
                self.assertEqual(records["events"][-1]["event"],
                                 "STOPPED_FAULT" if policy == "core" else "COMPLETE_SLOT")
                original_events = [json.loads(line) for line in (self.output / "events.jsonl").read_text().splitlines()]
                self.assertEqual(original_events[-1]["event"], "owner_terminal")

    def test_policy_cannot_relax_core_probe_or_swap_runner_source(self):
        plan, path = self.plan()
        runner = FixtureRunner([{}, {}])
        with patch.object(batch, "load_runner", return_value=runner):
            with self.assertRaisesRegex(ValueError, "Policy"):
                batch.run_batch(path, self.output, "extension")
        runner.__file__ = str(self.directory / "other_runner.py")
        with patch.object(batch, "load_runner", return_value=runner):
            with self.assertRaisesRegex(ValueError, "Same-root"):
                batch.run_batch(path, self.output, "core")
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
