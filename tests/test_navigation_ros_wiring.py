"""Exercise measured RGB-D -> selected identity -> independent nav state."""
from pathlib import Path
from collections import deque
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_nodes"))
from uav_tracking.core import Detection, TargetManager
from uav_tracking.core.navigation import NavigationPrior
from uav_tracking.core.uncertainty import pose_point_covariance
from uav_tracking_nodes.navigation_estimator import NavigationEstimator
from uav_tracking_nodes import state_estimator_node as adapter


def header(t=1.0):
    return NS(stamp=NS(sec=int(t), nanosec=round((t % 1) * 1e9)), frame_id="camera")


class NavigationWiringTests(unittest.TestCase):
    def setUp(self):
        self.node = adapter.StateEstimatorNode.__new__(adapter.StateEstimatorNode)
        self.node._manager = TargetManager(min_hits=1)
        self.node._navigation_estimator = NavigationEstimator(gate_threshold=9.21)
        self.node._navigation_prior = NavigationPrior("car", 4.5, 1.8, 1.5)
        self.node._navigation_transform = np.eye(4)
        self.node._navigation_transform[:3, 3] = [0, 0, 3]
        self.node._navigation_transform_key = ((1, 0), "camera")
        self.node.get_parameter = lambda name: NS(value=.05)
        self.node.get_clock = lambda: NS(now=lambda: NS(nanoseconds=1_050_000_000))
        x, y = np.meshgrid(np.linspace(7, 14, 22), np.linspace(-3, 3, 18))
        ground = np.column_stack([x.ravel(), y.ravel(), np.full(x.size, -3.)])
        y, z = np.meshgrid(np.linspace(-.9, .9, 30), np.linspace(.2, 1.3, 20))
        endface = np.column_stack([np.full(y.size, 10.), y.ravel(), z.ravel() - 3])
        self.source = NS(header=header(), navigation_ground_points_camera_m=ground.ravel().tolist())
        self.observation = NS(candidate_id=7, camera_frame="camera", header=header(),
                              class_name="car", confidence=.95, depth_valid_ratio=.83, depth_std_m=.04,
                              navigation_bbox_complete=True,
                              navigation_points_camera_m=endface.ravel().tolist(),
                              navigation_bottom_ray_camera=NS(x=1., y=0., z=-.3))
        self.result = self.node._manager.update_with_result([
            Detection((10, 10, 100, 100), "car", .95, 1., (10, 0, 1), metadata={"candidate_id": 7})], timestamp=1.)

    def test_accepted_surface_candidate_yields_independent_ground_center(self):
        self.node._update_navigation(self.result, [self.observation], self.source, 1.)
        diagnostic = self.node._navigation_last_diagnostics
        self.assertTrue(diagnostic["reference_valid"], diagnostic)
        self.assertTrue(diagnostic["fusion_accepted"], diagnostic)
        np.testing.assert_allclose(diagnostic["raw_position_world_m"], [12.25, 0, 0], atol=.05)
        # Surface association and its timestamp are unchanged by navigation.
        np.testing.assert_allclose(self.result.target.position_3d, [10, 0, 1])
        self.assertEqual(self.result.target.last_measurement_timestamp, 1.)

    def test_covariance_components_reconstruct_the_exact_fused_R_with_pose_provenance(self):
        self.node._propagate_vehicle_uncertainty = True
        covariance = np.diag([.01, .02, .03, .001, .002, .003])
        origin = np.array([.5, -.2, 3.])
        self.node._pose_samples = deque([
            (.97, np.zeros(3), np.eye(6)), (1.01, origin.copy(), covariance.copy())])
        self.node.get_parameter = lambda name: NS(value="map" if name == "state_frame" else .05)
        self.node._update_navigation(self.result, [self.observation], self.source, 1.)
        diagnostic = self.node._navigation_last_diagnostics
        self.assertTrue(diagnostic["fusion_accepted"], diagnostic)
        self.assertEqual(diagnostic["chosen_pose_source_s"], 1.01)
        geometry_R = np.asarray(diagnostic["reference_covariance_geometry"])
        recorded_pose_R = np.asarray(diagnostic["reference_covariance_pose"])
        independently_propagated_R = pose_point_covariance(
            diagnostic["raw_position_world_m"], diagnostic["chosen_pose_position_world_m"],
            diagnostic["chosen_pose_covariance_world_6x6"])
        np.testing.assert_allclose(recorded_pose_R, independently_propagated_R)
        np.testing.assert_allclose(geometry_R + recorded_pose_R, diagnostic["reference_covariance_total"])
        np.testing.assert_allclose(diagnostic["reference_covariance_total"], diagnostic["reference_covariance"])
        np.testing.assert_allclose(diagnostic["fusion"]["measurement_covariance"], geometry_R + recorded_pose_R)
        np.testing.assert_allclose(diagnostic["pose_lever_world_m"],
                                   np.asarray(diagnostic["raw_position_world_m"]) - origin)
        self.assertEqual(diagnostic["measurement_processing_s"], 1.05)
        self.assertEqual(diagnostic["depth_valid_ratio"], .83)
        self.assertEqual(diagnostic["depth_std_m"], .04)
        self.assertEqual(diagnostic["confidence"], .95)
        self.assertFalse(diagnostic["quality_scale_applied"])
        # Later pose-cache mutation cannot rewrite recorded measurement evidence.
        self.node._pose_samples[-1][2][0, 0] = 900.
        self.assertEqual(diagnostic["chosen_pose_covariance_world_6x6"][0][0], .01)

    def test_declared_pose_term_is_explicit_and_not_a_fabricated_pose_sample(self):
        self.node._update_navigation(self.result, [self.observation], self.source, 1.)
        diagnostic = self.node._navigation_last_diagnostics
        self.assertEqual(diagnostic["pose_uncertainty_source"], "declared_isotropic_position_std")
        self.assertNotIn("chosen_pose_source_s", diagnostic)
        np.testing.assert_allclose(diagnostic["reference_covariance_pose"], np.eye(3) * .05**2)

    def test_missing_and_nonfinite_quality_are_null_without_changing_geometry_or_crashing_json(self):
        import json
        for name in ("confidence", "depth_valid_ratio", "depth_std_m"):
            for missing in (True, False):
                with self.subTest(name=name, missing=missing):
                    self.setUp()
                    if missing:
                        delattr(self.observation, name)
                    else:
                        setattr(self.observation, name, float("nan"))
                    self.node._update_navigation(self.result, [self.observation], self.source, 1.)
                    diagnostic = self.node._navigation_last_diagnostics
                    self.assertTrue(diagnostic["fusion_accepted"], diagnostic)
                    self.assertIsNone(diagnostic[name])
                    self.assertIn(name, diagnostic["missing_quality_fields" if missing else "invalid_quality_fields"])
                    json.dumps(diagnostic, allow_nan=False)

    def test_truncated_or_wrong_stamp_support_cannot_create_navigation_state(self):
        for defect in ("truncated", "wrong_stamp", "no_ground", "mixed_frames"):
            with self.subTest(defect=defect):
                self.setUp()
                if defect == "truncated":
                    self.observation.navigation_bbox_complete = False
                elif defect == "wrong_stamp":
                    self.node._navigation_transform_key = ((0, 0), "camera")
                elif defect == "no_ground":
                    self.source.navigation_ground_points_camera_m = []
                else:
                    self.source.header.frame_id = "another_depth_camera"
                self.node._update_navigation(self.result, [self.observation], self.source, 1.)
                self.assertFalse(self.node._navigation_last_diagnostics["fusion_accepted"])
                snapshot = self.node._navigation_estimator.project(
                    1., target_uuid=self.node._manager.target_uuid,
                    track_id=self.result.target.track_id, surface_status="tracking")
                self.assertFalse(snapshot.valid)

    def test_unselected_candidate_depth_is_never_used_for_selected_navigation(self):
        self.observation.candidate_id = 8
        self.node._update_navigation(self.result, [self.observation], self.source, 1.)
        self.assertFalse(self.node._navigation_last_diagnostics["reference_valid"])
        self.assertFalse(self.node._navigation_last_diagnostics["fusion_accepted"])

    def test_malformed_optional_geometry_is_reported_without_stopping_surface_tracking(self):
        with patch.object(self.node, "_navigation_reference", side_effect=ValueError("bad sensor geometry")):
            self.node._update_navigation(self.result, [self.observation], self.source, 1.)
        diagnostic = self.node._navigation_last_diagnostics
        self.assertFalse(diagnostic["reference_valid"])
        self.assertFalse(diagnostic["fusion_accepted"])
        self.assertIn("bad sensor geometry", diagnostic["reference_reason"])
        self.assertIsNotNone(self.result.target.position_3d)

    def test_nonfinite_pose_uncertainty_is_invalid_and_json_serializable(self):
        import json
        self.node.get_parameter = lambda name: NS(value=float("nan"))
        self.node._update_navigation(self.result, [self.observation], self.source, 1.)
        diagnostic = self.node._navigation_last_diagnostics
        self.assertFalse(diagnostic["reference_valid"])
        json.dumps(diagnostic, allow_nan=False)

    def test_uninitialized_navigation_publication_contains_no_surface_values(self):
        published, diagnostics = [], []
        self.node._navigation_publisher = NS(publish=published.append)
        self.node._navigation_diagnostics_publisher = NS(publish=diagnostics.append)
        self.node._navigation_last_diagnostics = {}
        states = NS(STATE_MEASURED=1, STATE_PREDICTED=2, STATE_LOST=3, STATE_AMBIGUOUS=4)
        surface = NS(header=header(), state=1, target_uuid=self.node._manager.target_uuid,
                     track_id=self.result.target.track_id, target_visible=True,
                     position_m=NS(x=10., y=0., z=1.), velocity_mps=NS(x=.5, y=0., z=0.),
                     covariance=[1.] * 36, prediction_age_s=0.)
        self.node.get_parameter = lambda name: NS(value=.75)
        with patch.object(adapter, "TargetState", states, create=True), \
                patch.object(adapter, "String", lambda: NS(data=""), create=True):
            self.node._publish_navigation(surface, self.result)
        message = published[0]
        self.assertEqual(message.state, 3)
        self.assertEqual([message.position_m.x, message.position_m.y, message.position_m.z], [0., 0., 0.])
        self.assertEqual(message.velocity_mps.x, 0.)
        self.assertEqual(message.covariance, [0.] * 36)
        self.assertFalse(message.target_visible)
        self.assertEqual(surface.position_m.x, 10.)
        import json
        output = json.loads(diagnostics[0].data)
        self.assertEqual(output["output_s"], 1.)
        self.assertEqual(output["output_publication_s"], 1.05)
        self.assertEqual(output["output_target_uuid"], surface.target_uuid)
        self.assertEqual(output["output_track_id"], surface.track_id)
        self.assertFalse(output["valid"])
        self.assertIsNone(output["output_position_world_m"])
        self.assertIsNone(output["output_covariance_world_6x6"])


if __name__ == "__main__":
    unittest.main()
