"""Independent new-birth boundaries, synthetic data without simulator IDs."""
from dataclasses import replace
import unittest

from uav_tracking.core import Detection, TargetManager, TargetMode, TargetStatus


def observation(timestamp, x=0., *, box=(0., 0., 20., 20.), metadata=None):
    return Detection(box, "car", .9, timestamp, (x, 0., 1.),
                     depth_stats={"valid_fraction": 1., "std": .05},
                     metadata=metadata if metadata is not None else {
                         "surface_recovery_enabled": True,
                         "surface_measurement_supported": True,
                         "acquisition_epoch": 0})


def manager(**changes):
    settings = dict(mode=TargetMode.AUTO_UNIQUE, min_hits=1,
                    association_mode="hybrid_3d", reject_ambiguous_associations=True,
                    association_max_distance=1.5, gate_threshold=9.21,
                    max_coast_duration_s=.75, track_retention_duration_s=3.,
                    supported_birth_confirmation_required=True,
                    kf_kwargs={"measurement_noise_std": [.05, .05, .1],
                               "initial_position_covariance": .01,
                               "initial_velocity_covariance": .01})
    settings.update(changes)
    return TargetManager(**settings)


UNSUPPORTED = {"surface_recovery_enabled": True, "surface_measurement_supported": False}
FAR_BOX = (80., 0., 100., 20.)


class IndependentUnanchoredBirthTests(unittest.TestCase):
    def test_explicit_recovery_optin_requires_actual_true_support_without_constructor_flag(self):
        for support in [None, False, 1, "true", "absent"]:
            with self.subTest(support=support):
                metadata = {"surface_recovery_enabled": True}
                if support != "absent":
                    metadata["surface_measurement_supported"] = support
                tracking = manager(supported_birth_confirmation_required=False)
                result = tracking.update_with_result([observation(0., metadata=metadata)], timestamp=0.)
                self.assertEqual(result.tracks, ())
                self.assertIsNone(result.target)
                self.assertEqual(dict(result.spawn_deferred_reasons), {0: "birth_surface_support_unknown"})
                self.assertEqual(tracking._next_track_id, 1)

    def test_missing_or_nonboolean_optin_retains_unanchored_legacy_compatibility(self):
        for enabled in [None, False, 1, "true", "absent"]:
            with self.subTest(enabled=enabled):
                metadata = {"surface_measurement_supported": False}
                if enabled != "absent":
                    metadata["surface_recovery_enabled"] = enabled
                tracking = manager()
                result = tracking.update_with_result([observation(0., metadata=metadata)], timestamp=0.)
                self.assertEqual(len(result.tracks), 1)
                self.assertIsNotNone(result.target)
                self.assertEqual(result.spawn_deferred_reasons, ())

    def test_gate_remains_scoped_to_hybrid_association_with_ambiguity_protection(self):
        for changes in [{"association_mode": "iou_2d"}, {"association_mode": "legacy"},
                        {"reject_ambiguous_associations": False}]:
            with self.subTest(changes=changes):
                tracking = manager(**changes)
                result = tracking.update_with_result([observation(0., metadata=UNSUPPORTED)], timestamp=0.)
                self.assertEqual(len(result.tracks), 1)
                self.assertEqual(result.spawn_deferred_reasons, ())

    def test_explicit_selection_of_second_unsupported_box_preserves_only_requested_birth(self):
        tracking = manager(mode=TargetMode.LOCKED_TARGET)
        first = observation(0., metadata=UNSUPPORTED)
        second = observation(0., 4., box=FAR_BOX, metadata=UNSUPPORTED)
        result = tracking.update_with_result([first, second], timestamp=0., target_index=1)
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(result.target.bbox, FAR_BOX)
        self.assertEqual(result.target.last_measurement_timestamp, 0.)
        self.assertIsNotNone(tracking.target_uuid)
        self.assertEqual(dict(result.spawn_deferred_reasons), {0: "birth_surface_support_unknown"})

    def test_unsupported_unknown_does_not_measure_any_of_two_existing_tracks(self):
        tracking = manager(mode=TargetMode.LOCKED_TARGET)
        tracking.lock_detection(0, target_uuid="fixed-task")
        tracking.update_with_result([observation(0.), observation(0., 4., box=FAR_BOX)], timestamp=0.)
        result = tracking.update_with_result([
            observation(.1, 8., box=(160., 0., 180., 20.), metadata=UNSUPPORTED)], timestamp=.1)
        self.assertEqual(len(result.tracks), 2)
        self.assertEqual(result.associations, ())
        self.assertEqual([track.last_measurement_timestamp for track in result.tracks], [0., 0.])
        self.assertEqual(tracking._next_track_id, 3)
        self.assertEqual(result.target.track_id, 1)
        self.assertEqual(tracking.target_uuid, "fixed-task")

    def test_long_unknown_sequence_never_allocates_ids_or_extends_selected_measurement(self):
        tracking = manager(mode=TargetMode.LOCKED_TARGET)
        tracking.lock_detection(0, target_uuid="fixed-task")
        tracking.update_with_result([observation(0.)], timestamp=0.)
        for index in range(1, 51):
            timestamp = index / 10.
            result = tracking.update_with_result([
                observation(timestamp, 4., box=FAR_BOX, metadata=UNSUPPORTED)], timestamp=timestamp)
            self.assertEqual(tracking._next_track_id, 2)
            self.assertEqual(tracking._birth_evidence, [])
            self.assertEqual(result.target.last_measurement_timestamp, 0.)
        self.assertEqual(result.status, TargetStatus.LOST)
        self.assertTrue(tracking._requires_reselection)
        self.assertEqual(tracking.target_uuid, "fixed-task")

    def test_timer_projection_never_turns_deferred_candidate_into_identity(self):
        tracking = manager()
        first = tracking.update_with_result([observation(0., metadata=UNSUPPORTED)], timestamp=0.)
        self.assertEqual(first.tracks, ())
        for timestamp in [.05, .1, .2]:
            projected = tracking.predict_with_result(timestamp)
            self.assertEqual(projected.tracks, ())
            self.assertIsNone(projected.target)
            self.assertEqual(tracking._next_track_id, 1)
        result = tracking.update_with_result([observation(.3)], timestamp=.3)
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(result.target.last_measurement_timestamp, .3)

    def test_two_deferred_raw_candidates_still_latch_unique_instance_ambiguity(self):
        tracking = manager()
        result = tracking.update_with_result([
            observation(0., metadata=UNSUPPORTED),
            observation(0., 4., box=FAR_BOX, metadata=UNSUPPORTED)], timestamp=0.)
        self.assertEqual(result.tracks, ())
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        result = tracking.update_with_result([observation(.1, metadata=UNSUPPORTED)], timestamp=.1)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertIsNone(result.target)
        result = tracking.update_with_result([observation(.2)], timestamp=.2)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertEqual(result.target.last_measurement_timestamp, .2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
