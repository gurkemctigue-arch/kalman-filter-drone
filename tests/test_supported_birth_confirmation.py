"""Birth qualification regressions, independent of ROS and simulator truth.

The 31.3 s fixture restores one recorded selected prior and two observations.
It is a conditional local regression, not the complete graph or flight replay.
All other observations and all later motion are explicitly synthetic. The
one-frame entrant example uses labels only in the offline test assertion;
neither labels nor physical entity IDs are ever supplied to TargetManager.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import types
import unittest

import numpy as np

from uav_tracking.core import Detection, TargetManager, TargetMode, TargetStatus


FIXTURE = Path(__file__).with_name("fixtures") / "supported_birth_humble39_31_3.json"
RISK_FIXTURE = Path(__file__).with_name("fixtures") / "supported_birth_head39_identity_risk.json"
ANCHOR_BOX = (0., 0., 20., 20.)
OVERLAP_BOX = (10., 0., 30., 20.)  # Equal areas: original nested guard is irrelevant.


class Humble39BirthPolicyAblation(TargetManager):
    """Disable only the new qualification, retaining the source39 birth rule.

    This is a local policy ablation using the current manager, not an execution
    or full source replay of the historical frozen source39 artifact.
    """

    def _confirm_supported_births(self, detections, assignment, matched_detection_indices, timestamp):
        return None


def manager(*, policy=TargetManager, **overrides):
    parameters = dict(
        mode=TargetMode.LOCKED_TARGET, min_hits=1,
        association_mode="hybrid_3d", reject_ambiguous_associations=True,
        association_max_distance=1.5, gate_threshold=9.21,
        max_coast_duration_s=.75, track_retention_duration_s=3.,
        supported_birth_confirmation_required=True,
        kf_kwargs={"measurement_noise_std": [.05, .05, .1],
                   "process_acceleration_std": 1.,
                   "initial_position_covariance": .01,
                   "initial_velocity_covariance": .01},
    )
    parameters.update(overrides)
    return policy(**parameters)


def synthetic(timestamp, *, entrant=False, position=None, bbox=None,
              supported=True, enabled=True, epoch=0, class_name="car"):
    if position is None:
        position = (3., 0., 1.) if entrant else (0., 0., 1.)
    return Detection(
        bbox or (OVERLAP_BOX if entrant else ANCHOR_BOX), class_name, .9,
        timestamp, position, depth_stats={"valid_fraction": 1., "std": .05},
        metadata={"candidate_id": 1 if entrant else 0,
                  "surface_recovery_enabled": enabled,
                  "surface_measurement_supported": supported,
                  "acquisition_epoch": epoch},
    )


def selected_manager(**overrides):
    tracking = manager(**overrides)
    tracking.lock_detection(0, target_uuid="synthetic-selected-task")
    tracking.update_with_result([synthetic(0.)], timestamp=0.)
    return tracking


def frame(tracking, timestamp, *entrants, **anchor_overrides):
    return tracking.update_with_result(
        [synthetic(timestamp, **anchor_overrides), *entrants], timestamp=timestamp,
    )


def recorded(payload):
    return Detection(
        payload["bbox"], "car", payload["confidence"], payload["timestamp"],
        payload["position_3d"], depth_stats=payload["depth_stats"],
        metadata=payload["metadata"],
    )


def restored_recorded_manager(fixture, *, policy=TargetManager):
    tracking = manager(policy=policy)
    tracking.lock_detection(0, target_uuid="recorded-conditional-task")
    seed = recorded(fixture["selected_seed"])
    tracking.update_with_result([seed], timestamp=seed.timestamp)
    prior = fixture["selected_prior_state"]
    tracking.target._filter.initialize(
        prior[:3], velocity=prior[3:],
        covariance=fixture["selected_prior_covariance"], timestamp=31.3,
    )
    return tracking


def historical_head39_manager(test, provenance):
    """Load exact historical test-data bytes, independent of Git availability.

    The recorded commit was HEAD39 when this comparison was prepared. Pinning
    the reference bytes keeps HEAD40+ from replacing the old policy in this
    regression. The .py.txt artifact is historical test data, never runtime
    code. Core dependencies remain current; this is not a complete historical
    checkout or a flight replay. Frozen validation copies need no .git folder.
    """
    reference = provenance["reference_commit"] + ":" + provenance["reference_path"]
    source = RISK_FIXTURE.with_name(provenance["reference_fixture_file"]).read_bytes()
    test.assertEqual(hashlib.sha256(source).hexdigest(), provenance["reference_source_sha256"])
    test.assertEqual(len(source), provenance["reference_source_bytes"])
    module_name = "uav_tracking.core._test_historical_head39_identity_reference"
    module = types.ModuleType(module_name)
    module.__package__ = "uav_tracking.core"
    sys.modules[module_name] = module
    try:
        exec(compile(source, reference, "exec"), module.__dict__)
    finally:
        sys.modules.pop(module_name, None)
    return module.TargetManager


class SupportedBirthConfirmationTests(unittest.TestCase):
    def test_recorded_31_3_qualifies_birth_without_changing_selected_kf(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        selected = recorded(fixture["selected_update"])
        overlap = recorded(fixture["unmatched_overlap"])
        new = restored_recorded_manager(fixture)
        old = restored_recorded_manager(fixture, policy=Humble39BirthPolicyAblation)
        observations = [selected, overlap]
        covariance = new._measurement_covariance(new.target._filter, selected)
        np.testing.assert_allclose(
            covariance, fixture["expected_selected_measurement_covariance"],
            rtol=1e-12, atol=1e-12,
        )
        self.assertAlmostEqual(
            new.target._filter.mahalanobis_distance(
                selected.position_3d, measurement_covariance=covariance),
            fixture["expected_selected_mahalanobis_squared"], places=10,
        )
        self.assertIsNotNone(new._association_cost(new.target, selected))
        self.assertIsNone(new._association_cost(new.target, overlap))
        self.assertGreater(np.linalg.norm(np.asarray(selected.position_3d) - overlap.position_3d), 1.5)
        result = new.update_with_result(observations, timestamp=31.3)
        legacy = old.update_with_result(observations, timestamp=31.3)
        self.assertEqual(len(legacy.tracks), 2)
        self.assertEqual(legacy.spawn_deferred_detection_indices, ())
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(result.spawn_deferred_detection_indices, (1,))
        self.assertEqual(dict(result.spawn_deferred_reasons)[1], "overlap_birth_surface_support_unknown")
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertEqual(new.target_uuid, "recorded-conditional-task")
        self.assertEqual(result.target.last_detection, selected)
        self.assertEqual(observations, [selected, overlap])
        diagnostics = result.target.last_measurement_diagnostics
        for key, expected in (
            ("measurement_covariance", fixture["expected_selected_measurement_covariance"]),
            ("posterior_state", fixture["expected_selected_posterior_state"]),
            ("posterior_covariance", fixture["expected_selected_posterior_covariance"]),
        ):
            np.testing.assert_allclose(diagnostics[key], expected, rtol=1e-12, atol=1e-12)
            np.testing.assert_array_equal(diagnostics[key], legacy.target.last_measurement_diagnostics[key])
        self.assertEqual(diagnostics["mahalanobis_squared"], legacy.target.last_measurement_diagnostics["mahalanobis_squared"])
        self.assertEqual(diagnostics["reason"], "ACCEPTED")
        self.assertEqual(result.target.rejected_measurements, 0)
        self.assertEqual(new.association_max_distance, 1.5)
        self.assertEqual(new.gate_threshold, 9.21)
        self.assertEqual(new.SPAWN_CONTAINMENT_MIN, .95)
        self.assertEqual(new.SPAWN_AREA_RATIO_MAX, .8)

    def test_synthetic_two_supported_unique_unmatched_acquisitions_allow_birth(self):
        tracking = selected_manager()
        first = frame(tracking, .1, synthetic(.1, entrant=True))
        self.assertEqual(len(first.tracks), 1)
        self.assertEqual(first.spawn_deferred_detection_indices, (1,))
        self.assertEqual(tracking._next_track_id, 2)
        self.assertEqual(len(tracking._birth_evidence), 1)
        second = frame(tracking, .2, synthetic(.2, entrant=True))
        self.assertEqual(len(second.tracks), 2)
        self.assertEqual(second.spawn_deferred_detection_indices, ())
        self.assertEqual(second.tracks[1].last_measurement_timestamp, .2)
        self.assertEqual(second.status, TargetStatus.TRACKING)
        self.assertEqual(tracking.target_uuid, "synthetic-selected-task")

    def test_synthetic_unknown_repeated_observations_never_count_as_support(self):
        tracking = selected_manager()
        for timestamp in (.1, .2, .3, .4):
            result = frame(tracking, timestamp, synthetic(timestamp, entrant=True, supported=False))
            self.assertEqual(len(result.tracks), 1)
            self.assertEqual(len(tracking._birth_evidence), 0)
            self.assertEqual(dict(result.spawn_deferred_reasons)[1], "overlap_birth_surface_support_unknown")
            self.assertEqual(result.target.last_measurement_timestamp, timestamp)

    def test_synthetic_unknown_between_supported_frames_breaks_confirmation(self):
        tracking = selected_manager()
        frame(tracking, .1, synthetic(.1, entrant=True))
        frame(tracking, .2, synthetic(.2, entrant=True, supported=False))
        result = frame(tracking, .3, synthetic(.3, entrant=True))
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(dict(result.spawn_deferred_reasons)[1], "overlap_birth_requires_second_supported_acquisition")
        self.assertEqual(len(frame(tracking, .4, synthetic(.4, entrant=True)).tracks), 2)

    def test_synthetic_duplicate_stamp_is_not_an_independent_acquisition(self):
        tracking = selected_manager()
        frame(tracking, .1, synthetic(.1, entrant=True))
        repeated = frame(tracking, .1, synthetic(.1, entrant=True))
        self.assertEqual(len(repeated.tracks), 1)
        self.assertEqual(dict(repeated.spawn_deferred_reasons)[1], "overlap_birth_requires_second_supported_acquisition")

    def test_synthetic_reused_detection_with_new_update_stamp_is_not_new_evidence(self):
        tracking = selected_manager()
        candidate = synthetic(.1, entrant=True)
        frame(tracking, .1, candidate)
        reused = frame(tracking, .2, candidate)
        self.assertEqual(len(reused.tracks), 1)
        self.assertEqual(dict(reused.spawn_deferred_reasons)[1], "overlap_birth_acquisition_identity_missing")
        self.assertEqual(len(tracking._birth_evidence), 0)
        self.assertEqual(reused.target.last_measurement_timestamp, .2)

    def test_synthetic_epoch_change_cannot_join_birth_evidence(self):
        tracking = selected_manager()
        frame(tracking, .1, synthetic(.1, entrant=True, epoch=0))
        changed = frame(tracking, .2, synthetic(.2, entrant=True, epoch=1), epoch=1)
        self.assertEqual(len(changed.tracks), 1)
        self.assertEqual(dict(changed.spawn_deferred_reasons)[1], "overlap_birth_requires_second_supported_acquisition")
        self.assertEqual(len(frame(tracking, .3, synthetic(.3, entrant=True, epoch=1), epoch=1).tracks), 2)

    def test_synthetic_missing_camera_acquisition_breaks_support_even_without_empty_update(self):
        tracking = selected_manager()
        frame(tracking, .1, synthetic(.1, entrant=True))
        skipped = frame(tracking, .3, synthetic(.3, entrant=True))
        self.assertEqual(len(skipped.tracks), 1)
        self.assertEqual(dict(skipped.spawn_deferred_reasons)[1], "overlap_birth_requires_second_supported_acquisition")
        self.assertEqual(len(frame(tracking, .4, synthetic(.4, entrant=True)).tracks), 2)

    def test_synthetic_empty_acquisition_clears_pending_support(self):
        tracking = selected_manager()
        frame(tracking, .1, synthetic(.1, entrant=True))
        tracking.update_with_result([], timestamp=.2)
        self.assertEqual(len(tracking._birth_evidence), 0)
        result = frame(tracking, .3, synthetic(.3, entrant=True))
        self.assertEqual(len(result.tracks), 1)

    def test_synthetic_missing_entrant_with_valid_anchor_clears_support(self):
        tracking = selected_manager()
        frame(tracking, .1, synthetic(.1, entrant=True))
        frame(tracking, .2)
        result = frame(tracking, .3, synthetic(.3, entrant=True))
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(dict(result.spawn_deferred_reasons)[1], "overlap_birth_requires_second_supported_acquisition")

    def test_synthetic_projection_ticks_cannot_create_second_birth_measurement(self):
        tracking = selected_manager()
        frame(tracking, .1, synthetic(.1, entrant=True))
        for timestamp in (.12, .14, .16, .18):
            projected = tracking.predict_with_result(timestamp)
            self.assertEqual(len(projected.tracks), 1)
            self.assertEqual(tracking._next_track_id, 2)
            self.assertEqual(len(tracking._birth_evidence), 1)
        self.assertEqual(len(frame(tracking, .2, synthetic(.2, entrant=True)).tracks), 2)

    def test_synthetic_one_previous_to_two_current_candidates_is_not_greedily_promoted(self):
        tracking = selected_manager()
        frame(tracking, .1, synthetic(.1, entrant=True))
        candidates = [synthetic(.2, entrant=True, position=(3. + offset, 0., 1.)) for offset in (-.1, .1)]
        result = frame(tracking, .2, *candidates)
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(result.spawn_deferred_detection_indices, (1, 2))
        self.assertEqual(set(dict(result.spawn_deferred_reasons).values()), {"overlap_birth_confirmation_ambiguous"})
        self.assertEqual(tracking._next_track_id, 2)

    def test_synthetic_two_previous_to_one_current_candidate_is_not_greedily_promoted(self):
        tracking = selected_manager()
        frame(tracking, .1, synthetic(.1, entrant=True, position=(2.9, 0., 1.)),
              synthetic(.1, entrant=True, position=(3.1, 0., 1.)))
        self.assertEqual(len(tracking._birth_evidence), 2)
        result = frame(tracking, .2, synthetic(.2, entrant=True))
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(dict(result.spawn_deferred_reasons)[1], "overlap_birth_confirmation_ambiguous")

    def test_synthetic_candidate_order_does_not_choose_a_pending_identity(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                tracking = selected_manager()
                frame(tracking, .1, synthetic(.1, entrant=True))
                observations = [synthetic(.2), synthetic(.2, entrant=True, position=(2.9, 0., 1.)),
                                synthetic(.2, entrant=True, position=(3.1, 0., 1.))]
                if reverse:
                    observations.reverse()
                result = tracking.update_with_result(observations, timestamp=.2)
                self.assertEqual(len(result.tracks), 1)
                self.assertEqual(set(dict(result.spawn_deferred_reasons).values()), {"overlap_birth_confirmation_ambiguous"})
                self.assertEqual(result.target.last_detection.position_3d, (0., 0., 1.))

    def test_synthetic_zero_iou_cannot_confirm_even_with_zero_association_iou_threshold(self):
        tracking = selected_manager(association_iou_threshold=0.)
        first = synthetic(.1, entrant=True, bbox=(-10., 0., 1., 20.))
        second = synthetic(.2, entrant=True, bbox=(19., 0., 30., 20.))
        frame(tracking, .1, first)
        result = frame(tracking, .2, second)
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(dict(result.spawn_deferred_reasons)[1], "overlap_birth_requires_second_supported_acquisition")

    def test_synthetic_assigned_detection_cannot_be_borrowed_as_birth_support(self):
        tracking = selected_manager(kf_kwargs={"initial_position_covariance": 1., "initial_velocity_covariance": .01})
        frame(tracking, .1, synthetic(.1, entrant=True, position=(1.6, 0., 1.)))
        self.assertEqual(len(tracking._birth_evidence), 1)
        # A synthetic uncertain prior makes this observation a genuine
        # assignment to the established track, rather than a rejected edge.
        tracking.target._filter.initialize((0., 0., 1.), covariance=np.eye(6), timestamp=.2)
        assigned = tracking.update_with_result(
            [synthetic(.2, entrant=True, position=(1.4, 0., 1.))], timestamp=.2,
        )
        self.assertEqual(assigned.associations, ((1, 0),))
        self.assertEqual(len(assigned.tracks), 1)
        self.assertEqual(len(tracking._birth_evidence), 0)

    def test_synthetic_reserved_detection_cannot_be_borrowed_as_birth_support(self):
        tracking = manager()
        tracking.lock_detection(0, target_uuid="two-established-task")
        tracking.update_with_result(
            [synthetic(0.), synthetic(0., entrant=True, bbox=(40., 0., 60., 20.), position=(2.8, 0., 1.))], timestamp=0.,
        )
        frame(tracking, .1, synthetic(.1, entrant=True, position=(1.6, 0., 1.)))
        self.assertEqual(len(tracking._birth_evidence), 1)
        # Synthetic priors deliberately make both established identities
        # feasible; no data from a later recorded flight is implied.
        for track in tracking.tracks:
            track._filter.initialize(track.position_3d, covariance=np.eye(6), timestamp=.2)
        result = tracking.update_with_result(
            [synthetic(.2, entrant=True, position=(1.4, 0., 1.))], timestamp=.2,
        )
        self.assertEqual(result.ambiguous_track_ids, (1, 2))
        self.assertEqual(result.ambiguous_detection_indices, (0,))
        self.assertEqual(result.associations, ())
        self.assertEqual(len(tracking._birth_evidence), 0)
        self.assertEqual(len(result.tracks), 2)

    def test_synthetic_explicit_selection_bypasses_qualification_with_new_uuid(self):
        tracking = selected_manager()
        tracking.lock_detection(1, target_uuid="explicit-new-task")
        entrant = synthetic(.1, entrant=True, supported=False)
        result = frame(tracking, .1, entrant)
        self.assertEqual(result.target.last_detection, entrant)
        self.assertEqual(result.target.track_id, 2)
        self.assertEqual(tracking.target_uuid, "explicit-new-task")
        self.assertEqual(result.spawn_deferred_detection_indices, ())

    def test_synthetic_auto_unique_counts_original_candidates_even_when_birth_deferred(self):
        tracking = manager(mode=TargetMode.AUTO_UNIQUE)
        tracking.update_with_result([synthetic(0.)], timestamp=0.)
        result = frame(tracking, .1, synthetic(.1, entrant=True, supported=False))
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.spawn_deferred_detection_indices, (1,))
        self.assertEqual(len(result.tracks), 1)

    def test_synthetic_existing_two_confirmed_tracks_keep_true_ambiguity(self):
        tracking = manager(kf_kwargs={"initial_position_covariance": 1., "initial_velocity_covariance": .01})
        tracking.lock_detection(0, target_uuid="two-established-task")
        tracking.update_with_result(
            [synthetic(0.), synthetic(0., entrant=True, bbox=(40., 0., 60., 20.), position=(.7, 0., 1.))], timestamp=0.,
        )
        result = tracking.update_with_result(
            [synthetic(.1, position=(.35, 0., 1.), bbox=(0., 0., 60., 20.))], timestamp=.1,
        )
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(result.ambiguous_track_ids, (1, 2))
        self.assertEqual(result.spawn_deferred_detection_indices, ())
        self.assertTrue(all(track.last_measurement_timestamp == 0. for track in result.tracks))

    def test_synthetic_qualification_never_clears_long_loss_reselection_latch(self):
        tracking = selected_manager()
        frame(tracking, .1, synthetic(.1, entrant=True))
        self.assertEqual(tracking.predict_with_result(.851).status, TargetStatus.LOST)
        result = frame(tracking, .9, synthetic(.9, entrant=True))
        self.assertEqual(result.status, TargetStatus.LOST)
        self.assertEqual(tracking.target_uuid, "synthetic-selected-task")
        self.assertEqual(result.target.last_measurement_timestamp, .1)
        self.assertTrue(tracking._requires_reselection)

    def test_synthetic_initial_unanchored_frame_preserves_original_births(self):
        tracking = manager(mode=TargetMode.AUTO_UNIQUE)
        result = tracking.update_with_result(
            [synthetic(0.), synthetic(0., entrant=True, supported=False)], timestamp=0.,
        )
        self.assertEqual(len(result.tracks), 2)
        self.assertEqual(result.spawn_deferred_detection_indices, ())
        self.assertEqual(result.status, TargetStatus.AMBIGUOUS)

    def test_synthetic_image_separation_preserves_immediate_birth(self):
        tracking = selected_manager()
        result = frame(tracking, .1, synthetic(.1, entrant=True, bbox=(40., 0., 60., 20.), supported=False))
        self.assertEqual(len(result.tracks), 2)
        self.assertEqual(result.spawn_deferred_detection_indices, ())

    def test_synthetic_old_nonoptin_api_preserves_immediate_birth(self):
        tracking = selected_manager(supported_birth_confirmation_required=False)
        result = frame(tracking, .1, synthetic(.1, entrant=True, enabled=False, supported=False))
        self.assertEqual(len(result.tracks), 2)
        self.assertEqual(result.spawn_deferred_detection_indices, ())

    def test_synthetic_metadata_optin_applies_without_constructor_enforcement(self):
        tracking = selected_manager(supported_birth_confirmation_required=False)
        result = frame(tracking, .1, synthetic(.1, entrant=True, enabled=True, supported=False))
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(result.spawn_deferred_detection_indices, (1,))

    def test_synthetic_strict_constructor_cannot_be_bypassed_with_missing_flags(self):
        tracking = selected_manager()
        candidate = replace(synthetic(.1, entrant=True), metadata={"candidate_id": 1})
        result = frame(tracking, .1, candidate)
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(dict(result.spawn_deferred_reasons)[1], "overlap_birth_surface_support_unknown")

    def test_synthetic_support_flags_require_boolean_true(self):
        for enabled, supported in (("true", True), (True, "true"), (1, True), (True, 1)):
            with self.subTest(enabled=enabled, supported=supported):
                tracking = selected_manager()
                result = frame(tracking, .1, synthetic(.1, entrant=True, enabled=enabled, supported=supported))
                self.assertEqual(len(result.tracks), 1)
                self.assertEqual(len(tracking._birth_evidence), 0)

    def test_synthetic_invalid_depth_quality_cannot_confirm_world_measurement(self):
        for fraction in (0., -.1, 1.1, float("nan"), float("inf"), None, "bad"):
            with self.subTest(fraction=fraction):
                tracking = selected_manager()
                candidate = replace(synthetic(.1, entrant=True),
                                    depth_stats={"valid_fraction": fraction, "std": .05})
                result = frame(tracking, .1, candidate)
                self.assertEqual(len(result.tracks), 1)
                self.assertEqual(dict(result.spawn_deferred_reasons)[1], "overlap_birth_world_depth_missing")
                self.assertEqual(len(tracking._birth_evidence), 0)

    def test_synthetic_missing_world_depth_does_not_create_birth_support(self):
        tracking = selected_manager()
        # The tiny positive image overlap is below the ordinary association
        # threshold, so missing depth cannot create a feasible existing edge.
        candidate = replace(synthetic(.1, entrant=True, bbox=(19.99, 0., 39.99, 20.)),
                            position_3d=None)
        result = frame(tracking, .1, candidate)
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(dict(result.spawn_deferred_reasons)[1], "overlap_birth_world_depth_missing")
        self.assertEqual(len(tracking._birth_evidence), 0)

    def test_synthetic_invalid_acquisition_epoch_cannot_supply_support(self):
        for epoch in (-1, True, "0", None):
            with self.subTest(epoch=epoch):
                tracking = selected_manager()
                result = frame(tracking, .1, synthetic(.1, entrant=True, epoch=epoch))
                self.assertEqual(dict(result.spawn_deferred_reasons)[1], "overlap_birth_acquisition_identity_missing")
                self.assertEqual(len(tracking._birth_evidence), 0)

    def test_synthetic_maximum_uint64_epoch_can_confirm_consecutive_support(self):
        tracking = selected_manager()
        maximum = 2**64 - 1
        first = frame(tracking, .1, synthetic(.1, entrant=True, epoch=maximum), epoch=maximum)
        second = frame(tracking, .2, synthetic(.2, entrant=True, epoch=maximum), epoch=maximum)
        self.assertEqual(len(first.tracks), 1)
        self.assertEqual(len(second.tracks), 2)

    def test_synthetic_uint64_overflow_epoch_never_creates_or_joins_evidence(self):
        for epoch in (2**64, 2**64 + 1, 10**100):
            with self.subTest(epoch=epoch):
                tracking = selected_manager()
                frame(tracking, .1, synthetic(.1, entrant=True))
                invalid = frame(tracking, .2, synthetic(.2, entrant=True, epoch=epoch))
                self.assertEqual(len(invalid.tracks), 1)
                self.assertEqual(dict(invalid.spawn_deferred_reasons)[1], "overlap_birth_acquisition_identity_missing")
                self.assertEqual(len(tracking._birth_evidence), 0)
                restarted = frame(tracking, .3, synthetic(.3, entrant=True))
                self.assertEqual(len(restarted.tracks), 1)

    def test_synthetic_pending_storage_is_bounded_without_allocating_track_ids(self):
        tracking = selected_manager()
        candidates = [synthetic(.1, entrant=True) for _ in range(65)]
        result = frame(tracking, .1, *candidates)
        self.assertEqual(len(tracking._birth_evidence), 64)
        self.assertEqual(len(result.tracks), 1)
        self.assertEqual(tracking._next_track_id, 2)
        self.assertEqual(dict(result.spawn_deferred_reasons)[65], "overlap_birth_confirmation_capacity")
        tracking.update_with_result([], timestamp=.2)
        self.assertEqual(len(tracking._birth_evidence), 0)

    def test_synthetic_reset_and_mode_change_clear_pending_birth_evidence(self):
        for action in ("reset", "set_mode", "lock_detection", "lock_target"):
            with self.subTest(action=action):
                tracking = selected_manager()
                frame(tracking, .1, synthetic(.1, entrant=True))
                if action == "reset":
                    tracking.reset()
                elif action == "set_mode":
                    tracking.set_mode(TargetMode.LOCKED_TARGET)
                elif action == "lock_detection":
                    tracking.lock_detection(0, target_uuid="new-synthetic-task")
                else:
                    tracking.lock_target(1, target_uuid="new-synthetic-task")
                self.assertEqual(len(tracking._birth_evidence), 0)

    def test_synthetic_person_nonoptin_api_keeps_original_behavior(self):
        tracking = manager(supported_birth_confirmation_required=False)
        tracking.lock_detection(0)
        tracking.update_with_result([synthetic(0., class_name="person", enabled=False)], timestamp=0.)
        result = tracking.update_with_result(
            [synthetic(.1, class_name="person", enabled=False),
             synthetic(.1, entrant=True, class_name="person", enabled=False)], timestamp=.1,
        )
        self.assertEqual(len(result.tracks), 2)
        self.assertEqual(result.spawn_deferred_detection_indices, ())

    def test_synthetic_one_frame_real_entrant_remains_an_offline_identity_risk(self):
        tracking = selected_manager()
        first = frame(tracking, .1, synthetic(.1, entrant=True, position=(1.6, 0., 1.), supported=False))
        self.assertEqual(len(first.tracks), 1)
        # Ambiguous physical histories can produce the same detector inputs:
        # here the original becomes hidden and a one-frame entrant supplies a
        # compatible single surface. These synthetic labels are evaluation
        # data only and never passed to the manager or used to choose a match.
        offline_visible_entity = {.1: "original", .2: "entrant"}
        next_detection = synthetic(.2, position=(.15, 0., 1.))
        result = tracking.update_with_result([next_detection], timestamp=.2)
        self.assertEqual(result.status, TargetStatus.TRACKING)
        self.assertEqual(result.target.last_detection, next_detection)
        self.assertEqual(tracking.target_uuid, "synthetic-selected-task")
        self.assertNotEqual(offline_visible_entity[.1], offline_visible_entity[.2])
        # Preserving track UUID alone therefore cannot certify identity.
        self.assertEqual(result.target.last_measurement_timestamp, .2)

    def test_actual_head39_differential_exposes_one_frame_entrant_policy_risk(self):
        """New TRACKING versus actual old AMBIGUOUS is a tradeoff, not safety.

        Every input here is synthetic. The physical labels used below exist
        only in offline assertions. The runtime measurements support both
        continued visibility of the selected object and an entrant replacing
        it after occlusion. No complete ReID or physical identity proof is
        supplied by the boolean surface-support metadata.
        """
        fixture = json.loads(RISK_FIXTURE.read_text(encoding="utf-8"))
        old_type = historical_head39_manager(self, fixture["provenance"])
        parameters = fixture["manager_parameters"]
        old = old_type(mode=TargetMode.LOCKED_TARGET, **parameters)
        new = TargetManager(mode=TargetMode.LOCKED_TARGET,
                            supported_birth_confirmation_required=True, **parameters)
        outputs = []
        for tracking in (old, new):
            tracking.lock_detection(0, target_uuid="synthetic-head39-differential-task")
            recorded_outputs = []
            for acquisition in fixture["frames"]:
                observations = [Detection(class_id="car", **payload)
                                for payload in acquisition["detections"]]
                result = tracking.update_with_result(observations, timestamp=acquisition["timestamp"])
                recorded_outputs.append({
                    "timestamp": acquisition["timestamp"], "status": result.status.value,
                    "track_count": len(result.tracks),
                    "associations": [list(item) for item in result.associations],
                    "ambiguous_track_ids": list(result.ambiguous_track_ids),
                    "target_last_measurement_s": result.target.last_measurement_timestamp,
                    "target_uuid": tracking.target_uuid,
                    "selected_measurement_current": result.target._matched_this_frame,
                })
            outputs.append(recorded_outputs)
        self.assertEqual(outputs[0], fixture["expected_historical_manager_outputs"])
        self.assertEqual(outputs[1], fixture["expected_candidate_outputs"])
        self.assertEqual(outputs[0][-1]["status"], "ambiguous")
        self.assertEqual(outputs[0][-1]["target_last_measurement_s"], .1)
        self.assertEqual(outputs[1][-1]["status"], "tracking")
        self.assertEqual(outputs[1][-1]["target_last_measurement_s"], .2)
        offline_physical_histories = {
            "continued_selected_visibility": ("selected", "selected"),
            "real_entrant_after_selected_occlusion": ("selected", "entrant"),
        }
        self.assertEqual(offline_physical_histories["continued_selected_visibility"][0],
                         offline_physical_histories["continued_selected_visibility"][1])
        self.assertNotEqual(offline_physical_histories["real_entrant_after_selected_occlusion"][0],
                            offline_physical_histories["real_entrant_after_selected_occlusion"][1])
        self.assertEqual(old.target_uuid, new.target_uuid)
        # On the second possible history, new fusion may follow the wrong
        # physical object while old HOLD avoids committing that observation.
        # Keeping this differential passing explicitly preserves the risk;
        # neither engineering PASS nor fewer unknowns can negate it.


if __name__ == "__main__":
    unittest.main()
