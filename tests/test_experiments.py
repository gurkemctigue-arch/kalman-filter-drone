from __future__ import annotations

import unittest

from uav_tracking.experiments import ESTIMATORS, run_estimator_benchmark


class ExperimentTests(unittest.TestCase):
    def test_paired_baselines_are_deterministic_and_complete(self) -> None:
        first = run_estimator_benchmark(target_class="person", seeds=[3], steps=40)
        second = run_estimator_benchmark(target_class="person", seeds=[3], steps=40)
        self.assertEqual([item.as_dict() for item in first], [item.as_dict() for item in second])
        self.assertEqual({item.estimator for item in first}, set(ESTIMATORS))
        self.assertTrue(all(item.missing_measurements > 0 for item in first))
        self.assertTrue(all(item.position_rmse_m >= 0.0 for item in first))


if __name__ == "__main__":
    unittest.main()
