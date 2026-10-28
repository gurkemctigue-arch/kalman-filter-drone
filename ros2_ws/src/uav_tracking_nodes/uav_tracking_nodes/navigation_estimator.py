"""Timestamped navigation reference filter, separate from visual surface tracks.

This module has no ROS dependency. Only an accepted, independently valid
navigation measurement advances its posterior or refreshes its age. Surface
tracking still owns identity and can prohibit navigation output at any time.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from math import isfinite
from numbers import Integral
from typing import Any, Sequence

import numpy as np

from uav_tracking.core.kalman import ConstantVelocityKalman3D


@dataclass(frozen=True)
class NavigationUpdateResult:
    accepted: bool
    reason: str
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NavigationSnapshot:
    position_world_m: np.ndarray | None = None
    velocity_world_mps: np.ndarray | None = None
    covariance: np.ndarray | None = None
    measurement_age_s: float | None = None
    valid: bool = False
    reason: str = "uninitialized"
    measured_timestamp_s: float | None = None


class NavigationEstimator:
    """An independent six-state filter for a selected navigation reference.

    ``nav_ref`` follows ``core.navigation.NavigationEstimate``: valid,
    position_world_m, covariance (3x3), reason and optional diagnostic metadata.
    The covariance is required: surface uncertainty is never substituted for
    an unobservable footprint. Identity arguments are authoritative task keys;
    callers must pass only the manager's currently selected UUID and track.
    """

    def __init__(
        self,
        *,
        gate_threshold: float = 9.21,
        process_acceleration_std: float = 1.0,
        measurement_noise_std: float | Sequence[float] = (0.05, 0.05, 0.10),
        initial_velocity_covariance: float = 4.0,
        default_dt: float = 1.0 / 30.0,
    ) -> None:
        if not isfinite(float(initial_velocity_covariance)) or initial_velocity_covariance <= 0.0:
            raise ValueError("initial_velocity_covariance must be positive and finite")
        self._filter = ConstantVelocityKalman3D(
            gate_threshold=gate_threshold,
            process_acceleration_std=process_acceleration_std,
            measurement_noise_std=measurement_noise_std,
            initial_velocity_covariance=initial_velocity_covariance,
            default_dt=default_dt,
            adaptive_measurement_noise=False,
        )
        self._identity: tuple[str, int] | None = None
        self._measured_timestamp_s: float | None = None
        self._last_update_diagnostics: dict[str, Any] = {}

    @property
    def measured_timestamp_s(self) -> float | None:
        return self._measured_timestamp_s

    @property
    def last_update_diagnostics(self) -> dict[str, Any]:
        return deepcopy(self._last_update_diagnostics)

    def reset(self) -> None:
        self._identity = None
        self._clear_measurement()
        self._last_update_diagnostics = {}

    def _clear_measurement(self) -> None:
        self._filter.reset()
        self._measured_timestamp_s = None

    def _bind_identity(self, target_uuid: Any, track_id: Any) -> bool:
        if (not isinstance(target_uuid, str) or not target_uuid.strip()
                or isinstance(track_id, bool) or not isinstance(track_id, Integral)
                or track_id < 0):
            self.reset()
            raise ValueError("invalid_identity")
        identity = (target_uuid, int(track_id))
        changed = identity != self._identity
        if changed:
            self._clear_measurement()
            self._last_update_diagnostics = {}
            self._identity = identity
        return changed

    @staticmethod
    def _measurement(nav_ref: Any) -> tuple[np.ndarray, np.ndarray]:
        position = np.asarray(getattr(nav_ref, "position_world_m", None), dtype=float)
        covariance = np.asarray(getattr(nav_ref, "covariance", None), dtype=float)
        if position.shape != (3,) or not np.all(np.isfinite(position)):
            raise ValueError("invalid_navigation_position")
        if covariance.shape != (3, 3) or not np.all(np.isfinite(covariance)):
            raise ValueError("invalid_navigation_covariance")
        if not np.allclose(covariance, covariance.T, rtol=0.0, atol=1e-10):
            raise ValueError("invalid_navigation_covariance")
        covariance = (covariance + covariance.T) / 2.0
        if np.linalg.eigvalsh(covariance).min() < -1e-10:
            raise ValueError("invalid_navigation_covariance")
        return position.copy(), covariance.copy()

    def _result(self, accepted: bool, reason: str, diagnostics: dict[str, Any]) -> NavigationUpdateResult:
        diagnostics.update(accepted=accepted, reason=reason,
                           measured_timestamp_s=self._measured_timestamp_s)
        self._last_update_diagnostics = deepcopy(diagnostics)
        return NavigationUpdateResult(accepted, reason, deepcopy(diagnostics))

    def update(
        self,
        nav_ref: Any,
        timestamp: float,
        target_uuid: str,
        track_id: int,
        initial_velocity: Sequence[float] | None = None,
    ) -> NavigationUpdateResult:
        """Fuse at acquisition time, committing only an accepted candidate.

        Rejecting a malformed reference or innovation cannot move filter time
        or refresh measurement age. Changing either identity component clears
        the previous task before even inspecting the new reference's validity.
        """
        diagnostics: dict[str, Any] = {"schema_version": 1}
        try:
            changed = self._bind_identity(target_uuid, track_id)
            diagnostics.update(target_uuid=target_uuid, track_id=int(track_id),
                               identity_reset=changed)
            timestamp = float(timestamp)
            if not isfinite(timestamp) or timestamp < 0.0:
                raise ValueError("invalid_navigation_timestamp")
            diagnostics["source_timestamp_s"] = timestamp
            if self._measured_timestamp_s is not None and timestamp <= self._measured_timestamp_s:
                raise ValueError("nonmonotonic_navigation_timestamp")
            if getattr(nav_ref, "valid", False) is not True:
                diagnostics["reference_reason"] = str(getattr(nav_ref, "reason", "missing_reference"))
                return self._result(False, "invalid_navigation_reference", diagnostics)
            position, covariance = self._measurement(nav_ref)
            diagnostics.update(raw_measurement_m=position.tolist(),
                               measurement_covariance=covariance.tolist(),
                               reference_kind=str(getattr(nav_ref, "reference_kind", "unknown")),
                               heading_source=str(getattr(nav_ref, "heading_source", "unknown")))
            # update() propagates before applying its gate. Isolate the entire
            # attempt so even a rejected candidate cannot commit that timeline.
            candidate = deepcopy(self._filter)
            if candidate.initialized:
                accepted = candidate.update(position, timestamp=timestamp,
                                            measurement_covariance=covariance)
                diagnostics["filter"] = candidate.last_update_diagnostics
                if not accepted:
                    return self._result(False, "mahalanobis_gate", diagnostics)
                reason = "accepted"
            else:
                candidate.initialize(position, velocity=initial_velocity,
                                     timestamp=timestamp, covariance=covariance)
                diagnostics["filter"] = candidate.last_update_diagnostics
                reason = "initialized"
            self._filter = candidate
            self._measured_timestamp_s = timestamp
            return self._result(True, reason, diagnostics)
        except (TypeError, ValueError, OverflowError, np.linalg.LinAlgError) as error:
            return self._result(False, str(error), diagnostics)

    def project(
        self,
        now: float,
        target_uuid: str,
        track_id: int,
        max_age: float = 0.75,
        surface_status: Any = "tracking",
    ) -> NavigationSnapshot:
        """Return a detached output snapshot without committing predictions.

        An invalid snapshot contains no position/velocity that a caller could
        accidentally command. LOST clears the navigation posterior, while an
        ambiguous surface task may retain it for a later explicit valid update.
        """
        age: float | None = None
        try:
            self._bind_identity(target_uuid, track_id)
            status = str(getattr(surface_status, "value", surface_status)).strip().lower()
            if status == "lost":
                self._clear_measurement()
                raise ValueError("surface_lost")
            now, max_age = float(now), float(max_age)
            if not isfinite(now) or now < 0.0:
                raise ValueError("invalid_projection_timestamp")
            if not isfinite(max_age) or max_age <= 0.0:
                raise ValueError("invalid_navigation_max_age")
            if self._measured_timestamp_s is not None:
                age = now - self._measured_timestamp_s
                if age < 0.0:
                    age = None
                    raise ValueError("future_navigation_measurement")
            # REACQUIRED is a manager-confirmed fresh match after a missed
            # frame, not permission to revive a LOST task. The manager's
            # reselection latch and identity key remain authoritative.
            if status not in {"tracking", "coasting", "reacquired"}:
                raise ValueError(f"surface_{status or 'unknown'}")
            if self._measured_timestamp_s is None or not self._filter.initialized:
                raise ValueError("navigation_uninitialized")
            if age is None or age > max_age:
                raise ValueError("stale_navigation_measurement")
            estimate = self._filter.project(now)
            return NavigationSnapshot(
                position_world_m=estimate.position.copy(), velocity_world_mps=estimate.velocity.copy(),
                covariance=estimate.covariance.copy(), measurement_age_s=age,
                valid=True, reason="tracking" if age == 0.0 else "prediction",
                measured_timestamp_s=self._measured_timestamp_s,
            )
        except (TypeError, ValueError, OverflowError) as error:
            return NavigationSnapshot(measurement_age_s=age, valid=False,
                                      reason=str(error), measured_timestamp_s=self._measured_timestamp_s)
