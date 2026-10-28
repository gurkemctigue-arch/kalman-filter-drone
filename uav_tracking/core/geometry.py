"""Image geometry and depth utilities used by the tracking core."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Optional, Sequence, Tuple

import numpy as np

from .models import BBox, DepthStats, normalize_bbox


@dataclass(frozen=True)
class CameraIntrinsics:
    """Pinhole camera parameters in pixel units."""

    fx: float
    fy: float
    cx: float
    cy: float

    def __post_init__(self) -> None:
        for name in ("fx", "fy", "cx", "cy"):
            value = float(getattr(self, name))
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, value)
        if self.fx <= 0.0 or self.fy <= 0.0:
            raise ValueError("fx and fy must be positive")

    @classmethod
    def from_value(cls, value: Any) -> "CameraIntrinsics":
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            try:
                return cls(value["fx"], value["fy"], value["cx"], value["cy"])
            except KeyError as exc:
                raise ValueError("intrinsics mapping needs fx, fy, cx and cy") from exc
        if all(hasattr(value, name) for name in ("fx", "fy", "cx", "cy")):
            return cls(value.fx, value.fy, value.cx, value.cy)
        if isinstance(value, Sequence) and len(value) == 4:
            return cls(*value)
        array = np.asarray(value, dtype=float)
        if array.shape == (4,):
            return cls(*array.tolist())
        if array.shape == (3, 3):
            return cls(array[0, 0], array[1, 1], array[0, 2], array[1, 2])
        raise ValueError("intrinsics must be CameraIntrinsics, mapping, (fx,fy,cx,cy), or a 3x3 matrix")


def bbox_iou(box_a: Sequence[float], box_b: Sequence[float]) -> float:
    """Compute intersection-over-union for two ``xyxy`` boxes."""

    a = normalize_bbox(box_a)
    b = normalize_bbox(box_b)
    inter_x1 = max(a[0], b[0])
    inter_y1 = max(a[1], b[1])
    inter_x2 = min(a[2], b[2])
    inter_y2 = min(a[3], b[3])
    inter = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return 0.0 if union <= 0.0 else float(inter / union)


def _clip_roi(bbox: Sequence[float], height: int, width: int, margin: float = 0.0) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = normalize_bbox(bbox)
    if not 0.0 <= margin < 0.5:
        raise ValueError("margin must be in [0, 0.5)")
    dx = (x2 - x1) * margin
    dy = (y2 - y1) * margin
    left = max(0, min(width, int(np.ceil(x1 + dx))))
    top = max(0, min(height, int(np.ceil(y1 + dy))))
    right = max(0, min(width, int(np.floor(x2 - dx))))
    bottom = max(0, min(height, int(np.floor(y2 - dy))))
    return left, top, right, bottom


def depth_roi_stats(
    depth_image: Any,
    bbox: Optional[Sequence[float]] = None,
    *,
    min_depth: float = 1e-6,
    max_depth: Optional[float] = None,
    depth_scale: float = 1.0,
    margin: float = 0.0,
) -> DepthStats:
    """Summarize finite, positive depth values inside an image ROI.

    ``depth_scale`` converts raw values to the returned unit (for example,
    ``0.001`` for a millimetre image returning metres).  Coordinates are
    clipped to the image; an empty/degenerate ROI returns zero valid values.
    """

    image = np.asarray(depth_image)
    if image.ndim != 2:
        raise ValueError("depth_image must be a two-dimensional array")
    depth_scale = float(depth_scale)
    if not isfinite(depth_scale) or depth_scale <= 0.0:
        raise ValueError("depth_scale must be a positive finite number")
    min_depth = float(min_depth)
    if min_depth < 0.0 or not isfinite(min_depth):
        raise ValueError("min_depth must be finite and non-negative")
    if max_depth is not None:
        max_depth = float(max_depth)
        if not isfinite(max_depth) or max_depth <= min_depth:
            raise ValueError("max_depth must be greater than min_depth")

    height, width = image.shape
    if bbox is None:
        left, top, right, bottom = 0, 0, width, height
    else:
        left, top, right, bottom = _clip_roi(bbox, height, width, margin)
    total = max(0, right - left) * max(0, bottom - top)
    if total == 0:
        return DepthStats(0, 0, 0.0, scale=depth_scale)
    values = np.asarray(image[top:bottom, left:right], dtype=float).reshape(-1) * depth_scale
    valid = np.isfinite(values) & (values > min_depth)
    if max_depth is not None:
        valid &= values <= max_depth
    values = values[valid]
    count = int(values.size)
    if count == 0:
        return DepthStats(0, total, 0.0, scale=depth_scale)
    return DepthStats(
        valid_count=count,
        total_count=total,
        valid_fraction=float(count / total),
        mean=float(np.mean(values)),
        median=float(np.median(values)),
        std=float(np.std(values)),
        minimum=float(np.min(values)),
        maximum=float(np.max(values)),
        scale=depth_scale,
    )


def depth_roi_statistics(*args: Any, **kwargs: Any) -> DepthStats:
    """Alias with a verbose name for application code."""

    return depth_roi_stats(*args, **kwargs)


def pinhole_backproject(
    pixel: Sequence[float] | float | None = None,
    depth: float | None = None,
    intrinsics: CameraIntrinsics | Mapping[str, float] | Sequence[float] | Any = None,
    *legacy_args: Any,
    **keyword_args: Any,
) -> np.ndarray:
    """Back-project a pixel to camera-frame ``(x, y, z)``.

    The preferred call is ``pinhole_backproject((u, v), z, intrinsics)``.
    For small integrations, the common positional forms
    ``(u, v, z, intrinsics)`` and ``(u, v, z, fx, fy, cx, cy)`` are accepted
    as well.
    """

    if keyword_args:
        # Keyword form: pinhole_backproject(u=..., v=..., depth=...,
        # fx=..., fy=..., cx=..., cy=...).
        if pixel is not None or legacy_args:
            raise TypeError("do not mix keyword u/v form with positional pixel arguments")
        if "u" not in keyword_args or "v" not in keyword_args or depth is None:
            raise TypeError("keyword form needs u, v and depth")
        pixel = (keyword_args.pop("u"), keyword_args.pop("v"))
        if intrinsics is not None:
            raise TypeError("intrinsics cannot be combined with fx/fy/cx/cy keywords")
        required = ("fx", "fy", "cx", "cy")
        if any(name not in keyword_args for name in required):
            raise TypeError("keyword form needs fx, fy, cx and cy")
        intrinsics = tuple(keyword_args.pop(name) for name in required)
        if keyword_args:
            raise TypeError(f"unexpected keyword arguments: {', '.join(keyword_args)}")
    if pixel is None or depth is None or intrinsics is None:
        raise TypeError("pixel, depth and intrinsics are required")
    if np.isscalar(pixel):
        # In the four-argument form, the third positional argument currently
        # held in ``intrinsics`` is the depth and the first legacy argument is
        # the actual intrinsics object.
        if len(legacy_args) == 1:
            u, v, z, actual_intrinsics = float(pixel), float(depth), float(intrinsics), legacy_args[0]
        elif len(legacy_args) == 4:
            u, v, z = float(pixel), float(depth), float(intrinsics)
            actual_intrinsics = legacy_args
        else:
            raise TypeError("scalar form needs (u, v, depth, intrinsics) or (u, v, depth, fx, fy, cx, cy)")
    else:
        if legacy_args:
            raise TypeError("legacy positional arguments are only valid with scalar u")
        if len(pixel) != 2:
            raise ValueError("pixel must contain u and v")
        u, v = (float(value) for value in pixel)
        z = float(depth)
        actual_intrinsics = intrinsics
    if not all(isfinite(value) for value in (u, v, z)) or z <= 0.0:
        raise ValueError("pixel and depth must be finite, with depth > 0")
    camera = CameraIntrinsics.from_value(actual_intrinsics)
    return np.asarray([(u - camera.cx) * z / camera.fx, (v - camera.cy) * z / camera.fy, z], dtype=float)


def backproject_pixel(*args: Any, **kwargs: Any) -> np.ndarray:
    """Compatibility alias for :func:`pinhole_backproject`."""

    return pinhole_backproject(*args, **kwargs)


def pixel_to_camera(*args: Any, **kwargs: Any) -> np.ndarray:
    """Descriptive alias for :func:`pinhole_backproject`."""

    return pinhole_backproject(*args, **kwargs)


def backproject(*args: Any, **kwargs: Any) -> np.ndarray:
    """Short alias for :func:`pinhole_backproject`."""

    return pinhole_backproject(*args, **kwargs)


def valid_depth_stats(*args: Any, **kwargs: Any) -> DepthStats:
    """Short alias for :func:`depth_roi_stats`."""

    return depth_roi_stats(*args, **kwargs)


def backproject_bbox_center(
    bbox: Sequence[float],
    depth: float,
    intrinsics: CameraIntrinsics | Mapping[str, float] | Sequence[float] | Any,
) -> np.ndarray:
    box = normalize_bbox(bbox)
    return pinhole_backproject(((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0), depth, intrinsics)

