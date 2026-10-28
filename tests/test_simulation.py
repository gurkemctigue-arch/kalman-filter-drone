"""Smoke tests for the deterministic closed-loop demonstration."""

from __future__ import annotations

import unittest

from uav_tracking.simulation import run_demo


class SimulationTests(unittest.TestCase):
    def test_unique_person_demo_is_deterministic(self) -> None:
        first = run_demo(mode="auto_unique", target_class="person", steps=30, seed=2)
        second = run_demo(mode="auto_unique", target_class="person", steps=30, seed=2)
        self.assertEqual(first.as_dict(), second.as_dict())
        self.assertGreater(first.completed_steps, 0)

    def test_locked_car_demo_does_not_report_ambiguous_after_initial_selection(self) -> None:
        result = run_demo(mode="locked_target", target_class="car", steps=80, seed=4)
        self.assertGreater(result.completed_steps, 0)
        self.assertEqual(result.ambiguous_frames, 0)
        self.assertGreaterEqual(result.reacquired_frames, 1)


if __name__ == "__main__":
    unittest.main()
