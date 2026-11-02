"""Strict metadata-adapter regressions; all runtime evidence here is inert."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from tools import reliability_v4_guard as guard
from tools import reliability_v4_snapshot_audit as audit
from tools import run_reliability_v4_safety as safety

ROOT = Path(__file__).resolve().parents[1]
FREEZE_TIME = "2026-10-19T00:00:05+00:00"
PLAN_TIME = "2026-10-19T00:00:10+00:00"
CONTRACT_TIME = "2026-10-19T00:00:20+00:00"
REGISTRY_TIME = "2026-10-20T00:00:00+00:00"


def write(path, value):
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return guard.file_binding(path)


def inert_contract(root, plan=None, plan_path=None):
    """Create a tiny original freeze and an explicit, later tool contract."""
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    results = root / "results"
    results.mkdir(exist_ok=True)
    canonical = {"scripts/run_stage1_trial.py": b"# inert original scanner source\n",
        "uav_tracking/core/__init__.py": b"# canonical core package\n",
        "uav_tracking/core/kalman.py": b"# canonical filter revision\n",
        "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/__init__.py": b"# canonical nodes package\n",
        "models/inert.pt": b"inert model bytes", "config/dds_runtime_humble22.json": b"{}"}
    if plan is None:
        plan = {"frozen_root": str(root), "results_root": str(results), "trials": [], "source_hashes": {}}
    for name, raw in canonical.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(raw)
        plan["source_hashes"][name] = guard.sha(path)
    extras = {"ros2_ws/src/uav_tracking_nodes/build/lib/uav_tracking/core/kalman.py": b"# original stale filter copy\n"}
    for name, raw in extras.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    for relative in audit.BASE_NAMES.values():
        path = root / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"# inert original frozen tool, never imported\n")
    plan["created_utc"] = PLAN_TIME
    plan["plan_sha256"] = guard.sealed(plan, "plan_sha256")
    plan_path = plan_path or results / "core/plan.json"
    core = write(plan_path, plan)
    original = results / "freeze_validation"
    directory = original / "source_integrity"
    all_names = set(plan["source_hashes"]) | set(extras) | set(audit.BASE_NAMES.values())
    entries = {name: {"kind": "file", "bytes": (root / name).stat().st_size, "sha256": guard.sha(root / name)}
               for name in all_names}
    source = str(root.parent / "original_source")
    before = write(directory / "source_before.json", {"entries": entries, "source": source, "created_utc": FREEZE_TIME})
    after = write(directory / "source_after.json", {"entries": entries, "source": source})
    frozen = write(directory / "frozen_actual.json", {"entries": entries, "frozen": str(root)})
    report = {"schema_version": 1, "status": "PASS", "scope": "RSYNC_FILTERED_SOURCE_PRE_POST_AND_COMPLETE_FROZEN_COPY_BYTES",
        "source": source, "frozen": str(root), "created_utc": FREEZE_TIME, "errors": [], "build_returncode": 0,
        "source_unchanged": True, "copy_identical": True,
        "source_pre_post": {"added": [], "changed": [], "missing": []},
        "frozen_copy": {"added": [], "changed": [], "missing": []},
        "actual_frozen_entries": len(entries), "actual_source_entries": len(entries), "expected_entries": len(entries),
        "before": before, "maps": {"source_after.json": after, "frozen_actual.json": frozen}}
    report_binding = write(directory / "source_frozen_integrity.json", report)
    modules = {"uav_tracking.core": str(root / "uav_tracking/core/__init__.py"),
        "uav_tracking_nodes": str(root / "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/__init__.py")}
    for name, filename in (("uav_tracking_interfaces.msg", "__init__.py"),
            ("uav_tracking_interfaces.msg._target_observation_array", "_target_observation_array.py"),
            ("uav_tracking_interfaces.msg._target_state", "_target_state.py")):
        path = root / "ros2_ws/install/lib/python3.10/site-packages/uav_tracking_interfaces/msg" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# inert generated message, never imported\n")
        modules[name] = str(path)
    imports = write(original / "import_isolation.json", {"root": str(root), "isolated": True, "module_files": modules,
        "ros_package_prefixes": {name: str(root / "ros2_ws/install") for name in
            ("uav_tracking_nodes", "uav_tracking_interfaces", "uav_tracking_bringup", "uav_tracking_px4_adapter")}})
    contract = {"schema_version": 1, "kind": audit.KIND, "created_utc": CONTRACT_TIME, "rule": audit.RULE,
        "frozen_root": str(root), "audit_tool_root": str(ROOT),
        "core_plan": {**core, "plan_sha256": plan["plan_sha256"]},
        "freeze_report": report_binding, "source_before": before, "source_after": after, "frozen_map": frozen,
        "import_isolation": imports, "audit_tools": {key: guard.file_binding(ROOT / "tools" / name) for key, name in audit.TOOL_NAMES.items()},
        "base_tools": {key: guard.file_binding(root / name) for key, name in audit.BASE_NAMES.items()},
        "evidence_limitations": audit.LIMITATION}
    contract_path = results / "separate_audit/snapshot_contract.json"
    contract_binding = write(contract_path, contract)
    registry = {"snapshot_audit_contract": contract_binding, "driver": contract["audit_tools"]["driver"],
                "validator": contract["audit_tools"]["validator"], "created_utc": REGISTRY_TIME}
    expected = {name: digest for name, digest in plan["source_hashes"].items() if audit.selected_source(name)}
    expected.update({"models/inert.pt": plan["source_hashes"]["models/inert.pt"],
                     "config/dds_runtime_humble22.json": plan["source_hashes"]["config/dds_runtime_humble22.json"]})
    snapshot = {**expected, **{name: guard.sha(root / name) for name in extras}}
    return SimpleNamespace(root=root, plan=plan, plan_path=plan_path, contract=contract, contract_path=contract_path,
        registry=registry, expected=expected, snapshot=snapshot, extra=next(iter(extras)))


class SnapshotAuditTests(unittest.TestCase):
    def evidence(self, fixture):
        return guard.source_snapshot_evidence(fixture.snapshot, fixture.expected, fixture.registry, fixture.plan, fixture.plan_path)

    def test_exact_original_extra_is_retained_with_explicit_differing_copy_report(self):
        with tempfile.TemporaryDirectory() as folder:
            f = inert_contract(Path(folder) / "runtime")
            original = deepcopy(f.snapshot)
            report = self.evidence(f)
            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["original_extra_sources"], {f.extra: f.snapshot[f.extra]})
            self.assertFalse(report["historical_copy_comparisons"][f.extra]["same_bytes"])
            self.assertIn("adapter_node.__file__", report["evidence_limitations"])
            self.assertEqual(f.snapshot, original)
            self.assertNotEqual(f.root, Path(f.contract["audit_tool_root"]))

    def test_legacy_without_explicit_contract_still_requires_exact_registered_set(self):
        with tempfile.TemporaryDirectory() as folder:
            f = inert_contract(Path(folder) / "runtime")
            del f.registry["snapshot_audit_contract"]
            with self.assertRaisesRegex(ValueError, "snapshot differs"):
                self.evidence(f)
            f.snapshot = deepcopy(f.expected)
            self.assertEqual(self.evidence(f)["mode"], "EXACT_REGISTERED_SOURCE_SET")

    def test_even_consistently_changed_model_and_dds_expected_hashes_must_match_plan(self):
        for name in ("models/inert.pt", "config/dds_runtime_humble22.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                f = inert_contract(Path(folder) / "runtime")
                f.expected[name] = f.snapshot[name] = "f" * 64
                with self.assertRaisesRegex(ValueError, "requirements were removed or invented"):
                    self.evidence(f)

    def test_explicit_contract_requires_actual_distinct_roots(self):
        with tempfile.TemporaryDirectory() as folder:
            f = inert_contract(Path(folder) / "runtime")
            f.contract["audit_tool_root"] = str(f.root)
            f.registry["snapshot_audit_contract"] = write(f.contract_path, f.contract)
            with self.assertRaisesRegex(ValueError, "roots must be distinct"):
                self.evidence(f)

    def test_snapshot_missing_changed_or_unknown_canonical_and_extra_are_refused(self):
        for change in ("missing_canonical", "changed_canonical", "missing_extra", "changed_extra", "unknown_extra"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                f = inert_contract(Path(folder) / "runtime")
                if change == "unknown_extra":
                    f.snapshot["ros2_ws/src/unregistered/build/lib/new.py"] = "f" * 64
                else:
                    key = f.extra if change.endswith("extra") else "uav_tracking/core/kalman.py"
                    if change.startswith("missing"):
                        del f.snapshot[key]
                    else:
                        f.snapshot[key] = "f" * 64
                with self.assertRaises(ValueError):
                    self.evidence(f)

    def test_changes_to_actual_registered_unscanned_and_extra_sources_are_refused(self):
        for name in ("config/dds_runtime_humble22.json", "uav_tracking/core/kalman.py", "extra", "new_source"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                f = inert_contract(Path(folder) / "runtime")
                selected = f.extra if name == "extra" else "scripts/new_original_unregistered.py" if name == "new_source" else name
                (f.root / selected).write_bytes(b"changed outside original freeze\n")
                with self.assertRaises(ValueError):
                    self.evidence(f)

    def test_contract_tool_root_plan_and_chronology_cannot_be_rebound(self):
        for change in ("tool_sha", "helper_path", "root", "audit_root", "core", "late_contract", "validator"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                f = inert_contract(Path(folder) / "runtime")
                c = f.contract
                if change == "tool_sha":
                    c["audit_tools"]["driver"]["sha256"] = "0" * 64
                elif change == "helper_path":
                    c["audit_tools"]["helper"] = guard.file_binding(ROOT / "tools/reliability_v4_register.py")
                elif change == "root":
                    c["frozen_root"] = str(f.root.parent)
                elif change == "audit_root":
                    c["audit_tool_root"] = str(f.root)
                elif change == "core":
                    c["core_plan"]["plan_sha256"] = "0" * 64
                elif change == "late_contract":
                    c["created_utc"] = "2026-10-21T00:00:00+00:00"
                else:
                    f.registry["validator"] = c["audit_tools"]["driver"]
                f.registry["snapshot_audit_contract"] = write(f.contract_path, c)
                with self.assertRaises(ValueError):
                    self.evidence(f)

    def test_original_map_bytes_origin_and_entry_kind_cannot_be_changed(self):
        for change in ("bytes", "rebound_map", "origin", "kind", "escape", "counts", "rebound_report_path"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                f = inert_contract(Path(folder) / "runtime")
                c = f.contract
                path = Path(c["frozen_map"]["path"])
                data = guard.load(path)
                if change == "bytes":
                    path.write_bytes(b"{}")
                elif change == "rebound_report_path":
                    c["freeze_report"] = write(f.root / "results/fake_report.json", guard.load(c["freeze_report"]["path"]))
                elif change == "counts":
                    report = guard.load(c["freeze_report"]["path"])
                    report["actual_frozen_entries"] += 1
                    c["freeze_report"] = write(Path(c["freeze_report"]["path"]), report)
                else:
                    if change == "origin":
                        data["frozen"] = str(f.root.parent)
                    elif change == "kind":
                        data["entries"][f.extra]["kind"] = "symlink"
                    elif change == "escape":
                        data["entries"]["../outside.py"] = data["entries"][f.extra]
                    else:
                        data["entries"][f.extra]["sha256"] = "0" * 64
                    c["frozen_map"] = write(path, data)
                f.registry["snapshot_audit_contract"] = write(f.contract_path, c)
                with self.assertRaises(ValueError):
                    self.evidence(f)

    def test_rehashed_complete_maps_still_cannot_authorize_bad_kind_escape_or_metadata(self):
        for change in ("kind", "escape", "bytes", "pre_post_divergence"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                f = inert_contract(Path(folder) / "runtime")
                c = f.contract
                maps = {name: guard.load(c[name]["path"]) for name in ("source_before", "source_after", "frozen_map")}
                for name, data in maps.items():
                    if change == "kind":
                        data["entries"][f.extra]["kind"] = "symlink"
                    elif change == "escape":
                        data["entries"]["../escaped.py"] = deepcopy(data["entries"][f.extra])
                    elif change == "bytes":
                        data["entries"][f.extra]["bytes"] += 1
                    elif name == "source_after":
                        data["entries"][f.extra]["sha256"] = "0" * 64
                    c[name] = write(Path(c[name]["path"]), data)
                report_path = Path(c["freeze_report"]["path"])
                report = guard.load(report_path)
                report["before"] = c["source_before"]
                report["maps"] = {"source_after.json": c["source_after"], "frozen_actual.json": c["frozen_map"]}
                for name in ("actual_frozen_entries", "actual_source_entries", "expected_entries"):
                    report[name] = len(maps["frozen_map"]["entries"])
                c["freeze_report"] = write(report_path, report)
                f.registry["snapshot_audit_contract"] = write(f.contract_path, c)
                with self.assertRaises(ValueError):
                    self.evidence(f)

    def test_import_receipt_must_be_actual_isolated_canonical_tree_and_adapter_prefix(self):
        for change in ("false", "core_stale", "node_stale", "adapter_prefix", "extra_adapter_claim", "missing_messages"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                f = inert_contract(Path(folder) / "runtime")
                c = f.contract
                path = Path(c["import_isolation"]["path"])
                receipt = guard.load(path)
                if change == "false":
                    receipt["isolated"] = False
                elif change in {"core_stale", "node_stale"}:
                    receipt["module_files"]["uav_tracking.core" if change == "core_stale" else "uav_tracking_nodes"] = str(f.root / f.extra)
                elif change == "adapter_prefix":
                    receipt["ros_package_prefixes"]["uav_tracking_px4_adapter"] = str(f.root.parent)
                elif change == "extra_adapter_claim":
                    receipt["module_files"]["uav_tracking_px4_adapter.adapter_node"] = str(f.root / f.extra)
                else:
                    del receipt["module_files"]["uav_tracking_interfaces.msg._target_state"]
                c["import_isolation"] = write(path, receipt)
                f.registry["snapshot_audit_contract"] = write(f.contract_path, c)
                with self.assertRaises(ValueError):
                    self.evidence(f)

    def test_metadata_contract_creation_does_not_change_any_original_file(self):
        with tempfile.TemporaryDirectory() as folder:
            f = inert_contract(Path(folder) / "runtime")
            before = {path: path.read_bytes() for path in f.root.rglob("*") if path.is_file()}
            destination = f.root / "results/new_contract/contract.json"
            result = audit.create_contract(f.plan_path, f.contract["freeze_report"]["path"],
                f.contract["import_isolation"]["path"], destination, api=guard)
            self.assertEqual(result, guard.file_binding(destination))
            self.assertTrue(all(path.read_bytes() == raw for path, raw in before.items()))
            with self.assertRaises(ValueError):
                audit.create_contract(f.plan_path, f.contract["freeze_report"]["path"],
                    f.contract["import_isolation"]["path"], destination, api=guard)

    def test_public_safety_loads_explicit_distinct_audit_and_runtime_roots_without_root_patch(self):
        batch = guard.import_file("snapshot_actual_inert_normal_batch", ROOT / "scripts/run_reliability_v4_batch.py")
        original_import = guard.import_file
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve() / "runtime"
            (root / "scripts").mkdir(parents=True)
            sources = {}
            for name in ("scripts/run_reliability_v4.py", "scripts/run_reliability_v4_batch.py"):
                (root / name).write_bytes(b"# inert frozen runner, never executed\n")
                sources[name] = guard.sha(root / name)
            trials, rows = [], {}
            for cls in guard.CLASSES:
                for group in guard.GROUPS:
                    identifier = cls + "_" + group + "_seed004"
                    specs, evaluations = [], []
                    for kind in ("source_clock", "native_startup"):
                        report = write(root / "results/reports" / (identifier + "_" + kind + ".json"), {"result": "PASS"})
                        specs.append({"kind": kind, "report": report["path"]})
                        evaluations.append({"kind": kind, "result": "PASS", "error": None, "report": report["path"],
                            "report_sha256": report["sha256"], "execution": {"returncode": 0, "error": None}})
                    trial = {"id": identifier, "target_class": cls, "group": group, "seed": 4, "evaluations": specs}
                    trials.append(trial)
                    rows[identifier] = {"status": "PASS", "engineering_result": "PASS", "infrastructure_stop": False,
                        "execution_status": "COMPLETED", "flight_exit_code": 0, "runtime_configuration": {"errors": []},
                        "cleanup": {"residual_processes": []}, "evaluations": evaluations, "commands": [{"kind": "flight"}]}
                    write(root / "results/slots" / (identifier + ".json"), rows[identifier])
            plan = {"frozen_root": str(root), "results_root": str(root / "results"), "mode": "PROBE",
                "selected_seeds": [4], "selected_classes": list(guard.CLASSES), "selected_groups": list(guard.GROUPS),
                "trials": trials, "split_clock_bridge": True, "source_hashes": sources}
            f = inert_contract(root, plan)
            expected_owner_sources = {name: sources[name] for name in ("scripts/run_reliability_v4.py", "scripts/run_reliability_v4_batch.py")}
            owner = {"scope": "THIN_OWNER_OF_UNCHANGED_NORMAL_V4_RUNNER", "status": "COMPLETED", "policy": "core",
                "plan": str(f.plan_path), "plan_file_sha256": guard.sha(f.plan_path), "plan_sha256": plan["plan_sha256"],
                "all_engineering_pass": True, "all_slots_terminal": True, "status_counts": {"PASS": 12}, "pending_ids": [],
                "active_slot": None, "source_hashes": expected_owner_sources,
                "owner": {"pid": 99999999, "start_ticks": 123, "boot_id": "inert-boot",
                          "creation_identity_scope": "LINUX_PROC_START_TICKS_AND_BOOT_ID"}}
            owner_path = root / "results/normal_owner/owner_terminal.json"
            write(owner_path, owner)
            write(owner_path.with_name("owner_state.json"), owner)
            runner = SimpleNamespace(__file__=str(root / "scripts/run_reliability_v4.py"), ROOT=root,
                CLASSES=guard.CLASSES, GROUPS=guard.GROUPS, validate_plan=lambda *a: None, verify_sources=lambda *a: None,
                read_slots=lambda *a: rows, engineering_verdict=lambda *a: ("PASS", []), runtime_configuration=lambda *a: {"errors": []},
                record_path=lambda p, t: root / "results/slots" / (t["id"] + ".json"),
                required_evaluators=lambda t: {"source_clock", "native_startup"},
                read_evaluation=lambda spec, *a: {"result": "PASS", "report_sha256": guard.sha(spec["report"])},
                simulation_processes=lambda: [])
            def imported(name, path):
                if name.startswith("reliability_v4_snapshot_audit_"):
                    return original_import(name, path)
                return batch if name == "safety_same_root_normal_batch" else SimpleNamespace(bindings=lambda p: {"inert_fixture": True})
            with patch.object(guard, "load_runtime", return_value=SimpleNamespace(v4=runner)), patch.object(guard, "import_file", side_effect=imported):
                context = safety.load_core(f.plan_path, owner_path, snapshot_audit_contract=f.registry["snapshot_audit_contract"])
                self.assertEqual(context.root, root)
                self.assertNotEqual(context.root, safety.ROOT)
                self.assertEqual(len(context.closure["original_core_records"]), 12)
                with self.assertRaisesRegex(ValueError, "same-root"):
                    safety.load_core(f.plan_path, owner_path)
                runner.ROOT = root.parent
                with self.assertRaisesRegex(ValueError, "runner/root"):
                    safety.load_core(f.plan_path, owner_path, snapshot_audit_contract=f.registry["snapshot_audit_contract"])

    def test_full_real_safety_validator_accepts_only_explicit_preserved_original_snapshot(self):
        spec = importlib.util.spec_from_file_location("snapshot_guard_full_fixtures", ROOT / "tests/test_reliability_v4_guard.py")
        fixtures = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixtures)
        with tempfile.TemporaryDirectory() as folder:
            manifest, context, runtime, summary, facts, _ = fixtures.safety_fixture(Path(folder))
            f = inert_contract(Path(context.development["frozen_root"]), context.development, context.development_path)
            registry_path = Path(facts["registry"]["path"])
            registry = guard.load(registry_path)
            registry.update(f.registry)
            registry["source_core_plan"] = {**guard.file_binding(f.plan_path), "plan_sha256": f.plan["plan_sha256"]}
            registry["flight_source_hashes"] = context.gate_bindings["flight_source_hashes"]
            for slot in facts["slots"]:
                snapshot_path = Path(slot["evidence"]["source_snapshot"]["path"])
                old = guard.load(snapshot_path)
                old.update({name: digest for name, digest in f.snapshot.items() if audit.selected_source(name)})
                slot["evidence"]["source_snapshot"] = write(snapshot_path, old)
            facts["registry"] = write(registry_path, registry)
            summary["source_facts"] = write(Path(summary["source_facts"]["path"]), facts)
            manifest["safety"] = write(Path(manifest["safety"]["path"]), summary)
            guard.validate_safety(manifest, context, runtime)
            del registry["snapshot_audit_contract"]
            facts["registry"] = write(registry_path, registry)
            summary["source_facts"] = write(Path(summary["source_facts"]["path"]), facts)
            manifest["safety"] = write(Path(manifest["safety"]["path"]), summary)
            with self.assertRaisesRegex(ValueError, "snapshot differs"):
                guard.validate_safety(manifest, context, runtime)


if __name__ == "__main__":
    unittest.main()
