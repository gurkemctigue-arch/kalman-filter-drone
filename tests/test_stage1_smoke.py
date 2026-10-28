"""Static checks for the controlled ROS stage-one acceptance test."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "ros2_ws" / "src" / "uav_tracking_bringup" / "uav_tracking_bringup" / "stage1_smoke_test.py"
SETUP = ROOT / "ros2_ws" / "src" / "uav_tracking_bringup" / "setup.py"
DOCS = ROOT / "docs" / "ROS2_SIMULATION.md"


class Stage1SmokeAssetTests(unittest.TestCase):
    def test_controlled_smoke_script_has_all_acceptance_phases(self) -> None:
        source = SMOKE.read_text(encoding="utf-8")
        compile(source, str(SMOKE), "exec")
        for marker in (
            "CONTROLLED_TEST_SOURCE",
            "STATE_MEASURED",
            "STATE_PREDICTED",
            "STATE_LOST",
            "LIFECYCLE_HOVER",
            "MODE_FAILSAFE",
            "depth_probe",
        ):
            self.assertIn(marker, source)

    def test_smoke_script_is_installed_and_documented(self) -> None:
        setup_source = SETUP.read_text(encoding="utf-8")
        self.assertIn("stage1_smoke_test = uav_tracking_bringup.stage1_smoke_test:main", setup_source)
        docs = DOCS.read_text(encoding="utf-8")
        self.assertIn("stage1_smoke_test", docs)
        self.assertIn("CONTROLLED_TEST_SOURCE", docs)


if __name__ == "__main__":
    unittest.main()
