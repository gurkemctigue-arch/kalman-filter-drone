"""Pure contracts only; real RGB-D shutdown is run separately in isolation."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("shutdown_probe_fixture", ROOT / "scripts/probe_gazebo_shutdown.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class ShutdownProbeTests(unittest.TestCase):
    def test_source_verified_server_api_and_ack_require_actual_success(self):
        command = probe.server_stop_command()
        self.assertIn("/server_control", command)
        self.assertIn("gz.msgs.ServerControl", command)
        self.assertEqual(command[-1], "stop: true")
        self.assertTrue(probe.response_acknowledged(0, "data: true\n"))
        self.assertFalse(probe.response_acknowledged(0, "data: false\n"))
        self.assertFalse(probe.response_acknowledged(1, "data: true\n"))
        self.assertFalse(probe.response_acknowledged(0, ""))

    def test_isolated_partition_overrides_inherited_without_changing_driver(self):
        with patch.dict(probe.os.environ, {"GZ_PARTITION":"person_current_trial", "GALLIUM_DRIVER":"llvmpipe"}):
            env = probe.owned_environment("uav_shutdown_smoke_" + "a" * 32, [], [], 4)
            self.assertNotEqual(env["GZ_PARTITION"], "person_current_trial")
            self.assertEqual(env["GALLIUM_DRIVER"], "llvmpipe")
            self.assertEqual(env["LP_NUM_THREADS"], "4")
            self.assertEqual(env["OMP_NUM_THREADS"], "2")
            self.assertEqual(probe.os.environ["GZ_PARTITION"], "person_current_trial")
        with self.assertRaises(ValueError):
            probe.owned_environment("stage1_flight", [], [], 4)


if __name__ == "__main__":
    unittest.main()
