"""A shutter's minimum dwell starts at its own successful close ACK."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from uav_tracking.control.gimbal_geometry import camera_optical_quaternion

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "stage1_flight_monitor.py"
SPEC = importlib.util.spec_from_file_location("shutter_timing_monitor", SOURCE)
monitor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = monitor
SPEC.loader.exec_module(monitor)


class Response:
    def __init__(self):
        self.ready = False
        self.success = True
        self.error = None

    def done(self):
        return self.ready

    def result(self):
        if self.error is not None:
            raise self.error
        return NS(success=self.success)


class ShutterTimingTests(unittest.TestCase):
    def setUp(self):
        self.time = 22.0
        self.events, self.requests, self.responses = [], [], []
        self.node = monitor.FlightMonitor.__new__(monitor.FlightMonitor)
        self.node.args = NS(world="stage2_flight", target_class="car")
        self.node.now_s = lambda: self.time
        self.node.event = lambda kind, **fields: self.events.append({"kind": kind, "time_s": self.time, **fields})
        self.node.follow_start = 10.0
        self.node.shutter_requested = False
        self.node.shutter_future = self.node.shutter_pending = None
        self.node.shutter_request_seq = 0
        self.node.shutter_events, self.node.shutter_results = [], {}
        self.node.shutter_last_pose_update_s = -float("inf")
        self.node.occlusion_schedule = [
            {"name": "short", "start_offset_s": 12.0, "duration_s": 0.2,
             "render_margin_s": monitor.SHUTTER_RENDER_MARGIN_S, "state": "waiting"},
            {"name": "long", "start_offset_s": 25.0, "duration_s": 3.0,
             "render_margin_s": monitor.SHUTTER_RENDER_MARGIN_S, "state": "waiting"},
        ]
        self.node.odom = NS(pose=NS(pose=NS(position=NS(x=0., y=0., z=3.),
                                           orientation=NS(x=0., y=0., z=0., w=1.))))
        self.node.shutter_client = NS(service_is_ready=lambda: True, call_async=self.request)
        self.node.shutter_tf_buffer = NS(lookup_transform=lambda *args, **kwargs: self.transform())
        for name, value in (("SetEntityPose", NS(Request=self.request_message)),
                            ("Time", lambda: NS()), ("Duration", lambda **kwargs: NS()),
                            ("TransformException", RuntimeError)):
            patcher = patch.object(monitor, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def request_message():
        return NS(entity=NS(MODEL=2), pose=NS(position=NS(), orientation=NS()))

    def request(self, request):
        self.requests.append(request)
        response = Response()
        self.responses.append(response)
        return response

    def transform(self):
        stamp_ns = round(self.time * 1e9)
        q = camera_optical_quaternion((0.2, 0.1, 0.0))
        return NS(header=NS(stamp=NS(sec=stamp_ns // 1_000_000_000, nanosec=stamp_ns % 1_000_000_000),
                            frame_id="map"), child_frame_id="camera_link",
                  transform=NS(translation=NS(x=0., y=0., z=3.),
                               rotation=NS(x=q[0], y=q[1], z=q[2], w=q[3])))

    def tick(self, timestamp):
        self.time = timestamp
        self.node.run_shutter_schedule(timestamp)

    def edges(self):
        return [row for row in self.events if row["kind"] == "shutter"]

    def test_late_close_ack_does_not_consume_dwell_or_allow_early_open(self):
        self.tick(22.0)
        self.tick(22.3)  # the entire old nominal interval has already expired
        self.tick(23.0)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.node.occlusion_schedule[0]["state"], "closing")
        self.responses[0].ready = True
        self.tick(23.1)
        self.assertAlmostEqual(self.node.occlusion_schedule[0]["open_not_before_s"], 23.35)
        self.tick(23.349)
        self.assertEqual(len(self.requests), 1)
        self.tick(23.35)
        self.assertEqual([row["active"] for row in self.edges()], [True, False])
        self.assertAlmostEqual(self.edges()[1]["time_s"] - 23.1, 0.25)
        result = next(row for row in self.events if row["kind"] == "shutter_service_result")
        self.assertEqual(result["request_time_s"], 22.0)
        self.assertEqual(result["time_s"], 23.1)
        self.assertEqual(result["request_id"], self.edges()[0]["request_id"])

    def test_failed_close_ack_is_failure_and_never_starts_a_hold(self):
        self.tick(22.0)
        self.responses[0].ready, self.responses[0].success = True, False
        self.tick(22.1)
        episode = self.node.occlusion_schedule[0]
        self.assertEqual(episode["state"], "failed")
        self.assertEqual(episode["failure"], "close_service_failed")
        self.assertNotIn("close_ack_s", episode)
        self.assertNotIn("open_not_before_s", episode)
        self.assertFalse(any(row["kind"] == "shutter_hold_started" for row in self.events))
        self.assertFalse(self.node.shutter_results[1]["success"])
        self.assertEqual(self.edges()[-1]["active"], False)  # explicit best-effort parking

    def test_exceptional_close_response_stays_failed(self):
        self.tick(22.0)
        self.responses[0].ready = True
        self.responses[0].error = RuntimeError("bridge disconnected")
        self.tick(22.1)
        self.assertEqual(self.node.occlusion_schedule[0]["state"], "failed")
        self.assertEqual(self.node.shutter_results[1]["error"], "bridge disconnected")
        self.assertNotIn("close_ack_s", self.node.occlusion_schedule[0])

    def test_synchronous_request_failure_cannot_be_treated_as_successful_close(self):
        def fail(_request):
            raise RuntimeError("service unavailable")
        self.node.shutter_client.call_async = fail
        self.tick(22.0)
        self.tick(22.1)
        self.assertEqual(self.node.occlusion_schedule[0]["state"], "failed")
        self.assertFalse(self.node.shutter_results[1]["success"])
        self.assertNotIn("close_ack_s", self.node.occlusion_schedule[0])
        self.assertEqual(len(self.edges()), 2)
        self.assertFalse(self.edges()[1]["active"])
        self.assertTrue(self.edges()[1]["cleanup"])

    def test_open_ack_must_complete_before_next_episode_can_close(self):
        self.tick(22.0)
        self.responses[0].ready = True
        self.tick(22.1)
        self.tick(22.35)
        self.tick(35.0)  # long episode is due, but the open ACK is still missing
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.node.occlusion_schedule[1]["state"], "waiting")
        self.responses[1].ready = True
        self.tick(35.1)
        self.assertEqual(self.node.occlusion_schedule[0]["state"], "complete")
        self.tick(35.2)
        self.assertEqual(len(self.requests), 3)
        self.assertEqual([row["active"] for row in self.edges()], [True, False, True])
        self.responses[2].ready = True
        self.tick(35.3)
        self.tick(38.349)
        self.assertEqual(len(self.requests), 3)
        self.tick(38.35)
        self.assertEqual(len(self.requests), 4)

    def test_failed_open_ack_does_not_complete_successfully(self):
        self.tick(22.0)
        self.responses[0].ready = True
        self.tick(22.1)
        self.tick(22.35)
        self.responses[1].ready, self.responses[1].success = True, False
        self.tick(22.4)
        self.assertEqual(self.node.occlusion_schedule[0]["state"], "failed")
        self.assertEqual(self.node.occlusion_schedule[0]["failure"], "open_service_failed")
        self.assertFalse(any(row["kind"] == "shutter_hold_finished" for row in self.events))
        self.assertEqual(len(self.requests), 3)
        self.assertTrue(self.edges()[-1]["cleanup"])
        self.responses[2].ready = True
        self.tick(22.5)
        self.assertEqual(self.node.occlusion_schedule[0]["state"], "failed")
        self.assertFalse(self.node.shutter_results[2]["success"])
        self.assertTrue(self.node.shutter_results[3]["success"])
        self.assertFalse(any(row["kind"] == "shutter_hold_finished" for row in self.events))

    def test_failed_cleanup_does_not_retry_forever(self):
        self.tick(22.0)
        self.responses[0].ready, self.responses[0].success = True, False
        self.tick(22.1)
        self.responses[1].ready, self.responses[1].success = True, False
        self.tick(22.2)
        self.tick(24.0)
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.node.occlusion_schedule[0]["state"], "failed")

    def test_gimbal_refresh_ack_does_not_restart_close_dwell(self):
        self.node.args.world = "stage3_flight"
        self.tick(22.0)
        self.responses[0].ready = True
        self.tick(22.1)
        self.tick(22.25)  # moving camera needs a measured-TF refresh
        self.assertEqual(len(self.requests), 2)
        self.assertTrue(self.node.shutter_pending["refresh"])
        self.tick(22.35)  # cannot overtake an in-flight refresh service call
        self.assertEqual(len(self.edges()), 1)
        self.responses[1].ready = True
        self.tick(22.4)
        self.assertEqual([row["active"] for row in self.edges()], [True, False])
        self.assertEqual(self.node.occlusion_schedule[0]["close_ack_s"], 22.1)
        self.assertAlmostEqual(self.node.occlusion_schedule[0]["open_not_before_s"], 22.35)
        self.assertEqual(len([row for row in self.events if row["kind"] == "shutter_hold_started"]), 1)
        self.assertEqual(self.events[-2]["kind"], "shutter_pose_update_result")

    def test_service_not_ready_cannot_start_nominal_dwell(self):
        self.node.shutter_client.service_is_ready = lambda: False
        self.tick(22.0)
        self.tick(24.0)
        self.assertEqual(self.node.occlusion_schedule[0]["state"], "waiting")
        self.assertEqual(self.edges(), [])
        self.node.shutter_client.service_is_ready = lambda: True
        self.tick(24.1)
        self.responses[0].ready = True
        self.tick(24.2)
        self.assertAlmostEqual(self.node.occlusion_schedule[0]["open_not_before_s"], 24.45)


if __name__ == "__main__":
    unittest.main()
