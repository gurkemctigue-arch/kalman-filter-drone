"""Conservative directed RGB-D visibility for declared passenger-car priors.

This is an engineering confidence test, not a physical visibility certificate.
It consumes measured same-acquisition support, never GT, mesh or object names.
Unknown geometry retains the strict overlapping-box navigation veto.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import numpy as np

from .navigation import GroundPlane, NavigationPrior, _car_reference
from .body_bounds import BOUND_STATUS, TwoFaceBodyBoundCase, correlated_two_face_front_bound


CONFIDENCE_MULTIPLIER = 3.0
MAX_OVERLAP_PIXELS = 4096
DEPTH_NOISE_STD_M = .05
REGISTRATION_STD_M = .03
MIN_VISIBILITY_SUPPORT = 12


@dataclass(frozen=True)
class VisibilityModel:
    valid: bool = False
    reason: str = "uninitialized"
    center_world_m: Any = None
    axes_world: Any = None
    dimensions_m: Any = None
    face_normals_world: Any = None
    face_points_world: Any = None
    measured_support_world: Any = None
    visible_front_lo_m: float | None = None
    visible_back_hi_m: float | None = None
    body_front_lo_m: float | None = None
    surface_tolerance_m: float = 0.0
    body_tolerance_m: float = 0.0
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _cloud(value: Any) -> np.ndarray:
    points = np.asarray(value, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError("visibility_support_malformed")
    return points


def overlap_pixel_rectangle(box_a, box_b, width: int, height: int) -> tuple[int, int, int, int] | None:
    """All sensor pixel cells touched by a continuous positive-area overlap.

    Pixel cells use [u,u+1)x[v,v+1); rounding outward prevents a subpixel
    intersection from disappearing between integer sampling centers.
    """
    a, b = np.asarray(box_a, dtype=float), np.asarray(box_b, dtype=float)
    if a.shape != (4,) or b.shape != (4,) or not np.isfinite(np.r_[a, b]).all():
        raise ValueError("visibility_bbox_malformed")
    low, high = np.maximum(a[:2], b[:2]), np.minimum(a[2:], b[2:])
    if np.any(high <= low):
        return None
    left, top = np.floor(low).astype(int)
    right, bottom = np.ceil(high).astype(int)
    if left < 0 or top < 0 or right > width or bottom > height:
        raise ValueError("visibility_overlap_outside_image")
    return int(left), int(top), int(right), int(bottom)


def nested_boxes(box_a, box_b) -> bool:
    a, b = np.asarray(box_a, dtype=float), np.asarray(box_b, dtype=float)
    return bool((np.all(a[:2] <= b[:2]) and np.all(a[2:] >= b[2:]))
                or (np.all(b[:2] <= a[:2]) and np.all(b[2:] >= a[2:])))


def fit_unique_visibility_model(points_world, *, ground_plane: GroundPlane,
                                camera_position_world, camera_forward_world,
                                prior: NavigationPrior,
                                correlated_two_face_bound: bool = False) -> VisibilityModel:
    """Enumerate supported foreground groups; never choose the nearest group.

    Each supported group must admit the existing unique end/side face model.
    Any second supported group or unexplained off-model foreground is unknown.
    Ground pixels are distinguished by the independently fitted ground plane.
    """
    try:
        points = _cloud(points_world)
        camera = np.asarray(camera_position_world, dtype=float)
        forward = np.asarray(camera_forward_world, dtype=float)
        if (prior.class_name != "car" or not ground_plane.valid or camera.shape != (3,)
                or forward.shape != (3,) or not np.isfinite(np.r_[camera, forward]).all()
                or not math.isclose(float(np.linalg.norm(forward)), 1., abs_tol=1e-6)):
            return VisibilityModel(reason="visibility_context_invalid")
        heights = points @ ground_plane.normal + ground_plane.offset
        if np.any(heights < -(.05 + CONFIDENCE_MULTIPLIER * ground_plane.residual_std_m)):
            return VisibilityModel(reason="visibility_support_below_ground")
        # This matches the existing geometry operating envelope. Samples beyond
        # it are not quietly assigned to an independently invented vehicle.
        non_ground = heights > .08
        if np.any(heights[non_ground] >= prior.height_m * 1.4 + .15):
            return VisibilityModel(reason="visibility_foreground_height_outside_prior")
        foreground = points[non_ground]
        if len(foreground) < MIN_VISIBILITY_SUPPORT:
            return VisibilityModel(reason="visibility_foreground_support_insufficient")
        ranges = np.linalg.norm(foreground-camera, axis=1)
        order = np.argsort(ranges)
        groups = np.split(order, np.flatnonzero(np.diff(ranges[order]) > .45)+1)
        required = max(MIN_VISIBILITY_SUPPORT, math.ceil(.15 * len(foreground)))
        supported = [group for group in groups if len(group) >= required]
        if len(supported) != 1:
            return VisibilityModel(reason="visibility_foreground_multiple_or_missing",
                                   diagnostics={"supported_groups": len(supported)})
        group = foreground[supported[0]]
        reference = _car_reference(group, ground_plane, camera, prior, None, None, MIN_VISIBILITY_SUPPORT)
        if not reference.valid:
            return VisibilityModel(reason="visibility_" + reference.reason, diagnostics=reference.diagnostics)
        metadata = reference.diagnostics
        length_axis = np.asarray(metadata["body_length_axis_world"])
        lateral = np.asarray(metadata["body_lateral_axis_world"])
        axes = np.column_stack((length_axis, lateral, ground_plane.normal))
        # The navigation reference is a ground footprint, not body centroid.
        center = reference.position_world_m + ground_plane.normal * prior.height_m * .5
        dimensions = np.array([prior.length_m, prior.width_m, prior.height_m])
        normals = np.asarray(metadata["visible_face_normals_world"])
        face_points = np.asarray(metadata["visible_face_points_world"])
        face_sigma = max(metadata["visible_face_sigma_m"])
        surface_sigma = face_sigma + DEPTH_NOISE_STD_M + REGISTRATION_STD_M
        surface_tolerance = CONFIDENCE_MULTIPLIER * surface_sigma
        relative = (foreground-center) @ axes
        inside = np.all(np.abs(relative) <= dimensions*.5 + surface_tolerance, axis=1)
        # Small fragments not explained by the one model also remain unknown;
        # a large valid component does not authorize selecting a convenient one.
        if not inside.all():
            return VisibilityModel(reason="visibility_unexplained_foreground")
        # Every measured body-compatible point belongs to the visible envelope,
        # including roof/windscreen support away from vertical RANSAC planes.
        # A convenient fitted-face subset must not hide a farther target layer.
        visible = foreground
        z = (visible-camera) @ forward
        visible_lo = float(z.min() - surface_tolerance)
        visible_hi = float(z.max() + surface_tolerance)
        coefficients = np.abs(forward @ axes)
        half_extent = float(coefficients @ dimensions) * .5
        # Conservative sums avoid assuming independent fitted-center/dimension
        # errors. k=3 is a declared multiplier, not a calibrated probability.
        sigma_center = math.sqrt(max(0., float(forward @ reference.covariance @ forward)))
        sigma_extent = float(coefficients @ np.asarray(prior.dimension_std_m)) * .5
        sigma_heading = float(np.linalg.norm(dimensions[:2])) * .5 * prior.heading_std_rad
        body_sigma = sigma_center + sigma_extent + sigma_heading + DEPTH_NOISE_STD_M + REGISTRATION_STD_M
        body_tolerance = CONFIDENCE_MULTIPLIER * body_sigma
        front = float((center-camera) @ forward - half_extent - body_tolerance)
        diagnostics = {"scope": "DECLARED_CAR_FAMILY_ENGINEERING_CONFIDENCE_NOT_PHYSICAL_CERTIFICATE",
                       "k": CONFIDENCE_MULTIPLIER, "support_count": len(foreground),
                       "visible_support_count": len(visible), "prior_id": prior.prior_id,
                       "dimensions_m": dimensions.tolist(), "dimension_std_m": list(prior.dimension_std_m),
                       "depth_noise_std_m": DEPTH_NOISE_STD_M, "registration_std_m": REGISTRATION_STD_M,
                       "surface_sigma_m": surface_sigma, "body_sigma_m": body_sigma,
                       "center_world_m": center.tolist(), "camera_position_world_m": camera.tolist(),
                       "camera_forward_world": forward.tolist(),
                       "visible_front_lo_m": visible_lo, "visible_back_hi_m": visible_hi,
                       "body_front_lo_m": front, "geometry": metadata}
        if correlated_two_face_bound:
            # Preserve the unique measured model and selected-support envelope.
            # Only the other body's directional confidence bound can change;
            # all association, complete-pixel and geometry checks still apply.
            bound = correlated_two_face_front_bound(TwoFaceBodyBoundCase(
                forward_world=tuple(forward), camera_position_world_m=tuple(camera),
                face_normals_world=tuple(map(tuple, normals)), face_points_world_m=tuple(map(tuple, face_points)),
                face_labels=tuple(metadata["face_labels"]),
                face_std_m=tuple(metadata["visible_face_sigma_m"]),
                ground_normal_world=tuple(ground_plane.normal), ground_offset_m=ground_plane.offset,
                ground_covariance_4x4=ground_plane.covariance,
                ground_residual_std_m=ground_plane.residual_std_m,
                dimensions_m=tuple(dimensions), dimension_std_m=tuple(prior.dimension_std_m),
                heading_std_rad=prior.heading_std_rad, depth_noise_std_m=DEPTH_NOISE_STD_M,
                registration_std_m=REGISTRATION_STD_M,
            ))
            diagnostics["correlated_two_face_bound"] = {
                "status": bound.status, "reason": bound.reason, "metadata": bound.metadata,
                "legacy_body_front_lo_m": front,
            }
            if (bound.status == BOUND_STATUS and bound.lower_bound_m is not None
                    and math.isfinite(bound.lower_bound_m)):
                front = float(bound.lower_bound_m)
                diagnostics["body_front_lo_m"] = front
                diagnostics["body_front_bound_method"] = "correlated_two_face_fixed_normal_3sigma"
            else:
                diagnostics["body_front_bound_method"] = "legacy_independent_aggregation_fallback"
        return VisibilityModel(valid=True, reason="unique_visible_car_faces", center_world_m=center,
                               axes_world=axes, dimensions_m=dimensions, face_normals_world=normals,
                               face_points_world=face_points, measured_support_world=visible.copy(),
                               visible_front_lo_m=visible_lo, visible_back_hi_m=visible_hi,
                               body_front_lo_m=front, surface_tolerance_m=surface_tolerance,
                               body_tolerance_m=body_tolerance, diagnostics=diagnostics)
    except (ValueError, TypeError, KeyError, np.linalg.LinAlgError) as error:
        return VisibilityModel(reason="visibility_model_error:" + str(error))


def directed_depth_order(selected: VisibilityModel, other: VisibilityModel) -> dict[str, Any]:
    if not selected.valid or not other.valid:
        return {"allowed": False, "reason": "visibility_model_unknown"}
    margin = float(other.body_front_lo_m - selected.visible_back_hi_m)
    return {"allowed": margin > 0., "reason": "selected_visible_faces_in_front" if margin > 0. else "depth_order_uncertain_or_behind",
            "selected_visible_back_hi_m": selected.visible_back_hi_m,
            "other_body_front_lo_m": other.body_front_lo_m, "depth_order_margin_m": margin,
            "k": CONFIDENCE_MULTIPLIER}


def _model_explains(points, model: VisibilityModel, *, visible_only: bool) -> np.ndarray:
    relative = (points-model.center_world_m) @ model.axes_world
    inside = np.all(np.abs(relative) <= model.dimensions_m*.5 + model.surface_tolerance_m, axis=1)
    if not visible_only:
        return inside
    distances = np.min(np.abs(np.einsum("nfi,fi->nf", points[:, None, :]-model.face_points_world,
                                       model.face_normals_world)), axis=1)
    # A measured roof/windscreen continuation can explain an overlap pixel
    # without inventing an unobserved cuboid surface. Chunking bounds memory
    # for a full 4096-pixel intersection and up to 500 support samples.
    close_support = np.zeros(len(points), dtype=bool)
    for start in range(0, len(points), 256):
        difference = points[start:start+256, None, :] - model.measured_support_world[None, :, :]
        close_support[start:start+256] = np.min(np.linalg.norm(difference, axis=2), axis=1) <= model.surface_tolerance_m
    return inside & ((distances <= model.surface_tolerance_m) | close_support)


def assess_overlap_visibility(selected: VisibilityModel, other: VisibilityModel, points_world,
                              *, expected_pixels: int, valid_pixels: int,
                              ground_plane: GroundPlane) -> dict[str, Any]:
    """All pair pixels must be explained; no depth holes or subsampling waiver."""
    decision = directed_depth_order(selected, other)
    if not decision["allowed"]:
        return decision
    if (isinstance(expected_pixels, bool) or not isinstance(expected_pixels, (int, np.integer))
            or isinstance(valid_pixels, bool) or not isinstance(valid_pixels, (int, np.integer))
            or not 0 < expected_pixels <= MAX_OVERLAP_PIXELS or valid_pixels != expected_pixels
            or not ground_plane.valid):
        return {**decision, "allowed": False, "reason": "overlap_depth_incomplete_or_over_budget"}
    try:
        points = _cloud(points_world)
        if len(points) != expected_pixels:
            return {**decision, "allowed": False, "reason": "overlap_pixel_count_mismatch"}
        heights = np.abs(points @ ground_plane.normal + ground_plane.offset)
        ground_tolerance = .05 + CONFIDENCE_MULTIPLIER * ground_plane.residual_std_m
        ground = heights <= ground_tolerance
        selected_support = _model_explains(points, selected, visible_only=True)
        other_support = _model_explains(points, other, visible_only=False)
        explained = ground | selected_support | other_support
        counts = {"expected_pixels": int(expected_pixels), "valid_pixels": int(valid_pixels),
                  "selected_foreground_pixels": int(selected_support.sum()),
                  "other_geometry_pixels": int(other_support.sum()), "ground_pixels": int(ground.sum()),
                  "unexplained_pixels": int((~explained).sum())}
        return {**decision, **counts, "allowed": bool(explained.all()),
                "reason": "directed_front_visible" if explained.all() else "overlap_unexplained_foreground"}
    except (ValueError, TypeError, np.linalg.LinAlgError) as error:
        return {**decision, "allowed": False, "reason": "overlap_geometry_error:" + str(error)}


__all__ = ["VisibilityModel", "fit_unique_visibility_model", "directed_depth_order",
           "assess_overlap_visibility", "overlap_pixel_rectangle", "nested_boxes",
           "MAX_OVERLAP_PIXELS"]
