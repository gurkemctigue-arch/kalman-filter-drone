"""Independent plane solves and eight vertices; no ROS, weights or recordings."""
from dataclasses import replace
import itertools
import math
import unittest

import numpy as np

from uav_tracking.core.body_bounds import (
    BOUND_STATUS, TwoFaceBodyBoundCase, correlated_two_face_front_bound,
)


def unit(value):
    value = np.asarray(value, dtype=float)
    return value/np.linalg.norm(value)


def rotation(axis, angle):
    x, y, z = unit(axis)
    skew = np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])
    return np.eye(3)+math.sin(angle)*skew+(1.-math.cos(angle))*(skew @ skew)


def synthetic_case():
    return TwoFaceBodyBoundCase(
        forward_world=unit((1., .12, -.3)), camera_position_world_m=(0., 0., 3.),
        face_normals_world=((-1., 0., 0.), (0., -1., 0.)),
        face_points_world_m=((10., 2., .7), (12., 1., .8)),
        face_labels=("end", "side"), face_std_m=(.04, .05),
        ground_normal_world=(0., 0., 1.), ground_offset_m=0.,
        ground_covariance_4x4=np.diag([1e-8, 1e-8, 1e-8, 1e-6]),
        ground_residual_std_m=.002, dimensions_m=(4.5, 1.8, 1.5),
        dimension_std_m=(.45, .18, .15), heading_std_rad=.12,
        depth_noise_std_m=.05, registration_std_m=.03)


def recorded_24_7_case():
    """Original cand0 scalar geometry, not a label, cloud or trial verdict.

    Source ground fit/TF and full source covariance were independently
    reconstructed from the original acquisition. All original uncertainty
    values are retained. Original bounds below check numerical compatibility.
    """
    return TwoFaceBodyBoundCase(
        forward_world=(.9408354454902566, -.009506069634692638, -.3387304225328023),
        camera_position_world_m=(4.976556639607233, .20276598375359317, 2.149362384365491),
        face_normals_world=(
            (-.4297200528419087, .9029616018557934, -.0010108212337816933),
            (-.9089053034548076, -.41699513845351005, -.002490754476503401)),
        face_points_world_m=(
            (18.939226453819725, -3.4347140493930977, .45550356444290774),
            (17.692509423831147, -5.095654011784273, .641006841041142)),
        face_labels=("side", "end"), face_std_m=(.04, .04830844338162912),
        ground_normal_world=(-.0026708266974261614, -.00015160132209617733, .9999964218444942),
        ground_offset_m=.20281138256401018,
        ground_covariance_4x4=np.diag([1.834594756631675e-10]*3+[3.333333333333333e-9]),
        ground_residual_std_m=.002, dimensions_m=(4.5, 1.8, 1.5),
        dimension_std_m=(.45, .18, .15), heading_std_rad=.12,
        depth_noise_std_m=.05, registration_std_m=.03)


def direct_vertex_front(case, dimensions, offsets, heading):
    """Resolve perturbed rotated planes and enumerate vertices independently.

    This does not call implementation helpers or the support/extent formula.
    Center and extent use the same dimensions and heading.
    """
    normals = np.asarray(case.face_normals_world, dtype=float)
    points = np.asarray(case.face_points_world_m, dtype=float)
    up = np.asarray(case.ground_normal_world)
    matrix = np.vstack((normals, up))
    corner = np.linalg.solve(matrix, np.r_[np.sum(normals*points, axis=1), -case.ground_offset_m])
    r = rotation(up, heading)
    rotated_normals = normals @ r.T
    face_dimensions = [dimensions[0 if label == "end" else 1] for label in case.face_labels]
    rhs = np.r_[rotated_normals @ corner+np.asarray(offsets[:2])-.5*np.asarray(face_dimensions),
                -case.ground_offset_m+offsets[2]]
    center = np.linalg.solve(np.vstack((rotated_normals, up)), rhs)+up*dimensions[2]*.5
    length = r @ normals[case.face_labels.index("end")]
    lateral = np.cross(up, length)
    projections = []
    for signs in itertools.product((-1., 1.), repeat=3):
        vertex = center.copy()
        for axis, dimension, sign in zip((length, lateral, up), dimensions, signs):
            vertex += axis*dimension*sign*.5
        projections.append(float(np.asarray(case.forward_world) @ (vertex-np.asarray(case.camera_position_world_m))))
    return min(projections)-3.*(case.depth_noise_std_m+case.registration_std_m)


def old_aggregation(case):
    """Original independent sigma aggregation, implemented only in tests."""
    normals = np.asarray(case.face_normals_world)
    up = np.asarray(case.ground_normal_world)
    f = np.asarray(case.forward_world)
    dims = np.asarray(case.dimensions_m)
    stds = np.asarray(case.dimension_std_m)
    a = np.vstack((normals, up))
    mapping = [0 if label == "end" else 1 for label in case.face_labels]
    rhs = np.r_[np.sum(normals*np.asarray(case.face_points_world_m), axis=1)-dims[mapping]*.5, -case.ground_offset_m]
    center = np.linalg.solve(a, rhs)
    q = np.r_[center, 1.]
    ground_variance = max(.02**2, case.ground_residual_std_m**2, float(q @ case.ground_covariance_4x4 @ q))
    inv = np.linalg.inv(a)
    variances = np.r_[np.asarray(case.face_std_m)**2+(stds[mapping]*.5)**2, ground_variance]
    covariance = inv @ np.diag(variances) @ inv.T
    corner = np.linalg.solve(a, np.r_[np.sum(normals*np.asarray(case.face_points_world_m), axis=1), -case.ground_offset_m])
    lever = np.cross(up, center-corner)
    covariance += case.heading_std_rad**2*np.outer(lever, lever)
    length = normals[case.face_labels.index("end")]
    coefficients = np.abs(np.array([length, np.cross(up, length), up]) @ f)
    sigma = (math.sqrt(float(f @ covariance @ f))+.5*float(coefficients @ stds)
             +.5*float(np.linalg.norm(dims[:2]))*case.heading_std_rad
             +case.depth_noise_std_m+case.registration_std_m)
    return float(f @ (center+up*dims[2]*.5-np.asarray(case.camera_position_world_m))-.5*coefficients @ dims-3.*sigma)


class CorrelatedBodyBoundTests(unittest.TestCase):
    def assert_finite_samples_enclosed(self, case, headings=25, random_samples=100):
        result = correlated_two_face_front_bound(case)
        self.assertEqual(result.status, BOUND_STATUS, result)
        domains = [(d-3.*s, d+3.*s) for d, s in zip(case.dimensions_m, case.dimension_std_m)]
        offsets_domain = result.metadata["plane_offset_intervals_m"]
        for dimensions, offsets, heading in itertools.product(
                itertools.product(*domains), itertools.product(*offsets_domain),
                np.linspace(-3.*case.heading_std_rad, 3.*case.heading_std_rad, headings)):
            self.assertGreaterEqual(direct_vertex_front(case, dimensions, offsets, heading)-result.lower_bound_m, -1e-10)
        rng = np.random.default_rng(247)
        for _ in range(random_samples):
            dims = tuple(rng.uniform(*interval) for interval in domains)
            offsets = tuple(rng.uniform(*interval) for interval in offsets_domain)
            self.assertGreaterEqual(direct_vertex_front(case, dims, offsets, rng.uniform(-3.*case.heading_std_rad, 3.*case.heading_std_rad))-result.lower_bound_m, -1e-10)
        witness = result.metadata["witness"]
        actual = direct_vertex_front(case, witness["dimensions_m"], witness["plane_offsets_m"], witness["heading_rad"])
        self.assertAlmostEqual(actual-result.lower_bound_m, result.metadata["floating_point_guard_m"], places=8)
        self.assertFalse(result.metadata["certified_outward_rounding"])
        self.assertEqual(result.metadata["parameter_corners_evaluated"], 64)
        return result

    def test_original_24_7_model_retains_every_uncertainty(self):
        case = recorded_24_7_case()
        result = self.assert_finite_samples_enclosed(case, headings=65, random_samples=400)
        self.assertAlmostEqual(old_aggregation(case), 9.416567159315548, places=12)
        self.assertAlmostEqual(result.lower_bound_m, 11.282640365770149, places=10)
        self.assertAlmostEqual(result.metadata["ground_variance_m2"], .0004, places=15)
        self.assertAlmostEqual(result.metadata["ground_variance_components_m2"]["original_covariance_quadratic_m2"], 7.757352255422868e-8, places=16)
        self.assertAlmostEqual(result.metadata["retained_depth_registration_three_sigma_m"], .24, places=15)
        self.assertEqual(result.metadata["heading_interval_rad"], [-.36, .36])
        np.testing.assert_allclose(result.metadata["dimension_intervals_m"], [[3.15, 5.85], [1.26, 2.34], [1.05, 1.95]])
        # A mathematical positive margin does not assert a runtime or flight verdict.
        selected_original_upper = 9.741959884446938
        self.assertAlmostEqual(result.lower_bound_m-selected_original_upper, 1.5406804813232107, places=10)

    def test_nonorthogonal_faces_keep_the_original_plane_solve(self):
        base = synthetic_case()
        for sign in (-1., 1.):
            with self.subTest(sign=sign):
                case = replace(base, face_normals_world=((-1., 0., 0.), unit((sign*.24, -1., 0.))))
                self.assert_finite_samples_enclosed(case)

    def test_heading_sign_crossings_and_full_circle(self):
        base = replace(synthetic_case(), forward_world=unit((.01, 1., -.1)))
        for heading_std in (.4, 1.4):
            with self.subTest(heading_std=heading_std):
                result = self.assert_finite_samples_enclosed(replace(base, heading_std_rad=heading_std), headings=33)
                self.assertGreater(result.metadata["witness"]["heading_sign_segments"], 1)

    def test_zero_heading_and_vertical_forward_are_defined(self):
        case = replace(synthetic_case(), heading_std_rad=0., forward_world=(0., 0., -1.))
        self.assert_finite_samples_enclosed(case, headings=1, random_samples=20)

    def test_face_row_order_does_not_select_a_convenient_assignment(self):
        case = recorded_24_7_case()
        swapped = replace(case, face_normals_world=case.face_normals_world[::-1],
                          face_points_world_m=case.face_points_world_m[::-1],
                          face_labels=case.face_labels[::-1], face_std_m=case.face_std_m[::-1])
        self.assertAlmostEqual(correlated_two_face_front_bound(case).lower_bound_m,
                               correlated_two_face_front_bound(swapped).lower_bound_m, places=12)

    def test_each_original_uncertainty_domain_expansion_cannot_improve_bound(self):
        base = recorded_24_7_case()
        original = correlated_two_face_front_bound(base)
        changes = [dict(heading_std_rad=.18), dict(face_std_m=(.08, base.face_std_m[1])),
                   dict(face_std_m=(.04, .09)), dict(ground_residual_std_m=.04),
                   dict(ground_covariance_4x4=np.asarray(base.ground_covariance_4x4)*10000.),
                   dict(depth_noise_std_m=.1), dict(registration_std_m=.06)]
        for i in range(3):
            std = list(base.dimension_std_m); std[i] *= 1.2
            changes.append(dict(dimension_std_m=std))
        for change in changes:
            with self.subTest(change=change):
                result = correlated_two_face_front_bound(replace(base, **change))
                self.assertEqual(result.status, BOUND_STATUS, result)
                self.assertLessEqual(result.lower_bound_m, original.lower_bound_m+1e-10)

    def test_common_rigid_transform_invariance_including_plane_covariance(self):
        case = recorded_24_7_case()
        r, t = rotation((1., 2., -.7), .87), np.array([7., -3., 4.])
        # [normal,offset] -> [R normal, offset-t dot R normal].
        m = np.zeros((4, 4)); m[:3, :3] = r; m[3, :3] = -t @ r; m[3, 3] = 1.
        normal = r @ case.ground_normal_world
        moved = replace(case, forward_world=r @ case.forward_world,
                        camera_position_world_m=r @ case.camera_position_world_m+t,
                        face_normals_world=np.asarray(case.face_normals_world) @ r.T,
                        face_points_world_m=np.asarray(case.face_points_world_m) @ r.T+t,
                        ground_normal_world=normal, ground_offset_m=case.ground_offset_m-float(normal @ t),
                        ground_covariance_4x4=m @ case.ground_covariance_4x4 @ m.T)
        a, b = correlated_two_face_front_bound(case), self.assert_finite_samples_enclosed(moved, headings=9, random_samples=30)
        self.assertAlmostEqual(a.metadata["unrounded_domain_minimum_without_depth_registration_m"],
                               b.metadata["unrounded_domain_minimum_without_depth_registration_m"], places=11)
        self.assertAlmostEqual(a.metadata["ground_variance_m2"], b.metadata["ground_variance_m2"], places=14)

    def test_missing_malformed_single_face_and_invalid_geometry_are_unknown(self):
        case = synthetic_case()
        changes = [dict(ground_covariance_4x4=None), dict(ground_covariance_4x4=np.eye(3)),
                   dict(ground_covariance_4x4=np.diag([-1., 1., 1., 1.])),
                   dict(ground_covariance_4x4=np.eye(4)+np.diag([.1]*3, k=1)),
                   dict(ground_residual_std_m=None), dict(face_labels=("end",)),
                   dict(face_normals_world=((-1., 0., 0.),)), dict(face_points_world_m=None),
                   dict(face_labels=("end", "end")), dict(dimension_std_m=(2., .18, .15)),
                   dict(heading_std_rad=-.1), dict(face_std_m=(.04, -.05)),
                   dict(depth_noise_std_m=None), dict(registration_std_m=float("nan")),
                   dict(ground_normal_world=(0., 0., 2.)), dict(forward_world=(1., 0., 1.)),
                   dict(face_normals_world=((-1., 0., 0.), unit((1., .01, 0.)))),
                   dict(face_normals_world=((-1., 0., 0.), unit((0., -1., .1)))),
                   dict(camera_position_world_m=(0., float("inf"), 0.)),
                   dict(camera_position_world_m=(1e308, 1e308, 1e308)),
                   dict(face_points_world_m=((1e308, 1e308, 1e308), (1e308, -1e308, 1e308))),
                   dict(dimensions_m=(1e308, 1e308, 1e308)),
                   dict(heading_std_rad=1e308), dict(ground_residual_std_m=1e308),
                   dict(heading_std_rad=True), dict(dimension_std_m="missing")]
        for change in changes:
            with self.subTest(change=change):
                result = correlated_two_face_front_bound(replace(case, **change))
                self.assertEqual(result.status, "UNKNOWN", result)
                self.assertIsNone(result.lower_bound_m)
                self.assertEqual(result.metadata, {})
        self.assertEqual(correlated_two_face_front_bound(None).status, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
