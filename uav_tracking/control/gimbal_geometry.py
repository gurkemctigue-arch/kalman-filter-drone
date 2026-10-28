"""Geometry of the stage-three physical FLU yaw/pitch/roll gimbal.

All three axes intersect at the measured camera mount origin. Joint angles
are yaw about +Z, pitch about +Y (positive looks down), roll about +X.
Pitch has a fixed 0.35 rad downward mount bias. This is deliberately a
transport-independent description; it consumes measured joint positions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np


JOINT_NAMES = ("tracking_gimbal_yaw", "tracking_gimbal_pitch", "tracking_gimbal_roll")
MOUNT_TRANSLATION = np.array([0.13233, 0.0, 0.26078])
MOUNT_PITCH = 0.35
JOINT_LOWER = np.array([-1.2, -1.4, -0.7])
JOINT_UPPER = np.array([1.2, 0.9, 0.7])


def _finite_vector(value: Sequence[float], size: int) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.shape != (size,) or not np.all(np.isfinite(array)):
        raise ValueError(f"expected {size} finite values")
    return array


def rotation_xyz(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Rz(yaw) Ry(pitch) Rx(roll), frame-to-parent active rotation."""

    _finite_vector([roll, pitch, yaw], 3)
    sr, cr, sp, cp, sy, cy = math.sin(roll), math.cos(roll), math.sin(pitch), math.cos(pitch), math.sin(yaw), math.cos(yaw)
    return np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ])


def quaternion_rotation(quaternion_xyzw: Sequence[float]) -> np.ndarray:
    q = _finite_vector(quaternion_xyzw, 4)
    norm = float(np.linalg.norm(q))
    if norm < 1e-12:
        raise ValueError("zero quaternion")
    x, y, z, w = q / norm
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _quaternion_product(left: Sequence[float], right: Sequence[float]) -> np.ndarray:
    x1, y1, z1, w1 = left
    x2, y2, z2, w2 = right
    return np.array([w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
                     w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2])


def camera_optical_quaternion(joint_angles: Sequence[float], mount_pitch: float = MOUNT_PITCH) -> np.ndarray:
    """Body FLU <- optical right/down/forward, from feedback (ROS xyzw)."""

    yaw, pitch_delta, roll = _finite_vector(joint_angles, 3)
    pitch = float(mount_pitch) + pitch_delta
    _finite_vector([pitch], 1)
    qz = [0, 0, math.sin(yaw / 2), math.cos(yaw / 2)]
    qy = [0, math.sin(pitch / 2), 0, math.cos(pitch / 2)]
    qx = [math.sin(roll / 2), 0, 0, math.cos(roll / 2)]
    return _quaternion_product(_quaternion_product(_quaternion_product(qz, qy), qx), [-0.5, 0.5, -0.5, 0.5])


def desired_joint_angles(line_of_sight_body: Sequence[float], world_from_body: np.ndarray,
                         mount_pitch: float = MOUNT_PITCH) -> np.ndarray:
    """Point optical forward at LOS and level the image horizon.

    Roll is solved after yaw/pitch, rather than simply subtracting Euler
    roll, which is incorrect when the gimbal is turned sideways.
    """

    x, y, z = _finite_vector(line_of_sight_body, 3)
    rotation = np.asarray(world_from_body, dtype=float)
    if rotation.shape != (3, 3) or not np.all(np.isfinite(rotation)):
        raise ValueError("world_from_body must be finite 3x3")
    if math.sqrt(x * x + y * y + z * z) < 1e-9:
        raise ValueError("zero line of sight")
    yaw = math.atan2(y, x)
    pitch = math.atan2(-z, math.hypot(x, y))
    # World-up resolved in the pre-roll yaw/pitch camera FLU frame. The
    # post-roll left-axis has dot(up)=uy*cos(roll)+uz*sin(roll), set to zero.
    up = rotation_xyz(0.0, pitch, yaw).T @ rotation.T @ np.array([0.0, 0.0, 1.0])
    roll = math.atan2(-float(up[1]), float(up[2]))
    return np.clip([yaw, pitch - float(mount_pitch), roll], JOINT_LOWER, JOINT_UPPER)


def ordered_joint_positions(names: Sequence[str], positions: Sequence[float]) -> np.ndarray:
    """Resolve all three distinct measured joints; reject partial/NaN state."""

    if len(names) != len(positions) or len(set(names)) != len(names):
        raise ValueError("joint names/positions are incomplete or duplicated")
    mapping = dict(zip(names, positions))
    try:
        return _finite_vector([mapping[name] for name in JOINT_NAMES], 3)
    except KeyError as error:
        raise ValueError(f"missing measured joint {error.args[0]}") from error


def bounded_joint_command(measured: Sequence[float], desired: Sequence[float], dt: float,
                          gains: Sequence[float] = (4.0, 4.0, 5.0),
                          max_rates: Sequence[float] = (1.0, 0.8, 1.0)) -> tuple[np.ndarray, np.ndarray]:
    measured = _finite_vector(measured, 3)
    desired = np.clip(_finite_vector(desired, 3), JOINT_LOWER, JOINT_UPPER)
    gains, limits = _finite_vector(gains, 3), _finite_vector(max_rates, 3)
    if not math.isfinite(dt) or not 0 < dt <= 0.2 or np.any(gains < 0) or np.any(limits < 0):
        raise ValueError("invalid control dt/gains/rates")
    rates = np.clip(gains * (desired - measured), -limits, limits)
    return np.clip(measured + rates * dt, JOINT_LOWER, JOINT_UPPER), rates


def wrap_angle(angle: float) -> float:
    return (float(angle) + math.pi) % (2 * math.pi) - math.pi


@dataclass
class BodyYawReference:
    """Slow continuous recenter reference, aligned to the real body on reset.

    The integration rate is bounded. A sudden external body-yaw change can
    violate the lead constraint; in that case, reset to measured attitude
    rather than retaining an unsafe distant yaw reference. Reset discontinuity
    is explicitly reported and is not presented as a rate-bounded segment.
    """

    max_rate: float = 0.10
    gain: float = 0.6
    deadzone: float = 0.15
    max_lead: float = 0.20
    yaw: float | None = None
    target_uuid: str | None = None

    def reset(self) -> None:
        self.yaw, self.target_uuid = None, None

    def update(self, body_yaw: float, gimbal_yaw: float, dt: float, target_uuid: str) -> tuple[float, float, bool]:
        _finite_vector([body_yaw, gimbal_yaw, dt, self.max_rate, self.gain, self.deadzone, self.max_lead], 7)
        if not 0 < dt <= 0.2 or self.max_rate < 0 or self.gain < 0 or self.deadzone < 0 or self.max_lead <= 0:
            raise ValueError("invalid yaw reference configuration")
        reset = self.yaw is None or self.target_uuid != target_uuid
        if reset:
            self.yaw = wrap_angle(body_yaw)
            self.target_uuid = target_uuid
        excess = math.copysign(max(0.0, abs(gimbal_yaw) - self.deadzone), gimbal_yaw)
        rate = float(np.clip(self.gain * excess, -self.max_rate, self.max_rate))
        previous = float(self.yaw)
        proposal = wrap_angle(previous + rate * dt)
        # If the body catches/passes the reference, a zero gimbal demand must
        # not leave an old yaw offset forever. Track actual body only during
        # a hard lead violation; normal recenter uses the integrated reference.
        lead = wrap_angle(proposal - body_yaw)
        if abs(lead) > self.max_lead:
            proposal = wrap_angle(body_yaw + float(np.clip(lead, -self.max_lead, self.max_lead)))
            reset = True
        self.yaw = proposal
        return proposal, rate, reset
