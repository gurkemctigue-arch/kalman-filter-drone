"""Hardware-agnostic control primitives for the UAV tracking pipeline."""

from .follow_controller import (
    FollowConfig,
    FollowController,
    FollowControllerConfig,
    FollowSetpoint,
    TargetState,
    VehicleState,
)
from .gimbal_controller import (
    GimbalConfig,
    GimbalController,
    GimbalControllerConfig,
    GimbalSetpoint,
    GimbalState,
)

__all__ = [
    "FollowConfig",
    "FollowController",
    "FollowControllerConfig",
    "FollowSetpoint",
    "TargetState",
    "VehicleState",
    "GimbalConfig",
    "GimbalController",
    "GimbalControllerConfig",
    "GimbalSetpoint",
    "GimbalState",
]
