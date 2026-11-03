"""Tiny command/closure/stop contracts; no native command or bag read."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("runner08_small_contracts", Path(__file__).with_name("run_followon08.py"))
s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s)


class Runner08Contracts(unittest.TestCase):
    def budget(self):
        bindings = {label: {"path": "/fixture/" + label, "sha256": label[0] * 64} for label in ("core", "extension")}
        storage = {"cells": [{"matrix": matrix, "target_class": target, "condition": condition}
                    for matrix, groups in (("core", s.CORE_GROUPS), ("extension", s.EXTENSION_GROUPS))
                    for target in ("person", "car") for condition in groups]}
        return {"kind": "RELIABILITY_V4_STORAGE_BUDGET_ASSEMBLY_NOT_ADMISSION", "admission_performed": False,
                "storage": storage, "storage_sha256": s.sha(json.dumps(storage, sort_keys=True, separators=(",", ":")).encode()),
                "provenance": {"development_plans": bindings, "assumptions": {"sha256": s.ASSUMPTIONS_SHA}},
                "capacity_preview": {"scheduled_slots": 280, "fits_declared_logical_budget": True,
                                     "volumes": {"drive_D": {"fits_declared_physical_budget": True}}}}, bindings

    def test_default_and_unarmed_execute_never_read_or_start(self):
        with patch.object(s, "fixed_module", side_effect=AssertionError("No source read")), \
                patch.object(s.subprocess, "Popen", side_effect=AssertionError("No process")), redirect_stdout(io.StringIO()):
            self.assertEqual(s.main([]), 0)
            self.assertEqual(s.main(["--execute"]), 2)
        self.assertFalse(s.EXECUTION_ENABLED)

    def test_fixed_serial_steps_keep_the_two_original_recordings_and_reserves(self):
        p = s.paths()
        steps = s.workflow_commands(p)
        self.assertEqual([name for name, _ in steps], ["measure_actual28", "physical_inventory", "person_velocity_export", "car_velocity_export", "R0_candidate", "full280_budget"])
        for target in ("person", "car"):
            argv = dict(steps)[target + "_velocity_export"]
            self.assertIn(str(p["frozen"] / ("results/reliability_v4_humble54_core12_probe01_" + target + "_stage1_velocity_seed004")), argv)
            self.assertEqual(argv[-2:], ["--output", str(p["calibration"] / (target + "_export"))])
        budget = dict(steps)["full280_budget"]
        self.assertEqual(s.ASSUMPTIONS_SHA, "bc0ef3a6549bb7421b1b6de64c17951c4d71af32114c94a8e4234ad42360b049")
        self.assertEqual(budget[budget.index("--assumptions") + 1], str(p["assumptions"]))
        flat = [str(value).lower() for _, argv in steps for value in argv]
        self.assertFalse(any(value.endswith(("wsl.exe", "colcon", "prepare_and_validate.sh")) for value in flat))
        self.assertEqual(s.COMMIT, "eedd8d9abcd6890b0bd5d0155f76ac08253426b9")

    def test_unknown_or_negative_budget_refuses_without_changing_original(self):
        for value in (None, False, 1):
            budget, bindings = self.budget()
            budget["capacity_preview"]["volumes"]["drive_D"]["fits_declared_physical_budget"] = value
            before = deepcopy(budget)
            with self.assertRaisesRegex(ValueError, "Unknown or negative"):
                s.positive_budget(budget, bindings["core"], bindings["extension"])
            self.assertEqual(budget, before)
        budget, bindings = self.budget()
        s.positive_budget(budget, bindings["core"], bindings["extension"])

    def test_foreign_cells_cannot_replace_measured28_even_if_resealed(self):
        budget, bindings = self.budget()
        budget["storage"]["cells"][0]["condition"] = "wrong_condition"
        budget["storage_sha256"] = s.sha(json.dumps(budget["storage"], sort_keys=True, separators=(",", ":")).encode())
        with self.assertRaisesRegex(ValueError, "exact measured28"):
            s.positive_budget(budget, bindings["core"], bindings["extension"])

    def test_fresh_single_attempt_ignores_distinct_old_outputs_but_rejects_reentry(self):
        with tempfile.TemporaryDirectory(prefix="runner08_fresh_fixture_") as temporary:
            root = Path(temporary)
            p = {name: root / (name + "_followon08") for name in ("receipt", "tools", "sizes", "calibration")}
            p["budget"] = root / "budget_followon08/budget.json"
            (root / "receipt_followon05").mkdir()
            s.fresh_outputs(p)
            p["receipt"].mkdir()
            with self.assertRaisesRegex(ValueError, "no resume"):
                s.fresh_outputs(p)

    def test_publication_fault_after_popen_still_waits_actual_child(self):
        with tempfile.TemporaryDirectory(prefix="runner08_child_fixture_") as temporary:
            p = {"receipt": Path(temporary)}
            state = {"steps": [], "interruptions": []}
            child = SimpleNamespace(pid=123, wait=Mock(return_value=0))
            publish = Mock(side_effect=[None, OSError("SYNTHETIC state failure"), None])
            with patch.object(s.subprocess, "Popen", return_value=child), patch.object(s, "publish_state", publish), patch.object(s, "linux_identity", return_value={"pid": 123}):
                with self.assertRaisesRegex(OSError, "state failure"):
                    s.child_step(p, state, "inert", ["NO_COMMAND"], SimpleNamespace(unchanged=lambda: None), environment={})
            child.wait.assert_called_once()
            self.assertEqual(state["steps"][0]["returncode"], 0)
            self.assertTrue((p["receipt"] / "inert.stdout.log").exists())

    def test_interrupt_waits_original_child_then_stops(self):
        with tempfile.TemporaryDirectory(prefix="runner08_child_fixture_") as temporary:
            p = {"receipt": Path(temporary)}
            state = {"steps": [], "interruptions": []}
            child = SimpleNamespace(pid=123, wait=Mock(side_effect=[KeyboardInterrupt(), 0]))
            with patch.object(s.subprocess, "Popen", return_value=child), patch.object(s, "linux_identity", return_value={"pid": 123}):
                with self.assertRaises(KeyboardInterrupt):
                    s.child_step(p, state, "inert", ["NO_COMMAND"], SimpleNamespace(unchanged=lambda: None), environment={})
            self.assertEqual(child.wait.call_count, 2)
            self.assertEqual(state["steps"][0]["returncode"], 0)
            self.assertEqual(len(state["interruptions"]), 1)

    def test_nonzero_original_step_refuses_and_keeps_logs(self):
        with tempfile.TemporaryDirectory(prefix="runner08_child_fixture_") as temporary:
            p = {"receipt": Path(temporary)}
            state = {"steps": [], "interruptions": []}
            child = SimpleNamespace(pid=123, wait=Mock(return_value=2))
            with patch.object(s.subprocess, "Popen", return_value=child), patch.object(s, "linux_identity", return_value={"pid": 123}):
                with self.assertRaisesRegex(ValueError, "partial output retained"):
                    s.child_step(p, state, "inert", ["NO_COMMAND"], SimpleNamespace(unchanged=lambda: None), environment={})
            self.assertEqual(state["steps"][0]["returncode"], 2)
            self.assertTrue((p["receipt"] / "inert.stderr.log").exists())

    def test_full_chain_cannot_bypass_actual_durable07_zero_handle_closure(self):
        now = ["2020-01-01T00:00:0" + str(index) + "+00:00" for index in range(4)]
        profile_binding = {"path": "/fixture/durable/full_owner_chain_profile.json", "sha256": "a" * 64}
        closure_binding = {"path": "/fixture/durable/terminal.json", "sha256": "b" * 64}
        audit_binding = {"path": "/fixture/durable/owner_chain_audit.json", "sha256": "c" * 64}
        plan_binding = {"path": "/fixture/plan.json", "sha256": "d" * 64}
        audit = {"status": "OWNER_CHAIN_COMPLETED_NOT_ENGINEERING_ADMISSION", "closed_ids": list(map(str, range(16))), "pending_ids": [],
                 "plan": plan_binding, "input_bindings": [plan_binding]}
        closure = {"status": "CLOSURE_AUDIT_COMPLETED", "scope": "DURABLE_WINDOWS_HELD_HANDLE_CLOSURE_ONLY", "errors": [], "returncode": 0,
                   "exit_codes": {"outer": 0, "monitor": 0, "wsl": 0}, "source": {"path": str(s.DURABLE), "sha256": s.DURABLE_SHA},
                   "handles": {name: {"exit_code": 0, "acquired_utc": now[0], "first_exit_observed_utc": now[1], "closed_utc": now[2]}
                               for name in ("outer", "monitor", "wsl")}, "finished_utc": now[3],
                   "future_closure": {"status": "FULL_OWNER_CHAIN_CLOSED_NOT_ENGINEERING_ADMISSION", "pending_ids": [],
                                      "full_profile": profile_binding, "audit": audit_binding}}
        values = {profile_binding["path"]: {}, closure_binding["path"]: closure, audit_binding["path"]: audit, plan_binding["path"]: {}}
        inputs = SimpleNamespace(json=lambda binding: deepcopy(values[binding["path"]]), bound=Mock(), bind_plan_results_alias=Mock())
        chain = SimpleNamespace(validate_chain=Mock(return_value=audit), v=SimpleNamespace(timestamp=lambda value, current: datetime.fromisoformat(value)))
        with patch.object(s, "same_actual", side_effect=lambda module, a, b: str(a).replace("\\", "/") == str(b).replace("\\", "/")):
            s.validate_closure(chain, inputs, profile_binding, closure_binding, {"durable_output": Path("/fixture/durable")})
            for defect in ("nonzero", "unclosed", "partial"):
                changed = deepcopy(closure)
                if defect == "nonzero":
                    changed["exit_codes"]["wsl"] = 2
                elif defect == "unclosed":
                    del changed["handles"]["outer"]["closed_utc"]
                else:
                    changed["future_closure"]["pending_ids"] = ["last"]
                values[closure_binding["path"]] = changed
                with self.assertRaises(ValueError, msg=defect):
                    s.validate_closure(chain, inputs, profile_binding, closure_binding, {"durable_output": Path("/fixture/durable")})


if __name__ == "__main__":
    unittest.main()
