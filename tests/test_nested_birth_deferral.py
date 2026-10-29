"""Identity regressions for nested RGB-D detections, without ROS or GT.

Box/confidence/first surface samples below come from the preserved Humble17
car crossing source22.6--23.2 window. Subsequent world samples deliberately
use a stated smooth motion; these tests are not a replay or flight result.
"""
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

import numpy as np

from uav_tracking.core import Detection, TargetManager, TargetMode, TargetStatus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_nodes"))
from uav_tracking_nodes.stage2_telemetry import track_snapshot


OUTER = {
    22.6: (263.90161133, 133.95092773, 387.10144043, 232.23880005),
    22.7: (262.74798584, 134.13766479, 387.00653076, 232.81857300),
    22.8: (261.48309326, 133.85095215, 386.01739502, 234.16442871),
    22.9: (260.13388062, 133.65666199, 386.03927612, 233.99900818),
    23.0: (259.49783325, 134.36676025, 385.18289185, 233.67260742),
    23.1: (258.71240234, 133.01623535, 385.03515625, 233.91790771),
    23.2: (258.29339600, 139.50825500, 384.48937988, 240.79725647),
}
INNER = {
    22.7: (274.99114990, 133.93676758, 372.99017334, 166.93887329),
    22.8: (273.62890625, 134.13827515, 372.37969971, 167.30325317),
    22.9: (273.05718994, 134.29489136, 371.50238037, 167.37817383),
    23.1: (270.82879639, 133.75735474, 370.81622314, 167.14913940),
}
OUTER_POSITION = (10.599662780550798, -.021887674057478032, .8301883657997375)
INNER_POSITION = (11.345001256776104, -.014270986299321595, 1.2129104260433803)
VELOCITY = (.42464715971980543, .031059069742884058, .03541922314502988)


def sample(source_s, *, inner=False, position="smooth", class_name="car"):
    origin = INNER_POSITION if inner else OUTER_POSITION
    if position == "smooth":
        position = tuple(value + velocity * (source_s - 22.7)
                         for value, velocity in zip(origin, VELOCITY))
    confidence = ({22.7: .5066197515, 22.8: .5951582789, 22.9: .5682440996,
                   23.1: .6519147158} if inner else
                  {22.6: .8348297477, 22.7: .6951804161, 22.8: .5447202325,
                   22.9: .6449950337, 23.0: .8296799660, 23.1: .5356482863,
                   23.2: .8887338638})[source_s]
    return Detection(INNER[source_s] if inner else OUTER[source_s], class_name,
                     confidence, source_s, position,
                     depth_stats={"valid_fraction": 1.0, "std": .05},
                     metadata={"candidate_id": 3 if inner else 2})


def manager(**overrides):
    parameters = dict(mode=TargetMode.LOCKED_TARGET, min_hits=1,
                      association_mode="hybrid_3d", reject_ambiguous_associations=True,
                      association_max_distance=1.5, gate_threshold=9.21,
                      max_coast_duration_s=.75, track_retention_duration_s=3.0,
                      kf_kwargs={"measurement_noise_std": [.05, .05, .1],
                                 "process_acceleration_std": 1.,
                                 "initial_position_covariance": .01,
                                 "initial_velocity_covariance": .01})
    parameters.update(overrides)
    return TargetManager(**parameters)


def selected_manager(**overrides):
    result = manager(**overrides)
    result.lock_detection(0, target_uuid="original-task")
    result.update_with_result([sample(22.6)], timestamp=22.6)
    return result


class NestedBirthDeferralTests(unittest.TestCase):
    def test_recorded_prior_rejects_inner_at_25_668_without_allocating_its_track(self):
        tracking = selected_manager()
        # Exact accepted-filter prior and pose-uncertainty observations from
        # source22.7; no simulator identity or projected GT is in this fixture.
        prior_state = [10.602114453432012, -.014997445646787374, .8345295434603952,
                       .4261885032518364, .032100640103107585, .03711009436426008]
        prior_covariance = [
            [.007594805497082464, .0008037274349419691, .00005795495691929029,
             .015180384450598874, .0005746954118420543, .00006610578867230532],
            [.0008037274349419691, .08678006277865974, .00010934460159465554,
             .0006703503674053876, .07467351553081952, .0002065195112583627],
            [.00005795495691929029, .00010934460159465554, .016162030378433022,
             .00006333964300658954, .00008106948904904282, .02477426706841084],
            [.015180384450598874, .0006703503674053876, .00006333964300658954,
             .05506111937750322, .0006720735439442913, .0001049602723688652],
            [.0005746954118420543, .07467351553081952, .00008106948904904282,
             .0006720735439442913, .12632026226095336, .00007782312139128204],
            [.00006610578867230532, .0002065195112583627, .02477426706841084,
             .0001049602723688652, .00007782312139128204, .07036790880733211],
        ]
        tracking.target._filter.initialize(prior_state[:3], velocity=prior_state[3:],
                                           covariance=prior_covariance, timestamp=22.7)
        outer = replace(sample(22.7), confidence=.6951804161071777,
                        depth_stats={"valid_fraction": 1., "std": .6329407691955566},
                        metadata={"candidate_id": 2, "additional_measurement_covariance": [
                            [.01173644081338641, .004004367407668491, .00019476334252873983],
                            [.004004367407668491, .395270515875444, .00042166384842049674],
                            [.00019476334252873983, .00042166384842049674, .030418921697063228]]})
        inner = replace(sample(22.7, inner=True), confidence=.5066197514533997,
                        depth_stats={"valid_fraction": 1., "std": .24788327515125275},
                        metadata={"candidate_id": 3, "additional_measurement_covariance": [
                            [.011710202477331467, .003954808257679247, .00014022312087961006],
                            [.003954808257679247, .48510379714171686, .0004916840113281544],
                            [.00014022312087961006, .0004916840113281544, .03069633927671421]]})
        covariance = tracking._measurement_covariance(tracking.target._filter, inner)
        distance = tracking.target._filter.mahalanobis_distance(
            inner.position_3d, measurement_covariance=covariance)
        self.assertAlmostEqual(distance, 25.66805528188335, places=6)
        self.assertIsNone(tracking._association_cost(tracking.target, inner))
        result = tracking.update_with_result([outer, inner], timestamp=22.7)
        self.assertEqual(result.spawn_deferred_detection_indices, (1,))
        self.assertEqual([track.track_id for track in result.tracks], [1])
        np.testing.assert_allclose(result.target.last_detection.position_3d, OUTER_POSITION)
        self.assertAlmostEqual(result.target.last_measurement_diagnostics["mahalanobis_squared"],
                               .0006317294473036102, places=9)

    def test_recorded_nested_boxes_do_not_birth_a_sticky_competing_identity(self):
        tracking = selected_manager()
        original_id = tracking.target_track_id
        for source_s in (22.7, 22.8, 22.9):
            outer, fragment = sample(source_s), sample(source_s, inner=True)
            observations = [outer, fragment]
            result = tracking.update_with_result(observations, timestamp=source_s)
            self.assertEqual(len(result.tracks), 1)
            self.assertEqual(result.target.track_id, original_id)
            self.assertEqual(result.target.last_measurement_timestamp, source_s)
            self.assertEqual(result.target.last_detection, outer)
            self.assertEqual(result.spawn_deferred_detection_indices, (1,))
            self.assertEqual(result.merge_uncertainty_detection_indices, ())
            self.assertEqual(observations, [outer, fragment], "all actual observations must survive")
        recovered = tracking.update_with_result([sample(23.0)], timestamp=23.0)
        self.assertEqual(recovered.status, TargetStatus.TRACKING)
        self.assertEqual(recovered.target.track_id, original_id)
        self.assertEqual(tracking.target_uuid, "original-task")
        self.assertEqual(recovered.spawn_deferred_detection_indices, ())
        self.assertEqual(recovered.ambiguous_track_ids, ())
        # Confidence reverses in the actual22.8 frame; keeping the highest
        # confidence would have selected the incomplete inner surface.
        self.assertGreater(sample(22.8, inner=True).confidence, sample(22.8).confidence)

    def test_actual_one_to_many_ambiguity_is_not_silenced_by_containment(self):
        tracking = selected_manager()
        for source_s in (22.7, 22.8, 22.9):
            outer = sample(source_s)
            plausible_inner = sample(source_s, inner=True, position=outer.position_3d)
            result = tracking.update_with_result([outer, plausible_inner], timestamp=source_s)
            self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
            self.assertEqual(result.ambiguous_detection_indices, (0, 1))
            self.assertEqual(result.target.last_measurement_timestamp, 22.6)
            self.assertFalse(result.target._matched_this_frame)
            self.assertEqual(len(result.tracks), 1)
            self.assertEqual(result.spawn_deferred_detection_indices, ())
        recovered = tracking.update_with_result([sample(23.0)], timestamp=23.0)
        self.assertEqual(recovered.status, TargetStatus.REACQUIRED)
        self.assertEqual(recovered.target.track_id, 1)

    def test_unmatched_fragment_inside_reserved_ambiguous_outer_also_defers(self):
        tracking = selected_manager()
        outer = sample(22.7)
        plausible_other = replace(outer, bbox=OUTER[22.8], metadata={"candidate_id": 8})
        fragment = sample(22.7, inner=True)
        result = tracking.update_with_result([outer, plausible_other, fragment], timestamp=22.7)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.ambiguous_detection_indices, (0, 1))
        self.assertEqual(result.spawn_deferred_detection_indices, (2,))
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(result.target.last_measurement_timestamp, 22.6)
        self.assertEqual(result.merge_uncertainty_detection_indices, ())

    def test_second_object_can_birth_after_independent_visual_separation(self):
        tracking = selected_manager()
        tracking.update_with_result([sample(22.7), sample(22.7, inner=True)], timestamp=22.7)
        separate = replace(sample(22.8, inner=True), bbox=(416, 115, 514, 171),
                           position_3d=(11.4, -2.0, 1.2))
        result = tracking.update_with_result([sample(22.8), separate], timestamp=22.8)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertEqual(result.target.track_id, 1)
        self.assertEqual([track.track_id for track in result.tracks], [1, 2],
                         "deferred observations must not consume track IDs")
        self.assertEqual(result.tracks[1].last_detection, separate)
        self.assertEqual(result.spawn_deferred_detection_indices, ())

    def test_independent_depth_beyond_original_distance_bound_never_defers(self):
        tracking = selected_manager()
        far = sample(22.7, inner=True, position=(13., 0., 1.2))
        result = tracking.update_with_result([sample(22.7), far], timestamp=22.7)
        self.assertEqual(len(result.tracks), 2)
        self.assertEqual(result.tracks[1].last_detection, far)
        self.assertEqual(result.spawn_deferred_detection_indices, ())
        self.assertEqual(tracking.association_max_distance, 1.5)
        self.assertEqual(tracking.gate_threshold, 9.21)

    def test_partially_overlapping_or_similarly_sized_new_object_is_not_deferred(self):
        for box in ((320, 133, 418, 167), (267, 138, 382, 229)):
            with self.subTest(box=box):
                tracking = selected_manager()
                candidate = replace(sample(22.7, inner=True), bbox=box)
                result = tracking.update_with_result([sample(22.7), candidate], timestamp=22.7)
                self.assertEqual(result.spawn_deferred_detection_indices, ())
                self.assertEqual(len(result.tracks), 2)

    def test_independently_established_overlapping_tracks_are_never_collapsed(self):
        tracking = manager(kf_kwargs={"initial_position_covariance": 1.,
                                    "initial_velocity_covariance": .01})
        tracking.lock_detection(0, target_uuid="two-established-objects")
        independent = replace(sample(22.6), bbox=(416, 115, 514, 171),
                              position_3d=(11.3, 0., 1.))
        tracking.update_with_result([sample(22.6), independent], timestamp=22.6)
        self.assertEqual(len(tracking.tracks), 2)
        merged_view = sample(22.8)
        result = tracking.update_with_result([merged_view], timestamp=22.8)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.ambiguous_track_ids, (1, 2))
        self.assertEqual(len(result.tracks), 2)
        self.assertEqual(result.spawn_deferred_detection_indices, ())
        self.assertTrue(all(not track._matched_this_frame for track in result.tracks))

    def test_explicit_inner_box_selection_bypasses_birth_deferral_with_new_uuid(self):
        tracking = selected_manager()
        tracking.update_with_result([sample(22.7), sample(22.7, inner=True)], timestamp=22.7)
        tracking.lock_detection(1, target_uuid="explicit-inner-task")
        inner = sample(22.8, inner=True)
        result = tracking.update_with_result([sample(22.8), inner], timestamp=22.8)
        self.assertEqual(tracking.target_uuid, "explicit-inner-task")
        self.assertEqual(result.target.track_id, 2)
        self.assertEqual(result.target.last_detection, inner)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertEqual(result.spawn_deferred_detection_indices, ())

    def test_long_loss_latch_is_never_cleared_by_a_later_complete_box(self):
        tracking = selected_manager()
        tracking.update_with_result([sample(22.7), sample(22.7, inner=True)], timestamp=22.7)
        self.assertEqual(tracking.predict_with_result(23.451).status, TargetStatus.LOST)
        returned = replace(sample(23.2), timestamp=23.5)
        result = tracking.update_with_result([returned], timestamp=23.5)
        self.assertEqual(result.status, TargetStatus.LOST)
        self.assertEqual(result.target.track_id, 1)
        self.assertEqual(result.target.last_measurement_timestamp, 22.7)
        self.assertEqual(tracking.target_uuid, "original-task")

    def test_missing_depth_keeps_real_matching_ambiguity_and_never_refreshes_measurement(self):
        tracking = selected_manager()
        for source_s in (22.7, 22.8, 22.9):
            result = tracking.update_with_result([
                sample(source_s), sample(source_s, inner=True, position=None),
            ], timestamp=source_s)
            self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
            self.assertEqual(result.target.last_measurement_timestamp, 22.6)
            self.assertEqual(len(result.tracks), 1)
        self.assertEqual(tracking.predict_with_result(23.351).status, TargetStatus.LOST)

    def test_depthless_accepted_outer_can_defer_birth_but_cannot_refresh_three_d_state(self):
        tracking = selected_manager()
        result = tracking.update_with_result([
            sample(22.7, position=None), sample(22.7, inner=True),
        ], timestamp=22.7)
        self.assertEqual(result.spawn_deferred_detection_indices, (1,))
        self.assertEqual(result.spawn_deferred_reasons,
                         ((1, "nested_unmatched_without_depth_separation_evidence"),))
        self.assertEqual(result.target.last_measurement_timestamp, 22.6)
        self.assertEqual(len(result.tracks), 1)

    def test_initial_unique_mode_counts_all_real_candidates_without_prior_anchors(self):
        tracking = manager(mode=TargetMode.AUTO_UNIQUE)
        result = tracking.update_with_result([
            sample(22.7), sample(22.7, inner=True, position=None),
        ], timestamp=22.7)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertIsNone(result.target)
        self.assertEqual(len(result.tracks), 2)
        self.assertEqual(result.spawn_deferred_detection_indices, ())

    def test_unique_mode_does_not_ignore_raw_candidate_when_birth_is_deferred(self):
        tracking = manager(mode=TargetMode.AUTO_UNIQUE)
        tracking.update_with_result([sample(22.6)], timestamp=22.6)
        result = tracking.update_with_result([sample(22.7), sample(22.7, inner=True)], timestamp=22.7)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.spawn_deferred_detection_indices, (1,))
        self.assertEqual(len(result.tracks), 1)

    def test_projected_snapshots_never_republish_deferred_birth_as_a_new_observation(self):
        tracking = selected_manager()
        result = tracking.update_with_result([sample(22.7), sample(22.7, inner=True)], timestamp=22.7)
        payload = track_snapshot(result, target_uuid=tracking.target_uuid, acquisition_s=22.7,
                                 output_s=22.868, frame_id="map", projected=False)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["spawn_deferred_detection_indices"], [1])
        self.assertEqual(payload["spawn_deferred_reasons"][0]["detection_index"], 1)
        self.assertEqual(payload["spawn_deferred_reasons"][0]["reason"],
                         "nested_unmatched_within_existing_distance_domain")
        json.dumps(payload, allow_nan=False)
        for projected_result in (result, tracking.predict_with_result(22.9)):
            projected = track_snapshot(projected_result, target_uuid=tracking.target_uuid,
                                       acquisition_s=22.7, output_s=22.9, frame_id="map", projected=True)
            self.assertEqual(projected["spawn_deferred_detection_indices"], [])
            self.assertEqual(projected["spawn_deferred_reasons"], [])
        self.assertEqual(tracking.last_result.spawn_deferred_detection_indices, ())


if __name__ == "__main__":
    unittest.main()
