"""Stage-three files must explicitly record the audited adapter/reference contract."""

from pathlib import Path
import unittest

import yaml


CONFIG = Path(__file__).resolve().parents[1] / "ros2_ws/src/uav_tracking_bringup/config"


class Stage3RuntimeSnapshotTests(unittest.TestCase):
    def test_raw_and_adapted_odometry_topics_are_explicit(self):
        for target_class in ("person", "car"):
            with self.subTest(target_class=target_class):
                document = yaml.safe_load((CONFIG / f"stage3_tracking_{target_class}.yaml").read_text(encoding="utf-8"))
                parameters = document["uav_tracking_px4_adapter"]["ros__parameters"]
                self.assertEqual(parameters["vehicle_odometry_topic"], "/fmu/out/vehicle_odometry")
                self.assertEqual(parameters["vehicle_odom_topic"], "/vehicle/odometry")

    def test_zero_follow_offset_is_explicit_for_independent_geometry_evaluation(self):
        for target_class in ("person", "car"):
            with self.subTest(target_class=target_class):
                document = yaml.safe_load((CONFIG / f"stage3_tracking_{target_class}.yaml").read_text(encoding="utf-8"))
                parameters = document["uav_tracking_controller"]["ros__parameters"]
                self.assertEqual(parameters["desired_offset_m"], [0.0, 0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
