"""A dependency-light 3-D constant-velocity Kalman filter."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from .models import DepthStats, normalize_vector3


CHI_SQUARE_3D_99 = 11.344866730144373


def _vector3(value: Sequence[float], name: str = "value") -> np.ndarray:
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.size != 3 or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite 3-vector")
    return array.copy()


@dataclass(frozen=True)
class FilterEstimate:
    """Immutable snapshot returned by :meth:`ConstantVelocityKalman3D.estimate`."""

    position: np.ndarray
    velocity: np.ndarray
    covariance: np.ndarray
    timestamp: Optional[float]
    initialized: bool


class ConstantVelocityKalman3D:
    """Six-state ``[x,y,z,vx,vy,vz]`` Kalman filter.

    The filter accepts a quality score or :class:`DepthStats` on update.  A
    lower quality inflates measurement covariance, making noisy RGB-D samples
    less influential while preserving a configurable floor and ceiling.
    """

    measurement_matrix = np.hstack((np.eye(3), np.zeros((3, 3))))

    def __init__(
        self,
        *,
        process_acceleration_std: float = 1.0,
        measurement_noise_std: float | Sequence[float] = 0.05,
        initial_position_covariance: float = 1.0,
        initial_velocity_covariance: float = 4.0,
        gate_threshold: float = CHI_SQUARE_3D_99,
        adaptive_measurement_noise: bool = True,
        min_quality: float = 0.05,
        max_noise_scale: float = 100.0,
        default_dt: float = 1.0 / 30.0,
        # Common shorter names are accepted for adapters and examples.  The
        # explicit names above remain the canonical API.
        dt: Optional[float] = None,
        process_noise: Optional[float] = None,
        measurement_noise: Optional[float | Sequence[float]] = None,
    ) -> None:
        if dt is not None:
            default_dt = float(dt)
        if process_noise is not None:
            process_acceleration_std = float(process_noise)
        if measurement_noise is not None:
            measurement_noise_std = measurement_noise
        if process_acceleration_std <= 0.0 or not isfinite(float(process_acceleration_std)):
            raise ValueError("process_acceleration_std must be positive and finite")
        if initial_position_covariance <= 0.0 or initial_velocity_covariance <= 0.0:
            raise ValueError("initial covariance values must be positive")
        if gate_threshold <= 0.0 or not isfinite(float(gate_threshold)):
            raise ValueError("gate_threshold must be positive and finite")
        if default_dt <= 0.0 or not isfinite(float(default_dt)):
            raise ValueError("default_dt must be positive and finite")
        self.process_acceleration_std = float(process_acceleration_std)
        noise_array = np.asarray(measurement_noise_std, dtype=float)
        if noise_array.shape == (3, 3):
            noise = np.sqrt(np.maximum(0.0, np.diag(noise_array)))
        else:
            noise = noise_array.reshape(-1)
        if noise.size == 1:
            noise = np.repeat(noise, 3)
        if noise.size != 3 or np.any(noise <= 0.0) or not np.all(np.isfinite(noise)):
            raise ValueError("measurement_noise_std must be one or three positive finite values")
        self.measurement_noise_std = noise
        self.initial_position_covariance = float(initial_position_covariance)
        self.initial_velocity_covariance = float(initial_velocity_covariance)
        self.gate_threshold = float(gate_threshold)
        self.adaptive_measurement_noise = bool(adaptive_measurement_noise)
        self.min_quality = float(min_quality)
        self.max_noise_scale = float(max_noise_scale)
        self.default_dt = float(default_dt)
        if not 0.0 < self.min_quality <= 1.0:
            raise ValueError("min_quality must be in (0, 1]")
        if self.max_noise_scale < 1.0 or not isfinite(self.max_noise_scale):
            raise ValueError("max_noise_scale must be finite and at least one")
        self.state = np.zeros(6, dtype=float)
        self.covariance = np.eye(6, dtype=float)
        self.timestamp: Optional[float] = None
        self.initialized = False
        self.last_mahalanobis_distance: Optional[float] = None
        self.last_measurement_covariance = np.diag(self.measurement_noise_std**2)
        self.last_update_accepted = False

    @property
    def position(self) -> np.ndarray:
        return self.state[:3].copy()

    @property
    def velocity(self) -> np.ndarray:
        return self.state[3:].copy()

    @property
    def x(self) -> np.ndarray:
        """Alias for the six-element state vector."""

        return self.state.copy()

    @property
    def P(self) -> np.ndarray:
        """Alias for state covariance."""

        return self.covariance.copy()

    @property
    def R(self) -> np.ndarray:
        """Most recently used measurement covariance."""

        return self.last_measurement_covariance.copy()

    @property
    def Q(self) -> np.ndarray:
        """Discrete process covariance for the configured default timestep."""

        return self._process_covariance(self.default_dt)

    @property
    def estimate(self) -> FilterEstimate:
        return FilterEstimate(self.position, self.velocity, self.covariance.copy(), self.timestamp, self.initialized)

    def reset(self) -> None:
        self.state[:] = 0.0
        self.covariance = np.eye(6, dtype=float)
        self.timestamp = None
        self.initialized = False
        self.last_mahalanobis_distance = None
        self.last_update_accepted = False

    def initialize(
        self,
        position: Sequence[float],
        *,
        velocity: Optional[Sequence[float]] = None,
        timestamp: Optional[float] = None,
        covariance: Optional[Any] = None,
    ) -> FilterEstimate:
        pos = _vector3(position, "position")
        vel = np.zeros(3, dtype=float) if velocity is None else _vector3(velocity, "velocity")
        self.state = np.concatenate((pos, vel))
        if covariance is None:
            self.covariance = np.diag(
                [
                    self.initial_position_covariance,
                    self.initial_position_covariance,
                    self.initial_position_covariance,
                    self.initial_velocity_covariance,
                    self.initial_velocity_covariance,
                    self.initial_velocity_covariance,
                ]
            )
        else:
            array = np.asarray(covariance, dtype=float)
            if array.shape == (3, 3):
                self.covariance = np.zeros((6, 6), dtype=float)
                self.covariance[:3, :3] = array
                self.covariance[3:, 3:] = np.eye(3) * self.initial_velocity_covariance
            elif array.shape == (6, 6):
                self.covariance = array.copy()
            else:
                raise ValueError("covariance must be 3x3 or 6x6")
            if not np.all(np.isfinite(self.covariance)):
                raise ValueError("covariance must be finite")
        self.timestamp = None if timestamp is None else float(timestamp)
        if self.timestamp is not None and not isfinite(self.timestamp):
            raise ValueError("timestamp must be finite")
        self.initialized = True
        self.last_update_accepted = True
        return self.estimate

    def _transition(self, dt: float) -> np.ndarray:
        transition = np.eye(6, dtype=float)
        transition[:3, 3:] = np.eye(3) * dt
        return transition

    def _process_covariance(self, dt: float) -> np.ndarray:
        # Continuous white acceleration model, independently per axis.
        q = self.process_acceleration_std**2
        block = np.array([[dt**4 / 4.0, dt**3 / 2.0], [dt**3 / 2.0, dt**2]], dtype=float) * q
        process = np.zeros((6, 6), dtype=float)
        for axis in range(3):
            process[axis, axis] = block[0, 0]
            process[axis, axis + 3] = block[0, 1]
            process[axis + 3, axis] = block[1, 0]
            process[axis + 3, axis + 3] = block[1, 1]
        return process

    def predict(self, dt: Optional[float] = None, timestamp: Optional[float] = None) -> FilterEstimate:
        """Advance the state; repeated timestamps produce a no-op prediction."""

        if not self.initialized:
            return self.estimate
        if timestamp is not None:
            timestamp = float(timestamp)
            if not isfinite(timestamp):
                raise ValueError("timestamp must be finite")
            if self.timestamp is None:
                effective_dt = self.default_dt if dt is None else float(dt)
            else:
                effective_dt = timestamp - self.timestamp
                if effective_dt < -1e-9:
                    raise ValueError("timestamps must be monotonic")
                effective_dt = max(0.0, effective_dt)
        else:
            effective_dt = self.default_dt if dt is None else float(dt)
        if not isfinite(effective_dt) or effective_dt < 0.0:
            raise ValueError("dt must be finite and non-negative")
        transition = self._transition(effective_dt)
        self.state = transition @ self.state
        self.covariance = transition @ self.covariance @ transition.T + self._process_covariance(effective_dt)
        self.covariance = (self.covariance + self.covariance.T) / 2.0
        if timestamp is not None:
            self.timestamp = timestamp
        elif self.timestamp is not None:
            self.timestamp += effective_dt
        return self.estimate

    def project(self, timestamp: float) -> FilterEstimate:
        """Project to an output time without moving the measurement timeline.

        A controller may need 50 Hz predictions while camera inference only
        completes at 5 Hz.  Committing those predictions would put the filter
        ahead of normally delayed image timestamps.  This snapshot leaves the
        posterior state, covariance, and timestamp unchanged so the next image
        can still be fused at its actual acquisition time.
        """

        timestamp = float(timestamp)
        if not isfinite(timestamp):
            raise ValueError("timestamp must be finite")
        if not self.initialized:
            return self.estimate
        if self.timestamp is None:
            raise ValueError("project requires a timestamped filter")
        dt = timestamp - self.timestamp
        if dt < -1e-9:
            raise ValueError("projection time must not precede filter time")
        dt = max(0.0, dt)
        transition = self._transition(dt)
        state = transition @ self.state
        covariance = transition @ self.covariance @ transition.T + self._process_covariance(dt)
        covariance = (covariance + covariance.T) / 2.0
        return FilterEstimate(state[:3].copy(), state[3:].copy(), covariance, timestamp, True)

    @staticmethod
    def _quality_value(quality: Any = None, depth_stats: Any = None, confidence: Any = None) -> float:
        values = []
        if quality is not None:
            values.append(float(quality))
        if confidence is not None:
            values.append(float(confidence))
        if depth_stats is not None:
            if isinstance(depth_stats, Mapping):
                fraction = depth_stats.get("valid_fraction", depth_stats.get("fraction"))
                spread = depth_stats.get("std", depth_stats.get("depth_std"))
            else:
                fraction = getattr(depth_stats, "valid_fraction", None)
                spread = getattr(depth_stats, "std", getattr(depth_stats, "depth_std", None))
            if fraction is not None:
                values.append(float(fraction))
            if spread is not None and isfinite(float(spread)):
                # A large spread indicates less reliable depth, but does not
                # dominate a detector confidence by itself.
                values.append(1.0 / (1.0 + max(0.0, float(spread))))
        if not values:
            return 1.0
        return float(np.clip(np.mean(values), 0.0, 1.0))

    def measurement_covariance(
        self,
        *,
        quality: Any = None,
        depth_stats: Any = None,
        confidence: Any = None,
        covariance: Optional[Any] = None,
    ) -> np.ndarray:
        if covariance is not None:
            matrix = np.asarray(covariance, dtype=float)
            if matrix.shape == (3,):
                # ``measurement_covariance`` is already a variance vector;
                # standard deviations are configured via measurement_noise_std.
                matrix = np.diag(matrix)
            elif matrix.shape != (3, 3):
                raise ValueError("measurement covariance must be a 3-vector or 3x3 matrix")
            if not np.all(np.isfinite(matrix)):
                raise ValueError("measurement covariance must be finite")
            return matrix.copy()
        base = np.diag(self.measurement_noise_std**2)
        if not self.adaptive_measurement_noise:
            return base
        q = max(self.min_quality, self._quality_value(quality, depth_stats, confidence))
        scale = min(self.max_noise_scale, 1.0 / (q * q))
        return base * scale

    def innovation(self, measurement: Sequence[float], measurement_covariance: Optional[Any] = None) -> tuple[np.ndarray, np.ndarray]:
        z = _vector3(measurement, "measurement")
        covariance = self.measurement_covariance(covariance=measurement_covariance)
        innovation = z - self.state[:3]
        innovation_covariance = self.covariance[:3, :3] + covariance
        return innovation, innovation_covariance

    def mahalanobis_distance(
        self,
        measurement: Sequence[float],
        *,
        measurement_covariance: Optional[Any] = None,
    ) -> float:
        innovation, innovation_covariance = self.innovation(measurement, measurement_covariance)
        try:
            solved = np.linalg.solve(innovation_covariance, innovation)
        except np.linalg.LinAlgError:
            solved = np.linalg.pinv(innovation_covariance) @ innovation
        return float(innovation @ solved)

    def mahalanobis(self, measurement: Sequence[float], *, measurement_covariance: Optional[Any] = None) -> float:
        """Short alias for :meth:`mahalanobis_distance`."""

        return self.mahalanobis_distance(measurement, measurement_covariance=measurement_covariance)

    def update(
        self,
        measurement: Sequence[float],
        timestamp: Optional[float] = None,
        *,
        quality: Any = None,
        depth_stats: Any = None,
        confidence: Any = None,
        measurement_covariance: Optional[Any] = None,
        gate_threshold: Optional[float] = None,
    ) -> bool:
        """Update from a 3-D measurement, returning ``False`` on gate rejection."""

        z = _vector3(measurement, "measurement")
        if not self.initialized:
            self.initialize(z, timestamp=timestamp)
            self.last_measurement_covariance = self.measurement_covariance(
                quality=quality, depth_stats=depth_stats, confidence=confidence, covariance=measurement_covariance
            )
            self.last_mahalanobis_distance = 0.0
            return True
        if timestamp is not None:
            timestamp = float(timestamp)
            if self.timestamp is not None and timestamp < self.timestamp - 1e-9:
                raise ValueError("timestamps must be monotonic")
            self.predict(timestamp=timestamp)
        covariance = self.measurement_covariance(
            quality=quality, depth_stats=depth_stats, confidence=confidence, covariance=measurement_covariance
        )
        innovation = z - self.state[:3]
        innovation_covariance = self.covariance[:3, :3] + covariance
        try:
            solved = np.linalg.solve(innovation_covariance, innovation)
        except np.linalg.LinAlgError:
            solved = np.linalg.pinv(innovation_covariance) @ innovation
        distance = float(innovation @ solved)
        self.last_mahalanobis_distance = distance
        self.last_measurement_covariance = covariance.copy()
        threshold = self.gate_threshold if gate_threshold is None else float(gate_threshold)
        if threshold <= 0.0 or not isfinite(threshold):
            raise ValueError("gate_threshold must be positive and finite")
        if distance > threshold:
            self.last_update_accepted = False
            return False
        gain = self.covariance[:, :3] @ np.linalg.pinv(innovation_covariance)
        self.state = self.state + gain @ innovation
        identity = np.eye(6)
        observation = self.measurement_matrix
        # Joseph form keeps covariance positive semidefinite under finite
        # precision and changing measurement noise.
        residual_transform = identity - gain @ observation
        self.covariance = (
            residual_transform @ self.covariance @ residual_transform.T + gain @ covariance @ gain.T
        )
        self.covariance = (self.covariance + self.covariance.T) / 2.0
        self.last_update_accepted = True
        return True

    def update_from_depth(
        self,
        measurement: Sequence[float],
        depth_stats: Optional[DepthStats],
        *,
        confidence: Optional[float] = None,
        timestamp: Optional[float] = None,
    ) -> bool:
        return self.update(
            measurement,
            depth_stats=depth_stats,
            confidence=confidence,
            timestamp=timestamp,
        )


# Familiar aliases keep the core easy to adopt without coupling callers to a
# particular naming convention.
KalmanFilter3D = ConstantVelocityKalman3D
ConstantVelocityKF3D = ConstantVelocityKalman3D

