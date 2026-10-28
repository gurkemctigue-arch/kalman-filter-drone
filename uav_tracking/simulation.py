"""Deterministic, middleware-free synthetic closed-loop demonstration.

The simulator is intentionally small: it exercises the same target manager,
3-D filter, follow controller, and gimbal controller used by later ROS 2
adapters. It is useful on a machine that has Python and NumPy but no ROS 2.
Gazebo truth is represented only by the synthetic plant; association receives
the noisy detections, never an actor identifier.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from typing import Iterable

import numpy as np

from .control import (
    FollowConfig,
    FollowController,
    GimbalController,
    GimbalState,
    TargetState,
    VehicleState,
)
from .core import Detection, TargetManager, TargetMode, TargetStatus


@dataclass
class DemoResult:
    target_class: str
    mode: str
    steps: int
    completed_steps: int
    mean_distance_error: float
    mean_height_error: float
    max_speed_command: float
    reacquired_frames: int
    ambiguous_frames: int
    lost_frames: int
    gimbal_limit_hits: int

    def as_dict(self) -> dict[str, object]:
        return {
            "target_class": self.target_class,
            "mode": self.mode,
            "steps": self.steps,
            "completed_steps": self.completed_steps,
            "mean_distance_error_m": round(self.mean_distance_error, 6),
            "mean_height_error_m": round(self.mean_height_error, 6),
            "max_speed_command_mps": round(self.max_speed_command, 6),
            "reacquired_frames": self.reacquired_frames,
            "ambiguous_frames": self.ambiguous_frames,
            "lost_frames": self.lost_frames,
            "gimbal_limit_hits": self.gimbal_limit_hits,
        }


def _bbox_from_world(position: np.ndarray, *, width: float = 28.0) -> tuple[float, float, float, float]:
    """Produce a deterministic image box from a synthetic world position."""

    u = 320.0 + 55.0 * float(position[0]) / max(1.0, float(position[2]))
    v = 240.0 - 45.0 * float(position[2]) / max(1.0, abs(float(position[1])) + 5.0)
    return (u - width / 2.0, v - width, u + width / 2.0, v)


def _detection(position: np.ndarray, class_name: str, timestamp: float, rng: np.random.Generator, *, noise: float = 0.03, x_offset: float = 0.0) -> Detection:
    noisy = np.asarray(position, dtype=float) + rng.normal(0.0, noise, 3)
    noisy[2] = max(0.5, noisy[2])
    noisy[0] += x_offset
    return Detection(
        bbox=_bbox_from_world(noisy, width=28.0),
        class_id=class_name,
        confidence=0.92,
        timestamp=timestamp,
        position_3d=noisy,
        metadata={"source": "synthetic_sensor"},
    )


def run_demo(
    *,
    mode: TargetMode | str = TargetMode.AUTO_UNIQUE,
    target_class: str = "person",
    steps: int = 120,
    seed: int = 7,
    dt: float = 0.05,
    include_distractor: bool | None = None,
) -> DemoResult:
    """Run a deterministic noisy target-following scenario."""

    if steps <= 0 or dt <= 0.0:
        raise ValueError("steps and dt must be positive")
    mode = TargetMode(mode)
    rng = np.random.default_rng(seed)
    if include_distractor is None:
        include_distractor = mode == TargetMode.LOCKED_TARGET

    manager = TargetManager(
        mode=mode,
        target_class=target_class,
        min_hits=1,
        max_coast_frames=8,
        max_lost_frames=20,
        association_iou_threshold=0.0,
        association_max_distance=3.0,
    )
    if mode == TargetMode.LOCKED_TARGET:
        manager.lock_detection(0)

    controller = FollowController(
        config=FollowConfig(
            mode="velocity",
            desired_distance=5.0,
            desired_height=2.0,
            position_gain=np.array([0.8, 0.8, 0.9]),
            feedforward_gain=0.35,
            max_speed=2.5,
            max_acceleration=4.0,
            target_timeout=0.7,
            vehicle_timeout=0.7,
        )
    )
    gimbal = GimbalController()
    vehicle = np.array([0.0, -7.5, 2.0], dtype=float)
    vehicle_velocity = np.zeros(3, dtype=float)
    gimbal_angles = np.zeros(3, dtype=float)
    distance_errors: list[float] = []
    height_errors: list[float] = []
    max_speed = 0.0
    reacquired = ambiguous = lost = limit_hits = 0
    completed = 0

    for step in range(steps):
        timestamp = step * dt
        target = np.array(
            [0.75 * np.sin(timestamp * 0.55), 0.55 * timestamp, 1.0 + 0.08 * np.sin(timestamp * 0.7)],
            dtype=float,
        )
        target_velocity = np.array(
            [0.75 * 0.55 * np.cos(timestamp * 0.55), 0.55, 0.08 * 0.7 * np.cos(timestamp * 0.7)],
            dtype=float,
        )
        detections: list[Detection] = []
        occluded = 45 <= step < 53
        if not occluded:
            detections.append(_detection(target, target_class, timestamp, rng))
            if include_distractor:
                distractor = target + np.array([2.1, 0.2, 0.05])
                detections.append(_detection(distractor, target_class, timestamp, rng, x_offset=3.0))

        result = manager.update_with_result(detections, timestamp=timestamp)
        if result.status == TargetStatus.REACQUIRED:
            reacquired += 1
        elif result.status == TargetStatus.AMBIGUOUS:
            ambiguous += 1
        elif result.status == TargetStatus.LOST:
            lost += 1

        if result.target is None or result.target.position_3d is None:
            target_state = TargetState(position=np.zeros(3), velocity=np.zeros(3), valid=False, age=1.0)
        else:
            target_state = TargetState(
                position=result.target.position_3d,
                velocity=result.target.velocity_3d or np.zeros(3),
                valid=result.status not in {TargetStatus.LOST, TargetStatus.AMBIGUOUS},
                age=0.0 if result.target._matched_this_frame else min(1.0, result.target.missed * dt),
                covariance=result.target.covariance_3d,
                confidence=result.target.confidence,
            )
        vehicle_state = VehicleState(position=vehicle, velocity=vehicle_velocity, valid=True, yaw=0.0)
        command = controller.update(target_state, vehicle_state, dt=dt)
        vehicle_velocity = command.value if command.valid and not command.failsafe else np.zeros(3)
        vehicle += vehicle_velocity * dt

        if result.target is not None and result.target.position_3d is not None:
            estimated = np.asarray(result.target.position_3d)
            horizontal_distance = float(np.linalg.norm(estimated[:2] - vehicle[:2]))
            distance_errors.append(abs(horizontal_distance - 5.0))
            height_errors.append(abs((estimated[2] - vehicle[2]) - (-1.0)))
            line_of_sight = estimated - vehicle
            gimbal_command = gimbal.update(line_of_sight, state=GimbalState(gimbal_angles), dt=dt)
            gimbal_angles = gimbal_command.angles
            limit_hits += int(np.any(np.isclose(np.abs(gimbal_angles), [np.pi, np.pi / 2.0, np.pi])))
            completed += 1
        max_speed = max(max_speed, float(np.linalg.norm(vehicle_velocity)))

    return DemoResult(
        target_class=target_class,
        mode=mode.value,
        steps=steps,
        completed_steps=completed,
        mean_distance_error=float(np.mean(distance_errors)) if distance_errors else float("inf"),
        mean_height_error=float(np.mean(height_errors)) if height_errors else float("inf"),
        max_speed_command=max_speed,
        reacquired_frames=reacquired,
        ambiguous_frames=ambiguous,
        lost_frames=lost,
        gimbal_limit_hits=limit_hits,
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=[mode.value for mode in TargetMode], default=TargetMode.AUTO_UNIQUE.value)
    parser.add_argument("--target-class", choices=["person", "car"], default="person")
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = run_demo(mode=args.mode, target_class=args.target_class, steps=args.steps, seed=args.seed)
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
