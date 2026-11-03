"""Small synthetic refresh fixtures: no WSL, native child, bag or model access."""
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
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("capacity_refresh_fixtures", HERE / "refresh_capacity_after28.py")
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
m = s.fixed_module(s.MEASUREMENT, s.MEASUREMENT_SHA)
old_real = m.fixed_module(m.OLD08, m.OLD08_SHA)
vpath = m.ROOT / "tools/staging/final55_offline_overlay_profile03_20261103/validate_owner_closure.py"
v = s.fixed_module(vpath, hashlib.sha256(vpath.read_bytes()).hexdigest())


def binding(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    old_real.write_new(path, value)
    return binding(path)


class RefreshTests(unittest.TestCase):
    def test_derived_size_limit_precedes_open_and_growth_stops_after_sentinel(self):
        class FakePath:
            def __init__(self, size):
                self.size = size; self.read_requests = []; self.opened = False
            def is_file(self): return True
            def is_symlink(self): return False
            def stat(self):
                return types.SimpleNamespace(st_dev=1, st_ino=1, st_size=self.size, st_mtime_ns=1)
            @contextmanager
            def open(self, mode):
                self.opened = True
                owner = self
                class GrowingStream:
                    def read(self, count):
                        owner.read_requests.append(count)
                        return b"x" * count
                yield GrowingStream()
        oversized = FakePath(s.DERIVED_MAX_BYTES+1)
        with self.assertRaisesRegex(ValueError, "independent16MiB limit"):
            s.DerivedArtifacts._hash(oversized, "0"*64)
        self.assertFalse(oversized.opened)
        growing = FakePath(3)
        with self.assertRaisesRegex(ValueError, "grew beyond its initial size"):
            s.DerivedArtifacts._hash(growing, "0"*64)
        self.assertEqual(growing.read_requests, [4])

    def test_default_has_no_import_read_or_execution_and_review_precedes_helper_loading(self):
        with patch.object(s, "fixed_module", side_effect=AssertionError("Must remain inert")), redirect_stdout(io.StringIO()):
            self.assertEqual(s.main([]), 0)
            self.assertEqual(s.main(["--execute"]), 2)
        with patch.object(sys, "platform", "linux"), patch.dict(s.os.environ, {"WSL_DISTRO_NAME": "UAVHumble22"}), \
             patch.object(s, "fixed_module", side_effect=AssertionError("Must check review first")):
            with self.assertRaisesRegex(ValueError, "reviewed capacity-refresh source SHA"):
                s.run(receipt=Path("/unused"), reviewed_source_sha256="wrong")

    def fixture(self, tmp, *, new_free=150, storage_drift=False):
        root = Path(tmp).resolve(); frozen = root / "frozen"; frozen.mkdir()
        receipts = root / "validation"; receipts.mkdir()
        first_receipt = receipts / "old"; first_receipt.mkdir()
        p = {"frozen": frozen, "receipt": first_receipt, "inventory": first_receipt / "never_created.json",
             "tools": root / "tools", "sizes": root / "sizes", "calibration": root / "calibration",
             "budget": root / "old_budget/budget.json", "core": root / "core.json", "extension": root / "extension.json",
             "idle": root / "idle.sh"}
        for name in ("tools", "sizes", "calibration"):
            p[name].mkdir()
        q = s.continuation_paths(p); q["receipt"].mkdir()
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        t = lambda n: (start + timedelta(seconds=n)).isoformat()
        guard = {"machine_lock": "synthetic_only", "blockers": []}
        core = write(p["core"], {"plan_sha256": "core_plan"})
        extension = write(p["extension"], {"plan_sha256": "extension_plan"})
        closure = {"kind": "SYNTHETIC_CLOSURE", "created_utc": t(0)}
        closure_binding = write(first_receipt / "closure.json", closure)
        inv = {"schema_version": 1, "kind": "RELIABILITY_V4_PHYSICAL_STORAGE_INVENTORY", "created_utc": t(6),
            "evidence_scope": "METADATA_ONLY_NOT_FORMAL_ADMISSION", "volumes": [
                {"mount": "/mnt/d", "windows_volume_id": "actual_synthetic_volume", "free_bytes": 50}],
            "vhd_host": {"distribution": "UAVHumble22", "path": "/mnt/d/synthetic/ext4.vhdx"}}
        inv_binding = write(q["inventory"], inv)
        storage = {"vhd_host": {"volume": "drive_D"}, "cells": [
            {"matrix": matrix, "target_class": cls, "condition": group}
            for matrix, groups in (("core", old_real.CORE_GROUPS), ("extension", old_real.EXTENSION_GROUPS))
            for cls in ("person", "car") for group in groups], "unchanged_all_reserves": 123}
        budget = {"schema_version": 1, "kind": "RELIABILITY_V4_STORAGE_BUDGET_ASSEMBLY_NOT_ADMISSION",
            "admission_performed": False, "created_utc": t(17), "storage": storage, "storage_sha256": s.digest(storage),
            "provenance": {"development_plans": {"core": core, "extension": extension},
                "assumptions": {"sha256": old_real.ASSUMPTIONS_SHA}, "physical_inventory": inv_binding,
                "small_inputs_sha256": {inv_binding["path"]: inv_binding["sha256"], core["path"]: core["sha256"]}},
            "capacity_preview": {"scope": "fixed_scope", "scheduled_slots": 280,
                "ext4_logical_free_bytes": 1000, "fits_declared_logical_budget": True,
                "volumes": {"drive_D": {"mount": "/mnt/d", "windows_volume_id": "actual_synthetic_volume",
                    "free_bytes": 50, "required_bytes": 100, "remaining_after_budget_bytes": -50,
                    "fits_declared_physical_budget": False}}}, "limits": "SYNTHETIC_UNCHANGED"}
        budget_binding = write(p["budget"], budget)
        policy = write(frozen / "policy.json", {"kind": "SYNTHETIC_POLICY"})
        provenance = {}
        for cls in ("person", "car"):
            directory = p["calibration"] / (cls + "_export"); directory.mkdir()
            arrays = write(directory / "arrays.json", {"synthetic": cls})
            sidecars = {name: write(directory / name, {"synthetic": name})["sha256"] for name in s.SIDECARS}
            audit = {"scope": "DEVELOPMENT_ONLY", "kind": "DEVELOPMENT_ONLY_FILE_HASH_SOURCE_BOUND_EXPORT_AND_ONLINE_AUDIT",
                "sidecar_sha256": sidecars, "export_source_hashes": {}}
            audit["evidence_sha256"] = s.digest(audit)
            provenance[cls] = {"slot_id": cls + "_stage1_velocity_seed004", "arrays": arrays,
                "terminal_record": write(root / (cls + "_terminal.json"), {"synthetic": cls}),
                "recording_evidence": {name: write(root / cls / name, {"synthetic": name})
                    for name in ("run_config.json", "bag_integrity.json")}, "verified_export_evidence": audit}
        candidate = {"kind": "RELIABILITY_V4_DEVELOPMENT_CALIBRATION", "status": "CANDIDATE_NOT_REGISTERED",
            "scope": "DEVELOPMENT_ONLY", "created_utc": t(14), "classes": {"person": {}, "car": {}},
            "provenance": provenance, "development_plan": {**core, "plan_sha256": "core_plan"},
            "source_hashes": {}, "policy": {"path": "policy.json", "sha256": policy["sha256"]}}
        candidate_binding = write(p["calibration"] / "R0_candidate.json", candidate)
        first = {"started_utc": t(1), "finished_utc": t(3), "returncode": 2,
            "errors": [{"error": "Refused: Refusing large input"}], "steps": [], "closure_audit": closure_binding}
        first_binding = write(first_receipt / "terminal.json", first)
        continued = {"started_utc": t(4), "finished_utc": t(20), "returncode": 2,
            "errors": [{"utc": t(19), "error": "ValueError: " + s.CAPACITY_ERROR}], "steps": [
                {"started_utc": t(4), "finished_utc": t(5)}, {"started_utc": t(5), "finished_utc": t(7)},
                {}, {}, {"started_utc": t(13), "finished_utc": t(15)}, {"started_utc": t(16), "finished_utc": t(18)}],
            "closure_audit": closure_binding, "input_bindings": [budget_binding, candidate_binding]}
        for cls, row in zip(("person", "car"), continued["steps"][2:4]):
            path = q["receipt"] / (cls + ".stdout.log")
            write(path, {"status": "PASS", "scope": "DEVELOPMENT_ONLY",
                "online_equivalence_status": "PASS", "native_state_audit_status": "PASS",
                "output": str(p["calibration"] / (cls + "_export"))})
            row["stdout"] = str(path)
        continued_binding = write(q["receipt"] / "terminal.json", continued)
        archive = root / "archive.py"; archive.write_text("fixture_only = True\n", encoding="utf8")
        calls = []
        @contextmanager
        def idle_guard():
            yield guard
        base = types.SimpleNamespace(binding=binding, linux_idle_guard=idle_guard)
        def child(paths, state, name, argv, inputs, *, environment):
            inputs.unchanged(); calls.append((name, list(map(str, argv))))
            row = {"id": name, "command": list(map(str, argv)), "started_utc": old_real.utc()}
            state["steps"].append(row)
            stdout = paths["receipt"] / (name + ".stdout.log")
            if name == "native_idle":
                write(stdout, {"kind": "ACTUAL_CURRENT_NATIVE_PROCESS_QUERY_ONLY", "matching_processes": []})
            elif name == "physical_inventory":
                fresh = deepcopy(inv); fresh["created_utc"] = old_real.utc(); fresh["volumes"][0]["free_bytes"] = new_free
                write(paths["inventory"], fresh); stdout.write_bytes(b"synthetic inventory\n")
            elif name == "full280_budget":
                fresh = deepcopy(budget); fresh["created_utc"] = old_real.utc()
                fresh["provenance"]["physical_inventory"] = binding(paths["inventory"])
                mapping = fresh["provenance"]["small_inputs_sha256"]
                mapping.pop(inv_binding["path"]); mapping[str(paths["inventory"])] = binding(paths["inventory"])["sha256"]
                volume = fresh["capacity_preview"]["volumes"]["drive_D"]
                volume.update(free_bytes=new_free, remaining_after_budget_bytes=new_free-100, fits_declared_physical_budget=new_free >= 100)
                if storage_drift:
                    fresh["storage"]["unchanged_all_reserves"] -= 1; fresh["storage_sha256"] = s.digest(fresh["storage"])
                write(paths["budget"], fresh); stdout.write_bytes(b"synthetic budget\n")
            else:
                raise AssertionError("Forbidden extra command: " + name)
            row.update(returncode=0, finished_utc=old_real.utc())
            inputs.unchanged()
            return stdout
        def workflow(paths):
            return [(name, ["ORIGINAL_FACTORY", name, str(paths["inventory"]), str(paths["budget"])]) for name in
                ("measure_actual28", "physical_inventory", "person_velocity_export", "car_velocity_export", "R0_candidate", "full280_budget")]
        old = types.SimpleNamespace(fixed_module=lambda *args: base, BASE="synthetic_base", BASE_SHA="synthetic",
            COMMIT="synthetic_commit", workflow_commands=workflow,
            positive_budget=old_real.positive_budget, sha=old_real.sha, utc=old_real.utc, write_new=old_real.write_new,
            linux_identity=lambda pid: {"pid": pid, "boot_id": "synthetic", "start_ticks": 1},
            child_step=child, bound_generated=old_real.bound_generated)
        collector = types.SimpleNamespace(review_library=lambda: v)
        fake_m = types.SimpleNamespace(OLD08="synthetic_old", OLD08_SHA="synthetic", REGISTERED_INPUTS={
                "collector": {"path": "synthetic_collector", "sha256": "synthetic"}},
            fixed_module=lambda path, pin: old if path == "synthetic_old" else collector,
            new_paths=lambda _: p, EXECUTED_SOURCE_ARCHIVE=archive, EXECUTED_SOURCE_SHA=binding(archive)["sha256"],
            closure_audit=lambda *args: (closure, v.Inputs(v.local_small_read)), after28_inputs=m.after28_inputs,
            AFTER28_TERMINAL=first_binding, validate_after28_terminal=lambda *args: {"synthetic_proof": True},
            verify_after28_products=lambda *args: {"synthetic_reuse": True})
        return types.SimpleNamespace(root=root, p=p, q=q, calls=calls, fake_m=fake_m, budget=budget, old=old,
            continued=continued, continuation_binding=continued_binding, candidate_binding=candidate_binding,
            budget_binding=budget_binding, receipt=receipts / "refresh", candidate=candidate)

    def execute(self, f):
        source_sha = binding(Path(s.__file__))["sha256"]
        with patch.object(sys, "platform", "linux"), patch.dict(s.os.environ, {"WSL_DISTRO_NAME": "UAVHumble22"}), \
             patch.object(s, "fixed_module", return_value=f.fake_m), patch.object(s, "CONTINUATION", f.continuation_binding), \
             patch.object(s, "OLD_BUDGET_SHA", f.budget_binding["sha256"]), patch.object(s, "R0_SHA", f.candidate_binding["sha256"]), \
             patch.object(s, "validate_continuation"):
            return s.run(receipt=f.receipt, reviewed_source_sha256=source_sha)

    def test_three_actual_fixture_steps_positive_budget_preserves_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.fixture(tmp); before = {path: path.read_bytes() for path in f.root.rglob("*") if path.is_file()}
            result = self.execute(f)
            self.assertEqual(result["returncode"], 0)
            self.assertEqual([x[0] for x in f.calls], ["native_idle", "physical_inventory", "full280_budget"])
            self.assertEqual(len(result["derived_input_bindings"]), 8)
            self.assertFalse(f.p["inventory"].exists())
            self.assertFalse(result["formal_admission"])
            for path, content in before.items():
                self.assertEqual(path.read_bytes(), content, str(path))

    def test_negative_budget_and_changed_storage_stop_with_new_outputs_retained(self):
        for free, drift, reason in ((50, False, s.CAPACITY_ERROR), (150, True, "changed storage/reserves/cells")):
            with self.subTest(free=free, drift=drift), tempfile.TemporaryDirectory() as tmp:
                f = self.fixture(tmp, new_free=free, storage_drift=drift)
                original = f.p["budget"].read_bytes(); result = self.execute(f)
                self.assertEqual(result["returncode"], 2)
                self.assertIn(reason, result["errors"][0]["error"])
                self.assertEqual([x[0] for x in f.calls], ["native_idle", "physical_inventory", "full280_budget"])
                self.assertTrue((f.receipt / "budget.json").is_file())
                self.assertTrue((f.receipt / "terminal.json").is_file())
                self.assertEqual(f.p["budget"].read_bytes(), original)

    def test_derived_drift_and_output_conflict_refuse_before_any_child(self):
        for drift in (True, False):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as tmp:
                f = self.fixture(tmp)
                if drift:
                    (f.p["calibration"] / "car_export/arrays.json").write_text("CHANGED", encoding="utf8")
                else:
                    f.receipt.mkdir()
                with self.assertRaisesRegex(ValueError, "derived export SHA|exclusive external receipt"):
                    self.execute(f)
                self.assertEqual(f.calls, [])

    def test_unknown_or_schema_failure_is_not_an_eligible_negative_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.fixture(tmp)
            for mutate in (lambda b: b.update(storage_sha256="0"*64),
                           lambda b: b["capacity_preview"].update(fits_declared_logical_budget=None),
                           lambda b: b["capacity_preview"]["volumes"]["drive_D"].update(free_bytes=None)):
                changed = deepcopy(f.budget); mutate(changed)
                with self.assertRaises((ValueError, TypeError)):
                    s.negative_budget(changed, f.old, binding(f.p["core"]), binding(f.p["extension"]))

    def test_independent_six_step_validation_rejects_other_windows_errors_and_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.fixture(tmp)
            first = json.loads(Path(f.fake_m.AFTER28_TERMINAL["path"]).read_text())
            term = deepcopy(f.continued); proof = {"proof": True}; reused = {"reused": True}
            identity = {"pid": 123, "start_ticks": 123, "boot_id": "f79204a4-99cd-42cf-b886-aa905b1cac6a"}
            term.update(scope="CONTINUATION_SCOPE", status="STOPPED_AFTER28_CONTINUATION_PARTIAL_OUTPUTS_RETAINED",
                interruptions=[], automatic_retry=False, formal_admission=False, commit=f.old.COMMIT,
                guard={"machine_lock": "fixture", "blockers": []}, actual_original_bindings={},
                source={"path": str(s.MEASUREMENT.resolve()), "sha256": s.MEASUREMENT_SHA},
                original_failure_terminal=f.fake_m.AFTER28_TERMINAL, original_execution_window=s.execution_window(first),
                preserved_executed_source=proof, reused_actual28=reused, owner_identity=identity,
                inventory_output_choice={"original_uncreated_path": str(f.p["inventory"]), "actual_new_path": str(f.q["inventory"]),
                    "reason": "Keep the entire original stopped receipt unchanged; calibration and budget retain their original uncreated paths."})
            stamp = lambda seconds: (datetime(2020, 1, 1, tzinfo=timezone.utc)+timedelta(seconds=seconds)).isoformat()
            expected = [("native_idle", ["bash", f.p["idle"]])] + f.old.workflow_commands(f.q)[1:]
            term["steps"] = []
            for i, (name, argv) in enumerate(expected):
                row = {"id": name, "command": list(map(str, argv)), "returncode": 0, "pid": 123, "identity": identity,
                    "started_utc": stamp(5+i*2), "finished_utc": stamp(6+i*2)}
                for channel in ("stdout", "stderr"):
                    path = f.q["receipt"] / (name+"."+channel+".log"); path.write_bytes(b"fixture log")
                    row[channel] = str(path)
                term["steps"].append(row)
            term["input_bindings"] = [term["source"], term["closure_audit"], f.fake_m.AFTER28_TERMINAL]
            term["input_bindings"] += [{"path": "/synthetic/%d" % i, "sha256": "0"*64} for i in range(1104)]
            module = types.SimpleNamespace(AFTER28_SCOPE="CONTINUATION_SCOPE", REGISTERED_INPUTS={}, AFTER28_TERMINAL=f.fake_m.AFTER28_TERMINAL)
            class Inputs:
                def read_reference(self, path): return Path(path).read_bytes()
                def bound(self, item): return b""
            args = lambda obj: (obj, first, proof, reused, module, f.old, f.p, f.q, Inputs(), v, term["guard"], datetime.now(timezone.utc))
            s.validate_continuation(*args(term))
            for mutate in (lambda x: x["errors"][0].update(error="Refused: Refusing large input"),
                           lambda x: x["steps"].pop(), lambda x: x["steps"][3].update(returncode=2),
                           lambda x: x["steps"][1].update(command=["OTHER"]),
                           lambda x: x["original_execution_window"].update(returncode=0),
                           lambda x: x["input_bindings"].pop(), lambda x: x["interruptions"].append({"interrupted": True})):
                changed = deepcopy(term); mutate(changed)
                with self.assertRaises(ValueError):
                    s.validate_continuation(*args(changed))


if __name__ == "__main__":
    unittest.main()
