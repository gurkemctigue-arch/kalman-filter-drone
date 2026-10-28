"""Geometric signs, physical assets, source-time TF and gimbal failsafes."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np

from uav_tracking.control.gimbal_geometry import (
    BodyYawReference, JOINT_NAMES, JOINT_LOWER, JOINT_UPPER, bounded_joint_command,
    camera_optical_quaternion, desired_joint_angles, ordered_joint_positions,
    quaternion_rotation, rotation_xyz,
)

ROOT = Path(__file__).resolve().parents[1]
BRINGUP = ROOT / "ros2_ws" / "src" / "uav_tracking_bringup"
sys.path.insert(0, str(BRINGUP))
from uav_tracking_bringup import flight_tf_node as flight_tf  # noqa: E402
from uav_tracking_bringup import gimbal_adapter_node as adapter  # noqa: E402


def stamp(seconds: float) -> NS:
    nanoseconds = round(seconds * 1e9)
    return NS(sec=nanoseconds // 1_000_000_000, nanosec=nanoseconds % 1_000_000_000)


def vec(x=0.0, y=0.0, z=0.0) -> NS:
    return NS(x=x, y=y, z=z)


class GeometryTests(unittest.TestCase):
    def test_neutral_matches_stage_one_optical_mount(self):
        np.testing.assert_allclose(camera_optical_quaternion([0, 0, 0]), flight_tf.optical_mount_quaternion(0.35), atol=1e-12)

    def test_yaw_left_and_pitch_down_have_physical_signs(self):
        forward = np.array([0.0, 0.0, 1.0])  # optical forward
        left = quaternion_rotation(camera_optical_quaternion([0.3, -0.35, 0])) @ forward
        down = quaternion_rotation(camera_optical_quaternion([0, 0.2, 0])) @ forward
        self.assertGreater(left[1], 0)
        self.assertLess(down[2], 0)
        self.assertAlmostEqual(math.atan2(-down[2], down[0]), 0.55)

    def test_body_roll_is_cancelled_at_straight_ahead_los(self):
        body_rotation = rotation_xyz(0.25, 0, 0)
        desired = desired_joint_angles([10, 0, 0], body_rotation)
        self.assertAlmostEqual(desired[2], -0.25)
        actual = body_rotation @ quaternion_rotation(camera_optical_quaternion(desired))
        self.assertAlmostEqual(actual[2, 0], 0.0, places=12)

    def test_general_yaw_pitch_roll_level_horizon_and_align_forward(self):
        body_rotation = rotation_xyz(0.18, -0.12, 0.4)
        los = np.array([8.0, 3.0, -2.0])
        desired = desired_joint_angles(los, body_rotation)
        camera = body_rotation @ quaternion_rotation(camera_optical_quaternion(desired))
        expected_forward = body_rotation @ los / np.linalg.norm(los)
        np.testing.assert_allclose(camera[:, 2], expected_forward, atol=1e-12)
        self.assertAlmostEqual(camera[2, 0], 0.0, places=12)

    def test_sideways_horizon_is_not_simple_negative_body_roll(self):
        body_rotation = rotation_xyz(0.3, -0.2, 0)
        los = [4.0, 6.0, -2.0]
        desired = desired_joint_angles(los, body_rotation)
        self.assertGreater(abs(float(desired[2]) + 0.3), 0.05)
        camera = body_rotation @ quaternion_rotation(camera_optical_quaternion(desired))
        self.assertAlmostEqual(camera[2, 0], 0.0, places=12)

    def test_hard_limits_and_independent_rate_limits(self):
        command, rates = bounded_joint_command([0, 0, 0], [10, -10, 10], 0.02)
        np.testing.assert_allclose(rates, [1, -0.8, 1])
        np.testing.assert_allclose(command, [0.02, -0.016, 0.02])
        for _ in range(200):
            command, _ = bounded_joint_command(command, [10, -10, 10], 0.02)
        np.testing.assert_allclose(command, [JOINT_UPPER[0], JOINT_LOWER[1], JOINT_UPPER[2]], atol=1e-5)

    def test_partial_duplicate_nan_feedback_is_rejected(self):
        for names, positions in ((JOINT_NAMES[:2], [0, 0]), (JOINT_NAMES, [0, math.nan, 0]),
                                 ([JOINT_NAMES[0]] * 3, [0, 0, 0]), (JOINT_NAMES, [0, 0])):
            with self.subTest(names=names, positions=positions), self.assertRaises(ValueError):
                ordered_joint_positions(names, positions)
        np.testing.assert_allclose(ordered_joint_positions(JOINT_NAMES[::-1], [0.3, 0.2, 0.1]), [0.1, 0.2, 0.3])


class FakeFloat64:
    def __init__(self):
        self.data = 0.0


class BodyYawReferenceTests(unittest.TestCase):
    def test_continuous_reference_accumulates_at_limited_rate(self):
        reference = BodyYawReference()
        previous = 0.0
        for _ in range(80):
            # An independently following body stays behind the reference.
            yaw, rate, _ = reference.update(previous - 0.03, 0.6, 0.02, "target-a")
            self.assertLessEqual(abs(yaw - previous), 0.10 * 0.02 + 1e-12 if previous else 0.05)
            self.assertAlmostEqual(rate, 0.10)
            previous = yaw
        self.assertGreater(yaw, 0.12)

    def test_reverse_and_variable_timestep_do_not_exceed_rate(self):
        reference = BodyYawReference()
        previous, _, _ = reference.update(0, 0.6, 0.02, "a")
        for dt in (0.01, 0.03, 0.07, 0.1):
            yaw, rate, reset = reference.update(previous, -0.6, dt, "a")
            self.assertFalse(reset)
            self.assertAlmostEqual(yaw - previous, -0.10 * dt)
            self.assertAlmostEqual(rate, -0.10)
            previous = yaw

    def test_hard_lead_is_capped_and_reported(self):
        reference = BodyYawReference()
        for _ in range(300):
            yaw, _, reset = reference.update(0, 0.9, 0.02, "a")
            self.assertLessEqual(abs(yaw), 0.2 + 1e-12)
        self.assertTrue(reset)
        # A large independently imposed body rotation makes hard lead take
        # precedence over continuous reference rate, with explicit reset.
        yaw, _, reset = reference.update(1.0, 0.6, 0.02, "a")
        self.assertTrue(reset)
        self.assertLessEqual(abs(yaw - 1.0), 0.2 + 1e-12)

    def test_target_change_and_failsafe_reset_align_to_current_body(self):
        reference = BodyYawReference()
        for _ in range(30):
            reference.update(0, 0.9, 0.02, "a")
        yaw, _, reset = reference.update(0.5, 0, 0.02, "b")
        self.assertTrue(reset)
        self.assertAlmostEqual(yaw, 0.5)
        reference.reset()
        self.assertIsNone(reference.yaw)
        yaw, _, reset = reference.update(-0.5, 0, 0.02, "b")
        self.assertTrue(reset)
        self.assertAlmostEqual(yaw, -0.5)

    def test_wrap_crossing_preserves_small_positive_step(self):
        reference = BodyYawReference()
        yaw, _, _ = reference.update(math.pi - 0.001, 0.9, 0.02, "a")
        self.assertLess(yaw, 0)
        difference = (yaw - (math.pi - 0.001) + math.pi) % (2 * math.pi) - math.pi
        self.assertAlmostEqual(difference, 0.002)


class FakeVector:
    def __init__(self):
        self.header, self.vector = NS(), vec()


class FakeString:
    def __init__(self):
        self.data = ""


class AdapterSafetyTests(unittest.TestCase):
    def setUp(self):
        self.time = 10.0
        self.node = adapter.GimbalAdapterNode.__new__(adapter.GimbalAdapterNode)
        self.parameters = dict(gimbal_mode="active", control_rate_hz=50.0,
                               joint_feedback_timeout_s=0.2, vehicle_timeout_s=0.5,
                               target_timeout_s=0.75, max_command_lead_rad=0.2,
                               joint_position_gain=[4, 4, 5], max_joint_rate_radps=[1, 0.8, 1],
                               body_yaw_deadzone_rad=0.15, body_yaw_recenter_gain=0.6,
                               max_body_yaw_rate_radps=0.12)
        self.node.get_parameter = lambda key: NS(value=self.parameters[key])
        self.node.get_clock = lambda: NS(now=lambda: NS(nanoseconds=round(self.time * 1e9), to_msg=lambda: stamp(self.time)))
        self.node._last_tick_ns, self.node._last_command = None, None
        self.node._body_yaw = BodyYawReference()
        self.node._joint = NS(header=NS(stamp=stamp(10)), name=list(JOINT_NAMES), position=[0.4, 0, 0])
        self.node._vehicle = NS(header=NS(stamp=stamp(10), frame_id="map"), child_frame_id="base_link",
                                pose=NS(pose=NS(position=vec(z=3), orientation=NS(x=0, y=0, z=0, w=1))))
        self.node._target = NS(header=NS(stamp=stamp(10), frame_id="map"), state=1,
                               prediction_age_s=0.0, target_uuid="chosen", position_m=vec(8, 3, 1))
        self.commands, self.diagnostics, self.references = [[], [], []], [], []
        self.node._commands = [NS(publish=values.append) for values in self.commands]
        self.node._diagnostics = NS(publish=lambda message: self.diagnostics.append(json.loads(message.data)))
        self.node._yaw_reference = NS(publish=self.references.append)
        for name, value in (("Float64", FakeFloat64), ("Vector3Stamped", FakeVector), ("String", FakeString),
                            ("TargetState", NS(STATE_MEASURED=1, STATE_PREDICTED=2))):
            patcher = patch.object(adapter, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_active_commands_are_distinct_from_real_feedback_and_yaw_is_bounded(self):
        self.node._step()
        self.assertTrue(self.diagnostics[-1]["active"])
        np.testing.assert_allclose(self.diagnostics[-1]["feedback_angles_rad"], [0.4, 0, 0])
        self.assertNotEqual(self.commands[0][-1].data, 0.4)
        self.assertLessEqual(abs(self.references[-1].vector.z), 0.12 * 0.02 + 1e-12)

    def test_midpoint_is_explicit_and_emits_no_active_yaw_reference(self):
        self.parameters["gimbal_mode"] = "midpoint"
        self.node._target, self.node._vehicle = None, None
        self.node._step()
        self.assertEqual(self.diagnostics[-1]["reason"], "midpoint")
        self.assertFalse(self.diagnostics[-1]["active"])
        self.assertLess(self.commands[0][-1].data, 0.4)
        self.assertEqual(self.references, [])

    def test_stale_joint_feedback_freezes_at_last_measured_angle(self):
        self.node._joint.header.stamp = stamp(9.79)
        self.node._last_command = np.array([0.6, 0.3, 0.2])
        self.node._step()
        self.assertEqual(self.diagnostics[-1]["reason"], "stale_joint_feedback")
        np.testing.assert_allclose([values[-1].data for values in self.commands], [0.4, 0, 0])
        self.assertEqual(self.references, [])

    def test_lost_or_ambiguous_target_cannot_move_gimbal_or_body(self):
        for state in (0, 3, 4):
            self.node._last_tick_ns = None
            self.node._target.state = state
            self.node._step()
            self.assertEqual(self.diagnostics[-1]["reason"], "invalid_target_state")
            np.testing.assert_allclose([values[-1].data for values in self.commands], [0.4, 0, 0])
        self.assertEqual(self.references, [])

    def test_source_transport_age_and_prediction_age_are_added(self):
        self.node._target.header.stamp = stamp(9.6)
        self.node._target.prediction_age_s = 0.4
        self.node._step()
        self.assertEqual(self.diagnostics[-1]["reason"], "stale_target")
        self.assertEqual(self.references, [])

    def test_missing_partial_or_nan_feedback_never_fabricates_zero_angles(self):
        for positions in ([], [0], [0, math.nan, 0]):
            self.node._last_tick_ns = None
            self.node._joint.position = positions
            self.node._step()
            self.assertIsNone(self.diagnostics[-1]["feedback_angles_rad"])
        self.assertEqual(self.references, [])
        self.assertEqual(self.commands, [[], [], []])

    def test_future_or_zero_vehicle_timestamp_fails_safe(self):
        for timestamp in (0, 10.051):
            self.node._last_tick_ns = None
            self.node._vehicle.header.stamp = stamp(timestamp)
            self.node._step()
            self.assertEqual(self.diagnostics[-1]["reason"], "invalid source timestamp")
        self.assertEqual(self.references, [])

    def test_invalid_target_nan_age_does_not_crash_diagnostics(self):
        self.node._target.prediction_age_s = math.nan
        self.node._step()
        self.assertEqual(self.diagnostics[-1]["reason"], "stale_target")
        self.assertEqual(self.references, [])


class FakeTransform:
    def __init__(self):
        self.header = NS()
        self.transform = NS(translation=vec(), rotation=NS(x=0, y=0, z=0, w=1))


class FeedbackTfTests(unittest.TestCase):
    def setUp(self):
        self.time, self.transforms = 10.0, []
        self.node = flight_tf.FlightTfNode.__new__(flight_tf.FlightTfNode)
        parameters = dict(base_frame="base_link", camera_frame="camera_link", camera_x_m=0.13233,
                          camera_y_m=0.0, camera_z_m=0.26078, camera_pitch_rad=0.35)
        self.node.get_parameter = lambda key: NS(value=parameters[key])
        self.node.get_clock = lambda: NS(now=lambda: NS(nanoseconds=round(self.time * 1e9)))
        self.node._joint_stamp_ns = -1
        self.node._dynamic = NS(sendTransform=self.transforms.append)
        patcher = patch.object(flight_tf, "TransformStamped", FakeTransform, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def message(self, seconds=9.95, positions=(0.2, 0.1, -0.1)):
        return NS(header=NS(stamp=stamp(seconds)), name=list(JOINT_NAMES), position=list(positions))

    def test_tf_keeps_feedback_source_stamp_not_publish_time(self):
        message = self.message()
        self.node._on_joint(message)
        transform = self.transforms[-1]
        self.assertEqual(transform.header.stamp, stamp(9.95))
        self.assertEqual(transform.header.frame_id, "base_link")
        self.assertEqual(transform.child_frame_id, "camera_link")
        q = transform.transform.rotation
        np.testing.assert_allclose([q.x, q.y, q.z, q.w], camera_optical_quaternion(message.position))

    def test_duplicate_out_of_order_and_stale_feedback_are_not_rebroadcast(self):
        for source in (9.95, 9.95, 9.94, 9.7, 10.06):
            self.node._on_joint(self.message(source))
        self.assertEqual(len(self.transforms), 1)

    def test_epoch_reset_accepts_new_fresh_samples(self):
        self.node._on_joint(self.message())
        self.time = 1.0
        self.node._on_joint(self.message(0.99))
        self.assertEqual(len(self.transforms), 2)
        self.assertEqual(self.transforms[-1].header.stamp, stamp(0.99))


class PhysicalAssetTests(unittest.TestCase):
    def test_model_has_three_revolute_joints_force_pid_and_feedback(self):
        model = ET.parse(BRINGUP / "models" / "x500_stage3" / "model.sdf").getroot().find("model")
        joints = model.findall("joint")
        self.assertEqual({joint.get("name") for joint in joints}, set(JOINT_NAMES))
        self.assertTrue(all(joint.get("type") == "revolute" for joint in joints))
        axes = {joint.get("name"): joint.findtext("axis/xyz") for joint in joints}
        self.assertEqual(axes, dict(zip(JOINT_NAMES, ("0 0 1", "0 1 0", "1 0 0"))))
        controllers = model.findall("plugin[@name='gz::sim::systems::JointPositionController']")
        self.assertEqual(len(controllers), 3)
        for plugin in controllers:
            self.assertIsNone(plugin.find("use_velocity_commands"))
            self.assertGreater(float(plugin.findtext("p_gain")), 0)
        feedback = model.find("plugin[@name='gz::sim::systems::JointStatePublisher']")
        self.assertEqual(set(element.text for element in feedback.findall("joint_name")), set(JOINT_NAMES))
        self.assertEqual(feedback.findtext("topic"), "/gimbal/joint_states")
        self.assertEqual(model.findtext(".//sensor/camera/image/width"), "640")
        self.assertEqual(model.findtext(".//sensor/camera/image/height"), "480")

    def test_both_worlds_share_real_vehicle_and_single_visual_target(self):
        for category in ("person", "car"):
            world = ET.parse(BRINGUP / "worlds" / f"stage3_flight_{category}.sdf").getroot().find("world")
            self.assertEqual(world.get("name"), "stage3_flight")
            includes = {include.findtext("name"): include.findtext("uri") for include in world.findall("include")}
            self.assertEqual(includes, {"stage1_uav": "model://x500_stage3", f"target_{category}": f"model://target_{category}"})


if __name__ == "__main__":
    unittest.main()
