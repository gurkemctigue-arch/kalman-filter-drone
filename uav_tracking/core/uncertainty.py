"""First-order propagation of measured vehicle pose uncertainty to a point."""
from __future__ import annotations

from typing import Any
import numpy as np


def pose_point_covariance(point_world: Any, body_position_world: Any, pose_covariance_world: Any) -> np.ndarray:
    """Return pose contribution to a transformed 3-D point covariance.

    Pose errors use world x/y/z translation and small rotation-vector angles
    about world axes. The lever arm includes the camera mount. Pose/point
    independence is an explicit approximation; no simulator truth is used.
    """
    point, origin = np.asarray(point_world, dtype=float), np.asarray(body_position_world, dtype=float)
    covariance = np.asarray(pose_covariance_world, dtype=float)
    if point.shape != (3,) or origin.shape != (3,) or covariance.shape != (6, 6):
        raise ValueError("point/origin must be 3-vectors and pose covariance 6x6")
    if not all(np.isfinite(value).all() for value in (point, origin, covariance)):
        raise ValueError("pose uncertainty inputs must be finite")
    if not np.allclose(covariance, covariance.T, atol=1e-10) or np.linalg.eigvalsh(covariance).min() < -1e-10:
        raise ValueError("pose covariance must be symmetric positive semidefinite")
    x, y, z = point - origin
    cross = np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])
    jacobian = np.column_stack((np.eye(3), -cross))
    result = jacobian @ covariance @ jacobian.T
    return (result + result.T) * .5
