"""Deterministic paired estimator experiments for the simulation-first study.

This module deliberately uses the same synthetic observations for all four
estimators.  It is a state-estimation baseline, not a replacement for the
later ROS bag and PX4 closed-loop experiments.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

import numpy as np

from .core import ConstantVelocityKalman3D


ESTIMATORS = ("raw", "ema", "fixed_kf", "adaptive_kf")


@dataclass(frozen=True)
class EstimatorMetrics:
    estimator: str
    target_class: str
    seed: int
    steps: int
    position_rmse_m: float
    velocity_rmse_mps: float
    position_p95_m: float
    rejected_measurements: int
    missing_measurements: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _truth(timestamp: float) -> tuple[np.ndarray, np.ndarray]:
    position = np.array(
        [0.8 * np.sin(0.45 * timestamp), 0.55 * timestamp, 1.0 + 0.12 * np.sin(0.7 * timestamp)],
        dtype=float,
    )
    velocity = np.array(
        [0.8 * 0.45 * np.cos(0.45 * timestamp), 0.55, 0.12 * 0.7 * np.cos(0.7 * timestamp)],
        dtype=float,
    )
    return position, velocity


def _observations(steps: int, dt: float, rng: np.random.Generator) -> list[tuple[float, np.ndarray | None, float, float]]:
    """Create one shared noisy measurement sequence.

    The tuple contains timestamp, measurement (or ``None``), depth-valid
    fraction and depth spread.  Every estimator receives this exact list.
    """

    result = []
    for index in range(steps):
        timestamp = index * dt
        position, _ = _truth(timestamp)
        missing = 22 <= index < 27 or index % 47 == 0
        quality = float(np.clip(0.55 + 0.4 * rng.random(), 0.05, 1.0))
        spread = float(0.02 + 0.12 * (1.0 - quality))
        measurement = None if missing else position + rng.normal(0.0, [0.025, 0.025, 0.08], 3)
        result.append((timestamp, measurement, quality, spread))
    return result


def _estimate(kind: str, observations: Sequence[tuple[float, np.ndarray | None, float, float]], dt: float) -> tuple[np.ndarray, np.ndarray, int]:
    positions: list[np.ndarray] = []
    velocities: list[np.ndarray] = []
    rejected = 0
    last_position = np.zeros(3, dtype=float)
    previous_position: np.ndarray | None = None
    filter_: ConstantVelocityKalman3D | None = None

    if kind in {"fixed_kf", "adaptive_kf"}:
        filter_ = ConstantVelocityKalman3D(
            process_acceleration_std=0.35,
            measurement_noise_std=[0.025, 0.025, 0.08],
            initial_position_covariance=0.1,
            initial_velocity_covariance=1.0,
            adaptive_measurement_noise=kind == "adaptive_kf",
            default_dt=dt,
        )

    ema_position: np.ndarray | None = None
    alpha = 0.35
    for timestamp, measurement, quality, spread in observations:
        if kind in {"fixed_kf", "adaptive_kf"}:
            assert filter_ is not None
            if not filter_.initialized:
                if measurement is None:
                    estimate_position = last_position.copy()
                    estimate_velocity = np.zeros(3, dtype=float)
                else:
                    filter_.initialize(measurement, timestamp=timestamp)
                    estimate_position = filter_.position
                    estimate_velocity = filter_.velocity
            else:
                filter_.predict(timestamp=timestamp)
                if measurement is not None:
                    accepted = filter_.update(
                        measurement,
                        timestamp=timestamp,
                        depth_stats={"valid_fraction": quality, "std": spread},
                        confidence=0.9,
                    )
                    if not accepted:
                        rejected += 1
                estimate_position = filter_.position
                estimate_velocity = filter_.velocity
        else:
            if measurement is not None:
                if kind == "ema":
                    ema_position = measurement.copy() if ema_position is None else alpha * measurement + (1.0 - alpha) * ema_position
                    estimate_position = ema_position.copy()
                else:
                    estimate_position = measurement.copy()
                if previous_position is None:
                    estimate_velocity = np.zeros(3, dtype=float)
                else:
                    estimate_velocity = (estimate_position - previous_position) / dt
                previous_position = estimate_position.copy()
            else:
                estimate_position = last_position.copy()
                estimate_velocity = np.zeros(3, dtype=float)

        last_position = estimate_position.copy()
        positions.append(estimate_position)
        velocities.append(estimate_velocity)

    return np.asarray(positions), np.asarray(velocities), rejected


def run_estimator_benchmark(
    *,
    target_class: str = "person",
    seeds: Iterable[int] = range(10),
    steps: int = 120,
    dt: float = 0.05,
) -> list[EstimatorMetrics]:
    """Run paired raw/EMA/fixed-KF/adaptive-KF state-estimation trials."""

    if target_class not in {"person", "car"}:
        raise ValueError("target_class must be 'person' or 'car'")
    if steps <= 0 or dt <= 0.0:
        raise ValueError("steps and dt must be positive")
    metrics: list[EstimatorMetrics] = []
    for seed in seeds:
        seed = int(seed)
        observations = _observations(steps, dt, np.random.default_rng(seed))
        truth_positions = np.asarray([_truth(index * dt)[0] for index in range(steps)])
        truth_velocities = np.asarray([_truth(index * dt)[1] for index in range(steps)])
        missing_count = sum(measurement is None for _, measurement, _, _ in observations)
        for estimator in ESTIMATORS:
            positions, velocities, rejected = _estimate(estimator, observations, dt)
            position_errors = np.linalg.norm(positions - truth_positions, axis=1)
            velocity_errors = np.linalg.norm(velocities - truth_velocities, axis=1)
            metrics.append(
                EstimatorMetrics(
                    estimator=estimator,
                    target_class=target_class,
                    seed=seed,
                    steps=steps,
                    position_rmse_m=float(np.sqrt(np.mean(position_errors**2))),
                    velocity_rmse_mps=float(np.sqrt(np.mean(velocity_errors**2))),
                    position_p95_m=float(np.percentile(position_errors, 95)),
                    rejected_measurements=int(rejected),
                    missing_measurements=int(missing_count),
                )
            )
    return metrics

