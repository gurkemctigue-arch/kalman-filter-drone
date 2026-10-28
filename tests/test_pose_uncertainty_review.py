"""Independent integration regressions for measured vehicle uncertainty."""
from __future__ import annotations

from collections import deque
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_px4_adapter"))
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_nodes"))
from uav_tracking.core import Detection, TargetManager, TargetMode, TargetStatus
from uav_tracking.core.uncertainty import pose_point_covariance
from uav_tracking.core.estimator_strategies import make_state_estimator
from uav_tracking.core.kalman import ConstantVelocityKalman3D
from uav_tracking.research_labels import rpy_matrix
from uav_tracking_px4_adapter.adapter_node import px4_pose_covariance_to_enu, _matrix_to_quaternion_xyzw
from uav_tracking_nodes.state_estimator_node import StateEstimatorNode


def detection(timestamp, confidence=.95, *, extra=None, position=(10., 0., 0.)):
    metadata = {} if extra is None else {"additional_measurement_covariance":np.asarray(extra).tolist()}
    return Detection((0, 0, 20, 20), "car", confidence, timestamp, position, metadata=metadata)


class PoseUncertaintyReviewTests(unittest.TestCase):
    def manager(self, method):
        return TargetManager(min_hits=1, estimator_method=method, kf_kwargs={"measurement_noise_std":.1})

    def test_fixed_output_sensor_R_stays_fixed_while_shared_gate_adapts(self):
        extra = np.diag([.04, .2, .08])
        gate_variances = []
        for confidence in (.95, .2):
            tracker = self.manager("fixed_kf")
            tracker.update([detection(0., confidence, extra=extra)], timestamp=0.)
            track = tracker.update([detection(.1, confidence, extra=extra)], timestamp=.1)
            strategy = track._filter
            # Association/acceptance retains the adaptive quality contract.
            gate_variances.append(strategy._gate.last_measurement_covariance[0, 0])
            # Only the extra physical pose component is common to outputs;
            # a fixed sensor baseline must not receive gate's adaptive base R.
            np.testing.assert_allclose(strategy._fixed.last_measurement_covariance, np.eye(3) * .01 + extra)
        self.assertGreater(gate_variances[1], gate_variances[0])

    def test_fixed_initialization_uses_fixed_sensor_plus_pose_for_new_and_2d_tracks(self):
        extra = np.diag([.04, .2, .08])
        for starts_in_2d in (False, True):
            for confidence in (.95, .2):
                with self.subTest(starts_in_2d=starts_in_2d, confidence=confidence):
                    tracker = self.manager("fixed_kf")
                    if starts_in_2d:
                        tracker.update([detection(0., confidence, position=None)], timestamp=0.)
                    timestamp = .1 if starts_in_2d else 0.
                    track = tracker.update([detection(timestamp, confidence, extra=extra)], timestamp=timestamp)
                    expected = np.eye(3) * .01 + extra
                    np.testing.assert_allclose(track.covariance_3d, expected)
                    self.assertGreater(track._filter._gate.covariance[0, 0], expected[0, 0])

    def test_legacy_initialization_without_explicit_covariance_is_preserved(self):
        for method in ("raw", "ema", "fixed_kf", "adaptive_kf"):
            estimator = make_state_estimator(method, measurement_noise_std=.1)
            estimator.initialize([10, 0, 0], timestamp=0.)
            expected = .01 if method in {"raw", "ema"} else 1.
            np.testing.assert_allclose(np.diag(estimator.covariance)[:3], expected)
        estimator = ConstantVelocityKalman3D(measurement_noise_std=.1)
        estimator.update([10, 0, 0], timestamp=0., confidence=.2)
        np.testing.assert_allclose(estimator.covariance[:3, :3], np.eye(3))

    def test_raw_and_ema_initial_output_uncertainty_contains_the_pose_term(self):
        extra = np.diag([.1, 1., .2])
        for method in ("raw", "ema"):
            with self.subTest(method=method):
                tracker = self.manager(method)
                track = tracker.update([detection(0., extra=extra)], timestamp=0.)
                gate_position = np.diag(track._filter._gate.covariance[:3, :3])
                np.testing.assert_allclose(np.diag(track.covariance_3d), gate_position)
                self.assertTrue(np.all(np.diag(track.covariance_3d) >= np.diag(extra)))

    def test_first_world_measurement_after_2d_only_track_initializes_with_its_R(self):
        tracker = self.manager("adaptive_kf")
        tracker.update([detection(0., position=None)], timestamp=0.)
        track = tracker.update([detection(.1, extra=np.eye(3) * 25.)], timestamp=.1)
        np.testing.assert_allclose(track.covariance_3d, track._filter.last_measurement_covariance)
        self.assertGreater(track.covariance_3d[0, 0], 25.)

    def test_attitude_variance_is_rotated_from_an_arbitrary_frd_body_to_world(self):
        body_to_ned = rpy_matrix(.4, -.3, .8)
        xyzw = _matrix_to_quaternion_xyzw(body_to_ned)
        q = [xyzw[3], *xyzw[:3]]
        message = NS(position_variance=[1., 4., 9.], orientation_variance=[.01, .04, .09], q=q)
        result = px4_pose_covariance_to_enu(message)
        ned_to_enu = np.array([[0, 1, 0], [1, 0, 0], [0, 0, -1]])
        expected = ned_to_enu @ body_to_ned @ np.diag(message.orientation_variance) @ body_to_ned.T @ ned_to_enu.T
        np.testing.assert_allclose(result[3:, 3:], expected, atol=1e-12)
        self.assertGreater(abs(result[3, 4]), .001)
        np.testing.assert_allclose(result[:3, :3], np.diag([4, 1, 9]))

    def test_point_jacobian_preserves_pose_translation_rotation_cross_terms(self):
        point = np.array([7., -2., 1.5]); origin = np.array([.5, .2, 2.])
        rng = np.random.default_rng(3); matrix = rng.normal(size=(6, 6)); covariance = matrix @ matrix.T * .001
        jacobian = np.empty((3, 6)); epsilon = 1e-6
        def transformed(perturbation):
            angles = perturbation[3:]
            theta = np.linalg.norm(angles)
            rotation = np.eye(3)
            if theta:
                axis = angles / theta
                x, y, z = axis
                cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
                rotation += np.sin(theta) * cross + (1 - np.cos(theta)) * (cross @ cross)
            return origin + perturbation[:3] + rotation @ (point - origin)
        for index in range(6):
            delta = np.zeros(6); delta[index] = epsilon
            jacobian[:, index] = (transformed(delta) - transformed(-delta)) / (2 * epsilon)
        np.testing.assert_allclose(pose_point_covariance(point, origin, covariance), jacobian @ covariance @ jacobian.T, atol=1e-10)

    def test_pose_cache_rejects_a_different_child_origin(self):
        node = StateEstimatorNode.__new__(StateEstimatorNode)
        node._pose_samples = deque(maxlen=400)
        node.get_parameter = lambda name: NS(value="map" if name == "state_frame" else "base_link")
        message = NS(header=NS(stamp=NS(sec=1, nanosec=0), frame_id="map"), child_frame_id="camera_link",
                     pose=NS(pose=NS(position=NS(x=0., y=0., z=0.)), covariance=np.eye(6).reshape(-1).tolist()))
        node._on_pose_uncertainty(message)
        with self.assertRaises(ValueError):
            node._point_pose_covariance([10, 0, 0], 1.)

    def test_broad_pose_R_preserves_designated_identity_and_ambiguity(self):
        tracker = TargetManager(min_hits=1, association_mode="hybrid_3d", mode=TargetMode.LOCKED_TARGET,
                                reject_ambiguous_associations=True)
        extra = np.eye(3)
        first = tracker.update_with_result([
            Detection((0, 0, 20, 20), "car", .95, 0., (0, 0, 0), metadata={"additional_measurement_covariance":extra}),
            Detection((60, 0, 80, 20), "car", .95, 0., (1, 0, 0), metadata={"additional_measurement_covariance":extra})], timestamp=0.)
        selected = first.tracks[0].track_id
        tracker.lock_target(selected, target_uuid="requested-physical-individual")
        result = tracker.update_with_result([
            Detection((25, 0, 45, 20), "car", .95, .1, (.45, 0, 0), metadata={"additional_measurement_covariance":extra}),
            Detection((26, 0, 46, 20), "car", .95, .1, (.55, 0, 0), metadata={"additional_measurement_covariance":extra})], timestamp=.1)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.target.track_id, selected)
        self.assertEqual(tracker.target_uuid, "requested-physical-individual")
        self.assertEqual(result.target.last_measurement_timestamp, 0.)


if __name__ == "__main__":
    unittest.main()
