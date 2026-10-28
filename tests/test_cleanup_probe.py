"""Pure small-JSON fixtures: never launch a process, ROS or a simulator."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cleanup_probe_fixture", ROOT / "scripts/run_cleanup_probe.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class CleanupProbeTests(unittest.TestCase):
    def inputs(self, root):
        return {"formal_plan": root / "full_plan_research_v3/plan.json",
                "offline_manifest": root / "full_plan_research_v3/offline_manifest.json",
                "engineering_manifest": root / "extended_engineering_v3_matrix/manifest.json",
                "supplement_manifest": root / "full_plan_supplement_v3/manifest.json"}

    def readiness(self, root):
        return probe.validate_completed_research(root, **self.inputs(root))

    def rewrite_supplement(self, root, change):
        path = self.inputs(root)["supplement_manifest"]
        data = probe.load(path)
        change(data)
        data["plan_sha256"] = probe.digest(data["plan"])
        write(path, data)

    def completed_fixture(self, root):
        names = [f"formal_{index:03d}" for index in range(166)]
        original_root = "/root/uav_tracking_fullplan_v3"
        matrices = []
        for key, selected, kind in (("velocity", names[:80], "stage1"),
                                     ("position", names[80:100], "stage1"),
                                     ("stage23", names[100:], "stage23")):
            relative = f"{key}.json"
            matrices.append({"kind": kind, "trial_names": selected,
                             "report": f"{original_root}/results/{relative}"})
            if kind == "stage1":
                child = {"trials": [{"name": name, "result": "PASS"} for name in selected]}
            else:
                child = {"slots": [{"trial": {"name": name}, "status": "PASS"} for name in selected]}
            write(root / relative, child)
        plan = {"schema_version": 1, "frozen_root": original_root,
                "source_hashes": {"scripts/flight.py": "a" * 64}, "preregistration_sha256": "b" * 64,
                "matrices": matrices, "trials": [{"name": name} for name in names]}
        plan["plan_sha256"] = probe.digest(plan)
        study = root / "full_plan_research_v3"
        write(study / "plan.json", plan)
        write(study / "offline_manifest.json", {
            "schema_version": 1, "plan_sha256": plan["plan_sha256"],
            "trials": {name: {"name": name, "status": "RECORDED"} for name in names}})
        engineering_plan = {"trials": [{"name": f"engineering_{index}"} for index in range(16)],
                            "expected_trials": 16, "primary_166_included": False,
                            "source_hashes": plan["source_hashes"],
                            "preregistration_sha256": plan["preregistration_sha256"]}
        write(root / "extended_engineering_v3_matrix/manifest.json", {
            "schema_version": 1, "source": "EXTENDED_ENGINEERING_16_FLIGHTS",
            "plan_sha256": probe.digest(engineering_plan), "plan": engineering_plan,
            "slots": [{"trial": trial, "status": "PASS"} for trial in engineering_plan["trials"]]})
        inputs = self.inputs(root)
        sources = []
        for key in ("formal_plan", "offline_manifest", "engineering_manifest"):
            path = inputs[key]
            declared_path = str(probe.PurePosixPath(original_root) / "results" / path.relative_to(root).as_posix())
            sources.append({"path": declared_path, "exists": True,
                            "bytes": path.stat().st_size, "sha256": probe.sha(path)})
        supplement_plan = {"frozen_root": original_root, "source_main_plan_sha256": plan["plan_sha256"],
                           "source_engineering_plan_sha256": probe.digest(engineering_plan),
                           "sources": sources, "trials": engineering_plan["trials"]}
        write(inputs["supplement_manifest"], {
            "schema_version": 1, "source": "POST_FLIGHT_ENGINEERING_16_SUPPLEMENT",
            "plan_sha256": probe.digest(supplement_plan), "plan": supplement_plan,
            "slots": [{"trial": trial, "status": "RECORDED", "tasks": [
                {"kind": kind, "status": "RECORDED", "returncode": 0}
                for kind in ("online_state_accuracy", "follow_dynamics")]}
                for trial in engineering_plan["trials"]]})

    def assessment(self, *, death=None, missing=None, pre_stop=None, fallback=False):
        plan = probe.probe_plan("stage1", "cleanup_fixture")
        nodes = plan["expected_ros_executables"]
        starts = [f"[INFO] [{name}-{index}]: process started with pid [{100+index}]"
                  for index, name in enumerate(nodes)]
        finishes = []
        early = []
        for index, name in enumerate(nodes):
            if name == missing:
                continue
            if name == death:
                line = f"[ERROR] [{name}-{index}]: process has died [pid {100+index}, exit code -2, cmd 'fixture']."
            else:
                line = f"[INFO] [{name}-{index}]: process has finished cleanly [pid {100+index}]"
            (early if name == pre_stop else finishes).append(line)
        text = "\n".join(starts + early + ["[WARNING] [launch]: user interrupted with ctrl-c (SIGINT)"] + finishes)
        events = [{"kind": "process_start", "service": "ros", "stdin_devnull": True},
                  {"kind": "signal_sent", "service": "ros", "scope": "PROCESS", "signal": "SIGINT"}]
        if fallback:
            events.extend([{"kind": "wait_timeout", "service": "ros"},
                           {"kind": "signal_sent", "service": "ros", "scope": "GROUP", "signal": "SIGTERM"}])
        return probe.assess_cleanup(plan, probe.parse_ros_exits(text), events, [], None,
                                    {"monitor_success": True}, {"monitor": 0, "ros": 0, "agent": -2}, [], {})

    def test_graphs_cover_both_motion_nodes_and_physical_gimbal(self):
        first = probe.probe_plan("stage1", "cleanup_fixture")
        third = probe.probe_plan("stage3_multi", "cleanup_fixture")
        self.assertEqual(set(first["expected_ros_executables"]), probe.COMMON_NODES | {"scenario_motion"})
        self.assertEqual(set(third["expected_ros_executables"]), probe.COMMON_NODES | {"stage2_motion", "gimbal_adapter"})
        self.assertIn("--multi-target", third["runner_args"])
        self.assertIn("--reselect-after-loss", third["runner_args"])
        self.assertNotEqual(first["name"], third["name"])
        self.assertFalse(first["primary_166_included"])

    def test_default_only_prints_plan_without_executing_or_creating_results(self):
        with patch.object(sys, "argv", ["probe", "--probe", "stage1"]), \
                patch.object(probe, "execute_probe") as execute, contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(probe.main(), 0)
        execute.assert_not_called()
        self.assertEqual(json.loads(stdout.getvalue())["status"], "PLAN_ONLY_NO_PROCESSES_OR_OUTPUT_FILES")

    def test_complete_ledgers_accept_retained_failures_as_terminal_not_as_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.completed_fixture(root)
            child = probe.load(root / "velocity.json")
            child["trials"][0]["result"] = "FAIL"
            write(root / "velocity.json", child)
            evidence = self.readiness(root)
            self.assertEqual(evidence["primary_flights_terminal"], 166)
            self.assertEqual(evidence["primary_offline_terminal"], 166)
            self.assertEqual(evidence["engineering_terminal"], 16)
            self.assertEqual(evidence["supplement_terminal"], 16)
            self.assertEqual(evidence["supplement_status_counts"], {"RECORDED": 16})
            self.assertIn("full_plan_research_v3", evidence["explicit_inputs"]["formal_plan"])
            self.assertTrue(evidence["completion_does_not_mean_all_pass"])

    def test_pending_primary_flight_blocks_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.completed_fixture(root)
            child = probe.load(root / "velocity.json")
            child["trials"][0]["result"] = "RUNNING_FLIGHT"
            write(root / "velocity.json", child)
            with self.assertRaisesRegex(ValueError, "not uniquely terminal"):
                self.readiness(root)

    def test_missing_offline_attempt_blocks_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.completed_fixture(root)
            path = self.inputs(root)["offline_manifest"]
            data = probe.load(path)
            data["trials"].pop("formal_000")
            write(path, data)
            with self.assertRaisesRegex(ValueError, "166 bound offline"):
                self.readiness(root)

    def test_pending_engineering_flight_blocks_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.completed_fixture(root)
            path = self.inputs(root)["engineering_manifest"]
            data = probe.load(path)
            data["slots"][0]["status"] = "PENDING"
            write(path, data)
            with self.assertRaisesRegex(ValueError, "sixteen-slot"):
                self.readiness(root)

    def test_corrupt_plan_digest_blocks_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.completed_fixture(root)
            path = self.inputs(root)["formal_plan"]
            data = probe.load(path)
            data["frozen_root"] = "/changed"
            write(path, data)
            with self.assertRaisesRegex(ValueError, "digest"):
                self.readiness(root)

    def test_readiness_cli_requires_all_explicit_evidence_paths(self):
        with patch.object(sys, "argv", ["probe", "--probe", "stage1", "--check-ready",
                                        "--formal-results", "unused"]), \
                patch.object(probe, "execute_probe") as execute, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            probe.main()
        self.assertEqual(raised.exception.code, 2)
        execute.assert_not_called()

    def test_missing_supplement_never_authorizes_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.completed_fixture(root)
            self.inputs(root)["supplement_manifest"].unlink()
            with self.assertRaises(FileNotFoundError):
                self.readiness(root)

    def test_every_nonterminal_supplement_status_blocks_probe(self):
        for status in ("PENDING", "RUNNING_ANALYSIS", "UNKNOWN"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.completed_fixture(root)
                self.rewrite_supplement(root, lambda data: data["slots"][0].update(status=status))
                with self.assertRaisesRegex(ValueError, "supplementary slots"):
                    self.readiness(root)

    def test_supplement_retained_failure_and_interruption_are_terminal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.completed_fixture(root)
            def failures(data):
                data["slots"][0].update(status="INCOMPLETE_EVIDENCE", tasks=[])
                data["slots"][1].update(status="INTERRUPTED", tasks=[])
            self.rewrite_supplement(root, failures)
            result = self.readiness(root)
            self.assertEqual(result["supplement_terminal"], 16)
            self.assertEqual(result["supplement_status_counts"],
                             {"RECORDED": 14, "INCOMPLETE_EVIDENCE": 1, "INTERRUPTED": 1})
            self.assertTrue(result["completion_does_not_mean_all_pass"])

    def test_rehashed_supplement_must_bind_both_exact_plan_shas(self):
        for key in ("source_main_plan_sha256", "source_engineering_plan_sha256", "frozen_root"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.completed_fixture(root)
                self.rewrite_supplement(root, lambda data: data["plan"].update({key: "foreign"}))
                with self.assertRaisesRegex(ValueError, "both frozen plans"):
                    self.readiness(root)

    def test_corrupt_supplement_digest_blocks_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.completed_fixture(root)
            path = self.inputs(root)["supplement_manifest"]
            data = probe.load(path)
            data["plan"]["scope"] = "changed after freezing"
            write(path, data)
            with self.assertRaisesRegex(ValueError, "both frozen plans"):
                self.readiness(root)

    def test_missing_or_swapped_supplement_slot_blocks_probe(self):
        for change in (lambda data: data["slots"].pop(),
                       lambda data: data["slots"][0].update(trial=data["slots"][1]["trial"])):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.completed_fixture(root)
                self.rewrite_supplement(root, change)
                with self.assertRaisesRegex(ValueError, "supplementary slots"):
                    self.readiness(root)

    def test_recorded_supplement_requires_completed_distinct_tasks(self):
        for tasks in ([], [{"kind": "follow_dynamics", "status": "RUNNING_ANALYSIS"}],
                      [{"kind": kind, "status": "RECORDED", "returncode": 2}
                       for kind in ("online_state_accuracy", "follow_dynamics")]):
            with self.subTest(tasks=tasks), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.completed_fixture(root)
                self.rewrite_supplement(root, lambda data: data["slots"][0].update(tasks=tasks))
                with self.assertRaisesRegex(ValueError, "task bookkeeping"):
                    self.readiness(root)

    def test_stale_supplement_input_hash_blocks_even_valid_terminal_ledger(self):
        for key in ("offline_manifest", "engineering_manifest"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.completed_fixture(root)
                path = self.inputs(root)[key]
                data = probe.load(path)
                if key == "offline_manifest":
                    data["trials"]["formal_000"]["status"] = "INCOMPLETE_EVIDENCE"
                else:
                    data["slots"][0]["status"] = "FAIL"
                write(path, data)
                with self.assertRaisesRegex(ValueError, "source SHA/size"):
                    self.readiness(root)

    def test_missing_duplicate_and_tampered_source_sha_are_rejected(self):
        changes = (lambda data: data["plan"]["sources"].pop(),
                   lambda data: data["plan"]["sources"].append(data["plan"]["sources"][0].copy()),
                   lambda data: data["plan"]["sources"][0].update(sha256="0" * 64))
        for change in changes:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.completed_fixture(root)
                self.rewrite_supplement(root, change)
                with self.assertRaisesRegex(ValueError, "source SHA"):
                    self.readiness(root)

    def test_engineering_from_another_source_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.completed_fixture(root)
            path = self.inputs(root)["engineering_manifest"]
            data = probe.load(path)
            data["plan"]["source_hashes"] = {"scripts/flight.py": "c" * 64}
            data["plan_sha256"] = probe.digest(data["plan"])
            write(path, data)
            with self.assertRaisesRegex(ValueError, "engineering ledger"):
                self.readiness(root)

    def test_explicit_inputs_cannot_escape_formal_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "formal"
            self.completed_fixture(root)
            outside = parent / "foreign.json"
            write(outside, {})
            inputs = self.inputs(root)
            inputs["supplement_manifest"] = outside
            with self.assertRaisesRegex(ValueError, "within the declared formal results"):
                probe.validate_completed_research(root, **inputs)

    def test_relative_frozen_matrix_report_paths_resolve_under_original_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.completed_fixture(root)
            path = self.inputs(root)["formal_plan"]
            plan = probe.load(path)
            for matrix in plan["matrices"]:
                matrix["report"] = "results/" + probe.PurePosixPath(matrix["report"]).name
            plan["plan_sha256"] = probe.digest({key: value for key, value in plan.items() if key != "plan_sha256"})
            write(path, plan)
            offline_path = self.inputs(root)["offline_manifest"]
            offline = probe.load(offline_path)
            offline["plan_sha256"] = plan["plan_sha256"]
            write(offline_path, offline)
            def rebind(data):
                data["plan"]["source_main_plan_sha256"] = plan["plan_sha256"]
                for source in data["plan"]["sources"]:
                    if source["path"].endswith("/plan.json"):
                        source.update(bytes=path.stat().st_size, sha256=probe.sha(path))
                    elif source["path"].endswith("/offline_manifest.json"):
                        source.update(bytes=offline_path.stat().st_size, sha256=probe.sha(offline_path))
            self.rewrite_supplement(root, rebind)
            self.assertEqual(self.readiness(root)["primary_flights_terminal"], 166)

    def test_outer_zero_does_not_hide_child_sigint_failure(self):
        assessment = self.assessment(death="controller")
        self.assertEqual(assessment["result"], "FAIL")
        self.assertTrue(assessment["checks"]["outer_ros_exit_zero"])
        self.assertFalse(assessment["checks"]["every_node_clean_after_shutdown"])

    def test_missing_child_exit_cannot_pass(self):
        self.assertEqual(self.assessment(missing="state_estimator")["result"], "FAIL")

    def test_early_clean_child_exit_cannot_pass(self):
        self.assertEqual(self.assessment(pre_stop="detector")["result"], "FAIL")

    def test_ros_fallback_cannot_be_reported_as_clean(self):
        assessment = self.assessment(fallback=True)
        self.assertEqual(assessment["result"], "FAIL")
        self.assertFalse(assessment["checks"]["no_ros_timeout_or_signal_error"])

    def test_all_children_need_individual_clean_evidence(self):
        self.assertEqual(self.assessment()["result"], "PASS")

    def test_formal_prefix_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "cleanup_"):
            probe.probe_plan("stage1", "fullplan_v2")


if __name__ == "__main__":
    unittest.main()
