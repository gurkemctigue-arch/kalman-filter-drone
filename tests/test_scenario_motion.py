"""Deterministic physical scenario timing, independent of tracker state."""

import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "scenario_motion_under_test",
    Path(__file__).resolve().parents[1] / "ros2_ws/src/uav_tracking_bringup/uav_tracking_bringup/scenario_motion.py",
)
motion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(motion)


class ScenarioMotionTests(unittest.TestCase):
    def test_takeoff_stationary_and_visual_hold_does_not_pause_target(self):
        timeline = motion.MotionTimeline()
        timeline.on_phase("TAKEOFF: climb", 4.0)
        self.assertEqual(timeline.command(8.0), (0.0, 0.0))
        timeline.on_phase("FOLLOW: ready", 10.0)
        self.assertAlmostEqual(timeline.command(11.0)[0], 0.25)
        timeline.on_phase("HOLD: target lost", 12.0)
        self.assertAlmostEqual(timeline.command(22.0)[1], 0.07)
        timeline.on_phase("FOLLOW: reacquired", 23.0)
        self.assertEqual(timeline.started_s, 10.0)
        timeline.on_phase("ABORTED: flight ended", 24.0)
        timeline.on_phase("FOLLOW: cannot restart", 25.0)
        self.assertEqual(timeline.command(28.0), (0.0, 0.0))

    def test_profile_has_bounded_speed_and_both_gentle_turns(self):
        self.assertEqual(motion.motion_profile(0.0), (0.0, 0.0))
        self.assertEqual(motion.motion_profile(5.0), (0.5, 0.0))
        self.assertAlmostEqual(motion.motion_profile(15.0)[1], 0.07)
        self.assertAlmostEqual(motion.motion_profile(35.0)[1], -0.07)
        for step in range(1501):
            speed, turn = motion.motion_profile(step / 10.0)
            self.assertLessEqual(abs(speed), 0.5)
            self.assertLessEqual(abs(turn), 0.07)

    def test_optional_speed_changes_decelerate_accelerate_without_discontinuity(self):
        self.assertGreater(motion.motion_profile(8,.5,"speed_changes")[0],motion.motion_profile(12,.5,"speed_changes")[0])
        self.assertLess(motion.motion_profile(18,.5,"speed_changes")[0],motion.motion_profile(22,.5,"speed_changes")[0])
        for t in (8,12,18,22,28,32,36,40,50):
            before=motion.motion_profile(t-1e-6,.5,"speed_changes")[0]
            after=motion.motion_profile(t+1e-6,.5,"speed_changes")[0]
            self.assertLess(abs(after-before),1e-6)
        for step in range(1001):
            t=step*.1
            changed=motion.motion_profile(t,.5,"speed_changes")
            standard=motion.motion_profile(t,.5)
            self.assertEqual(changed[1],standard[1])
            self.assertLessEqual(changed[0],.5)
            self.assertGreaterEqual(changed[0],0)

    def test_standard_default_and_variant_validation(self):
        for t in (0,1,10,15,20,35,49,50,55):
            self.assertEqual(motion.motion_profile(t),motion.motion_profile(t,motion_profile_kind="standard"))
        with self.assertRaises(ValueError):motion.motion_profile(1,motion_profile_kind="typo")


if __name__ == "__main__":
    unittest.main()
