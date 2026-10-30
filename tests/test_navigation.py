"""Geometry and observability checks for RGB-D navigation references."""

import math
import unittest

import numpy as np

from uav_tracking.core.geometry import CameraIntrinsics
from uav_tracking.core.navigation import (
    GroundPlane,
    NavigationPrior,
    estimate_footprint_from_points,
    estimate_ground_plane,
    estimate_navigation_reference,
    fit_ground_plane,
    sample_depth_points,
)


def plane():
    return GroundPlane(np.array([0., 0., 1.]), 0., np.eye(4)*1e-6, True, "test_plane", 100, 100, .005)


def car_prior(**overrides):
    values = dict(class_name="car", length_m=4.6, width_m=1.8, height_m=1.5, dimension_std_m=(.2, .1, .1))
    values.update(overrides)
    return NavigationPrior(**values)


def end_face(x=8., width=1.8, height=1.5):
    y, z = np.meshgrid(np.linspace(-width/2, width/2, 18), np.linspace(.12, height*.9, 12))
    return np.column_stack((np.full(y.size, x), y.reshape(-1), z.reshape(-1)))


def adjacent_car_faces(length=4.6, width=1.8, center=(10., 0., 0.)):
    """Independent measured end and side samples, with no runtime truth input."""
    center = np.asarray(center)
    y, z = np.meshgrid(np.linspace(-width/2, width/2, 22), np.linspace(.12, 1.35, 13))
    end = np.column_stack((np.full(y.size, -length/2), y.reshape(-1), z.reshape(-1)))
    x, z = np.meshgrid(np.linspace(-length/2, length/2, 27), np.linspace(.12, 1.35, 13))
    side = np.column_stack((x.reshape(-1), np.full(x.size, -width/2), z.reshape(-1)))
    return np.vstack((end, side)) + center


class PixelExclusionTests(unittest.TestCase):
    @staticmethod
    def pixels(points):
        return {tuple(pixel) for pixel in np.rint(points[:, :2]/points[:, 2:3]).astype(int)}

    @staticmethod
    def touches(pixel, box):
        u, v = pixel
        return (box[2] > box[0] and box[3] > box[1]
                and max(u, box[0]) < min(u+1, box[2])
                and max(v, box[1]) < min(v+1, box[3]))

    def test_fractional_other_box_excludes_361_203_without_changing_full_cloud(self):
        depth = np.ones((210, 370))
        args = dict(bbox=(359., 201., 365., 207.), max_points=1000)
        full = sample_depth_points(depth, (1, 1, 0, 0), **args)
        box = (361.2589, 202.3, 364.4, 205.7)
        exclusive = sample_depth_points(depth, (1, 1, 0, 0), exclude_bboxes=[box], **args)
        self.assertIn((361, 203), self.pixels(full))
        self.assertNotIn((361, 203), self.pixels(exclusive))
        self.assertEqual(self.pixels(exclusive), {p for p in self.pixels(full) if not self.touches(p, box)})
        np.testing.assert_array_equal(full, sample_depth_points(depth, (1, 1, 0, 0), **args))

    def test_each_fractional_edge_and_corner_removes_every_touched_cell(self):
        all_pixels = {(u, v) for v in range(6) for u in range(6)}
        boxes = [(1.9, 2.2, 2.1, 2.8), (2.9, 2.2, 3.1, 2.8),
                 (2.2, 1.9, 2.8, 2.1), (2.2, 2.9, 2.8, 3.1),
                 (1.9, 1.9, 2.1, 2.1), (2.9, 1.9, 3.1, 2.1),
                 (1.9, 2.9, 2.1, 3.1), (2.9, 2.9, 3.1, 3.1)]
        for box in boxes:
            with self.subTest(box=box):
                sampled = self.pixels(sample_depth_points(np.ones((6, 6)), (1, 1, 0, 0),
                    exclude_bboxes=[box], max_points=1000))
                self.assertNotIn((2, 2), sampled)
                self.assertEqual(sampled, {p for p in all_pixels if not self.touches(p, box)})

    def test_integer_edges_are_half_open_and_subpixel_disjoint_roi_is_unchanged(self):
        image = np.ones((8, 8))
        all_pixels = {(u, v) for v in range(8) for u in range(8)}
        sampled = self.pixels(sample_depth_points(image, (1, 1, 0, 0),
            exclude_bboxes=[(2., 2., 3., 3.)], max_points=1000))
        self.assertEqual(sampled, all_pixels-{(2, 2)})
        args = dict(bbox=(2.1, 2.1, 6.9, 6.9), max_points=1000)
        full = sample_depth_points(image, (1, 1, 0, 0), **args)
        exclusive = sample_depth_points(image, (1, 1, 0, 0),
            exclude_bboxes=[(6.95, 2.2, 7.05, 6.8)], **args)
        np.testing.assert_array_equal(exclusive, full)
        self.assertEqual(self.pixels(full), {(u, v) for v in (3, 4, 5) for u in (3, 4, 5)})

    def test_degenerate_exclusions_stay_empty_before_rounding_and_finite_checks_remain(self):
        image = np.ones((8, 8))
        full = sample_depth_points(image, (1, 1, 0, 0), max_points=1000)
        boxes = [(2.1, 2.1, 2.1, 2.8), (2.1, 2.8, 2.8, 2.8),
                 (2.9, 2.1, 2.1, 2.8), (2.1, 2.9, 2.8, 2.1), (.1, .1, .1, .1)]
        for box in boxes:
            with self.subTest(box=box):
                np.testing.assert_array_equal(full, sample_depth_points(image, (1, 1, 0, 0),
                    exclude_bboxes=[box], max_points=1000))
        for box in ((np.inf, 0, np.inf, 0), (0, np.nan, 2, 3), (0, 1, 2)):
            with self.subTest(box=box), self.assertRaisesRegex(ValueError, "finite xyxy"):
                sample_depth_points(image, (1, 1, 0, 0), exclude_bboxes=[box])

    def test_clipped_exclusions_never_wrap_or_overflow_image_cells(self):
        image = np.ones((6, 6))
        all_pixels = {(u, v) for v in range(6) for u in range(6)}
        for box in ((-.2, 1.2, .2, 2.2), (-2., -2., -.1, -.1),
                    (5.8, 5.8, 8., 8.), (-1e100, -1e100, 1e100, 1e100)):
            with self.subTest(box=box):
                sampled = self.pixels(sample_depth_points(image, (1, 1, 0, 0),
                    exclude_bboxes=[box], max_points=1000))
                self.assertEqual(sampled, {p for p in all_pixels if not self.touches(p, box)})

    def test_stride_cap_depth_validity_and_all_exclusion_cells_are_preserved(self):
        image = np.full((24, 32), 4.)
        image[3, 2], image[6, 5], image[9, 8], image[12, 11] = np.nan, 0., 51., .05
        boxes = [(-.2, 4.1, 4.2, 10.2), (10.4, 8.6, 16.2, 15.9), (22.1, 17.2, 35., 20.9)]
        args = dict(bbox=(1.2, 2.4, 29.9, 21.8), exclude_bboxes=boxes, stride=2, max_points=17)
        points = sample_depth_points(image, (1, 1, 0, 0), **args)
        self.assertEqual(len(points), 17)
        np.testing.assert_array_equal(points, sample_depth_points(image, (1, 1, 0, 0), **args))
        self.assertTrue(np.all(points[:, 2] == 4.))
        pixels = self.pixels(points)
        self.assertTrue(all((u-2) % 3 == 0 and (v-3) % 3 == 0 for u, v in pixels))
        self.assertTrue(all(not self.touches(p, box) for p in pixels for box in boxes))


class DepthAndGroundTests(unittest.TestCase):
    def test_sampling_excludes_all_boxes_and_invalid_depth(self):
        depth = np.full((30, 40), 3.)
        depth[0, 0], depth[0, 1], depth[0, 2], depth[0, 3] = np.nan, np.inf, 0., -1.
        intrinsics = CameraIntrinsics(40., 40., 20., 15.)
        boxes = [(5, 5, 12, 12), (22, 16, 29, 24)]
        points = sample_depth_points(depth, intrinsics, exclude_bboxes=boxes, max_points=2000)
        self.assertTrue(np.isfinite(points).all())
        self.assertTrue((points[:, 2] > 0).all())
        u = points[:, 0]*40/points[:, 2]+20
        v = points[:, 1]*40/points[:, 2]+15
        for x1, y1, x2, y2 in boxes:
            self.assertFalse(np.any((u >= x1-.00001) & (u < x2-.00001) & (v >= y1-.00001) & (v < y2-.00001)))
        self.assertEqual(len(points), 30*40-4-7*7-7*8)

    def test_sampling_scale_roi_cap_and_determinism(self):
        image = np.full((100, 120), 2500, dtype=np.uint16)
        args = dict(bbox=(10, 20, 90, 80), depth_scale=.001, max_points=75)
        first = sample_depth_points(image, (100, 100, 60, 50), **args)
        self.assertLessEqual(len(first), 75)
        np.testing.assert_array_equal(first, sample_depth_points(image, (100, 100, 60, 50), **args))
        np.testing.assert_allclose(first[:, 2], 2.5)
        self.assertEqual(sample_depth_points(image, (100, 100, 60, 50), bbox=(2, 2, 2, 5)).shape, (0, 3))

    def test_ground_ransac_with_outliers_and_slope(self):
        rng = np.random.default_rng(7)
        xy = rng.uniform(-4, 4, size=(400, 2))
        z = .10*xy[:, 0]-.04*xy[:, 1]+.3+rng.normal(0, .005, len(xy))
        points = np.vstack((np.column_stack((xy, z)), rng.uniform(-4, 4, size=(80, 3)), [np.nan, 0, 0]))
        fitted = fit_ground_plane(points)
        self.assertTrue(fitted.valid, fitted.reason)
        expected = np.array([-.1, .04, 1.]); expected /= np.linalg.norm(expected)
        self.assertGreater(fitted.normal @ expected, .999)
        self.assertAlmostEqual(fitted.offset, -.3/np.linalg.norm([-.1, .04, 1.]), delta=.01)
        self.assertGreaterEqual(fitted.inlier_count, 390)
        self.assertTrue(np.isfinite(fitted.covariance).all())

    def test_ground_rejects_tilt_missing_support_and_line(self):
        x, y = np.meshgrid(np.linspace(-2, 2, 12), np.linspace(-2, 2, 12))
        steep = np.column_stack((x.reshape(-1), y.reshape(-1), x.reshape(-1)))
        self.assertFalse(fit_ground_plane(steep).valid)
        self.assertFalse(fit_ground_plane(np.zeros((5, 3))).valid)
        line = np.column_stack((np.linspace(-2, 2, 60), np.zeros(60), np.zeros(60)))
        self.assertFalse(fit_ground_plane(line).valid)

    def test_image_ground_wrapper_transforms_and_excludes_object(self):
        image = np.full((60, 80), 3.)
        image[20:40, 30:50] = 1.5
        transform = np.eye(4); transform[:3, :3] = np.diag([1, -1, -1]); transform[:3, 3] = [0, 0, 3]
        fitted = estimate_ground_plane(image, (70, 70, 40, 30), [(30, 20, 50, 40)], world_from_camera=transform)
        self.assertTrue(fitted.valid, fitted.reason)
        np.testing.assert_allclose(fitted.normal, [0, 0, 1], atol=1e-9)
        self.assertAlmostEqual(fitted.offset, 0, places=8)

    def test_invalid_inputs_are_not_silently_converted(self):
        with self.assertRaises(ValueError):
            sample_depth_points(np.ones((4, 4)), (1, 1, 0, 0), stride=0)
        with self.assertRaises(ValueError):
            fit_ground_plane(np.ones((20, 2)))
        with self.assertRaises(ValueError):
            NavigationPrior("car", -1, 1, 1)


class FootprintReferenceTests(unittest.TestCase):
    def test_person_foot_ground_intersection_is_independent_of_surface_height(self):
        prior = NavigationPrior("person", .45, .35, 1.7)
        rng = np.random.default_rng(1)
        body = np.column_stack((5+rng.normal(0, .05, 80), rng.normal(0, .04, 80), rng.uniform(.2, 1.6, 80)))
        reference = estimate_footprint_from_points(body, ground_plane=plane(), camera_position_world=[0, 0, 3], prior=prior,
                                                    bottom_ray_world=[5, 0, -3])
        self.assertTrue(reference.valid, reference.reason)
        np.testing.assert_allclose(reference.position_world_m, [5, 0, 0], atol=1e-10)
        self.assertEqual(reference.reference_kind, "person_ground_contact")
        self.assertTrue(np.linalg.eigvalsh(reference.covariance).min() > 0)

    def test_person_rejects_horizon_missing_ray_and_inconsistent_foot(self):
        prior = NavigationPrior("person", .45, .35, 1.7)
        body = end_face(x=5, width=.3, height=1.7)
        arguments = dict(ground_plane=plane(), camera_position_world=[0, 0, 3], prior=prior)
        self.assertFalse(estimate_footprint_from_points(body, **arguments).valid)
        self.assertFalse(estimate_footprint_from_points(body, bottom_ray_world=[1, 0, 0], **arguments).valid)
        result = estimate_footprint_from_points(body, bottom_ray_world=[10, 0, -3], **arguments)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "foot_body_geometry_inconsistent")

    def test_car_rear_face_with_velocity_recovers_ground_center(self):
        result = estimate_footprint_from_points(end_face(), ground_plane=plane(), camera_position_world=[0, 0, 3],
                                               prior=car_prior(), velocity_world=[.5, 0, 0])
        self.assertTrue(result.valid, result.reason)
        np.testing.assert_allclose(result.position_world_m, [10.3, 0, 0], atol=1e-8)
        self.assertEqual(result.heading_source, "track_velocity")
        self.assertGreater(result.covariance[0, 0], (.2/2)**2)

    def test_car_front_face_and_heading_sign(self):
        for heading in ([1, 0, 0], [-1, 0, 0]):
            result = estimate_footprint_from_points(end_face(x=12.6), ground_plane=plane(), camera_position_world=[20, 0, 3],
                                                   prior=car_prior(), heading_world=heading)
            self.assertTrue(result.valid, result.reason)
            np.testing.assert_allclose(result.position_world_m, [10.3, 0, 0], atol=1e-8)

    def test_measured_face_normal_does_not_inherit_motion_heading_noise(self):
        reference = estimate_footprint_from_points(end_face(), ground_plane=plane(), camera_position_world=[0, 0, 3],
                                                   prior=car_prior(), velocity_world=[.48, .24, 0])
        self.assertTrue(reference.valid, reference.reason)
        np.testing.assert_allclose(reference.position_world_m, [10.3, 0, 0], atol=1e-8)

    def test_static_end_face_startup_requires_unique_shape(self):
        result = estimate_footprint_from_points(end_face(), ground_plane=plane(), camera_position_world=[0, 0, 3],
                                               prior=car_prior(), velocity_world=[0, 0, 0])
        self.assertTrue(result.valid, result.reason)
        np.testing.assert_allclose(result.position_world_m, [10.3, 0, 0], atol=1e-7)
        self.assertEqual(result.heading_source, "visible_face_shape_prior")
        ambiguous = estimate_footprint_from_points(end_face(), ground_plane=plane(), camera_position_world=[0, 0, 3],
                                                   prior=car_prior(length_m=1.8))
        self.assertFalse(ambiguous.valid)
        self.assertEqual(ambiguous.reason, "car_static_end_side_ambiguous")

    def test_full_side_face_static_and_moving_recovers_width_half_offset(self):
        for camera, expected in (([0, 0, 3], [8.9, 0, 0]), ([16, 0, 3], [7.1, 0, 0])):
            for velocity in (None, [0, .5, 0], [.5, 0, 0]):
                reference = estimate_footprint_from_points(end_face(width=4.6), ground_plane=plane(),
                    camera_position_world=camera, prior=car_prior(), velocity_world=velocity)
                self.assertTrue(reference.valid, reference.reason)
                np.testing.assert_allclose(reference.position_world_m, expected, atol=1e-8)
                self.assertEqual(reference.reason, "car_upright_side_face_prior")
                self.assertEqual(reference.diagnostics["face_labels"], ["side"])

    def test_partial_narrow_face_is_not_called_car_center(self):
        reference = estimate_footprint_from_points(end_face(width=.6), ground_plane=plane(),
            camera_position_world=[0, 0, 3], prior=car_prior())
        self.assertFalse(reference.valid, reference.reason)

    def test_reliable_heading_does_not_make_a_grazing_surface_observable(self):
        result = estimate_footprint_from_points(end_face(), ground_plane=plane(), camera_position_world=[8, -8, 3],
                                               prior=car_prior(), velocity_world=[.5, 0, 0])
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "car_face_grazing_view")

    def test_two_observed_faces_determine_center_without_face_midpoint(self):
        points = adjacent_car_faces()
        # Only the near half of the side is visible. Its biased midpoint must
        # not move the center along the car; the two measured planes fix it.
        points = points[(points[:, 0] < 10.5) | (points[:, 1] > -.89)]
        reference = estimate_footprint_from_points(points, ground_plane=plane(), camera_position_world=[0, -6, 3], prior=car_prior())
        self.assertTrue(reference.valid, reference.reason)
        self.assertEqual(reference.reason, "car_upright_two_face_prior")
        np.testing.assert_allclose(reference.position_world_m, [10, 0, 0], atol=.04)
        self.assertCountEqual(reference.diagnostics["face_labels"], ["end", "side"])
        self.assertTrue(np.linalg.eigvalsh(reference.covariance).min() > 0)

    def test_two_face_geometry_is_invariant_to_wrong_motion_heading(self):
        arguments = dict(ground_plane=plane(), camera_position_world=[0, -6, 3], prior=car_prior())
        static = estimate_footprint_from_points(adjacent_car_faces(), **arguments)
        turning = estimate_footprint_from_points(adjacent_car_faces(), velocity_world=[0, .5, 0], **arguments)
        self.assertTrue(static.valid, static.reason)
        self.assertTrue(turning.valid, turning.reason)
        np.testing.assert_allclose(static.position_world_m, turning.position_world_m, atol=1e-10)
        self.assertEqual(turning.heading_source, "two_visible_faces_shape_prior")
        self.assertLess(turning.diagnostics["motion_geometry_alignment_cosine"], .1)

    def test_noisy_two_faces_preserve_unique_center_and_finite_covariance(self):
        for seed in range(5):
            with self.subTest(seed=seed):
                rng = np.random.default_rng(seed)
                points = adjacent_car_faces()
                points += rng.normal(0, .02, points.shape)
                reference = estimate_footprint_from_points(points, ground_plane=plane(),
                    camera_position_world=[0, -6, 3], prior=car_prior())
                self.assertTrue(reference.valid, reference.reason)
                self.assertEqual(reference.reason, "car_upright_two_face_prior")
                self.assertLess(np.linalg.norm(reference.position_world_m-[10, 0, 0]), .08)
                self.assertTrue(np.isfinite(reference.covariance).all())
                self.assertGreater(np.linalg.eigvalsh(reference.covariance).min(), 0)

    def test_two_face_ambiguous_assignments_are_rejected_even_with_heading(self):
        reference = estimate_footprint_from_points(adjacent_car_faces(length=2.), ground_plane=plane(),
            camera_position_world=[0, -6, 3], prior=car_prior(length_m=2.), velocity_world=[.5, 0, 0])
        self.assertFalse(reference.valid, reference.reason)
        self.assertEqual(reference.reason, "car_static_end_side_ambiguous")
        self.assertEqual(len(reference.diagnostics["geometric_hypotheses"]), 2)

    def test_nonorthogonal_visible_faces_are_not_a_cuboid(self):
        points = adjacent_car_faces()
        # Shear the long side, preserving its vertical-plane support.
        side = np.isclose(points[:, 1], -.9)
        points[side, 1] += .6*(points[side, 0]-7.7)
        reference = estimate_footprint_from_points(points, ground_plane=plane(),
            camera_position_world=[0, -6, 3], prior=car_prior())
        self.assertFalse(reference.valid, reference.reason)
        self.assertEqual(reference.reason, "car_visible_faces_not_orthogonal")

    def test_two_face_rigid_transform_and_prior_uncertainty(self):
        angle = .65
        rotation = np.array([[math.cos(angle), -math.sin(angle), 0], [math.sin(angle), math.cos(angle), 0], [0, 0, 1]])
        translation = np.array([12., -7., 2.])
        # Zero plane-parameter covariance isolates the geometry covariance;
        # the minimum plane residual floor is rigid-coordinate invariant.
        ground = GroundPlane(np.array([0., 0., 1.]), 0., np.zeros((4, 4)), True)
        shifted = GroundPlane(np.array([0., 0., 1.]), -2., np.zeros((4, 4)), True)
        points, camera = adjacent_car_faces(), np.array([0., -6., 3.])
        original = estimate_footprint_from_points(points, ground_plane=ground, camera_position_world=camera, prior=car_prior())
        transformed = estimate_footprint_from_points(points@rotation.T+translation, ground_plane=shifted,
            camera_position_world=camera@rotation.T+translation, prior=car_prior())
        uncertain = estimate_footprint_from_points(points, ground_plane=ground, camera_position_world=camera,
            prior=car_prior(dimension_std_m=(.8, .4, .2)))
        for reference in (original, transformed, uncertain):
            self.assertTrue(reference.valid, reference.reason)
            self.assertTrue(np.isfinite(reference.covariance).all())
            self.assertGreater(np.linalg.eigvalsh(reference.covariance).min(), 0)
        np.testing.assert_allclose(transformed.position_world_m, original.position_world_m@rotation.T+translation, atol=1e-7)
        np.testing.assert_allclose(transformed.covariance, rotation@original.covariance@rotation.T, atol=1e-7)
        self.assertTrue(np.linalg.eigvalsh(uncertain.covariance-original.covariance).min() >= -1e-10)

    def test_car_rotation_translation_and_no_ground_height_bias(self):
        angle = .9
        rotation = np.array([[math.cos(angle), -math.sin(angle), 0], [math.sin(angle), math.cos(angle), 0], [0, 0, 1]])
        translation = np.array([12, -7, 2.])
        points = end_face() @ rotation.T+translation
        shifted_ground = GroundPlane(np.array([0, 0, 1.]), -2., np.eye(4)*1e-6, True)
        reference = estimate_footprint_from_points(points, ground_plane=shifted_ground, camera_position_world=np.array([0, 0, 3])@rotation.T+translation,
                                                   prior=car_prior(), velocity_world=np.array([.5, 0, 0])@rotation.T)
        self.assertTrue(reference.valid, reference.reason)
        np.testing.assert_allclose(reference.position_world_m, np.array([10.3, 0, 0])@rotation.T+translation, atol=1e-7)

    def test_declared_dimension_uncertainty_and_mismatch_remain_visible(self):
        arguments = dict(ground_plane=plane(), camera_position_world=[0, 0, 3], velocity_world=[.5, 0, 0])
        nominal = estimate_footprint_from_points(end_face(), prior=car_prior(), **arguments)
        changed = estimate_footprint_from_points(end_face(), prior=car_prior(length_m=5.0, dimension_std_m=(.8, .3, .2)), **arguments)
        self.assertAlmostEqual(changed.position_world_m[0]-nominal.position_world_m[0], .2)
        self.assertGreater(changed.covariance[0, 0], nominal.covariance[0, 0])
        self.assertGreater(changed.covariance[1, 1], nominal.covariance[1, 1])

    def test_missing_ground_foreground_and_below_plane_are_invalid(self):
        for ground, points, camera in ((GroundPlane(reason="missing"), end_face(), [0, 0, 3]),
                                       (plane(), np.zeros((50, 3)), [0, 0, 3]),
                                       (plane(), end_face(), [0, 0, -.1])):
            result = estimate_footprint_from_points(points, ground_plane=ground, camera_position_world=camera, prior=car_prior())
            self.assertFalse(result.valid)
            self.assertIsNone(result.position_world_m)

    def test_foreground_ground_pixels_and_background_do_not_drag_center(self):
        rng = np.random.default_rng(10)
        ground = np.column_stack((rng.uniform(7, 15, 80), rng.uniform(-1, 1, 80), np.zeros(80)))
        background = end_face(x=25)
        result = estimate_footprint_from_points(np.vstack((end_face(), ground, background, [np.nan, 0, 0])), ground_plane=plane(),
                                               camera_position_world=[0, 0, 3], prior=car_prior(), velocity_world=[.5, 0, 0])
        self.assertTrue(result.valid, result.reason)
        np.testing.assert_allclose(result.position_world_m, [10.3, 0, 0], atol=1e-8)

    def test_truncated_image_box_is_invalid_before_estimation(self):
        result = estimate_navigation_reference(np.ones((60, 80)), (70, 70, 40, 30), [20, 20, 40, 60], prior=car_prior(),
                                               ground_plane=plane(), world_from_camera=np.eye(4))
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "target_box_truncated")


if __name__ == "__main__":
    unittest.main()
