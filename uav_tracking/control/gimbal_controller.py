"""Pure Python three-axis gimbal controller.

The controller consumes a line-of-sight vector and produces bounded yaw,
pitch, and roll commands.  It is intentionally independent of ROS, PX4, and
any particular gimbal transport.  The convention used here is x-forward,
y-right, z-up in the gimbal frame; adapters are responsible for converting a
camera/vehicle convention before calling :meth:`GimbalController.update`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence, Union

import numpy as np


ArrayLike = Union[Sequence[float], np.ndarray]


def _vec3(value: ArrayLike, name: str) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.shape != (3,):
        raise ValueError(f"{name} must have shape (3,), got {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    return array.copy()


def _finite_nonnegative(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _limit(value: Union[float, ArrayLike], name: str) -> Union[float, np.ndarray]:
    if np.isscalar(value):
        result = float(value)
        if result < 0.0 or math.isnan(result):
            raise ValueError(f"{name} must be non-negative")
        return result
    result = np.asarray(value, dtype=float)
    if result.shape != (3,) or np.any(np.isnan(result)) or np.any(result < 0.0):
        raise ValueError(f"{name} must be non-negative")
    return result.copy()


def _gain(value: Union[float, ArrayLike], vector: np.ndarray) -> np.ndarray:
    return float(value) * vector if np.isscalar(value) else np.asarray(value, dtype=float) * vector


def _clip_rate(value: np.ndarray, limits: Union[float, np.ndarray]) -> np.ndarray:
    if np.isscalar(limits):
        limit = float(limits)
        if not math.isfinite(limit):
            return value.copy()
        if limit <= 0.0:
            return np.zeros(3)
        # A scalar gimbal rate is an independent per-axis limit.  This keeps
        # yaw, pitch, and roll from affecting one another's saturation.
        return np.clip(value, -limit, limit)
    limits = np.asarray(limits, dtype=float)
    result = value.copy()
    finite = np.isfinite(limits)
    result[finite] = np.clip(result[finite], -limits[finite], limits[finite])
    return result


def _wrap(angle: float) -> float:
    """Wrap an angle to [-pi, pi)."""

    return (float(angle) + math.pi) % (2.0 * math.pi) - math.pi


def _angle_error(desired: float, current: float, periodic: bool) -> float:
    error = float(desired) - float(current)
    return _wrap(error) if periodic else error


@dataclass
class GimbalState:
    """Current gimbal state in radians, ordered yaw/pitch/roll."""

    angles: ArrayLike = field(default_factory=lambda: np.zeros(3))
    rates: ArrayLike = field(default_factory=lambda: np.zeros(3))
    valid: bool = True
    age: float = 0.0
    timestamp: Optional[float] = None
    is_valid: Optional[bool] = None

    def __post_init__(self) -> None:
        self.angles = _vec3(self.angles, "angles")
        self.rates = _vec3(self.rates, "rates")
        self.age = _finite_nonnegative(self.age, "age")
        if self.is_valid is not None:
            self.valid = bool(self.is_valid)

    @property
    def yaw(self) -> float:
        return float(self.angles[0])

    @property
    def pitch(self) -> float:
        return float(self.angles[1])

    @property
    def roll(self) -> float:
        return float(self.angles[2])


@dataclass
class GimbalConfig:
    """Three-axis gimbal limits and proportional gains, in radians."""

    yaw_gain: float = 2.0
    pitch_gain: float = 2.0
    roll_gain: float = 2.0
    max_rate: Union[float, ArrayLike] = field(default_factory=lambda: np.array([1.5, 1.0, 1.0]))
    yaw_limits: tuple[float, float] = (-math.pi, math.pi)
    pitch_limits: tuple[float, float] = (-math.pi / 2.0, math.pi / 2.0)
    roll_limits: tuple[float, float] = (-math.pi, math.pi)
    deadzone: Union[float, ArrayLike] = 0.0
    target_timeout: float = 0.5
    max_dt: float = 0.5
    failsafe_mode: str = "hold"
    horizon_roll: float = 0.0

    def __post_init__(self) -> None:
        for name in ("yaw_gain", "pitch_gain", "roll_gain"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
            setattr(self, name, value)
        self.max_rate = _limit(self.max_rate, "max_rate")
        self.deadzone = _limit(self.deadzone, "deadzone")
        self.target_timeout = _finite_nonnegative(self.target_timeout, "target_timeout")
        self.max_dt = _finite_nonnegative(self.max_dt, "max_dt")
        self.horizon_roll = float(self.horizon_roll)
        if not math.isfinite(self.horizon_roll):
            raise ValueError("horizon_roll must be finite")
        self.yaw_limits = self._limits(self.yaw_limits, "yaw_limits", periodic=True)
        self.pitch_limits = self._limits(self.pitch_limits, "pitch_limits")
        self.roll_limits = self._limits(self.roll_limits, "roll_limits", periodic=True)
        self.failsafe_mode = str(self.failsafe_mode).lower()
        if self.failsafe_mode not in {"hold", "zero"}:
            raise ValueError("failsafe_mode must be 'hold' or 'zero'")

    @staticmethod
    def _limits(value: Sequence[float], name: str, periodic: bool = False) -> tuple[float, float]:
        if len(value) != 2:
            raise ValueError(f"{name} must contain (min, max)")
        lower, upper = float(value[0]), float(value[1])
        if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
            raise ValueError(f"{name} must be finite and ordered")
        if periodic and upper - lower > 2.0 * math.pi + 1e-9:
            raise ValueError(f"{name} span cannot exceed 2*pi")
        return lower, upper


GimbalControllerConfig = GimbalConfig


@dataclass
class GimbalSetpoint:
    """Bounded gimbal angle and angular-rate command."""

    angles: np.ndarray
    rates: np.ndarray = field(default_factory=lambda: np.zeros(3))
    valid: bool = True
    failsafe: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        self.angles = _vec3(self.angles, "angles")
        self.rates = _vec3(self.rates, "rates")

    @property
    def yaw(self) -> float:
        return float(self.angles[0])

    @property
    def pitch(self) -> float:
        return float(self.angles[1])

    @property
    def roll(self) -> float:
        return float(self.angles[2])

    @property
    def yaw_rate(self) -> float:
        return float(self.rates[0])

    @property
    def pitch_rate(self) -> float:
        return float(self.rates[1])

    @property
    def roll_rate(self) -> float:
        return float(self.rates[2])

    @property
    def command_angles(self) -> np.ndarray:
        return self.angles.copy()

    @property
    def command_rates(self) -> np.ndarray:
        return self.rates.copy()


class GimbalController:
    """P-control for yaw/pitch line of sight and level-horizon roll."""

    def __init__(
        self,
        config: Optional[Union[GimbalConfig, Mapping[str, Any]]] = None,
        **overrides: Any,
    ) -> None:
        if config is None:
            self.config = GimbalConfig(**overrides)
        elif isinstance(config, GimbalConfig):
            values = dict(config.__dict__)
            values.update(overrides)
            self.config = GimbalConfig(**values)
        elif isinstance(config, Mapping):
            values = dict(config)
            values.update(overrides)
            self.config = GimbalConfig(**values)
        else:
            raise TypeError("config must be GimbalConfig, a mapping, or None")
        self._angles = np.zeros(3, dtype=float)

    def reset(self, angles: Optional[ArrayLike] = None) -> None:
        self._angles = np.zeros(3, dtype=float) if angles is None else _vec3(angles, "angles")

    def update(
        self,
        line_of_sight: Optional[ArrayLike] = None,
        state: Optional[Union[GimbalState, ArrayLike, Mapping[str, Any]]] = None,
        dt: float = 0.02,
        target_valid: bool = True,
        target_age: float = 0.0,
        horizon_roll: Optional[float] = None,
        current_angles: Optional[ArrayLike] = None,
        target_vector: Optional[ArrayLike] = None,
    ) -> GimbalSetpoint:
        """Compute one bounded gimbal command.

        ``line_of_sight`` is a vector in gimbal coordinates.  A zero vector,
        stale target, invalid state, or invalid time step yields a hold
        failsafe command.  ``horizon_roll`` can override the configured level
        roll when an attitude estimator supplies a horizon reference.
        """

        if current_angles is not None:
            state = current_angles
        if target_vector is not None:
            line_of_sight = target_vector
        try:
            dt = float(dt)
            target_age = float(target_age)
        except (TypeError, ValueError):
            return self._failsafe("invalid_dt")
        current, state_valid, state_age = self._coerce_state(state)
        if not math.isfinite(dt) or dt <= 0.0 or (self.config.max_dt > 0 and dt > self.config.max_dt):
            return self._failsafe("invalid_dt", current)
        if not math.isfinite(target_age) or target_age < 0.0:
            return self._failsafe("invalid_target_age", current)
        if not math.isfinite(state_age) or state_age < 0.0 or not state_valid or state_age > self.config.target_timeout:
            return self._failsafe("invalid_gimbal_state", current)
        if not target_valid or target_age > self.config.target_timeout:
            return self._failsafe("stale_target", current)
        if line_of_sight is None:
            return self._failsafe("missing_line_of_sight", current)
        try:
            vector = _vec3(line_of_sight, "line_of_sight")
        except ValueError:
            return self._failsafe("invalid_line_of_sight", current)
        norm = float(np.linalg.norm(vector))
        if norm <= 1e-9:
            return self._failsafe("zero_line_of_sight", current)

        # Normalize only for numerical consistency; atan2 itself is scale
        # invariant, but normalizing makes the intent explicit.
        vector /= norm
        desired = np.array(
            [
                math.atan2(vector[1], vector[0]),
                math.atan2(vector[2], math.hypot(vector[0], vector[1])),
                self.config.horizon_roll if horizon_roll is None else float(horizon_roll),
            ],
            dtype=float,
        )
        desired = self._clamp_angles(desired)

        errors = np.array(
            [
                _angle_error(desired[0], current[0], periodic=True),
                _angle_error(desired[1], current[1], periodic=False),
                _angle_error(desired[2], current[2], periodic=True),
            ],
            dtype=float,
        )
        errors = self._apply_deadzone(errors)
        rates = np.array(
            [
                self.config.yaw_gain * errors[0],
                self.config.pitch_gain * errors[1],
                self.config.roll_gain * errors[2],
            ],
            dtype=float,
        )
        rates = _clip_rate(rates, self.config.max_rate)

        # Integrate the bounded rate for a transport-friendly angle command.
        angles = self._clamp_angles(current + rates * dt)
        # If a limit was reached, do not continue commanding outward motion.
        rates = self._zero_outward_limit_rates(angles, rates)
        self._angles = angles.copy()
        return GimbalSetpoint(angles=angles, rates=rates, valid=True)

    compute = update
    step = update

    def from_errors(
        self,
        yaw_error: float,
        pitch_error: float,
        current_angles: Optional[ArrayLike] = None,
        dt: float = 0.02,
        roll_error: Optional[float] = None,
    ) -> GimbalSetpoint:
        """Control directly from angular errors when no LOS vector is available."""

        current, state_valid, state_age = self._coerce_state(current_angles)
        try:
            dt = float(dt)
        except (TypeError, ValueError):
            return self._failsafe("invalid_dt", current)
        if (
            not math.isfinite(dt)
            or dt <= 0.0
            or (self.config.max_dt > 0.0 and dt > self.config.max_dt)
            or not state_valid
            or not math.isfinite(state_age)
            or state_age > self.config.target_timeout
        ):
            return self._failsafe("invalid_dt", current)
        if roll_error is None:
            roll_error = self.config.horizon_roll - current[2]
        rates = np.array(
            [
                self.config.yaw_gain * float(yaw_error),
                self.config.pitch_gain * float(pitch_error),
                self.config.roll_gain * float(roll_error),
            ],
            dtype=float,
        )
        if not np.all(np.isfinite(rates)):
            return self._failsafe("invalid_error", current)
        rates = _clip_rate(rates, self.config.max_rate)
        angles = self._clamp_angles(current + rates * dt)
        rates = self._zero_outward_limit_rates(angles, rates)
        self._angles = angles.copy()
        return GimbalSetpoint(angles=angles, rates=rates, valid=True)

    def _coerce_state(
        self,
        state: Optional[Union[GimbalState, ArrayLike, Mapping[str, Any]]],
    ) -> tuple[np.ndarray, bool, float]:
        if state is None:
            return self._angles.copy(), True, 0.0
        if isinstance(state, GimbalState):
            self._angles = state.angles.copy()
            return state.angles.copy(), bool(state.valid), float(state.age)
        if isinstance(state, Mapping):
            angles = state.get("angles", state.get("position", None))
            if angles is None:
                return self._angles.copy(), False, math.inf
            try:
                angles = _vec3(angles, "angles")
            except ValueError:
                return self._angles.copy(), False, math.inf
            try:
                age = float(state.get("age", 0.0))
            except (TypeError, ValueError):
                return self._angles.copy(), False, math.inf
            return angles, bool(state.get("valid", state.get("is_valid", True))), age
        try:
            angles = _vec3(state, "angles")
        except (TypeError, ValueError):
            return self._angles.copy(), False, math.inf
        return angles, True, 0.0

    def _apply_deadzone(self, errors: np.ndarray) -> np.ndarray:
        if np.isscalar(self.config.deadzone):
            mask = np.abs(errors) <= float(self.config.deadzone)
        else:
            mask = np.abs(errors) <= np.asarray(self.config.deadzone, dtype=float)
        result = errors.copy()
        result[mask] = 0.0
        return result

    def _clamp_angles(self, angles: np.ndarray) -> np.ndarray:
        result = angles.copy()
        result[0] = np.clip(result[0], *self.config.yaw_limits)
        result[1] = np.clip(result[1], *self.config.pitch_limits)
        result[2] = np.clip(result[2], *self.config.roll_limits)
        return result

    def _zero_outward_limit_rates(self, angles: np.ndarray, rates: np.ndarray) -> np.ndarray:
        result = rates.copy()
        limits = (self.config.yaw_limits, self.config.pitch_limits, self.config.roll_limits)
        for index, (lower, upper) in enumerate(limits):
            if angles[index] <= lower + 1e-9 and result[index] < 0.0:
                result[index] = 0.0
            if angles[index] >= upper - 1e-9 and result[index] > 0.0:
                result[index] = 0.0
        return result

    def _failsafe(self, reason: str, current: Optional[np.ndarray] = None) -> GimbalSetpoint:
        if current is None:
            current = self._angles.copy()
        current = self._clamp_angles(_vec3(current, "angles"))
        self._angles = current.copy()
        if self.config.failsafe_mode == "zero":
            # Zero mode still emits a valid angle command, but removes motion.
            return GimbalSetpoint(angles=current, rates=np.zeros(3), valid=False, failsafe=True, reason=reason)
        return GimbalSetpoint(angles=current, rates=np.zeros(3), valid=False, failsafe=True, reason=reason)


__all__ = [
    "GimbalConfig",
    "GimbalControllerConfig",
    "GimbalController",
    "GimbalSetpoint",
    "GimbalState",
]
