"""RGB-D ground and footprint references, independent of surface tracking.

Inputs are measured depth, calibrated camera geometry, and declared object-size
priors. No simulator identity, mesh, or evaluation anchor is used. Upright car
end/side faces require a unique geometric interpretation; an unobservable
center is invalid rather than a guessed navigation command.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Sequence

import numpy as np

from .geometry import CameraIntrinsics


def _vector(value: Any, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.shape != (3,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite three-vector")
    return result.copy()


def _points(value: Any) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.size == 0:
        return np.empty((0, 3), dtype=float)
    if result.ndim != 2 or result.shape[1] != 3:
        raise ValueError("points must have shape (N, 3)")
    return result[np.all(np.isfinite(result), axis=1)].copy()


@dataclass(frozen=True)
class GroundPlane:
    """Plane ``normal @ p + offset = 0``; normal points towards declared up.

    Covariance is for ``[nx, ny, nz, offset]``.  This approximate local fit
    covariance does not include camera-pose uncertainty; the transport adapter
    must add that uncertainty before using the reference for control.
    """

    normal: np.ndarray | None = None
    offset: float = 0.0
    covariance: np.ndarray | None = None
    valid: bool = False
    reason: str = "uninitialized"
    inlier_count: int = 0
    sample_count: int = 0
    residual_std_m: float = 0.0

    def __post_init__(self) -> None:
        if not self.valid:
            return
        normal = _vector(self.normal, "normal")
        norm = float(np.linalg.norm(normal))
        if norm <= 1e-9 or not math.isfinite(float(self.offset)):
            raise ValueError("valid ground plane needs a nonzero normal and finite offset")
        covariance = np.eye(4) * 1e-4 if self.covariance is None else np.asarray(self.covariance, dtype=float)
        if covariance.shape != (4, 4) or not np.all(np.isfinite(covariance)):
            raise ValueError("ground covariance must be a finite 4x4 matrix")
        object.__setattr__(self, "normal", normal / norm)
        object.__setattr__(self, "offset", float(self.offset) / norm)
        object.__setattr__(self, "covariance", covariance.copy() / norm**2)


@dataclass(frozen=True)
class NavigationPrior:
    """Declared dimensions of an upright object family, never inferred from GT.

    Length is along travel/body heading; width is lateral. Dimension standard
    deviations default to 10% of each dimension and remain in center covariance.
    A family prior is an assumption, not a promise of arbitrary-vehicle support.
    """

    class_name: str
    length_m: float
    width_m: float
    height_m: float
    dimension_std_m: Sequence[float] | None = None
    min_heading_speed_mps: float = 0.15
    max_end_view_angle_deg: float = 35.0
    heading_std_rad: float = 0.12
    prior_id: str = "declared_object_family"

    def __post_init__(self) -> None:
        if self.class_name not in {"person", "car"}:
            raise ValueError("navigation prior supports person or car")
        dimensions = np.asarray([self.length_m, self.width_m, self.height_m], dtype=float)
        if not np.all(np.isfinite(dimensions)) or np.any(dimensions <= 0):
            raise ValueError("object dimensions must be finite and positive")
        uncertainty = dimensions * 0.1 if self.dimension_std_m is None else _vector(self.dimension_std_m, "dimension_std_m")
        if np.any(uncertainty < 0):
            raise ValueError("dimension uncertainty must be nonnegative")
        if not math.isfinite(self.min_heading_speed_mps) or self.min_heading_speed_mps < 0:
            raise ValueError("minimum heading speed must be finite and nonnegative")
        if not 0 < self.max_end_view_angle_deg < 90 or not math.isfinite(self.heading_std_rad) or self.heading_std_rad < 0:
            raise ValueError("invalid heading/view uncertainty")
        object.__setattr__(self, "dimension_std_m", tuple(float(v) for v in uncertainty))


@dataclass(frozen=True)
class NavigationEstimate:
    position_world_m: np.ndarray | None = None
    covariance: np.ndarray | None = None
    valid: bool = False
    reason: str = "uninitialized"
    reference_kind: str = "ground_footprint_center"
    support_count: int = 0
    heading_source: str = "none"
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def footprint_center_world_m(self) -> np.ndarray | None:
        return self.position_world_m


def sample_depth_points(
    depth_image: Any,
    intrinsics: Any,
    bbox: Sequence[float] | None = None,
    exclude_bboxes: Sequence[Sequence[float]] = (),
    *,
    stride: int = 1,
    depth_scale: float = 1.0,
    max_points: int = 800,
    min_depth_m: float = 0.1,
    max_depth_m: float = 50.0,
) -> np.ndarray:
    """Deterministically sample finite aligned depth as camera optical Nx3.

    ``bbox`` keeps its inward-rounded sampling bounds. Positive-area exclusion
    boxes remove every touched [u,u+1)x[v,v+1) pixel cell (floor low, ceil high,
    clipped to the image), before the final evenly spaced cap. Degenerate
    exclusions remove nothing. A zero/invalid ROI yields an empty cloud.
    This function has no frame transform or TF read.
    """

    image = np.asarray(depth_image)
    if image.ndim != 2:
        raise ValueError("depth image must be two-dimensional")
    camera = CameraIntrinsics.from_value(intrinsics)
    if stride < 1 or int(stride) != stride or max_points < 1 or int(max_points) != max_points:
        raise ValueError("stride and max_points must be positive integers")
    if not math.isfinite(depth_scale) or depth_scale <= 0 or not 0 <= min_depth_m < max_depth_m or not math.isfinite(max_depth_m):
        raise ValueError("invalid depth scale/range")
    height, width = image.shape
    box = np.asarray([0, 0, width, height] if bbox is None else bbox, dtype=float)
    if box.shape != (4,) or not np.all(np.isfinite(box)):
        raise ValueError("bbox must contain four finite xyxy values")
    left, top = max(0, int(math.ceil(box[0]))), max(0, int(math.ceil(box[1])))
    right, bottom = min(width, int(math.floor(box[2]))), min(height, int(math.floor(box[3])))
    if left >= right or top >= bottom:
        return np.empty((0, 3), dtype=float)
    # A regular grid avoids a large temporary full-resolution point cloud.
    grid_stride = max(int(stride), int(math.ceil(math.sqrt((right-left)*(bottom-top)/(max_points*4)))))
    u, v = np.meshgrid(np.arange(left, right, grid_stride), np.arange(top, bottom, grid_stride))
    u, v = u.reshape(-1), v.reshape(-1)
    z = image[v, u].astype(float) * depth_scale
    keep = np.isfinite(z) & (z >= min_depth_m) & (z <= max_depth_m) & (z > 0)
    for exclusion in exclude_bboxes:
        exclusion = np.asarray(exclusion, dtype=float)
        if exclusion.shape != (4,) or not np.all(np.isfinite(exclusion)):
            raise ValueError("exclude_bboxes must contain finite xyxy boxes")
        if exclusion[2] <= exclusion[0] or exclusion[3] <= exclusion[1]:
            continue
        exclude_left = max(0, min(width, math.floor(exclusion[0])))
        exclude_top = max(0, min(height, math.floor(exclusion[1])))
        exclude_right = max(0, min(width, math.ceil(exclusion[2])))
        exclude_bottom = max(0, min(height, math.ceil(exclusion[3])))
        keep &= ~((u >= exclude_left) & (u < exclude_right) & (v >= exclude_top) & (v < exclude_bottom))
    u, v, z = u[keep], v[keep], z[keep]
    if len(z) > max_points:
        indices = np.linspace(0, len(z)-1, int(max_points), dtype=int)
        u, v, z = u[indices], v[indices], z[indices]
    return np.column_stack(((u-camera.cx)*z/camera.fx, (v-camera.cy)*z/camera.fy, z))


def fit_ground_plane(
    points_world: Any,
    *,
    up_world: Any = (0.0, 0.0, 1.0),
    min_support: int = 40,
    min_inlier_ratio: float = 0.25,
    distance_threshold_m: float = 0.05,
    max_tilt_deg: float = 25.0,
    iterations: int = 80,
    random_seed: int = 0,
) -> GroundPlane:
    """Fit a sufficiently supported, near-up plane using bounded RANSAC.

    Callers must exclude every detected object box from these ground samples.
    Geometry alone cannot distinguish an entire level roof from ground. Ground
    support near the target and a physically plausible camera height must also
    be checked by the adapter for its declared operating environment.
    """

    points = _points(points_world)
    if min_support < 3 or not 0 < min_inlier_ratio <= 1 or distance_threshold_m <= 0 or not 0 <= max_tilt_deg < 90 or iterations < 1:
        raise ValueError("invalid ground fit configuration")
    up = _vector(up_world, "up_world")
    up_norm = float(np.linalg.norm(up))
    if up_norm < 1e-9:
        raise ValueError("up_world must be nonzero")
    up /= up_norm
    if len(points) < min_support:
        return GroundPlane(reason="insufficient_ground_samples", sample_count=len(points))
    required = max(min_support, int(math.ceil(len(points)*min_inlier_ratio)))
    cosine = math.cos(math.radians(max_tilt_deg))
    rng = np.random.default_rng(random_seed)
    best: np.ndarray | None = None
    best_count = 0
    for _ in range(iterations):
        a, b, c = points[rng.choice(len(points), 3, replace=False)]
        normal = np.cross(b-a, c-a)
        norm = float(np.linalg.norm(normal))
        if norm < 1e-9:
            continue
        normal /= norm
        if abs(float(normal @ up)) < cosine:
            continue
        mask = np.abs((points-a) @ normal) <= distance_threshold_m
        count = int(mask.sum())
        if count > best_count:
            best, best_count = mask, count
    if best is None or best_count < required:
        return GroundPlane(reason="ground_support_or_orientation_rejected", sample_count=len(points), inlier_count=best_count)
    fitted = points[best]
    center = np.mean(fitted, axis=0)
    _, singular, directions = np.linalg.svd(fitted-center, full_matrices=False)
    if singular[1] / math.sqrt(len(fitted)) < 0.1:
        return GroundPlane(reason="ground_support_degenerate", sample_count=len(points), inlier_count=best_count)
    normal = directions[-1]
    if normal @ up < 0:
        normal = -normal
    if normal @ up < cosine:
        return GroundPlane(reason="ground_tilt_rejected", sample_count=len(points), inlier_count=best_count)
    offset = -float(normal @ center)
    mask = np.abs(points @ normal + offset) <= distance_threshold_m
    if int(mask.sum()) < required:
        return GroundPlane(reason="refined_ground_support_rejected", sample_count=len(points), inlier_count=int(mask.sum()))
    residual = points[mask] @ normal + offset
    sigma = max(0.002, float(np.sqrt(np.mean(residual**2))))
    span = max(0.1, float(singular[1]/math.sqrt(len(fitted))))
    covariance = np.diag([sigma**2/(len(fitted)*span**2)]*3 + [sigma**2/len(fitted)])
    return GroundPlane(normal, offset, covariance, True, "ground_fit", int(mask.sum()), len(points), sigma)


def _transform(points: np.ndarray, world_from_camera: Any) -> np.ndarray:
    transform = np.asarray(world_from_camera, dtype=float)
    if transform.shape != (4, 4) or not np.all(np.isfinite(transform)) or not np.allclose(transform[3], [0, 0, 0, 1]):
        raise ValueError("world_from_camera must be a finite rigid 4x4 transform")
    rotation = transform[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5) or np.linalg.det(rotation) < 0.999:
        raise ValueError("camera rotation must be proper and orthonormal")
    return points @ rotation.T + transform[:3, 3]


def estimate_ground_plane(depth_image: Any, intrinsics: Any, excluded_bboxes: Sequence[Sequence[float]], *, world_from_camera: Any, **fit_options: Any) -> GroundPlane:
    """Convenience image wrapper; sparse adapters can call fit_ground_plane."""

    points = sample_depth_points(depth_image, intrinsics, exclude_bboxes=excluded_bboxes)
    return fit_ground_plane(_transform(points, world_from_camera), **fit_options)


def _ground_project(points: np.ndarray, plane: GroundPlane) -> np.ndarray:
    return points - (points @ plane.normal + plane.offset)[..., None] * plane.normal


def _covariance(plane: GroundPlane, center: np.ndarray, along: np.ndarray, sigma_along: float, sigma_lateral: float) -> np.ndarray:
    lateral = np.cross(plane.normal, along)
    local_plane_variance = float(np.r_[center, 1.0] @ plane.covariance @ np.r_[center, 1.0])
    sigma_z2 = max(0.02**2, plane.residual_std_m**2, local_plane_variance)
    return (sigma_along**2*np.outer(along, along) + sigma_lateral**2*np.outer(lateral, lateral)
            + sigma_z2*np.outer(plane.normal, plane.normal))


def _person_reference(points: np.ndarray, plane: GroundPlane, camera: np.ndarray, prior: NavigationPrior, ray: Any) -> NavigationEstimate:
    if ray is None:
        return NavigationEstimate(reason="person_bottom_ray_missing", support_count=len(points))
    direction = _vector(ray, "bottom_ray_world")
    norm = float(np.linalg.norm(direction))
    if norm < 1e-9:
        return NavigationEstimate(reason="bottom_ray_invalid", support_count=len(points))
    direction /= norm
    denominator = float(plane.normal @ direction)
    camera_height = float(plane.normal @ camera + plane.offset)
    if camera_height <= 0.2 or denominator >= -0.05:
        return NavigationEstimate(reason="ground_intersection_unobservable", support_count=len(points))
    distance = -camera_height / denominator
    if distance <= 0 or distance > 50:
        return NavigationEstimate(reason="ground_intersection_out_of_range", support_count=len(points))
    center = camera + distance*direction
    body_ground = _ground_project(np.median(points, axis=0), plane)
    disagreement = float(np.linalg.norm(center-body_ground))
    if disagreement > max(prior.length_m, prior.width_m)*0.75 + 0.35:
        return NavigationEstimate(reason="foot_body_geometry_inconsistent", support_count=len(points), diagnostics={"foot_body_disagreement_m": disagreement})
    along = _ground_project(center+direction, plane)-center
    along /= max(float(np.linalg.norm(along)), 1e-9)
    sigma = 0.025 + 0.02*distance + max(prior.dimension_std_m[:2])*0.5
    covariance = _covariance(plane, center, along, sigma, sigma)
    return NavigationEstimate(center, covariance, True, "person_ground_contact", "person_ground_contact", len(points), "not_required",
                              {"prior_id": prior.prior_id, "foot_body_disagreement_m": disagreement, "intersection_range_m": distance})


def _vertical_face(points: np.ndarray, normal_up: np.ndarray, camera: np.ndarray, threshold: float, min_support: int) -> tuple[np.ndarray, np.ndarray] | None:
    """Find a vertical visible face without presupposing travel direction."""

    rng = np.random.default_rng(0)
    best = None
    best_count = 0
    for _ in range(64):
        a, b = points[rng.choice(len(points), 2, replace=False)]
        normal = np.cross(b-a, normal_up)
        norm = float(np.linalg.norm(normal))
        if norm < 1e-6:
            continue
        normal /= norm
        mask = np.abs((points-a) @ normal) <= threshold
        count = int(mask.sum())
        if count > best_count:
            best, best_count = mask, count
    if best is None or best_count < max(min_support, int(math.ceil(len(points)*0.25))):
        return None
    face = points[best]
    # Fit the horizontal trace; vertical spread must not tilt its normal.
    helper = np.array([1.0, 0.0, 0.0]) if abs(normal_up[0]) < 0.8 else np.array([0.0, 1.0, 0.0])
    a = np.cross(normal_up, helper); a /= np.linalg.norm(a)
    b = np.cross(normal_up, a)
    xy = np.column_stack((face @ a, face @ b))
    _, _, vh = np.linalg.svd(xy-np.mean(xy, axis=0), full_matrices=False)
    normal = vh[-1, 0]*a + vh[-1, 1]*b
    if normal @ (camera-np.median(face, axis=0)) < 0:
        normal = -normal
    mask = np.abs((points-np.median(face, axis=0)) @ normal) <= threshold
    return normal, points[mask]


def _car_reference(points: np.ndarray, plane: GroundPlane, camera: np.ndarray, prior: NavigationPrior, velocity: Any, heading: Any, min_support: int) -> NavigationEstimate:
    n = plane.normal
    fitted = _vertical_face(points, n, camera, .10, min_support)
    if fitted is None:
        return NavigationEstimate(reason="car_visible_face_unobservable", support_count=len(points))
    faces = [fitted]
    normal, first = fitted
    remaining = points[np.abs((points - np.median(first, axis=0)) @ normal) > .16]
    if len(remaining) >= max(min_support, int(math.ceil(.15 * len(points)))):
        second = _vertical_face(remaining, n, camera, .10, min_support)
        if second is not None and len(second[1]) >= max(min_support, int(math.ceil(.15 * len(points)))):
            # Two well-supported planes must be adjacent cuboid faces.
            # Nearby parallel layers are not a second independent face.
            dot = abs(float(normal @ second[0]))
            if dot <= math.sin(math.radians(15.)):
                faces.append(second)
            elif dot < math.cos(math.radians(15.)):
                return NavigationEstimate(reason="car_visible_faces_not_orthogonal", support_count=len(points))

    summaries = []
    for outward, face in faces:
        tangent = np.cross(n, outward)
        lo, hi = np.quantile(face @ tangent, [.05, .95])
        heights = face @ n + plane.offset
        height_span = float(np.quantile(heights, .95) - np.quantile(heights, .05))
        point = np.median(face, axis=0)
        view = camera - point; view -= n * (view @ n)
        incidence = float(outward @ view) / max(float(np.linalg.norm(view)), 1e-9)
        if incidence < .15:
            continue  # A grazing surface cannot determine a normal offset.
        if (len(face) < max(min_support, int(math.ceil(.15 * len(points))))
                or not .25 * prior.height_m <= height_span <= 1.35 * prior.height_m):
            return NavigationEstimate(reason="car_visible_face_support_insufficient", support_count=len(face))
        point += tangent * ((lo + hi) * .5 - point @ tangent)
        summaries.append({"normal":outward, "face":face, "point":point, "span":float(hi - lo),
                          "height_span":height_span, "sigma":max(.04, float(np.std(face @ outward)))})
    if not summaries:
        return NavigationEstimate(reason="car_face_grazing_view", support_count=len(points))

    def dimensions(label):
        # Return normal dimension/std, tangential dimension/std.
        if label == "end":
            return prior.length_m, prior.dimension_std_m[0], prior.width_m, prior.dimension_std_m[1]
        return prior.width_m, prior.dimension_std_m[1], prior.length_m, prior.dimension_std_m[0]

    assignments = [("end",), ("side",)] if len(summaries) == 1 else [("end", "side"), ("side", "end")]
    candidates = []
    for labels in assignments:
        # A single plane needs most of its full tangential span. With two
        # independent planes shorter spans can establish a unique assignment;
        # when both assignments survive, no heading selects a convenient one.
        ratio = .65 if len(summaries) == 1 else .40
        if any(not ratio * dimensions(label)[2] <= face["span"] <= 1.25 * dimensions(label)[2]
               for face, label in zip(summaries, labels)):
            continue
        if len(summaries) == 1:
            face = summaries[0]; dimension, std, tangent_dimension, tangent_std = dimensions(labels[0])
            center = _ground_project(face["point"], plane) - face["normal"] * dimension * .5
            covariance = _covariance(plane, center, face["normal"], math.hypot(face["sigma"], std * .5),
                                     math.sqrt(.05**2 + (tangent_std * .5)**2 + (dimension * .5 * prior.heading_std_rad)**2))
            length_axis = face["normal"] if labels[0] == "end" else np.cross(n, face["normal"])
        else:
            matrix = np.vstack([summaries[0]["normal"], summaries[1]["normal"], n])
            if abs(float(np.linalg.det(matrix))) < .8:
                continue
            rhs = [face["normal"] @ face["point"] - dimensions(label)[0] * .5
                   for face, label in zip(summaries, labels)] + [-plane.offset]
            center = np.linalg.solve(matrix, rhs)
            inverse = np.linalg.inv(matrix)
            plane_variance = max(.02**2, plane.residual_std_m**2,
                                 float(np.r_[center, 1.] @ plane.covariance @ np.r_[center, 1.]))
            variances = [face["sigma"]**2 + (dimensions(label)[1] * .5)**2
                         for face, label in zip(summaries, labels)] + [plane_variance]
            covariance = inverse @ np.diag(variances) @ inverse.T
            corner = np.linalg.solve(matrix, [face["normal"] @ face["point"] for face in summaries] + [-plane.offset])
            angular_lever = np.cross(n, center - corner)
            covariance += prior.heading_std_rad**2 * np.outer(angular_lever, angular_lever)
            length_axis = summaries[labels.index("end")]["normal"]
        # Every accepted interpretation must contain the observed body. This
        # rejects a side/end size mismatch or a contradictory second cluster;
        # it never infers dimensions from a simulator or a target trajectory.
        lateral_axis = np.cross(n, length_axis)
        relative = points - center
        inside = ((np.abs(relative @ length_axis) <= prior.length_m * .5 + .15)
                  & (np.abs(relative @ lateral_axis) <= prior.width_m * .5 + .15))
        if float(np.mean(inside)) < .85:
            continue
        candidates.append((labels, center, covariance, length_axis))
    if not candidates:
        return NavigationEstimate(reason="car_visible_face_shape_inconsistent", support_count=len(points),
                                  diagnostics={"visible_face_spans_m":[face["span"] for face in summaries]})
    if len(candidates) != 1:
        return NavigationEstimate(reason="car_static_end_side_ambiguous", support_count=len(points),
                                  diagnostics={"geometric_hypotheses":[list(candidate[0]) for candidate in candidates]})
    labels, center, covariance, length_axis = candidates[0]
    heading_source = "visible_face_shape_prior" if len(labels) == 1 else "two_visible_faces_shape_prior"
    direction = None; motion_source = None
    if heading is not None:
        direction = np.array([math.cos(float(heading)), math.sin(float(heading)), 0.]) if np.isscalar(heading) else _vector(heading, "heading_world")
        motion_source = "declared_heading"
    elif velocity is not None:
        v = _vector(velocity, "velocity_world"); v -= n * (v @ n)
        if np.linalg.norm(v) >= prior.min_heading_speed_mps:
            direction, motion_source = v, "track_velocity"
    agreement = None
    if direction is not None:
        direction -= n * (direction @ n)
        if np.linalg.norm(direction) > 1e-6:
            agreement = abs(float(direction @ length_axis)) / float(np.linalg.norm(direction))
            if agreement >= math.cos(math.radians(prior.max_end_view_angle_deg)):
                heading_source = motion_source
    reason = "car_upright_two_face_prior" if len(labels) == 2 else "car_upright_" + labels[0] + "_face_prior"
    return NavigationEstimate(center, (covariance + covariance.T) * .5, True, reason, "car_cuboid_ground_center",
                              sum(len(face["face"]) for face in summaries), heading_source,
                              {"prior_id":prior.prior_id, "face_labels":list(labels),
                               "visible_face_spans_m":[face["span"] for face in summaries],
                               "visible_face_height_spans_m":[face["height_span"] for face in summaries],
                               "length_prior_m":prior.length_m, "width_prior_m":prior.width_m,
                               "motion_heading_source":motion_source, "motion_geometry_alignment_cosine":agreement,
                               "visible_face_normals_world":[face["normal"].tolist() for face in summaries],
                               "visible_face_points_world":[face["point"].tolist() for face in summaries],
                               "visible_face_sigma_m":[face["sigma"] for face in summaries],
                               "body_length_axis_world":length_axis.tolist(),
                               "body_lateral_axis_world":np.cross(n, length_axis).tolist(),
                               "observability":"upright supported end/side face(s), unique dimension assignment; dimensions are declared priors"})


def estimate_footprint_from_points(
    points_world: Any,
    *,
    ground_plane: GroundPlane,
    camera_position_world: Any,
    prior: NavigationPrior,
    bottom_ray_world: Any = None,
    velocity_world: Any = None,
    heading_world: Any = None,
    min_support: int = 12,
) -> NavigationEstimate:
    """Return a measured ground footprint point or an explicit invalid reason.

    ``bottom_ray_world`` is a direction originating at camera_position_world,
    required for person feet. ``heading_world`` is a yaw radians scalar or a
    three-vector; absent heading uses reliable horizontal track velocity as a
    diagnostic. Car references require a uniquely compatible end/side shape
    hypothesis; motion heading cannot choose between ambiguous geometries.
    Source timestamps, identity, and age limits remain the caller's contract.
    """

    if not isinstance(prior, NavigationPrior) or not isinstance(ground_plane, GroundPlane):
        raise TypeError("ground_plane and prior must use the declared core types")
    if min_support < 3:
        raise ValueError("min_support must be at least three")
    if not ground_plane.valid:
        return NavigationEstimate(reason="ground_invalid:"+ground_plane.reason)
    camera = _vector(camera_position_world, "camera_position_world")
    camera_height = float(ground_plane.normal @ camera + ground_plane.offset)
    if camera_height <= 0.2:
        return NavigationEstimate(reason="camera_not_above_ground")
    points = _points(points_world)
    heights = points @ ground_plane.normal + ground_plane.offset
    points = points[(heights > 0.08) & (heights < prior.height_m*1.4+0.15)]
    if len(points) < min_support:
        return NavigationEstimate(reason="foreground_support_insufficient", support_count=len(points))
    # A separate depth cluster behind a valid nearer object is not its body.
    ranges = np.linalg.norm(points-camera, axis=1)
    order = np.argsort(ranges)
    groups = np.split(order, np.flatnonzero(np.diff(ranges[order]) > 0.45)+1)
    supported = [group for group in groups if len(group) >= max(min_support, int(math.ceil(len(points)*0.15)))]
    if not supported:
        return NavigationEstimate(reason="foreground_depth_cluster_missing", support_count=len(points))
    points = points[supported[0]]
    if prior.class_name == "person":
        return _person_reference(points, ground_plane, camera, prior, bottom_ray_world)
    return _car_reference(points, ground_plane, camera, prior, velocity_world, heading_world, min_support)


def estimate_navigation_reference(
    depth_image: Any,
    intrinsics: Any,
    bbox: Sequence[float],
    *,
    prior: NavigationPrior,
    ground_plane: GroundPlane,
    world_from_camera: Any,
    velocity_world: Any = None,
    heading_world: Any = None,
    depth_scale: float = 1.0,
) -> NavigationEstimate:
    """Image convenience wrapper; no partial/clipped target box is accepted."""

    image = np.asarray(depth_image)
    if image.ndim != 2:
        raise ValueError("depth image must be two-dimensional")
    box = np.asarray(bbox, dtype=float)
    if box.shape != (4,) or not np.all(np.isfinite(box)):
        raise ValueError("bbox must contain four finite values")
    height, width = image.shape
    if box[0] <= 0 or box[1] <= 0 or box[2] >= width-1 or box[3] >= height-1:
        return NavigationEstimate(reason="target_box_truncated")
    points = sample_depth_points(image, intrinsics, box, max_points=400, depth_scale=depth_scale)
    transform = np.asarray(world_from_camera, dtype=float)
    world_points = _transform(points, transform)
    camera = CameraIntrinsics.from_value(intrinsics)
    ray = transform[:3, :3] @ np.array([((box[0]+box[2])*0.5-camera.cx)/camera.fx, (box[3]-camera.cy)/camera.fy, 1.0])
    return estimate_footprint_from_points(world_points, ground_plane=ground_plane, camera_position_world=transform[:3, 3],
                                          prior=prior, bottom_ray_world=ray, velocity_world=velocity_world, heading_world=heading_world)


__all__ = ["GroundPlane", "NavigationPrior", "NavigationEstimate", "sample_depth_points", "fit_ground_plane",
           "estimate_ground_plane", "estimate_footprint_from_points", "estimate_navigation_reference"]
