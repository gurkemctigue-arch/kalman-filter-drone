"""Behavior checks for measured car visibility order; no ROS, bags or truth."""
import unittest

import numpy as np

from uav_tracking.core.navigation import GroundPlane, NavigationPrior
from uav_tracking.core.visibility import (
    assess_overlap_visibility, directed_depth_order, fit_unique_visibility_model,
    nested_boxes, overlap_pixel_rectangle,
)


def ground():
    return GroundPlane(np.array([0., 0., 1.]), 0., np.eye(4)*1e-6,
                       True, "measured_fixture_plane", 100, 100, .005)


def measured_face(x):
    y, z = np.meshgrid(np.linspace(-.9, .9, 24), np.linspace(.15, 1.35, 16))
    return np.column_stack((np.full(y.size, x), y.ravel(), z.ravel()))


def model(x, support=None):
    return fit_unique_visibility_model(
        measured_face(x) if support is None else support, ground_plane=ground(),
        camera_position_world=np.array([0., 0., 3.]), camera_forward_world=np.array([1., 0., 0.]),
        prior=NavigationPrior("car", 4.5, 1.8, 1.5, dimension_std_m=(.45, .18, .15)))


class DirectedVisibilityTests(unittest.TestCase):
    def test_front_candidate_can_continue_while_back_candidate_cannot(self):
        near, far = model(8.), model(18.)
        self.assertTrue(near.valid, near.reason)
        self.assertTrue(far.valid, far.reason)
        front = directed_depth_order(near, far)
        self.assertTrue(front["allowed"], front)
        self.assertGreater(front["depth_order_margin_m"], 0.)
        self.assertFalse(directed_depth_order(far, near)["allowed"])
        self.assertFalse(directed_depth_order(near, near)["allowed"])
        self.assertEqual(front["k"], 3.)

    def test_whole_overlap_may_contain_explained_front_surface_and_ground(self):
        # Actual foreground is explicitly retained as foreground, never called
        # pure background or discarded to obtain a passing navigation cloud.
        overlap = np.array([[8., 0., .8], [18., .2, .7], [24., 0., 0.]])
        decision = assess_overlap_visibility(model(8.), model(18.), overlap,
                                             expected_pixels=3, valid_pixels=3, ground_plane=ground())
        self.assertTrue(decision["allowed"], decision)
        self.assertEqual(decision["selected_foreground_pixels"], 1)
        self.assertEqual(decision["other_geometry_pixels"], 1)
        self.assertEqual(decision["ground_pixels"], 1)
        self.assertEqual(decision["unexplained_pixels"], 0)

    def test_one_unexplained_near_or_intermediate_surface_still_vetoes(self):
        for unknown in ([5., 0., .8], [14., 0., .8]):
            with self.subTest(unknown=unknown):
                points = np.array([[8., 0., .8], unknown])
                decision = assess_overlap_visibility(model(8.), model(18.), points,
                                                     expected_pixels=2, valid_pixels=2, ground_plane=ground())
                self.assertFalse(decision["allowed"])
                self.assertEqual(decision["unexplained_pixels"], 1)

    def test_missing_invalid_or_over_budget_pixels_do_not_disappear(self):
        near, far = model(8.), model(18.)
        for expected, valid, points in ((2, 1, [[8., 0., .8]]),
                                        (2, 2, [[8., 0., .8]]),
                                        (4097, 4097, []),
                                        (1, 1, [[np.nan, 0., .8]]),
                                        (0, 0, [])):
            with self.subTest(expected=expected, valid=valid):
                decision = assess_overlap_visibility(near, far, np.asarray(points),
                                                     expected_pixels=expected, valid_pixels=valid,
                                                     ground_plane=ground())
                self.assertFalse(decision["allowed"], decision)

    def test_multiple_depth_groups_cannot_be_repaired_by_choosing_the_nearest(self):
        result = model(8., np.vstack((measured_face(8.), measured_face(18.))))
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "visibility_foreground_multiple_or_missing")

    def test_partial_visible_face_does_not_prove_full_navigation_geometry(self):
        face = measured_face(8.)
        partial = face[np.abs(face[:, 1]) < .2]
        result = model(8., partial)
        self.assertFalse(result.valid)
        self.assertIn("visibility_", result.reason)

    def test_observed_roof_support_is_kept_in_the_visible_depth_envelope(self):
        x, y = np.meshgrid(np.linspace(8., 12., 16), np.linspace(-.8, .8, 6))
        roof = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, 1.5)))
        with_roof = model(8., np.vstack((measured_face(8.), roof)))
        self.assertTrue(with_roof.valid, with_roof.reason)
        self.assertGreater(with_roof.visible_back_hi_m, 12.)
        self.assertGreater(with_roof.visible_back_hi_m, model(8.).visible_back_hi_m)

    def test_prior_uncertainty_can_only_make_an_order_less_certain(self):
        near = model(8.)
        prior = NavigationPrior("car", 4.5, 1.8, 1.5, dimension_std_m=(20., 20., 20.))
        uncertain = fit_unique_visibility_model(
            measured_face(18.), ground_plane=ground(), camera_position_world=[0., 0., 3.],
            camera_forward_world=[1., 0., 0.], prior=prior)
        self.assertTrue(uncertain.valid, uncertain.reason)
        self.assertFalse(directed_depth_order(near, uncertain)["allowed"])

    def test_subpixel_intersection_is_not_an_empty_success(self):
        self.assertEqual(overlap_pixel_rectangle([1., 1., 4.01, 4.01], [4., 4., 7., 7.], 10, 10),
                         (4, 4, 5, 5))
        self.assertIsNone(overlap_pixel_rectangle([1., 1., 4., 4.], [4., 4., 7., 7.], 10, 10))
        self.assertTrue(nested_boxes([1, 1, 7, 7], [2, 2, 3, 3]))


if __name__ == "__main__":
    unittest.main()
