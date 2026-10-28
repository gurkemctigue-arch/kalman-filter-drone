"""Small, middleware-independent data models for visual tracking.

The models deliberately contain plain Python values at their public boundary.
NumPy arrays are accepted as input, but are copied into tuples where a stable
serializable value is useful.  ROS messages and simulator entities should be
adapted to these classes at the application boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import Any, Hashable, Mapping, Optional, Sequence, Tuple


BBox = Tuple[float, float, float, float]
Vector3 = Tuple[float, float, float]


def _finite_float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def normalize_bbox(value: Sequence[float]) -> BBox:
    """Return an ``xyxy`` bounding box with finite, ordered coordinates."""

    if len(value) != 4:
        raise ValueError("bbox must contain four values in x1, y1, x2, y2 order")
    x1, y1, x2, y2 = (_finite_float(item, "bbox coordinate") for item in value)
    if x2 < x1 or y2 < y1:
        raise ValueError("bbox coordinates must satisfy x2 >= x1 and y2 >= y1")
    return (x1, y1, x2, y2)


def normalize_vector3(value: Sequence[float], name: str = "vector") -> Vector3:
    if len(value) != 3:
        raise ValueError(f"{name} must contain three values")
    result = tuple(_finite_float(item, name) for item in value)
    return result  # type: ignore[return-value]


class TrackState(str, Enum):
    """Lifecycle state of a track."""

    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    COASTING = "coasting"
    LOST = "lost"
    REMOVED = "removed"

    @classmethod
    def _missing_(cls, value: object) -> "TrackState | None":
        if isinstance(value, str):
            normalized = value.strip().lower()
            for member in cls:
                if member.value == normalized or member.name.lower() == normalized:
                    return member
        return None


class TargetMode(str, Enum):
    """Target selection policy used by :class:`TargetManager`."""

    AUTO_UNIQUE = "auto_unique"
    LOCKED_TARGET = "locked_target"

    @classmethod
    def _missing_(cls, value: object) -> "TargetMode | None":
        if isinstance(value, str):
            normalized = value.strip().lower()
            for member in cls:
                if member.value == normalized or member.name.lower() == normalized:
                    return member
        return None


class TargetStatus(str, Enum):
    """Task-level status, distinct from an individual track lifecycle."""

    UNINITIALIZED = "uninitialized"
    TRACKING = "tracking"
    COASTING = "coasting"
    AMBIGUOUS = "ambiguous"
    LOST = "lost"
    REACQUIRED = "reacquired"

    @classmethod
    def _missing_(cls, value: object) -> "TargetStatus | None":
        if isinstance(value, str):
            normalized = value.strip().lower()
            for member in cls:
                if member.value == normalized or member.name.lower() == normalized:
                    return member
        return None


@dataclass(frozen=True)
class DepthStats:
    """Statistics for valid depth values in an image ROI.

    Depth values are expressed in the same unit as the input after applying
    ``scale``.  Empty or invalid ROIs use ``None`` for numeric statistics.
    """

    valid_count: int
    total_count: int
    valid_fraction: float
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    scale: float = 1.0

    @property
    def is_valid(self) -> bool:
        return self.valid_count > 0 and self.median is not None

    @property
    def count(self) -> int:
        return self.valid_count

    @property
    def depth_mean(self) -> Optional[float]:
        return self.mean

    @property
    def depth_median(self) -> Optional[float]:
        return self.median

    @property
    def depth_std(self) -> Optional[float]:
        return self.std

    def __getitem__(self, key: str) -> Any:
        """Offer dict-like access for simple logging/serialization code."""

        aliases = {
            "valid": "valid_count",
            "count": "valid_count",
            "fraction": "valid_fraction",
            "depth_mean": "mean",
            "depth_median": "median",
            "depth_std": "std",
        }
        return getattr(self, aliases.get(key, key))


@dataclass(frozen=True)
class Detection:
    """One detector output in image coordinates.

    ``position_3d`` is optional and, when present, must be in one documented
    frame (usually camera or local world coordinates).  The core package does
    not perform TF transforms; callers must transform before constructing the
    detection.
    """

    bbox: Sequence[float]
    class_id: Hashable
    confidence: float = 1.0
    timestamp: float = 0.0
    position_3d: Optional[Sequence[float]] = None
    depth_stats: Optional[DepthStats | Mapping[str, Any]] = None
    detection_id: Optional[Hashable] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "bbox", normalize_bbox(self.bbox))
        confidence = _finite_float(self.confidence, "confidence")
        if confidence < 0.0 or confidence > 1.0:
            raise ValueError("confidence must be in [0, 1]")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "timestamp", _finite_float(self.timestamp, "timestamp"))
        if self.position_3d is not None:
            object.__setattr__(self, "position_3d", normalize_vector3(self.position_3d, "position_3d"))

    @property
    def label(self) -> Hashable:
        return self.class_id

    @property
    def class_name(self) -> Hashable:
        return self.class_id

    @property
    def id(self) -> Optional[Hashable]:
        return self.detection_id

    @property
    def bbox_xyxy(self) -> BBox:
        return self.bbox  # type: ignore[return-value]

    @property
    def position(self) -> Optional[Vector3]:
        return self.position_3d  # type: ignore[return-value]

    @property
    def depth_valid_fraction(self) -> Optional[float]:
        stats = self.depth_stats
        if stats is None:
            return None
        if isinstance(stats, Mapping):
            value = stats.get("valid_fraction", stats.get("fraction"))
        else:
            value = stats.valid_fraction
        return None if value is None else float(value)

    @property
    def depth(self) -> Optional[float]:
        stats = self.depth_stats
        if stats is None:
            return None
        value = stats.get("median", stats.get("depth_median")) if isinstance(stats, Mapping) else stats.median
        return None if value is None else float(value)


@dataclass
class Track:
    """Public snapshot and mutable lifecycle state for one target hypothesis."""

    track_id: int
    class_id: Hashable
    bbox: BBox
    state: TrackState = TrackState.TENTATIVE
    confidence: float = 0.0
    position_3d: Optional[Vector3] = None
    velocity_3d: Optional[Vector3] = None
    covariance_3d: Any = None
    # Full [position, velocity] covariance, including cross terms.  The 3x3
    # field remains available to existing consumers that only need position.
    covariance_6d: Any = None
    created_timestamp: float = 0.0
    last_update_timestamp: float = 0.0
    age: int = 1
    hits: int = 1
    missed: int = 0
    # Number of 3-D observations rejected by the Kalman innovation gate for
    # this track.  Keeping the counter on the track lets ROS telemetry and
    # offline evaluation report depth outliers without coupling the core to a
    # middleware message type.
    rejected_measurements: int = 0
    last_detection: Optional[Detection] = None
    # Timestamp of the most recent accepted 3-D RGB-D measurement.  A 2-D
    # box can refresh association while depth is invalid, so it must not reset
    # prediction age used by the controller.
    last_measurement_timestamp: Optional[float] = None
    # Detached evidence of the last attempted 3-D fusion, including rejected
    # candidates. It never replaces last_detection or refreshes measurement age.
    last_measurement_diagnostics: dict[str, Any] = field(default_factory=dict)
    # The filter and frame-local flag are intentionally internal implementation
    # details, but keeping them on the model makes snapshots cheap and clear.
    _filter: Any = field(default=None, repr=False, compare=False)
    _matched_this_frame: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.track_id = int(self.track_id)
        self.bbox = normalize_bbox(self.bbox)
        self.state = TrackState(self.state)
        self.confidence = _finite_float(self.confidence, "confidence")
        if self.position_3d is not None:
            self.position_3d = normalize_vector3(self.position_3d, "position_3d")
        if self.velocity_3d is not None:
            self.velocity_3d = normalize_vector3(self.velocity_3d, "velocity_3d")

    @property
    def label(self) -> Hashable:
        return self.class_id

    @property
    def class_name(self) -> Hashable:
        return self.class_id

    @property
    def id(self) -> int:
        return self.track_id

    @property
    def position(self) -> Optional[Vector3]:
        return self.position_3d

    @property
    def velocity(self) -> Optional[Vector3]:
        return self.velocity_3d

    @property
    def covariance(self) -> Any:
        return self.covariance_3d

    @property
    def is_confirmed(self) -> bool:
        return self.state == TrackState.CONFIRMED

    @property
    def is_active(self) -> bool:
        return self.state in {
            TrackState.TENTATIVE,
            TrackState.CONFIRMED,
            TrackState.COASTING,
        }

    @property
    def is_lost(self) -> bool:
        return self.state in {TrackState.LOST, TrackState.REMOVED}

    @property
    def missed_frames(self) -> int:
        return self.missed

    @property
    def last_seen(self) -> float:
        return self.last_update_timestamp

