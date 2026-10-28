"""Physical covariance propagation, independent of ROS and simulator truth."""
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_px4_adapter"))
from uav_tracking.core.uncertainty import pose_point_covariance
from uav_tracking.core import Detection, TargetManager
from uav_tracking_px4_adapter.adapter_node import px4_pose_covariance_to_enu


class PoseUncertaintyTests(unittest.TestCase):
    def test_yaw_uncertainty_grows_with_range_squared_in_lateral_axis(self):
        pose = np.diag([.01, .01, .04, 0., 0., .1**2])
        near = pose_point_covariance([5, 0, 0], [0, 0, 0], pose)
        far = pose_point_covariance([10, 0, 0], [0, 0, 0], pose)
        np.testing.assert_allclose(np.diag(near), [.01, .26, .04])
        np.testing.assert_allclose(np.diag(far), [.01, 1.01, .04])

    def test_rotation_of_world_axes_rotates_point_uncertainty(self):
        covariance = np.diag([.01, .02, .03, .04, .05, .06])
        rotation = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
        transform = np.zeros((6, 6)); transform[:3, :3] = rotation; transform[3:, 3:] = rotation
        point = np.array([4., 2., 1.]); body = np.array([1., -1., .2])
        first = pose_point_covariance(point, body, covariance)
        second = pose_point_covariance(rotation @ point, rotation @ body, transform @ covariance @ transform.T)
        np.testing.assert_allclose(second, rotation @ first @ rotation.T)

    def test_bad_covariance_cannot_be_treated_as_zero_uncertainty(self):
        for covariance in (np.full((6, 6), np.nan), -np.eye(6), np.ones((3, 3))):
            with self.subTest(covariance=covariance.shape), self.assertRaises(ValueError):
                pose_point_covariance([1, 0, 0], [0, 0, 0], covariance)

    def test_px4_body_attitude_covariance_is_rotated_to_world_enu(self):
        message = NS(position_variance=[1., 4., 9.], orientation_variance=[.01, .04, .09], q=[1., 0., 0., 0.])
        result = px4_pose_covariance_to_enu(message)
        np.testing.assert_allclose(np.diag(result), [4., 1., 9., .04, .01, .09])
        message.orientation_variance[2] = float("nan")
        self.assertIsNone(px4_pose_covariance_to_enu(message))

    def test_all_estimators_use_same_pose_covariance_in_association_and_fusion(self):
        for method in ("raw", "ema", "fixed_kf", "adaptive_kf"):
            with self.subTest(method=method):
                tracker = TargetManager(min_hits=1, estimator_method=method, association_mode="hybrid_3d", gate_threshold=9.21)
                extra = np.diag([.01, 1., .04])
                def detection(t, y):
                    return Detection((0, 0, 20, 20), "car", .95, t, (10., y, 0.),
                                     metadata={"additional_measurement_covariance": extra.tolist()})
                first = tracker.update([detection(0., 0.)], timestamp=0.)
                updated = tracker.update([detection(.1, .8)], timestamp=.1)
                self.assertEqual(updated.track_id, first.track_id)
                self.assertEqual(updated.last_measurement_timestamp, .1)
                np.testing.assert_allclose(updated.last_measurement_diagnostics["additional_pose_covariance"], extra)
                self.assertGreater(updated.last_measurement_diagnostics["measurement_covariance"][1][1], 1.)
                self.assertEqual(updated.last_measurement_diagnostics["gate_threshold"], 9.21)


if __name__ == "__main__":
    unittest.main()
