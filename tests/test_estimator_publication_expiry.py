"""Independent adapter regressions for elapsed loss between output ticks."""
from __future__ import annotations

import json
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import numpy as np

import test_estimator_timing as timing
from uav_tracking.core import TargetMode, TargetStatus, TrackState
from uav_tracking.core.navigation import NavigationEstimate
from uav_tracking_nodes.navigation_estimator import NavigationEstimator


class EstimatorPublicationExpiryTests(unittest.TestCase):
    def setUp(self):
        timing.EstimatorAdapterTimingTests.setUp(self)

    def seed_target(self, mode=TargetMode.AUTO_UNIQUE, acquired=1.0, received=1.1):
        self.node._manager = timing.manager(mode)
        if mode == TargetMode.LOCKED_TARGET:
            self.node._manager.lock_detection(0, target_uuid="original-selected-task")
        self.time = received
        source = timing.observation(acquired)
        self.assertTrue(self.node._commit_observations([source], source))
        self.assertEqual(self.messages[-1].state, timing.FakeState.STATE_MEASURED)
        return self.node._manager.target_uuid, self.node._manager.target.track_id

    def complete_frame(self, acquired, received, observations=()):
        self.time = received
        source = NS(header=NS(stamp=timing.stamp(acquired), frame_id="camera_optical"),
                    observations=list(observations))
        self.node._on_observation_frame(source)
        return source

    def attach_navigation_and_tracks(self):
        self.nav_messages, self.nav_diagnostics, self.track_messages = [], [], []
        self.node._navigation_estimator = NavigationEstimator()
        self.node._navigation_last_diagnostics = {}
        reference = NavigationEstimate(
            valid=True, position_world_m=np.array([8., 0., 0.]), covariance=np.eye(3) * .01,
            reason="independent_valid_reference", reference_kind="ground_center",
            support_count=100, heading_source="test")
        accepted = self.node._navigation_estimator.update(
            reference, timestamp=self.node._manager.target.last_measurement_timestamp,
            target_uuid=self.node._manager.target_uuid, track_id=self.node._manager.target.track_id)
        self.assertTrue(accepted.accepted)
        self.node._navigation_enabled = True
        self.node._navigation_publisher = NS(publish=self.nav_messages.append)
        self.node._navigation_diagnostics_publisher = NS(publish=self.nav_diagnostics.append)
        self.node._tracks_publisher = NS(publish=self.track_messages.append)
        string_patch = patch.object(timing.estimator, "String", lambda: NS(data=""), create=True)
        string_patch.start()
        self.addCleanup(string_patch.stop)
        return reference

    def assert_lost_selected_outputs(self, identity, track_id, now):
        message = self.messages[-1]
        self.assertEqual(message.state, timing.FakeState.STATE_LOST)
        self.assertFalse(message.target_visible)
        self.assertEqual((message.target_uuid, message.track_id), (identity, track_id))
        self.assertEqual(self.node._manager.status, TargetStatus.LOST)
        self.assertEqual(self.node._manager.target.state, TrackState.LOST)
        self.assertAlmostEqual(self.node._stamp_seconds(message.header.stamp), now)

    def test_good_detection_cannot_hide_gap_crossed_during_transform(self):
        for mode in (TargetMode.AUTO_UNIQUE, TargetMode.LOCKED_TARGET):
            with self.subTest(mode=mode):
                self.setUp()
                identity, track_id = self.seed_target(mode)
                transform = self.node._transform

                def slow_transform(observation):
                    position = transform(observation)
                    self.time = 1.764  # Callback began at 1.744, before expiry.
                    return position

                self.node._transform = slow_transform
                source = timing.observation(1.6)
                self.time = 1.744
                self.assertTrue(self.node._commit_observations([source], source))
                self.assert_lost_selected_outputs(identity, track_id, 1.764)
                self.assertEqual(self.node._manager.target.last_measurement_timestamp, 1.0)
                self.assertEqual(self.node._manager.target._filter.timestamp, 1.6)
                self.assertEqual(self.node._last_observation_timestamp, 1.6)
                self.assertEqual(self.node._stamp_seconds(source.header.stamp), 1.6)
                self.assertAlmostEqual(self.messages[-1].prediction_age_s, .764)
                self.assertEqual(self.warnings, [])

    def test_atomic_empty_frame_expires_without_waiting_for_next_timer(self):
        identity, track_id = self.seed_target(acquired=50.4, received=50.5)
        self.time = 51.144
        self.node._flush()
        source = self.complete_frame(51., 51.160)
        self.assert_lost_selected_outputs(identity, track_id, 51.160)
        self.assertEqual(self.node._last_observation_timestamp, 51.)
        self.assertEqual(self.node._stamp_seconds(source.header.stamp), 51.)
        self.assertAlmostEqual(self.messages[-1].prediction_age_s, .760)

    def test_legacy_empty_output_tick_has_same_elapsed_loss_boundary(self):
        identity, track_id = self.seed_target(acquired=50.4, received=50.5)
        self.time = 51.144
        self.node._flush()
        self.assertEqual(self.messages[-1].state, timing.FakeState.STATE_PREDICTED)
        self.time = 51.160
        self.node._flush()
        self.assert_lost_selected_outputs(identity, track_id, 51.160)
        self.assertEqual(self.node._last_observation_timestamp, 50.4)
        self.assertEqual(self.node._manager.target._filter.timestamp, 50.4)

    def test_legacy_batched_distractor_cannot_replace_expired_selected_target(self):
        identity, track_id = self.seed_target(TargetMode.LOCKED_TARGET, acquired=50.4, received=50.5)
        self.time = 51.130
        self.node._on_observation(timing.observation(51., x=30.))
        self.time = 51.160
        self.node._flush()
        self.assert_lost_selected_outputs(identity, track_id, 51.160)
        self.assertEqual(self.node._last_observation_timestamp, 51.)
        self.assertEqual(self.node._manager.target.last_measurement_timestamp, 50.4)

    def test_publication_crossing_cannot_revive_cached_navigation_or_selected_track(self):
        identity, track_id = self.seed_target(TargetMode.LOCKED_TARGET)
        self.attach_navigation_and_tracks()

        def slow_optional_navigation(_result, _observations, _source, _timestamp):
            self.time = 1.764

        self.node._update_navigation = slow_optional_navigation
        source = self.complete_frame(1.6, 1.744)
        self.assert_lost_selected_outputs(identity, track_id, 1.764)
        nav = self.nav_messages[-1]
        self.assertEqual(nav.state, timing.FakeState.STATE_LOST)
        self.assertFalse(nav.target_visible)
        self.assertEqual([nav.position_m.x, nav.position_m.y, nav.position_m.z], [0., 0., 0.])
        self.assertEqual([nav.velocity_mps.x, nav.velocity_mps.y, nav.velocity_mps.z], [0., 0., 0.])
        self.assertEqual(nav.covariance, [0.] * 36)
        self.assertIsNone(self.node._navigation_estimator.measured_timestamp_s)
        diagnostic = json.loads(self.nav_diagnostics[-1].data)
        self.assertFalse(diagnostic["valid"])
        self.assertEqual(diagnostic["output_surface_status"], "lost")
        self.assertEqual(diagnostic["state_reason"], "surface_lost")
        tracks = json.loads(self.track_messages[-1].data)
        self.assertEqual(tracks["target_status"], "lost")
        self.assertTrue(tracks["projected"])
        self.assertEqual(tracks["target_uuid"], identity)
        self.assertEqual(tracks["target_track_id"], track_id)
        selected = next(item for item in tracks["tracks"] if item["selected"])
        self.assertEqual(selected["state"], "lost")
        self.assertFalse(selected["matched"])
        self.assertAlmostEqual(tracks["acquisition_s"], 1.6)
        self.assertAlmostEqual(tracks["output_s"], 1.764)
        self.assertEqual(self.node._stamp_seconds(source.header.stamp), 1.6)

    def test_explicit_box_reselection_and_new_reference_can_resume_after_latched_loss(self):
        identity, track_id = self.seed_target(TargetMode.LOCKED_TARGET)
        reference = self.attach_navigation_and_tracks()
        self.complete_frame(1.6, 1.764)
        self.assert_lost_selected_outputs(identity, track_id, 1.764)
        self.assertIsNone(self.node._navigation_estimator.measured_timestamp_s)
        # A later, well formed return cannot clear the original task's latch.
        self.complete_frame(1.8, 1.9, [timing.observation(1.8)])
        self.assertEqual(self.messages[-1].state, timing.FakeState.STATE_LOST)
        self.assertEqual(self.nav_messages[-1].state, timing.FakeState.STATE_LOST)
        selection = NS(action=2, track_id=0, target_uuid="explicit-new-task", class_name="person",
                       center_u_px=5., center_v_px=5., width_px=10., height_px=10.)
        constants = NS(ACTION_CLEAR=0, ACTION_RESET=1, ACTION_SELECT=2)
        with patch.object(timing.estimator, "TargetSelection", constants, create=True):
            self.node._on_selection(selection)
        # Only an explicit selection plus a valid independent new-task nav
        # reference permits a new measured navigation state.
        with patch.object(self.node, "_navigation_reference", return_value=(reference, {})):
            self.complete_frame(2., 2.1, [timing.observation(2.)])
        self.assertEqual(self.messages[-1].target_uuid, "explicit-new-task")
        self.assertIsNone(self.node._pending_selection)
        self.assertEqual(self.messages[-1].state, timing.FakeState.STATE_MEASURED)
        self.assertEqual(self.node._manager.target.last_measurement_timestamp, 2.)
        self.assertEqual(self.node._manager.target._filter.timestamp, 2.)
        self.assertEqual(self.nav_messages[-1].state, timing.FakeState.STATE_MEASURED)
        self.assertTrue(self.nav_messages[-1].target_visible)
        self.assertEqual(self.nav_messages[-1].target_uuid, "explicit-new-task")
        self.assertEqual(self.node._navigation_estimator.measured_timestamp_s, 2.)
        tracks = json.loads(self.track_messages[-1].data)
        self.assertEqual(tracks["target_status"], "tracking")
        self.assertFalse(tracks["projected"])

    def test_delayed_fresh_measurement_keeps_filter_and_output_acquisition_causality(self):
        identity, track_id = self.seed_target()
        self.time = 1.7
        self.node._flush()
        self.assertEqual(self.node._manager.target._filter.timestamp, 1.)
        source = self.complete_frame(1.6, 1.72, [timing.observation(1.6)])
        message = self.messages[-1]
        self.assertEqual(message.state, timing.FakeState.STATE_MEASURED)
        self.assertTrue(message.target_visible)
        self.assertEqual((message.target_uuid, message.track_id), (identity, track_id))
        self.assertEqual(self.node._manager.target._filter.timestamp, 1.6)
        self.assertEqual(self.node._manager.target.last_measurement_timestamp, 1.6)
        self.assertEqual(self.node._stamp_seconds(message.header.stamp), 1.6)
        self.assertEqual(self.node._stamp_seconds(source.header.stamp), 1.6)
        self.assertEqual(message.prediction_age_s, 0.)
        self.time = 1.74
        self.node._flush()
        self.assertEqual(self.node._manager.target._filter.timestamp, 1.6)
        self.assertEqual(self.messages[-1].state, timing.FakeState.STATE_PREDICTED)
        self.assertAlmostEqual(self.messages[-1].prediction_age_s, .14)

    def test_one_nanosecond_after_limit_latches_even_with_good_acquisition(self):
        identity, track_id = self.seed_target()
        self.complete_frame(1.6, 1.750000001, [timing.observation(1.6)])
        self.assert_lost_selected_outputs(identity, track_id, 1.750000001)
        self.assertEqual(self.node._manager.target.last_measurement_timestamp, 1.)


if __name__ == "__main__":
    unittest.main()
