"""Inert all28 fixtures for the explicit saved snapshot-audit size adapter.

No native validator, model inference or recorded-payload decoder is executed.
Only production absolute tool locations are relocated into a temporary tree;
the four reviewed tool pins and original native producer SHA stay unchanged.
"""
from contextlib import contextmanager, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tests import test_measure_reliability_v4_storage as base
from tests.test_reliability_v4_probe_gate import builder
from tools import reliability_v4_snapshot_audit as original
from tools import reliability_v4_storage_snapshot_audit as support

measurement, guard, v4 = base.measurement, base.guard, base.v4
ROOT = base.fixtures.ROOT
FREEZE = "2026-10-18T00:00:00+00:00"
PLAN = "2026-10-19T00:00:00+00:00"
NATIVE_START = "2026-10-19T00:00:10+00:00"
CONTRACT = "2026-10-19T00:00:20+00:00"
NATIVE_END = "2026-10-19T00:00:30+00:00"
REGISTRY = "2026-10-19T00:00:40+00:00"
SAFETY_END = "2026-10-19T00:10:00+00:00"
EXTRA = "ros2_ws/src/uav_tracking_nodes/build/lib/uav_tracking/core/__init__.py"


def write(path, value):
    base.write(path, value)
    return guard.file_binding(path)


def bytes_binding(path):
    return {**guard.file_binding(path), "bytes": path.stat().st_size}


def fixture(folder):
    actual = base.extensions.extension_fixture
    def with_original_scanner(root):
        actual(root)
        for relative, raw in {
            "config/dds_runtime_humble22.json": b"{}",
            "uav_tracking/core/__init__.py": b"# canonical original core\n",
            "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/__init__.py": b"# canonical nodes\n",
            EXTRA: b"# retained differing historical build copy\n",
            **{name: b"# inert original frozen tool, never imported\n" for name in original.BASE_NAMES.values()},
        }.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    with patch.object(base.extensions, "extension_fixture", side_effect=with_original_scanner):
        f = base.fixture(folder)
    for label, plan in f.plans.items():
        plan["created_utc"] = PLAN
        plan["plan_sha256"] = v4.digest(plan, ("plan_sha256",))
        write(f.paths[label], plan)
    scanned = {path.relative_to(f.root).as_posix(): guard.sha(path)
               for directory in ("scripts", "uav_tracking", "ros2_ws/src")
               for path in (f.root / directory).rglob("*")
               if path.is_file() and path.suffix in {".py", ".sh", ".msg"}}
    core = f.plans["core"]
    def expected(model):
        return {**scanned, model: core["source_hashes"][model],
                "config/dds_runtime_humble22.json": core["source_hashes"]["config/dds_runtime_humble22.json"]}
    for sample in f.samples:
        sample.record["plan_sha256"] = sample.plan["plan_sha256"]
        base.change_report(sample, "configuration/source_sha256.json", expected(sample.trial["model"]))
    names = set(core["source_hashes"]) | set(scanned) | set(original.BASE_NAMES.values())
    entries = {name: {"kind": "file", "bytes": (f.root / name).stat().st_size, "sha256": guard.sha(f.root / name)}
               for name in names}
    source = str(f.root.parent / "original_before_freeze")
    directory = f.results / "freeze_validation/source_integrity"
    before = write(directory / "source_before.json", {"source": source, "entries": entries})
    after = write(directory / "source_after.json", {"source": source, "entries": entries})
    frozen = write(directory / "frozen_actual.json", {"frozen": str(f.root), "entries": entries})
    report = write(directory / "source_frozen_integrity.json", {
        "status": "PASS", "scope": "RSYNC_FILTERED_SOURCE_PRE_POST_AND_COMPLETE_FROZEN_COPY_BYTES",
        "created_utc": FREEZE, "source": source, "frozen": str(f.root), "errors": [], "build_returncode": 0,
        "copy_identical": True, "source_unchanged": True,
        "source_pre_post": {"added": [], "changed": [], "missing": []},
        "frozen_copy": {"added": [], "changed": [], "missing": []}, "before": before,
        "maps": {"source_after.json": after, "frozen_actual.json": frozen},
        **{name: len(entries) for name in ("actual_frozen_entries", "actual_source_entries", "expected_entries")}})
    modules = {"uav_tracking.core": str(f.root / "uav_tracking/core/__init__.py"),
               "uav_tracking_nodes": str(f.root / "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/__init__.py")}
    for name, filename in (("uav_tracking_interfaces.msg", "__init__.py"),
            ("uav_tracking_interfaces.msg._target_observation_array", "_target_observation_array.py"),
            ("uav_tracking_interfaces.msg._target_state", "_target_state.py")):
        path = f.root / "ros2_ws/install/lib/python3.10/site-packages/uav_tracking_interfaces/msg" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# inert generated message; never imported\n")
        modules[name] = str(path)
    imports = write(f.results / "freeze_validation/import_isolation.json", {
        "root": str(f.root), "isolated": True, "module_files": modules,
        "ros_package_prefixes": {name: str(f.root / "ros2_ws/install") for name in
            ("uav_tracking_nodes", "uav_tracking_interfaces", "uav_tracking_bringup", "uav_tracking_px4_adapter")}})
    audit_root = Path(folder).resolve() / "separate_audit_tools"
    (audit_root / "tools").mkdir(parents=True)
    for name, digest in support.TOOL_PINS.values():
        shutil.copyfile(ROOT / "tools" / name, audit_root / "tools" / name)
        assert guard.sha(audit_root / "tools" / name) == digest
    native_script = Path(folder).resolve() / "native_original/audit_snapshot_contract_integration.py"
    native_script.parent.mkdir()
    shutil.copyfile(ROOT / "tools/diagnostics/snapshot_audit54_integration_prepare01/audit_snapshot_contract_integration.py", native_script)
    assert guard.sha(native_script) == support.NATIVE_SCRIPT_SHA
    core_pin = guard.file_binding(f.paths["core"])
    contract = {"schema_version": 1, "kind": original.KIND, "created_utc": CONTRACT, "rule": original.RULE,
        "frozen_root": str(f.root), "audit_tool_root": str(audit_root),
        "core_plan": {**core_pin, "plan_sha256": core["plan_sha256"]},
        "freeze_report": report, "source_before": before, "source_after": after, "frozen_map": frozen,
        "import_isolation": imports,
        "audit_tools": {key: guard.file_binding(audit_root / "tools" / name) for key, (name, _) in support.TOOL_PINS.items()},
        "base_tools": {key: guard.file_binding(f.root / name) for key, name in original.BASE_NAMES.items()},
        "evidence_limitations": original.LIMITATION}
    contract_pin = write(f.results / "snapshot_contract.json", contract)
    extra = {EXTRA: scanned[EXTRA]}
    def audit_evidence(model):
        registered = {name: value for name, value in expected(model).items() if name != EXTRA}
        return {"result": "PASS", "mode": original.KIND, "contract": contract_pin,
                "registered_count": len(registered), "original_extra_count": len(extra), "original_extra_sources": extra,
                "historical_copy_comparisons": original.historical_copy_comparisons(extra, core["source_hashes"]),
                "evidence_limitations": original.LIMITATION}
    snapshots = []
    for i, trial in enumerate(core["trials"][:3]):
        row = {"id": trial["id"], "original": bytes_binding(Path(trial["directory"]) / "configuration/source_sha256.json"),
               "entries": len(expected(trial["model"])), "helper_validate_snapshot_called": i == 0}
        if i == 0:
            row.update(validation_basis="ACTUAL_UNMODIFIED_HELPER_VALIDATE_SNAPSHOT_CALL",
                       explicit_contract_validation=audit_evidence(trial["model"]))
        snapshots.append(row)
    freeze = {relative: bytes_binding(Path(contract[key]["path"])) for key, relative in {
        "freeze_report": "source_integrity/source_frozen_integrity.json", "source_before": "source_integrity/source_before.json",
        "source_after": "source_integrity/source_after.json", "frozen_map": "source_integrity/frozen_actual.json",
        "import_isolation": "import_isolation.json"}.items()}
    bundle = {"files": {"tools/" + name: bytes_binding(audit_root / "tools" / name) for name, _ in support.TOOL_PINS.values()}}
    native = {"schema_version": 1, "scope": "ACTUAL_FIXED_TOOL_NATIVE_CONTRACT_AND_SNAPSHOT_AUDIT_ONLY",
        "result": support.NATIVE_RESULT, "exit_code": 0, "contract_creation_attempted": True,
        "self": bytes_binding(native_script), "plan": bytes_binding(f.paths["core"]), "plan_after": bytes_binding(f.paths["core"]),
        "contract": contract_pin, "contract_metadata": contract, "started_utc": NATIVE_START, "finished_utc": NATIVE_END,
        "mandatory_helper_hash_traversals_skipped": False, "helper_original_source_and_model_hashing_allowed_and_preserved": True,
        "bundle_before": bundle, "bundle_after": deepcopy(bundle), "freeze_metadata_before": freeze,
        "freeze_metadata_after": deepcopy(freeze), "snapshots": snapshots,
        "expected_registered_snapshot_entries": len(expected(core["trials"][0]["model"])) - len(extra),
        **{key: False for key in ("safety_registration_created", "formal_admission_or_plan_created", "formal_execution_authorized",
            "formal_dual_root_integration_validated", "historical_flight_imports_proved", "runtime_root_edited",
            "original_snapshots_edited", "bag_sidecar_or_telemetry_read_by_this_script")}}
    native_pin = write(f.results / "native_receipt.json", native)
    safety_dir = f.results / "safety_audit"
    trials = [{"id": cls + "_" + case, "target_class": cls, "case": case,
               "directory": str(f.results / "safety_trials" / (cls + "_" + case))}
              for cls in ("person", "car") for case in ("auto_unique_multi", "locked_ambiguity")]
    registry = {"schema_version": 1, "kind": "RELIABILITY_V4_SAFETY_PROSPECTIVE_EXECUTION_REGISTRY", "created_utc": REGISTRY,
                "source_core_plan": contract["core_plan"], "snapshot_audit_contract": contract_pin,
                "driver": contract["audit_tools"]["driver"], "validator": contract["audit_tools"]["validator"], "trials": trials}
    registry_pin = write(safety_dir / "registry.json", registry)
    facts, terminal_slots = [], []
    for trial in trials:
        model = core["protocol"]["resources"][trial["target_class"]]["model"]
        snapshot = write(Path(trial["directory"]) / "configuration/source_sha256.json", expected(model))
        fact = {"id": trial["id"], "result": "PASS", "evidence": {"source_snapshot": snapshot}}
        row_pin = write(safety_dir / (trial["id"] + ".json"), {"trial": trial, "status": "PASS", "infrastructure_stop": False,
            "cleanup": {"residual_processes": []}, "execution_facts": fact, "source_snapshot_audit": audit_evidence(model)})
        facts.append({**fact, "original_terminal": row_pin})
        terminal_slots.append({"id": trial["id"], "status": "PASS", "terminal": row_pin})
    facts_pin = write(safety_dir / "slots_facts.json", {"kind": "RELIABILITY_V4_SAFETY_EXECUTION_FACTS", "result": "PASS",
        "created_utc": SAFETY_END, "planned_count": 4, "attempted_count": 4, "pending_count": 0,
        "registry": registry_pin, "slots": facts})
    summary_pin = write(safety_dir / "development_validation_summary.json", {
        "kind": "RELIABILITY_V4_FINAL_SAFETY_SUMMARY", "result": "PASS", "created_utc": SAFETY_END,
        "evidence_scope": "REAL_RECORDED_DEVELOPMENT_EVIDENCE", "validation_scope": "DEVELOPMENT_ONLY_NOT_FORMAL_ADMISSION",
        "source_facts": facts_pin, "slots": facts, "bindings": builder.bindings(core)})
    validation_pin = write(safety_dir / "development_guard_validation.json", {"result": "PASS", "error": None,
        "finished_utc": SAFETY_END, "summary": summary_pin})
    terminal_pin = write(safety_dir / "execution_terminal.json", {"status": "COMPLETED", "returncode": 0, "stop_reason": None,
        "finished_utc": SAFETY_END, "planned_count": 4, "attempted_count": 4, "pending_count": 0,
        "unclosed_started_ids": [], "cleanup": {"residual_processes": []}, "registry": registry_pin,
        "facts": facts_pin, "guard_validation": validation_pin, "slots": terminal_slots})
    owner = {"status": "COMPLETED", "all_engineering_pass": True, "registry": registry_pin, "execution_terminal": terminal_pin}
    write(safety_dir / "owner_terminal.json", owner)
    write(safety_dir / "owner_state.json", owner)
    return SimpleNamespace(f=f, audit_root=audit_root, native_script=native_script, native=native,
        native_pin=native_pin, registry=registry, registry_pin=registry_pin, contract=contract, contract_pin=contract_pin)


class SnapshotSizeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.s = fixture(self.temporary.name)
        self.f = self.s.f

    @contextmanager
    def relocated(self):
        actual = measurement.guard.import_file
        def imported(name, path):
            module = actual(name, path)
            if name == "measurement_saved_snapshot_audit":
                module.AUDIT_ROOT = self.s.audit_root
                module.NATIVE_SCRIPT = self.s.native_script
            return module
        with patch.object(measurement.guard, "import_file", side_effect=imported):
            yield

    def measure(self, **kwargs):
        options = {"snapshot_audit_registry": self.s.registry_pin["path"],
                   "snapshot_audit_registry_sha256": self.s.registry_pin["sha256"],
                   "snapshot_audit_native_receipt": self.s.native_pin["path"],
                   "snapshot_audit_native_receipt_sha256": self.s.native_pin["sha256"]}
        options.update(kwargs)
        with self.relocated():
            return measurement.measure(self.f.paths["core"], self.f.paths["extension"], self.f.output, **options)

    def refuse(self, message=None, **kwargs):
        with self.assertRaisesRegex((guard.Refusal, OSError, KeyError, ValueError), message or ".*"):
            self.measure(**kwargs)
        self.assertFalse(self.f.output.exists())

    def rebind_native(self):
        self.s.native_pin = write(Path(self.s.native_pin["path"]), self.s.native)

    def test_complete28_keeps_fail_and_explicit_prior_evidence_without_payload_reads(self):
        actual = Path.open
        def checked(path, *args, **kwargs):
            if path.suffix.lower() in {".pt", ".jsonl", ".db3", ".zstd", ".mcap", ".vhdx"}:
                self.fail("Payload/model read: " + str(path))
            return actual(path, *args, **kwargs)
        with patch.object(Path, "open", checked):
            result = self.measure()
        self.assertEqual(result["measured_count"], 28)
        self.assertEqual(result["original_status_counts"], {"FAIL": 1, "PASS": 27})
        self.assertFalse(result["payload_content_reads"])
        proof = result["source_snapshot_validation"]
        self.assertEqual(proof["original_extra_count"], 1)
        self.assertFalse(proof["model_content_revalidated"])
        self.assertFalse(proof["original_helper_validation_repeated"])
        self.assertEqual(proof["saved_four_safety_snapshots_checked"], 4)
        self.assertEqual(proof["native_integration_receipt"], self.s.native_pin)
        self.assertIn("snapshot_audit_metadata_adapter", result["tool_bindings"])
        for label, plan in self.f.plans.items():
            for trial in plan["trials"]:
                key = (label, trial["target_class"], trial["group"] if label == "core" else trial["extension_condition"])
                paths = measurement.budget.sample_paths(plan, trial, self.f.output)
                self.assertGreater(measurement.budget.read_sample(key, plan, trial, paths, {})["total_bytes"], 0)
                receipt = guard.load(self.f.output / (trial["name"] + ".json"))
                self.assertEqual(receipt["source_snapshot_validation"]["original_extra_sources"], proof["original_extra_sources"])
        self.assertFalse(any(self.s.audit_root.rglob("__pycache__")))

    def test_default_strict_path_still_refuses_retained_original_extra(self):
        with self.assertRaisesRegex(guard.Refusal, "snapshot differs"):
            measurement.measure(self.f.paths["core"], self.f.paths["extension"], self.f.output)
        self.assertFalse(self.f.output.exists())

    def test_opt_in_requires_all_four_flags_before_loading_or_writing(self):
        for name in ("snapshot_audit_registry", "snapshot_audit_registry_sha256",
                     "snapshot_audit_native_receipt", "snapshot_audit_native_receipt_sha256"):
            with self.subTest(name=name):
                self.refuse("all four explicit", **{name: None})

    def test_unknown_missing_changed_extra_and_canonical_snapshot_rejected_even_when_rebound(self):
        sample = self.f.samples[-1]
        path = sample.directory / "configuration/source_sha256.json"
        original_snapshot = guard.load(path)
        variants = []
        for name, digest in ((EXTRA, None), (EXTRA, "9" * 64), ("scripts/unregistered.py", "9" * 64),
                             ("uav_tracking/core/__init__.py", "9" * 64)):
            changed = deepcopy(original_snapshot)
            if digest is None:
                del changed[name]
            else:
                changed[name] = digest
            variants.append(changed)
        for changed in variants:
            with self.subTest(changed=changed.get(EXTRA)):
                base.change_report(sample, "configuration/source_sha256.json", changed)
                self.refuse("exact original scanned")

    def test_current_original_extra_mutation_and_new_scanner_name_are_rejected(self):
        path = self.f.root / EXTRA
        original_bytes = path.read_bytes()
        path.write_bytes(b"# changed original extra\n")
        self.refuse("scanner text changed")
        path.write_bytes(original_bytes)
        (self.f.root / "scripts/new_unregistered.py").write_bytes(b"# new scanner file\n")
        self.refuse("scanner name set changed")

    def test_native_preparation_or_wrong_scope_or_skipped_helper_is_insufficient(self):
        original_native = deepcopy(self.s.native)
        for key, value in (("result", "WINDOWS_PREPARATION_ONLY"), ("scope", "PREP_ONLY"),
                           ("exit_code", 2), ("mandatory_helper_hash_traversals_skipped", True),
                           ("helper_original_source_and_model_hashing_allowed_and_preserved", False)):
            with self.subTest(key=key):
                self.s.native = {**original_native, key: value}
                self.rebind_native()
                self.refuse("Completed original native integration")

    def test_mismatched_native_contract_metadata_refuses(self):
        self.s.native["contract_metadata"]["rule"] = "invented_rule"
        self.rebind_native()
        self.refuse("Completed original native integration")

    def test_wrong_fixed_tool_digest_or_path_refuses(self):
        tool = self.s.audit_root / "tools/reliability_v4_snapshot_audit.py"
        tool.write_bytes(tool.read_bytes() + b"\n# changed bytes\n")
        self.refuse("Saved audit binding changed")

    def test_prior_native_plan_and_producer_must_be_bound(self):
        self.s.native["plan_after"]["sha256"] = "0" * 64
        self.rebind_native()
        self.refuse("Completed original native integration")

    def test_safety_owner_and_safety_guard_failure_cannot_be_ignored(self):
        audit = Path(self.s.registry_pin["path"]).parent
        owner_path = audit / "owner_state.json"
        owner = guard.load(owner_path)
        write(owner_path, {**owner, "all_engineering_pass": False})
        self.refuse("four-safety lifecycle")
        write(owner_path, owner)
        validation = guard.load(audit / "development_guard_validation.json")
        write(audit / "development_guard_validation.json", {**validation, "result": "FAIL"})
        self.refuse("four-safety lifecycle")

    def test_registry_and_native_metadata_cannot_point_to_payload_before_rejection(self):
        actual = Path.open
        def checked(path, *args, **kwargs):
            if path.suffix.lower() in {".pt", ".jsonl", ".db3", ".zstd", ".vhdx"}:
                self.fail("Forbidden read before metadata refusal: " + str(path))
            return actual(path, *args, **kwargs)
        with patch.object(Path, "open", checked):
            self.refuse("Named <=1 MiB", snapshot_audit_native_receipt=self.f.root / "models/yolo11n.pt")
            self.refuse("Named <=1 MiB", snapshot_audit_registry=self.f.samples[0].directory / "telemetry.jsonl")

    def test_nested_metadata_binding_cannot_read_model_before_rejection(self):
        self.s.registry["snapshot_audit_contract"] = {"path": str(self.f.root / "models/yolo11n.pt"), "sha256": "0" * 64}
        self.s.registry_pin = write(Path(self.s.registry_pin["path"]), self.s.registry)
        actual = Path.open
        def checked(path, *args, **kwargs):
            if path.suffix == ".pt":
                self.fail("Nested model read")
            return actual(path, *args, **kwargs)
        with patch.object(Path, "open", checked):
            self.refuse("Named <=1 MiB")

    def test_end_of_collection_checks_model_stat_and_new_scanner_name(self):
        actual = measurement.inventory
        calls = 0
        def changed(directory):
            nonlocal calls
            calls += 1
            if calls == 29:
                with (self.f.root / "models/yolo11n.pt").open("ab") as stream:
                    stream.write(b"changed stat only")
            return actual(directory)
        with patch.object(measurement, "inventory", side_effect=changed):
            self.refuse("original map/stat differs|Model stat changed")

    def test_cli_incomplete_opt_in_returns_refusal_without_output(self):
        stream = io.StringIO()
        with redirect_stderr(stream):
            code = measurement.main(["--core-development-plan", str(self.f.paths["core"]),
                "--extension-development-plan", str(self.f.paths["extension"]), "--output", str(self.f.output),
                "--snapshot-audit-registry", self.s.registry_pin["path"]])
        self.assertEqual(code, 2)
        self.assertIn("all four explicit", json.loads(stream.getvalue())["reason"])
        self.assertFalse(self.f.output.exists())


if __name__ == "__main__":
    unittest.main()
