"""Tests for the middleware-independent tracking core.

The file uses ``unittest`` so it can run in a minimal Python environment:
``python -m unittest discover -s tests -v``.  It is also compatible with
pytest when that is available.
"""

from __future__ import annotations

import unittest

import numpy as np

from uav_tracking.core import (
    CameraIntrinsics,
    ConstantVelocityKalman3D,
    Detection,
    TargetManager,
    TargetMode,
    TargetStatus,
    TrackState,
    bbox_iou,
    depth_roi_stats,
    pinhole_backproject,
)


class GeometryTests(unittest.TestCase):
    def test_bbox_iou(self) -> None:
        self.assertAlmostEqual(bbox_iou((0, 0, 2, 2), (1, 1, 3, 3)), 1 / 7)
        self.assertEqual(bbox_iou((0, 0, 1, 1), (2, 2, 3, 3)), 0.0)

    def test_depth_stats_ignore_invalid_values_and_scale(self) -> None:
        depth = np.array([[1000, 0, np.nan], [2000, 3000, 99999]], dtype=float)
        stats = depth_roi_stats(depth, (0, 0, 3, 2), depth_scale=0.001, max_depth=4.0)
        self.assertEqual(stats.valid_count, 3)
        self.assertEqual(stats.total_count, 6)
        self.assertAlmostEqual(stats.valid_fraction, 0.5)
        self.assertAlmostEqual(stats.median, 2.0)

    def test_depth_stats_can_use_the_whole_image_as_an_roi(self) -> None:
        stats = depth_roi_stats(np.array([[1.0, 2.0], [0.0, np.nan]]))
        self.assertEqual(stats.valid_count, 2)
        self.assertEqual(stats.total_count, 4)

    def test_pinhole_backprojection(self) -> None:
        point = pinhole_backproject((350, 260), 2.0, CameraIntrinsics(500, 500, 320, 240))
        np.testing.assert_allclose(point, [0.12, 0.08, 2.0])
        legacy = pinhole_backproject(350, 260, 2.0, 500, 500, 320, 240)
        np.testing.assert_allclose(legacy, point)
        keyword = pinhole_backproject(u=350, v=260, depth=2.0, fx=500, fy=500, cx=320, cy=240)
        np.testing.assert_allclose(keyword, point)


class KalmanTests(unittest.TestCase):
    def test_constant_velocity_prediction(self) -> None:
        filter_ = ConstantVelocityKalman3D(
            process_acceleration_std=0.05,
            measurement_noise_std=0.01,
            initial_position_covariance=0.01,
            initial_velocity_covariance=0.01,
        )
        filter_.initialize([0, 0, 2], velocity=[1, 0, 0], timestamp=0.0)
        filter_.predict(timestamp=1.0)
        np.testing.assert_allclose(filter_.position, [1, 0, 2], atol=1e-8)
        np.testing.assert_allclose(filter_.x, filter_.state)
        np.testing.assert_allclose(filter_.P, filter_.covariance)

    def test_outlier_is_rejected_by_mahalanobis_gate(self) -> None:
        filter_ = ConstantVelocityKalman3D(
            process_acceleration_std=0.01,
            measurement_noise_std=0.01,
            initial_position_covariance=0.001,
            initial_velocity_covariance=0.001,
            gate_threshold=5.0,
        )
        filter_.initialize([0, 0, 0], timestamp=0.0)
        filter_.predict(timestamp=0.1)
        accepted = filter_.update([100, 100, 100], timestamp=0.1)
        self.assertFalse(accepted)
        self.assertGreater(filter_.last_mahalanobis_distance or 0, 5.0)
        np.testing.assert_allclose(filter_.position, [0, 0, 0], atol=0.01)

    def test_low_depth_quality_inflates_measurement_noise(self) -> None:
        filter_ = ConstantVelocityKalman3D(measurement_noise_std=0.1)
        good = filter_.measurement_covariance(quality=1.0)
        poor = filter_.measurement_covariance(quality=0.1)
        self.assertTrue(np.all(np.diag(poor) > np.diag(good)))


def detection(x: float, *, class_id: str = "person", z: float = 5.0, timestamp: float = 0.0) -> Detection:
    return Detection((x, 0, x + 10, 10), class_id, 0.95, timestamp, (x / 10, 0, z))


class TargetManagerTests(unittest.TestCase):
    def test_auto_unique_selects_only_one_confirmed_candidate(self) -> None:
        manager = TargetManager(TargetMode.AUTO_UNIQUE, min_hits=1)
        target = manager.update([detection(0)])
        self.assertIsNotNone(target)
        self.assertEqual(manager.status, TargetStatus.TRACKING)

    def test_auto_unique_is_ambiguous_and_does_not_switch(self) -> None:
        manager = TargetManager(TargetMode.AUTO_UNIQUE, min_hits=1)
        self.assertIsNone(manager.update([detection(0), detection(30)]))
        self.assertEqual(manager.status, TargetStatus.AMBIGUOUS)
        # Once one target has been selected, a later distractor cannot replace it.
        manager.reset()
        first = manager.update([detection(0)])
        self.assertIsNotNone(first)
        original_id = first.track_id
        original_uuid = manager.target_uuid
        manager.update([detection(0), detection(30)])
        self.assertEqual(manager.target_track_id, original_id)
        self.assertEqual(manager.target_uuid, original_uuid)
        self.assertEqual(manager.status, TargetStatus.AMBIGUOUS)

    def test_auto_unique_ambiguity_survives_predictions_until_original_is_unique(self) -> None:
        manager = TargetManager(TargetMode.AUTO_UNIQUE, min_hits=1, max_coast_frames=5)
        original = manager.update([detection(0, timestamp=1.0)], timestamp=1.0)
        original_uuid = manager.target_uuid
        multiple = manager.update_with_result(
            [detection(0, timestamp=1.1), detection(30, timestamp=1.1)], timestamp=1.1)
        self.assertEqual(multiple.status, TargetStatus.AMBIGUOUS)
        for timestamp in (1.11, 1.12, 1.13):
            self.assertEqual(manager.predict_with_result(timestamp).status, TargetStatus.AMBIGUOUS)
        self.assertEqual(manager.update_with_result([], timestamp=1.15).status, TargetStatus.AMBIGUOUS)
        # Only the distractor remains: never follow it or clear the pause.
        wrong = manager.update_with_result([detection(30, timestamp=1.2)], timestamp=1.2)
        self.assertEqual(wrong.status, TargetStatus.AMBIGUOUS)
        self.assertFalse(wrong.target._matched_this_frame)
        self.assertEqual(manager.predict_with_result(1.21).status, TargetStatus.AMBIGUOUS)
        recovered = manager.update_with_result([detection(0, timestamp=1.3)], timestamp=1.3)
        self.assertIn(recovered.status, (TargetStatus.TRACKING, TargetStatus.REACQUIRED))
        self.assertEqual(recovered.target.track_id, original.track_id)
        self.assertEqual(manager.target_uuid, original_uuid)
        self.assertEqual(manager.predict_with_result(1.31).status, TargetStatus.COASTING)

    def test_auto_unique_initial_ambiguity_never_selects_on_timer_or_empty_frame(self) -> None:
        manager = TargetManager(TargetMode.AUTO_UNIQUE, min_hits=1)
        manager.update([detection(0, timestamp=1.0), detection(30, timestamp=1.0)], timestamp=1.0)
        self.assertIsNone(manager.target_uuid)
        self.assertEqual(manager.predict_with_result(1.1).status, TargetStatus.AMBIGUOUS)
        self.assertEqual(manager.update_with_result([], timestamp=1.2).status, TargetStatus.AMBIGUOUS)
        self.assertIsNone(manager.target)
        self.assertIsNone(manager.target_uuid)
        result = manager.update_with_result([detection(0, timestamp=1.3)], timestamp=1.3)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertIsNotNone(manager.target_uuid)

    def test_second_candidate_counts_even_without_depth_or_confirmation(self) -> None:
        manager = TargetManager(TargetMode.AUTO_UNIQUE, min_hits=2)
        manager.update([detection(0, timestamp=1.0)], timestamp=1.0)
        original = manager.update([detection(0, timestamp=1.1)], timestamp=1.1)
        self.assertIsNotNone(original)
        result = manager.update_with_result([
            detection(0, timestamp=1.2), Detection((30, 0, 40, 10), "person", 0.95, 1.2, None),
        ], timestamp=1.2)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.target.track_id, original.track_id)

    def test_locked_target_can_follow_selected_instance_among_multiple_candidates(self) -> None:
        manager = TargetManager(TargetMode.LOCKED_TARGET, min_hits=1)
        manager.lock_detection(0, target_uuid="explicit-person")
        original = manager.update([detection(0, timestamp=1.0)], timestamp=1.0)
        result = manager.update_with_result(
            [detection(0, timestamp=1.1), detection(30, timestamp=1.1)], timestamp=1.1)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertEqual(result.target.track_id, original.track_id)
        self.assertEqual(manager.target_uuid, "explicit-person")
        self.assertEqual(manager.predict_with_result(1.2).status, TargetStatus.COASTING)

    def test_locked_mode_requires_explicit_target_and_coasts_then_loses(self) -> None:
        manager = TargetManager(
            TargetMode.LOCKED_TARGET,
            min_hits=1,
            max_coast_frames=1,
            max_lost_frames=2,
        )
        manager.lock_detection(0)
        target = manager.update([detection(0)])
        self.assertIsNotNone(target)
        manager.update([])
        self.assertEqual(manager.status, TargetStatus.COASTING)
        manager.update([])
        self.assertEqual(manager.status, TargetStatus.LOST)
        self.assertEqual(manager.target_track_id, target.track_id)

    def test_locked_mode_does_not_switch_to_distractor(self) -> None:
        manager = TargetManager(TargetMode.LOCKED_TARGET, min_hits=1, max_coast_frames=1, max_lost_frames=3)
        manager.lock_detection(0)
        target = manager.update([detection(0)])
        self.assertIsNotNone(target)
        original_id = target.track_id
        manager.update([detection(30)])
        self.assertEqual(manager.target_track_id, original_id)
        self.assertEqual(manager.status, TargetStatus.COASTING)

    def test_long_loss_requires_explicit_reselection(self) -> None:
        manager = TargetManager(TargetMode.LOCKED_TARGET, min_hits=1, max_coast_frames=1, max_lost_frames=2)
        manager.lock_detection(0)
        original = manager.update([detection(0, timestamp=0.0)])
        self.assertIsNotNone(original)
        original_id = original.track_id
        manager.update([], timestamp=0.1)
        manager.update([], timestamp=0.2)
        self.assertEqual(manager.status, TargetStatus.LOST)
        # A returning detection cannot silently reactivate the old task.
        returning = manager.update([detection(0, timestamp=0.3)], timestamp=0.3)
        self.assertEqual(manager.status, TargetStatus.LOST)
        self.assertEqual(manager.target_track_id, original_id)
        self.assertIsNotNone(returning)
        # An explicit new box selection is required to resume control.
        manager.lock_detection(0)
        resumed = manager.update([detection(0, timestamp=0.4)], timestamp=0.4)
        self.assertIsNotNone(resumed)
        self.assertEqual(manager.status, TargetStatus.TRACKING)

    def test_short_occlusion_reacquires_same_track(self) -> None:
        manager = TargetManager(TargetMode.AUTO_UNIQUE, min_hits=1, max_coast_frames=2, max_lost_frames=4)
        target = manager.update([detection(0, timestamp=0.0)])
        self.assertIsNotNone(target)
        track_id = target.track_id
        manager.update([], timestamp=0.1)
        result = manager.update_with_result([detection(0.5, timestamp=0.2)], timestamp=0.2)
        self.assertEqual(result.target.track_id, track_id)
        self.assertEqual(result.status, TargetStatus.REACQUIRED)
        self.assertTrue(result.reacquired)

    def test_mode_names_are_case_insensitive(self) -> None:
        manager = TargetManager("AUTO_UNIQUE", min_hits=1)
        self.assertEqual(manager.mode, TargetMode.AUTO_UNIQUE)
        self.assertFalse(manager.lock_target(99))
        self.assertEqual(manager.mode, TargetMode.LOCKED_TARGET)

    def test_rejected_depth_does_not_replace_track_box(self) -> None:
        manager = TargetManager(
            TargetMode.AUTO_UNIQUE,
            min_hits=1,
            kf_kwargs={
                "measurement_noise_std": 0.01,
                "initial_position_covariance": 0.001,
                "initial_velocity_covariance": 0.001,
                "gate_threshold": 5.0,
            },
        )
        target = manager.update([detection(0, timestamp=0.0)])
        self.assertIsNotNone(target)
        old_box = target.bbox
        manager.update([detection(30, timestamp=0.1)])
        self.assertEqual(manager.target.bbox, old_box)
        self.assertEqual(manager.status, TargetStatus.COASTING)

    def test_invalid_depth_keeps_2d_association_without_refreshing_3d_age(self) -> None:
        manager = TargetManager(TargetMode.AUTO_UNIQUE, min_hits=1)
        first = manager.update([detection(0, timestamp=0.0)], timestamp=0.0)
        self.assertIsNotNone(first)
        self.assertEqual(first.last_measurement_timestamp, 0.0)
        invalid_depth = Detection((0.2, 0, 10.2, 10), "person", 0.9, 0.1, None)
        second = manager.update([invalid_depth], timestamp=0.1)
        self.assertIsNotNone(second)
        self.assertTrue(second._matched_this_frame)
        self.assertEqual(second.last_measurement_timestamp, 0.0)
        self.assertAlmostEqual(second.last_update_timestamp, 0.1)

    def test_manager_frame_timestamp_overrides_default_detection_timestamp(self) -> None:
        manager = TargetManager(TargetMode.AUTO_UNIQUE, min_hits=1)
        manager.update([detection(0)], timestamp=1.0)
        target = manager.update([detection(1)], timestamp=1.1)
        self.assertIsNotNone(target)
        self.assertAlmostEqual(target.last_update_timestamp, 1.1)

    def test_manager_accepts_single_or_empty_detection_input(self) -> None:
        manager = TargetManager(TargetMode.AUTO_UNIQUE, min_hits=1)
        target = manager.update(detection(0))
        self.assertIsNotNone(target)
        manager.update(None)
        self.assertEqual(manager.status, TargetStatus.COASTING)

    def test_empty_frame_coast_predicts_once(self) -> None:
        manager = TargetManager(
            TargetMode.AUTO_UNIQUE,
            min_hits=1,
            max_coast_frames=2,
            kf_kwargs={
                "process_acceleration_std": 0.001,
                "initial_position_covariance": 0.001,
                "initial_velocity_covariance": 0.001,
            },
        )
        first = Detection((0, 0, 10, 10), "person", 1.0, 0.0, (0, 0, 0), metadata={"velocity": 1})
        manager.update([first], timestamp=0.0)
        # Inject a known velocity into the public filter for a deterministic
        # check of one default-dt prediction per empty frame.
        track = manager.target
        self.assertIsNotNone(track)
        track._filter.state[3] = 1.0
        before = track.position_3d[0]
        manager.update([])
        after = manager.target.position_3d[0]
        self.assertAlmostEqual(after - before, track._filter.default_dt, places=6)
        self.assertAlmostEqual(manager.last_result.timestamp, track._filter.timestamp, places=6)


if __name__ == "__main__":
    unittest.main()

