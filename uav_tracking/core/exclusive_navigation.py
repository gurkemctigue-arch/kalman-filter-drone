"""Conditional car reference from complete, independent native depth pixels.

This opt-in measurement has a different dependency domain from full-box
navigation: shared pixels never enter its fit, center or uncertainty. The caller
must retain same-frame task/association/ambiguity/LOST protection. Bounding boxes
are detector hypotheses, not physical ownership or a segmentation certificate.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from .geometry import CameraIntrinsics
from .navigation import GroundPlane, NavigationEstimate, NavigationPrior, _car_reference
from .visibility import fit_unique_visibility_model


METHOD = "native_exclusive_single_face_center_v1"
MAX_EXCLUSIVE_PIXELS = 16384
MAX_IMAGE_PIXELS = 307200
MAX_OTHER_BOXES = 64
SCOPE = "CONDITIONAL_ON_ORIGINAL_FITTED_SINGLE_FACE_LABEL_AND_GROUND_NOT_PHYSICAL_CERTIFICATE"


def extract_native_exclusive(
    depth_image: Any,
    intrinsics: Any,
    bbox: Sequence[float],
    other_bboxes: Sequence[Sequence[float]],
    *,
    depth_scale: float = 1.0,
    min_depth_m: float = .2,
    max_depth_m: float = 50.0,
) -> dict[str, Any]:
    """Return every selected native pixel outside all other detected boxes.

    Selected bounds round inward; every other class's bounds round outward.
    There is no stride, cap, interpolation, invalid-depth removal, body clipping,
    nearest-layer selection or implicit forgiveness of an unknown competitor.
    An invalid result exposes counts but no consumable partial point cloud.
    """
    result: dict[str, Any] = {
        "method": METHOD, "valid": False, "reason": "exclusive_context_invalid",
        "expected_pixels": 0, "valid_pixels": 0, "budget_pixels": MAX_EXCLUSIVE_PIXELS,
        "excluded_bbox_count": 0,
    }
    try:
        image = np.asarray(depth_image)
        if image.ndim != 2:
            return result
        if image.size > MAX_IMAGE_PIXELS:
            return {**result, "reason": "exclusive_image_budget_exceeded"}
        result["excluded_bbox_count"] = len(other_bboxes)
        if len(other_bboxes) > MAX_OTHER_BOXES:
            return {**result, "reason": "exclusive_competitor_budget_exceeded"}
        height, width = image.shape
        result.update(image_width=width, image_height=height)
        camera = CameraIntrinsics.from_value(intrinsics)
        box = np.asarray(bbox, dtype=float)
        if (not math.isfinite(depth_scale) or depth_scale <= 0 or
                not math.isfinite(max_depth_m) or not 0 <= min_depth_m < max_depth_m):
            return result
        if (box.shape != (4,) or not np.isfinite(box).all() or
                not (box[0] > 2 and box[1] > 2 and box[2] < width-2 and box[3] < height-2)):
            return {**result, "reason": "exclusive_bbox_edge_or_malformed"}
        left, top = np.ceil(box[:2]).astype(int)
        right, bottom = np.floor(box[2:]).astype(int)
        if right <= left or bottom <= top:
            return {**result, "reason": "exclusive_bbox_empty"}
        u, v = np.meshgrid(np.arange(left, right), np.arange(top, bottom))
        u, v = u.ravel(), v.ravel()
        keep = np.ones(len(u), dtype=bool)
        for other in other_bboxes:
            other = np.asarray(other, dtype=float)
            if other.shape != (4,) or not np.isfinite(other).all():
                return {**result, "reason": "exclusive_competitor_bbox_malformed"}
            if other[2] <= other[0] or other[3] <= other[1]:
                continue
            # Clip in floating point before integer conversion: a finite bbox
            # may exceed int64 even though its intersection is representable.
            limits = np.array([width, height], dtype=float)
            lo = np.floor(np.clip(other[:2], 0., limits)).astype(int)
            hi = np.ceil(np.clip(other[2:], 0., limits)).astype(int)
            keep &= ~((u >= lo[0]) & (u < hi[0]) & (v >= lo[1]) & (v < hi[1]))
        u, v = u[keep], v[keep]
        result["expected_pixels"] = len(u)
        if len(u) > MAX_EXCLUSIVE_PIXELS:
            return {**result, "reason": "exclusive_native_budget_exceeded"}
        if len(u) < 12:
            return {**result, "reason": "exclusive_native_support_missing"}
        z = image[v, u].astype(float)*depth_scale
        valid = np.isfinite(z) & (z >= min_depth_m) & (z <= max_depth_m) & (z > 0)
        result["valid_pixels"] = int(valid.sum())
        if not valid.all():
            return {**result, "reason": "exclusive_native_depth_incomplete"}
        points = np.column_stack(((u-camera.cx)*z/camera.fx, (v-camera.cy)*z/camera.fy, z))
        if not np.isfinite(points).all():
            return {**result, "reason": "exclusive_projection_nonfinite"}
        return {**result, "valid": True, "reason": "complete_native_exclusive",
                "points_camera_m": points, "pixel_uv": np.column_stack((u, v))}
    except (ValueError, TypeError, OverflowError, IndexError):
        return result


def _trig_interval(a: float, b: float, delta: float) -> np.ndarray:
    angles = [-delta, delta]
    phase = math.atan2(b, a)
    for k in range(-3, 4):
        value = phase+k*math.pi
        if -delta <= value <= delta:
            angles.append(value)
    values = [a*math.cos(t)+b*math.sin(t) for t in angles]
    return np.array([min(values), max(values)])


def _product(a, b) -> np.ndarray:
    values = [x*y for x in a for y in b]
    return np.array([min(values), max(values)])


def estimate_exclusive_reference(
    points_world: Any,
    *,
    ground_plane: GroundPlane,
    camera_position_world: Any,
    camera_forward_world: Any,
    prior: NavigationPrior,
) -> NavigationEstimate:
    """Estimate a single-face reference with explicit truncation uncertainty.

    Validity is conditional on the original unique nominal end/side face model,
    declared family and fitted ground. It is not proof of identity, complete
    visibility or label uniqueness over all noisy alternative physical worlds.
    Dimension/heading domains and original ground covariance are retained. Ego
    pose uncertainty must still be added by the caller. Two faces currently
    return UNKNOWN rather than reuse a partial single-face argument.
    """
    diagnostics: dict[str, Any] = {"method": METHOD, "scope": SCOPE,
        "measurement_domain": "ALL_NATIVE_SELECTED_PIXELS_EXCLUDING_ALL_OTHER_DETECTED_BOXES",
        "identity_assessed": False, "complete_error_domain_assignment_uniqueness_proven": False,
        "ego_pose_uncertainty_added_here": False}

    def invalid(reason: str) -> NavigationEstimate:
        return NavigationEstimate(reason=reason, diagnostics=diagnostics)

    try:
        points = np.asarray(points_world, dtype=float)
        if (points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all()
                or not 12 <= len(points) <= MAX_EXCLUSIVE_PIXELS):
            return invalid("exclusive_support_malformed_missing_or_over_budget")
        model = fit_unique_visibility_model(points, ground_plane=ground_plane,
            camera_position_world=camera_position_world, camera_forward_world=camera_forward_world,
            prior=prior, correlated_two_face_bound=False)
        diagnostics.update(native_support_count=len(points), original_model_reason=model.reason,
                           original_model=model.diagnostics)
        if not model.valid:
            return invalid("exclusive_"+model.reason)
        geometry = model.diagnostics["geometry"]
        labels = geometry["face_labels"]
        if len(labels) != 1:
            return invalid("exclusive_single_face_required")
        n = ground_plane.normal
        outward = np.array(geometry["visible_face_normals_world"][0], dtype=float)
        outward -= n*float(outward@n)
        outward /= np.linalg.norm(outward)
        tangent = np.cross(n, outward)
        anchor = np.array(geometry["visible_face_points_world"][0], dtype=float)
        anchor -= n*float(anchor@n+ground_plane.offset)
        foreground = points[(points@n+ground_plane.offset) > .08]
        fitted = foreground[np.abs((foreground-anchor)@outward) <= .16]
        if len(fitted) < 12:
            return invalid("exclusive_face_support_insufficient")
        original = _car_reference(foreground, ground_plane, np.asarray(camera_position_world), prior, None, None, 12)
        if not original.valid or original.diagnostics.get("face_labels") != labels:
            return invalid("exclusive_original_face_assignment_inconsistent")
        dimensions = np.array([prior.length_m, prior.width_m, prior.height_m])
        std = np.asarray(prior.dimension_std_m)
        low, high = dimensions-3*std, dimensions+3*std
        delta = 3*prior.heading_std_rad
        if np.any(low <= 0) or delta > math.pi/2:
            return invalid("exclusive_prior_domain_unsupported")
        # Additional rejection over the full dimension domain while holding
        # the original fitted span fixed. This does not prove label uniqueness
        # over the complete noisy/rotated observation domain (see scope).
        span = float(geometry["visible_face_spans_m"][0])
        dimension_only_assignments = [label for label, index in (("end", 1), ("side", 0))
                                      if .65*low[index] <= span <= 1.25*high[index]]
        diagnostics["fixed_span_dimension_only_assignments"] = dimension_only_assignments
        if len(dimension_only_assignments) != 1 or dimension_only_assignments[0] != labels[0]:
            return invalid("exclusive_fixed_span_dimension_assignment_ambiguous")
        normal_index, tangent_index = (0, 1) if labels[0] == "end" else (1, 0)
        sigma = float(geometry["visible_face_sigma_m"][0])
        epsilon = 3*(sigma+.05+.03)
        relative, face_relative = foreground-anchor, fitted-anchor
        normal_projection = np.array([_trig_interval(float(q@outward), float(q@tangent), delta) for q in face_relative])
        tangent_projection = np.array([_trig_interval(float(q@tangent), -float(q@outward), delta) for q in relative])
        face_interval = np.array([normal_projection[:, 0].max()-epsilon, normal_projection[:, 1].min()+epsilon])
        tangent_interval = np.array([tangent_projection[:, 0].max()-high[tangent_index]*.5-epsilon,
                                    tangent_projection[:, 1].min()+high[tangent_index]*.5+epsilon])
        if face_interval[0] > face_interval[1] or tangent_interval[0] > tangent_interval[1]:
            return invalid("exclusive_center_domain_empty")
        normal_interval = face_interval-np.array([high[normal_index], low[normal_index]])*.5
        cos_interval, sin_interval = [math.cos(delta), 1.], [-math.sin(delta), math.sin(delta)]
        normal_box = _product(normal_interval, cos_interval)-_product(tangent_interval, sin_interval)[::-1]
        tangent_box = _product(normal_interval, sin_interval)+_product(tangent_interval, cos_interval)
        midpoint = np.array([normal_box.mean(), tangent_box.mean()])
        half = np.array([np.ptp(normal_box)*.5, np.ptp(tangent_box)*.5])
        center = anchor+outward*midpoint[0]+tangent*midpoint[1]
        covariance = original.covariance.copy()
        covariance += half[0]**2/3*np.outer(outward, outward)+half[1]**2/3*np.outer(tangent, tangent)
        covariance = (covariance+covariance.T)*.5
        if not np.isfinite(center).all() or not np.isfinite(covariance).all():
            return invalid("exclusive_center_or_covariance_nonfinite")
        nominal_tangent = foreground@tangent
        nominal_interval = [float(nominal_tangent.max()-high[tangent_index]*.5-epsilon),
                            float(nominal_tangent.min()+high[tangent_index]*.5+epsilon)]
        radius = float(np.max(np.linalg.norm(face_relative, axis=1)))
        span_error = 2*epsilon+4*radius*math.sin(delta/2)
        span_outer = [max(0., span-span_error), span+span_error]
        not_excluded = [label for label, index in (("end", 1), ("side", 0))
                        if span_outer[1] >= .65*low[index] and span_outer[0] <= 1.25*high[index]]
        diagnostics.update(
            conditioning_on_original_fitted_label=labels[0],
            original_geometry=geometry,
            full_dimension_domain_m=np.column_stack((low, high)).tolist(),
            full_heading_domain_rad=[-delta, delta], surface_error_radius_m=epsilon,
            nominal_heading_tangent_center_interval_world_m=nominal_interval,
            normal_center_interval_relative_anchor_m=normal_box.tolist(),
            tangent_center_interval_relative_anchor_m=tangent_box.tolist(),
            outer_horizontal_halfwidth_m=half.tolist(),
            representative_center_world_m=center.tolist(),
            original_reference_world_m=original.position_world_m.tolist(),
            representative_delta_from_original_m=float(np.linalg.norm(center-original.position_world_m)),
            conservative_noisy_rotated_span_interval_m=span_outer,
            assignments_not_excluded_by_conservative_span_outer_bound=not_excluded,
            span_outer_bound_is_feasibility_witness=False,
            covariance_scope="ORIGINAL_GEOMETRY_COVARIANCE_PLUS_DETERMINISTIC_BOX_ENCODING_NOT_CALIBRATED_CROP_VARIANCE",
            covariance_box_encoding="R_add=sum(halfwidth_i^2/3 * axis_i axis_i^T); rectangle d^2<=6<9",
            ground_pose_scope="Fitted-ground conditional envelope; original approximate ground covariance retained; caller adds ego pose",
            ownership_assumption="Exclusive foreground belongs to selected object within detector/association/family scope; not physical proof",
        )
        return NavigationEstimate(center, covariance, True, "exclusive_conditional_single_face_center",
            "car_cuboid_ground_center", len(foreground), "exclusive_visible_face_shape_prior", diagnostics)
    except (ValueError, TypeError, KeyError, IndexError, np.linalg.LinAlgError):
        return invalid("exclusive_geometry_error")


__all__ = ["METHOD", "MAX_EXCLUSIVE_PIXELS", "extract_native_exclusive", "estimate_exclusive_reference"]
