"""Pure Python follow-controller primitives.

The module deliberately contains no ROS, PX4, or simulator types.  State is
expressed in one common Cartesian frame (normally ``map``/``odom``), while a
later adapter can translate the resulting setpoint to a vehicle-specific
message and frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence, Union

import numpy as np


ArrayLike = Union[Sequence[float], np.ndarray]


def _vector3(value: ArrayLike, name: str) -> np.ndarray:
    """Return a finite three-vector, copying caller-owned data."""

    array = np.asarray(value, dtype=float)
    if array.shape != (3,):
        raise ValueError(f"{name} must have shape (3,), got {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    return array.copy()


def _scalar_or_vector3(value: Union[float, ArrayLike], name: str) -> Union[float, np.ndarray]:
    """Normalize a scalar or per-axis positive limit/gain."""

    if np.isscalar(value):
        number = float(value)
        if math.isnan(number) or number < 0.0:
            raise ValueError(f"{name} must be a non-negative number")
        return number
    array = np.asarray(value, dtype=float)
    if array.shape != (3,) or np.any(np.isnan(array)) or np.any(array < 0.0):
        raise ValueError(f"{name} must be a non-negative scalar or shape-(3,) vector")
    return array.copy()


def _optional_vector3(value: Optional[ArrayLike], name: str) -> Optional[np.ndarray]:
    if value is None:
        return None
    return _vector3(value, name)


def _finite_nonnegative(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return number


def _as_limit(value: Union[float, np.ndarray], vector: np.ndarray) -> np.ndarray:
    """Apply scalar (Euclidean) or per-axis limits to a vector."""

    if np.isscalar(value):
        limit = float(value)
        if not math.isfinite(limit):
            return vector.copy()
        if limit <= 0.0:
            return np.zeros(3, dtype=float)
        norm = float(np.linalg.norm(vector))
        if norm > limit:
            return vector * (limit / norm)
        return vector.copy()

    limits = np.asarray(value, dtype=float)
    if limits.shape != (3,):
        raise ValueError("vector limit must have shape (3,)")
    result = vector.copy()
    finite = np.isfinite(limits)
    result[finite] = np.clip(result[finite], -limits[finite], limits[finite])
    result[~finite] = vector[~finite]
    return result


def _clip_delta(delta: np.ndarray, limit: Union[float, np.ndarray]) -> np.ndarray:
    """Limit a change vector, using a norm for scalar limits."""

    return _as_limit(limit, delta)


def _read_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


@dataclass
class TargetState:
    """Estimated target state in the controller's common Cartesian frame."""

    position: ArrayLike
    velocity: ArrayLike = field(default_factory=lambda: np.zeros(3))
    valid: bool = True
    age: float = 0.0
    covariance: Optional[np.ndarray] = None
    confidence: float = 1.0
    frame: str = "world"
    timestamp: Optional[float] = None
    # ``is_valid`` is accepted as a compatibility alias for message adapters.
    is_valid: Optional[bool] = None

    def __post_init__(self) -> None:
        self.position = _vector3(self.position, "position")
        self.velocity = _vector3(self.velocity, "velocity")
        if self.is_valid is not None:
            self.valid = bool(self.is_valid)
        self.age = _finite_nonnegative(self.age, "age")
        self.confidence = float(self.confidence)
        if not math.isfinite(self.confidence):
            raise ValueError("confidence must be finite")
        if self.covariance is not None:
            covariance = np.asarray(self.covariance, dtype=float)
            if covariance.shape not in ((3, 3), (6, 6)):
                raise ValueError("covariance must have shape (3, 3) or (6, 6)")
            if not np.all(np.isfinite(covariance)):
                raise ValueError("covariance must contain only finite values")
            self.covariance = covariance.copy()


@dataclass
class VehicleState:
    """Estimated vehicle state in the same Cartesian frame as ``TargetState``."""

    position: ArrayLike
    velocity: ArrayLike = field(default_factory=lambda: np.zeros(3))
    yaw: float = 0.0
    valid: bool = True
    age: float = 0.0
    frame: str = "world"
    timestamp: Optional[float] = None
    heading: Optional[float] = None
    is_valid: Optional[bool] = None

    def __post_init__(self) -> None:
        self.position = _vector3(self.position, "position")
        self.velocity = _vector3(self.velocity, "velocity")
        if self.heading is not None:
            self.yaw = float(self.heading)
        self.yaw = float(self.yaw)
        if not math.isfinite(self.yaw):
            raise ValueError("yaw must be finite")
        if self.is_valid is not None:
            self.valid = bool(self.is_valid)
        self.age = _finite_nonnegative(self.age, "age")


@dataclass
class FollowConfig:
    """Parameters for :class:`FollowController`.

    ``desired_offset`` is expressed in the common world frame.  If
    ``desired_distance`` is set, its horizontal component supersedes the
    horizontal offset and keeps the vehicle on its current side of the target.
    ``desired_height`` is a target-relative z offset.
    """

    mode: str = "velocity"
    desired_offset: ArrayLike = field(default_factory=lambda: np.zeros(3))
    desired_distance: Optional[float] = None
    desired_height: Optional[float] = None
    position_gain: Union[float, ArrayLike] = 1.0
    feedforward_gain: Union[float, ArrayLike] = 1.0
    integral_gain: Union[float, ArrayLike] = 0.0
    integral_limit: Union[float, ArrayLike] = 2.0
    deadzone: Union[float, ArrayLike] = 0.0
    max_speed: Union[float, ArrayLike] = 2.0
    max_acceleration: Union[float, ArrayLike] = 3.0
    target_timeout: float = 0.5
    vehicle_timeout: float = 0.5
    min_confidence: float = 0.0
    max_dt: float = 0.5
    failsafe_mode: str = "hold"
    slew_position: bool = False
    max_position_lead: Union[float, ArrayLike] = 1.0

    def __post_init__(self) -> None:
        self.mode = str(self.mode).lower()
        if self.mode not in {"velocity", "position"}:
            raise ValueError("mode must be 'velocity' or 'position'")
        self.desired_offset = _vector3(self.desired_offset, "desired_offset")
        if self.desired_distance is not None:
            self.desired_distance = _finite_nonnegative(self.desired_distance, "desired_distance")
        if self.desired_height is not None and not math.isfinite(float(self.desired_height)):
            raise ValueError("desired_height must be finite")
        self.position_gain = _scalar_or_vector3(self.position_gain, "position_gain")
        self.feedforward_gain = _scalar_or_vector3(self.feedforward_gain, "feedforward_gain")
        self.integral_gain = _scalar_or_vector3(self.integral_gain, "integral_gain")
        self.integral_limit = _scalar_or_vector3(self.integral_limit, "integral_limit")
        self.deadzone = _scalar_or_vector3(self.deadzone, "deadzone")
        self.max_speed = _scalar_or_vector3(self.max_speed, "max_speed")
        self.max_acceleration = _scalar_or_vector3(self.max_acceleration, "max_acceleration")
        self.max_position_lead = _scalar_or_vector3(self.max_position_lead, "max_position_lead")
        self.target_timeout = _finite_nonnegative(self.target_timeout, "target_timeout")
        self.vehicle_timeout = _finite_nonnegative(self.vehicle_timeout, "vehicle_timeout")
        self.max_dt = _finite_nonnegative(self.max_dt, "max_dt")
        self.min_confidence = float(self.min_confidence)
        if not math.isfinite(self.min_confidence):
            raise ValueError("min_confidence must be finite")
        self.failsafe_mode = str(self.failsafe_mode).lower()
        if self.failsafe_mode not in {"hold", "zero"}:
            raise ValueError("failsafe_mode must be 'hold' or 'zero'")


# A shorter alias is convenient for callers that use the conventional name.
FollowControllerConfig = FollowConfig


@dataclass
class FollowSetpoint:
    """Controller output.

    For a healthy output exactly one of ``position`` and ``velocity`` is
    populated.  A failsafe output also preserves the requested mode and marks
    ``failsafe=True`` so an adapter cannot mistake a hold command for tracking.
    """

    mode: str
    position: Optional[np.ndarray] = None
    velocity: Optional[np.ndarray] = None
    yaw: Optional[float] = None
    yaw_rate: Optional[float] = None
    valid: bool = True
    failsafe: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        self.mode = str(self.mode).lower()
        if self.mode not in {"velocity", "position"}:
            raise ValueError("setpoint mode must be 'velocity' or 'position'")
        if self.position is not None:
            self.position = _vector3(self.position, "position")
        if self.velocity is not None:
            self.velocity = _vector3(self.velocity, "velocity")
        if self.position is not None and self.velocity is not None:
            raise ValueError("a setpoint cannot contain both position and velocity")
        if not self.failsafe and self.position is None and self.velocity is None:
            raise ValueError("a healthy setpoint must contain position or velocity")
        if self.yaw is not None and not math.isfinite(float(self.yaw)):
            raise ValueError("yaw must be finite")
        if self.yaw_rate is not None and not math.isfinite(float(self.yaw_rate)):
            raise ValueError("yaw_rate must be finite")

    @property
    def value(self) -> np.ndarray:
        """Return the active vector, useful to generic adapters."""

        value = self.velocity if self.mode == "velocity" else self.position
        if value is None:
            return np.zeros(3, dtype=float)
        return value.copy()

    @property
    def is_failsafe(self) -> bool:
        return self.failsafe

    @property
    def control_mode(self) -> str:
        """Alias used by transport adapters and telemetry code."""

        return self.mode

    @property
    def position_setpoint(self) -> Optional[np.ndarray]:
        return None if self.position is None else self.position.copy()

    @property
    def velocity_setpoint(self) -> Optional[np.ndarray]:
        return None if self.velocity is None else self.velocity.copy()


def _gain_product(gain: Union[float, np.ndarray], vector: np.ndarray) -> np.ndarray:
    if np.isscalar(gain):
        return float(gain) * vector
    return np.asarray(gain, dtype=float) * vector


class FollowController:
    """Generate bounded position or velocity follow setpoints.

    The controller is intentionally an outer-loop controller.  It never emits
    attitude, thrust, or motor commands; PX4 (or another autopilot adapter)
    remains responsible for those inner loops.
    """

    def __init__(
        self,
        mode: Optional[str] = None,
        config: Optional[Union[FollowConfig, Mapping[str, Any]]] = None,
        **overrides: Any,
    ) -> None:
        # ``control_mode`` is accepted as a readable alias in integration code.
        if "control_mode" in overrides:
            mode = overrides.pop("control_mode")
        if config is None:
            values: dict[str, Any] = {"mode": mode or "velocity"}
            values.update(overrides)
            self.config = FollowConfig(**values)
        elif isinstance(config, FollowConfig):
            values = dict(config.__dict__)
            if mode is not None:
                values["mode"] = mode
            values.update(overrides)
            self.config = FollowConfig(**values)
        elif isinstance(config, Mapping):
            values = dict(config)
            values.setdefault("mode", mode or "velocity")
            values.update(overrides)
            self.config = FollowConfig(**values)
        else:
            raise TypeError("config must be FollowConfig, a mapping, or None")

        self._integral = np.zeros(3, dtype=float)
        self._last_velocity = np.zeros(3, dtype=float)
        self._last_position: Optional[np.ndarray] = None

    @property
    def mode(self) -> str:
        return self.config.mode

    def set_mode(self, mode: str) -> None:
        mode = str(mode).lower()
        if mode not in {"velocity", "position"}:
            raise ValueError("mode must be 'velocity' or 'position'")
        if mode != self.config.mode:
            self.config.mode = mode
            self.reset()

    def reset(self) -> None:
        self._integral.fill(0.0)
        self._last_velocity.fill(0.0)
        self._last_position = None

    def update(
        self,
        target: Union[TargetState, Mapping[str, Any], Any],
        vehicle: Union[VehicleState, Mapping[str, Any], Any],
        dt: float = 0.02,
        mode: Optional[str] = None,
    ) -> FollowSetpoint:
        """Compute one setpoint and update controller state.

        Invalid states, stale measurements, non-finite values, and invalid time
        steps all produce an explicit bounded failsafe output.
        """

        if mode is not None:
            self.set_mode(mode)
        vehicle_state = self._coerce_vehicle(vehicle)
        try:
            dt = float(dt)
        except (TypeError, ValueError):
            return self._failsafe(vehicle_state, None, "invalid_dt")
        if not math.isfinite(dt) or dt <= 0.0 or (self.config.max_dt > 0 and dt > self.config.max_dt):
            return self._failsafe(vehicle_state, None, "invalid_dt")

        target_state = self._coerce_target(target)
        if target_state is None or vehicle_state is None:
            return self._failsafe(vehicle_state, None, "invalid_state")
        if not self._state_is_usable(target_state, vehicle_state):
            return self._failsafe(vehicle_state, None, self._invalid_reason(target_state, vehicle_state))

        desired = self._desired_position(target_state, vehicle_state)
        error = desired - vehicle_state.position
        error = self._apply_deadzone(error)
        if self.config.mode == "velocity":
            setpoint = self._velocity_setpoint(target_state, vehicle_state, error, dt)
        else:
            setpoint = self._position_setpoint(target_state, desired, vehicle_state, dt)
        horizontal = target_state.position[:2] - vehicle_state.position[:2]
        setpoint.yaw = (
            math.atan2(float(horizontal[1]), float(horizontal[0]))
            if np.linalg.norm(horizontal) > 1e-6 else vehicle_state.yaw
        )
        return setpoint

    # Familiar aliases for control-loop code.
    compute = update
    step = update

    def _coerce_target(self, value: Any) -> Optional[TargetState]:
        if isinstance(value, TargetState):
            return value
        position = _read_field(value, "position", None)
        if position is None:
            return None
        try:
            return TargetState(
                position=position,
                velocity=_read_field(value, "velocity", np.zeros(3)),
                valid=_read_field(value, "valid", _read_field(value, "is_valid", True)),
                age=_read_field(value, "age", 0.0),
                covariance=_read_field(value, "covariance", None),
                confidence=_read_field(value, "confidence", 1.0),
                frame=_read_field(value, "frame", "world"),
                timestamp=_read_field(value, "timestamp", None),
            )
        except (TypeError, ValueError):
            return None

    def _coerce_vehicle(self, value: Any) -> Optional[VehicleState]:
        if isinstance(value, VehicleState):
            return value
        position = _read_field(value, "position", None)
        if position is None:
            return None
        try:
            return VehicleState(
                position=position,
                velocity=_read_field(value, "velocity", np.zeros(3)),
                yaw=_read_field(value, "yaw", _read_field(value, "heading", 0.0)),
                valid=_read_field(value, "valid", _read_field(value, "is_valid", True)),
                age=_read_field(value, "age", 0.0),
                frame=_read_field(value, "frame", "world"),
                timestamp=_read_field(value, "timestamp", None),
            )
        except (TypeError, ValueError):
            return None

    def _state_is_usable(self, target: TargetState, vehicle: VehicleState) -> bool:
        return bool(
            target.valid
            and vehicle.valid
            and target.age <= self.config.target_timeout
            and vehicle.age <= self.config.vehicle_timeout
            and target.confidence >= self.config.min_confidence
            and (
                not target.frame
                or not vehicle.frame
                or str(target.frame) == str(vehicle.frame)
            )
            and np.all(np.isfinite(target.position))
            and np.all(np.isfinite(target.velocity))
            and np.all(np.isfinite(vehicle.position))
            and np.all(np.isfinite(vehicle.velocity))
        )

    def _invalid_reason(self, target: TargetState, vehicle: VehicleState) -> str:
        if not target.valid or not vehicle.valid:
            return "invalid_state"
        if target.age > self.config.target_timeout:
            return "stale_target"
        if vehicle.age > self.config.vehicle_timeout:
            return "stale_vehicle"
        if target.confidence < self.config.min_confidence:
            return "low_confidence"
        if target.frame and vehicle.frame and str(target.frame) != str(vehicle.frame):
            return "frame_mismatch"
        return "unsafe_state"

    def _desired_position(self, target: TargetState, vehicle: VehicleState) -> np.ndarray:
        desired = target.position + self.config.desired_offset
        if self.config.desired_distance is not None:
            horizontal = vehicle.position[:2] - target.position[:2]
            norm = float(np.linalg.norm(horizontal))
            direction = horizontal / norm if norm > 1e-9 else np.array([1.0, 0.0])
            desired[:2] = target.position[:2] + direction * self.config.desired_distance
        if self.config.desired_height is not None:
            desired[2] = target.position[2] + float(self.config.desired_height)
        return desired

    def _apply_deadzone(self, error: np.ndarray) -> np.ndarray:
        deadzone = self.config.deadzone
        if np.isscalar(deadzone):
            mask = np.abs(error) <= float(deadzone)
        else:
            mask = np.abs(error) <= np.asarray(deadzone, dtype=float)
        result = error.copy()
        result[mask] = 0.0
        return result

    def _velocity_setpoint(
        self,
        target: TargetState,
        vehicle: VehicleState,
        error: np.ndarray,
        dt: float,
    ) -> FollowSetpoint:
        # Do not accumulate integral error while inside a deadzone.
        deadzone = self.config.deadzone
        if np.isscalar(deadzone):
            inside = np.abs(error) <= float(deadzone)
        else:
            inside = np.abs(error) <= np.asarray(deadzone, dtype=float)

        candidate_integral = self._integral + error * dt
        candidate_integral = _as_limit(self.config.integral_limit, candidate_integral)
        candidate_integral[inside] = 0.0

        feedforward = _gain_product(self.config.feedforward_gain, target.velocity)
        proportional = _gain_product(self.config.position_gain, error)
        integral_term = _gain_product(self.config.integral_gain, candidate_integral)
        unsaturated = feedforward + proportional + integral_term
        speed_limited = _as_limit(self.config.max_speed, unsaturated)

        # Component-wise conditional integration prevents windup while an
        # integral term is driving an already saturated output farther out.
        integral_enabled = (
            bool(np.any(np.asarray(self.config.integral_gain) != 0.0))
            if not np.isscalar(self.config.integral_gain)
            else float(self.config.integral_gain) != 0.0
        )
        if integral_enabled:
            saturated = np.abs(speed_limited - unsaturated) > 1e-12
            drives_outward = saturated & (np.sign(error) == np.sign(unsaturated))
            candidate_integral[drives_outward] = self._integral[drives_outward]
        self._integral = candidate_integral

        command = feedforward + proportional + _gain_product(self.config.integral_gain, self._integral)
        command = _as_limit(self.config.max_speed, command)
        command = self._apply_acceleration_limit(command, self._last_velocity, dt)
        self._last_velocity = command.copy()
        return FollowSetpoint(mode="velocity", velocity=command, valid=True)

    def _position_setpoint(
        self,
        target: TargetState,
        desired: np.ndarray,
        vehicle: VehicleState,
        dt: float,
    ) -> FollowSetpoint:
        if not self.config.slew_position:
            self._last_velocity.fill(0.0)
            self._last_position = desired.copy()
            return FollowSetpoint(mode="position", position=desired, valid=True)

        # Generate a moving position reference instead of jumping several
        # metres when tracking restarts. Integrating from the vehicle on every
        # tick would leave only a tiny dt-sized lead and prevent it catching a
        # moving target. Integrate the previous reference, with target velocity
        # feedforward, then bound its lead over the actual vehicle so it cannot
        # run away while the aircraft is held back.
        previous = self._last_position if self._last_position is not None else vehicle.position
        reference_error = self._apply_deadzone(desired - previous)
        velocity = (_gain_product(self.config.feedforward_gain, target.velocity)
                    + _gain_product(self.config.position_gain, reference_error))
        velocity = _as_limit(self.config.max_speed, velocity)
        velocity = self._apply_acceleration_limit(velocity, self._last_velocity, dt)
        proposed = previous + velocity * dt
        position = vehicle.position + _as_limit(self.config.max_position_lead, proposed - vehicle.position)
        # Keeping the reference close to a moving vehicle takes priority when
        # the lead and nominal slew bounds conflict (e.g. backward drift).
        # Do not feed an exceptional projection rate into the slew state.
        realized = _as_limit(self.config.max_speed, (position - previous) / dt)
        self._last_velocity = self._apply_acceleration_limit(realized, self._last_velocity, dt)
        self._last_position = position.copy()
        return FollowSetpoint(mode="position", position=position, valid=True)

    def _apply_acceleration_limit(self, command: np.ndarray, previous: np.ndarray, dt: float) -> np.ndarray:
        delta = command - previous
        acceleration = self.config.max_acceleration
        if np.isscalar(acceleration):
            if math.isfinite(float(acceleration)):
                delta = _clip_delta(delta, float(acceleration) * dt)
        else:
            acceleration = np.asarray(acceleration, dtype=float)
            if np.any(np.isfinite(acceleration)):
                delta = _clip_delta(delta, acceleration * dt)
        return previous + delta

    def _failsafe(
        self,
        vehicle: Optional[VehicleState],
        _unused: Optional[np.ndarray],
        reason: str,
    ) -> FollowSetpoint:
        if self.config.failsafe_mode == "hold" and vehicle is not None:
            self._last_position = vehicle.position.copy()
            self._last_velocity.fill(0.0)
            self._integral.fill(0.0)
            if self.config.mode == "position":
                return FollowSetpoint(
                    mode="position",
                    position=vehicle.position,
                    valid=False,
                    failsafe=True,
                    reason=reason,
                )
        self.reset()
        if self.config.mode == "position":
            position = vehicle.position if vehicle is not None else np.zeros(3)
            return FollowSetpoint(mode="position", position=position, valid=False, failsafe=True, reason=reason)
        return FollowSetpoint(mode="velocity", velocity=np.zeros(3), valid=False, failsafe=True, reason=reason)


__all__ = [
    "FollowConfig",
    "FollowControllerConfig",
    "FollowController",
    "FollowSetpoint",
    "TargetState",
    "VehicleState",
]
