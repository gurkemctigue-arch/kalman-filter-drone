"""Measured car-surface centroids with one shared ground fit per RGB-D frame.

This only proposes a visible-surface reference. It does not assign identity,
calibrate R, alter an existing raw observation, or grant navigation permission.
UNKNOWN has ``measurement=None``; callers retain their original raw behavior.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import math
from typing import Any, Sequence

import numpy as np

from .geometry import CameraIntrinsics, _clip_roi, depth_roi_stats, pinhole_backproject
from .models import normalize_bbox
from .navigation import NavigationPrior, fit_ground_plane, sample_depth_points
from .visibility import MIN_VISIBILITY_SUPPORT, _model_explains, fit_unique_visibility_model


@dataclass(frozen=True)
class DepthOptions:
    min_depth_m: float
    max_depth_m: float
    depth_scale: float = 1.0
    roi_margin: float = .15
    min_valid_fraction: float = .35


@dataclass(frozen=True)
class SamplingOptions:
    exclusive_stride: int = 2
    exclusive_max_points: int = 500
    ground_stride: int = 8
    ground_max_points: int = 1200
    image_edge_margin_px: float = 2.0


@dataclass(frozen=True)
class GroundOptions:
    min_support: int = 40
    min_inlier_ratio: float = .25
    distance_threshold_m: float = .05
    max_tilt_deg: float = 25.
    iterations: int = 80
    random_seed: int = 0


@dataclass(frozen=True)
class WorkBudget:
    max_image_pixels: int
    max_roi_pixels: int
    max_visible_boxes: int


def component_centroid(points: Any) -> np.ndarray:
    """Mean of one complete finite component; no representative-pixel choice.

    This operator is rigid-equivariant for a fixed point set. Membership may
    still change with viewpoint, occlusion, depth faults or detection boxes.
    """
    values = np.asarray(points, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("centroid requires a nonempty finite Nx3 component")
    return np.mean(values, axis=0, dtype=np.float64)


def _validate(depth, sampling, ground, budget):
    if (not math.isfinite(depth.depth_scale) or depth.depth_scale <= 0
            or not 0 <= depth.min_depth_m < depth.max_depth_m or not math.isfinite(depth.max_depth_m)
            or not 0 <= depth.roi_margin < .5 or not 0 <= depth.min_valid_fraction <= 1):
        raise ValueError("invalid original depth options")
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in asdict(budget).values()):
        raise ValueError("work budget entries must be positive integers")
    for name, maximum in (("exclusive_stride", None), ("ground_stride", None),
                          ("exclusive_max_points", 500), ("ground_max_points", 1200)):
        value = getattr(sampling, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1 or (maximum is not None and value > maximum):
            raise ValueError("invalid or over-budget sampling option: " + name)
    if not math.isfinite(sampling.image_edge_margin_px) or sampling.image_edge_margin_px < 2.:
        raise ValueError("image edge margin must preserve the original >=2px envelope")
    if (isinstance(ground.min_support, bool) or not isinstance(ground.min_support, int) or ground.min_support < 40
            or not math.isfinite(ground.min_inlier_ratio) or not .25 <= ground.min_inlier_ratio <= 1.
            or not math.isfinite(ground.distance_threshold_m) or not 0 < ground.distance_threshold_m <= .05
            or not math.isfinite(ground.max_tilt_deg) or not 0 <= ground.max_tilt_deg <= 25.
            or isinstance(ground.iterations, bool) or not isinstance(ground.iterations, int) or not 1 <= ground.iterations <= 80
            or isinstance(ground.random_seed, bool) or not isinstance(ground.random_seed, int) or not 0 <= ground.random_seed < 2**32):
        raise ValueError("ground options must retain the original bounded envelope")


def _groups(points, plane):
    """Enumerate every radial foreground component in stable measured order."""
    heights = points[:, 2:] @ plane.normal + plane.offset
    foreground = np.flatnonzero(heights > .08)
    if len(foreground) == 0:
        return [], []
    ranges = np.linalg.norm(points[foreground, 2:], axis=1)
    order = np.argsort(ranges, kind="stable")
    partitions = np.split(order, np.flatnonzero(np.diff(ranges[order]) > .45) + 1)
    required = max(MIN_VISIBILITY_SUPPORT, math.ceil(.15 * len(foreground)))
    descriptions, indices = [], []
    for i, partition in enumerate(partitions):
        chosen = foreground[partition]
        descriptions.append({"group_index": i, "count": len(partition), "required_count": required,
            "supported": len(partition) >= required, "range_min_m": float(ranges[partition].min()),
            "range_max_m": float(ranges[partition].max()), "z_min_m": float(points[chosen, 4].min()),
            "z_max_m": float(points[chosen, 4].max())})
        indices.append(chosen)
    return descriptions, indices


class CarSurfaceFrame:
    """One acquisition's bounded depth snapshot, all boxes and shared plane.

    Use ``prepare_car_surface_frame``. ``assess`` returns detached compact
    dictionaries and caches per-box work; no complete cloud escapes the core.
    The supplied up vector must belong to this same acquisition. Plane fitting
    assumes a suitable near-up background; it cannot distinguish a level roof.
    """
    def __init__(self, image, camera, boxes, depth, prior, up, budget, sampling, ground, correlated):
        self._depth, self._prior, self._up = depth, prior, up.copy()
        self._budget, self._sampling, self._ground_options = budget, sampling, ground
        self._camera, self._correlated = camera, correlated
        self._image = image.copy() if image.size <= budget.max_image_pixels else image
        if self._image is not image:
            self._image.setflags(write=False)
        # Over-budget inputs never normalize/copy the complete box collection,
        # never prepare depth and never fit ground; requested boxes stay raw.
        self._raw_boxes = boxes
        self._boxes = tuple(normalize_bbox(b) for b in boxes) if len(boxes) <= budget.max_visible_boxes else None
        if self._boxes is not None:
            self._raw_boxes = self._boxes
        self._depth_m = self._valid = self._plane = None
        self._ground_evidence = None
        self._ground_calls = self._depth_preparations = 0
        self._cache = {}

    @property
    def diagnostics(self):
        return {"scope": "CAR_SURFACE_MEASUREMENT_ONLY_NOT_IDENTITY_OR_NAVIGATION",
                "visible_box_count": len(self._raw_boxes), "ground_fit_calls": self._ground_calls,
                "strict_depth_preparations": self._depth_preparations, "cached_assessments": len(self._cache),
                "ground": deepcopy(self._ground_evidence)}

    def _prepare_ground(self):
        if self._plane is not None:
            return
        depth = np.asarray(self._image, dtype=float) * self._depth.depth_scale
        self._valid = np.isfinite(depth) & (depth > self._depth.min_depth_m) & (depth <= self._depth.max_depth_m)
        self._depth_m = np.where(self._valid, depth, np.nan)
        self._depth_preparations += 1
        points = sample_depth_points(self._depth_m, self._camera, exclude_bboxes=self._boxes,
            stride=self._sampling.ground_stride, max_points=self._sampling.ground_max_points,
            min_depth_m=self._depth.min_depth_m, max_depth_m=self._depth.max_depth_m)
        self._plane = fit_ground_plane(points, up_world=self._up, **asdict(self._ground_options))
        self._ground_calls += 1
        plane = self._plane
        self._ground_evidence = {"valid": plane.valid, "reason": plane.reason, "samples": plane.sample_count,
            "inliers": plane.inlier_count, "residual_std_m": plane.residual_std_m,
            "normal_camera": None if not plane.valid else plane.normal.tolist(), "offset_m": plane.offset,
            "up_camera": self._up.tolist(),
            "scope": "independent_near_up_background_plane_with_declared_environment_assumption"}

    def assess(self, box_index: int, *, class_name: str = "car") -> dict[str, Any]:
        if (isinstance(box_index, bool) or not isinstance(box_index, (int, np.integer))
                or not 0 <= box_index < len(self._raw_boxes)):
            raise ValueError("box_index must identify an original visible box")
        key = int(box_index), class_name == "car"
        if key not in self._cache:
            self._cache[key] = self._assess(int(box_index), class_name)
        return deepcopy(self._cache[key])

    def _assess(self, box_index, class_name):
        box = self._boxes[box_index] if self._boxes is not None else normalize_bbox(self._raw_boxes[box_index])
        result = {"status": "UNKNOWN", "ownership_status": "UNKNOWN", "reason": "uninitialized",
            "original": {"bbox_xyxy": list(box), "box_index": box_index, "depth_options": asdict(self._depth),
                         "depth_stats": None, "depth_stats_status": "not_computed", "bbox_center_median_camera_m": None},
            "measurement": None, "evidence": {
                "scope": "DECLARED_CAR_FAMILY_GEOMETRIC_MEASUREMENT_ONLY_NOT_INSTANCE_IDENTITY",
                "input_depth_unchanged": True, "sampling": asdict(self._sampling),
                "ground_options": asdict(self._ground_options), "work_budget": asdict(self._budget)}}

        def unknown(reason):
            result["reason"] = reason
            return result

        height, width = self._image.shape
        left, top, right, bottom = _clip_roi(box, height, width, self._depth.roi_margin)
        count = max(0, right-left) * max(0, bottom-top)
        result["evidence"]["roi_bounds_integer"] = [left, top, right, bottom]
        if self._image.size > self._budget.max_image_pixels or count > self._budget.max_roi_pixels:
            result["original"]["depth_stats_status"] = "not_computed_work_budget"
            return unknown("image_or_roi_work_budget_exceeded")
        stats = depth_roi_stats(self._image, box, min_depth=self._depth.min_depth_m,
            max_depth=self._depth.max_depth_m, depth_scale=self._depth.depth_scale, margin=self._depth.roi_margin)
        result["original"]["depth_stats"] = asdict(stats)
        result["original"]["depth_stats_status"] = "computed_from_original_input"
        if stats.is_valid:
            result["original"]["bbox_center_median_camera_m"] = pinhole_backproject(
                ((box[0]+box[2])*.5, (box[1]+box[3])*.5), stats.median, self._camera).tolist()
        if self._boxes is None:
            return unknown("visible_boxes_work_budget_exceeded")
        if class_name != "car" or self._prior.class_name != "car":
            return unknown("unsupported_declared_geometry_family")
        edge = self._sampling.image_edge_margin_px
        if not (box[0] > edge and box[1] > edge and box[2] < width-edge and box[3] < height-edge):
            return unknown("bbox_outside_original_geometry_operating_envelope")
        if not stats.is_valid or stats.valid_fraction < self._depth.min_valid_fraction:
            return unknown("original_roi_depth_invalid_or_insufficient")
        self._prepare_ground()
        result["evidence"]["ground"] = deepcopy(self._ground_evidence)
        if not self._plane.valid:
            return unknown("independent_ground_invalid:" + self._plane.reason)
        if self._plane.offset <= .2:
            return unknown("camera_not_above_independent_ground")
        xyz = sample_depth_points(self._depth_m, self._camera, box,
            exclude_bboxes=[b for i, b in enumerate(self._boxes) if i != box_index],
            stride=self._sampling.exclusive_stride, max_points=self._sampling.exclusive_max_points,
            min_depth_m=self._depth.min_depth_m, max_depth_m=self._depth.max_depth_m)
        camera = self._camera
        exclusive = np.empty((0, 5)) if len(xyz) == 0 else np.column_stack((
            np.rint(xyz[:, 0]/xyz[:, 2]*camera.fx+camera.cx), np.rint(xyz[:, 1]/xyz[:, 2]*camera.fy+camera.cy), xyz))
        vv, uu = np.nonzero(self._valid[top:bottom, left:right])
        vv, uu = vv+top, uu+left
        z = self._depth_m[vv, uu]
        roi = np.column_stack((uu, vv, (uu-camera.cx)*z/camera.fx, (vv-camera.cy)*z/camera.fy, z))
        ex_groups, _ = _groups(exclusive, self._plane)
        roi_groups, roi_ids = _groups(roi, self._plane)
        result["evidence"].update(exclusive_sample_count=len(exclusive), exclusive_groups=ex_groups, roi_groups=roi_groups)
        supported_ex = [i for i, group in enumerate(ex_groups) if group["supported"]]
        if len(supported_ex) != 1:
            return unknown("exclusive_foreground_multiple_or_missing")
        model = fit_unique_visibility_model(xyz, ground_plane=self._plane,
            camera_position_world=(0., 0., 0.), camera_forward_world=(0., 0., 1.),
            prior=self._prior, correlated_two_face_bound=self._correlated)
        result["evidence"]["exclusive_geometry"] = {"valid": model.valid, "reason": model.reason, "diagnostics": model.diagnostics}
        if not model.valid:
            return unknown("exclusive_geometry_invalid:" + model.reason)
        ex = ex_groups[supported_ex[0]]
        candidates = []
        for i, group in enumerate(roi_groups):
            if group["supported"] and max(group["range_min_m"], ex["range_min_m"]) <= min(group["range_max_m"], ex["range_max_m"]):
                explained = _model_explains(roi[roi_ids[i], 2:], model, visible_only=False)
                candidates.append({"roi_group_index": i, "group_count": len(explained),
                    "body_compatible_count": int(explained.sum()), "all_body_compatible": bool(explained.all())})
        result["evidence"]["range_overlapping_roi_components"] = candidates
        if len(candidates) != 1:
            return unknown("roi_independent_component_multiple_or_missing")
        if not candidates[0]["all_body_compatible"]:
            return unknown("roi_component_not_fully_body_compatible")
        chosen = candidates[0]["roi_group_index"]
        points = roi[roi_ids[chosen], 2:]
        result.update(status="SUPPORTED_SURFACE_MEASUREMENT", ownership_status="INDEPENDENT_GEOMETRIC_SUPPORT_ONLY",
            reason="unique_exclusive_geometry_and_unique_compatible_measured_roi_component",
            measurement={"position_camera_m": component_centroid(points).tolist(),
                "measurement_kind": "DERIVED_POINT_SET_CENTROID", "reference_kind": "visible_surface_proxy_component_centroid",
                "is_actual_pixel_measurement": False, "roi_component_index": chosen,
                "exclusive_component_index": supported_ex[0], "component_support_count": len(points),
                "component_camera_std_m": np.std(points, axis=0).tolist(),
                "covariance_camera_m2": None, "covariance_status": "not_calibrated_by_this_module",
                "identity_status": "NOT_ASSESSED", "association_status": "NOT_RUN"})
        return result


def prepare_car_surface_frame(depth_image: Any, intrinsics: Any, visible_boxes: Sequence[Sequence[float]], *,
    depth_options: DepthOptions, prior: NavigationPrior, up_camera: Sequence[float], budget: WorkBudget,
    sampling: SamplingOptions = SamplingOptions(), ground_options: GroundOptions = GroundOptions(),
    correlated_two_face_bound: bool = True) -> CarSurfaceFrame:
    """Snapshot one aligned optical-Z frame; lazily share its ground fit.

    All detected classes belong in ``visible_boxes``. Call ``assess`` only for
    the intended car indices (or pass another class to receive UNKNOWN).
    Depth supports obey ``min < Z <= max`` in metres without changing input.
    Invalid configuration raises ValueError; resource excess yields UNKNOWN
    without ground/geometry work. TF, timestamps, R and raw fallback belong to
    the adapter, which must use this acquisition's up vector.
    """
    image = np.asarray(depth_image)
    if image.ndim != 2 or image.dtype.kind not in "fiu":
        raise ValueError("depth_image must be a numeric two-dimensional array")
    camera = CameraIntrinsics.from_value(intrinsics)
    _validate(depth_options, sampling, ground_options, budget)
    up = np.asarray(up_camera, dtype=float)
    if up.shape != (3,) or not np.isfinite(up).all() or np.linalg.norm(up) < 1e-9:
        raise ValueError("up_camera must be a finite nonzero three-vector")
    return CarSurfaceFrame(image, camera, visible_boxes, depth_options, prior, up, budget,
                           sampling, ground_options, correlated_two_face_bound)
