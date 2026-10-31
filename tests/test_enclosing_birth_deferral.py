"""Regressions for an unmatched box enclosing an established observation.

The small JSON fixture contains recorded Humble38 diagnostic inputs at 33.3 s.
It restores one selected filter prior and only two observations: this is a
conditional local regression, not a complete association graph or flight replay.
Every other case and every subsequent motion sample is explicitly synthetic.
No simulator truth or physical-entity identifier is used by these tests.
"""
from dataclasses import replace
import json
from pathlib import Path
import unittest

import numpy as np

from uav_tracking.core import Detection, TargetManager, TargetMode, TargetStatus


FIXTURE = Path(__file__).with_name("fixtures") / "enclosing_birth_humble38_33_3.json"
SELECTED_BOX = (10., 10., 30., 30.)
ENCLOSING_BOX = (0., 0., 40., 40.)


def manager(**overrides):
    parameters = dict(
        mode=TargetMode.LOCKED_TARGET, min_hits=1,
        association_mode="hybrid_3d", reject_ambiguous_associations=True,
        association_max_distance=1.5, gate_threshold=9.21,
        max_coast_duration_s=.75, track_retention_duration_s=3.,
        kf_kwargs={"measurement_noise_std": [.05, .05, .1],
                   "process_acceleration_std": 1.,
                   "initial_position_covariance": .01,
                   "initial_velocity_covariance": .01},
    )
    parameters.update(overrides)
    return TargetManager(**parameters)


def synthetic(timestamp, *, enclosing=False, position="default", bbox=None):
    if position == "default":
        position = (.7, 0., 1.) if enclosing else (0., 0., 1.)
    return Detection(
        bbox or (ENCLOSING_BOX if enclosing else SELECTED_BOX), "car",
        .99 if enclosing else .55, timestamp, position,
        depth_stats={"valid_fraction": 1., "std": .05},
        metadata={"candidate_id": 1 if enclosing else 0},
    )


def selected_manager(*, bbox=None, **overrides):
    tracking = manager(**overrides)
    tracking.lock_detection(0, target_uuid="synthetic-selected-task")
    tracking.update_with_result([synthetic(0., bbox=bbox)], timestamp=0.)
    return tracking


def recorded_observation(payload):
    return Detection(
        tuple(payload["bbox"]), "car", payload["confidence"], payload["timestamp"],
        tuple(payload["position_3d"]), depth_stats=payload["depth_stats"],
        metadata=payload["metadata"],
    )


class EnclosingBirthDeferralTests(unittest.TestCase):
    def test_recorded_33_3_prior_and_enclosing_observation_defer_only_new_birth(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        tracking = manager()
        tracking.lock_detection(0, target_uuid="recorded-local-regression-task")
        seed = recorded_observation(fixture["selected_seed"])
        tracking.update_with_result([seed], timestamp=seed.timestamp)
        prior = fixture["selected_prior_state"]
        tracking.target._filter.initialize(
            prior[:3], velocity=prior[3:],
            covariance=fixture["selected_prior_covariance"], timestamp=33.3,
        )
        selected = recorded_observation(fixture["selected_update"])
        enclosing = recorded_observation(fixture["unmatched_enclosing"])
        covariance = tracking._measurement_covariance(tracking.target._filter, selected)
        np.testing.assert_allclose(
            covariance, fixture["expected_selected_measurement_covariance"],
            rtol=1e-12, atol=1e-12,
        )
        mahalanobis = tracking.target._filter.mahalanobis_distance(
            selected.position_3d, measurement_covariance=covariance,
        )
        self.assertAlmostEqual(
            mahalanobis, fixture["expected_selected_mahalanobis_squared"], places=10,
        )
        self.assertIsNotNone(tracking._association_cost(tracking.target, selected))
        self.assertIsNone(tracking._association_cost(tracking.target, enclosing))
        self.assertLess(
            np.linalg.norm(np.asarray(selected.position_3d) - enclosing.position_3d),
            tracking.association_max_distance,
        )
        observations = [selected, enclosing]
        result = tracking.update_with_result(observations, timestamp=33.3)
        # The accepted measurement must remain exactly the recorded one. The
        # enclosing candidate must not be fused or replace the selected box.
        self.assertEqual(result.target.last_detection, selected)
        self.assertEqual(result.target.last_measurement_diagnostics["reason"], "ACCEPTED")
        np.testing.assert_allclose(
            result.target.last_measurement_diagnostics["posterior_state"],
            fixture["expected_selected_posterior_state"], rtol=1e-12, atol=1e-12,
        )
        self.assertEqual(result.spawn_deferred_detection_indices, (1,))
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertEqual(tracking.target_uuid, "recorded-local-regression-task")
        self.assertEqual(observations, [selected, enclosing])

    def test_synthetic_superset_without_independent_support_does_not_compete_later(self):
        tracking = selected_manager()
        original_id = tracking.target_track_id
        selected, enclosing = synthetic(.1), synthetic(.1, enclosing=True)
        # Higher confidence is deliberately assigned to the rejected enclosing
        # box. Confidence ranking cannot be substituted for identity evidence.
        self.assertGreater(enclosing.confidence, selected.confidence)
        self.assertIsNone(tracking._association_cost(tracking.target, enclosing))
        observations = [selected, enclosing]
        result = tracking.update_with_result(observations, timestamp=.1)
        self.assertEqual(result.spawn_deferred_detection_indices, (1,))
        self.assertEqual(result.target.last_detection, selected)
        self.assertEqual(observations, [selected, enclosing])
        self.assertEqual(len(result.tracks), 1)
        # These stationary later frames are synthetic, not recorded telemetry.
        for timestamp in (.2, .3, .4, .5, .6, .7, .8, .9, 1.):
            result = tracking.update_with_result([synthetic(timestamp)], timestamp=timestamp)
            self.assertEqual(result.status, TargetStatus.TRACKING)
            self.assertEqual(result.target.track_id, original_id)
            self.assertEqual(result.target.last_measurement_timestamp, timestamp)
            self.assertEqual(len(result.tracks), 1)
        self.assertEqual(tracking.target_uuid, "synthetic-selected-task")

    def test_synthetic_detection_order_does_not_change_birth_decision(self):
        tracking = selected_manager()
        result = tracking.update_with_result(
            [synthetic(.1, enclosing=True), synthetic(.1)], timestamp=.1,
        )
        self.assertEqual(result.spawn_deferred_detection_indices, (0,))
        self.assertEqual(result.target.last_detection.metadata["candidate_id"], 0)
        self.assertEqual(len(result.tracks), 1)

    def test_synthetic_real_one_to_many_feasibility_remains_ambiguous(self):
        tracking = selected_manager()
        selected = synthetic(.1)
        enclosing = synthetic(.1, enclosing=True, position=selected.position_3d)
        self.assertIsNotNone(tracking._association_cost(tracking.target, enclosing))
        result = tracking.update_with_result([selected, enclosing], timestamp=.1)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.ambiguous_detection_indices, (0, 1))
        self.assertEqual(result.spawn_deferred_detection_indices, ())
        self.assertEqual(result.target.last_measurement_timestamp, 0.)
        self.assertFalse(result.target._matched_this_frame)
        self.assertEqual(len(result.tracks), 1)

    def test_synthetic_depth_beyond_existing_distance_domain_allows_birth(self):
        tracking = selected_manager()
        independent = synthetic(.1, enclosing=True, position=(1.500001, 0., 1.))
        result = tracking.update_with_result([synthetic(.1), independent], timestamp=.1)
        self.assertEqual(result.spawn_deferred_detection_indices, ())
        self.assertEqual(len(result.tracks), 2)
        self.assertEqual(result.tracks[1].last_detection, independent)
        self.assertEqual(tracking.association_max_distance, 1.5)
        self.assertEqual(tracking.gate_threshold, 9.21)

    def test_synthetic_distance_boundary_does_not_invent_independent_depth(self):
        tracking = selected_manager()
        boundary = synthetic(.1, enclosing=True, position=(1.5, 0., 1.))
        result = tracking.update_with_result([synthetic(.1), boundary], timestamp=.1)
        self.assertEqual(result.spawn_deferred_detection_indices, (1,))
        self.assertEqual(len(result.tracks), 1)

    def test_synthetic_established_tracks_survive_an_enclosing_observation(self):
        tracking = manager(kf_kwargs={"initial_position_covariance": 1.,
                                      "initial_velocity_covariance": .01})
        tracking.lock_detection(0, target_uuid="two-established-synthetic-objects")
        independent = synthetic(0., bbox=(50., 10., 70., 30.), position=(.7, 0., 1.))
        tracking.update_with_result([synthetic(0.), independent], timestamp=0.)
        self.assertEqual(len(tracking.tracks), 2)
        merged = synthetic(.1, enclosing=True, position=(.35, 0., 1.))
        result = tracking.update_with_result([merged], timestamp=.1)
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.ambiguous_track_ids, (1, 2))
        self.assertEqual(len(result.tracks), 2)
        self.assertEqual(result.spawn_deferred_detection_indices, ())
        self.assertTrue(all(not track._matched_this_frame for track in result.tracks))
        self.assertTrue(all(track.last_measurement_timestamp == 0. for track in result.tracks))

    def test_synthetic_initial_auto_unique_counts_both_original_observations(self):
        tracking = manager(mode=TargetMode.AUTO_UNIQUE)
        result = tracking.update_with_result(
            [synthetic(0.), synthetic(0., enclosing=True)], timestamp=0.,
        )
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertIsNone(result.target)
        self.assertEqual(len(result.tracks), 2)
        self.assertEqual(result.spawn_deferred_detection_indices, ())

    def test_synthetic_auto_unique_counts_original_observation_even_if_birth_deferred(self):
        tracking = manager(mode=TargetMode.AUTO_UNIQUE)
        tracking.update_with_result([synthetic(0.)], timestamp=0.)
        result = tracking.update_with_result(
            [synthetic(.1), synthetic(.1, enclosing=True)], timestamp=.1,
        )
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.spawn_deferred_detection_indices, (1,))
        self.assertEqual(len(result.tracks), 1)

    def test_synthetic_explicit_enclosing_selection_bypasses_birth_deferral(self):
        tracking = selected_manager()
        tracking.lock_detection(1, target_uuid="explicit-new-synthetic-task")
        enclosing = synthetic(.1, enclosing=True)
        result = tracking.update_with_result([synthetic(.1), enclosing], timestamp=.1)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertEqual(result.target.track_id, 2)
        self.assertEqual(result.target.last_detection, enclosing)
        self.assertEqual(tracking.target_uuid, "explicit-new-synthetic-task")
        self.assertEqual(result.spawn_deferred_detection_indices, ())
        self.assertEqual(len(result.tracks), 2)

    def test_synthetic_depthless_anchor_can_defer_but_never_refresh_three_d_state(self):
        tracking = selected_manager()
        result = tracking.update_with_result(
            [synthetic(.1, position=None), synthetic(.1, enclosing=True)], timestamp=.1,
        )
        self.assertEqual(result.target.last_measurement_timestamp, 0.)
        self.assertEqual(result.target.last_measurement_diagnostics["reason"], "NO_WORLD_MEASUREMENT")
        self.assertEqual(result.spawn_deferred_detection_indices, (1,))
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(tracking.predict_with_result(.751).status, TargetStatus.LOST)

    def test_synthetic_missing_candidate_depth_preserves_matching_ambiguity_and_age(self):
        tracking = selected_manager()
        result = tracking.update_with_result(
            [synthetic(.1), synthetic(.1, enclosing=True, position=None)], timestamp=.1,
        )
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.ambiguous_detection_indices, (0, 1))
        self.assertEqual(result.spawn_deferred_detection_indices, ())
        self.assertEqual(result.target.last_measurement_timestamp, 0.)
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(tracking.predict_with_result(.751).status, TargetStatus.LOST)

    def test_synthetic_original_95_percent_containment_bound_is_preserved(self):
        for anchor_box, should_defer in (
            ((21., 10., 41., 30.), True),
            ((21.01, 10., 41.01, 30.), False),
        ):
            with self.subTest(anchor_box=anchor_box):
                tracking = selected_manager(bbox=anchor_box)
                result = tracking.update_with_result(
                    [synthetic(.1, bbox=anchor_box), synthetic(.1, enclosing=True)], timestamp=.1,
                )
                self.assertEqual(result.spawn_deferred_detection_indices, (1,) if should_defer else ())
                self.assertEqual(len(result.tracks), 1 if should_defer else 2)

    def test_synthetic_original_80_percent_area_bound_is_preserved(self):
        for anchor_box, should_defer in (
            ((0., 0., 32., 40.), True),
            ((0., 0., 32.001, 40.), False),
        ):
            with self.subTest(anchor_box=anchor_box):
                tracking = selected_manager(bbox=anchor_box)
                result = tracking.update_with_result(
                    [synthetic(.1, bbox=anchor_box), synthetic(.1, enclosing=True)], timestamp=.1,
                )
                self.assertEqual(result.spawn_deferred_detection_indices, (1,) if should_defer else ())
                self.assertEqual(len(result.tracks), 1 if should_defer else 2)


if __name__ == "__main__":
    unittest.main()
