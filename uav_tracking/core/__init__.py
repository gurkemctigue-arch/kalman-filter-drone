"""Pure-Python visual tracking primitives."""

from .geometry import (
    CameraIntrinsics,
    backproject,
    backproject_bbox_center,
    backproject_pixel,
    bbox_iou,
    depth_roi_statistics,
    depth_roi_stats,
    pinhole_backproject,
    pixel_to_camera,
    valid_depth_stats,
)
from .kalman import (
    CHI_SQUARE_3D_99,
    ConstantVelocityKF3D,
    ConstantVelocityKalman3D,
    FilterEstimate,
    KalmanFilter3D,
)
from .models import (
    BBox,
    Detection,
    DepthStats,
    TargetMode,
    TargetStatus,
    Track,
    TrackState,
)
from .target_manager import TargetManager, TargetUpdate

__all__ = [
    "BBox",
    "CameraIntrinsics",
    "CHI_SQUARE_3D_99",
    "ConstantVelocityKalman3D",
    "ConstantVelocityKF3D",
    "Detection",
    "DepthStats",
    "FilterEstimate",
    "KalmanFilter3D",
    "TargetManager",
    "TargetMode",
    "TargetStatus",
    "TargetUpdate",
    "Track",
    "TrackState",
    "backproject_bbox_center",
    "backproject",
    "backproject_pixel",
    "bbox_iou",
    "depth_roi_statistics",
    "depth_roi_stats",
    "pinhole_backproject",
    "pixel_to_camera",
    "valid_depth_stats",
]

