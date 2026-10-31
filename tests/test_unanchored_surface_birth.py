"""Behavior checks for unanchored, unsupported RGB-D birth proposals.

Inputs are synthetic. Humble42's observed unsupported birth motivated these
cases; they do not restore its private association priors or replay that flight.
"""
from dataclasses import replace
import unittest

from uav_tracking.core import Detection, TargetManager, TargetMode, TargetStatus


def observation(time, x=0., *, supported=True, enabled=True, box=(0., 0., 20., 20.)):
    return Detection(box, "car", .9, time, (x, 0., 1.),
        depth_stats={"valid_fraction": 1., "std": .05},
        metadata={"surface_recovery_enabled": enabled,
                  "surface_measurement_supported": supported, "acquisition_epoch": 0})


def manager(**kwargs):
    settings = dict(mode=TargetMode.LOCKED_TARGET, min_hits=1,
        association_mode="hybrid_3d", reject_ambiguous_associations=True,
        association_max_distance=1.5, gate_threshold=9.21,
        max_coast_duration_s=.75, track_retention_duration_s=3.,
        supported_birth_confirmation_required=True,
        kf_kwargs={"measurement_noise_std": [.05, .05, .1],
                   "initial_position_covariance": .01,
                   "initial_velocity_covariance": .01})
    settings.update(kwargs)
    return TargetManager(**settings)


def selected():
    result = manager()
    result.lock_detection(0, target_uuid="selected-task")
    result.update_with_result([observation(0.)], timestamp=0.)
    return result


FAR_BOX = (80., 0., 100., 20.)


class UnanchoredSurfaceBirthTests(unittest.TestCase):
    def test_unsupported_only_roi_does_not_spawn_while_selected_coasts(self):
        tracking = selected()
        for time in (.1, .2, .3):
            candidate = observation(time, 4., supported=False, box=FAR_BOX)
            result = tracking.update_with_result([candidate], timestamp=time)
            self.assertEqual([track.track_id for track in result.tracks], [1])
            self.assertEqual(result.associations, ())
            self.assertEqual(dict(result.spawn_deferred_reasons), {0: "birth_surface_support_unknown"})
            self.assertEqual(result.target.last_measurement_timestamp, 0.)
            self.assertEqual(tracking.target_uuid, "selected-task")
            self.assertEqual(tracking._next_track_id, 2)

    def test_separate_unsupported_roi_is_deferred_when_selected_is_measured(self):
        tracking = selected()
        result = tracking.update_with_result([observation(.1, .01),
            observation(.1, 4., supported=False, box=FAR_BOX)], timestamp=.1)
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(result.associations, ((1, 0),))
        self.assertEqual(result.target.last_measurement_timestamp, .1)
        self.assertEqual(result.status, TargetStatus.TRACKING)

    def test_real_entry_can_be_born_when_independent_surface_support_arrives(self):
        tracking = selected()
        tracking.update_with_result([observation(.1),
            observation(.1, 4., supported=False, box=FAR_BOX)], timestamp=.1)
        result = tracking.update_with_result([observation(.2),
            observation(.2, 4., supported=True, box=FAR_BOX)], timestamp=.2)
        self.assertEqual([track.track_id for track in result.tracks], [1, 2])
        self.assertEqual(result.tracks[1].last_measurement_timestamp, .2)
        self.assertEqual(result.target.track_id, 1)
        self.assertEqual(tracking.target_uuid, "selected-task")

    def test_existing_track_still_accepts_supported_policy_fallback_measurement(self):
        tracking = selected()
        result = tracking.update_with_result([observation(.1, .01, supported=False)], timestamp=.1)
        self.assertEqual(result.associations, ((1, 0),))
        self.assertEqual(result.target.last_measurement_timestamp, .1)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertEqual(result.spawn_deferred_detection_indices, ())

    def test_two_feasible_observations_still_freeze_existing_selected_track(self):
        tracking = selected()
        result = tracking.update_with_result([observation(.1),
            observation(.1, .02, supported=False, box=FAR_BOX)], timestamp=.1)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.ambiguous_track_ids, (1,))
        self.assertEqual(result.ambiguous_detection_indices, (0, 1))
        self.assertEqual(result.target.last_measurement_timestamp, 0.)
        self.assertEqual(len(result.tracks), 1)

    def test_two_existing_tracks_with_one_feasible_roi_still_freeze(self):
        tracking = manager()
        tracking.lock_detection(0, target_uuid="selected-task")
        tracking.update_with_result([observation(0.), observation(0., .2, box=FAR_BOX)], timestamp=0.)
        result = tracking.update_with_result([observation(.1, .1, supported=False)], timestamp=.1)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.ambiguous_track_ids, (1, 2))
        self.assertEqual(result.associations, ())

    def test_unseen_surface_does_not_extend_prediction_or_restore_lost_task(self):
        tracking = selected()
        result = tracking.update_with_result([
            observation(.76, 4., supported=False, box=FAR_BOX)], timestamp=.76)
        self.assertEqual(result.status, TargetStatus.LOST)
        self.assertEqual(result.target.last_measurement_timestamp, 0.)
        result = tracking.update_with_result([
            observation(.8, 4., box=FAR_BOX)], timestamp=.8)
        self.assertEqual(result.status, TargetStatus.LOST)
        self.assertEqual(tracking.target_uuid, "selected-task")
        self.assertEqual(result.target.track_id, 1)

    def test_unique_mode_waits_for_surface_support_and_keeps_candidate_ambiguity(self):
        tracking = manager(mode=TargetMode.AUTO_UNIQUE)
        first = tracking.update_with_result([observation(0., supported=False)], timestamp=0.)
        self.assertIsNone(first.target)
        supported = tracking.update_with_result([observation(.1)], timestamp=.1)
        self.assertIsNotNone(supported.target)
        multiple = tracking.update_with_result([observation(.2),
            observation(.2, 4., supported=False, box=FAR_BOX)], timestamp=.2)
        self.assertEqual(multiple.status, TargetStatus.AMBIGUOUS)

    def test_explicit_image_selection_retains_initialization_authority(self):
        tracking = manager()
        tracking.lock_detection(0, target_uuid="explicit-selection")
        result = tracking.update_with_result([observation(0., supported=False)], timestamp=0.)
        self.assertIsNotNone(result.target)
        self.assertEqual(result.target.last_measurement_timestamp, 0.)
        self.assertEqual(tracking.target_uuid, "explicit-selection")

    def test_policy_disabled_or_absent_keeps_original_unanchored_birth(self):
        for metadata in ({}, {"surface_recovery_enabled": False,
                              "surface_measurement_supported": False}):
            with self.subTest(metadata=metadata):
                tracking = manager()
                candidate = replace(observation(0.), metadata=metadata)
                result = tracking.update_with_result([candidate], timestamp=0.)
                self.assertEqual(len(result.tracks), 1)
                self.assertEqual(result.spawn_deferred_detection_indices, ())


if __name__ == "__main__":
    unittest.main()
