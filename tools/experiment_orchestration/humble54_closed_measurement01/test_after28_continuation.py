"""Windows synthetic continuation checks; no WSL, native child or real bag."""
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
spec = importlib.util.spec_from_file_location("after28_measurement_fixtures", HERE / "run_closed_measurement.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
vpath = s.ROOT / "tools/staging/final55_offline_overlay_profile03_20261103/validate_owner_closure.py"
v = s.fixed_module(vpath, hashlib.sha256(vpath.read_bytes()).hexdigest())
old_real = s.fixed_module(s.OLD08, s.OLD08_SHA)


def binding(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    old_real.write_new(path, obj)
    return binding(path)


class After28Tests(unittest.TestCase):
    def test_actual_executed_archive_and_only_two_original_large_pins(self):
        self.assertEqual(binding(s.EXECUTED_SOURCE_ARCHIVE)["sha256"], s.EXECUTED_SOURCE_SHA)
        self.assertEqual(s.EXECUTED_SOURCE_SHA, "47fcbd727debbdb418bb9fbb1cc6a5abeb9806855f6331709c8590c688232433")
        self.assertEqual(sorted(x["bytes"] for x in s.AFTER28_LARGE_JSON.values()), [3066769, 7660044])
        self.assertEqual(len(s.AFTER28_LARGE_JSON), 2)
        self.assertTrue(all(path.endswith("/physical_identity.json") and "core12_probe01_car_stage" in path
                            for path in s.AFTER28_LARGE_JSON))

    def test_describe_continuation_is_inert_and_execute_requires_reviewed_native_source(self):
        with patch.object(s, "fixed_module", side_effect=AssertionError("No helper import")), redirect_stdout(io.StringIO()):
            self.assertEqual(s.main(["--continue-after28"]), 0)
            self.assertEqual(s.main(["--continue-after28", "--execute"]), 2)
        with patch.object(sys, "platform", "linux"), patch.dict(s.os.environ, {"WSL_DISTRO_NAME": "UAVHumble22"}), \
             patch.object(s, "fixed_module", side_effect=AssertionError("No helper before exact review")):
            with self.assertRaisesRegex(ValueError, "reviewed continuation source SHA"):
                s.run_after28(reviewed_source_sha256="wrong")

    def test_exact_size_exception_survives_bound_and_unchanged_while_other_large_files_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            allowed = root / "original_identity.json"
            raw = b"x" * (2 * 1024**2 + 1)
            allowed.write_bytes(raw)
            fixed = {str(allowed): {"bytes": len(raw), "sha256": binding(allowed)["sha256"]}}
            other = root / "other_identity.json"; other.write_bytes(raw)
            with patch.object(s, "AFTER28_LARGE_JSON", fixed):
                inputs = s.after28_inputs(v, v.Inputs(v.local_small_read))
                self.assertEqual(inputs.bound(binding(allowed)), raw)
                inputs.unchanged()
                with self.assertRaisesRegex(ValueError, "Refusing large input"):
                    inputs.bound(binding(other))
                with patch.object(v, "local_small_read", return_value=raw):
                    with self.assertRaisesRegex(ValueError, "Raw evidence/source SHA differs"):
                        inputs.bound(binding(other))
                wrong = {**binding(allowed), "sha256": "0" * 64}
                with self.assertRaisesRegex(ValueError, "two exact original"):
                    inputs.bound(wrong)
                changed = b"y" + raw[1:]; allowed.write_bytes(changed)
                with self.assertRaisesRegex(ValueError, "identity JSON SHA differs"):
                    inputs.unchanged()
                allowed.write_bytes(raw + b"x")
                with self.assertRaisesRegex(ValueError, "identity JSON size differs"):
                    inputs.bound({"path": str(allowed), "sha256": fixed[str(allowed)]["sha256"]})
                oversized = {str(allowed): {"bytes": 8 * 1024**2 + 1, "sha256": "a" * 64}}
                with patch.object(s, "AFTER28_LARGE_JSON", oversized), self.assertRaisesRegex(ValueError, "size differs"):
                    inputs.read(str(allowed))

    def test_allowlisted_read_keeps_stat_race_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "identity.json"; path.write_bytes(b"fixed")
            before = path.stat(); changed = types.SimpleNamespace(st_dev=before.st_dev, st_ino=before.st_ino,
                st_size=before.st_size, st_mtime_ns=before.st_mtime_ns + 1)
            fixed = {str(path): {"bytes": 5, "sha256": binding(path)["sha256"]}}
            class RacedPath:
                reads = 0
                def is_file(self): return True
                def is_symlink(self): return False
                def resolve(self, strict): return self
                def stat(self):
                    self.reads += 1
                    return before if self.reads == 1 else changed
                def read_bytes(self): return b"fixed"
            with patch.object(s, "AFTER28_LARGE_JSON", fixed), patch.object(v, "local_path", return_value=RacedPath()):
                inputs = s.after28_inputs(v, v.Inputs(v.local_small_read))
                with self.assertRaisesRegex(ValueError, "changed while reading"):
                    inputs.bound({"path": str(path), "sha256": fixed[str(path)]["sha256"]})

    def terminal_fixture(self, tmp):
        root = Path(tmp).resolve(); receipt = root / "original_receipt"; receipt.mkdir()
        p = {"receipt": receipt, "idle": root / "native_idle.sh", "tools": root / "tools"}
        tools = {"tools/tool_%d.py" % i: str(i) * 64 for i in range(5)}
        old = types.SimpleNamespace(COMMIT="fixed_commit", TOOL_PINS=tools, sha=old_real.sha,
            workflow_commands=lambda paths: [("measure_actual28", ["ORIGINAL_MEASURE", str(paths["tools"])])])
        original = types.SimpleNamespace(SCOPE=s.SCOPE, ROOT=s.ROOT, PRODUCTION_ENABLED=True,
            REGISTERED_INPUTS=s.REGISTERED_INPUTS, new_paths=lambda _: p)
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        stamp = lambda sec: (start + timedelta(seconds=sec)).isoformat()
        identity = {"pid": 123, "boot_id": "f79204a4-99cd-42cf-b886-aa905b1cac6a", "start_ticks": 123}
        source = {"path": str(Path(s.__file__).resolve()), "sha256": s.EXECUTED_SOURCE_SHA}
        closure = write(receipt / "audit.json", {"status": "FIXTURE"})
        terminal = {"scope": s.SCOPE, "status": "STOPPED_DIRECT_MEASUREMENT_PARTIAL_OUTPUTS_RETAINED", "returncode": 2,
            "interruptions": [], "errors": [{"utc": stamp(16), "error": "Refused: Refusing large input"}],
            "automatic_retry": False, "formal_admission": False, "commit": old.COMMIT,
            "guard": {"machine_lock": "existing_lock", "blockers": []}, "actual_original_bindings": s.REGISTERED_INPUTS,
            "source": source, "owner_identity": identity, "started_utc": stamp(0), "finished_utc": stamp(17),
            "input_bindings": [source, closure], "closure_audit": closure, "steps": []}
        expected = [("native_idle", ["bash", p["idle"]])]
        expected += [("tool_" + str(i), ["git", "-C", original.ROOT, "show", old.COMMIT + ":" + rel])
                     for i, rel in enumerate(tools)]
        expected += old.workflow_commands(p)
        for i, (label, argv) in enumerate(expected):
            row = {"id": label, "command": list(map(str, argv)), "returncode": 0, "pid": 123,
                   "identity": identity, "started_utc": stamp(i * 2 + 1), "finished_utc": stamp(i * 2 + 2)}
            for channel in ("stdout", "stderr"):
                path = receipt / (label + "." + channel + ".log"); path.write_bytes(b"synthetic only")
                row[channel] = str(path)
            terminal["steps"].append(row)
        class Inputs:
            seen = []
            def read_reference(self, path): return Path(path).read_bytes()
            def bound(self, row): self.seen.append(row); return b""
        return terminal, original, old, p, Inputs(), v, terminal["guard"], \
            {"path": str(s.EXECUTED_SOURCE_ARCHIVE), "sha256": s.EXECUTED_SOURCE_SHA}, start + timedelta(days=1)

    def test_only_exact_original_stop_reuses_seven_steps_and_archives_only_old_self_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.terminal_fixture(tmp); before = deepcopy(args[0])
            proof = s.validate_after28_terminal(*args)
            self.assertEqual(proof["original_step_count"], 7); self.assertEqual(args[0], before)
            self.assertIn(args[-2], args[4].seen)
            self.assertNotIn(args[0]["source"], args[4].seen)

    def test_any_other_stop_missing_or_failed_step_changed_source_or_binding_refuses(self):
        mutations = [lambda x: x.update(returncode=0), lambda x: x["errors"][0].update(error="ValueError: negative budget"),
            lambda x: x["errors"].append(x["errors"][0].copy()), lambda x: x["steps"].pop(),
            lambda x: x["steps"][6].update(returncode=2), lambda x: x["steps"][6].update(command=["OTHER"]),
            lambda x: x["source"].update(sha256="0" * 64), lambda x: x["input_bindings"].pop(0),
            lambda x: x["interruptions"].append({"actual": True}), lambda x: x["steps"][6].update(finished_utc=x["started_utc"])]
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as tmp:
                args = self.terminal_fixture(tmp); mutate(args[0])
                with self.assertRaises((ValueError, v.Refused)):
                    s.validate_after28_terminal(*args)

    def test_complete28_and690_are_all_rebound_using_original_declaration_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); sizes = root / "sizes"; sizes.mkdir()
            receipt = root / "original_receipt"; receipt.mkdir()
            tools = root / "tools"; tools.mkdir()
            receipts = [write(sizes / (str(i) + ".json"), {"original_status": "FAIL" if i == 0 else "PASS"}) for i in range(28)]
            small = {}; originals = []
            for i in range(690):
                path = root / ("small_%03d.json" % i); path.write_bytes(b"{}")
                row = binding(path); small[row["path"]] = {"sha256": row["sha256"], "bag_metadata": False}; originals.append(row)
            pins = {}
            for i in range(5):
                rel = "tool_%d.py" % i; payload = ("# fake tool%d" % i).encode()
                (tools / rel).write_bytes(payload); pins[rel] = binding(tools / rel)["sha256"]
                (receipt / ("tool_%d.stdout.log" % i)).write_bytes(payload)
            summary = {"planned_count": 28, "measured_count": 28, "payload_content_reads": False,
                "capacity_admission_performed": False, "receipts": receipts, "small_input_bindings": small}
            summary_binding = write(sizes / "summary.json", summary)
            allowed = {row["path"]: {"bytes": 2, "sha256": row["sha256"]} for row in originals[:2]}
            old = types.SimpleNamespace(TOOL_PINS=pins)
            paths = {"sizes": sizes, "tools": tools, "receipt": receipt}
            with patch.object(s, "AFTER28_SUMMARY_SHA", summary_binding["sha256"]), patch.object(s, "AFTER28_LARGE_JSON", allowed):
                inputs = s.after28_inputs(v, v.Inputs(v.local_small_read))
                result = s.verify_after28_products(old, paths, {"input_bindings": [summary_binding]}, inputs, v)
                self.assertEqual(result["verified_receipts"], 28)
                self.assertEqual(result["verified_small_input_bindings"], 690)
                self.assertTrue(all(v.path_key(row["path"]) in inputs.seen for row in originals + receipts))
                Path(originals[-1]["path"]).write_bytes(b"[]")
                with self.assertRaisesRegex(v.Refused, "Evidence changed during validation"):
                    inputs.unchanged()

    def continuation_fixture(self, tmp, negative):
        root = Path(tmp).resolve(); receipt = root / "original_receipt"; receipt.mkdir()
        p = {"receipt": receipt, "tools": root / "tools", "sizes": root / "sizes", "calibration": root / "calibration",
            "budget": root / "budget/budget.json", "inventory": receipt / "physical_inventory.json",
            "frozen": root / "frozen", "idle": root / "idle.sh", "core": root / "core.json", "extension": root / "extension.json"}
        for label in ("core", "extension"): write(p[label], {"label": label})
        audit = {"status": s.CLOSURE_STATUS, "created_utc": "2020-01-01T00:00:00+00:00"}
        closure = write(receipt / "full16_closure_audit.json", audit)
        new_audit = {**audit, "created_utc": "2020-01-01T00:00:03+00:00"}
        terminal = {"closure_audit": closure, "started_utc": "2020-01-01T00:00:01+00:00",
            "finished_utc": "2020-01-01T00:00:02+00:00", "returncode": 2,
            "errors": [{"error": "Refused: Refusing large input"}], "steps": [{"id": str(i)} for i in range(7)]}
        terminal_binding = write(receipt / "terminal.json", terminal)
        calls = []
        @contextmanager
        def guard():
            calls.append("guard_enter")
            try: yield {"machine_lock": "EXISTING_LOCK", "blockers": []}
            finally: calls.append("guard_exit")
        base = types.SimpleNamespace(linux_idle_guard=guard, binding=binding)
        commands = lambda paths: [("measure_actual28", ["NEVER_INVOKE_MEASURE"])] + [(label, [label, str(paths["inventory"])])
            for label in ("physical_inventory", "person_velocity_export", "car_velocity_export", "R0_candidate", "full280_budget")]
        def child(paths, state, label, argv, inputs, **kwargs):
            calls.append(label)
            row = {"id": label, "command": list(map(str, argv)), "returncode": 0}; state["steps"].append(row)
            stdout = paths["receipt"] / (label + ".stdout.log")
            if label == "native_idle": result = {"kind": "ACTUAL_CURRENT_NATIVE_PROCESS_QUERY_ONLY", "matching_processes": []}
            elif label == "physical_inventory":
                result = {"kind": "RELIABILITY_V4_PHYSICAL_STORAGE_INVENTORY", "evidence_scope": "METADATA_ONLY_NOT_FORMAL_ADMISSION", "volumes": ["fixture"]}
                write(paths["inventory"], result)
            elif label.endswith("_velocity_export"): result = {"status": "PASS"}
            elif label == "R0_candidate":
                result = {"status": "CANDIDATE_NOT_REGISTERED", "scope": "DEVELOPMENT_ONLY", "classes": {"person": {}, "car": {}}}
                write(p["calibration"] / "R0_candidate.json", result)
            else:
                storage = {"cells": [{"matrix": matrix, "target_class": cls, "condition": condition}
                    for matrix, groups in (("core", old_real.CORE_GROUPS), ("extension", old_real.EXTENSION_GROUPS))
                    for cls in ("person", "car") for condition in groups]}
                result = {"kind": "RELIABILITY_V4_STORAGE_BUDGET_ASSEMBLY_NOT_ADMISSION", "admission_performed": False,
                    "storage": storage, "storage_sha256": old_real.sha(json.dumps(storage, sort_keys=True, separators=(",", ":")).encode()),
                    "provenance": {"development_plans": {label: binding(p[label]) for label in ("core", "extension")},
                        "assumptions": {"sha256": old_real.ASSUMPTIONS_SHA}, "small_inputs_sha256": {}},
                    "capacity_preview": {"scheduled_slots": 280, "fits_declared_logical_budget": True,
                        "volumes": {"drive_D": {"fits_declared_physical_budget": not negative}}}}
                write(p["budget"], result)
            write(stdout, result)
            return stdout
        old = types.SimpleNamespace(fixed_module=lambda *args: base, workflow_commands=commands, child_step=child,
            bound_generated=old_real.bound_generated, positive_budget=old_real.positive_budget, utc=old_real.utc,
            write_new=old_real.write_new, COMMIT=old_real.COMMIT, linux_identity=lambda pid: {"pid": pid},
            BASE="FAKE_BASE_NEVER_EXECUTED", BASE_SHA="FAKE_BASE_SHA")
        collector = types.SimpleNamespace(review_library=lambda: v)
        def module(path, digest): return old if Path(path) == s.OLD08 else collector
        return p, terminal_binding, new_audit, calls, module

    def test_only_actual_remaining_five_workflow_steps_follow_fresh_idle_original_window_stays_failed(self):
        for negative in (False, True):
            with self.subTest(negative=negative), tempfile.TemporaryDirectory() as tmp:
                p, terminal_binding, audit, calls, module = self.continuation_fixture(tmp, negative)
                before = {str(x): x.read_bytes() for x in p["receipt"].iterdir()}
                reviewed = hashlib.sha256(Path(s.__file__).read_bytes()).hexdigest()
                with patch.object(sys, "platform", "linux"), patch.dict(s.os.environ, {"WSL_DISTRO_NAME": "UAVHumble22"}), \
                     patch.object(s, "fixed_module", side_effect=module), patch.object(s, "new_paths", return_value=p), \
                     patch.object(s, "closure_audit", return_value=(audit, v.Inputs(v.local_small_read))), \
                     patch.object(s, "AFTER28_TERMINAL", terminal_binding), \
                     patch.object(s, "validate_after28_terminal", return_value={"original_failure_preserved": True}), \
                     patch.object(s, "verify_after28_products", return_value={"verified_receipts": 28, "verified_small_input_bindings": 690}) as reuse:
                    state = s.run_after28(reviewed_source_sha256=reviewed)
                self.assertEqual(calls, ["guard_enter", "native_idle", "physical_inventory", "person_velocity_export",
                    "car_velocity_export", "R0_candidate", "full280_budget", "guard_exit"])
                self.assertEqual(reuse.call_count, 1)
                self.assertEqual(len(state["steps"]), 6)
                self.assertEqual(len(state["original_execution_window"]["steps"]), 7)
                self.assertEqual(state["original_execution_window"]["returncode"], 2)
                self.assertEqual(state["returncode"], 2 if negative else 0)
                if negative:
                    self.assertIn("Unknown or negative physical/logical", state["errors"][0]["error"])
                self.assertFalse(state["formal_admission"]); self.assertFalse(state["automatic_retry"])
                self.assertTrue(p["budget"].is_file())
                self.assertFalse(p["inventory"].exists())
                self.assertEqual({str(x): x.read_bytes() for x in p["receipt"].iterdir()}, before)
                new_receipt = p["receipt"].with_name(p["receipt"].name + "_continue_after28_01")
                self.assertTrue((new_receipt / "physical_inventory.json").is_file())
                self.assertEqual(json.loads((new_receipt / "terminal.json").read_text(encoding="utf-8")), state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
