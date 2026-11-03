"""Pure Windows contracts; never start WSL, a flight or the real owner."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile
import unittest
from unittest.mock import Mock, patch


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


ROOT = Path(__file__).resolve().parents[3]
g = module("registered05_gate", Path(__file__).with_name("run_registered05.py"))
w = module("registered05_outer", ROOT / "tools/experiment_orchestration/humble54_probe02_windows_owner05/start_owner05.py")


class GateContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.plan_path = Path(self.tmp.name) / "plan.json"
        self.plan_path.write_text("{}", encoding="utf8")
        self.plan_patch = patch.object(g, "PLAN", self.plan_path)
        self.plan_patch.start()
        self.addCleanup(self.plan_patch.stop)
        self.plan = {"plan_sha256": "2" * 64, "trials": [{"id": "slot" + str(n)} for n in range(16)]}
        self.audit = {"status": "BOUND_PRESERVED_PREFIX_CHAIN",
                      "plan": {"path": str(self.plan_path), "sha256": g.PINS["plan"], "plan_sha256": self.plan["plan_sha256"]},
                      "after_slot": "slot1", "closed_ids": ["slot0", "slot1"],
                      "pending_ids": ["slot" + str(n) for n in range(2, 16)],
                      "closed": [{"id": "slot" + str(n), "marker": {"sha256": "a" * 64},
                                  "terminal": {"sha256": "b" * 64}} for n in range(2)],
                      "input_bindings": [{"path": "fixture", "sha256": "c" * 64}]}

    def test_accepts_only_the_exact_existing_contiguous_prefix(self):
        bound = g.check_chain_result(self.audit, self.plan)
        self.assertEqual(bound["after_slot"], "slot1")
        self.assertEqual(len(bound["pending_ids"]), 14)
        for defect in ("wrong_plan", "gap", "after", "pending", "duplicate_plan_slot", "empty_bindings", "full_chain_status"):
            with self.subTest(defect=defect):
                audit, plan = deepcopy(self.audit), deepcopy(self.plan)
                if defect == "wrong_plan":
                    audit["plan"]["sha256"] = "0" * 64
                elif defect == "gap":
                    audit["closed_ids"][1] = "slot2"
                elif defect == "after":
                    audit["after_slot"] = "slot0"
                elif defect == "pending":
                    audit["pending_ids"].reverse()
                elif defect == "duplicate_plan_slot":
                    plan["trials"][-1]["id"] = "slot0"
                elif defect == "empty_bindings":
                    audit["input_bindings"] = []
                else:
                    audit["status"] = "OWNER_CHAIN_COMPLETED_NOT_ENGINEERING_ADMISSION"
                with self.assertRaises(ValueError):
                    g.check_chain_result(audit, plan)

    def test_zero_prefix_is_not_a_registered_continuation(self):
        audit = deepcopy(self.audit)
        audit.update(closed_ids=[], closed=[], pending_ids=[row["id"] for row in self.plan["trials"]], after_slot=None)
        with self.assertRaisesRegex(ValueError, "contiguous original closed prefix"):
            g.check_chain_result(audit, self.plan)

    def test_plan_comparison_uses_chain_localizer_for_linux_drive_reference(self):
        audit = deepcopy(self.audit)
        audit["plan"]["path"] = r"D:\fixture\closed\plan.json"
        normalized = PurePosixPath("/mnt/d") / PureWindowsPath(audit["plan"]["path"]).relative_to("D:/").as_posix()
        self.assertEqual(str(normalized), "/mnt/d/fixture/closed/plan.json")
        localizer = Mock(return_value=self.plan_path)
        self.assertEqual(g.check_chain_result(audit, self.plan, local_path=localizer)["after_slot"], "slot1")
        localizer.assert_called_once_with(r"D:\fixture\closed\plan.json")
        with self.assertRaises((OSError, ValueError)):
            g.check_chain_result(audit, self.plan)

    def test_changed_closed_chain_stops_before_original_source_scan(self):
        original = Mock()
        original.source_hashes.return_value = {"source": "d" * 64}
        admitted = g.check_chain_result(self.audit, self.plan)
        changed = deepcopy(admitted)
        changed["closed"][0]["terminal"]["sha256"] = "0" * 64
        revalidate = Mock(side_effect=[admitted, changed])
        bound = g.ChainBoundValidator(original, revalidate, admitted)
        self.assertEqual(bound.source_hashes(Path("fixture")), {"source": "d" * 64})
        with self.assertRaisesRegex(ValueError, "Previously admitted owner-chain evidence changed"):
            bound.source_hashes(Path("fixture"))
        self.assertEqual(original.source_hashes.call_count, 1)
        self.assertEqual(revalidate.call_count, 2)
        self.assertIs(bound.navigation_verdict, original.navigation_verdict)

    def test_gate_refuses_before_import_or_run_without_actual_registration(self):
        error = io.StringIO()
        with patch.object(g, "run") as run, patch.object(g.sys, "stderr", error):
            code = g.main(["--profile", str(Path(self.tmp.name) / "does_not_exist.json"), "--execute"])
        self.assertEqual(code, 2)
        run.assert_not_called()
        self.assertIsNone(g.REGISTERED_PROFILE_SHA256)
        self.assertIsNone(g.CHAIN_VALIDATOR_SHA256)
        self.assertIn("production gate remains disabled", json.loads(error.getvalue())["error"])

    def test_admission_is_complete_at_publication_and_existing_bytes_are_preserved(self):
        path = Path(self.tmp.name) / "admission.json"
        value = {"input_bindings": [{"path": "synthetic" + str(n), "sha256": "e" * 64} for n in range(100)]}
        real_link = g.os.link
        observed = []

        def observe_before_publish(source, destination):
            self.assertEqual(destination, path)
            self.assertFalse(path.exists())
            self.assertEqual(json.loads(source.read_bytes()), value)
            observed.append(source)
            real_link(source, destination)
            self.assertEqual(json.loads(path.read_bytes()), value)

        with patch.object(g.os, "link", side_effect=observe_before_publish):
            g.publish_admission(path, value)
        self.assertEqual(len(observed), 1)
        self.assertFalse(observed[0].exists())
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            g.publish_admission(path, {"different": True})
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(list(path.parent.glob(".admission.json.*.tmp")))


class OuterAdmissionTests(unittest.TestCase):
    def admission(self):
        return {"gate_source": {"path": w.mounted(w.GATE), "sha256": w.PINS["gate"]},
                "profile": {"path": w.mounted(w.PROFILE), "sha256": w.PINS["registered_profile"]},
                "chain_validator": {"path": w.mounted(w.CHAIN), "sha256": w.PINS["chain_validator"]},
                "collector": {"path": w.mounted(w.COLLECTOR), "sha256": w.PINS["collector"]},
                "plan": {"sha256": w.PINS["plan"]},
                "chain_admission": {"status": "BOUND_PRESERVED_PREFIX_CHAIN"},
                "unknown_evidence_exceptions": {}, "automatic_retry": False}

    def test_disabled_outer_never_starts_a_process(self):
        for argv in ([], ["--execute"]):
            with self.subTest(argv=argv), patch.object(w.subprocess, "Popen") as popen, patch.object(w.sys, "stdout", io.StringIO()):
                code = w.main(argv)
                self.assertEqual(code, 2 if argv else 0)
                popen.assert_not_called()

    def test_unfilled_pins_refuse_even_if_only_status_is_changed(self):
        with patch.object(w, "PROFILE_STATUS", "REGISTERED_ACTUAL_CLOSED_PREFIX_CHAIN"):
            with self.assertRaisesRegex(ValueError, "Pinned source differs"):
                w.description()

    def test_admission_requires_each_source_identity_and_no_unknown_exception(self):
        admission = self.admission()
        w.check_admission(admission)
        for defect in ("gate_source", "profile", "chain_validator", "collector", "plan", "status", "unknown", "retry"):
            with self.subTest(defect=defect):
                changed = deepcopy(admission)
                if defect in {"gate_source", "profile", "chain_validator", "collector", "plan"}:
                    changed[defect]["sha256"] = "0" * 64
                elif defect == "status":
                    changed["chain_admission"]["status"] = "OWNER_CHAIN_COMPLETED_NOT_ENGINEERING_ADMISSION"
                elif defect == "unknown":
                    changed["unknown_evidence_exceptions"] = {"fixture": True}
                else:
                    changed["automatic_retry"] = True
                with self.assertRaisesRegex(ValueError, "admission differs"):
                    w.check_admission(changed)

    def test_gate_closure_binds_actual_native_exit_and_unchanged_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "admission.json"
            path.write_text("{}", encoding="utf8")
            identity = {"pid": 123, "boot_id": "fixture", "start_ticks": 42}
            row = {"first_registered_admission_owner_identity": identity, "first_registered_admission_sha256": w.sha(path)}
            native = {"owner_identity": identity, "returncode": 2, "status": "STOPPED_FAULT"}
            raw = json.dumps(native).encode()
            terminal = {"gate_source": {"path": w.mounted(w.GATE), "sha256": w.PINS["gate"]},
                        "profile": {"path": w.mounted(w.PROFILE), "sha256": w.PINS["registered_profile"]},
                        "admission": {"path": w.NATIVE_OWNER + ".admission.json", "sha256": w.sha(path)},
                        "native_terminal": {"path": w.NATIVE_OWNER + "/terminal.json", "sha256": w.hashlib.sha256(raw).hexdigest()},
                        "returncode": 2, "status": "STOPPED_FAULT"}
            with patch.object(w, "ADMISSION_UNC", path):
                w.check_gate_terminal(terminal, row, native, raw)
                for defect in ("identity", "raw", "exit", "status", "admission_path", "native_path"):
                    with self.subTest(defect=defect):
                        changed_row, changed = deepcopy(row), deepcopy(terminal)
                        if defect == "identity":
                            changed_row["first_registered_admission_owner_identity"]["start_ticks"] += 1
                        elif defect == "raw":
                            changed["native_terminal"]["sha256"] = "0" * 64
                        elif defect == "exit":
                            changed["returncode"] = 0
                        elif defect == "status":
                            changed["status"] = "COLLECTION_FINISHED"
                        elif defect == "admission_path":
                            changed["admission"]["path"] += "other"
                        else:
                            changed["native_terminal"]["path"] += "other"
                        with self.assertRaisesRegex(ValueError, "closure differs"):
                            w.check_gate_terminal(changed, changed_row, native, raw)
                path.write_text("{ }", encoding="utf8")
                with self.assertRaisesRegex(ValueError, "closure differs"):
                    w.check_gate_terminal(terminal, row, native, raw)


if __name__ == "__main__":
    unittest.main()
