"""Car-surface core behavior using small measured ray/face scenes; no ROS."""
from dataclasses import asdict, replace
import json
import unittest
from unittest.mock import patch

import numpy as np

from uav_tracking.core.car_surface_measurement import (
    DepthOptions, GroundOptions, SamplingOptions, WorkBudget,
    component_centroid, prepare_car_surface_frame,
)
from uav_tracking.core.geometry import CameraIntrinsics, depth_roi_stats
from uav_tracking.core.navigation import NavigationPrior, fit_ground_plane


CAMERA = CameraIntrinsics(160., 160., 160., 60.)
PRIOR = NavigationPrior("car", 4.5, 1.8, 1.5, dimension_std_m=(.45, .18, .15))
BOX = (140., 88., 180., 122.)
DEPTH = DepthOptions(.2, 50.)
BUDGET = WorkBudget(320*240, 320*240, 32)


def render(face=True):
    vv, _ = np.indices((240, 320))
    image = np.full(vv.shape, np.nan)
    valid = vv > CAMERA.cy
    image[valid] = 3.*CAMERA.fy/(vv[valid]-CAMERA.cy)
    if face:
        image[90:117, 142:179] = 8.
    return image


def prepare(image, boxes=(BOX,), **overrides):
    return prepare_car_surface_frame(image, CAMERA, boxes,
        depth_options=overrides.pop("depth_options", DEPTH), prior=PRIOR,
        up_camera=(0., -1., 0.), budget=overrides.pop("budget", BUDGET), **overrides)


class CarSurfaceMeasurementTests(unittest.TestCase):
    def test_supported_centroid_uses_complete_component_and_output_is_compact(self):
        image = render()
        context = prepare(image)
        result = context.assess(0)
        self.assertEqual(result["status"], "SUPPORTED_SURFACE_MEASUREMENT", result)
        measurement = result["measurement"]
        # The inward-rounded ROI contains this complete measured 8m face;
        # independently enumerate every foreground pixel in that ROI.
        l, t, r, b = result["evidence"]["roi_bounds_integer"]
        vv, uu = np.nonzero(image[t:b, l:r] == 8.)
        uu, vv = uu+l, vv+t
        points = np.column_stack(((uu-CAMERA.cx)*8./CAMERA.fx, (vv-CAMERA.cy)*8./CAMERA.fy, np.full(len(uu), 8.)))
        # The independent enumeration is row-major; implementation groups in
        # stable radial order, so float summation order may differ at roundoff.
        np.testing.assert_allclose(measurement["position_camera_m"], np.mean(points, axis=0), rtol=0, atol=1e-14)
        self.assertEqual(measurement["component_support_count"], len(points))
        self.assertEqual(measurement["reference_kind"], "visible_surface_proxy_component_centroid")
        self.assertEqual(measurement["identity_status"], "NOT_ASSESSED")
        self.assertIsNone(measurement["covariance_camera_m2"])
        for field in ("component_point_set", "points", "pixel_uv", "native_pixel_depth", "depth_m"):
            self.assertNotIn(field, measurement)
        self.assertLess(len(json.dumps(result)), 20_000)

    def test_actual_ground_fit_is_shared_once_for_all_known_boxes_and_cached(self):
        boxes = (BOX, (40., 88., 80., 122.))
        with patch("uav_tracking.core.car_surface_measurement.fit_ground_plane", wraps=fit_ground_plane) as fit:
            context = prepare(render(), boxes)
            first = context.assess(0)
            second = context.assess(1)
            again = context.assess(0)
        self.assertEqual(first["status"], "SUPPORTED_SURFACE_MEASUREMENT")
        self.assertEqual(second["status"], "UNKNOWN")
        self.assertEqual(first, again)
        self.assertEqual(fit.call_count, 1)
        self.assertEqual(context.diagnostics["ground_fit_calls"], 1)
        self.assertEqual(context.diagnostics["strict_depth_preparations"], 1)
        self.assertEqual(first["evidence"]["ground"], second["evidence"]["ground"])
        first["evidence"]["ground"]["valid"] = False
        self.assertTrue(context.assess(0)["evidence"]["ground"]["valid"])

    def test_unknown_keeps_original_valid_raw_reference_without_replacement(self):
        two = render()
        two[90:117, 142:164] = 6.
        cases = ((render(False), (BOX,)), (two, (BOX,)), (render(), (BOX, BOX)))
        for image, boxes in cases:
            with self.subTest(boxes=boxes):
                result = prepare(image, boxes).assess(0)
                self.assertEqual(result["status"], "UNKNOWN")
                self.assertIsNone(result["measurement"])
                stats = asdict(depth_roi_stats(image, BOX, min_depth=.2, max_depth=50., margin=.15))
                self.assertEqual(result["original"]["depth_stats"], stats)
                self.assertIsNotNone(result["original"]["bbox_center_median_camera_m"])

    def test_all_classes_and_duplicate_boxes_exclude_exclusive_support(self):
        context = prepare(render(), (BOX, BOX))
        self.assertEqual(context.assess(1, class_name="person")["reason"], "unsupported_declared_geometry_family")
        result = context.assess(0)
        self.assertIsNone(result["measurement"])
        self.assertEqual(result["evidence"]["exclusive_sample_count"], 0)

    def test_source_snapshot_and_results_survive_caller_mutation(self):
        image, boxes = render(), [list(BOX)]
        context = prepare(image, boxes)
        image[:] = np.nan
        boxes[0][:] = [0., 0., 1., 1.]
        boxes.append(list(BOX))
        result = context.assess(0)
        self.assertEqual(result["status"], "SUPPORTED_SURFACE_MEASUREMENT")
        self.assertEqual(result["original"]["bbox_xyxy"], list(BOX))
        self.assertEqual(context.diagnostics["visible_box_count"], 1)

    def test_strict_native_depth_domain_and_millimetre_scale(self):
        for z, expected in ((.2, 0), (50., 616), (50.001, 0)):
            result = prepare(np.full((240, 320), z)).assess(0)
            self.assertEqual(result["original"]["depth_stats"]["valid_count"], expected)
        integer = np.rint(np.nan_to_num(render(), nan=0)*1000).astype(np.uint16)
        before = integer.copy()
        result = prepare(integer, depth_options=replace(DEPTH, depth_scale=.001)).assess(0)
        self.assertEqual(result["status"], "SUPPORTED_SURFACE_MEASUREMENT", result)
        self.assertEqual(result["measurement"]["position_camera_m"][2], 8.)
        np.testing.assert_array_equal(integer, before)

    def test_resource_excess_never_fits_ground_or_performs_over_budget_stats(self):
        cases = ((replace(BUDGET, max_image_pixels=1), "image_or_roi_work_budget_exceeded", False),
                 (replace(BUDGET, max_roi_pixels=1), "image_or_roi_work_budget_exceeded", False),
                 (replace(BUDGET, max_visible_boxes=1), "visible_boxes_work_budget_exceeded", True))
        for budget, reason, has_stats in cases:
            with self.subTest(budget=budget), patch("uav_tracking.core.car_surface_measurement.fit_ground_plane", wraps=fit_ground_plane) as fit:
                context = prepare(render(), (BOX, BOX), budget=budget)
                result = context.assess(0)
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["original"]["depth_stats"] is not None, has_stats)
                self.assertEqual(fit.call_count, 0)
                self.assertEqual(context.diagnostics["strict_depth_preparations"], 0)

    def test_configuration_cannot_relax_geometry_or_unbound_work(self):
        for options in (SamplingOptions(exclusive_max_points=501), SamplingOptions(ground_max_points=1201),
                        SamplingOptions(image_edge_margin_px=1.999), SamplingOptions(ground_stride=1.5)):
            with self.subTest(options=options), self.assertRaises(ValueError):
                prepare(render(), sampling=options)
        for options in (GroundOptions(iterations=81), GroundOptions(max_tilt_deg=25.1),
                        GroundOptions(min_support=39), GroundOptions(distance_threshold_m=.051)):
            with self.subTest(options=options), self.assertRaises(ValueError):
                prepare(render(), ground_options=options)
        for index in (-1, True, .5, 3):
            with self.subTest(index=index), self.assertRaises(ValueError):
                prepare(render()).assess(index)

    def test_centroid_fixed_point_set_is_rigid_equivariant_and_has_no_pixel_tie(self):
        points = np.array([[0., 0., 8.], [2., 0., 8.], [0., 1., 8.], [4., -3., 9.]])
        axis = np.array([1., 2., -3.]); axis /= np.linalg.norm(axis)
        skew = np.array([[0., -axis[2], axis[1]], [axis[2], 0., -axis[0]], [-axis[1], axis[0], 0.]])
        rotation = np.eye(3)+np.sin(.71)*skew+(1.-np.cos(.71))*(skew @ skew)
        translation = np.array([4.5, -1.3, 7.])
        np.testing.assert_allclose(component_centroid(points @ rotation.T+translation),
            rotation @ component_centroid(points)+translation, rtol=1e-14, atol=1e-13)
        np.testing.assert_array_equal(component_centroid([[-1., 0., 8.], [1., 0., 8.]]), [0., 0., 8.])
        for bad in ([], [[1., 2.]], [[1., np.nan, 3.]]):
            self.assertRaises(ValueError, component_centroid, bad)


if __name__ == "__main__":
    unittest.main()
