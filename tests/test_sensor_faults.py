import importlib.util
from pathlib import Path
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location("sensor_fault_bridge", Path(__file__).parents[1] / "scripts/sensor_fault_bridge.py")
faults = importlib.util.module_from_spec(spec)
spec.loader.exec_module(faults)


class SensorFaultTests(unittest.TestCase):
    def test_seeded_depth_preserves_invalid_and_input(self):
        original = np.full((80, 80), 5.0, dtype=np.float32)
        original[0, 0] = np.nan
        first = faults.perturb_depth(original, seed=4, stamp_ns=1_000_000_000, noise_std_m=.05, hole_fraction=.2)
        second = faults.perturb_depth(original, seed=4, stamp_ns=1_000_000_000, noise_std_m=.05, hole_fraction=.2)
        np.testing.assert_equal(first, second)
        self.assertTrue(np.isnan(first[0, 0]))
        self.assertEqual(original[1, 1], 5.0)
        self.assertGreater(np.isnan(first).mean(), .15)
        self.assertLess(np.isnan(first).mean(), .25)
        self.assertGreater(np.nanstd(first), .03)

    def test_drop_is_acquisition_window_based(self):
        decisions = [faults.frame_dropped(7, n * 200_000_000, .2) for n in range(1000)]
        self.assertGreater(sum(decisions), 150)
        self.assertLess(sum(decisions), 250)
        for n in range(100):
            self.assertEqual(faults.frame_dropped(7, n * 200_000_000, .2),
                             faults.frame_dropped(7, n * 200_000_000 + 50_000_000, .2))

    def test_clean_is_unchanged(self):
        data = np.array([[1, 2], [np.nan, 3]], dtype=np.float32)
        np.testing.assert_equal(faults.perturb_depth(data, seed=0, stamp_ns=0), data)
        self.assertFalse(faults.frame_dropped(0, 0, 0))
        self.assertTrue(faults.frame_dropped(0, 0, 1))
