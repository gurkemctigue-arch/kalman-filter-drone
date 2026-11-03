"""Synthetic immutable matrices only; no simulator or bag database reads."""
from datetime import timedelta
from copy import deepcopy
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


def navigation_pair(root):
    """One synthetic original core12+extension16, then a new offline revision."""
    extensions.extension_fixture(root, registered=True)
    for name in (builder.SCRIPT, builder.RUNNER):
        shutil.copy2(fixtures.ROOT / name, root / name)
    core = fixtures.plan(root, groups=list(v4.GROUPS), classes=list(v4.CLASSES), seeds=[4], suffix="navigation_core")
    extension = extensions.make(root, seeds=[4], output="results/navigation_extension", prefix="reliability_v4_navigation_extension")
    v4.persist_plan(extension)
    run_fixture(core)
    run_fixture(extension, extensions.ExtensionCommands())
    # Preserve a synthetic original endpoint-denominator failure as a failure.
    latency = next(trial for trial in extension["trials"] if trial["target_class"] == "person" and trial["extension_condition"] == "latency")
    report_path = Path(next(spec["report"] for spec in latency["evaluations"] if spec["kind"] == "navigation"))
    report = v4.load(report_path)
    report["whole_interval"]["transients"]["base_link"]["distance"]["scheduled_samples"] -= 1
    fixtures.write(report_path, report)
    record_path = v4.record_path(extension, latency)
    record = v4.load(record_path)
    record.update(status="INCOMPLETE_EVIDENCE", engineering_result="INCOMPLETE_EVIDENCE")
    record["artifact_hashes"][Path(report_path).name] = v4.sha(report_path)
    next(entry for entry in record["evaluations"] if entry["kind"] == "navigation")["report_sha256"] = v4.sha(report_path)
    record["record_sha256"] = v4.digest(record, ("record_sha256",))
    fixtures.write(record_path, record)
    (root / "scripts/evaluate_navigation_reference.py").write_text("# ORCHESTRATION_FIXTURE_ONLY: revised offline endpoint\n", encoding="utf-8")
    target_core = fixtures.plan(root, groups=list(v4.GROUPS), classes=list(v4.CLASSES), seeds=[7], suffix="navigation_target")
    target_extension = extensions.make(root, seeds=[7], output="results/navigation_extension_target", prefix="reliability_v4_navigation_extension_target")
    v4.persist_plan(target_extension)
    return core, extension, target_core, target_extension


def navigation_overrides(root, core, extension, target):
    """All commands/reports here are explicitly synthetic, with no bag reads."""
    paths = [Path(plan["output"]) / "plan.json" for plan in (core, extension)]
    registration_path = root / "results/all28_navigation_registration.json"
    registration = builder.register_navigation_reevaluations(Path(target["output"]) / "plan.json", paths, registration_path)
    slots = []
    for fixed in registration["planned_evaluations"]:
        previous = v4.load(fixed["plan_path"])
        trial = next(trial for trial in previous["trials"] if trial["id"] == fixed["slot_id"])
        original = next(spec for spec in trial["evaluations"] if spec["kind"] == "navigation")
        report = v4.load(original["report"])
        for transient in report["whole_interval"]["transients"]["base_link"].values():
            transient["scheduled_samples"] = report["whole_interval"]["scheduled_samples"]
        report["evaluation_source"] = fixtures.provenance(Path(target["frozen_root"]), "navigation", original["script"])
        identity = next((spec for spec in trial["evaluations"] if spec["kind"] == "physical_identity"), None)
        report["physical_identity_sha256"] = v4.sha(identity["report"]) if identity else None
        fixtures.write(Path(fixed["report"]), report)
        log = Path(fixed["report"]).with_suffix(".log")
        log.write_text("ORCHESTRATION_FIXTURE_ONLY: no evaluator or bag read\n", encoding="utf-8")
        slots.append({"plan_path":fixed["plan_path"], "slot_id":fixed["slot_id"], "record_file_sha256":fixed["record_file_sha256"],
            "evaluation_overrides":[{"kind":"navigation", "original_report_sha256":fixed["original_report_sha256"],
                "report":fixed["report"], "report_sha256":v4.sha(fixed["report"]), "evaluation_root":target["frozen_root"],
                "execution":{"command":fixed["command"], "started_utc":registration["created_utc"], "finished_utc":v4.utc_now(),
                    "returncode":0, "error":None, "log":str(log), "log_sha256":v4.sha(log), "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY"}}]})
    manifest = {"schema_version":1, "kind":"RELIABILITY_V4_ALL28_NAVIGATION_REEVALUATIONS", "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY",
        "registered_utc":registration["created_utc"], "created_utc":v4.utc_now(), "source_plans":registration["source_plans"],
        "evaluation_source_hashes":registration["evaluation_source_hashes"],
        "prospective_registration":{"path":str(registration_path), "sha256":v4.sha(registration_path)}, "slots":slots}
    path = root / "results/all28_navigation_manifest.json"
    fixtures.write(path, manifest)
    return path, manifest, registration


def sensor_input_fixture(root, original, source_path):
    """Explicitly inert orchestration attachment; no raw evidence is invented as real."""
    external = root.parent / (root.name + "_sensor_fixture")
    external.mkdir()
    cells = []
    for trial in original["trials"]:
        if trial.get("extension_condition") not in ("dropout", "combined"):
            continue
        cells.append({"slot_id":trial["id"], "target_class":trial["target_class"], "condition":trial["extension_condition"]})
        path = Path(next(spec["report"] for spec in trial["evaluations"] if spec["kind"] == "surface_flight"))
        report = v4.load(path)
        short = next(row for row in report["occlusions"] if row["kind"] == "short")
        short["checks"]["detector_interruption_observed"] = None
        short.update(diagnostic_frames_inside=0, candidate_free_frames_inside=0, valid_depth_frames_inside=0)
        failed = trial["target_class"] == "person" and trial["extension_condition"] == "dropout"
        if failed:
            short["checks"]["prediction_observed"] = False
        report["acceptance"]["result"] = "FAIL" if failed else "INCOMPLETE_EVIDENCE"
        fixtures.write(path, report)
        saved_path = v4.record_path(original, trial)
        saved = v4.load(saved_path)
        saved.update(status=report["acceptance"]["result"], engineering_result=report["acceptance"]["result"],
                     engineering_evidence={"ORCHESTRATION_FIXTURE_ONLY":"preserve original null and false"})
        saved["artifact_hashes"][path.name] = v4.sha(path)
        entry = next(item for item in saved["evaluations"] if item["kind"] == "surface_flight")
        entry.update(result=report["acceptance"]["result"], reported_verdict=report["acceptance"]["result"], report_sha256=v4.sha(path))
        saved["record_sha256"] = v4.digest(saved, ("record_sha256",))
        fixtures.write(saved_path, saved)
    module_path = external / "evidence.py"
    module_path.write_text('''# ORCHESTRATION_FIXTURE_ONLY: no bag, raw image, inference or real corroboration.
import hashlib, json
from pathlib import Path
REVISION = "sensor_input_interruption_v1"
SCOPE = "DEVELOPMENT_EVIDENCE_ONLY_NOT_FORMAL_ADMISSION"
def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def binding(path):
    return {"path":str(Path(path).resolve()), "sha256":sha(path)}
def evaluate_development_manifest(path, contract):
    manifest, plan = load(path), load(contract["source_plan"]["path"])
    rows = []
    for item in manifest["slots"]:
        trial = next(row for row in plan["trials"] if row["id"] == item["slot_id"])
        terminal_path = Path(plan["output"]) / "slots" / (trial["id"] + ".json")
        terminal = load(terminal_path)
        surface_path = next(row["report"] for row in trial["evaluations"] if row["kind"] == "surface_flight")
        surface = load(surface_path)
        rows.append({"slot_id":item["slot_id"], "status":item.get("synthetic_status", "UPSTREAM_INPUT_INTERRUPTION_CORROBORATED"),
            "errors":[], "original":{"terminal_status":terminal["status"], "engineering_evidence":terminal["engineering_evidence"],
                "acceptance":surface["acceptance"], "occlusions":surface["occlusions"]},
            "input_bindings":{"plan":binding(contract["source_plan"]["path"]), "terminal":binding(terminal_path),
                "flight_evaluation.json":binding(surface_path)}})
    return {"schema_version":1,"revision":REVISION,"scope":SCOPE,"status":"UPSTREAM_INPUT_INTERRUPTION_CORROBORATED",
        "errors":[], "missing_slot_ids":sorted({row["slot_id"] for row in contract["dev_slots"]}-{row["slot_id"] for row in rows}),
        "contract_sha256":hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest(),
        "module_sha256":sha(__file__), "development_manifest":binding(path), "per_slot":rows,
        "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY"}
''', encoding="utf-8")
    source_binding = {"path":str(source_path.resolve()), "sha256":v4.sha(source_path)}
    contract = {"schema_version":1, "revision":"sensor_input_interruption_v1", "scope":v4.SENSOR_INPUT_EVIDENCE_SCOPE,
        "source_plan":source_binding, "dev_slots":cells, "scope_note":"ORCHESTRATION_FIXTURE_ONLY"}
    contract_path = external / "contract.json"
    fixtures.write(contract_path, contract)
    declaration = {"schema_version":1, "revision":"sensor_input_interruption_v1", "scope":v4.SENSOR_INPUT_EVIDENCE_SCOPE,
        "evidence_basis":v4.SENSOR_INPUT_EVIDENCE_BASIS, "module":{"path":str(module_path.resolve()), "sha256":v4.sha(module_path)},
        "contract":{"path":str(contract_path.resolve()), "sha256":v4.sha(contract_path), "canonical_sha256":v4.digest(contract)},
        "source_plan":source_binding, "dev_slots":cells}
    manifest_path = external / "development_manifest.json"
    fixtures.write(manifest_path, {"schema_version":1, "contract_sha256":v4.digest(contract), "source_plan":source_binding,
        "slots":[{"slot_id":row["slot_id"]} for row in cells], "evidence_scope":"ORCHESTRATION_FIXTURE_ONLY"})
    protocol = v4.load(root / v4.PROTOCOL_PATH)
    protocol[v4.SENSOR_INPUT_EVIDENCE_FIELD] = declaration
    fixtures.write(root / v4.PROTOCOL_PATH, protocol)
    return manifest_path, declaration


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


class NavigationReevaluationTests(unittest.TestCase):
    def test_all28_prospective_manifest_serves_both_gates_and_preserves_original_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); core, extension, target, target_extension = navigation_pair(root)
            before = {**preserved_hashes(core), **preserved_hashes(extension)}
            path, manifest, registration = navigation_overrides(root, core, extension, target)
            self.assertEqual(len(registration["planned_evaluations"]), 28)
            self.assertEqual({item["mode"] for item in registration["source_plans"]}, {"PROBE", "EXTENSION_PROBE"})
            for original, final, size in ((core, target, 12), (extension, target_extension, 16)):
                output = root / f"results/navigation_gate_{size}.json"
                cutoff = v4.utc_now() if size == 16 else None
                gate = builder.run(Path(final["output"]) / "plan.json", [Path(original["output"]) / "plan.json"], output,
                    registration_utc=cutoff, navigation_manifest=path)
                self.assertEqual(len(gate["probe_slots"]), size)
                self.assertTrue(all(len(item["evaluation_overrides"]) == 1 for item in gate["probe_slots"]))
                self.assertEqual(gate["navigation_reevaluation_manifest"]["manifest"], manifest)
                if size == 16:
                    self.assertEqual(gate["generation"]["source_terminal_status_counts"], {"PASS":15, "INCOMPLETE_EVIDENCE":1})
                v4.validate_probe_gate(builder.verification_context(final, output, gate, extension=size == 16, registration_utc=cutoff), extensions=size == 16)
            self.assertEqual({**preserved_hashes(core), **preserved_hashes(extension)}, before)
            with self.assertRaises(FileExistsError):
                builder.register_navigation_reevaluations(Path(target["output"]) / "plan.json",
                    [Path(plan["output"]) / "plan.json" for plan in (core, extension)], root / "results/late_navigation.json")

    def test_navigation_registration_requires_both_complete_plans_and_new_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); core, extension, target, _ = navigation_pair(root)
            target_path = Path(target["output"]) / "plan.json"
            paths = [Path(plan["output"]) / "plan.json" for plan in (core, extension)]
            for wrong in ([paths[0]], [paths[0], paths[0]], [paths[1], paths[1]]):
                with self.subTest(paths=wrong), self.assertRaises(ValueError):
                    builder.register_navigation_reevaluations(target_path, wrong, root / "results/rejected_registration.json")
            for basename in ("../outside.json", "navigation_reference_evaluation.json", "not_json.txt"):
                with self.subTest(basename=basename), self.assertRaises(ValueError):
                    builder.register_navigation_reevaluations(target_path, paths, root / "results/rejected_registration.json", basename=basename)
            output = Path(core["trials"][0]["directory"]) / v4.NAVIGATION_REEVALUATION_FILENAME
            for collision in (output, *(output.with_suffix("." + name + ".jsonl") for name in ("frames", "raw_frames", "message_frames"))):
                with self.subTest(collision=collision), self.assertRaisesRegex(ValueError, "future report/sidecar"):
                    builder.register_navigation_reevaluations(target_path, paths, collision)
                self.assertFalse(collision.exists())
            output.with_suffix(".frames.jsonl").write_text("fixture partial output\n", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                builder.register_navigation_reevaluations(target_path, paths, root / "results/rejected_registration.json")
            self.assertFalse((root / "results/rejected_registration.json").exists())

    def test_all28_manifest_rejects_selection_stale_bindings_and_nonexecutions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); core, extension, target, _ = navigation_pair(root)
            path, original, _ = navigation_overrides(root, core, extension, target)
            probe = [Path(core["output"]) / "plan.json"]
            for defect in ("partial", "duplicate", "unknown", "record", "old_report", "new_report", "command", "exit", "bool_exit", "log", "chronology", "registration", "source"):
                with self.subTest(defect=defect):
                    manifest = deepcopy(original)
                    entry = manifest["slots"][0]["evaluation_overrides"][0]
                    if defect == "partial": manifest["slots"].pop()
                    elif defect == "duplicate": manifest["slots"][-1] = deepcopy(manifest["slots"][0])
                    elif defect == "unknown": manifest["slots"][0]["slot_id"] = "unknown"
                    elif defect == "record": manifest["slots"][0]["record_file_sha256"] = "0" * 64
                    elif defect == "old_report": entry["original_report_sha256"] = "0" * 64
                    elif defect == "new_report": entry["report_sha256"] = "0" * 64
                    elif defect == "command": entry["execution"]["command"][2] = "/wrong/navigation.py"
                    elif defect == "exit": entry["execution"]["returncode"] = 2
                    elif defect == "bool_exit": entry["execution"]["returncode"] = False
                    elif defect == "log": entry["execution"]["log_sha256"] = "0" * 64
                    elif defect == "chronology": entry["execution"]["started_utc"] = "2000-01-01T00:00:00Z"
                    elif defect == "registration": manifest["prospective_registration"]["sha256"] = "0" * 64
                    elif defect == "source": manifest["evaluation_source_hashes"] = {}
                    fixtures.write(path, manifest)
                    with self.assertRaises(ValueError):
                        builder.read_navigation_reevaluation_manifest(path, target, probe, extension=False)

    def test_all28_manifest_checks_other_gate_subset_and_actual_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); core, extension, target, _ = navigation_pair(root)
            path, original, _ = navigation_overrides(root, core, extension, target)
            # A core gate must still reject bad provenance or structure in an extension report.
            chosen = next(item for item in original["slots"] if "extension" in item["slot_id"])
            entry = chosen["evaluation_overrides"][0]
            report_path = Path(entry["report"]); report = v4.load(report_path)
            for defect in ("script", "helper", "physical", "denominator", "incomplete"):
                altered = deepcopy(report)
                if defect == "script": altered["evaluation_source"]["script_sha256"] = "0" * 64
                elif defect == "helper": altered["evaluation_source"]["dependencies"] = {}
                elif defect == "physical": altered["physical_identity_sha256"] = "0" * 64
                elif defect == "denominator": altered["whole_interval"]["scheduled_samples"] -= 1
                else: altered["incomplete_reasons"] = ["ORCHESTRATION_FIXTURE_ONLY missing evidence"]
                fixtures.write(report_path, altered)
                manifest = deepcopy(original)
                changed = next(item for item in manifest["slots"] if item["slot_id"] == chosen["slot_id"])
                changed["evaluation_overrides"][0]["report_sha256"] = v4.sha(report_path)
                fixtures.write(path, manifest)
                reason = "numeric structure is incomplete" if defect in ("denominator", "incomplete") else "provenance differs"
                with self.subTest(defect=defect), self.assertRaisesRegex(ValueError, reason):
                    builder.read_navigation_reevaluation_manifest(path, target, [Path(core["output"]) / "plan.json"], extension=False)
            # Complete genuine FAIL remains available for its own gate; never relabel it as missing evidence.
            altered = deepcopy(report)
            altered["whole_interval"]["metrics"]["base_link_distance_error_m"]["rmse"] = target["protocol"]["navigation_acceptance"]["maximum_base_link_distance_rmse_m"] + 1.
            self.assertEqual(v4.navigation_verdict(altered, target["protocol"]["navigation_acceptance"])[0], "FAIL")
            fixtures.write(report_path, altered)
            manifest = deepcopy(original)
            next(item for item in manifest["slots"] if item["slot_id"] == chosen["slot_id"])["evaluation_overrides"][0]["report_sha256"] = v4.sha(report_path)
            fixtures.write(path, manifest)
            overrides, _ = builder.read_navigation_reevaluation_manifest(path, target, [Path(core["output"]) / "plan.json"], extension=False)
            self.assertEqual(len(overrides), 12)

    def test_no_manifest_still_rejects_changed_navigation_and_manifest_types_are_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); core, extension, target, _ = navigation_pair(root)
            output = root / "results/default_rejected.json"
            with self.assertRaisesRegex(ValueError, "Changed offline evaluator"):
                builder.run(Path(target["output"]) / "plan.json", [Path(core["output"]) / "plan.json"], output)
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError, "cannot be combined"):
                builder.assemble(target, [Path(core["output"]) / "plan.json"], extension=False, registration_utc=None,
                    overrides_manifest=root / "gimbal.json", navigation_manifest=root / "navigation.json")


class SensorInputEvidenceTests(unittest.TestCase):
    def fixture(self, tmp):
        root = Path(tmp) / "snapshot"
        root.mkdir()
        original, source = matrix(root, extension=True)
        manifest, declaration = sensor_input_fixture(root, original, source)
        target = extensions.make(root, seeds=[7], output="results/sensor_target", prefix="reliability_v4_sensor_target")
        v4.persist_plan(target)
        return root, original, source, target, manifest, declaration

    def test_complete_attachment_preserves_failures_nulls_and_original_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, original, source, target, manifest, _ = self.fixture(tmp)
            before = preserved_hashes(original)
            output = root.parent / "sensor_gate.json"
            cutoff = v4.utc_now()
            with self.assertRaisesRegex(ValueError, "complete fixed four-slot"):
                builder.run(Path(target["output"]) / "plan.json", [source], output, registration_utc=cutoff)
            gate = builder.run(Path(target["output"]) / "plan.json", [source], output,
                registration_utc=cutoff, sensor_input_manifest=manifest)
            self.assertEqual(gate["generation"]["source_terminal_status_counts"], {"PASS":12, "FAIL":1, "INCOMPLETE_EVIDENCE":3})
            self.assertEqual(len(gate["unobserved_surface_checks"]), 4)
            self.assertTrue(all(row["original_value"] is None and row["outcome"] == "UNOBSERVED" for row in gate["unobserved_surface_checks"]))
            failures = [failure for row in gate["known_algorithm_failures"] for failure in row["failures"]]
            self.assertEqual(failures, ["surface:short:prediction_observed=FAIL"])
            self.assertEqual(preserved_hashes(original), before)
            v4.validate_probe_gate(builder.verification_context(target, output, gate, extension=True, registration_utc=cutoff), extensions=True)
            altered = deepcopy(gate)
            altered["unobserved_surface_checks"][0]["original_value"] = False
            tampered = root.parent / "tampered_sensor_gate.json"
            fixtures.write(tampered, altered)
            with self.assertRaisesRegex(ValueError, "UNOBSERVED appendix differs"):
                v4.validate_probe_gate(builder.verification_context(target, tampered, altered, extension=True, registration_utc=cutoff), extensions=True)

    def test_manifest_fixed_four_and_bound_sources_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, original, source, target, path, declaration = self.fixture(tmp)
            original_manifest = v4.load(path)
            for defect in ("partial", "duplicate", "unknown", "incomplete"):
                manifest = deepcopy(original_manifest)
                if defect == "partial": manifest["slots"].pop()
                elif defect == "duplicate": manifest["slots"][-1] = deepcopy(manifest["slots"][0])
                elif defect == "unknown": manifest["slots"][0]["slot_id"] = original["trials"][0]["id"]
                else: manifest["slots"][0]["synthetic_status"] = "INCOMPLETE"
                fixtures.write(path, manifest)
                with self.subTest(defect=defect), self.assertRaises(ValueError):
                    v4.read_sensor_input_evidence_manifest(target, path, [source])
            fixtures.write(path, original_manifest)
            for field in ("module", "contract", "source_plan"):
                altered = deepcopy(target)
                altered["protocol"][v4.SENSOR_INPUT_EVIDENCE_FIELD][field]["sha256"] = "0" * 64
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "file/SHA binding differs"):
                    v4.read_sensor_input_evidence_manifest(altered, path, [source])
            altered = deepcopy(target)
            altered["protocol"][v4.SENSOR_INPUT_EVIDENCE_FIELD]["contract"]["canonical_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "canonical/source/fixed-cell"):
                v4.read_sensor_input_evidence_manifest(altered, path, [source])
            altered = deepcopy(target)
            altered["protocol"][v4.SENSOR_INPUT_EVIDENCE_FIELD]["source_plan"]["path"] = str(source.parent / ".." / source.parent.name / source.name)
            with self.assertRaisesRegex(ValueError, "canonical path"):
                v4.read_sensor_input_evidence_manifest(altered, path, [source])
            altered = deepcopy(target)
            altered["protocol"].pop(v4.SENSOR_INPUT_EVIDENCE_FIELD)
            with self.assertRaisesRegex(ValueError, "explicit development"):
                v4.read_sensor_input_evidence_manifest(altered, path, [source])
            with self.assertRaisesRegex(ValueError, "limited to the original extension"):
                builder.assemble(target, [source], extension=False, registration_utc=None, sensor_input_manifest=path)
            # A changed module is rejected before any of its code can execute.
            module_path = Path(declaration["module"]["path"])
            module_path.write_text("raise RuntimeError('UNBOUND MODULE MUST NOT EXECUTE')\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "module file/SHA binding differs"):
                v4.read_sensor_input_evidence_manifest(target, path, [source])

    def test_stimulus_attachment_keeps_all_long_safety_and_navigation_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, original, source, target, manifest, _ = self.fixture(tmp)
            mapping, _ = v4.read_sensor_input_evidence_manifest(target, manifest, [source])
            trial = next(row for row in original["trials"] if (str(source.resolve()), row["id"]) in mapping)
            record = v4.load(v4.record_path(original, trial))
            entries = deepcopy(record["evaluations"])
            flight = next(row for row in record["commands"] if row["kind"] == "flight")
            proof = mapping[str(source.resolve()), trial["id"]]
            spec = next(row for row in trial["evaluations"] if row["kind"] == "surface_flight")
            path = Path(spec["report"])
            surface = v4.load(path)
            keys = ("recorded_close_event", "shutter_close_service_succeeded", "shutter_open_service_succeeded",
                "shutter_close_ack_before_open_request", "lost_observed_for_long_occlusion", "hover_observed_for_long_occlusion",
                "sustained_low_speed_after_hover", "no_automatic_recovery_after_long_loss", "no_tracking_control_before_reselection_after_long_loss")
            for key in keys:
                for value in (False, None):
                    altered = deepcopy(surface)
                    altered["occlusions"][1]["checks"][key] = value
                    fixtures.write(path, altered)
                    changed = deepcopy(entries)
                    next(row for row in changed if row["kind"] == "surface_flight")["report_sha256"] = v4.sha(path)
                    evidence = deepcopy(proof)
                    evidence["original"]["occlusions"] = altered["occlusions"]
                    with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "original shutter/loss/hover/reselection safety"):
                        v4.extension_algorithm_failures(target, trial, flight, changed, sensor_input_evidence=evidence)
            for key in ("prediction_observed", "no_loss_during_short_occlusion", "identity_preserved_on_observed_recovery"):
                altered = deepcopy(surface)
                altered["occlusions"][0]["checks"][key] = None
                fixtures.write(path, altered)
                changed = deepcopy(entries)
                next(row for row in changed if row["kind"] == "surface_flight")["report_sha256"] = v4.sha(path)
                evidence = deepcopy(proof)
                evidence["original"]["occlusions"] = altered["occlusions"]
                with self.subTest(other_null=key), self.assertRaises(ValueError):
                    v4.extension_algorithm_failures(target, trial, flight, changed, sensor_input_evidence=evidence)
            fixtures.write(path, surface)
            nav_path = Path(next(row["report"] for row in trial["evaluations"] if row["kind"] == "navigation"))
            nav = v4.load(nav_path)
            nav["whole_interval"]["metrics"]["base_link_distance_error_m"]["rmse"] = 100.
            fixtures.write(nav_path, nav)
            next(row for row in entries if row["kind"] == "navigation")["report_sha256"] = v4.sha(nav_path)
            failures = v4.extension_algorithm_failures(target, trial, flight, entries, sensor_input_evidence=proof)
            self.assertIn("navigation:REGISTERED_PERFORMANCE_GATES_FAILED", failures)
            self.assertIn("surface:short:prediction_observed=FAIL", failures)
            nav["whole_interval"]["scheduled_samples"] -= 1
            fixtures.write(nav_path, nav)
            next(row for row in entries if row["kind"] == "navigation")["report_sha256"] = v4.sha(nav_path)
            with self.assertRaisesRegex(ValueError, "not independently evaluable"):
                v4.extension_algorithm_failures(target, trial, flight, entries, sensor_input_evidence=proof)

    def test_sensor_attachment_can_accompany_the_same_full28_navigation_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "snapshot"
            root.mkdir()
            core, extension, _, _ = navigation_pair(root)
            extension_path = Path(extension["output"]) / "plan.json"
            sensor_manifest, _ = sensor_input_fixture(root, extension, extension_path)
            target_core = fixtures.plan(root, groups=list(v4.GROUPS), classes=list(v4.CLASSES), seeds=[8], suffix="sensor_navigation_target")
            target_extension = extensions.make(root, seeds=[8], output="results/sensor_navigation_target_extension", prefix="reliability_v4_sensor_nav_target")
            v4.persist_plan(target_extension)
            nav_manifest, _, _ = navigation_overrides(root, core, extension, target_core)
            gate = builder.run(Path(target_extension["output"]) / "plan.json", [extension_path], root.parent / "combined_gate.json",
                registration_utc=v4.utc_now(), navigation_manifest=nav_manifest, sensor_input_manifest=sensor_manifest)
            self.assertEqual(len(gate["probe_slots"]), 16)
            self.assertEqual(len(gate["unobserved_surface_checks"]), 4)
            self.assertIn("navigation_reevaluation_manifest", gate)
            self.assertIn("sensor_input_interruption_evidence", gate)

    def test_bound_real_external_module_consumes_its_small_synthetic_four_slot_fixture(self):
        # Integrate the actual independent module with its own generated tiny
        # PNG/JSON fixtures. This does not validate any real image or flight.
        module_path = fixtures.ROOT / "tools/offline_evaluation/sensor_input_interruption_v1/evidence.py"
        fixture_path = module_path.with_name("test_evidence.py")
        spec = importlib.util.spec_from_file_location("sensor_input_module_fixture", fixture_path)
        helpers = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helpers)
        synthetic = helpers.EvidenceTests("test_valid_slot_preserves_unknown_and_exact_drop_ledger")
        synthetic.setUp()
        self.addCleanup(synthetic.doCleanups)
        contract_path = synthetic.root / "bound_contract.json"
        fixtures.write(contract_path, synthetic.contract)
        declaration = {"schema_version":1, "revision":"sensor_input_interruption_v1", "scope":v4.SENSOR_INPUT_EVIDENCE_SCOPE,
            "evidence_basis":v4.SENSOR_INPUT_EVIDENCE_BASIS, "module":{"path":str(module_path.resolve()), "sha256":v4.sha(module_path)},
            "contract":{"path":str(contract_path), "sha256":v4.sha(contract_path), "canonical_sha256":v4.digest(synthetic.contract)},
            "source_plan":synthetic.contract["source_plan"], "dev_slots":synthetic.contract["dev_slots"]}
        target = {"frozen_root":str(synthetic.root / "future_source"), "protocol":{v4.SENSOR_INPUT_EVIDENCE_FIELD:declaration}}
        manifest = synthetic.matrix_manifest()
        mapping, binding = v4.read_sensor_input_evidence_manifest(target, manifest, [synthetic.plan_path])
        self.assertEqual(len(mapping), 4)
        self.assertEqual(binding["evidence"]["status"], "UPSTREAM_INPUT_INTERRUPTION_CORROBORATED")
        self.assertEqual(binding["sha256"], v4.sha(manifest))
        self.assertEqual(len(v4.sensor_input_unobserved_checks(mapping)), 4)
        def observed_failure(surface):
            short = surface["occlusions"][0]
            short["checks"]["detector_interruption_observed"] = False
            short["diagnostic_frames_inside"] = 3
            short["result"] = surface["acceptance"]["result"] = "FAIL"
        synthetic.edit_surface(observed_failure, terminal_status="FAIL")
        manifest = synthetic.matrix_manifest()
        mapping, binding = v4.read_sensor_input_evidence_manifest(target, manifest, [synthetic.plan_path])
        observed = mapping[str(synthetic.plan_path), "person_dropout"]
        self.assertEqual(observed["status"], "NOT_APPLICABLE")
        self.assertFalse(observed["original"]["occlusions"][0]["checks"]["detector_interruption_observed"])
        self.assertEqual(observed["known_algorithm_failures"], ["surface:short:detector_interruption_observed=FAIL"])
        self.assertEqual(len(v4.sensor_input_unobserved_checks(mapping)), 3)
        synthetic.edit_surface(lambda surface:surface["occlusions"][0].update(diagnostic_frames_inside=0))
        with self.assertRaisesRegex(ValueError, "all four independently complete"):
            v4.read_sensor_input_evidence_manifest(target, synthetic.matrix_manifest(), [synthetic.plan_path])


if __name__ == "__main__":
    unittest.main()
