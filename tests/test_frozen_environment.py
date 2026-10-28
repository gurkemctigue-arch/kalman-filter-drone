"""Frozen studies must not resolve their code or ROS overlay to an old root."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class FrozenImportIsolationTests(unittest.TestCase):
    def run_guard(self, escaped_module=None, escaped_prefix=None):
        # Exercise the exact inline guard used after colcon, without building
        # ROS or importing runtime nodes during a test.
        shell = (ROOT / "scripts/freeze_full_plan_workspace.sh").read_text(encoding="utf-8")
        code = shell.split("import importlib\n", 1)[1].split("\nPY_VERIFY_FROZEN", 1)[0]
        code = "import importlib\n" + code
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            frozen, old = base / "frozen", base / "old"
            frozen.mkdir()
            old.mkdir()
            names = ("uav_tracking.core", "uav_tracking_nodes",
                     "uav_tracking_interfaces.msg",
                     "uav_tracking_interfaces.msg._target_observation_array",
                     "uav_tracking_interfaces.msg._target_state")
            modules = {}
            for name in names:
                location = (old if name == escaped_module else frozen) / (name + ".py")
                location.touch()
                module = ModuleType(name)
                module.__file__ = str(location)
                modules[name] = module

            def prefix(command, **kwargs):
                return str(old if command[-1] == escaped_prefix else frozen) + "\n"

            output = io.StringIO()
            with patch.dict(sys.modules, modules), \
                    patch.dict(os.environ, {"TRACKING_FROZEN_ROOT": str(frozen)}), \
                    patch("subprocess.check_output", side_effect=prefix), redirect_stdout(output):
                exec(compile(code, "frozen-import-guard", "exec"), {})
            return json.loads(output.getvalue())

    def test_current_modules_and_all_ros_prefixes_are_recorded(self):
        result = self.run_guard()
        self.assertTrue(result["isolated"])
        self.assertEqual(len(result["module_files"]), 5)
        self.assertEqual(len(result["ros_package_prefixes"]), 4)

    def test_old_editable_algorithm_import_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Frozen import escaped.*uav_tracking.core"):
            self.run_guard(escaped_module="uav_tracking.core")

    def test_old_generated_message_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Frozen import escaped.*_target_observation_array"):
            self.run_guard(escaped_module="uav_tracking_interfaces.msg._target_observation_array")

    def test_old_ros_overlay_prefix_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Frozen ament prefix escaped.*uav_tracking_nodes"):
            self.run_guard(escaped_prefix="uav_tracking_nodes")


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"),
                     "POSIX shell integration; run in WSL")
class OfflineEnvironmentShellTests(unittest.TestCase):
    def invoke(self, script, override=None):
        with tempfile.TemporaryDirectory(prefix="frozen environment ") as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy2(ROOT / "scripts" / script, scripts / script)
            binary = root / "bin"
            binary.mkdir()
            python = binary / "python3"
            python.write_text(
                "#!" + sys.executable + "\nimport json,os,sys\n"
                "print(json.dumps({'argv':sys.argv[1:],'pythonpath':os.environ.get('PYTHONPATH'),"
                "'sourced':os.environ.get('SOURCED_PATHS')}))\n")
            python.chmod(0o755)
            environment = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ["PATH"],
                               PYTHONPATH="/old/editable/project",
                               STAGE1_PYTHON_EXECUTABLE=str(python))
            environment.pop("STAGE1_PROJECT_ROOT", None)
            if override is not None:
                environment["STAGE1_PROJECT_ROOT"] = str(root) if override == "same" else "/old/project"
            wrapper = ('source() { export SOURCED_PATHS="${SOURCED_PATHS:-}|$1"; }; '
                       'export -f source; exec bash "$1" sentinel.py --example')
            result = subprocess.run(["bash", "-c", wrapper, "environment-test", str(scripts / script)],
                                    env=environment, capture_output=True, text=True, timeout=10)
            return result, str(root)

    def test_default_and_matching_override_use_scripts_own_install_and_algorithms(self):
        for script in ("research_env.sh", "evaluate_stage1_flight.sh"):
            for override in (None, "same"):
                with self.subTest(script=script, override=override):
                    result, root = self.invoke(script, override)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    evidence = json.loads(result.stdout)
                    self.assertIn(root + "/ros2_ws/install/setup.bash", evidence["sourced"])
                    self.assertTrue(evidence["pythonpath"].startswith(root + ":" + root + "/scripts:"))
                    if script == "evaluate_stage1_flight.sh":
                        self.assertEqual(evidence["argv"][0], root + "/scripts/evaluate_stage1_flight.py")

    def test_contradictory_override_fails_before_loading_any_ros_environment(self):
        for script in ("research_env.sh", "evaluate_stage1_flight.sh"):
            with self.subTest(script=script):
                result, _ = self.invoke(script, "old")
                self.assertEqual(result.returncode, 2)
                self.assertIn("STAGE1_PROJECT_ROOT conflicts", result.stderr)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
