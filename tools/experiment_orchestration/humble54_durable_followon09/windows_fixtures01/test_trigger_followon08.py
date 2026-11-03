"""Windows small synthetic fixtures. No real WSL, power request or process."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("trigger09_fixture", Path(__file__).with_name("trigger_followon08.py"))
t = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(t)


class FakeInputs:
    def __init__(self):
        self.calls = 0

    def unchanged(self):
        self.calls += 1


class FakeChild:
    pid = 123

    def __init__(self, events, values=None):
        self.events, self.values = events, list(values or [None, 0])
        self.exited = False
        self.result = None

    def wait(self, timeout):
        self.events.append("wait")
        value = self.values.pop(0)
        if value is None:
            raise subprocess.TimeoutExpired("synthetic", timeout)
        if isinstance(value, BaseException):
            raise value
        self.exited, self.result = True, value
        return value


class FakeAPI:
    def __init__(self, events, child, *, exit_code=None, bind_fault=False, accept=1, release=1):
        self.events, self.child = events, child
        self.exit_code, self.bind_fault = exit_code, bind_fault
        self.accept, self.release = accept, release
        self.leased, self.closed = False, False

    def thread_id(self):
        return 44

    def power(self, flags):
        self.events.append(("power", flags))
        if flags == 0x80000003:
            self.leased = self.accept != 0
            return self.accept
        if "launch" in self.events:
            assert self.child.exited, "power release before actual child exit"
            if not self.bind_fault:
                assert self.closed, "power release before held-handle release"
        self.leased = False
        return self.release

    def bind_child(self, child):
        self.events.append("bind")
        assert self.leased and child is self.child
        if self.bind_fault:
            raise OSError("synthetic duplicate failure; Popen original remains held")
        return "held", {"pid": child.pid, "start_token": "windows_filetime:synthetic"}

    def exit(self, held):
        self.events.append("handle_exit")
        assert held == "held" and self.child.exited
        return self.child.result if self.exit_code is None else self.exit_code

    def close(self, held):
        self.events.append("close")
        assert self.child.exited and self.leased
        self.closed = True


class TriggerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original07 = self.root / "synthetic07"
        self.original07.mkdir()
        (self.original07 / "terminal.json").write_text('{"scope":"SYNTHETIC_NOT_ACTUAL_EVIDENCE"}')
        self.output = self.root / "synthetic09"
        self.context = {"started07_binding": {"path": "synthetic-started", "sha256": "a" * 64}}
        self.proof = {"profile": {"path": str(self.root / "synthetic_profile.json"), "sha256": "b" * 64},
                      "closure": {"path": str(self.original07 / "terminal.json"), "sha256": "c" * 64},
                      "audit": {"closed_ids": ["synthetic_slot" + str(i) for i in range(16)]}, "inputs": FakeInputs()}
        self.events = []
        self.child = FakeChild(self.events)
        self.api = FakeAPI(self.events, self.child)
        self.launch = Mock(side_effect=self.launch_child)
        self.ready = Mock(return_value=self.proof)
        self.complete = Mock(return_value={"status": "SYNTHETIC_NOT_ACTUAL_MEASUREMENT", "stage_build_formal": "NOT_RUN"})
        self.patches = [patch.object(t, "ORIGINAL07", self.original07), patch.object(t, "NATIVE08", str(self.root / "synthetic08"))]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def launch_child(self, command, **kwargs):
        self.assertTrue(self.api.leased)
        self.assertTrue(self.ready.called)
        self.events.append("launch")
        self.assertEqual(command[:6], ["wsl.exe", "--distribution", "UAVHumble22", "--exec", "python3", "-B"])
        self.assertEqual(command.count("--execute"), 1)
        return self.child

    def run_case(self, **kwargs):
        options = dict(pause=lambda _: None, ready=self.ready, complete=self.complete, launch=self.launch, check=lambda: None)
        options.update(kwargs)
        return t.supervise(self.context, self.output, self.api, **options)

    def test_default_and_disabled_execute_do_not_read_or_acquire_anything(self):
        with patch.object(t, "load_context") as load, patch.object(t, "WindowsAPI") as api, patch.object(t.sys, "stdout", io.StringIO()):
            self.assertEqual(t.main([]), 0)
            self.assertEqual(t.main(["--execute"]), 2)
        load.assert_not_called()
        api.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_success_holds_thread_lease_and_bound_handle_until_real_exit(self):
        result = self.run_case()
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(self.launch.call_count, 1)
        self.assertEqual(self.ready.call_count, 1)
        self.assertEqual(self.complete.call_count, 1)
        self.assertTrue(self.api.closed)
        self.assertLess(self.events.index("launch"), self.events.index("close"))
        self.assertLess(self.events.index("close"), self.events.index(("power", 0x80000000)))
        self.assertEqual(result["power_lease"]["request_return"], 1)
        self.assertEqual(result["power_lease"]["release_return"], 1)
        self.assertEqual(result["power_lease"]["thread_id"], 44)
        self.assertEqual(result["child"]["popen_wait_exit_code"], 0)
        self.assertEqual(result["child"]["final_held_handle_exit_code"], 0)
        self.assertEqual(json.loads((self.output / "terminal.json").read_text())["returncode"], 0)

    def test_waits_for_actual07_existence_with_lease_before_gate(self):
        (self.original07 / "terminal.json").unlink()

        def pause(_):
            self.assertTrue(self.api.leased)
            self.ready.assert_not_called()
            self.launch.assert_not_called()
            (self.original07 / "terminal.json").write_text('{"scope":"SYNTHETIC_ONLY"}')

        self.assertEqual(self.run_case(pause=pause)["returncode"], 0)

    def test_fault07_or_fresh_pending16_never_starts08(self):
        self.ready.side_effect = ValueError("synthetic actual07 fault or fresh chain pending")
        result = self.run_case()
        self.assertEqual(result["returncode"], 2)
        self.launch.assert_not_called()
        self.complete.assert_not_called()
        self.assertFalse(self.api.leased)

    def test_source_change_after_gate_never_starts08(self):
        check = Mock(side_effect=[None, ValueError("synthetic source changed")])
        self.assertEqual(self.run_case(check=check)["returncode"], 2)
        self.launch.assert_not_called()

    def test_failed_power_request_never_reads_future_or_starts_child(self):
        self.api.accept = 0
        result = self.run_case()
        self.assertEqual(result["returncode"], 2)
        self.ready.assert_not_called()
        self.launch.assert_not_called()
        self.assertEqual(result["power_lease"]["request_return"], 0)
        self.assertIn("released_utc", result["power_lease"])

    def test_metadata_fault_after_launch_keeps_child_handle_and_lease_to_exit(self):
        def publish(path, state, **kwargs):
            if path.name == "state.json" and state["status"] == "WAITING_OWNED_NATIVE08_ACTUAL_EXIT":
                raise PermissionError("synthetic metadata fault")
            t.atomic_json(path, state, **kwargs)

        result = self.run_case(publish=publish)
        self.assertEqual(result["returncode"], 2)
        self.assertTrue(self.child.exited)
        self.assertTrue(self.api.closed)
        self.assertFalse(self.api.leased)
        self.assertEqual(self.launch.call_count, 1)
        self.complete.assert_not_called()

    def test_bind_fault_still_holds_popen_creation_handle_until_actual_exit(self):
        self.api.bind_fault = True
        result = self.run_case()
        self.assertEqual(result["returncode"], 2)
        self.assertTrue(self.child.exited)
        self.assertEqual(result["child"]["popen_wait_exit_code"], 0)
        self.assertEqual(self.launch.call_count, 1)
        self.complete.assert_not_called()

    def test_keyboard_interrupt_waits_original_child_without_retry(self):
        self.child.values = [KeyboardInterrupt(), None, 0]
        result = self.run_case()
        self.assertEqual(result["returncode"], 2)
        self.assertTrue(self.child.exited)
        self.assertTrue(self.api.closed)
        self.assertEqual(self.launch.call_count, 1)
        self.complete.assert_not_called()

    def test_nonzero_native_exit_never_accepts_receipt(self):
        self.child.values = [None, 2]
        result = self.run_case()
        self.assertEqual(result["returncode"], 2)
        self.assertEqual(result["child"]["popen_wait_exit_code"], 2)
        self.complete.assert_not_called()

    def test_mismatched_kernel_and_popen_exit_is_failure(self):
        self.api.exit_code = 9
        self.assertEqual(self.run_case()["returncode"], 2)
        self.assertTrue(self.api.closed)
        self.complete.assert_not_called()

    def test_missing_actual08_terminal_is_failure_even_with_both_zero_exits(self):
        self.complete.side_effect = FileNotFoundError("synthetic original08 terminal missing")
        result = self.run_case()
        self.assertEqual(result["returncode"], 2)
        self.assertEqual(result["child"]["popen_wait_exit_code"], 0)
        self.assertIsNone(result["completion"])

    def test_release_failure_preserves_completion_but_is_not_success(self):
        self.api.release = 0
        result = self.run_case()
        self.assertEqual(result["returncode"], 2)
        self.assertIsNotNone(result["completion"])
        self.assertEqual(result["power_lease"]["release_return"], 0)

    def test_existing_output_is_not_resumed_and_no_lease_is_requested(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "Fresh09"):
            self.run_case()
        self.assertEqual(self.events, [])
        self.launch.assert_not_called()

    def test_terminal_publication_failure_does_not_retry_or_hide_child_exit(self):
        def publish(path, state, **kwargs):
            if path.name == "terminal.json":
                raise OSError("synthetic disk publication fault")
            t.atomic_json(path, state, **kwargs)

        with patch.object(t.sys, "stderr", io.StringIO()):
            result = self.run_case(publish=publish)
        self.assertEqual(result["returncode"], 2)
        self.assertTrue(self.child.exited)
        self.assertTrue(self.api.closed)
        self.assertFalse(self.api.leased)
        self.assertFalse((self.output / "terminal.json").exists())
        self.assertEqual(self.launch.call_count, 1)


class CompletionContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.closed = ["synthetic_slot" + str(i) for i in range(16)]
        self.proof = {"profile": {"path": str(self.root / "profile.json"), "sha256": "a" * 64},
                      "closure": {"path": str(self.root / "closure.json"), "sha256": "b" * 64},
                      "audit": {"closed_ids": self.closed}, "inputs": FakeInputs()}
        self.terminal = {"scope": "NATIVE_SERIAL_FOLLOWON08_ACTUAL28_R0_BUDGET_ONLY",
                         "status": "COMPLETED_MEASUREMENT_CALIBRATION_BUDGET_NOT_ADMISSION", "returncode": 0,
                         "errors": [], "interruptions": [], "automatic_retry": False,
                         "source": {"path": str(t.RUNNER08), "sha256": "c" * 64},
                         "full_chain_profile": self.proof["profile"], "durable07_closure": self.proof["closure"],
                         "closed_ids": self.closed, "steps": [{"id": label, "returncode": 0} for label in t.STEP_IDS],
                         "started_utc": "2026-01-01T00:00:01+00:00", "finished_utc": "2026-01-01T00:00:02+00:00"}
        self.state = {"child": {"started_utc": "2026-01-01T00:00:00+00:00", "finished_utc": "2026-01-01T00:00:03+00:00"}}
        v = Mock()
        v.local_path.side_effect = Path
        v.timestamp.side_effect = lambda value, now: value
        self.context = {"chain": Mock(v=v)}

    def check(self):
        (self.root / "terminal.json").write_text(json.dumps(self.terminal))
        with patch.object(t, "NATIVE08", str(self.root)), patch.object(t, "RUNNER08_SHA256", "c" * 64), patch.object(t, "check_sources"):
            return t.validate_completion(self.context, self.proof, self.state)

    def test_exact_twelve_steps_and_actual_terminal_are_required(self):
        self.assertEqual(self.check()["stage_build_formal"], "NOT_RUN")
        self.terminal["steps"].pop()
        with self.assertRaisesRegex(ValueError, "serial steps"):
            self.check()

    def test_native_negative_budget_is_failure_even_after_twelve_zero_steps(self):
        self.terminal.update(status="STOPPED_FOLLOWON08_PARTIAL_OUTPUTS_RETAINED", returncode=2,
                             errors=[{"error": "synthetic negative budget"}])
        with self.assertRaisesRegex(ValueError, "terminal"):
            self.check()

    def test_other_source_or_input_or_closed_ids_is_failure(self):
        original = deepcopy(self.terminal)
        for field, value in (("source", {"path": str(t.RUNNER08), "sha256": "d" * 64}),
                             ("full_chain_profile", {"path": str(self.root / "other.json"), "sha256": "a" * 64}),
                             ("closed_ids", self.closed[:-1])):
            with self.subTest(field=field):
                self.terminal = deepcopy(original)
                self.terminal[field] = value
                with self.assertRaises(ValueError):
                    self.check()


if __name__ == "__main__":
    unittest.main(verbosity=2)
