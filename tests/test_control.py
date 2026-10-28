"""Safety and interface tests for the portable control primitives."""

from __future__ import annotations

import unittest

import numpy as np

from uav_tracking.control import (
    FollowConfig,
    FollowController,
    GimbalConfig,
    GimbalController,
    TargetState,
    VehicleState,
)


class FollowControllerTests(unittest.TestCase):
    def test_follow_heading_faces_world_target_for_both_modes(self) -> None:
        for mode in ("velocity", "position"):
            controller = FollowController(config=FollowConfig(mode=mode))
            output = controller.update(TargetState(position=[0, 10, 2]), VehicleState(position=[0, 0, 1]), dt=0.1)
            self.assertAlmostEqual(output.yaw, np.pi / 2)

    def test_velocity_mode_outputs_only_velocity_and_respects_limit(self) -> None:
        controller = FollowController(config=FollowConfig(mode="velocity", max_speed=1.0, max_acceleration=100.0))
        output = controller.update(
            TargetState(position=[10, 0, 2], velocity=[0, 0, 0]),
            VehicleState(position=[0, 0, 0]),
            dt=0.1,
        )
        self.assertTrue(output.valid)
        self.assertIsNone(output.position)
        self.assertIsNotNone(output.velocity)
        self.assertLessEqual(float(np.linalg.norm(output.velocity)), 1.0 + 1e-9)

    def test_position_mode_outputs_only_position(self) -> None:
        controller = FollowController(config=FollowConfig(mode="position", desired_offset=[0, 0, 1]))
        output = controller.update(TargetState(position=[2, 3, 4]), VehicleState(position=[0, 0, 0]), dt=0.1)
        self.assertTrue(output.valid)
        self.assertIsNone(output.velocity)
        np.testing.assert_allclose(output.position, [2, 3, 5])

    def test_stale_target_emits_explicit_failsafe(self) -> None:
        controller = FollowController(config=FollowConfig(mode="velocity", target_timeout=0.1))
        output = controller.update(
            TargetState(position=[1, 0, 0], age=0.2), VehicleState(position=[0, 0, 0]), dt=0.1
        )
        self.assertTrue(output.failsafe)
        np.testing.assert_allclose(output.velocity, [0, 0, 0])

    def test_position_restart_ramps_reference_and_caps_lead_while_vehicle_is_held(self) -> None:
        controller = FollowController(config=FollowConfig(
            mode="position", slew_position=True, max_speed=1.5,
            max_acceleration=1.0, max_position_lead=0.8))
        target, vehicle = TargetState(position=[30, 0, 0]), VehicleState(position=[0, 0, 0])
        first = controller.update(target, vehicle, dt=0.05)
        self.assertIsNone(first.velocity)
        self.assertLessEqual(float(np.linalg.norm(first.position)), 1.0 * 0.05 ** 2 + 1e-12)
        for _ in range(200):
            command = controller.update(target, vehicle, dt=0.05)
            self.assertLessEqual(float(np.linalg.norm(command.position - vehicle.position)), 0.8 + 1e-12)
        self.assertGreater(float(command.position[0]), 0.5)

    def test_slewed_position_reference_can_follow_a_moving_target(self) -> None:
        controller = FollowController(config=FollowConfig(
            mode="position", slew_position=True, desired_distance=5.0,
            position_gain=0.6, max_speed=1.5, max_acceleration=1.0, max_position_lead=1.0))
        vehicle_position = np.zeros(3)
        dt = 0.05
        # Independent first-order position plant: a dt-sized offset from the
        # vehicle each tick cannot achieve the target's 0.5 m/s speed here.
        for step in range(400):
            target = TargetState(position=[10 + 0.5 * step * dt, 0, 0], velocity=[0.5, 0, 0])
            command = controller.update(target, VehicleState(position=vehicle_position), dt=dt)
            velocity = np.clip(command.position - vehicle_position, -2.0, 2.0)
            vehicle_position += velocity * dt
        distance_error = target.position[0] - vehicle_position[0] - 5.0
        self.assertLess(abs(float(distance_error)), 1.0)
        self.assertGreater(float(velocity[0]), 0.4)

    def test_position_restart_discards_reference_from_before_loss(self) -> None:
        controller = FollowController(config=FollowConfig(
            mode="position", slew_position=True, max_speed=1.5, max_acceleration=1.0))
        for _ in range(20):
            controller.update(TargetState(position=[30, 0, 0]), VehicleState(position=[0, 0, 0]), dt=0.05)
        held = VehicleState(position=[10, 2, 3])
        failure = controller.update(TargetState(position=[30, 0, 0], valid=False), held, dt=0.05)
        self.assertTrue(failure.failsafe)
        restarted = controller.update(TargetState(position=[30, 2, 3]), held, dt=0.05)
        self.assertIsNone(restarted.velocity)
        self.assertLessEqual(float(np.linalg.norm(restarted.position - held.position)), 0.0025 + 1e-12)

    def test_lead_projection_does_not_inject_a_large_reverse_slew_rate(self) -> None:
        controller = FollowController(config=FollowConfig(
            mode="position", slew_position=True, max_speed=1.5,
            max_acceleration=1.0, max_position_lead=0.8))
        target = TargetState(position=[30, 0, 0])
        for _ in range(200):
            controller.update(target, VehicleState(position=[0, 0, 0]), dt=0.05)
        drifted = VehicleState(position=[-0.02, 0, 0])
        projected = controller.update(target, drifted, dt=0.05)
        self.assertLessEqual(float(projected.position[0] - drifted.position[0]), 0.8 + 1e-12)
        following = controller.update(target, drifted, dt=0.05)
        self.assertGreaterEqual(float(following.position[0]), float(projected.position[0]) - 1e-12)


class GimbalControllerTests(unittest.TestCase):
    def test_yaw_pitch_follow_and_roll_horizon(self) -> None:
        controller = GimbalController(GimbalConfig(horizon_roll=0.1, max_rate=[10, 10, 10]))
        output = controller.update([1, 1, 1], dt=0.1)
        self.assertTrue(output.valid)
        self.assertGreater(output.yaw, 0.0)
        self.assertGreater(output.pitch, 0.0)
        self.assertAlmostEqual(output.roll, 0.0, delta=0.1)

    def test_invalid_line_of_sight_holds_position(self) -> None:
        controller = GimbalController()
        output = controller.update([0, 0, 0])
        self.assertTrue(output.failsafe)
        np.testing.assert_allclose(output.rates, [0, 0, 0])


if __name__ == "__main__":
    unittest.main()
