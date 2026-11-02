"""Confidence tiers preserve physical identity without weakening 3-D gates."""

from __future__ import annotations

import unittest

import numpy as np

from uav_tracking.core import Detection, TargetManager, TargetMode, TargetStatus, TrackState


def detection(timestamp, *, confidence=.9, x=0.0, position=True, bbox=(0, 0, 20, 20), **metadata):
    return Detection(
        bbox, "car", confidence, timestamp, (x, 0.0, 5.0) if position else None,
        depth_stats={"valid_fraction": .95, "std": .02}, metadata=metadata,
    )


def manager(**overrides):
    kwargs = dict(
        mode=TargetMode.LOCKED_TARGET, min_hits=1,
        initialization_confidence_threshold=.45, maintenance_confidence_threshold=.25,
        association_mode="hybrid_3d", reject_ambiguous_associations=True,
        association_max_distance=2.0, max_coast_duration_s=.75,
        track_retention_duration_s=3.0, gate_threshold=9.21,
        kf_kwargs={"initial_position_covariance": .01, "initial_velocity_covariance": .01,
                   "process_acceleration_std": .5},
    )
    kwargs.update(overrides)
    return TargetManager(**kwargs)


def selected(**overrides):
    tracker = manager(**overrides)
    tracker.lock_detection(0, target_uuid="original-task")
    tracker.update([detection(0)], timestamp=0)
    return tracker


class ConfidenceTierValidationTests(unittest.TestCase):
    def test_thresholds_are_optional_as_a_pair_and_finite_ordered_numbers(self):
        for high, low in ((None, .25), (.45, None), (.2, .25), (1.1, .25),
                          (.45, -.1), (float("nan"), .25), (.45, float("inf")),
                          (True, .25), (.45, False)):
            with self.subTest(high=high, low=low), self.assertRaises(ValueError):
                manager(initialization_confidence_threshold=high,
                        maintenance_confidence_threshold=low)
        manager(initialization_confidence_threshold=0, maintenance_confidence_threshold=0)
        manager(initialization_confidence_threshold=1, maintenance_confidence_threshold=1)

    def test_disabled_api_retains_immediate_mode_and_birth_evidence_side_effects(self):
        tracker = TargetManager(min_hits=1)
        tracker._birth_evidence = [object()]
        self.assertFalse(tracker.lock_target(99))
        self.assertEqual(tracker.mode, TargetMode.LOCKED_TARGET)
        self.assertEqual(tracker._birth_evidence, [])
        tracker._birth_evidence = [object()]
        tracker.lock_detection(0)
        self.assertEqual(tracker._birth_evidence, [])
        tracker.update([detection(0, confidence=.1)], timestamp=0)
        self.assertIsNotNone(tracker.target)

    def test_low_and_high_boundaries_have_distinct_identity_permissions(self):
        tracker = selected()
        target_id = tracker.target.track_id
        result = tracker.update_with_result([detection(.1, confidence=.25)], timestamp=.1)
        self.assertEqual(result.target.track_id, target_id)
        self.assertEqual(result.target.last_measurement_timestamp, .1)
        self.assertEqual(tracker.target_uuid, "original-task")
        self.assertTrue(result.target.last_measurement_diagnostics["maintenance_only"])
        result = tracker.update_with_result([detection(.2, confidence=.249999)], timestamp=.2)
        self.assertEqual(result.target.last_measurement_timestamp, .1)
        self.assertEqual(len(result.tracks), 1)
        high = manager(mode=TargetMode.AUTO_UNIQUE)
        high.update([detection(0, confidence=.45)], timestamp=0)
        self.assertIsNotNone(high.target)

    def test_metadata_cannot_promote_a_weak_confidence_to_initialization(self):
        tracker = manager(mode=TargetMode.AUTO_UNIQUE)
        result = tracker.update_with_result(
            [detection(0, confidence=.35, maintenance_only=False)], timestamp=0)
        self.assertIsNone(result.target)
        self.assertEqual(result.tracks, ())


class MaintenanceMeasurementTests(unittest.TestCase):
    def test_confirmed_and_coasting_tracks_keep_the_original_task_in_all_association_modes(self):
        for mode in ("legacy", "iou_2d", "hybrid_3d"):
            with self.subTest(mode=mode):
                tracker = selected(association_mode=mode, reject_ambiguous_associations=False)
                target_id = tracker.target.track_id
                tracker.update([], timestamp=.1)
                result = tracker.update_with_result([detection(.2, confidence=.35, x=.01)], timestamp=.2)
                self.assertEqual(result.target.track_id, target_id)
                self.assertEqual(result.status, TargetStatus.REACQUIRED)
                self.assertEqual(result.target.last_measurement_timestamp, .2)
                self.assertEqual(result.target.confidence, .35)
                self.assertEqual(tracker.target_uuid, "original-task")
                self.assertEqual(len(result.tracks), 1)

    def test_supported_surface_flag_is_required_when_surface_recovery_is_enabled(self):
        for support in (None, False, 1, "true"):
            with self.subTest(support=support):
                tracker = selected()
                result = tracker.update_with_result([
                    detection(.1, confidence=.35, surface_recovery_enabled=True,
                              surface_measurement_supported=support)], timestamp=.1)
                self.assertEqual(result.target.last_measurement_timestamp, 0)
                self.assertFalse(result.target._matched_this_frame)
                self.assertEqual(result.associations, ())
        tracker = selected()
        result = tracker.update_with_result([
            detection(.1, confidence=.35, surface_recovery_enabled=True,
                      surface_measurement_supported=True)], timestamp=.1)
        self.assertEqual(result.target.last_measurement_timestamp, .1)

    def test_an_earlier_supported_surface_does_not_authorize_a_current_unknown(self):
        tracker = selected()
        tracker.update([detection(.1, confidence=.35, surface_recovery_enabled=True,
                                  surface_measurement_supported=True)], timestamp=.1)
        result = tracker.update_with_result([
            detection(.2, confidence=.35, surface_recovery_enabled=True,
                      surface_measurement_supported=False)], timestamp=.2)
        self.assertEqual(result.target.last_measurement_timestamp, .1)
        self.assertFalse(result.target._matched_this_frame)

    def test_required_surface_policy_fails_closed_when_either_optin_or_support_is_missing(self):
        for metadata in ({}, {"surface_recovery_enabled": True},
                         {"surface_measurement_supported": True},
                         {"surface_recovery_enabled": False, "surface_measurement_supported": True}):
            with self.subTest(metadata=metadata):
                tracker = selected(supported_birth_confirmation_required=True)
                result = tracker.update_with_result([
                    detection(.1, confidence=.35, **metadata)], timestamp=.1)
                self.assertEqual(result.target.last_measurement_timestamp, 0)
                self.assertFalse(result.target._matched_this_frame)
                self.assertEqual(result.associations, ())

    def test_missing_world_point_never_refreshes_even_with_supported_flag(self):
        tracker = selected()
        result = tracker.update_with_result([
            detection(.1, confidence=.35, position=False, surface_recovery_enabled=True,
                      surface_measurement_supported=True)], timestamp=.1)
        self.assertEqual(result.target.last_measurement_timestamp, 0)
        self.assertFalse(result.target._matched_this_frame)

    def test_weak_frames_cannot_confirm_a_tentative_track(self):
        tracker = selected(min_hits=2)
        self.assertEqual(tracker.target.state, TrackState.TENTATIVE)
        for acquired in (.1, .2):
            tracker.update([detection(acquired, confidence=.35)], timestamp=acquired)
        self.assertEqual(tracker.target.hits, 1)
        self.assertEqual(tracker.target.last_measurement_timestamp, 0)
        tracker.update([detection(.3)], timestamp=.3)
        self.assertEqual(tracker.target.state, TrackState.CONFIRMED)

    def test_weak_depth_cannot_initialize_a_filter_for_a_two_dimensional_track(self):
        tracker = manager()
        tracker.lock_detection(0)
        tracker.update([detection(0, position=False)], timestamp=0)
        result = tracker.update_with_result([detection(.1, confidence=.35)], timestamp=.1)
        self.assertFalse(result.target._filter.initialized)
        self.assertIsNone(result.target.last_measurement_timestamp)
        self.assertEqual(len(result.tracks), 1)

    def test_weak_frame_cannot_bypass_distance_gate_with_identical_box_in_legacy_or_iou(self):
        for mode in ("legacy", "iou_2d", "hybrid_3d"):
            with self.subTest(mode=mode):
                tracker = selected(association_mode=mode)
                tracker.target._filter.covariance = np.eye(6) * 100
                result = tracker.update_with_result([detection(.1, confidence=.35, x=3)], timestamp=.1)
                self.assertEqual(result.associations, ())
                self.assertEqual(result.target.last_measurement_timestamp, 0)
                self.assertEqual(len(result.tracks), 1)

    def test_weak_frame_cannot_bypass_mahalanobis_gate_when_within_distance_bound(self):
        for mode in ("legacy", "iou_2d", "hybrid_3d"):
            with self.subTest(mode=mode):
                tracker = selected(association_mode=mode)
                tracker.target._filter.covariance = np.eye(6) * 1e-6
                result = tracker.update_with_result([detection(.1, confidence=.35, x=.8)], timestamp=.1)
                self.assertEqual(result.associations, ())
                self.assertEqual(result.target.last_measurement_timestamp, 0)
                self.assertEqual(len(result.tracks), 1)

    def test_rejected_weak_measurements_and_projection_do_not_extend_loss_deadline(self):
        tracker = selected()
        for acquired in (.1, .2, .3, .4, .5, .6, .7):
            tracker.update([detection(acquired, confidence=.35, position=False)], timestamp=acquired)
        self.assertEqual(tracker.predict_with_result(.75).status, TargetStatus.COASTING)
        self.assertEqual(tracker.predict_with_result(.751).status, TargetStatus.LOST)
        self.assertEqual(tracker.target.last_measurement_timestamp, 0)

    def test_observed_weak_scores_bridge_a_synthetic_gap_with_the_same_uuid_and_deadline(self):
        # Actual measured confidence values; synthetic world points isolate
        # core behavior. This is not a replay or acceptance of the old flight.
        for estimator in ("raw", "ema", "fixed_kf", "adaptive_kf"):
            with self.subTest(estimator=estimator):
                tracker = manager(estimator_method=estimator)
                tracker.lock_detection(0, target_uuid="original-task")
                tracker.update([detection(30.6)], timestamp=30.6)
                target_id = tracker.target.track_id
                for acquired in (30.7, 30.8, 30.9):
                    tracker.update([], timestamp=acquired)
                for acquired, score in ((31.0, .413131237), (31.2, .380103946)):
                    tracker.update([detection(acquired, confidence=score,
                                              surface_recovery_enabled=True,
                                              surface_measurement_supported=True)], timestamp=acquired)
                result = tracker.predict_with_result(31.36)
                self.assertEqual(result.status, TargetStatus.COASTING)
                self.assertEqual(result.target.track_id, target_id)
                self.assertEqual(tracker.target_uuid, "original-task")
                self.assertEqual(result.target.last_measurement_timestamp, 31.2)
                self.assertEqual(len(result.tracks), 1)
                self.assertEqual(tracker.predict_with_result(31.951).status, TargetStatus.LOST)


class ConfidenceTierAssociationTests(unittest.TestCase):
    def test_high_and_weak_competitors_freeze_together_even_without_legacy_reject_policy(self):
        for order in ((.9, .35), (.35, .9), (.35, .35)):
            with self.subTest(order=order):
                tracker = selected(association_mode="legacy", reject_ambiguous_associations=False)
                result = tracker.update_with_result(
                    [detection(.1, confidence=c, x=.001 * i) for i, c in enumerate(order)], timestamp=.1)
                self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
                self.assertEqual(result.associations, ())
                self.assertEqual(result.target.last_measurement_timestamp, 0)
                self.assertEqual(len(result.tracks), 1)
                self.assertEqual(result.ambiguous_detection_indices, (0, 1))

    def test_two_tracks_one_weak_candidate_is_ambiguous_and_never_weak_backfilled(self):
        tracker = manager(association_mode="legacy", reject_ambiguous_associations=False)
        tracker.lock_detection(0, target_uuid="original-task")
        tracker.update([detection(0, x=0), detection(0, x=.1, bbox=(30, 0, 50, 20))], timestamp=0)
        result = tracker.update_with_result([detection(.1, confidence=.35, x=.05)], timestamp=.1)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.associations, ())
        self.assertEqual(result.ambiguous_track_ids, (1, 2))
        self.assertEqual(len(result.tracks), 2)

    def test_unrelated_weak_ambiguity_does_not_pause_the_selected_unique_component(self):
        tracker = manager(association_mode="legacy", reject_ambiguous_associations=False)
        tracker.lock_detection(0)
        tracker.update([detection(0, x=0), detection(0, x=10), detection(0, x=10.1)], timestamp=0)
        result = tracker.update_with_result([
            detection(.1, x=0, bbox=(100, 0, 120, 20)),
            detection(.1, confidence=.35, x=10.05)], timestamp=.1)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertEqual(result.target.last_measurement_timestamp, .1)
        self.assertEqual(result.ambiguous_track_ids, (2, 3))

    def test_legacy_high_only_assignment_is_unchanged_when_reject_is_disabled(self):
        tracker = selected(association_mode="legacy", reject_ambiguous_associations=False)
        result = tracker.update_with_result([detection(.1), detection(.1, x=.01)], timestamp=.1)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertEqual(result.ambiguous_track_ids, ())

    def test_below_floor_box_cannot_add_merge_uncertainty(self):
        tracker = manager()
        tracker.lock_detection(0)
        tracker.update([detection(0), detection(0, x=.1, bbox=(25, 0, 45, 20))], timestamp=0)
        result = tracker.update_with_result([
            detection(.1, confidence=.249, bbox=(-5, -5, 50, 25), x=.05)], timestamp=.1)
        self.assertEqual(result.ambiguous_track_ids, ())
        self.assertEqual(result.merge_uncertainty_detection_indices, ())
        self.assertEqual(result.target.last_measurement_timestamp, 0)

    def test_weak_unassigned_observations_never_create_ids_or_birth_evidence(self):
        tracker = selected(supported_birth_confirmation_required=True)
        for i in range(1, 5):
            acquired = i / 10
            result = tracker.update_with_result([
                detection(acquired),
                detection(acquired, confidence=.35, x=10,
                          surface_recovery_enabled=True, surface_measurement_supported=True)], timestamp=acquired)
            self.assertEqual(len(result.tracks), 1)
            self.assertEqual(tracker._birth_evidence, [])
            self.assertIn((1, "maintenance_only_no_birth"), result.spawn_deferred_reasons)
        tracker.update([detection(.5), detection(.5, x=10, bbox=(60, 0, 80, 20),
                                               surface_recovery_enabled=True,
                                               surface_measurement_supported=True)], timestamp=.5)
        self.assertEqual([t.track_id for t in tracker.tracks], [1, 2])

    def test_auto_unique_ignores_unassigned_weak_noise_but_counts_maintained_other_track(self):
        tracker = manager(mode=TargetMode.AUTO_UNIQUE)
        tracker.update([detection(0), detection(0, confidence=.35, x=10)], timestamp=0)
        self.assertIsNotNone(tracker.target)
        self.assertEqual(len(tracker.tracks), 1)
        tracker.update([detection(.1), detection(.1, x=10)], timestamp=.1)
        result = tracker.update_with_result([detection(.2), detection(.2, x=10, confidence=.35)], timestamp=.2)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(len(result.associations), 2)
        self.assertEqual(tracker.target.track_id, 1)

    def test_auto_unique_cannot_start_a_task_from_only_weak_maintenance(self):
        tracker = manager(mode=TargetMode.AUTO_UNIQUE)
        tracker.update([detection(0), detection(0, x=10)], timestamp=0)
        self.assertIsNone(tracker.target)
        result = tracker.update_with_result([detection(.1, confidence=.35)], timestamp=.1)
        self.assertIsNone(result.target)
        self.assertEqual(result.tracks[0].last_measurement_timestamp, .1)

    def test_auto_unique_one_weak_box_feasible_for_two_tracks_is_ambiguous(self):
        tracker = manager(mode=TargetMode.AUTO_UNIQUE)
        tracker.update([detection(0), detection(0, x=.1)], timestamp=0)
        self.assertTrue(tracker.lock_target(1, target_uuid="original-task"))
        tracker.set_mode(TargetMode.AUTO_UNIQUE, clear_target=False)
        result = tracker.update_with_result([detection(.1, confidence=.35, x=.05)], timestamp=.1)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertFalse(result.target._matched_this_frame)


class ConfidenceTierSelectionTests(unittest.TestCase):
    def test_weak_box_selection_is_staged_without_mutating_old_identity_or_mode(self):
        tracker = selected()
        target_id = tracker.target.track_id
        tracker.lock_detection(0, target_uuid="weak-request")
        self.assertEqual(tracker.target.track_id, target_id)
        self.assertEqual(tracker.target_uuid, "original-task")
        result = tracker.update_with_result([detection(.1, confidence=.35)], timestamp=.1)
        self.assertEqual(result.target.track_id, target_id)
        self.assertEqual(tracker.target_uuid, "original-task")
        self.assertEqual(len(result.tracks), 1)

    def test_empty_or_out_of_range_request_is_consumed_once_without_later_binding(self):
        for index, observations in ((0, []), (2, [detection(.1)]),
                                    (0, [detection(.1, confidence=.35)])):
            with self.subTest(index=index, observations=observations):
                tracker = selected()
                tracker.lock_detection(index, target_uuid="must-not-bind-later")
                tracker.update(observations, timestamp=.1)
                tracker.update([detection(.2)], timestamp=.2)
                self.assertEqual(tracker.target_uuid, "original-task")

    def test_explicit_high_box_selection_commits_only_at_the_matching_acquisition(self):
        tracker = selected()
        tracker.lock_detection(0, target_uuid="explicit-high-task")
        self.assertEqual(tracker.target_uuid, "original-task")
        tracker.update([detection(.1)], timestamp=.1)
        self.assertEqual(tracker.target_uuid, "explicit-high-task")

    def test_weak_selection_apis_cannot_clear_the_original_lost_latch(self):
        for api in ("box", "initialize_box", "update_index", "track", "initialize_track"):
            with self.subTest(api=api):
                tracker = selected()
                target_id = tracker.target.track_id
                tracker.predict_with_result(.751)
                if api == "box":
                    tracker.lock_detection(0, target_uuid="forbidden")
                elif api == "initialize_box":
                    tracker.initialize_target(detection_index=0, target_uuid="forbidden")
                elif api == "track":
                    self.assertFalse(tracker.lock_target(target_id, target_uuid="forbidden"))
                elif api == "initialize_track":
                    tracker.initialize_target(track_id=target_id, target_uuid="forbidden")
                result = tracker.update_with_result([detection(.7, confidence=.35)], timestamp=.7,
                                                    target_index=0 if api == "update_index" else None)
                self.assertEqual(result.status, TargetStatus.LOST)
                self.assertEqual(result.target.track_id, target_id)
                self.assertEqual(tracker.target_uuid, "original-task")
                self.assertEqual(result.target.last_measurement_timestamp, 0)
                self.assertTrue(tracker._requires_reselection)
                self.assertEqual(len(result.tracks), 1)

    def test_later_high_measurement_without_explicit_selection_cannot_revive_the_lost_task(self):
        for mode in (TargetMode.AUTO_UNIQUE, TargetMode.LOCKED_TARGET):
            with self.subTest(mode=mode):
                tracker = selected()
                tracker.set_mode(mode, clear_target=False)
                original_id = tracker.target.track_id
                tracker.predict_with_result(.751)
                result = tracker.update_with_result([detection(.7)], timestamp=.7)
                self.assertEqual(result.status, TargetStatus.LOST)
                self.assertEqual(result.target.track_id, original_id)
                self.assertEqual(result.target.last_measurement_timestamp, 0)
                self.assertEqual(tracker.target_uuid, "original-task")

    def test_gated_high_outlier_is_not_current_initialization_evidence(self):
        tracker = selected(association_mode="legacy")
        tracker.target._filter.covariance = np.eye(6) * 1e-6
        result = tracker.update_with_result([detection(.1, x=.8)], timestamp=.1)
        self.assertEqual(len(result.associations), 1)
        self.assertEqual(tracker.target.rejected_measurements, 1)
        self.assertEqual(tracker.target.last_measurement_diagnostics["reason"], "MAHALANOBIS_GATE")
        self.assertFalse(tracker.lock_target(1, target_uuid="outlier-request"))
        self.assertEqual(tracker.target_uuid, "original-task")

    def test_high_box_request_cannot_bind_an_assignment_whose_kf_rejected_the_measurement(self):
        tracker = selected(association_mode="legacy")
        tracker.target._filter.covariance = np.eye(6) * 1e-6
        tracker.lock_detection(0, target_uuid="rejected-high-request")
        result = tracker.update_with_result([detection(.1, x=.8)], timestamp=.1)
        self.assertEqual(len(result.associations), 1)
        self.assertEqual(result.tracks[0].rejected_measurements, 1)
        self.assertIsNone(result.target)
        self.assertNotEqual(tracker.target_uuid, "rejected-high-request")

    def test_weak_never_revives_an_unselected_lost_track(self):
        tracker = manager()
        tracker.update([detection(0)], timestamp=0)
        tracker.predict_with_result(.751)
        result = tracker.update_with_result([detection(.8, confidence=.35)], timestamp=.8)
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(result.tracks[0].state, TrackState.LOST)
        self.assertEqual(result.tracks[0].last_measurement_timestamp, 0)

    def test_pending_track_id_requires_current_high_evidence_and_preserves_old_task(self):
        tracker = selected()
        self.assertFalse(tracker.lock_target(2, target_uuid="pending-high-task"))
        tracker.update([detection(.1), detection(.1, x=10)], timestamp=.1)
        self.assertEqual(tracker.target.track_id, 2)
        self.assertEqual(tracker.target_uuid, "pending-high-task")
        tracker.update([detection(.2), detection(.2, x=10, confidence=.35)], timestamp=.2)
        self.assertFalse(tracker.lock_target(2, target_uuid="weak-rebind"))
        tracker.update([detection(.3), detection(.3, x=10, confidence=.35)], timestamp=.3)
        self.assertEqual(tracker.target_uuid, "pending-high-task")
        tracker.update([detection(.4), detection(.4, x=10)], timestamp=.4)
        self.assertEqual(tracker.target_uuid, "weak-rebind")

    def test_retained_high_box_without_current_match_cannot_bind_a_new_task(self):
        tracker = selected()
        tracker.update([], timestamp=.1)
        self.assertFalse(tracker.lock_target(1, target_uuid="must-wait"))
        self.assertEqual(tracker.target_uuid, "original-task")
        tracker.update([detection(.2, confidence=.35)], timestamp=.2)
        self.assertEqual(tracker.target_uuid, "original-task")
        tracker.update([detection(.3)], timestamp=.3)
        self.assertEqual(tracker.target_uuid, "must-wait")

    def test_explicit_high_reselection_after_loss_makes_a_new_task(self):
        tracker = selected()
        tracker.predict_with_result(.751)
        tracker.lock_detection(0, target_uuid="new-high-task")
        result = tracker.update_with_result([detection(.8)], timestamp=.8)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertEqual(tracker.target_uuid, "new-high-task")
        self.assertFalse(tracker._requires_reselection)
        self.assertEqual(tracker.target.last_measurement_timestamp, .8)

    def test_reset_clear_and_mode_change_discard_a_staged_box_request(self):
        for operation in ("reset", "unlock", "mode"):
            with self.subTest(operation=operation):
                tracker = selected()
                tracker.lock_detection(0, target_uuid="stale-request")
                if operation == "reset":
                    tracker.reset()
                elif operation == "unlock":
                    tracker.unlock_target()
                else:
                    tracker.set_mode(TargetMode.LOCKED_TARGET)
                tracker.update([detection(.1)], timestamp=.1)
                self.assertIsNone(tracker.target)
                self.assertIsNone(tracker.target_uuid)


if __name__ == "__main__":
    unittest.main()
