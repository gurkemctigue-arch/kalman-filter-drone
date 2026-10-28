"""Clock and lag diagnostics must distinguish physical bias from delayed pose."""
from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import diagnose_px4_camera_timing as diagnosis
from evaluate_online_state_accuracy import PoseSeries


class PX4CameraTimingTests(unittest.TestCase):
    def poses(self):
        def yaw(t):
            return .4 * t + .2 * math.sin(3 * t)
        truth = PoseSeries([{"time_s":index * .025, "position_m":[0, 0, 0],
                             "quaternion_xyzw":[0, 0, math.sin(yaw(index * .025) / 2), math.cos(yaw(index * .025) / 2)]}
                            for index in range(401)])
        return truth, yaw

    def rows(self, yaw, *, delay=0., bias=0.):
        return [{"time_s":1. + index * .05, "position_m":[0, 0, .24],
                 "quaternion_xyzw":[0, 0, math.sin((yaw(1. + index * .05 - delay) + bias) / 2),
                                    math.cos((yaw(1. + index * .05 - delay) + bias) / 2)]}
                for index in range(121)]

    def test_negative_lag_identifies_a_delayed_pose_without_yaw_fit(self):
        truth, yaw = self.poses()
        rows = self.rows(yaw, delay=.1)
        alignment = {"translation_world_from_map_m":[0, 0, 0]}
        zero = diagnosis.score_pose(rows, truth, alignment, "receipt_clock", None, 0., 1., 7.)
        corrected = diagnosis.score_pose(rows, truth, alignment, "receipt_clock", None, -.1, 1., 7.)
        self.assertGreater(zero["attitude_error_rad"]["rmse"], .03)
        self.assertLess(corrected["attitude_error_rad"]["rmse"], 1e-6)
        self.assertEqual(corrected["attitude_error_rad"]["count"], 121)

    def test_constant_yaw_bias_is_reported_separately_and_not_hidden_in_primary_error(self):
        truth, yaw = self.poses()
        result = diagnosis.score_pose(self.rows(yaw, bias=.12), truth,
                                      {"translation_world_from_map_m":[0, 0, 0]}, "receipt_clock", None, 0., 1., 7.)
        self.assertAlmostEqual(result["attitude_error_rad"]["rmse"], .12, places=10)
        self.assertAlmostEqual(result["diagnostic_median_yaw_bias_rad"], .12, places=10)
        self.assertLess(result["diagnostic_yaw_after_median_removal_rad"]["rmse"], 1e-10)

    def test_time_map_uses_receive_pairs_and_rejects_heldout_discontinuities(self):
        rows = [{"time_s":index * .05, "timestamp_s":1_700_000_000. + index * .05}
                for index in range(161)]
        stable = diagnosis.fit_clock_map(rows)
        self.assertTrue(stable["valid_for_source_timestamping"])
        self.assertAlmostEqual(stable["slope_sim_per_px4"], 1., places=7)
        for row in rows:
            if row["time_s"] > 5.:
                row["timestamp_s"] += 10.
        invalid = diagnosis.fit_clock_map(rows)
        self.assertFalse(invalid["valid_for_source_timestamping"])
        self.assertGreater(invalid["holdout_receipt_minus_mapped_publish_s"]["max_absolute"], 9.)

    def test_source_publication_and_sample_domains_stay_distinct(self):
        row = {"time_s":3., "timestamp_s":103., "timestamp_sample_s":102.95}
        mapping = {"slope_sim_per_px4":1., "px4_origin_s":100., "sim_intercept_s":0.}
        self.assertEqual(diagnosis.mapped_time(row, "receipt_clock", mapping), 3.)
        self.assertEqual(diagnosis.mapped_time(row, "source_sample_identity", mapping), 102.95)
        self.assertAlmostEqual(diagnosis.mapped_time(row, "affine_sample", mapping), 2.95)
        self.assertAlmostEqual(diagnosis.mapped_time(row, "affine_publish", mapping), 3.)


if __name__ == "__main__":
    unittest.main()
