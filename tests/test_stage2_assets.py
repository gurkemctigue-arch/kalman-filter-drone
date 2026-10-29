"""Deterministic three-actor paths and simulator-only identity boundaries."""

from pathlib import Path
import math
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_bringup"))
from uav_tracking_bringup.stage2_motion import stage2_motion_profile


def integrate(end_s, target_class, kind):
    poses = [[0.0, 0.0, 0.0] for _ in range(3)]
    dt = 0.005
    for step in range(round(end_s / dt)):
        for pose, (speed, rate) in zip(poses, stage2_motion_profile(
                (step + 0.5) * dt, target_class=target_class, scenario_kind=kind)):
            heading = pose[2] + rate * dt / 2
            pose[0] += speed * math.cos(heading) * dt
            pose[1] += speed * math.sin(heading) * dt
            pose[2] += rate * dt
    return poses


class Stage2AssetsTests(unittest.TestCase):
    def test_both_worlds_have_three_separately_commanded_same_class_models(self):
        for cls in ("person", "car"):
            with self.subTest(cls=cls):
                world = ET.parse(ROOT / f"ros2_ws/src/uav_tracking_bringup/worlds/stage2_flight_{cls}.sdf").getroot().find("world")
                self.assertEqual(world.attrib["name"], "stage2_flight")
                topics = []
                for index in range(3):
                    model = world.find(f"model[@name='stage2_{cls}_{index}']")
                    self.assertIsNotNone(model)
                    plugins = model.findall("plugin")
                    topics.append(next(plugin.findtext("topic") for plugin in plugins
                                       if "VelocityControl" in plugin.attrib["name"]))
                    self.assertTrue(any(plugin.findtext("topic") == "/ground_truth/poses" for plugin in plugins))
                self.assertEqual(topics, [f"/scenario/target_{index}/cmd_vel" for index in range(3)])
                self.assertEqual(len(set(topics)), 3)

    def test_motion_starts_stopped_and_rejects_malformed_configuration(self):
        self.assertEqual(stage2_motion_profile(0), ((0.0, 0.0),) * 3)
        for args in ({"target_class": "dog"}, {"scenario_kind": "fake"}, {"speed_mps": float("nan")}):
            with self.assertRaises(ValueError):
                stage2_motion_profile(1, **args)

    def test_crossing_paths_exchange_image_lanes_at_separate_depths(self):
        for cls, amplitude in (("person", 2.0), ("car", 4.2)):
            poses = integrate(22.0, cls, "crossing")
            self.assertAlmostEqual(poses[1][0], poses[0][0], delta=0.02)
            self.assertAlmostEqual(poses[2][0], poses[0][0], delta=0.02)
            self.assertAlmostEqual(poses[1][1], 2 * amplitude, delta=0.02)
            self.assertAlmostEqual(poses[2][1], -2 * amplitude, delta=0.02)
            self.assertAlmostEqual(poses[1][2], 0.0, delta=0.01)

    def test_crossing_holds_exchanged_lanes_without_periodic_return(self):
        for cls, amplitude in (("person", 2.0), ("car", 4.2)):
            with self.subTest(cls=cls):
                poses = integrate(45.0, cls, "crossing")
                self.assertAlmostEqual(poses[1][1], 2 * amplitude, delta=0.02)
                self.assertAlmostEqual(poses[2][1], -2 * amplitude, delta=0.02)
                for elapsed in (22.0, 30.0, 45.0):
                    commands = stage2_motion_profile(elapsed, target_class=cls, scenario_kind="crossing")
                    for speed, yaw_rate in commands:
                        self.assertAlmostEqual(speed, 0.5)
                        self.assertAlmostEqual(yaw_rate, 0.0)

    def test_crossing_enters_and_leaves_turn_smoothly(self):
        for boundary in (4.0, 22.0):
            before = stage2_motion_profile(boundary - 1e-5, scenario_kind="crossing")
            after = stage2_motion_profile(boundary + 1e-5, scenario_kind="crossing")
            for first, second in zip(before, after):
                self.assertAlmostEqual(first[0], second[0], delta=1e-5)
                self.assertAlmostEqual(first[1], second[1], delta=1e-5)

    def test_ambiguity_paths_approach_then_separate_without_sideways_translation(self):
        for cls, dx, dy, duration in (("person", 3.0, 2.0, 16.0), ("car", 6.0, 4.2, 32.0)):
            with self.subTest(cls=cls):
                poses = integrate(4 + duration + 0.5, cls, "ambiguity")
                self.assertAlmostEqual(dx + poses[1][0] - poses[0][0], 0.2, delta=0.025)
                self.assertAlmostEqual(-dy + poses[1][1], -0.05, delta=0.025)
                poses = integrate(4 + 2 * duration + 1.5, cls, "ambiguity")
                self.assertAlmostEqual(poses[1][0], poses[0][0], delta=0.04)
                self.assertAlmostEqual(poses[1][1], 0.0, delta=0.04)
                self.assertAlmostEqual(poses[1][2], 0.0, delta=0.01)


if __name__ == "__main__":
    unittest.main()
