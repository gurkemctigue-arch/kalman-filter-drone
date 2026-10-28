"""Concurrency regressions without ROS, torch or a real inference model."""

from collections import deque
import json
from pathlib import Path
import signal
import sys
from threading import Event, Lock, Thread
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
NODES = ROOT / "ros2_ws/src/uav_tracking_nodes"
if str(NODES) not in sys.path:
    sys.path.insert(0, str(NODES))

from uav_tracking.core import CameraIntrinsics  # noqa: E402
from uav_tracking_nodes import detector_node as detector  # noqa: E402
from uav_tracking_nodes.inference_worker import NonQueuingWorker  # noqa: E402


def image(stamp_s):
    nanoseconds = round(stamp_s * 1e9)
    return NS(header=NS(stamp=NS(sec=nanoseconds // 1_000_000_000, nanosec=nanoseconds % 1_000_000_000),
                        frame_id="camera_link"), width=4, height=4)


class WorkerTests(unittest.TestCase):
    def test_busy_submissions_are_dropped_without_a_backlog(self):
        entered, release = Event(), Event()
        processed, errors = [], []

        def process(job):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test did not release inference")
            processed.append(job)

        worker = NonQueuingWorker(process, errors.append)
        try:
            self.assertTrue(worker.submit("first"))
            self.assertTrue(entered.wait(1))
            for candidate in range(100):
                self.assertFalse(worker.submit(candidate))
            release.set()
            self.assertTrue(worker.wait_idle(1))
            self.assertEqual(processed, ["first"])
            self.assertTrue(worker.submit("latest"))
            self.assertTrue(worker.wait_idle(1))
            self.assertEqual(processed, ["first", "latest"])
            self.assertEqual(errors, [])
        finally:
            release.set()
            worker.shutdown()

    def test_processing_exception_is_reported_and_next_job_can_run(self):
        processed, errors = [], []

        def process(job):
            if job == "bad":
                raise ValueError("bad model output")
            processed.append(job)

        worker = NonQueuingWorker(process, errors.append)
        try:
            self.assertTrue(worker.submit("bad"))
            self.assertTrue(worker.wait_idle(1))
            self.assertIsInstance(errors[0], ValueError)
            self.assertFalse(worker.busy)
            self.assertTrue(worker.submit("good"))
            self.assertTrue(worker.wait_idle(1))
            self.assertEqual(processed, ["good"])
        finally:
            worker.shutdown()

    def test_shutdown_waits_for_accepted_work_and_rejects_later_submissions(self):
        entered, release, closing, closed = Event(), Event(), Event(), Event()
        completed = []

        def process(job):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test did not release inference")
            completed.append(job)

        worker = NonQueuingWorker(process, lambda error: None)
        worker.submit("in flight")
        self.assertTrue(entered.wait(1))

        def shutdown():
            closing.set()
            worker.shutdown()
            closed.set()

        shutdown_thread = Thread(target=shutdown)
        shutdown_thread.start()
        try:
            self.assertTrue(closing.wait(1))
            self.assertFalse(closed.wait(0.03))
            self.assertFalse(worker.submit("during shutdown"))
            release.set()
            self.assertTrue(closed.wait(1))
            self.assertEqual(completed, ["in flight"])
            self.assertFalse(worker.submit("after shutdown"))
        finally:
            release.set()
            shutdown_thread.join(2)
            worker.shutdown()


class DetectorShutdownTests(unittest.TestCase):
    def test_repeated_launch_signals_cannot_interrupt_slow_inference_join(self):
        entered, release, closing = Event(), Event(), Event()
        events, errors, installed = [], [], {}
        context = {"ok": False}
        previous = {signal.SIGINT: object(), signal.SIGTERM: object()}
        installed.update(previous)

        def install(number, handler):
            old = installed[number]
            installed[number] = handler
            return old

        class FakeNode:
            def __init__(self):
                self.context = object()
                self.publishers_alive = True
                self.worker = NonQueuingWorker(self.infer, errors.append)
                self.worker.submit("slow native inference")
                if not entered.wait(1):
                    raise RuntimeError("inference did not start")

            def infer(self, job):
                entered.set()
                if not release.wait(2):
                    raise RuntimeError("test did not release inference")
                if not self.publishers_alive or not context["ok"]:
                    raise RuntimeError("resources destroyed before native work finished")
                events.append("inference finished")

            def destroy_node(self):
                closing.set()
                events.append("join started")
                self.worker.shutdown()
                self.publishers_alive = False
                events.append("node destroyed")

        class FakeExecutor:
            def __init__(self, **kwargs):
                pass

            def add_node(self, node):
                pass

            def spin_once(self, timeout_sec):
                installed[signal.SIGINT](signal.SIGINT, None)
                events.append("initial signal")

            def shutdown(self):
                events.append("executor stopped")

        def repeat_signals_during_join():
            if not closing.wait(1):
                errors.append(RuntimeError("join did not start"))
            for number in (signal.SIGINT, signal.SIGINT, signal.SIGTERM):
                installed[number](number, None)
            events.append("repeated signals")
            release.set()

        def init(**kwargs):
            self.assertEqual(kwargs["signal_handler_options"], "no ROS handlers")
            context["ok"] = True

        def shutdown():
            context["ok"] = False
            events.append("context destroyed")

        repeater = Thread(target=repeat_signals_during_join)
        repeater.start()
        try:
            with patch.object(detector.signal, "signal", side_effect=install), \
                    patch.object(detector, "rclpy", NS(init=init, ok=lambda: context["ok"], shutdown=shutdown)), \
                    patch.object(detector, "SignalHandlerOptions", NS(NO="no ROS handlers"), create=True), \
                    patch.object(detector, "ExternalShutdownException", type("ExternalShutdown", (Exception,), {}), create=True), \
                    patch.object(detector, "SingleThreadedExecutor", FakeExecutor, create=True), \
                    patch.object(detector, "DetectorNode", FakeNode):
                detector.main([])
        finally:
            release.set()
            repeater.join(2)
        self.assertEqual(errors, [])
        self.assertEqual(events, ["initial signal", "executor stopped", "join started",
                                  "repeated signals", "inference finished", "node destroyed", "context destroyed"])
        self.assertEqual(installed, previous, "embedding callers recover their original signal handlers")


class DetectorSchedulingTests(unittest.TestCase):
    def make_node(self, process=None):
        node = detector.DetectorNode.__new__(detector.DetectorNode)
        node._input_lock = Lock()
        node._rgb_message = None
        node._depth_messages = deque(maxlen=15)
        node._intrinsics = CameraIntrinsics(100.0, 100.0, 2.0, 2.0)
        node._camera_size = (4, 4)
        node._last_inference_stamp = None
        node._last_submit_ros_ns = None
        node._last_clock_ros_ns = None
        node._clock_epoch = 0
        node._inference_period_ns = 200_000_000
        node._test_clock = {"nanoseconds": 1_000_000_000}
        node.get_clock = lambda: NS(now=lambda: NS(nanoseconds=node._test_clock["nanoseconds"]))
        node._model = NS()
        node._tracking_active, node._activation_stamp_s = True, None
        parameters = {
            "inference_image_size": 640, "inference_device": "cpu", "class_id": 0,
            "class_name": "person", "confidence_threshold": 0.45, "depth_scale": 1.0,
            "min_depth_m": 0.2, "max_depth_m": 50.0, "min_depth_valid_ratio": 0.35,
            "depth_max_age_s": 0.20,
        }
        node.get_parameter = lambda name: NS(value=parameters[name])
        warnings = []
        node.get_logger = lambda: NS(warning=warnings.append)
        node._worker = NonQueuingWorker(process or node._infer_snapshot, node._on_inference_error)
        self.addCleanup(node._worker.shutdown)
        return node, warnings

    @staticmethod
    def set_time(node, seconds):
        node._test_clock["nanoseconds"] = round(seconds * 1_000_000_000)

    @staticmethod
    def configure_fake_inference(node, predict):
        node._bridge = NS(imgmsg_to_cv2=lambda message, desired_encoding: (
            np.zeros((4, 4, 3), dtype=np.uint8) if desired_encoding == "bgr8"
            else np.full((4, 4), 5.0, dtype=np.float32)))
        node._model = NS(predict=predict)
        diagnostics, observations = [], []
        node._diagnostics_pub = NS(publish=lambda message: diagnostics.append(json.loads(message.data)))
        node._publisher = NS(publish=observations.append)
        return diagnostics, observations

    def test_busy_timer_skips_work_and_after_completion_selects_latest_frame(self):
        entered, release = Event(), Event()
        selected = []

        def process(snapshot):
            selected.append((snapshot.rgb.header.stamp.sec, snapshot.depth.header.stamp.sec))
            if len(selected) == 1:
                entered.set()
                if not release.wait(2):
                    raise RuntimeError("test did not release inference")

        node, warnings = self.make_node(process)
        self.addCleanup(release.set)
        node._process_latest()  # No input does not create a job.
        node._on_rgb(image(1))
        node._on_depth(image(1))
        node._model = None
        node._process_latest()  # A missing model also never queues a frame.
        self.assertEqual(selected, [])
        self.assertIsNone(node._last_inference_stamp)
        node._model = NS()
        node._process_latest()
        self.assertTrue(entered.wait(1))
        for timestamp in (2, 3):
            self.set_time(node, timestamp)
            node._on_rgb(image(timestamp))
            node._on_depth(image(timestamp))
            node._process_latest()
        self.assertEqual(selected, [(1, 1)])
        self.assertEqual(node._last_inference_stamp, 1)
        release.set()
        self.assertTrue(node._worker.wait_idle(1))
        node._process_latest()
        self.assertTrue(node._worker.wait_idle(1))
        self.assertEqual(selected, [(1, 1), (3, 3)])
        node._process_latest()  # The same acquisition stamp is never repeated.
        self.assertTrue(node._worker.wait_idle(1))
        self.assertEqual(len(selected), 2)
        self.assertEqual(warnings, [])

    def test_complete_frame_contains_all_candidates_and_publishes_empty_frames(self):
        for count in (0, 3):
            with self.subTest(candidate_count=count):
                node, warnings = self.make_node()
                boxes = [NS(conf=[0.9], cls=[0], xyxy=[np.array([0., 0., 4., 4.])])
                         for _ in range(count)]
                diagnostics, observations = self.configure_fake_inference(
                    node, lambda *_args, **_kwargs: [NS(boxes=boxes)])
                frames = []
                node._frame_publisher = NS(publish=frames.append)
                observation_factory = lambda: NS(position_camera_m=NS(x=0., y=0., z=0.))
                with patch.object(detector, "String", lambda: NS(data=""), create=True), \
                        patch.object(detector, "TargetObservation", observation_factory, create=True), \
                        patch.object(detector, "TargetObservationArray", lambda: NS(), create=True):
                    node._on_rgb(image(1))
                    node._on_depth(image(1))
                    node._process_latest()
                    self.assertTrue(node._worker.wait_idle(1))
                self.assertEqual(warnings, [])
                self.assertEqual(len(frames), 1)
                self.assertEqual(len(frames[0].observations), count)
                self.assertEqual(frames[0].observations, observations)
                self.assertEqual(len(diagnostics[0]["detections"]), count)
                self.assertTrue(all(item.header == frames[0].header for item in observations))

    def test_slow_inference_is_resubmitted_on_next_poll_without_period_quantization(self):
        entered, release = Event(), Event()
        submitted = []

        def process(snapshot):
            submitted.append(snapshot.submitted_ros_ns)
            if len(submitted) == 1:
                entered.set()
                if not release.wait(2):
                    raise RuntimeError("test did not release inference")

        node, warnings = self.make_node(process)
        self.addCleanup(release.set)
        self.set_time(node, 10)
        node._on_rgb(image(10))
        node._on_depth(image(10))
        node._process_latest()
        self.assertTrue(entered.wait(1))
        for tick in range(1, 11):
            timestamp = 10 + tick * 0.02
            self.set_time(node, timestamp)
            node._on_rgb(image(timestamp))
            node._on_depth(image(timestamp))
            node._process_latest()
        self.assertEqual(submitted, [10_000_000_000])
        self.set_time(node, 10.21)
        release.set()
        self.assertTrue(node._worker.wait_idle(1))
        self.set_time(node, 10.22)
        node._on_rgb(image(10.22))
        node._on_depth(image(10.22))
        node._process_latest()
        self.assertTrue(node._worker.wait_idle(1))
        self.assertEqual(submitted, [10_000_000_000, 10_220_000_000])
        self.assertEqual(warnings, [])

    def test_fast_inference_never_exceeds_five_hz_with_fifty_hz_polling(self):
        submitted = []
        node, warnings = self.make_node(lambda snapshot: submitted.append(snapshot.submitted_ros_ns))
        for tick in range(51):
            timestamp = tick * 0.02
            self.set_time(node, timestamp)
            node._on_rgb(image(timestamp))
            node._on_depth(image(timestamp))
            node._process_latest()
            self.assertTrue(node._worker.wait_idle(1))
        self.assertEqual(submitted, [0, 200_000_000, 400_000_000, 600_000_000, 800_000_000, 1_000_000_000])
        self.assertTrue(all(later - earlier >= 200_000_000 for earlier, later in zip(submitted, submitted[1:])))
        self.assertEqual(warnings, [])

    def test_future_rgb_and_depth_are_not_submitted(self):
        submitted = []
        node, warnings = self.make_node(lambda snapshot: submitted.append(snapshot))
        node._on_rgb(image(1.1))
        node._on_depth(image(1))
        node._process_latest()
        node._on_rgb(image(1))
        node._depth_messages.clear()
        node._on_depth(image(1.1))
        node._process_latest()
        self.assertEqual(submitted, [])
        self.assertIsNone(node._last_submit_ros_ns)
        node._on_depth(image(1))
        node._process_latest()
        self.assertTrue(node._worker.wait_idle(1))
        self.assertEqual(len(submitted), 1)
        self.assertEqual(submitted[0].depth.header.stamp, image(1).header.stamp)
        self.assertEqual(warnings, [])

    def test_clock_rollback_discards_old_epoch_and_allows_fresh_submission(self):
        for poll_during_inference in (False, True):
            with self.subTest(poll_during_inference=poll_during_inference):
                entered, release = Event(), Event()
                node, warnings = self.make_node()
                self.addCleanup(release.set)
                box = NS(conf=[0.9], cls=[0], xyxy=[np.array([0.0, 0.0, 4.0, 4.0])])

                def predict(*_args, **_kwargs):
                    entered.set()
                    if not release.wait(2):
                        raise RuntimeError("test did not release inference")
                    return [NS(boxes=[box])]

                diagnostics, observations = self.configure_fake_inference(node, predict)
                observation_factory = lambda: NS(position_camera_m=NS(x=0.0, y=0.0, z=0.0))
                with patch.object(detector, "String", lambda: NS(data=""), create=True), \
                        patch.object(detector, "TargetObservation", observation_factory, create=True):
                    self.set_time(node, 10)
                    node._on_rgb(image(10))
                    node._on_depth(image(10))
                    node._process_latest()
                    self.assertTrue(entered.wait(1))
                    self.set_time(node, 1)
                    if poll_during_inference:
                        node._process_latest()  # Busy polling still observes the reset.
                        # Even if new time catches up, old-epoch output remains invalid.
                        self.set_time(node, 10.5)
                    release.set()
                    self.assertTrue(node._worker.wait_idle(1))
                    self.assertEqual(node._clock_epoch, 1)
                    self.assertEqual(observations, [])
                    self.assertEqual(diagnostics, [])
                    self.assertIsNone(node._last_submit_ros_ns)
                    self.assertIsNone(node._rgb_message)
                    self.assertEqual(len(node._depth_messages), 0)
                    timestamp = 10.52 if poll_during_inference else 1.02
                    self.set_time(node, timestamp)
                    node._on_rgb(image(timestamp))
                    node._on_depth(image(timestamp))
                    node._process_latest()
                    self.assertTrue(node._worker.wait_idle(1))
                self.assertEqual(len(observations), 1)
                self.assertEqual(len(diagnostics), 1)
                self.assertAlmostEqual(diagnostics[0]["stamp_s"], timestamp)
                self.assertEqual(warnings, [])

    def test_inference_does_not_block_input_clock_or_mutate_camera_snapshot(self):
        entered, release = Event(), Event()
        node, warnings = self.make_node()
        self.addCleanup(release.set)
        clock = {"nanoseconds": 1_100_000_000}
        node.get_clock = lambda: NS(now=lambda: NS(nanoseconds=clock["nanoseconds"]))
        node._bridge = NS(imgmsg_to_cv2=lambda message, desired_encoding: (
            np.zeros((4, 4, 3), dtype=np.uint8) if desired_encoding == "bgr8"
            else np.full((4, 4), 5.0, dtype=np.float32)))
        box = NS(conf=[0.9], cls=[0], xyxy=[np.array([0.0, 0.0, 4.0, 4.0])])

        def predict(*_args, **_kwargs):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test did not release inference")
            return [NS(boxes=[box])]

        node._model = NS(predict=predict)
        diagnostics, observations = [], []
        node._diagnostics_pub = NS(publish=lambda message: diagnostics.append(json.loads(message.data)))
        node._publisher = NS(publish=observations.append)
        observation_factory = lambda: NS(position_camera_m=NS(x=0.0, y=0.0, z=0.0))
        with patch.object(detector, "String", lambda: NS(data=""), create=True), \
                patch.object(detector, "TargetObservation", observation_factory, create=True):
            node._on_rgb(image(1))
            node._on_depth(image(1))
            node._process_latest()
            self.assertTrue(entered.wait(1))
            # These callbacks execute during the blocked inference, and can
            # replace the deque/calibration while the worker keeps its snapshot.
            node._on_rgb(image(1.5))
            for timestamp in range(2, 30):
                node._on_depth(image(timestamp))
            node._on_camera_info(NS(k=[200, 0, 0, 0, 200, 0], width=4, height=4))
            clock["nanoseconds"] = 1_600_000_000
            release.set()
            self.assertTrue(node._worker.wait_idle(1))
        self.assertEqual(warnings, [])
        self.assertEqual(diagnostics[0]["stamp_s"], 1.0)
        self.assertEqual(diagnostics[0]["completed_s"], 1.6)
        self.assertEqual(diagnostics[0]["rgb_depth_sync_error_s"], 0.0)
        self.assertEqual(len(observations), 1)
        self.assertAlmostEqual(observations[0].position_camera_m.x, 0.0)
        self.assertAlmostEqual(observations[0].position_camera_m.z, 5.0)

    def test_shutdown_discards_final_result_and_never_publishes_after_stop(self):
        entered, release = Event(), Event()
        node, warnings = self.make_node()
        self.addCleanup(release.set)

        def predict(*args, **kwargs):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test did not release inference")
            return [NS(boxes=[])]

        diagnostics, observations = self.configure_fake_inference(node, predict)
        node._on_rgb(image(1))
        node._on_depth(image(1))
        node._process_latest()
        self.assertTrue(entered.wait(1))
        with node._input_lock:
            node._stopping = True
        release.set()
        self.assertTrue(node._worker.wait_idle(1))
        self.assertEqual(diagnostics, [])
        self.assertEqual(observations, [])
        self.assertEqual(warnings, [])
        node._on_inference_error(RuntimeError("closed context"))
        self.assertEqual(warnings, [])
        node._process_latest()
        self.assertEqual(node._last_inference_stamp, 1)


if __name__ == "__main__":
    unittest.main()
