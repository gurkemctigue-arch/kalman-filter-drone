"""Correlated front support for a declared two-face car engineering model.

The complete original three-sigma dimension, common heading, face-offset,
scalar ground-distance, depth and registration domains are retained. Normals
are fixed nominal fitted normals. This is not a physical visibility or identity
certificate. Callers remain responsible for unique geometry, acquisition,
association, all-pair and full overlap-pixel checks. No runtime policy lives here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import itertools
import math
from typing import Any

import numpy as np


CONFIDENCE_MULTIPLIER = 3.0
BOUND_STATUS = "ENGINEERING_3SIGMA_FIXED_NORMAL_BOUND"


@dataclass(frozen=True)
class TwoFaceBodyBoundCase:
    """All uncertainty inputs are required; absent data is never zero-filled."""

    forward_world: Any
    camera_position_world_m: Any
    face_normals_world: Any
    face_points_world_m: Any
    face_labels: Any
    face_std_m: Any
    ground_normal_world: Any
    ground_offset_m: Any
    ground_covariance_4x4: Any
    ground_residual_std_m: Any
    dimensions_m: Any
    dimension_std_m: Any
    heading_std_rad: Any
    depth_noise_std_m: Any
    registration_std_m: Any


@dataclass(frozen=True)
class BodyFrontBound:
    status: str = "UNKNOWN"
    lower_bound_m: float | None = None
    reason: str = "uninitialized"
    metadata: dict[str, Any] = field(default_factory=dict)


def _array(value, shape, name):
    raw = np.asarray(value)
    if raw.dtype.kind not in "fiu" or raw.shape != shape:
        raise ValueError(name + "_malformed")
    array = raw.astype(float, copy=True)
    if not np.isfinite(array).all():
        raise ValueError(name + "_nonfinite")
    return array


def _scalar(value, name, *, nonnegative=False):
    if isinstance(value, (bool, str, bytes)) or not np.isscalar(value):
        raise ValueError(name + "_malformed")
    number = float(value)
    if not math.isfinite(number) or (nonnegative and number < 0.):
        raise ValueError(name + "_invalid")
    return number


def _prepare(case):
    if not isinstance(case, TwoFaceBodyBoundCase):
        raise ValueError("two_face_case_required")
    if not isinstance(case.face_labels, (list, tuple)) or sorted(case.face_labels) != ["end", "side"]:
        raise ValueError("two_distinct_end_side_labels_required")
    f = _array(case.forward_world, (3,), "forward")
    camera = _array(case.camera_position_world_m, (3,), "camera")
    normals = _array(case.face_normals_world, (2, 3), "face_normals")
    points = _array(case.face_points_world_m, (2, 3), "face_points")
    up = _array(case.ground_normal_world, (3,), "ground_normal")
    dims = _array(case.dimensions_m, (3,), "dimensions")
    dims_std = _array(case.dimension_std_m, (3,), "dimension_std")
    face_std = _array(case.face_std_m, (2,), "face_std")
    covariance = _array(case.ground_covariance_4x4, (4, 4), "ground_covariance")
    offset = _scalar(case.ground_offset_m, "ground_offset")
    residual = _scalar(case.ground_residual_std_m, "ground_residual", nonnegative=True)
    heading = _scalar(case.heading_std_rad, "heading_std", nonnegative=True)
    depth = _scalar(case.depth_noise_std_m, "depth_std", nonnegative=True)
    registration = _scalar(case.registration_std_m, "registration_std", nonnegative=True)
    if np.any(dims_std < 0.) or np.any(face_std < 0.):
        raise ValueError("negative_standard_deviation")
    if any(abs(float(np.linalg.norm(v))-1.) > 1e-8 for v in (f, up, *normals)):
        raise ValueError("nonunit_direction")
    if np.any(np.abs(normals @ up) > 1e-8):
        raise ValueError("face_not_vertical_in_fixed_normal_model")
    if abs(float(normals[0] @ normals[1])) > math.sin(math.radians(15.))+1e-12:
        raise ValueError("source_face_angle_gate_failed")
    matrix = np.vstack((normals, up))
    determinant = float(np.linalg.det(matrix))
    if abs(determinant) < .8:
        raise ValueError("source_matrix_determinant_gate_failed")
    scale = float(np.max(np.abs(covariance)))
    tolerance = 64.*np.finfo(float).eps*scale
    if not np.allclose(covariance, covariance.T, rtol=0., atol=tolerance):
        raise ValueError("ground_covariance_not_symmetric")
    if float(np.linalg.eigvalsh(covariance).min()) < -tolerance:
        raise ValueError("ground_covariance_not_psd")
    k = CONFIDENCE_MULTIPLIER
    intervals = np.column_stack((dims-k*dims_std, dims+k*dims_std))
    if not np.isfinite(intervals).all() or np.any(intervals[:, 0] <= 0.):
        raise ValueError("dimension_domain_not_positive_finite")
    if not math.isfinite(k*heading) or not np.isfinite(k*face_std).all():
        raise ValueError("uncertainty_domain_nonfinite")
    mapping = tuple(0 if label == "end" else 1 for label in case.face_labels)
    inverse = np.linalg.inv(matrix)
    corner_rhs = np.r_[np.einsum("ij,ij->i", normals, points), -offset]
    corner = inverse @ corner_rhs
    center = corner-inverse @ np.r_[dims[list(mapping)]*.5, 0.]
    homogeneous = np.r_[center, 1.]
    covariance_term = float(homogeneous @ covariance @ homogeneous)
    if covariance_term < -tolerance*float(homogeneous @ homogeneous):
        raise ValueError("negative_original_nominal_center_ground_variance")
    components = {"source_floor_m2": .02**2,
                  "source_residual_variance_m2": residual**2,
                  "original_covariance_quadratic_m2": covariance_term}
    ground_variance = max(components.values())
    length = normals[case.face_labels.index("end")]
    lateral = np.cross(up, length)
    offset_stds = np.r_[face_std, math.sqrt(ground_variance)]
    offset_intervals = np.column_stack((-k*offset_stds, k*offset_stds))
    finite = [*corner, *center, *offset_intervals.ravel(), *components.values()]
    if not all(math.isfinite(float(v)) for v in finite):
        raise ValueError("derived_geometry_or_uncertainty_nonfinite")
    return {"f": f, "camera": camera, "up": up, "inverse": inverse,
            "corner": corner, "center": center, "mapping": mapping,
            "length": length, "lateral": lateral, "determinant": determinant,
            "dimension_intervals": intervals, "offset_intervals": offset_intervals,
            "heading_half_width": k*heading, "depth_registration": k*(depth+registration),
            "ground_variance": ground_variance, "ground_components": components, "dimensions": dims}


def _projection_coefficients(f, vector, up):
    constant = float(f @ up)*float(up @ vector)
    return constant, float(f @ vector)-constant, float(f @ np.cross(up, vector))


def _value(coefficients, angle):
    c, a, b = coefficients
    return c+a*math.cos(angle)+b*math.sin(angle)


def _periodic_candidates(phase, period, low, high):
    first = math.ceil((low-phase)/period-1e-14)
    last = math.floor((high-phase)/period+1e-14)
    return [max(low, min(high, phase+j*period)) for j in range(first, last+1)]


def _zeros(coefficients, low, high):
    c, a, b = coefficients
    radius = math.hypot(a, b)
    if radius == 0. or abs(c) > radius:
        return []
    phase = math.atan2(b, a)
    delta = math.acos(max(-1., min(1., -c/radius)))
    return (_periodic_candidates(phase+delta, 2.*math.pi, low, high)
            + _periodic_candidates(phase-delta, 2.*math.pi, low, high))


def _minimum_for_corner(prepared, dims, offsets, axis_coefficients):
    p = prepared
    rhs = np.r_[[offsets[j]-.5*dims[i] for j, i in enumerate(p["mapping"])], offsets[2]]
    rotating = _projection_coefficients(p["f"], p["inverse"] @ rhs, p["up"])
    length, lateral = axis_coefficients
    base = float(p["f"] @ (p["corner"]-p["camera"]))+dims[2]*min(float(p["f"] @ p["up"]), 0.)
    half = min(p["heading_half_width"], math.pi)  # A wider domain contains a full period.
    low, high = -half, half
    cuts = sorted(set((low, high, *_zeros(length, low, high), *_zeros(lateral, low, high))))
    def front(angle):
        return (base+_value(rotating, angle)-.5*dims[0]*abs(_value(length, angle))
                -.5*dims[1]*abs(_value(lateral, angle)))
    candidates = list(cuts)
    for left, right in zip(cuts, cuts[1:]):
        middle = .5*(left+right)
        sl = 1. if _value(length, middle) >= 0. else -1.
        st = 1. if _value(lateral, middle) >= 0. else -1.
        a = rotating[1]-.5*dims[0]*sl*length[1]-.5*dims[1]*st*lateral[1]
        b = rotating[2]-.5*dims[0]*sl*length[2]-.5*dims[1]*st*lateral[2]
        if a != 0. or b != 0.:
            candidates.extend(_periodic_candidates(math.atan2(b, a), math.pi, left, right))
    angle = min(candidates, key=front)
    return front(angle), angle, len(candidates), max(len(cuts)-1, 0)


def correlated_two_face_front_bound(case: TwoFaceBodyBoundCase) -> BodyFrontBound:
    """Minimize the entire source-model cuboid over its original error box.

    For fixed heading the front is affine in three dimensions and three plane
    offsets, so all 64 corners suffice. Each corner's continuous heading domain
    is split at exact sinusoidal axis-projection zeros. Segment endpoints and
    derivative roots give every possible minimum. A grid is not used.

    Common same-frame rigid TF errors cancel only when the complete model and
    ground construction transform together. Independent/time-varying pose or
    normal-error domains are not asserted here. The numerical guard below is
    deliberately identified as ordinary floating point, not certified rounding.
    """
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            p = _prepare(case)
            axis_coefficients = tuple(_projection_coefficients(p["f"], axis, p["up"])
                                      for axis in (p["length"], p["lateral"]))
            best = None
            candidate_count = 0
            for dims, offsets in itertools.product(itertools.product(*p["dimension_intervals"]),
                                                    itertools.product(*p["offset_intervals"])):
                value, angle, count, segments = _minimum_for_corner(p, dims, offsets, axis_coefficients)
                candidate_count += count
                if best is None or value < best[0]:
                    best = value, angle, dims, offsets, segments
            value, angle, dims, offsets, segments = best
            guard = 1e-10*(1.+abs(value)+float(np.linalg.norm(p["corner"]))
                           +float(np.linalg.norm(p["camera"]))+float(p["dimensions"].sum()))
            lower = value-p["depth_registration"]-guard
            if not all(math.isfinite(x) for x in (value, lower, guard, p["depth_registration"])):
                raise ValueError("computed_bound_nonfinite")
            metadata = {
                "scope": "DECLARED_CAR_FAMILY_ENGINEERING_CONFIDENCE_NOT_PHYSICAL_CERTIFICATE",
                "uncertainty_model": "FIXED_NOMINAL_NORMALS_SHARED_DIMENSIONS_AND_CORNER_HEADING",
                "k": CONFIDENCE_MULTIPLIER, "parameter_corners_evaluated": 64,
                "analytic_heading_candidates_evaluated": candidate_count,
                "dimension_intervals_m": p["dimension_intervals"].tolist(),
                "plane_offset_intervals_m": p["offset_intervals"].tolist(),
                "heading_interval_rad": [-p["heading_half_width"], p["heading_half_width"]],
                "ground_variance_m2": p["ground_variance"],
                "ground_variance_components_m2": p["ground_components"],
                "nominal_ground_center_world_m": p["center"].tolist(),
                "measured_corner_world_m": p["corner"].tolist(),
                "source_matrix_determinant": p["determinant"],
                "unrounded_domain_minimum_without_depth_registration_m": value,
                "retained_depth_registration_three_sigma_m": p["depth_registration"],
                "floating_point_guard_m": guard, "certified_outward_rounding": False,
                "witness": {"heading_rad": angle, "dimensions_m": [float(v) for v in dims],
                            "plane_offsets_m": [float(v) for v in offsets],
                            "heading_sign_segments": segments},
            }
            return BodyFrontBound(BOUND_STATUS, lower, "complete_declared_two_face_domain", metadata)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError,
            OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        return BodyFrontBound(reason=str(error))
