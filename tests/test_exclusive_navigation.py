"""Meaningful negative controls for the opt-in independent depth domain."""
import math
import unittest

import numpy as np

from uav_tracking.core.exclusive_navigation import (
    MAX_EXCLUSIVE_PIXELS, METHOD, estimate_exclusive_reference, extract_native_exclusive,
)
from uav_tracking.core.geometry import CameraIntrinsics
from uav_tracking.core.navigation import GroundPlane, NavigationPrior


class NativeExclusiveExtractionTests(unittest.TestCase):
    def setUp(self):
        self.depth = np.full((32, 40), 10.)
        self.K = CameraIntrinsics(50., 50., 20., 16.)
        self.box = [5.2, 5.2, 30.7, 25.8]

    def extract(self, other=(), **kwargs):
        return extract_native_exclusive(self.depth, self.K, self.box, other, **kwargs)

    def test_every_native_pixel_is_retained_without_sampling(self):
        result = self.extract()
        self.assertTrue(result['valid'])
        self.assertEqual(result['expected_pixels'], 24*19)
        self.assertEqual(result['valid_pixels'], 24*19)
        self.assertEqual(result['points_camera_m'].shape, (24*19, 3))
        self.assertEqual(result['method'], METHOD)
        self.assertEqual(len(np.unique(result['pixel_uv'], axis=0)), 24*19)

    def test_unknown_competitor_and_subpixel_overlap_remain_excluded(self):
        result = self.extract([[10.3, 9.2, 14.8, 17.1]])
        uv = result['pixel_uv']
        forbidden = ((uv[:, 0] >= 10) & (uv[:, 0] < 15) &
                     (uv[:, 1] >= 9) & (uv[:, 1] < 18))
        self.assertFalse(forbidden.any())
        self.assertEqual(result['expected_pixels'], 24*19-5*9)

    def test_competitor_reordering_preserves_exact_measurement(self):
        boxes = [[10.3, 9.2, 14.8, 17.1], [18., 8., 22., 12.]]
        a, b = self.extract(boxes), self.extract(boxes[::-1])
        np.testing.assert_array_equal(a['points_camera_m'], b['points_camera_m'])

    def test_shared_depth_changes_cannot_change_exclusive_reference_input(self):
        box = [10.3, 9.2, 14.8, 17.1]
        before = self.extract([box])
        self.depth[9:18, 10:15] = np.nan
        after = self.extract([box])
        self.assertTrue(after['valid'])
        np.testing.assert_array_equal(before['points_camera_m'], after['points_camera_m'])

    def test_single_exclusive_hole_does_not_produce_partial_cloud(self):
        self.depth[6, 6] = np.nan
        result = self.extract()
        self.assertFalse(result['valid'])
        self.assertEqual(result['valid_pixels'], result['expected_pixels']-1)
        self.assertNotIn('points_camera_m', result)

    def test_declared_sensor_depth_scale_and_range_apply(self):
        self.depth *= 1000.
        result = self.extract(depth_scale=.001)
        self.assertTrue(result['valid'])
        np.testing.assert_allclose(result['points_camera_m'][:, 2], 10.)
        self.assertFalse(self.extract(depth_scale=.001, max_depth_m=9.)['valid'])

    def test_original_two_pixel_edge_gate_is_strict(self):
        for box in ([2., 5., 30., 25.], [5., 2., 30., 25.], [5., 5., 38., 25.], [5., 5., 30., 30.]):
            result = extract_native_exclusive(self.depth, self.K, box, [])
            self.assertFalse(result['valid'])

    def test_budget_excess_remains_unknown_without_subsampling(self):
        image = np.ones((200, 200))
        result = extract_native_exclusive(image, self.K, [3., 3., 197., 197.], [])
        self.assertGreater(result['expected_pixels'], MAX_EXCLUSIVE_PIXELS)
        self.assertFalse(result['valid'])
        self.assertNotIn('points_camera_m', result)

    def test_nested_competitor_can_remove_all_support(self):
        result = self.extract([[0., 0., 40., 32.]])
        self.assertFalse(result['valid'])
        self.assertEqual(result['expected_pixels'], 0)

    def test_extreme_finite_competitor_is_clipped_before_integer_conversion(self):
        result = self.extract([[-1e30, -1e30, 1e30, 1e30]])
        self.assertFalse(result['valid'])
        self.assertEqual(result['expected_pixels'], 0)

    def test_image_and_competitor_resource_limits_precede_allocation(self):
        image = np.ones((481, 640))
        result = extract_native_exclusive(image, self.K, [3., 3., 637., 478.], [])
        self.assertEqual(result['reason'], 'exclusive_image_budget_exceeded')
        result = self.extract([[0., 0., 1., 1.]]*65)
        self.assertEqual(result['reason'], 'exclusive_competitor_budget_exceeded')

    def test_missing_competitor_container_is_unknown(self):
        result = extract_native_exclusive(self.depth, self.K, self.box, None)
        self.assertFalse(result['valid'])

    def test_malformed_competitor_is_not_ignored(self):
        result = self.extract([[1., float('nan'), 3., 5.]])
        self.assertFalse(result['valid'])


class ExclusiveReferenceTests(unittest.TestCase):
    def setUp(self):
        self.plane = GroundPlane(np.array([0., 0., 1.]), 0., np.eye(4)*1e-6, True, 'synthetic')
        self.camera = np.array([0., 0., 3.])
        self.forward = np.array([0., 1., 0.])
        self.prior = NavigationPrior('car', 4., 2., 1.5)

    @staticmethod
    def face(xmin=-1., xmax=1., y=10.):
        x, z = np.meshgrid(np.linspace(xmin, xmax, 41), np.linspace(.2, 1.4, 10))
        return np.column_stack((x.ravel(), np.full(x.size, y), z.ravel()))

    def estimate(self, points, **kwargs):
        return estimate_exclusive_reference(points, ground_plane=self.plane,
            camera_position_world=kwargs.get('camera', self.camera), camera_forward_world=self.forward,
            prior=kwargs.get('prior', self.prior))

    def test_same_vehicle_partial_face_keeps_crop_uncertainty(self):
        prior = NavigationPrior('car', 4., 2., 1.5, dimension_std_m=(0., 0., 0.), heading_std_rad=0.)
        full, crop = self.estimate(self.face(), prior=prior), self.estimate(self.face(-.6, 1.), prior=prior)
        self.assertTrue(full.valid)
        self.assertTrue(crop.valid)
        self.assertGreater(crop.diagnostics['outer_horizontal_halfwidth_m'][1], full.diagnostics['outer_horizontal_halfwidth_m'][1])
        # A representative point may shift, but the actual centered end face is
        # not declared a uniquely observed center after one side is removed.
        self.assertAlmostEqual(crop.position_world_m[0], .2, places=8)
        self.assertGreaterEqual(crop.diagnostics['outer_horizontal_halfwidth_m'][1], .2)

    def test_full_declared_dimension_and_heading_domains_are_reported(self):
        result = self.estimate(self.face())
        self.assertTrue(result.valid)
        np.testing.assert_allclose(result.diagnostics['full_dimension_domain_m'], [[2.8, 5.2], [1.4, 2.6], [1.05, 1.95]])
        np.testing.assert_allclose(result.diagnostics['full_heading_domain_rad'], [-.36, .36])
        self.assertFalse(result.diagnostics['identity_assessed'])
        self.assertFalse(result.diagnostics['complete_error_domain_assignment_uniqueness_proven'])
        self.assertFalse(result.diagnostics['span_outer_bound_is_feasibility_witness'])

    def test_covariance_is_psd_and_covers_reported_horizontal_rectangle(self):
        result = self.estimate(self.face(-.6, 1.))
        self.assertTrue(result.valid)
        self.assertGreaterEqual(np.linalg.eigvalsh(result.covariance).min(), -1e-12)
        normal = np.asarray(result.diagnostics['original_geometry']['visible_face_normals_world'][0])
        tangent = np.cross(self.plane.normal, normal)
        a, b = result.diagnostics['outer_horizontal_halfwidth_m']
        for sa in [-1, 1]:
            for sb in [-1, 1]:
                corner = sa*a*normal+sb*b*tangent
                self.assertLessEqual(corner@np.linalg.solve(result.covariance, corner), 9.+1e-9)

    def test_two_foreground_layers_cannot_select_nearest(self):
        result = self.estimate(np.vstack((self.face(), self.face(y=15.))))
        self.assertFalse(result.valid)
        self.assertIn('foreground_multiple_or_missing', result.reason)

    def test_fixed_span_competition_in_full_dimension_domain_stays_unknown(self):
        prior = NavigationPrior('car', 4., 2., 1.5, dimension_std_m=(.8, .2, .15))
        result = self.estimate(self.face(), prior=prior)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, 'exclusive_fixed_span_dimension_assignment_ambiguous')
        self.assertEqual(result.diagnostics['fixed_span_dimension_only_assignments'], ['end', 'side'])

    def test_one_unexplained_foreground_point_is_not_body_clipped(self):
        result = self.estimate(np.vstack((self.face(), [[5., 10., .6]])))
        self.assertFalse(result.valid)

    def test_two_independent_faces_are_explicitly_unsupported(self):
        y, z = np.meshgrid(np.linspace(10., 14., 61), np.linspace(.2, 1.4, 10))
        side = np.column_stack((np.ones(y.size), y.ravel(), z.ravel()))
        result = self.estimate(np.vstack((self.face(), side)), camera=np.array([4., 0., 3.]))
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, 'exclusive_single_face_required')

    def test_bad_or_excessive_cloud_does_not_silently_drop_samples(self):
        for points in (np.empty((0, 3)), [[0., float('nan'), 1.]], np.ones((MAX_EXCLUSIVE_PIXELS+1, 3))):
            self.assertFalse(self.estimate(points).valid)

    def test_ground_or_class_context_cannot_be_invented(self):
        result = estimate_exclusive_reference(self.face(), ground_plane=GroundPlane(),
            camera_position_world=self.camera, camera_forward_world=self.forward, prior=self.prior)
        self.assertFalse(result.valid)
        prior = NavigationPrior('person', .4, .4, 1.7)
        self.assertFalse(self.estimate(self.face(), prior=prior).valid)

    def test_all_input_samples_are_preserved(self):
        points = self.face(-.6, 1.)
        original = points.copy()
        self.estimate(points)
        np.testing.assert_array_equal(points, original)


if __name__ == '__main__':
    unittest.main()
