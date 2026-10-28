"""Gimbal occlusion stimulus follows measured optical TF, not body heading."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import numpy as np

from uav_tracking.control.gimbal_geometry import camera_optical_quaternion, quaternion_rotation

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "stage1_flight_monitor.py"
SPEC = importlib.util.spec_from_file_location("stage3_shutter_monitor", SOURCE)
monitor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = monitor
SPEC.loader.exec_module(monitor)


def stamp(seconds):
    value = round(seconds * 1e9)
    return NS(sec=value // 1_000_000_000, nanosec=value % 1_000_000_000)


def transform(seconds=10.0, angles=(1.0, 0.2, 0.1)):
    q = camera_optical_quaternion(angles)
    return NS(header=NS(stamp=stamp(seconds), frame_id="map"), child_frame_id="camera_link",
              transform=NS(translation=NS(x=2.0, y=3.0, z=4.0), rotation=NS(x=q[0], y=q[1], z=q[2], w=q[3])))


class ShutterGeometryTests(unittest.TestCase):
    def test_plane_normal_and_position_follow_measured_optical_forward(self):
        measured = transform()
        position, orientation, source = monitor.shutter_pose_from_camera_transform(measured, 10.05)
        optical_q = measured.transform.rotation
        optical_rotation = quaternion_rotation([optical_q.x, optical_q.y, optical_q.z, optical_q.w])
        shutter_rotation = quaternion_rotation(orientation)
        np.testing.assert_allclose(position, [2, 3, 4] + 0.6 * optical_rotation[:, 2], atol=1e-12)
        np.testing.assert_allclose(shutter_rotation[:, 0], optical_rotation[:, 2], atol=1e-12)
        self.assertGreater(position[1] - 3, 0.3)  # turned left; body-forward would be incorrect
        self.assertEqual(source, 10.0)

    def test_stale_future_and_zero_feedback_tf_are_rejected(self):
        for seconds in (0, 9.79, 10.051):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                monitor.shutter_pose_from_camera_transform(transform(seconds), 10.0)

    def test_wrong_frame_or_zero_quaternion_cannot_fall_back_to_body(self):
        measured = transform()
        measured.child_frame_id = "body_link"
        with self.assertRaises(ValueError):
            monitor.shutter_pose_from_camera_transform(measured, 10)
        measured = transform()
        measured.transform.rotation = NS(x=0, y=0, z=0, w=0)
        with self.assertRaises(ValueError):
            monitor.shutter_pose_from_camera_transform(measured, 10)


class FakeRequest:
    def __init__(self):
        self.entity = NS(name="", type=0, MODEL=2)
        self.pose = NS(position=NS(x=0, y=0, z=0), orientation=NS(x=0, y=0, z=0, w=1))


class ShutterServiceTests(unittest.TestCase):
    def setUp(self):
        self.time, self.events, self.requests = 10.0, [], []
        self.node = monitor.FlightMonitor.__new__(monitor.FlightMonitor)
        self.node.args = NS(world="stage3_flight")
        self.node.odom = None  # source is feedback TF, not body odometry
        self.node.now_s = lambda: self.time
        self.node.event = lambda kind, **data: self.events.append(dict(kind=kind, time_s=self.time, **data) if "time_s" not in data else dict(kind=kind, **data))
        self.node.shutter_requested = False
        self.node.shutter_future = self.node.shutter_pending = None
        self.node.shutter_request_seq = 0
        self.node.shutter_events = []
        self.node.shutter_last_pose_update_s = -float("inf")
        self.node.shutter_tf_buffer = NS(lookup_transform=lambda *args, **kwargs: transform(self.time))
        def call_async(request):
            self.requests.append(request)
            return NS(done=lambda: True, result=lambda: NS(success=True))
        self.node.shutter_client = NS(service_is_ready=lambda: True, call_async=call_async)
        for key, value in (("SetEntityPose", NS(Request=FakeRequest)), ("Time", lambda: NS()),
                           ("Duration", lambda **kwargs: NS()), ("TransformException", RuntimeError)):
            patcher = patch.object(monitor, key, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_long_active_refresh_has_separate_logs_and_does_not_fabricate_occlusion_edges(self):
        self.node.set_shutter(True)
        self.time = 10.1
        self.node.set_shutter(True)
        self.assertEqual(len(self.requests), 1)
        self.time = 10.3
        self.node.set_shutter(True)
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(len(self.node.shutter_events), 1)
        self.assertTrue(self.events[-1]["refresh"])
        self.assertEqual(self.events[-1]["kind"], "shutter_pose_update")
        self.assertEqual(self.events[-1]["pose_source"], "measured_camera_tf")
        self.time = 13.0
        self.node.set_shutter(False)
        self.node.set_shutter(False)  # collect independent open acknowledgement
        self.assertEqual(len(self.node.shutter_events), 2)
        self.assertEqual([row["active"] for row in self.node.shutter_events], [True, False])
        self.assertEqual(self.requests[-1].pose.position.z, -50.0)
        kinds = [event["kind"] for event in self.events]
        self.assertIn("shutter_pose_update_result", kinds)
        self.assertEqual(kinds.count("shutter_service_result"), 2)

    def test_missing_or_stale_tf_does_not_claim_shutter_closed(self):
        self.node.shutter_tf_buffer.lookup_transform = lambda *args, **kwargs: transform(9.0)
        self.node.set_shutter(True)
        self.assertFalse(self.node.shutter_requested)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.node.shutter_events, [])
        self.assertEqual(self.events[-1]["kind"], "shutter_pose_unavailable")


if __name__ == "__main__":
    unittest.main()
