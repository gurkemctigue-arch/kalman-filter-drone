"""Synthetic immutable matrices only; no simulator or bag database reads."""
from datetime import timedelta
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests import test_reliability_v4_extensions as extensions
from tests import test_reliability_v4_runner as fixtures

SPEC = importlib.util.spec_from_file_location("probe_gate_builder", fixtures.ROOT / "scripts/build_reliability_v4_probe_gate.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
v4 = builder.v4


def run_fixture(plan, commands=None):
    # The existing orchestration fixture checks the same immutable source
    # tree before/after every fake command. Cache that fixture-construction
    # check once; gate generation itself uses entirely unmocked file checks.
    actual = fixtures.v4.verify_sources
    checked = False
    def once(frozen):
        nonlocal checked
        if not checked:
            actual(frozen)
            checked = True
    with patch.object(fixtures.v4, "verify_sources", side_effect=once):
        return fixtures.run(plan, commands)


def matrix(root, *, extension=False, algorithm_failure=False, commands=None, completed=True):
    if extension:
        extensions.extension_fixture(root, registered=True)
    else:
        fixtures.fixture(root, gates=True)
    # The gate implementation and validator really match this synthetic
    # target snapshot; online/flight commands remain inert fixture sources.
    for name in (builder.SCRIPT, builder.RUNNER):
        shutil.copy2(fixtures.ROOT / name, root / name)
    if extension:
        plan = extensions.make(root, seeds=[4], output="results/development", prefix="reliability_v4_development")
        fixtures.v4.persist_plan(plan)
        commands = commands or extensions.ExtensionCommands(algorithm_failure=algorithm_failure)
    else:
        plan = fixtures.plan(root, groups=list(v4.GROUPS), classes=list(v4.CLASSES), seeds=[4], suffix="development")
        commands = commands or fixtures.FakeCommands()
    if completed:
        result = run_fixture(plan, commands)
        if result["terminal_count"] != len(plan["trials"]) or result["stop"]:
            raise AssertionError(result)
    return plan, Path(plan["output"]) / "plan.json"


def preserved_hashes(plan):
    paths = [Path(plan["output"]) / "plan.json"]
    for trial in plan["trials"]:
        paths.append(v4.record_path(plan, trial))
        paths.extend(Path(spec["report"]) for spec in trial["evaluations"])
    return {str(path): v4.sha(path) for path in paths}


def gimbal_overrides(plan, source_path):
    """Pure fixture executions, explicitly never a claim of bag evaluation."""
    registration = Path(plan["output"]).parent / "six_gimbal_fixture_registration.json"
    registered_evidence = builder.register_gimbal_reevaluations(source_path, source_path, registration)
    registered = registered_evidence["created_utc"]
    source_plan = registered_evidence["source_plan"]
    slots = []
    for trial in plan["trials"]:
        if not trial["group"].startswith("stage3_"):
            continue
        spec = next(spec for spec in trial["evaluations"] if spec["kind"] == "gimbal")
        directory = Path(trial["directory"])
        report = v4.load(spec["report"])
        report["result"] = "PASS"  # Synthetic replacement, never real evidence.
        original = {"source_plan":source_path, "slot_record":v4.record_path(plan, trial),
                    "original_report":Path(spec["report"]), "recording_closure":directory / "recording_closure.json",
                    "bag_integrity":directory / "bag_integrity.json"}
        for name in ("recording_closure", "bag_integrity"):
            fixtures.write(original[name], {"scope":"ORCHESTRATION_FIXTURE_ONLY"})
        report["input_bindings"] = {name:{"path":str(path.resolve()), "sha256":v4.sha(path)} for name, path in original.items()}
        replacement = directory / v4.GIMBAL_REEVALUATION_FILENAME
        fixtures.write(replacement, report)
        command = v4.wrapper_command(Path(plan["frozen_root"]), Path(spec["script"]).name,
            directory / "rosbag", "--mode", trial["gimbal_mode"],
            *(["--selected-target"] if trial["group"] == "stage3_multi_active" else []),
            "--source-plan", source_path, "--slot-record", original["slot_record"],
            "--original-report", original["original_report"], "--output", replacement)
        log = directory / "gimbal_fixture_reevaluation.log"
        log.write_text("ORCHESTRATION_FIXTURE_ONLY: no bag evaluated\n", encoding="utf-8")
        slots.append({"slot_id":trial["id"], "record_file_sha256":v4.sha(original["slot_record"]),
            "evaluation_overrides":[{"kind":"gimbal", "original_report_sha256":v4.sha(original["original_report"]),
                "report":str(replacement), "report_sha256":v4.sha(replacement), "evaluation_root":plan["frozen_root"],
                "execution":{"command":command, "started_utc":registered, "finished_utc":v4.utc_now(),
                    "returncode":0, "error":None, "log":str(log), "log_sha256":v4.sha(log)}}]})
    path = Path(plan["output"]).parent / "six_gimbal_fixture_overrides.json"
    manifest = {"schema_version":1,"kind":"RELIABILITY_V4_SIX_STAGE3_GIMBAL_REEVALUATIONS",
        "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY", "registered_utc":registered,"created_utc":v4.utc_now(),
        "source_plan":source_plan,
        "prospective_registration":{"path":str(registration),"sha256":v4.sha(registration)},
        "evaluation_source_hashes":v4.offline_source_hashes(plan["source_hashes"]),
        "predetermined_gimbal_slots":sorted(item["slot_id"] for item in slots),"slots":slots}
    fixtures.write(path, manifest)
    return path, manifest


class UnsafeExtensions(extensions.ExtensionCommands):
    def __call__(self, command, log, root, timeout):
        result = super().__call__(command, log, root, timeout)
        if Path(command[2]).name == "evaluate_stage1_flight.py":
            path = Path(command[command.index("--output") + 1])
            report = v4.load(path)
            report["occlusions"][1]["checks"].pop("sustained_low_speed_after_hover")
            fixtures.write(path, report)
        return result


class OriginalGimbalFailures(fixtures.FakeCommands):
    def __call__(self, command, log, root, timeout):
        result = super().__call__(command, log, root, timeout)
        if Path(command[2]).name == "evaluate_stage3_gimbal.py":
            path = Path(command[command.index("--output") + 1])
            report = v4.load(path); report["result"] = "FAIL_OR_INCOMPLETE"
            fixtures.write(path, report); result["returncode"] = 2
        return result


class ProbeGateBuilderTests(unittest.TestCase):
    def test_unregistered_target_can_register_six_diagnostics_but_cannot_publish_acceptance_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, source = matrix(root)
            protocol = v4.load(root / v4.PROTOCOL_PATH)
            protocol["navigation_acceptance"]["status"] = "DRAFT"
            fixtures.write(root / v4.PROTOCOL_PATH, protocol)
            target = fixtures.plan(root, groups=list(v4.GROUPS), classes=list(v4.CLASSES), seeds=[7], suffix="ungated_diagnostics")
            target_path = Path(target["output"]) / "plan.json"
            registration_path = root / "results/diagnostics_registration.json"
            registered = builder.register_gimbal_reevaluations(target_path, source, registration_path)
            self.assertEqual(len(registered["planned_evaluations"]), 6)
            self.assertEqual(v4.load(root / v4.PROTOCOL_PATH)["navigation_acceptance"]["status"], "DRAFT")
            self.assertFalse(any(Path(row["report"]).exists() for row in registered["planned_evaluations"]))
            output = root / "results/ungated_acceptance_gate.json"
            with self.assertRaisesRegex(ValueError, "must be REGISTERED"):
                builder.run(target_path, [source], output)
            self.assertFalse(output.exists())

    def test_explicit_complete_six_gimbal_manifest_preserves_original_reports_and_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); plan, path = matrix(root, commands=OriginalGimbalFailures()); before = preserved_hashes(plan)
            manifest_path, manifest = gimbal_overrides(plan, path)
            output = root / "results/six_gimbal_gate.json"
            gate = builder.run(path, [path], output, overrides_manifest=manifest_path)
            self.assertEqual(len([item for item in gate["probe_slots"] if item.get("evaluation_overrides")]), 6)
            self.assertEqual(gate["evaluation_overrides_manifest"]["manifest"], manifest)
            self.assertEqual(gate["generation"]["source_terminal_status_counts"], {"PASS":6,"FAIL":6})
            self.assertEqual(preserved_hashes(plan), before)
            v4.validate_probe_gate(builder.verification_context(plan, output, gate, extension=False, registration_utc=None))
            with self.assertRaises(FileExistsError):
                builder.register_gimbal_reevaluations(path, path, root / "results/late_registration.json")
            self.assertFalse((root / "results/late_registration.json").exists())

    def test_gimbal_manifest_rejects_partial_selection_wrong_old_sha_bad_command_or_missing_log(self):
        for defect in ("partial", "old_sha", "command", "log", "chronology", "registration", "selected_target"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); plan, path = matrix(root)
                manifest_path, manifest = gimbal_overrides(plan, path)
                if defect == "partial":
                    manifest["slots"].pop()
                elif defect == "old_sha":
                    manifest["slots"][0]["record_file_sha256"] = "0" * 64
                elif defect == "registration":
                    manifest["prospective_registration"]["sha256"] = "0" * 64
                elif defect == "selected_target":
                    entry = next(item for item in manifest["slots"] if "stage3_multi_active" in item["slot_id"])
                    entry["evaluation_overrides"][0]["execution"]["command"].remove("--selected-target")
                else:
                    entry = manifest["slots"][0]["evaluation_overrides"][0]
                    if defect == "command":
                        entry["execution"]["command"][2] = "/wrong/evaluator.py"
                    elif defect == "log":
                        entry["execution"]["log_sha256"] = "0" * 64
                    else:
                        entry["execution"]["started_utc"] = "2000-01-01T00:00:00Z"
                fixtures.write(manifest_path, manifest)
                output = root / "results/rejected_gimbal_gate.json"
                with self.assertRaises(ValueError):
                    builder.run(path, [path], output, overrides_manifest=manifest_path)
                self.assertFalse(output.exists())

    def test_core_validates_real_temporary_artifact_then_publishes_without_rewriting_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); plan, path = matrix(root); before = preserved_hashes(plan)
            output = root / "results/generated_gate.json"
            with self.assertRaisesRegex(ValueError, "must not change the target frozen source"):
                builder.run(path, [path], root / "config/unsafe_gate.json")
            self.assertFalse((root / "config/unsafe_gate.json").exists())
            actual_validator = v4.validate_probe_gate
            calls = []
            def verified(context, **kwargs):
                artifact = Path(context["development_probe_gate"]["path"])
                self.assertTrue(artifact.is_file()); self.assertFalse(output.exists())
                self.assertNotEqual(artifact, output)
                calls.append(artifact)
                return actual_validator(context, **kwargs)
            with patch.object(v4, "validate_probe_gate", side_effect=verified):
                gate = builder.run(path, [path], output)
            self.assertEqual(len(calls), 1); self.assertFalse(calls[0].exists())
            self.assertEqual(v4.load(output), gate)
            self.assertEqual(len(gate["probe_slots"]), 12)
            self.assertEqual(gate["generation"]["source_terminal_status_counts"], {"PASS": 12})
            self.assertEqual(gate["evidence_scope"], "ORCHESTRATION_FIXTURE_ONLY")
            self.assertEqual(gate["generation"]["protocol_registration"], "NOT_PROTOCOL_REGISTRATION")
            self.assertEqual(preserved_hashes(plan), before)
            context = builder.verification_context(plan, output, gate, extension=False, registration_utc=None)
            actual_validator(context)
            with self.assertRaises(FileExistsError):
                builder.run(path, [path], output)

    def test_extension_retains_exact_original_algorithm_failures_and_never_registers_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); plan, path = matrix(root, extension=True, algorithm_failure=True)
            before = preserved_hashes(plan)
            protocol_path = root / v4.EXTENSION_PROTOCOL_PATH; protocol_sha = v4.sha(protocol_path)
            cutoff = v4.utc_now(); output = root / "results/extension_gate.json"
            gate = builder.run(path, [path], output, registration_utc=cutoff)
            self.assertEqual(len(gate["probe_slots"]), 16)
            self.assertEqual(len(gate["known_algorithm_failures"]), 16)
            expected = []
            records = v4.read_slots(plan)
            for trial in plan["trials"]:
                record = records[trial["id"]]
                flight = next(entry for entry in record["commands"] if entry["kind"] == "flight")
                failures = v4.extension_algorithm_failures(plan, trial, flight, record["evaluations"])
                expected.append({"plan_path": str(path), "slot_id": trial["id"], "failures": failures})
            self.assertEqual(gate["known_algorithm_failures"], expected)
            self.assertEqual(gate["generation"]["source_terminal_status_counts"], {"FAIL": 16})
            self.assertEqual(gate["generation"]["extension_verification_cutoff_utc"], cutoff)
            self.assertEqual(v4.sha(protocol_path), protocol_sha)
            self.assertEqual(preserved_hashes(plan), before)
            self.assertNotEqual(v4.load(protocol_path).get("status"), "REGISTERED")

    def test_pending_or_incomplete_matrix_cannot_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); plan, path = matrix(root, completed=False)
            output = root / "results/gate.json"
            with self.assertRaisesRegex(ValueError, "Incomplete immutable"):
                builder.run(path, [path], output)
            self.assertFalse(output.exists())
            run_fixture(plan)
            # A complete single-class source remains an incomplete gate,
            # even though every supplied trial independently passed.
            target = fixtures.plan(root, groups=["stage1_velocity"], classes=["person"], seeds=[7], suffix="subset")
            run_fixture(target)
            subset = Path(target["output"]) / "plan.json"
            with self.assertRaisesRegex(ValueError, "complete 2-class"):
                builder.run(path, [subset], output)
            self.assertFalse(output.exists())
            self.assertFalse(list(output.parent.glob(".gate.json.*.validation.json")))

    def test_source_drift_changed_snapshot_or_unregistered_gates_cannot_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, path = matrix(root); output = root / "results/gate.json"
            source = root / "config/safety.yaml"; source.write_text("prediction: 0.74\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Target frozen source"):
                builder.run(path, [path], output)
            target = fixtures.plan(root, seeds=[7], suffix="new_snapshot")
            with self.assertRaisesRegex(ValueError, "flight-critical source"):
                builder.run(Path(target["output"]) / "plan.json", [path], output)
            protocol = v4.load(root / v4.PROTOCOL_PATH)
            protocol["navigation_acceptance"]["status"] = "DRAFT"
            fixtures.write(root / v4.PROTOCOL_PATH, protocol)
            draft = fixtures.plan(root, seeds=[8], suffix="draft")
            with self.assertRaisesRegex(ValueError, "must be REGISTERED"):
                builder.run(Path(draft["output"]) / "plan.json", [path], output)
            self.assertFalse(output.exists())

    def test_extension_missing_long_loss_safety_or_invalid_cutoff_cannot_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, path = matrix(root, extension=True, commands=UnsafeExtensions())
            output = root / "results/gate.json"
            for cutoff in (None, "2026-01-01T00:00:00", "2000-01-01T00:00:00Z",
                           (v4.utc_timestamp(v4.utc_now()) + timedelta(days=1)).isoformat()):
                with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                    builder.run(path, [path], output, registration_utc=cutoff)
                self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError, "safety did not PASS"):
                builder.run(path, [path], output, registration_utc=v4.utc_now())
            self.assertFalse(output.exists())

    def test_original_failure_validator_rejection_duplicate_or_changed_report_never_publishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); plan, path = matrix(root); output = root / "results/gate.json"
            with self.assertRaisesRegex(ValueError, "Duplicate probe plan"):
                builder.run(path, [path, path], output)
            with patch.object(v4, "validate_probe_gate", side_effect=ValueError("independent rejection")):
                with self.assertRaisesRegex(ValueError, "independent rejection"):
                    builder.run(path, [path], output)
            self.assertFalse(output.exists())
            self.assertFalse(list(output.parent.glob(".gate.json.*.validation.json")))
            report = Path(plan["trials"][0]["evaluations"][0]["report"])
            report.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Terminal trial evidence changed"):
                builder.run(path, [path], output)
            self.assertFalse(output.exists())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, path = matrix(root, commands=fixtures.FakeCommands(native="FAIL"))
            output = root / "results/gate.json"
            with self.assertRaisesRegex(ValueError, "Independent core acceptance did not PASS"):
                builder.run(path, [path], output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
