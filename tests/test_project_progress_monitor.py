"""Real short processes and evidence boundaries; no WSL, ROS or simulation."""
import importlib.util
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/monitor_project_progress.py"
SPEC = importlib.util.spec_from_file_location("project_progress", SCRIPT)
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


@contextmanager
def deny_windows_replacement(path):
    """An ordinary reader sharing reads/writes but not Windows DELETE access."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


class ProjectProgressTests(unittest.TestCase):
    def setUp(self):
        # Frozen Linux workspaces deliberately symlink results to preserved
        # host evidence. Keep disposable fixtures inside the source workspace,
        # without resolving or writing through that results symlink.
        self.temporary = tempfile.TemporaryDirectory(prefix="progress_monitor_test_", dir=ROOT)
        self.directory = Path(self.temporary.name).resolve()
        self.assertEqual(self.directory.parent, ROOT.resolve())
        self.output = self.directory / "monitor"

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, *arguments):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, arguments)], cwd=ROOT,
                              capture_output=True, text=True, timeout=10,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    def run_child(self, code, *, phase="simulation"):
        return self.invoke("run", "--output", self.output, "--phase", phase,
                           "--interval", ".03", "--stale-after", "1", "--", sys.executable, "-c", code)

    def read_report(self):
        return json.loads((self.output / "progress.json").read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "nt", "Real Windows sharing semantics")
    def test_real_windows_reader_releasing_lock_allows_json_and_html_publication(self):
        for filename in ("progress.json", "index.html"):
            with self.subTest(filename=filename):
                path = self.directory / filename
                path.write_text("old", encoding="utf-8")
                locked, release = threading.Event(), threading.Event()

                def reader():
                    with deny_windows_replacement(path):
                        locked.set()
                        release.wait(2)

                thread = threading.Thread(target=reader)
                thread.start()
                try:
                    self.assertTrue(locked.wait(2))
                    timer = threading.Timer(.08, release.set)
                    timer.start()
                    if filename.endswith(".json"):
                        monitor.atomic_json(path, {"updated": True})
                        self.assertEqual(monitor.read_json(path), {"updated": True})
                    else:
                        monitor.atomic_text(path, "<html>new</html>")
                        self.assertEqual(path.read_text(), "<html>new</html>")
                    timer.join()
                finally:
                    release.set()
                    thread.join(timeout=2)
                self.assertEqual(list(self.directory.glob("*.tmp")), [])

    @unittest.skipUnless(os.name == "nt", "Real Windows sharing semantics")
    def test_real_windows_persistent_lock_preserves_snapshot_and_cleans_temporary(self):
        path = self.directory / "progress.json"
        path.write_text('{"old": true}', encoding="utf-8")
        with deny_windows_replacement(path), mock.patch.object(monitor, "REPLACE_RETRY_SECONDS", .04):
            with self.assertRaises(OSError) as caught:
                monitor.atomic_json(path, {"updated": True})
        self.assertIn(caught.exception.winerror, {5, 32, 33})
        self.assertEqual(monitor.read_json(path), {"old": True})
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    def test_nonsharing_replace_error_is_not_retried_and_cleans_temporary(self):
        path = self.directory / "progress.json"
        path.write_text('{"old": true}', encoding="utf-8")
        with mock.patch.object(monitor.os, "replace", side_effect=OSError("disk failure")) as replace:
            with self.assertRaisesRegex(OSError, "disk failure"):
                monitor.atomic_json(path, {"updated": True})
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(monitor.read_json(path), {"old": True})
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    @unittest.skipUnless(os.name == "nt", "Real Windows sharing semantics")
    def test_real_monitor_survives_busy_snapshot_without_restarting_or_killing_target(self):
        command = [sys.executable, str(SCRIPT), "run", "--output", str(self.output),
                   "--phase", "evaluation", "--interval", ".03", "--stale-after", "1",
                   "--", sys.executable, "-c", "import time; time.sleep(2)"]
        wrapper = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        expected = None
        try:
            deadline = time.monotonic() + 3
            while not (self.output / "progress.json").exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue((self.output / "progress.json").exists())
            state = monitor.read_json(self.output / "monitor_state.json")
            expected = state["task"]["process"]
            with deny_windows_replacement(self.output / "progress.json"):
                time.sleep(.75)  # Exceeds the bounded per-publication retry window.
                self.assertIsNone(wrapper.poll())
                self.assertTrue(monitor.verify_process(expected)["verified_alive"])
            stdout, stderr = wrapper.communicate(timeout=5)
            self.assertEqual(wrapper.returncode, 0, stderr)
            self.assertIn("SNAPSHOT_PUBLICATION_RETRY", stderr)
            report = self.read_report()
            self.assertEqual(report["status"], "COMPLETED")
            self.assertEqual(report["task"]["process"]["start_token"], expected["start_token"])
            self.assertEqual(report["task"]["returncode"], 0)
            self.assertEqual(len(report["tasks"]), 1)
            self.assertEqual(list(self.output.glob("*.tmp")), [])
            self.assertFalse((self.output / "monitor.lock.json").exists())
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.communicate(timeout=3)
            if expected and monitor.verify_process(expected)["verified_alive"]:
                os.kill(expected["pid"], signal.SIGTERM)

    def test_real_owned_process_success_records_exit_and_creation_identity(self):
        result = self.run_child("import time; time.sleep(.12)")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = self.read_report()
        self.assertEqual(report["status"], "COMPLETED")
        self.assertEqual(report["completion_scope"], "monitored_command")
        self.assertEqual(report["task"]["returncode"], 0)
        self.assertTrue(report["task"]["process"]["start_token"])
        self.assertTrue((self.output / "end_summary.json").is_file())
        self.assertFalse((self.output / "monitor.lock.json").exists())
        self.assertFalse(report["notification"]["submitted"])

    def test_real_nonzero_process_is_fault_not_engineering_pass(self):
        result = self.run_child("import time; time.sleep(.10); raise SystemExit(7)", phase="evaluation")
        self.assertEqual(result.returncode, 7, result.stderr)
        report = self.read_report()
        self.assertEqual(report["status"], "STOPPED_FAULT")
        self.assertEqual(report["task"]["returncode"], 7)
        self.assertEqual(report["phase"], "evaluation")

    def test_real_immediate_exit_is_still_recorded(self):
        result = self.run_child("pass")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_report()["status"], "COMPLETED")

    def test_killed_real_monitor_expires_while_real_target_remains_alive(self):
        command = [sys.executable, str(SCRIPT), "run", "--output", str(self.output),
                   "--phase", "evaluation", "--interval", ".03", "--stale-after", ".20",
                   "--", sys.executable, "-c", "import time; time.sleep(10)"]
        wrapper = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        expected = None
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state_path = self.output / "monitor_state.json"
                if state_path.is_file():
                    state = monitor.read_json(state_path)
                    expected = state["task"]["process"]
                    active = monitor.snapshot(state)
                    self.assertEqual(active["status"], "EVALUATING")
                    self.assertTrue(active["process_check"]["verified_alive"])
                    break
                time.sleep(.02)
            self.assertIsNotNone(expected, "Wrapper failed to establish a real heartbeat")
            wrapper.kill()
            wrapper.wait(timeout=3)
            time.sleep(.25)
            result = self.invoke("snapshot", "--output", self.output)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = self.read_report()
            self.assertEqual(report["status"], "STALE")
            self.assertTrue(report["process_check"]["verified_alive"])
            self.assertGreater(report["heartbeat_age_s"], .20)
            self.assertFalse(report["monitor_check"]["verified_alive"])
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait(timeout=3)
            if expected and monitor.verify_process(expected)["verified_alive"]:
                os.kill(expected["pid"], signal.SIGTERM)
                deadline = time.monotonic() + 2
                while monitor.verify_process(expected)["verified_alive"] and time.monotonic() < deadline:
                    time.sleep(.02)

    def test_pid_reuse_or_mismatched_start_token_cannot_claim_running(self):
        identity = monitor.process_identity(os.getpid())
        wrong = {**identity, "start_token": identity["start_token"] + "_different_creation"}
        state = {"task": {"phase": "simulation", "process": wrong}, "monitor_process": identity,
                 "heartbeat_utc": monitor.utc_now(), "stale_after_s": 10}
        report = monitor.snapshot(state)
        self.assertEqual(report["status"], "UNVERIFIED")
        self.assertFalse(report["process_check"]["identity_matches"])

    def test_existing_log_and_started_event_without_live_identity_stay_unverified(self):
        events = self.directory / "events.jsonl"
        events.write_text(json.dumps({"utc": monitor.utc_now(), "event": "START_SLOT", "slot": "a", "total": 12}) + "\n")
        (self.directory / "some.log").write_text("running forever")
        report = monitor.snapshot({"sources": {"events": str(events)}})
        self.assertEqual(report["status"], "UNVERIFIED")
        self.assertEqual(report["evidence"]["unattempted_slots"], 11)

    def test_infrastructure_stop_preserves_attempted_and_pending_denominators(self):
        events = self.directory / "events.jsonl"
        rows = [
            {"event": "START_SLOT", "slot": "a", "total": 3},
            {"event": "COMPLETE_SLOT", "slot": "a", "status": "EVALUATION_PENDING"},
            {"event": "START_SLOT", "slot": "b", "total": 3},
            {"event": "COMPLETE_SLOT", "slot": "b", "status": "INFRASTRUCTURE_ERROR"},
            {"event": "INFRASTRUCTURE_STOP_NO_AUTOMATIC_RETRY", "slot": "b"},
        ]
        events.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        self.assertEqual(self.invoke("snapshot", "--output", self.output, "--events", events).returncode, 0)
        first = self.read_report()
        self.assertEqual(first["status"], "STOPPED_FAULT")
        self.assertEqual(first["evidence"]["attempted_slots"], 2)
        self.assertEqual(first["evidence"]["unattempted_slots"], 1)
        self.assertNotIn("PASS", first["evidence"]["status_counts"])
        # Short refresh retains the actual source binding without starting a task.
        self.assertEqual(self.invoke("snapshot", "--output", self.output).returncode, 0)
        self.assertEqual(self.read_report()["status"], "STOPPED_FAULT")

    def test_zero_exit_does_not_complete_an_unattempted_batch(self):
        ledger = self.directory / "ledger.json"
        events = self.directory / "events.jsonl"
        ledger.write_text(json.dumps({"finished_utc": monitor.utc_now(), "returncode": 0}))
        events.write_text(json.dumps({"event": "START_SLOT", "slot": "a", "total": 2}) + "\n")
        report = monitor.snapshot({"sources": {"ledger": str(ledger), "events": str(events)}})
        self.assertEqual(report["status"], "UNVERIFIED")

    def test_duplicate_task_id_rejected_before_spawning_another_child(self):
        self.assertEqual(self.run_child("pass").returncode, 0)
        task_id = self.read_report()["task"]["id"]
        marker = self.directory / "must_not_exist"
        result = self.invoke("run", "--output", self.output, "--phase", "simulation", "--task-id", task_id,
                             "--", sys.executable, "-c", "from pathlib import Path; Path(" + repr(str(marker)) + ").write_text('bad')")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(marker.exists())

    def test_output_never_writes_frozen_or_unowned_evidence(self):
        with self.assertRaisesRegex(ValueError, "Frozen"):
            monitor.prepare_output(ROOT / "frozen_progress_forbidden/new_monitor")
        self.assertFalse((ROOT / "frozen_progress_forbidden").exists())
        self.directory.joinpath("original.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "not owned"):
            monitor.prepare_output(self.directory)


if __name__ == "__main__":
    unittest.main()
