"""Short fake lifecycle checks; no power API, WSL, ROS, or real native child."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("launcher07_under_test", HERE / "launch_windows07.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class FakePower:
    def __init__(self):
        self.calls = []

    def thread(self):
        return 17

    def request(self, flags):
        self.calls.append(flags)
        return 0x80000000


class FakeChild:
    pid = 12345

    def __init__(self, code):
        self.code, self.polls, self.waits = code, 0, 0

    def poll(self):
        self.polls += 1
        return self.code if self.polls >= 3 else None

    def wait(self):
        self.waits += 1
        return self.code


class LauncherLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.power, self.spawned = FakePower(), []
        self.desc = {"command": ["fake-monitor-only"], "monitor_output": str(self.root / "monitor"), "pins": {}}

    def run_owner(self, code=0, save=launcher.publish, pause=lambda value: None):
        self.child = FakeChild(code)
        def spawn(command, **kwargs):
            self.spawned.append((command, kwargs))
            return self.child
        def closure(state, output):
            state.update(closure_verified=True, native_collection_returncode=state["owned_monitor_returncode"])
        return launcher.supervise(deepcopy(self.desc), self.root / "receipt", self.power,
                                  lambda pid: {"pid": pid, "start_token": "fake-creation-token"},
                                  spawn=spawn, pause=pause, save=save, closure=closure)

    def test_zero_exit_has_one_owned_child_isolated_group_and_same_thread_power_release(self):
        state = self.run_owner()
        self.assertEqual(state["owned_monitor_returncode"], 0)
        self.assertEqual(state["returncode"], 0)
        self.assertEqual(len(self.spawned), 1)
        self.assertEqual(self.spawned[0][1]["creationflags"], 0x08000200)
        self.assertEqual(self.child.waits, 1)
        self.assertEqual(self.power.calls, [0x80000003, 0x80000000])
        self.assertEqual(state["power_lease"]["thread_id"], state["power_lease"]["release_thread_id"])

    def test_real_nonzero_is_retained_without_retry(self):
        state = self.run_owner(2)
        self.assertEqual(state["owned_monitor_returncode"], 2)
        self.assertEqual(state["returncode"], 2)
        self.assertEqual(state["status"], "STOPPED_FAULT_NO_RETRY")
        self.assertEqual(len(self.spawned), 1)
        self.assertEqual(self.child.waits, 1)

    def test_metadata_failure_after_spawn_keeps_waiting_same_child_and_releases_power(self):
        saves = []
        def broken_after_spawn(path, state):
            saves.append(path.name)
            if path.name == "started.json" and state["owned_monitor_identity"] is not None:
                raise OSError("simulated receipt sharing fault")
            launcher.publish(path, state)
        state = self.run_owner(save=broken_after_spawn)
        self.assertEqual(state["owned_monitor_returncode"], 0)
        self.assertEqual(state["returncode"], 2)
        self.assertEqual(self.child.waits, 1)
        self.assertEqual(len(self.spawned), 1)
        self.assertEqual(self.power.calls[-1], 0x80000000)

    def test_keyboard_interrupt_never_calls_kill_or_starts_replacement(self):
        calls = []
        def interrupt_once(value):
            calls.append(value)
            if len(calls) == 1:
                raise KeyboardInterrupt("fake outer console interrupt")
        state = self.run_owner(pause=interrupt_once)
        self.assertEqual(state["owned_monitor_returncode"], 0)
        self.assertEqual(state["returncode"], 2)
        self.assertEqual(len(self.spawned), 1)
        self.assertEqual(self.child.waits, 1)
        self.assertTrue(any("KeyboardInterrupt" in row["error"] for row in state["errors"]))

    def test_initial_metadata_failure_starts_no_child(self):
        def failed_start(path, state):
            if path.name == "started.json":
                raise OSError("fake initial write failure")
            launcher.publish(path, state)
        state = self.run_owner(save=failed_start)
        self.assertEqual(self.spawned, [])
        self.assertIsNone(state["owned_monitor_returncode"])
        self.assertEqual(state["returncode"], 2)
        self.assertEqual(self.power.calls, [0x80000003, 0x80000000])

    def test_terminal_metadata_failure_cannot_report_supervisor_success(self):
        attempted = []
        def terminal_failed_once(path, state):
            if path.name == "terminal.json":
                attempted.append(True)
                if len(attempted) == 1:
                    raise OSError("fake final write failure")
            launcher.publish(path, state)
        state = self.run_owner(save=terminal_failed_once)
        self.assertEqual(state["owned_monitor_returncode"], 0)
        self.assertEqual(state["returncode"], 2)
        self.assertEqual(len(attempted), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
