"""Safety and identity tests for designated targets, without ROS or Gazebo."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

import numpy as np

from uav_tracking.core import Detection, TargetManager, TargetMode, TargetStatus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_nodes"))
from uav_tracking_nodes.stage2_telemetry import track_snapshot


def detection(x, timestamp, *, z=5.0, confidence=0.9, box=None, candidate=0):
    return Detection(
        (100 + x * 30, 40, 120 + x * 30, 90) if box is None else box,
        "person", confidence, timestamp, (x, 0, z),
        depth_stats={"valid_fraction": 0.95, "std": 0.02},
        metadata={"candidate_id": candidate},
    )


def tracker(**kwargs):
    params = dict(
        mode=TargetMode.LOCKED_TARGET, min_hits=1, association_mode="hybrid_3d",
        association_max_distance=0.8, reject_ambiguous_associations=True,
        max_coast_duration_s=0.75, track_retention_duration_s=3.0,
        kf_kwargs={"initial_position_covariance": 0.01,
                   "initial_velocity_covariance": 0.01,
                   "process_acceleration_std": 0.5},
    )
    params.update(kwargs)
    return TargetManager(**params)


class Stage2AssociationTests(unittest.TestCase):
    def test_initial_box_selection_and_reordered_candidates_preserve_identity(self):
        manager = tracker()
        manager.lock_detection(1, target_uuid="task-chosen-in-image")
        first = manager.update_with_result([detection(-3, 0), detection(0, 0), detection(3, 0)], timestamp=0)
        target_id = first.target.track_id
        for index in range(1, 5):
            time_s = index * 0.1
            detections = [detection(3, time_s), detection(0, time_s), detection(-3, time_s)]
            result = manager.update_with_result(detections, timestamp=time_s)
            self.assertEqual(result.status, TargetStatus.TRACKING)
            self.assertEqual(result.target.track_id, target_id)
            self.assertEqual(result.target.last_detection.position_3d, (0, 0, 5))
        self.assertEqual(manager.target_uuid, "task-chosen-in-image")
        self.assertEqual(len(result.tracks), 3)

    def test_high_confidence_distractor_cannot_replace_selected_target(self):
        manager = tracker()
        manager.lock_detection(0)
        first = manager.update([detection(0, 0), detection(3, 0)], timestamp=0)
        result = manager.update_with_result([detection(3, 0.2, confidence=1.0)], timestamp=0.2)
        self.assertEqual(result.target.track_id, first.track_id)
        self.assertEqual(result.status, TargetStatus.COASTING)
        self.assertFalse(result.target._matched_this_frame)

    def test_crossing_in_image_uses_depth_to_preserve_physical_target(self):
        manager = tracker()
        manager.lock_detection(0, target_uuid="crossing-target")
        manager.update([detection(-0.5, 0), detection(0.5, 0, z=6.5)], timestamp=0)
        target_id = manager.target_track_id
        for track, velocity in zip(manager.tracks, (1.0, -1.0)):
            track._filter.state[3] = velocity
        for index in range(1, 7):
            timestamp = index * 0.1
            a = detection(-0.5 + timestamp, timestamp)
            b = detection(0.5 - timestamp, timestamp, z=6.5)
            result = manager.update_with_result([b, a], timestamp=timestamp)
            self.assertEqual(result.target.track_id, target_id)
            self.assertEqual(result.target.last_detection.position_3d, a.position_3d)
            self.assertEqual(result.status, TargetStatus.TRACKING)

    def test_one_track_two_plausible_boxes_pauses_instead_of_using_confidence(self):
        manager = tracker()
        manager.lock_detection(0)
        target = manager.update([detection(0, 0)], timestamp=0)
        result = manager.update_with_result([
            detection(-0.05, 0.1, confidence=0.6), detection(0.05, 0.1, confidence=1.0),
        ], timestamp=0.1)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertFalse(result.target._matched_this_frame)
        self.assertEqual(result.target.last_measurement_timestamp, 0)
        self.assertEqual(result.ambiguous_track_ids, (target.track_id,))
        self.assertEqual(len(result.tracks), 1, "ambiguous boxes must not manufacture extra identities")
        self.assertEqual(manager.predict_with_result(0.15).status, TargetStatus.AMBIGUOUS)
        self.assertEqual(manager.update_with_result([], timestamp=0.2).status, TargetStatus.AMBIGUOUS)
        recovered = manager.update_with_result([detection(0, 0.3)], timestamp=0.3)
        self.assertEqual(recovered.target.track_id, target.track_id)
        self.assertEqual(recovered.status, TargetStatus.REACQUIRED)

    def test_two_tracks_one_merged_box_freezes_whole_component(self):
        manager = tracker()
        manager.lock_detection(0)
        manager.update([detection(-0.1, 0), detection(0.1, 0)], timestamp=0)
        result = manager.update_with_result([detection(0, 0.1)], timestamp=0.1)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(set(result.ambiguous_track_ids), {1, 2})
        self.assertTrue(all(not track._matched_this_frame for track in result.tracks))

    def test_ambiguity_elsewhere_does_not_pause_selected_unique_component(self):
        manager = tracker()
        manager.lock_detection(0)
        manager.update([detection(-3, 0), detection(0, 0), detection(0.1, 0)], timestamp=0)
        result = manager.update_with_result([detection(-3, 0.1), detection(0.05, 0.1)], timestamp=0.1)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertEqual(result.ambiguous_track_ids, (2, 3))
        self.assertTrue(result.target._matched_this_frame)

    def test_long_unresolved_ambiguity_requires_explicit_reselection(self):
        manager = tracker()
        manager.lock_detection(0, target_uuid="old-task")
        manager.update([detection(-0.1, 0), detection(0.1, 0)], timestamp=0)
        manager.update([detection(0, 0.2)], timestamp=0.2)
        self.assertEqual(manager.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(manager.predict_with_result(0.751).status, TargetStatus.LOST)
        returned = manager.update_with_result([detection(-0.1, 0.8), detection(0.1, 0.8)], timestamp=0.8)
        self.assertEqual(returned.status, TargetStatus.LOST)
        self.assertEqual(manager.target_uuid, "old-task")
        manager.lock_detection(0, target_uuid="new-explicit-box")
        result = manager.update_with_result([detection(-0.1, 0.9), detection(0.1, 0.9)], timestamp=0.9)
        self.assertEqual(manager.target_uuid, "new-explicit-box")
        self.assertEqual(result.status, TargetStatus.TRACKING)

    def test_strict_three_d_gate_cannot_be_bypassed_by_identical_image_box(self):
        manager = tracker()
        manager.lock_detection(0)
        manager.update([detection(0, 0)], timestamp=0)
        far_depth = detection(0, 0.1, z=30)
        self.assertIsNone(manager._association_cost(manager.target, far_depth))

    def test_explicit_box_retires_stale_competitors_and_tracks_beyond_one_frame(self):
        manager = tracker()
        manager.lock_detection(0, target_uuid="old-task")
        manager.update([detection(-0.1, 0), detection(0.1, 0)], timestamp=0)
        manager.update([detection(0, 0.1)], timestamp=0.1)
        self.assertEqual(manager.status, TargetStatus.AMBIGUOUS)
        # Once visually separated, the user selects the actual new box. Two
        # stale predictions still gate that box; neither has privileged ID.
        manager.lock_detection(0, target_uuid="explicit-new-task")
        result = manager.update_with_result([detection(0, 0.2), detection(3, 0.2)], timestamp=0.2)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        selected_id = result.target.track_id
        self.assertNotIn(selected_id, (1, 2))
        for step in range(3, 54):
            timestamp = step / 10
            result = manager.update_with_result([detection(3, timestamp), detection(0, timestamp)], timestamp=timestamp)
            self.assertEqual(result.status, TargetStatus.TRACKING)
            self.assertEqual(result.target.track_id, selected_id)
            self.assertEqual(manager.target_uuid, "explicit-new-task")

    def test_mahalanobis_gate_rejects_near_but_statistically_inconsistent_box(self):
        manager = tracker()
        manager.lock_detection(0)
        manager.update([detection(0, 0)], timestamp=0)
        manager.target._filter.covariance = np.eye(6) * 1e-6
        self.assertIsNone(manager._association_cost(manager.target, detection(0.5, 0.1)))

    def test_real_car_merge_shape_freezes_without_relaxing_strict_gate(self):
        # Source44.4/44.6 geometry of the preserved failed engineering run.
        # Only RGB-D observations are used, never a simulator entity identity.
        manager = tracker(association_max_distance=1.5)
        manager.lock_detection(0, target_uuid="merge-task")
        prior = [
            Detection((270.68670654, 150.20098877, 365.15264893, 230.65985107),
                      "car", .6467, 44.4, (22.38653322, .04981052, .91529469)),
            Detection((313.66748047, 142.20297241, 423.09912109, 210.70352173),
                      "car", .4747, 44.4, (23.66628272, -1.15697947, .90644969)),
        ]
        manager.update_with_result(prior, timestamp=44.4)
        velocities = ((.52949544, .00415629, .01227751),
                      (.22780174, .10866975, .06191893))
        for track, velocity in zip(manager.tracks, velocities):
            track._filter.state[3:] = velocity
            track._filter.covariance = np.eye(6) * 1e-6
        merged = Detection((271.81225586, 142.13195801, 423.25744629, 229.98208618),
                           "car", .46536, 44.6, (22.98346521, -.56472801, .87380414))
        self.assertIsNone(manager._association_cost(manager.target, merged))
        result = manager.update_with_result([merged], timestamp=44.6)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.merge_uncertainty_detection_indices, (0,))
        self.assertEqual(result.ambiguous_track_ids, (1, 2))
        self.assertEqual(result.associations, ())
        self.assertEqual(len(result.tracks), 2, "merged box must not create a duplicate identity")
        self.assertEqual(manager.target_uuid, "merge-task")
        self.assertEqual(result.target.last_measurement_timestamp, 44.4)
        self.assertEqual(result.target.bbox, prior[0].bbox)
        self.assertIsNone(manager._association_cost(manager.target, merged))
        payload = track_snapshot(result, target_uuid=manager.target_uuid,
                                 acquisition_s=44.6, output_s=44.6, frame_id="map", projected=False)
        self.assertEqual(payload["merge_uncertainty_detection_indices"], [0])

    def test_depth_separated_overlapping_boxes_do_not_trigger_merge_guard(self):
        manager = tracker(association_max_distance=1.5)
        manager.lock_detection(0)
        box = (0, 0, 10, 10)
        manager.update_with_result([detection(0, 0, box=box),
                                    detection(0, 0, z=9, box=box)], timestamp=0)
        for track in manager.tracks:
            track._filter.covariance = np.eye(6) * 1e-6
        result = manager.update_with_result([
            detection(.6, .1, box=(0, 0, 14, 10)),
        ], timestamp=.1)
        self.assertEqual(result.merge_uncertainty_detection_indices, ())
        self.assertNotEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.target.last_measurement_timestamp, 0)

    def test_ordinary_box_without_growth_is_still_rejected_not_declared_merge(self):
        manager = tracker(association_max_distance=1.5)
        manager.lock_detection(0)
        box = (0, 0, 10, 10)
        manager.update_with_result([detection(0, 0, box=box),
                                    detection(1.2, 0, box=box)], timestamp=0)
        for track in manager.tracks:
            track._filter.covariance = np.eye(6) * 1e-6
        result = manager.update_with_result([detection(.6, .1, box=box)], timestamp=.1)
        self.assertEqual(result.merge_uncertainty_detection_indices, ())
        self.assertNotEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertFalse(result.target._matched_this_frame)

    def test_merge_guard_freezes_entire_component_but_keeps_distant_track(self):
        manager = tracker(association_max_distance=1.5)
        manager.lock_detection(0, target_uuid="merge-task")
        a, b = (0, 0, 10, 10), (4, 0, 14, 10)
        manager.update_with_result([detection(0, 0, box=a), detection(1.2, 0, box=b),
                                    detection(5, 0)], timestamp=0)
        for track in manager.tracks:
            track._filter.covariance = np.eye(6) * 1e-6
        result = manager.update_with_result([
            detection(0, .1, box=a), detection(.6, .1, box=(0, 0, 14, 10)),
            detection(5, .1),
        ], timestamp=.1)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.merge_uncertainty_detection_indices, (1,))
        self.assertEqual(result.ambiguous_detection_indices, (0, 1))
        self.assertEqual(result.associations, ((3, 2),))
        self.assertEqual(len(result.tracks), 3)
        self.assertTrue(result.tracks[2]._matched_this_frame)
        self.assertFalse(result.target._matched_this_frame)
        self.assertEqual(manager.predict_with_result(.751).status, TargetStatus.LOST)
        returned = manager.update_with_result([detection(0, .8, box=a)], timestamp=.8)
        self.assertEqual(returned.status, TargetStatus.LOST)
        self.assertEqual(manager.target_uuid, "merge-task")

    def test_merge_guard_does_not_apply_without_explicit_reject_policy(self):
        manager = tracker(reject_ambiguous_associations=False, association_max_distance=1.5)
        manager.lock_detection(0)
        manager.update_with_result([detection(0, 0, box=(0, 0, 10, 10)),
                                    detection(1.2, 0, box=(4, 0, 14, 10))], timestamp=0)
        for track in manager.tracks:
            track._filter.covariance = np.eye(6) * 1e-6
        result = manager.update_with_result([detection(.6, .1, box=(0, 0, 14, 10))], timestamp=.1)
        self.assertEqual(result.merge_uncertainty_detection_indices, ())
        self.assertEqual(len(result.tracks), 3)

    def test_stale_competitor_cannot_supply_merge_uncertainty(self):
        manager = tracker(association_max_distance=1.5)
        manager.lock_detection(0)
        manager.update_with_result([detection(0, 0, box=(0, 0, 10, 10)),
                                    detection(1.2, 0, box=(4, 0, 14, 10))], timestamp=0)
        manager.update_with_result([detection(0, .7, box=(0, 0, 10, 10))], timestamp=.7)
        for track in manager.tracks:
            track._filter.covariance = np.eye(6) * 1e-6
        result = manager.update_with_result([detection(.6, .8, box=(0, 0, 14, 10))], timestamp=.8)
        self.assertEqual(result.merge_uncertainty_detection_indices, ())
        self.assertNotEqual(result.status, TargetStatus.AMBIGUOUS)

    def v4_merge_manager(self):
        # Preserved v4 source43.6/44.0 measurements before the output timer
        # expires only competitor2, then source44.2 arrives at output44.376.
        manager = tracker(association_max_distance=1.5)
        manager.lock_detection(0, target_uuid="v4-original-task")
        selected = Detection((271.38507080,150.86657715,365.12579346,230.30889893),
                             "car",.805,43.6,(22.16032884,.02640513,.86415899))
        other = Detection((314.89297485,141.25895691,428.58596802,210.99415588),
                          "car",.572,43.6,(23.57846151,-1.25031989,.81377105))
        manager.update_with_result([selected,other],timestamp=43.6)
        manager.target._filter.state[3:] = (.51357862,-.00343880,.02530380)
        manager.tracks[1]._filter.state[3:] = (.17342238,.17958930,.08840434)
        manager.update_with_result([
            Detection((272.17098999,150.12370300,365.20950317,230.30986023),
                      "car",.641,44.0,(22.36464247,.02348319,.87558162)),
        ],timestamp=44.)
        for track in manager.tracks:
            track._filter.covariance = np.eye(6)*1e-6
        return manager

    def v4_merged_detection(self,source_s=44.2):
        return Detection((273.63110352,142.77670288,426.29687500,230.61361694),
                         "car",.720,source_s,(23.05873294,-.63154891,.80660164))

    def test_v4_output_expired_competitor_still_freezes_source_fresh_merge_without_revival(self):
        manager = self.v4_merge_manager()
        manager.predict_with_result(44.36)
        self.assertEqual(manager.tracks[1].state.value,"lost")
        self.assertEqual(manager.target.last_measurement_timestamp,44.)
        merged=self.v4_merged_detection()
        self.assertIsNone(manager._association_cost(manager.target,merged))
        result=manager.update_with_result([merged],timestamp=44.2)
        self.assertEqual(result.status,TargetStatus.AMBIGUOUS)
        self.assertEqual(result.ambiguous_track_ids,(1,2))
        self.assertEqual(result.merge_uncertainty_detection_indices,(0,))
        self.assertEqual(result.associations,())
        self.assertEqual(len(result.tracks),2)
        self.assertEqual(result.tracks[1].state.value,"lost")
        self.assertEqual(result.tracks[1].last_measurement_timestamp,43.6)
        self.assertEqual(result.target.last_measurement_timestamp,44.)
        self.assertEqual(manager.target_uuid,"v4-original-task")
        self.assertEqual(manager.predict_with_result(44.76).status,TargetStatus.LOST)
        self.assertEqual(manager.update_with_result([self.v4_merged_detection(44.8)],timestamp=44.8).status,
                         TargetStatus.LOST,"the selected task's output-time loss latch must never be undone")

    def test_v4_competitor_expired_at_source_cannot_freeze_merge(self):
        manager=self.v4_merge_manager()
        # Source44.4 is already .8 s after competitor's accepted43.6 depth.
        manager.predict_with_result(44.56)
        result=manager.update_with_result([self.v4_merged_detection(44.4)],timestamp=44.4)
        self.assertEqual(result.merge_uncertainty_detection_indices,())
        self.assertNotIn(manager.target_track_id,result.ambiguous_track_ids)

    def test_v4_delayed_merge_cannot_revive_already_expired_selected_task(self):
        manager=self.v4_merge_manager()
        self.assertEqual(manager.predict_with_result(44.76).status,TargetStatus.LOST)
        # Even source44.2 is before the selected deadline; arrival was after
        # its actual output-time loss. No retroactive recovery is allowed.
        result=manager.update_with_result([self.v4_merged_detection()],timestamp=44.2)
        self.assertEqual(result.status,TargetStatus.LOST)
        self.assertEqual(result.merge_uncertainty_detection_indices,())
        self.assertEqual(manager.target_uuid,"v4-original-task")

    def test_iou_baseline_uses_image_overlap_without_depth_association(self):
        manager = tracker(association_mode="iou_2d")
        manager.lock_detection(0)
        manager.update([detection(0, 0)], timestamp=0)
        self.assertEqual(manager._association_cost(manager.target, detection(0, 0.1, z=30)), 0.0)
        self.assertIsNone(manager._association_cost(manager.target, detection(5, 0.1)))

    def test_short_occlusion_does_not_follow_remaining_same_class_candidate(self):
        manager = tracker()
        manager.lock_detection(0, target_uuid="person-a")
        manager.update([detection(0, 0), detection(3, 0)], timestamp=0)
        manager.update([detection(3, 0.2)], timestamp=0.2)
        result = manager.update_with_result([detection(3, 0.4), detection(0, 0.4)], timestamp=0.4)
        self.assertEqual(result.status, TargetStatus.REACQUIRED)
        self.assertEqual(result.target.track_id, 1)
        self.assertEqual(manager.target_uuid, "person-a")

    def test_telemetry_distinguishes_fresh_boxes_and_predicted_states(self):
        manager = tracker()
        manager.lock_detection(1, target_uuid="telemetry-task")
        result = manager.update_with_result([detection(-3, 1), detection(0, 1, candidate=10)], timestamp=1)
        payload = track_snapshot(result, target_uuid=manager.target_uuid, acquisition_s=1,
                                 output_s=1, frame_id="map", projected=False)
        self.assertEqual(payload["target_track_id"], 2)
        self.assertEqual(payload["tracks"][1]["candidate_id"], 10)
        self.assertTrue(payload["tracks"][1]["matched"])
        self.assertEqual(payload["associations"], [])  # both were newly created
        json.dumps(payload, allow_nan=False)
        predicted = manager.predict_with_result(1.1)
        payload = track_snapshot(predicted, target_uuid=manager.target_uuid, acquisition_s=1,
                                 output_s=1.1, frame_id="map", projected=True)
        self.assertTrue(payload["projected"])
        self.assertTrue(all(not item["matched"] for item in payload["tracks"]))
        self.assertEqual(payload["acquisition_s"], 1)
        self.assertEqual(payload["output_s"], 1.1)


if __name__ == "__main__":
    unittest.main()
