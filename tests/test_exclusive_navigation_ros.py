"""Native E-only ROS transport and authorization, without ROS or a simulator.

These tests keep the original selected task fixed and perturb dependencies that
the new reference must not consume. They do not certify physical identity.
"""
from collections import deque
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_nodes"))
from uav_tracking.core import CameraIntrinsics, TargetStatus
from uav_tracking.core.exclusive_navigation import METHOD, MAX_EXCLUSIVE_PIXELS
from uav_tracking.core.uncertainty import pose_point_covariance
from uav_tracking_nodes import detector_node as detector
from uav_tracking_nodes import state_estimator_node as adapter
from tests import test_detector_worker as workers
from tests import test_navigation_ros_wiring as legacy


class ExclusiveNavigationAuthorizationTests(unittest.TestCase):
    def frame(self, selected_index=0):
        fixture = legacy.NavigationWiringTests()
        fixture.setUp()
        result, observations, source, pair = fixture.directed_frame(selected_index)
        node = fixture.node
        node._navigation_exclusive_enabled = True
        for item in observations:
            points = list(item.navigation_visibility_support_camera_m)
            item.navigation_exclusive_depth_complete = True
            item.navigation_exclusive_expected_pixel_count = len(points)//3
            item.navigation_exclusive_valid_pixel_count = len(points)//3
            item.navigation_exclusive_reason = "complete_native_exclusive"
            item.navigation_exclusive_points_camera_m = points
        return node, result, observations, source, pair

    def test_selected_behind_has_separate_reference_without_identity_reassociation(self):
        node, result, observations, source, _ = self.frame(selected_index=1)
        target = result.target
        surface_position = np.asarray(target.position_3d).copy()
        with patch.object(node, "_navigation_visibility", side_effect=AssertionError("legacy visibility consumed")), \
                patch.object(adapter, "estimate_footprint_from_points", side_effect=AssertionError("legacy center consumed")), \
                patch.object(node._manager, "update_with_result", side_effect=AssertionError("second association")), \
                patch.object(adapter, "estimate_exclusive_reference", wraps=adapter.estimate_exclusive_reference) as fit:
            node._update_navigation(result, observations, source, 1.)
        diagnostic = node._navigation_last_diagnostics
        self.assertTrue(diagnostic["reference_valid"], diagnostic)
        self.assertTrue(diagnostic["fusion_accepted"], diagnostic)
        self.assertEqual(fit.call_count, 1)
        self.assertEqual(diagnostic["navigation_reference_path"], METHOD)
        self.assertEqual(diagnostic["reference_reason"], "exclusive_conditional_single_face_center")
        self.assertFalse(diagnostic["geometry"]["identity_assessed"])
        self.assertEqual(node._manager.target_uuid, "explicit_task")
        self.assertEqual(node._manager.target_track_id, target.track_id)
        np.testing.assert_array_equal(target.position_3d, surface_position)
        self.assertEqual(target.last_measurement_timestamp, 1.)

    def test_shared_pixels_other_geometry_and_full_box_cannot_change_E_measurement(self):
        node, result, observations, source, pair = self.frame(selected_index=1)
        original, _ = node._navigation_reference(result, observations, source, 1.)
        self.assertTrue(original.valid, original.reason)
        # Keep rectangle/association metadata, but make every forbidden depth
        # source unusable. E of the already accepted selected task is unchanged.
        pair.points_camera_m = [float("nan")]
        pair.depth_complete, pair.valid_pixel_count = False, 0
        pair.expected_pixel_count = 1
        observations[0].navigation_points_camera_m = [float("inf")]
        observations[0].navigation_visibility_support_camera_m = []
        observations[0].navigation_exclusive_points_camera_m = []
        observations[1].navigation_points_camera_m = []
        observations[1].navigation_visibility_support_camera_m = [float("nan")]
        changed, details = node._navigation_reference(result, observations, source, 1.)
        self.assertTrue(changed.valid, (changed.reason, details))
        np.testing.assert_array_equal(changed.position_world_m, original.position_world_m)
        np.testing.assert_array_equal(changed.covariance, original.covariance)
        self.assertEqual(node._manager.target_uuid, "explicit_task")

    def test_large_unknown_shared_rectangle_does_not_apply_legacy_depth_budget_to_E(self):
        node, result, observations, source, pair = self.frame()
        box_a, box_b = [10., 10., 180., 150.], [99.5, 99.5, 240., 220.]
        for item, box in zip(observations, (box_a, box_b)):
            for field, value in zip(("bbox_x_min_px", "bbox_y_min_px", "bbox_x_max_px", "bbox_y_max_px"), box):
                setattr(item, field, value)
        pair.bbox_a_px, pair.bbox_b_px = box_a, box_b
        pair.u0, pair.v0, pair.width, pair.height = 99, 99, 81, 51
        pair.expected_pixel_count = 81*51
        pair.valid_pixel_count, pair.depth_complete, pair.points_camera_m = 0, False, []
        self.assertGreater(pair.expected_pixel_count, adapter.MAX_OVERLAP_PIXELS)
        node._update_navigation(result, observations, source, 1.)
        diagnostic = node._navigation_last_diagnostics
        self.assertTrue(diagnostic["fusion_accepted"], diagnostic)
        self.assertEqual(diagnostic["exclusive_navigation"]["valid_pixels"], 384)
        self.assertEqual(node._manager.target_uuid, "explicit_task")

    def test_incomplete_missing_malformed_or_overbudget_E_never_falls_back(self):
        for defect in ("hole", "missing", "over_budget", "count", "nonfinite", "zero_depth", "empty", "bool_count"):
            with self.subTest(defect=defect):
                node, result, observations, source, _ = self.frame()
                item = observations[0]
                if defect == "hole":
                    item.navigation_exclusive_depth_complete = False
                    item.navigation_exclusive_valid_pixel_count -= 1
                elif defect == "missing":
                    del item.navigation_exclusive_reason
                elif defect == "over_budget":
                    item.navigation_exclusive_expected_pixel_count = MAX_EXCLUSIVE_PIXELS + 1
                    item.navigation_exclusive_valid_pixel_count = MAX_EXCLUSIVE_PIXELS + 1
                elif defect == "count":
                    item.navigation_exclusive_points_camera_m.pop()
                elif defect == "nonfinite":
                    item.navigation_exclusive_points_camera_m[0] = float("nan")
                elif defect == "zero_depth":
                    item.navigation_exclusive_points_camera_m[2] = 0.
                elif defect == "empty":
                    item.navigation_exclusive_points_camera_m = []
                else:
                    item.navigation_exclusive_expected_pixel_count = True
                with patch.object(adapter, "estimate_exclusive_reference", side_effect=AssertionError("invalid E consumed")), \
                        patch.object(adapter, "estimate_footprint_from_points", side_effect=AssertionError("full-box fallback")):
                    node._update_navigation(result, observations, source, 1.)
                self.assertFalse(node._navigation_last_diagnostics["reference_valid"])
                self.assertFalse(node._navigation_last_diagnostics["fusion_accepted"])
                self.assertEqual(node._manager.target_uuid, "explicit_task")

    def test_lost_ambiguous_unmatched_or_stale_task_cannot_authorize_geometry(self):
        for defect in ("lost", "ambiguous", "unmatched", "stale", "no_detection"):
            with self.subTest(defect=defect):
                node, result, observations, source, _ = self.frame()
                if defect in ("lost", "ambiguous"):
                    result = NS(target=result.target, status=getattr(TargetStatus, defect.upper()))
                elif defect == "unmatched":
                    result.target._matched_this_frame = False
                elif defect == "stale":
                    result.target.last_measurement_timestamp = .9
                else:
                    result.target.last_detection = None
                with patch.object(adapter, "estimate_exclusive_reference", side_effect=AssertionError("unauthorized geometry")):
                    node._update_navigation(result, observations, source, 1.)
                self.assertFalse(node._navigation_last_diagnostics["fusion_accepted"])

    def test_competitors_cannot_be_omitted_relabelled_or_reused(self):
        for defect in ("third_omitted", "missing_pair", "duplicate_pair", "duplicate_observation",
                       "unmatched_other", "cross_class", "nested", "wrong_stamp", "wrong_frame", "wrong_rectangle"):
            with self.subTest(defect=defect):
                node, result, observations, source, pair = self.frame()
                if defect == "third_omitted":
                    third = deepcopy(observations[1])
                    third.candidate_id = 9
                    third.bbox_x_min_px, third.bbox_y_min_px = 80., 70.
                    observations.append(third)
                elif defect == "missing_pair":
                    source.navigation_overlaps = []
                elif defect == "duplicate_pair":
                    source.navigation_overlaps.append(deepcopy(pair))
                    observations[0].navigation_overlap_count = 2
                elif defect == "duplicate_observation":
                    observations.append(deepcopy(observations[1]))
                elif defect == "unmatched_other":
                    next(track for track in node._manager.tracks
                         if track.last_detection.metadata["candidate_id"] == 8)._matched_this_frame = False
                elif defect == "cross_class":
                    observations[1].class_name, observations[1].class_id = "person", 0
                    pair.class_b_id = 0
                elif defect == "nested":
                    observations[1].bbox_x_min_px, observations[1].bbox_y_min_px = 20., 20.
                    observations[1].bbox_x_max_px, observations[1].bbox_y_max_px = 80., 80.
                    pair.bbox_b_px = [20., 20., 80., 80.]
                elif defect == "wrong_stamp":
                    observations[1].header = legacy.header(.9)
                elif defect == "wrong_frame":
                    observations[1].camera_frame = "other_camera"
                else:
                    pair.width = 2
                with patch.object(adapter, "estimate_exclusive_reference", side_effect=AssertionError("uncertain competitor")):
                    node._update_navigation(result, observations, source, 1.)
                self.assertFalse(node._navigation_last_diagnostics["fusion_accepted"])
                self.assertEqual(node._manager.target_uuid, "explicit_task")

    def test_original_same_stamp_ground_locality_and_pose_covariance_are_retained(self):
        node, result, observations, source, _ = self.frame(selected_index=1)
        node._propagate_vehicle_uncertainty = True
        covariance = np.diag([.01, .02, .03, .001, .002, .003])
        origin = np.array([.5, -.2, 3.])
        node._pose_samples = deque([(1., origin.copy(), covariance.copy())])
        node.get_parameter = lambda name: NS(value="map" if name == "state_frame" else .05)
        node._update_navigation(result, observations, source, 1.)
        diagnostic = node._navigation_last_diagnostics
        self.assertTrue(diagnostic["fusion_accepted"], diagnostic)
        pose_R = pose_point_covariance(diagnostic["raw_position_world_m"], origin, covariance)
        np.testing.assert_allclose(diagnostic["reference_covariance_pose"], pose_R)
        np.testing.assert_allclose(diagnostic["reference_covariance_total"],
            np.asarray(diagnostic["reference_covariance_geometry"]) + pose_R)
        np.testing.assert_allclose(diagnostic["fusion"]["measurement_covariance"],
                                   diagnostic["reference_covariance_total"])
        self.assertEqual(diagnostic["chosen_pose_source_s"], 1.)
        for defect in ("stamp", "no_ground", "distant_ground"):
            with self.subTest(defect=defect):
                node, result, observations, source, _ = self.frame()
                if defect == "stamp":
                    node._navigation_transform_key = ((0, 0), "camera")
                elif defect == "no_ground":
                    source.navigation_ground_points_camera_m = []
                else:
                    ground = np.asarray(source.navigation_ground_points_camera_m).reshape(-1, 3)
                    ground[:, 0] += 100.  # Optical x is lateral world position.
                    source.navigation_ground_points_camera_m = ground.ravel().tolist()
                node._update_navigation(result, observations, source, 1.)
                self.assertFalse(node._navigation_last_diagnostics["fusion_accepted"])

    def test_disabled_parameter_retains_original_back_target_veto(self):
        node, result, observations, source, _ = self.frame(selected_index=1)
        node._navigation_exclusive_enabled = False
        with patch.object(adapter, "estimate_exclusive_reference", side_effect=AssertionError("disabled method")):
            node._update_navigation(result, observations, source, 1.)
        diagnostic = node._navigation_last_diagnostics
        self.assertFalse(diagnostic["fusion_accepted"])
        self.assertEqual(diagnostic["navigation_reference_path"], "legacy_full_support")
        self.assertEqual(diagnostic["visibility"]["reason"], "depth_order_uncertain_or_behind")


class ExclusiveDetectorTransportTests(unittest.TestCase):
    @staticmethod
    def evidence(depth, boxes, **changes):
        values = dict(enabled=True, class_name="car", inside=True, overlap_count=1,
                      depth_scale=1., min_depth_m=.2, max_depth_m=50.)
        values.update(changes)
        return detector.navigation_exclusive_evidence(depth, CameraIntrinsics(100., 100., 50., 50.),
            boxes[0][3], boxes, boxes[0][0], **values)

    def test_all_visible_classes_excluded_and_shared_depth_changes_do_not_enter_E(self):
        boxes = [(7, .9, 2, [10., 10., 70., 70.]),
                 (8, .9, 0, [40.2, 20.2, 80., 80.]),
                 (9, .9, 3, [20.2, 40.2, 35.1, 90.])]
        depth = np.full((100, 100), 5.)
        original = depth.copy()
        first = self.evidence(depth, boxes)
        self.assertTrue(first["valid"], first)
        points = np.asarray(first["points_camera_m"]).reshape(-1, 3)
        u, v = np.rint(100*points[:, :2]/points[:, 2:3]+50).astype(int).T
        for _, _, _, box in boxes[1:]:
            lower, upper = np.floor(box[:2]), np.ceil(box[2:])
            self.assertFalse(np.any((u >= lower[0]) & (u < upper[0]) & (v >= lower[1]) & (v < upper[1])))
        np.testing.assert_array_equal(depth, original)
        depth[20:80, 40:80] = np.nan
        depth[40:90, 20:36] = 49.
        changed = self.evidence(depth, boxes)
        self.assertTrue(changed["valid"], changed)
        np.testing.assert_array_equal(changed["points_camera_m"], first["points_camera_m"])
        self.assertEqual(first["expected_pixels"], len(points))

    def test_holes_budget_and_ineligible_inputs_do_not_publish_partial_E(self):
        boxes = [(7, .9, 2, [10., 10., 70., 70.]), (8, .9, 2, [40., 20., 80., 80.])]
        depth = np.full((100, 100), 5.)
        depth[12, 12] = np.nan
        hole = self.evidence(depth, boxes)
        self.assertFalse(hole["valid"])
        self.assertEqual(hole["valid_pixels"], hole["expected_pixels"]-1)
        self.assertEqual(hole["points_camera_m"], [])
        budget = self.evidence(np.full((200, 200), 5.),
            [(7, .9, 2, [5., 5., 190., 190.]), (8, .9, 2, [185., 10., 195., 180.])])
        self.assertFalse(budget["valid"])
        self.assertGreater(budget["expected_pixels"], MAX_EXCLUSIVE_PIXELS)
        self.assertEqual(budget["points_camera_m"], [])
        for changes in (dict(enabled=False), dict(class_name="person"), dict(inside=False), dict(overlap_count=0)):
            with self.subTest(changes=changes), \
                    patch.object(detector, "extract_native_exclusive", side_effect=AssertionError("ineligible extraction")):
                self.assertFalse(self.evidence(depth, boxes, **changes)["valid"])

    def test_inference_publishes_separate_native_fields_without_replacing_legacy_clouds(self):
        fixture = workers.DetectorSchedulingTests()
        self.addCleanup(fixture.doCleanups)
        node, warnings = fixture.make_node()
        node._navigation_enabled = node._navigation_exclusive_enabled = True
        node._camera_size = (100, 100)
        node._intrinsics = CameraIntrinsics(100., 100., 50., 50.)
        original_parameter = node.get_parameter
        node.get_parameter = lambda name: NS(value={"class_id": 2, "class_name": "car"}[name]) \
            if name in {"class_id", "class_name"} else original_parameter(name)
        selected_box, other_box = [20., 20., 60., 80.], [56.25, 32.25, 72.25, 72.25]
        boxes = [NS(conf=[.9], cls=[2], xyxy=[np.array(selected_box)]),
                 NS(conf=[.9], cls=[0], xyxy=[np.array(other_box)])]
        diagnostics, observations = fixture.configure_fake_inference(node, lambda *_a, **_kw: [NS(boxes=boxes)])
        native_depth = np.full((100, 100), 5., dtype=np.float32)
        node._bridge = NS(imgmsg_to_cv2=lambda msg, desired_encoding:
            np.zeros((100, 100, 3), dtype=np.uint8) if desired_encoding == "bgr8" else native_depth)
        frames = []
        node._frame_publisher = NS(publish=frames.append)
        factory = lambda: NS(position_camera_m=NS(), navigation_bottom_ray_camera=NS())
        with patch.object(detector, "String", lambda: NS(data=""), create=True), \
                patch.object(detector, "TargetObservation", factory, create=True), \
                patch.object(detector, "TargetObservationArray", NS, create=True), \
                patch.object(detector, "NavigationOverlap", NS, create=True):
            rgb, depth = workers.image(1), workers.image(1)
            rgb.width = rgb.height = depth.width = depth.height = 100
            node._on_rgb(rgb)
            node._on_depth(depth)
            node._process_latest()
            self.assertTrue(node._worker.wait_idle(1))
        self.assertEqual(warnings, [])
        selected, = observations
        expected = self.evidence(native_depth, [(0, .9, 2, selected_box), (1, .9, 0, other_box)])
        self.assertTrue(selected.navigation_exclusive_depth_complete)
        self.assertEqual(selected.navigation_exclusive_expected_pixel_count, expected["expected_pixels"])
        self.assertEqual(selected.navigation_exclusive_valid_pixel_count, expected["valid_pixels"])
        self.assertEqual(selected.navigation_exclusive_reason, expected["reason"])
        np.testing.assert_array_equal(selected.navigation_exclusive_points_camera_m, expected["points_camera_m"])
        self.assertTrue(selected.navigation_points_camera_m)
        self.assertTrue(selected.navigation_visibility_support_camera_m)
        self.assertNotEqual(len(selected.navigation_visibility_support_camera_m), len(expected["points_camera_m"]))
        self.assertTrue(selected.depth_valid)
        self.assertFalse(selected.navigation_bbox_complete)
        self.assertEqual(frames[0].observations, observations)
        self.assertEqual(len(frames[0].navigation_overlaps), 1)
        self.assertEqual(diagnostics[0]["detections"][0]["navigation_exclusive"]["method"], METHOD)
        self.assertTrue(diagnostics[0]["detections"][0]["navigation_exclusive"]["depth_complete"])


if __name__ == "__main__":
    unittest.main()
