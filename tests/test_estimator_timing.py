"""Regression checks for delayed RGB-D fusion and elapsed-time target loss."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from uav_tracking.core import ConstantVelocityKalman3D, Detection, TargetManager, TargetMode, TargetStatus, TrackState

ROOT = Path(__file__).resolve().parents[1]
NODES_SOURCE = ROOT / "ros2_ws" / "src" / "uav_tracking_nodes"
if str(NODES_SOURCE) not in sys.path:
    sys.path.insert(0, str(NODES_SOURCE))

from uav_tracking_nodes import state_estimator_node as estimator  # noqa: E402


def detection(timestamp: float, position=(0.0, 0.0, 5.0)) -> Detection:
    return Detection((0, 0, 10, 10), "person", 0.95, timestamp, position)


def manager(mode=TargetMode.AUTO_UNIQUE) -> TargetManager:
    return TargetManager(
        mode, min_hits=1, max_coast_frames=1, max_lost_frames=2,
        max_coast_duration_s=0.75, track_retention_duration_s=3.0,
    )


class OutputPredictionTests(unittest.TestCase):
    def test_projection_does_not_commit_filter_time_or_covariance(self) -> None:
        filter_ = ConstantVelocityKalman3D()
        filter_.initialize([0, 0, 5], velocity=[1, 0, 0], timestamp=0.0)
        state, covariance = filter_.state.copy(), filter_.covariance.copy()
        projected = filter_.project(0.3)
        np.testing.assert_allclose(projected.position, [0.3, 0, 5])
        np.testing.assert_array_equal(filter_.state, state)
        np.testing.assert_array_equal(filter_.covariance, covariance)
        self.assertEqual(filter_.timestamp, 0.0)
        self.assertTrue(filter_.update([0.2, 0, 5], timestamp=0.2))
        self.assertEqual(filter_.timestamp, 0.2)
        self.assertGreater(projected.covariance[0, 3], 0.0)

    def test_fifty_hz_outputs_do_not_consume_five_hz_camera_frames(self) -> None:
        tracker = manager()
        first = tracker.update([detection(0.0)], timestamp=0.0)
        for step in range(1, 16):
            result = tracker.predict_with_result(step * 0.02)
            self.assertEqual(result.status, TargetStatus.COASTING)
        self.assertEqual(first.missed, 0)
        self.assertEqual(first._filter.timestamp, 0.0)
        # This image arrived at wall/sim time 0.30, but was acquired at 0.20.
        updated = tracker.update_with_result([detection(0.2)], timestamp=0.2)
        self.assertEqual(updated.target.track_id, first.track_id)
        self.assertEqual(updated.status, TargetStatus.TRACKING)
        self.assertEqual(updated.target.last_measurement_timestamp, 0.2)

    def test_loss_depends_on_elapsed_seconds_not_prediction_count(self) -> None:
        for interval in (0.001, 0.02, 0.1):
            with self.subTest(interval=interval):
                tracker = manager()
                tracker.update([detection(0.0)], timestamp=0.0)
                for timestamp in np.arange(interval, 0.75, interval):
                    self.assertEqual(tracker.predict_with_result(float(timestamp)).status, TargetStatus.COASTING)
                self.assertEqual(tracker.predict_with_result(0.75).status, TargetStatus.COASTING)
                self.assertEqual(tracker.predict_with_result(0.751).status, TargetStatus.LOST)
                self.assertEqual(tracker.predict_with_result(3.001).target.state, TrackState.REMOVED)

    def test_long_loss_latches_reselection_in_locked_mode(self) -> None:
        tracker = manager(TargetMode.LOCKED_TARGET)
        tracker.lock_detection(0, target_uuid="selected-person")
        original = tracker.update([detection(0.0)], timestamp=0.0)
        tracker.predict_with_result(0.76)
        returned = tracker.update_with_result([detection(0.7)], timestamp=0.7)
        self.assertEqual(returned.status, TargetStatus.LOST)
        self.assertEqual(returned.target.track_id, original.track_id)
        self.assertEqual(tracker.target_uuid, "selected-person")
        tracker.lock_detection(0)
        resumed = tracker.update_with_result([detection(0.8)], timestamp=0.8)
        self.assertEqual(resumed.status, TargetStatus.TRACKING)

    def test_elapsed_loss_in_both_modes_cannot_be_undone_by_delayed_or_fresh_frame(self) -> None:
        for mode in (TargetMode.AUTO_UNIQUE, TargetMode.LOCKED_TARGET):
            with self.subTest(mode=mode):
                tracker = manager(mode)
                if mode == TargetMode.LOCKED_TARGET:
                    tracker.lock_detection(0)
                original = tracker.update([detection(1.0)], timestamp=1.0)
                original_uuid = tracker.target_uuid
                self.assertEqual(tracker.predict_with_result(1.751).status, TargetStatus.LOST)
                # A legal delayed acquisition is newer than the last image
                # but predates the output tick that latched the long loss.
                for acquired in (1.7, 1.8):
                    result = tracker.update_with_result([detection(acquired)], timestamp=acquired)
                    self.assertEqual(result.status, TargetStatus.LOST)
                    self.assertEqual(result.target.track_id, original.track_id)
                    self.assertEqual(tracker.target_uuid, original_uuid)
                    self.assertEqual(result.target.last_measurement_timestamp, 1.0)
                    self.assertFalse(result.target._matched_this_frame)
                self.assertEqual(tracker.predict_with_result(1.81).status, TargetStatus.LOST)
                self.assertFalse(tracker.lock_target(9999))
                self.assertEqual(tracker.update_with_result([detection(1.85)], timestamp=1.85).status, TargetStatus.LOST)
                tracker.lock_detection(0, target_uuid="explicit-new-task")
                resumed = tracker.update_with_result([detection(1.9)], timestamp=1.9)
                self.assertEqual(resumed.status, TargetStatus.TRACKING)
                self.assertEqual(tracker.target_uuid, "explicit-new-task")
                self.assertNotEqual(tracker.target_uuid, original_uuid)

    def test_short_loss_at_prediction_boundary_can_recover_original_task_in_both_modes(self) -> None:
        for mode in (TargetMode.AUTO_UNIQUE, TargetMode.LOCKED_TARGET):
            with self.subTest(mode=mode):
                tracker = manager(mode)
                if mode == TargetMode.LOCKED_TARGET:
                    tracker.lock_detection(0)
                original = tracker.update([detection(1.0)], timestamp=1.0)
                original_uuid = tracker.target_uuid
                self.assertEqual(tracker.predict_with_result(1.75).status, TargetStatus.COASTING)
                recovered = tracker.update_with_result([detection(1.75)], timestamp=1.75)
                self.assertEqual(recovered.status, TargetStatus.TRACKING)
                self.assertEqual(recovered.target.track_id, original.track_id)
                self.assertEqual(tracker.target_uuid, original_uuid)

    def test_long_loss_takes_precedence_over_latched_unique_instance_ambiguity(self) -> None:
        tracker = manager()
        tracker.update([detection(1.0)], timestamp=1.0)
        tracker.update([detection(1.1), Detection((30, 0, 40, 10), "person", 0.95, 1.1, (3, 0, 5))], timestamp=1.1)
        self.assertEqual(tracker.predict_with_result(1.2).status, TargetStatus.AMBIGUOUS)
        self.assertEqual(tracker.predict_with_result(1.851).status, TargetStatus.LOST)

    def test_invalid_depth_and_gated_outliers_cannot_extend_three_d_freshness(self) -> None:
        for position in (None, (0.0, 0.0, 100.0)):
            with self.subTest(position=position):
                tracker = manager()
                tracker.update([detection(0.0)], timestamp=0.0)
                for step in range(1, 9):
                    timestamp = step / 10
                    tracker.update([detection(timestamp, position)], timestamp=timestamp)
                self.assertEqual(tracker.target.last_measurement_timestamp, 0.0)
                self.assertEqual(tracker.status, TargetStatus.LOST)
                if position is not None:
                    # The eighth frame arrives after the elapsed-time loss
                    # boundary, so it must be excluded from target updates.
                    self.assertEqual(tracker.target.rejected_measurements, 7)

    def test_projected_snapshot_keeps_full_covariance_and_does_not_mutate_track(self) -> None:
        tracker = manager()
        track = tracker.update([detection(0.0)], timestamp=0.0)
        original = track.covariance_6d.copy()
        projected = tracker.predict_with_result(0.3).target
        self.assertEqual(projected.covariance_6d.shape, (6, 6))
        self.assertGreater(projected.covariance_6d[0, 3], 0.0)
        np.testing.assert_array_equal(track.covariance_6d, original)
        self.assertFalse(projected._matched_this_frame)


def stamp(seconds: float) -> SimpleNamespace:
    nanoseconds = round(seconds * 1e9)
    return SimpleNamespace(sec=nanoseconds // 1_000_000_000, nanosec=nanoseconds % 1_000_000_000)


def observation(timestamp: float, x: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(
        header=SimpleNamespace(stamp=stamp(timestamp), frame_id="camera_optical"),
        camera_frame="camera_optical", class_name="person", confidence=0.95,
        bbox_x_min_px=x, bbox_y_min_px=0.0, bbox_x_max_px=x + 10.0, bbox_y_max_px=10.0,
        position_camera_m=SimpleNamespace(x=x / 10, y=0.0, z=5.0),
        depth_valid=True, depth_valid_ratio=1.0, depth_std_m=0.01, candidate_id=0,
    )


class FakeState:
    STATE_UNINITIALIZED, STATE_MEASURED, STATE_PREDICTED, STATE_LOST, STATE_AMBIGUOUS = range(5)

    def __init__(self) -> None:
        self.position_m = SimpleNamespace(x=0.0, y=0.0, z=0.0)
        self.velocity_mps = SimpleNamespace(x=0.0, y=0.0, z=0.0)


class EstimatorAdapterTimingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.time = 0.0
        self.messages, self.warnings = [], []
        self.parameters = dict(buffer_delay_s=0.02, max_observation_age_s=0.60,
                               state_frame="map", max_prediction_duration_s=0.75,
                               min_depth_valid_ratio=0.35)
        self.node = estimator.StateEstimatorNode.__new__(estimator.StateEstimatorNode)
        self.node.get_parameter = lambda key: SimpleNamespace(value=self.parameters[key])
        self.node.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(
            nanoseconds=round(self.time * 1e9), to_msg=lambda: stamp(self.time)))
        self.node.get_logger = lambda: SimpleNamespace(warning=lambda message, **_: self.warnings.append(message))
        self.node._manager = manager()
        self.node._pending = defaultdict(list)
        self.node._pending_first_received = {}
        self.node._pending_selection = None
        self.node._last_source = None
        self.node._last_observation_timestamp = None
        self.node._publisher = SimpleNamespace(publish=self.messages.append)
        self.node._transform = lambda message: np.array([
            message.position_camera_m.x, message.position_camera_m.y, message.position_camera_m.z])
        self.patcher = patch.object(estimator, "TargetState", FakeState, create=True)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def deliver(self, acquired: float, received: float, x: float = 0.0) -> SimpleNamespace:
        self.time = received
        message = observation(acquired, x)
        self.node._on_observation(message)
        return message

    def flush(self, timestamp: float) -> None:
        self.time = timestamp
        self.node._flush()

    def test_delayed_image_is_accepted_after_more_recent_output_prediction(self) -> None:
        self.deliver(0.0, 0.10)
        self.flush(0.13)
        self.flush(0.30)
        self.deliver(0.20, 0.35)
        self.flush(0.38)
        self.assertEqual(self.node._last_observation_timestamp, 0.2)
        self.assertEqual(self.node._manager.target._filter.timestamp, 0.2)
        self.assertEqual(self.messages[-1].state, FakeState.STATE_MEASURED)
        self.assertEqual(self.warnings, [])

    def test_out_of_order_stale_and_future_acquisitions_are_rejected(self) -> None:
        self.deliver(0.2, 0.25)
        self.flush(0.28)
        for acquired, received in ((0.1, 0.3), (0.3, 1.0), (1.5, 1.1)):
            self.deliver(acquired, received)
            self.flush(received + 0.03)
        self.assertEqual(self.node._last_observation_timestamp, 0.2)
        self.assertEqual(len(self.warnings), 3)
        self.assertIn("out-of-order", self.warnings[0])
        self.assertIn("stale", self.warnings[1])
        self.assertIn("future", self.warnings[2])

    def test_same_stamp_candidates_batch_before_unique_target_selection(self) -> None:
        self.deliver(0.0, 0.10)
        self.flush(0.10)
        self.assertEqual(self.messages, [])
        self.deliver(0.0, 0.105, x=30.0)
        self.flush(0.13)
        self.assertIsNone(self.node._manager.target)
        self.assertEqual(self.node._manager.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(self.messages[-1].state, FakeState.STATE_AMBIGUOUS)
        self.flush(0.2)
        self.assertEqual(self.messages[-1].state, FakeState.STATE_AMBIGUOUS)

    def test_selected_target_ambiguity_is_transported_through_output_predictions(self) -> None:
        self.deliver(1.0, 1.10)
        self.flush(1.13)
        original_id = self.messages[-1].track_id
        original_uuid = self.messages[-1].target_uuid
        self.deliver(1.2, 1.25)
        self.deliver(1.2, 1.255, x=30.0)
        self.flush(1.28)
        for timestamp in (1.28, 1.30, 1.40):
            self.flush(timestamp)
            self.assertEqual(self.messages[-1].state, FakeState.STATE_AMBIGUOUS)
            self.assertFalse(self.messages[-1].target_visible)
            self.assertEqual(self.messages[-1].track_id, original_id)
            self.assertEqual(self.messages[-1].target_uuid, original_uuid)
        self.deliver(1.4, 1.45, x=30.0)
        self.flush(1.48)
        self.assertEqual(self.messages[-1].state, FakeState.STATE_AMBIGUOUS)
        self.deliver(1.5, 1.55)
        self.flush(1.58)
        self.assertEqual(self.messages[-1].state, FakeState.STATE_MEASURED)
        self.assertEqual(self.messages[-1].track_id, original_id)
        self.assertEqual(self.messages[-1].target_uuid, original_uuid)

    def test_delayed_image_after_elapsed_loss_still_publishes_lost(self) -> None:
        self.deliver(1.0, 1.1)
        self.flush(1.13)
        identity = self.messages[-1].target_uuid
        self.flush(1.751)
        self.assertEqual(self.messages[-1].state, FakeState.STATE_LOST)
        self.deliver(1.7, 1.8)
        self.flush(1.83)
        self.assertEqual(self.messages[-1].state, FakeState.STATE_LOST)
        self.assertEqual(self.messages[-1].target_uuid, identity)

    def test_prediction_keeps_original_camera_header_and_full_covariance(self) -> None:
        source = self.deliver(0.0, 0.10)
        self.flush(0.13)
        self.flush(0.30)
        self.assertEqual(source.header.frame_id, "camera_optical")
        self.assertEqual(source.header.stamp.sec, 0)
        self.assertEqual(source.header.stamp.nanosec, 0)
        predicted = self.messages[-1]
        self.assertEqual(predicted.header.frame_id, "map")
        self.assertAlmostEqual(predicted.prediction_age_s, 0.30)
        self.assertEqual(predicted.state, FakeState.STATE_PREDICTED)
        self.assertEqual(len(predicted.covariance), 36)
        self.assertGreater(predicted.covariance[3], 0.0)


if __name__ == "__main__":
    unittest.main()
