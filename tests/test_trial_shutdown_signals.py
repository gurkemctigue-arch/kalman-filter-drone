"""Check the real runner's signal routing with no processes or ROS imports.

Only nested start/stop functions are loaded from the production AST. These
mock checks do not establish clean integrated ROS launch shutdown.
"""
import ast
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, call


RUNNER = Path(__file__).resolve().parents[1] / "scripts/run_stage1_trial.py"
TREE = ast.parse(RUNNER.read_text(encoding="utf-8"))
MAIN = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "main")
FUNCTIONS = [node for node in MAIN.body
             if isinstance(node, ast.FunctionDef) and node.name in {"start", "stop"}]
# The runner targets Linux; the pure mock suite also runs on Windows, where
# the standard signal module does not expose SIGKILL.
SIGNALS = SimpleNamespace(SIGINT=2, SIGTERM=15, SIGKILL=9)


class TrialShutdownSignalTests(unittest.TestCase):
    def functions(self, process, name="ros"):
        fake_os = SimpleNamespace(killpg=Mock())
        fake_subprocess = SimpleNamespace(Popen=Mock(return_value=process), DEVNULL=subprocess.DEVNULL,
                                          STDOUT=subprocess.STDOUT,
                                          TimeoutExpired=subprocess.TimeoutExpired)
        namespace = {"processes": {name: process}, "logs": [], "output": MagicMock(),
                     "root": Path("/fixture/project"), "env": {"fixture": "no subprocess"},
                     "os": fake_os, "signal": SIGNALS, "subprocess": fake_subprocess,
                     "print": Mock()}
        exec(compile(ast.Module(body=FUNCTIONS, type_ignores=[]), str(RUNNER), "exec"), namespace)
        return namespace, fake_os, fake_subprocess

    def process(self):
        process = Mock(pid=8123)
        process.poll.return_value = None
        return process

    def test_ros_sends_initial_sigint_only_to_launch_parent(self):
        process = self.process()
        namespace, fake_os, _ = self.functions(process)
        namespace["stop"]("ros", timeout=8)
        process.send_signal.assert_called_once_with(SIGNALS.SIGINT)
        fake_os.killpg.assert_not_called()
        process.wait.assert_called_once_with(timeout=8)

    def test_other_services_keep_process_group_sigint(self):
        for name in ("monitor", "bag", "sensor_faults", "px4", "gazebo", "agent"):
            with self.subTest(service=name):
                process = self.process()
                namespace, fake_os, _ = self.functions(process, name)
                timeout = 45 if name == "bag" else 8
                namespace["stop"](name, timeout=timeout)
                process.send_signal.assert_not_called()
                fake_os.killpg.assert_called_once_with(8123, SIGNALS.SIGINT)
                process.wait.assert_called_once_with(timeout=timeout)

    def test_ros_timeout_retains_group_sigterm_fallback(self):
        process = self.process()
        process.wait.side_effect = [subprocess.TimeoutExpired("launch", 8), 0]
        namespace, fake_os, _ = self.functions(process)
        namespace["stop"]("ros", timeout=8)
        process.send_signal.assert_called_once_with(SIGNALS.SIGINT)
        self.assertEqual(fake_os.killpg.call_args_list, [call(8123, SIGNALS.SIGTERM)])
        self.assertEqual(process.wait.call_args_list, [call(timeout=8), call(timeout=5)])

    def test_ros_second_timeout_retains_group_sigkill_fallback(self):
        process = self.process()
        process.wait.side_effect = [subprocess.TimeoutExpired("launch", 8),
                                    subprocess.TimeoutExpired("launch", 5), 0]
        namespace, fake_os, _ = self.functions(process)
        namespace["stop"]("ros", timeout=8)
        process.send_signal.assert_called_once_with(SIGNALS.SIGINT)
        self.assertEqual(fake_os.killpg.call_args_list,
                         [call(8123, SIGNALS.SIGTERM), call(8123, SIGNALS.SIGKILL)])
        self.assertEqual(process.wait.call_args_list,
                         [call(timeout=8), call(timeout=5), call(timeout=3)])

    def test_other_service_timeout_sequence_is_unchanged(self):
        process = self.process()
        process.wait.side_effect = [subprocess.TimeoutExpired("bag", 45),
                                    subprocess.TimeoutExpired("bag", 5), 0]
        namespace, fake_os, _ = self.functions(process, "bag")
        namespace["stop"]("bag", timeout=45)
        process.send_signal.assert_not_called()
        self.assertEqual(fake_os.killpg.call_args_list,
                         [call(8123, SIGNALS.SIGINT), call(8123, SIGNALS.SIGTERM),
                          call(8123, SIGNALS.SIGKILL)])
        self.assertEqual(process.wait.call_args_list,
                         [call(timeout=45), call(timeout=5), call(timeout=3)])

    def test_missing_or_exited_process_is_not_signalled(self):
        process = self.process()
        process.poll.return_value = 0
        namespace, fake_os, _ = self.functions(process)
        namespace["stop"]("ros")
        namespace["stop"]("not_started")
        process.send_signal.assert_not_called()
        process.wait.assert_not_called()
        fake_os.killpg.assert_not_called()

    def test_only_ros_has_devnull_stdin_and_all_keep_their_own_session(self):
        for name in ("ros", "bag", "monitor", "sensor_faults", "px4", "gazebo", "agent"):
            with self.subTest(service=name):
                process = self.process()
                namespace, _, fake_subprocess = self.functions(process, name)
                self.assertIs(namespace["start"](name, ["fixture", name]), process)
                kwargs = fake_subprocess.Popen.call_args.kwargs
                self.assertEqual(kwargs["stdin"], subprocess.DEVNULL if name == "ros" else None)
                self.assertTrue(kwargs["start_new_session"])
                self.assertIs(namespace["processes"][name], process)

    def test_unexpected_wait_error_is_not_hidden(self):
        process = self.process()
        process.wait.side_effect = RuntimeError("unexpected wait failure")
        namespace, fake_os, _ = self.functions(process)
        with self.assertRaisesRegex(RuntimeError, "unexpected wait failure"):
            namespace["stop"]("ros")
        fake_os.killpg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
