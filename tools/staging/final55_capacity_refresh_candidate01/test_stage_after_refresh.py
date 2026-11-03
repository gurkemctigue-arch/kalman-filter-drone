"""Isolated small fixtures only; no native, WSL, source copy, bag or model work."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("capacity_stage_fixtures", HERE / "stage_after_refresh.py")
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
legacy = s.fixed_module(s.LEGACY, s.LEGACY_SHA)
refresh = s.fixed_module(s.REFRESH, s.REFRESH_SHA)
m = refresh.fixed_module(refresh.MEASUREMENT, refresh.MEASUREMENT_SHA)
old_real = m.fixed_module(m.OLD08, m.OLD08_SHA)
base_real = legacy.fixed_module(legacy.BASE, legacy.BASE_SHA)
prior_real = legacy.fixed_module(legacy.PRIOR, legacy.PRIOR_SHA)
vpath = s.ROOT / "tools/staging/final55_offline_overlay_profile03_20261103/validate_owner_closure.py"
v = s.fixed_module(vpath, hashlib.sha256(vpath.read_bytes()).hexdigest())


def binding(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+"\n", encoding="utf8")
    return binding(path)


class DerivedFixture:
    def __init__(self, root):
        self.bindings = []
        for cls in ("person", "car"):
            for name in ("arrays.json", *refresh.SIDECARS):
                path = root / (cls+"_export") / name
                item = write(path, {"kind": "SYNTHETIC_DERIVED", "class": cls, "name": name})
                self.bindings.append({**item, "bytes": path.stat().st_size})

    def unchanged(self):
        for item in self.bindings:
            path = Path(item["path"])
            if binding(path)["sha256"] != item["sha256"] or path.stat().st_size != item["bytes"]:
                raise ValueError("Synthetic derived artifact changed")


class StageRefreshTests(unittest.TestCase):
    def fixture(self, tmp):
        root = Path(tmp).resolve(); validation = root / "validation"; validation.mkdir()
        p = {"frozen": root / "frozen", "receipt": validation / "original7", "tools": root / "tools",
            "sizes": root / "sizes", "calibration": root / "calibration", "budget": root / "negative/budget.json",
            "core": root / "core.json", "extension": root / "extension.json", "idle": root / "idle.sh"}
        for name in ("frozen", "receipt", "tools", "sizes", "calibration"):
            p[name].mkdir()
        p["inventory"] = p["receipt"] / "never_created_inventory.json"
        q = refresh.continuation_paths(p); q["receipt"].mkdir()
        r = dict(p); r.update(receipt=validation / "SYNTHETIC_refresh3")
        r["receipt"].mkdir(); r.update(inventory=r["receipt"] / "physical_inventory.json", budget=r["receipt"] / "budget.json")
        epoch = datetime(2020, 1, 1, tzinfo=timezone.utc)
        t = lambda n: (epoch+timedelta(seconds=n)).isoformat()
        identity = {"pid": 123, "start_ticks": 123, "boot_id": "f79204a4-99cd-42cf-b886-aa905b1cac6a"}
        guard = {"machine_lock": "SYNTHETIC_LOCK_NO_NATIVE", "blockers": []}
        core = write(p["core"], {"kind": "SYNTHETIC_CORE", "plan_sha256": "core"})
        extension = write(p["extension"], {"kind": "SYNTHETIC_EXTENSION", "plan_sha256": "extension"})
        assumption_path = old_real.paths()["assumptions"]
        assumptions = binding(assumption_path)
        self.assertEqual(assumptions["sha256"], old_real.ASSUMPTIONS_SHA)
        tool = write(p["tools"] / "budget_tool.json", {"kind": "SYNTHETIC_TOOL"})
        guard_tool = write(p["tools"] / "guard_tool.json", {"kind": "SYNTHETIC_GUARD_TOOL"})
        pins = {"tools/reliability_v4_storage_budget.py": tool["sha256"], "tools/reliability_v4_guard.py": guard_tool["sha256"]}
        old = SimpleNamespace(COMMIT="SYNTHETIC_COMMIT", sha=old_real.sha, positive_budget=old_real.positive_budget, TOOL_PINS=pins)
        old.workflow_commands = lambda paths: [(name, ["SYNTHETIC_ORIGINAL_FACTORY", name, str(paths["inventory"]), str(paths["budget"])])
            for name in ("measure_actual28", "physical_inventory", "person_velocity_export", "car_velocity_export", "R0_candidate", "full280_budget")]
        audit = {"kind": "SYNTHETIC_FULL16", "status": "SYNTHETIC_CLOSED16", "pending_ids": [],
            "closed_ids": ["synthetic_%02d" % i for i in range(16)], "created_utc": t(50)}
        first_closure = write(p["receipt"] / "full16_closure_audit.json", {**audit, "created_utc": t(0)})
        continued_closure = write(q["receipt"] / "full16_closure_audit.json", {**audit, "created_utc": t(10.5)})
        fresh_closure = write(r["receipt"] / "full16_closure_audit.json", {**audit, "created_utc": t(39)})
        inventory = {"schema_version": 1, "kind": "RELIABILITY_V4_PHYSICAL_STORAGE_INVENTORY",
            "created_utc": t(14.5), "evidence_scope": "METADATA_ONLY_NOT_FORMAL_ADMISSION",
            "volumes": [{"mount": "/mnt/d", "windows_volume_id": "SYNTHETIC_VOLUME", "free_bytes": 50}],
            "vhd_host": {"distribution": "UAVHumble22", "path": "/mnt/d/SYNTHETIC/ext4.vhdx"}}
        old_inventory_binding = write(q["inventory"], inventory)
        cells = []
        for matrix, groups in (("core", old_real.CORE_GROUPS), ("extension", old_real.EXTENSION_GROUPS)):
            for cls in ("person", "car"):
                for group in groups:
                    name = matrix+"_"+cls+"_"+group
                    cells.append({"matrix": matrix, "target_class": cls, "condition": group,
                        "development_size_evidence": write(p["sizes"] / (name+".json"), {"kind": "SYNTHETIC_SIZE"}),
                        "archive_evidence": write(root / "archives" / (name+".json"), {"kind": "SYNTHETIC_METADATA_ONLY"})})
        storage = {"vhd_host": {"volume": "drive_D"}, "cells": cells, "fixed_all_reserves": 123}
        small = {item["path"]: item["sha256"] for item in (core, extension, assumptions, old_inventory_binding, tool, guard_tool)}
        for cell in cells:
            for role in ("development_size_evidence", "archive_evidence"):
                small[cell[role]["path"]] = cell[role]["sha256"]
        budget = {"schema_version": 1, "kind": "RELIABILITY_V4_STORAGE_BUDGET_ASSEMBLY_NOT_ADMISSION", "admission_performed": False,
            "created_utc": t(22.5), "storage": storage, "storage_sha256": refresh.digest(storage),
            "provenance": {"development_plans": {"core": core, "extension": extension}, "assumptions": assumptions,
                "physical_inventory": old_inventory_binding, "tool": tool, "guard_tool": guard_tool, "small_inputs_sha256": small},
            "capacity_preview": {"scope": "SYNTHETIC_SNAPSHOT_NOT_ADMISSION", "scheduled_slots": 280,
                "ext4_logical_free_bytes": 1000, "fits_declared_logical_budget": True, "volumes": {"drive_D": {
                    "mount": "/mnt/d", "windows_volume_id": "SYNTHETIC_VOLUME", "free_bytes": 50,
                    "required_bytes": 100, "remaining_after_budget_bytes": -50, "fits_declared_physical_budget": False}}},
            "limits": "SYNTHETIC_FIXTURE"}
        old_budget_binding = write(p["budget"], budget)
        candidate_binding = write(p["calibration"] / "R0_candidate.json", {"kind": "SYNTHETIC_R0", "created_utc": t(20.5)})
        derived = DerivedFixture(p["calibration"])
        first = {"scope": "SYNTHETIC_ORIGINAL7", "started_utc": t(1), "finished_utc": t(10), "returncode": 2,
            "errors": [{"utc": t(9), "error": "Refused: Refusing large input"}], "steps": [{"fixture": i} for i in range(7)],
            "closure_audit": first_closure}
        first_binding = write(p["receipt"] / "terminal.json", first)
        continued = {"scope": "SYNTHETIC_CONTINUATION6", "started_utc": t(11), "finished_utc": t(30), "returncode": 2,
            "errors": [{"utc": t(29), "error": "ValueError: "+refresh.CAPACITY_ERROR}],
            "steps": [{"started_utc": t(12+2*i), "finished_utc": t(13+2*i)} for i in range(6)],
            "closure_audit": continued_closure, "input_bindings": [old_budget_binding, candidate_binding]}
        for cls, row in zip(("person", "car"), continued["steps"][2:4]):
            path = q["receipt"] / (cls+".stdout.log")
            write(path, {"status": "PASS", "online_equivalence_status": "PASS", "native_state_audit_status": "PASS",
                "scope": "DEVELOPMENT_ONLY", "output": str(p["calibration"] / (cls+"_export"))})
            row["stdout"] = str(path)
        continued_binding = write(q["receipt"] / "terminal.json", continued)
        fresh_inventory = deepcopy(inventory); fresh_inventory["created_utc"] = t(43.5); fresh_inventory["volumes"][0]["free_bytes"] = 150
        new_inventory_binding = write(r["inventory"], fresh_inventory)
        fresh_budget = deepcopy(budget); fresh_budget["created_utc"] = t(45.5)
        fresh_budget["provenance"]["physical_inventory"] = new_inventory_binding
        mapping = fresh_budget["provenance"]["small_inputs_sha256"]
        mapping.pop(old_inventory_binding["path"]); mapping[new_inventory_binding["path"]] = new_inventory_binding["sha256"]
        fresh_budget["capacity_preview"]["volumes"]["drive_D"].update(free_bytes=150, remaining_after_budget_bytes=50, fits_declared_physical_budget=True)
        new_budget_binding = write(r["budget"], fresh_budget)
        source = {"path": str(s.REFRESH.resolve()), "sha256": s.REFRESH_SHA}
        proof, reused = {"kind": "SYNTHETIC_ARCHIVE_PROOF"}, {"kind": "SYNTHETIC_ACTUAL28_PROOF"}
        inputs = v.Inputs(v.local_small_read)
        for item in (first_binding, continued_binding, old_budget_binding, candidate_binding, first_closure, continued_closure):
            inputs.bound(item)
        history_bindings = list(inputs.seen.values())
        term = {"schema_version": 1, "scope": refresh.SCOPE, "status": "COMPLETED_CAPACITY_REFRESH_POSITIVE_FULL280_NOT_ADMISSION",
            "returncode": 0, "errors": [], "interruptions": [], "automatic_retry": False, "formal_admission": False,
            "source": source, "guard": guard, "commit": old.COMMIT, "owner_identity": identity,
            "started_utc": t(40), "finished_utc": t(47), "original_failure_terminal": first_binding,
            "continuation_failure_terminal": continued_binding, "original_execution_window": refresh.execution_window(first),
            "continuation_execution_window": refresh.execution_window(continued), "preserved_executed_source": proof,
            "reused_actual28": reused, "original_negative_budget": old_budget_binding, "original_R0_candidate": candidate_binding,
            "derived_input_bindings": derived.bindings, "new_inventory": new_inventory_binding, "new_budget": new_budget_binding,
            "closure_audit": fresh_closure, "steps": [], "input_bindings": history_bindings+[source, new_inventory_binding, new_budget_binding, fresh_closure]}
        for i, (name, argv) in enumerate([("native_idle", ["bash", p["idle"]])]+old.workflow_commands(r)[1:2]+old.workflow_commands(r)[5:]):
            row = {"id": name, "command": list(map(str, argv)), "returncode": 0, "pid": 123, "identity": identity,
                "started_utc": t(41+2*i), "finished_utc": t(42+2*i)}
            for channel in ("stdout", "stderr"):
                path = r["receipt"] / (name+"."+channel+".log")
                if name == "native_idle" and channel == "stdout":
                    item = write(path, {"kind": "ACTUAL_CURRENT_NATIVE_PROCESS_QUERY_ONLY", "matching_processes": []})
                else:
                    path.write_bytes(b"SYNTHETIC_LOG\n"); item = binding(path)
                row[channel] = str(path); term["input_bindings"].append(item)
            term["steps"].append(row)
        terminal_binding = write(r["receipt"] / "terminal.json", term)
        fake_m = SimpleNamespace(AFTER28_TERMINAL=first_binding)
        fake_refresh = SimpleNamespace(**{name: getattr(refresh, name) for name in (
            "SCOPE", "execution_window", "within_created", "inventory_identity", "same_budget_contract")}, CONTINUATION=continued_binding)
        context = {"p": p, "q": q, "v": v, "inputs": inputs, "audit": audit, "first": first, "continued": continued,
            "proof": proof, "reused": reused, "old_budget": budget, "old_budget_binding": old_budget_binding,
            "R0_binding": candidate_binding, "old_inventory": inventory, "derived": derived,
            "core_binding": core, "extension_binding": extension, "history_bindings": history_bindings}
        return SimpleNamespace(root=root, p=p, q=q, r=r, term=term, terminal_binding=terminal_binding, budget_binding=new_budget_binding,
            context=context, old=old, m=fake_m, refresh=fake_refresh, guard=guard, now=epoch+timedelta(seconds=60),
            t=t, fresh_budget=fresh_budget)

    def validate(self, f, terminal=None):
        return s.validate_refresh_terminal(terminal or f.term, f.terminal_binding, f.budget_binding,
            f.context, f.refresh, f.m, f.old, f.guard, f.now)

    def test_disabled_entry_is_inert_and_explicit_actions_cannot_import_or_prepare(self):
        with patch.object(s, "fixed_module", side_effect=AssertionError("No imports")), redirect_stdout(io.StringIO()):
            self.assertEqual(s.main([]), 0)
            self.assertEqual(s.main(["--execute"]), 2)
            self.assertEqual(s.main(["--preflight"]), 2)
        self.assertFalse(s.PRODUCTION_ENABLED); self.assertEqual(s.REGISTERED_INPUTS, {})

    def test_complete_synthetic_refresh_preserves_the_two_failed_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.fixture(tmp); before = {p: p.read_bytes() for p in f.root.rglob("*") if p.is_file()}
            checks = self.validate(f)
            self.assertEqual(checks["original_failed_returncodes"], [2, 2])
            self.assertEqual([checks[k] for k in ("preserved_original_step_count", "preserved_continuation_step_count", "closed_refresh_steps")], [7, 6, 3])
            self.assertFalse(checks["capacity_currently_revalidated"]); self.assertFalse(checks["formal_admission"])
            for path, content in before.items(): self.assertEqual(path.read_bytes(), content)

    def test_incomplete_relabelled_or_wrong_command_and_input_family_refuse(self):
        mutations = [lambda t: t["steps"].pop(), lambda t: t["steps"][1].update(command=["WRONG"]),
            lambda t: t["steps"][1].update(returncode=False), lambda t: t["source"].update(sha256="0"*64),
            lambda t: t["original_execution_window"].update(returncode=0), lambda t: t["continuation_execution_window"].update(returncode=0),
            lambda t: t["derived_input_bindings"][0].update(bytes=999), lambda t: t.update(guard={}),
            lambda t: t["input_bindings"].append(t["input_bindings"][0]),
            lambda t: t.update(input_bindings=[x for x in t["input_bindings"] if x != t["source"]]),
            lambda t: t.update(status="STOPPED_CAPACITY_REFRESH_PARTIAL_OUTPUTS_RETAINED"),
            lambda t: t["steps"][2].update(started_utc=t["started_utc"]),
            lambda t: t["interruptions"].append({"fixture": True})]
        for mutate in mutations:
            with self.subTest(mutation=mutate), tempfile.TemporaryDirectory() as tmp:
                f = self.fixture(tmp); changed = deepcopy(f.term); mutate(changed)
                with self.assertRaises(ValueError): self.validate(f, changed)

    def test_negative_unknown_or_changed_budget_contract_is_never_a_stage_permission(self):
        mutations = [lambda b: b["capacity_preview"]["volumes"]["drive_D"].update(
                free_bytes=50, remaining_after_budget_bytes=-50, fits_declared_physical_budget=False),
            lambda b: b["capacity_preview"]["volumes"]["drive_D"].update(free_bytes=None),
            lambda b: b["storage"].update(fixed_all_reserves=1),
            lambda b: b["provenance"]["tool"].update(sha256="0"*64)]
        for mutate in mutations:
            with self.subTest(mutation=mutate), tempfile.TemporaryDirectory() as tmp:
                f = self.fixture(tmp); changed = deepcopy(f.fresh_budget); mutate(changed)
                changed["storage_sha256"] = refresh.digest(changed["storage"])
                previous = f.budget_binding; f.budget_binding = write(f.r["budget"], changed)
                f.term["new_budget"] = f.budget_binding
                f.term["input_bindings"] = [f.budget_binding if item == previous else item for item in f.term["input_bindings"]]
                with self.assertRaises((ValueError, TypeError)): self.validate(f)

    def test_future_time_or_foreign_inventory_and_output_paths_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.fixture(tmp)
            with self.assertRaises(ValueError):
                s.validate_refresh_terminal(f.term, f.terminal_binding, f.budget_binding, f.context,
                    f.refresh, f.m, f.old, f.guard, datetime(2019, 1, 1, tzinfo=timezone.utc))
            wrong = write(f.root / "foreign_budget.json", f.fresh_budget)
            with self.assertRaisesRegex(ValueError, "exact actual refresh budget"):
                s.existing_refresh_paths(f.terminal_binding, wrong, f.context, v)
            changed = deepcopy(f.term); changed["new_inventory"]["path"] = f.q["inventory"].as_posix()
            with self.assertRaises(ValueError): self.validate(f, changed)

    def test_original_profile_and_all_ten_overlay_payloads_still_match(self):
        profile, _ = legacy.candidate_inputs(base_real, prior_real)
        self.assertEqual(len(profile["overlays"]), 10)
        self.assertEqual((profile["source_count"], profile["scanner_count"], profile["flight_count"]), (308, 185, 277))
        self.assertEqual(profile["source_digest"], base_real.PROFILE["source_digest"])

    def test_history_composes_original_readonly_helpers_and_never_reexecutes(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.fixture(tmp); archive=f.root / "executed47.py"
            archive.write_text("synthetic_preserved_source = True\n", encoding="utf8")
            before={p:p.read_bytes() for p in f.root.rglob("*") if p.is_file()}
            collector=SimpleNamespace(review_library=lambda: v)
            fake_m=SimpleNamespace(new_paths=lambda old: f.p, EXECUTED_SOURCE_ARCHIVE=archive,
                EXECUTED_SOURCE_SHA=binding(archive)["sha256"], REGISTERED_INPUTS={"collector":{"path":"SYNTHETIC","sha256":"SYNTHETIC"}},
                closure_audit=Mock(return_value=(f.context["audit"],f.context["inputs"])), fixed_module=lambda *args: collector,
                after28_inputs=lambda version, previous: previous, AFTER28_TERMINAL=f.m.AFTER28_TERMINAL,
                validate_after28_terminal=Mock(return_value=f.context["proof"]), verify_after28_products=Mock(return_value=f.context["reused"]),
                CLOSURE_STATUS=f.context["audit"]["status"], run=Mock(side_effect=AssertionError("No measurement run")))
            fake_refresh=SimpleNamespace(MEASUREMENT=refresh.MEASUREMENT, continuation_paths=refresh.continuation_paths,
                CONTINUATION=f.refresh.CONTINUATION, validate_continuation=Mock(),
                OLD_BUDGET_SHA=f.context["old_budget_binding"]["sha256"], R0_SHA=f.context["R0_binding"]["sha256"],
                negative_budget=refresh.negative_budget, within_created=refresh.within_created,
                DerivedArtifacts=Mock(return_value=f.context["derived"]), run=Mock(side_effect=AssertionError("No capacity refresh run")))
            result=s.audit_history(fake_refresh,fake_m,f.old,base_real,f.guard)
            self.assertEqual(result["first"]["returncode"],2); self.assertEqual(result["continued"]["returncode"],2)
            fake_m.closure_audit.assert_called_once(); fake_m.validate_after28_terminal.assert_called_once()
            fake_m.verify_after28_products.assert_called_once(); fake_refresh.validate_continuation.assert_called_once()
            fake_m.run.assert_not_called(); fake_refresh.run.assert_not_called()
            for path, content in before.items(): self.assertEqual(path.read_bytes(),content)

    def run_fake_stage(self, f, *, action="execute", drift=None, conflict=False, stage_override=None, receipt_override=None):
        stage = stage_override or f.root / "fresh_stage"; receipt = receipt_override or f.root / "fresh_stage_receipt"
        if conflict: stage.mkdir()
        class FakeBase:
            def __getattr__(self, name): return getattr(base_real, name)
            @contextmanager
            def linux_idle_guard(self): yield f.guard
            def prepare(self, paths, profile):
                if paths["stage"].exists() or paths["receipt"].exists(): raise ValueError("Synthetic output conflict")
                if drift == "prepare": Path(f.context["derived"].bindings[0]["path"]).write_bytes(b"CHANGED")
                return {"paths": paths, "profile": profile}
            def summary(self, prepared): return {"kind": "SYNTHETIC_PREPARED_NO_NATIVE"}
            def execute(self, prepared):
                prepared["paths"]["receipt"].mkdir()
                result = {"status": "SYNTHETIC_EXECUTE_ONLY_NO_NATIVE"}
                write(prepared["paths"]["receipt"] / "outcome.json", result)
                if drift == "execute": Path(f.context["derived"].bindings[0]["path"]).write_bytes(b"CHANGED")
                return result
        fake_base = FakeBase()
        fake_legacy = SimpleNamespace(**{key: getattr(legacy, key) for key in (
            "BASE", "BASE_SHA", "PRIOR", "PRIOR_SHA", "BUNDLE", "BUNDLE_SHA", "PROFILE_PATH", "PROFILE_SHA", "CONTRACT", "ROOT",
            "candidate_inputs", "production_paths")}, fixed_module=lambda path, pin: fake_base if path == legacy.BASE else prior_real)
        f.m.OLD08="FIXTURE_OLD"; f.m.OLD08_SHA="FIXTURE_SHA"; f.m.fixed_module=lambda *args: f.old
        f.refresh.MEASUREMENT=refresh.MEASUREMENT; f.refresh.MEASUREMENT_SHA=refresh.MEASUREMENT_SHA
        f.refresh.fixed_module=lambda *args: f.m
        registered={"capacity_refresh_terminal": f.terminal_binding, "capacity_refresh_budget": f.budget_binding}
        with patch.object(s, "PRODUCTION_ENABLED", True), patch.object(s, "REGISTERED_INPUTS", registered), \
             patch.object(sys, "platform", "linux"), patch.dict(s.os.environ, {"WSL_DISTRO_NAME": "UAVHumble22"}), \
             patch.object(s, "fixed_module", side_effect=lambda path, pin: fake_legacy if path == s.LEGACY else f.refresh), \
             patch.object(s, "audit_history", return_value=f.context):
            return s.run_registered(execute_requested=action=="execute", reviewed_source_sha256=binding(Path(s.__file__))["sha256"],
                stage_directory=stage, receipt_directory=receipt)

    def test_fake_preflight_creates_nothing_and_execute_preserves_failed_evidence(self):
        for action in ("preflight", "execute"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as tmp:
                f = self.fixture(tmp); before={p:p.read_bytes() for p in f.root.rglob("*") if p.is_file()}
                result=self.run_fake_stage(f, action=action)
                for path, content in before.items(): self.assertEqual(path.read_bytes(), content)
                if action == "preflight":
                    self.assertIn("PREFLIGHT_ONLY", result["status"])
                    self.assertFalse((f.root / "fresh_stage_receipt").exists())
                    self.assertFalse((f.root / "fresh_stage_receipt.admission.json").exists())
                else:
                    admission=json.loads((f.root / "fresh_stage_receipt.admission.json").read_text())
                    self.assertEqual(admission["original_execution_window"]["returncode"], 2)
                    self.assertEqual(admission["continuation_execution_window"]["returncode"], 2)
                    self.assertEqual(admission["capacity_refresh_execution_window"]["returncode"], 0)
                    self.assertFalse(admission["capacity_currently_revalidated"])

    def test_prepare_and_execute_derived_drift_and_existing_outputs_stop_truthfully(self):
        for drift in ("prepare", "execute", None):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as tmp:
                f = self.fixture(tmp)
                with self.assertRaisesRegex(ValueError, "derived artifact changed|output conflict|Fresh explicit staging output"):
                    self.run_fake_stage(f, drift=drift, conflict=drift is None)
                admission=f.root / "fresh_stage_receipt.admission.json"
                if drift == "execute":
                    self.assertTrue(admission.exists())
                    outcome=json.loads((f.root / "fresh_stage_receipt.admission.driver_outcome.json").read_text())
                    self.assertEqual(outcome["status"], "FAIL_PROFILE02_STAGING_RETAINED")
                else: self.assertFalse(admission.exists())

    def test_staging_and_sidecar_outputs_cannot_enter_reused_evidence_trees(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.fixture(tmp)
            protected = [f.p["receipt"], f.q["receipt"], f.r["receipt"], f.p["tools"], f.p["sizes"], f.p["calibration"], f.p["budget"].parent]
            for tree in protected:
                for key in ("stage", "receipt"):
                    paths={"stage":f.root / "new_stage", "receipt":f.root / "new_receipt"}
                    paths[key]=tree / "unsafe_new_output"
                    with self.subTest(tree=tree,key=key),self.assertRaisesRegex(ValueError,"protected evidence/source"):
                        s.validate_stage_outputs(paths,f.context,f.terminal_binding)
                    self.assertFalse(paths[key].exists())
            for suffix in (".admission.json", ".admission.driver_outcome.json"):
                receipt=f.root / ("sidecar_"+str(len(suffix)))
                reserved=receipt.with_name(receipt.name+suffix); reserved.write_bytes(b"SYNTHETIC_RESERVED")
                with self.assertRaisesRegex(ValueError,"Fresh explicit staging output or sidecar"):
                    s.validate_stage_outputs({"stage":f.root / "new_stage", "receipt":receipt},f.context,f.terminal_binding)
            receipt=f.root / "independent_receipt"
            for stage in (receipt.with_name(receipt.name+".admission.json"),
                          receipt.with_name(receipt.name+".admission.driver_outcome.json"),receipt / "nested_stage"):
                with self.subTest(alias_stage=stage), self.assertRaisesRegex(ValueError,"mutually independent"):
                    s.validate_stage_outputs({"stage":stage,"receipt":receipt},f.context,f.terminal_binding)
        for key in ("stage", "receipt"):
            with self.subTest(full_run_output=key), tempfile.TemporaryDirectory() as tmp:
                f=self.fixture(tmp)
                options={"stage_override":f.p["tools"] / "unsafe_stage_source"} if key == "stage" else {
                    "receipt_override":f.r["receipt"] / "unsafe_stage_receipt"}
                with self.assertRaisesRegex(ValueError,"protected evidence/source"):
                    self.run_fake_stage(f,**options)


if __name__ == "__main__":
    unittest.main(verbosity=2)
