"""Whole-frame acquisition boundaries must not manufacture an extra delay."""

from types import SimpleNamespace as NS
import unittest

import test_estimator_timing as timing
from uav_tracking.core import TargetStatus


class AtomicObservationFrameTests(unittest.TestCase):
    def setUp(self):
        timing.EstimatorAdapterTimingTests.setUp(self)

    def frame(self, acquired, received, xs=(0.0,)):
        self.time = received
        self.node._on_observation_frame(NS(
            header=NS(stamp=timing.stamp(acquired), frame_id="camera_optical"),
            observations=[timing.observation(acquired, x) for x in xs],
        ))

    def test_fresh_complete_frame_commits_before_prediction_expiry_tick(self):
        self.frame(34.0, 34.05)
        self.assertEqual(self.node._manager.target.last_measurement_timestamp, 34.0)
        # The actual failed-flight boundary: adding .02s batching here would
        # let a 34.752 output tick expire a measurement already received.
        self.frame(34.4, 34.744)
        self.assertEqual(self.node._manager.target.last_measurement_timestamp, 34.4)
        self.time = 34.752
        self.node._flush()
        self.assertEqual(self.node._manager.status, TargetStatus.COASTING)
        self.assertLess(self.messages[-1].prediction_age_s, .75)
        self.assertEqual(self.warnings, [])

    def test_multiple_candidates_are_committed_once_and_never_auto_select_first(self):
        self.frame(1.0, 1.1, xs=(0.0, 30.0))
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(len(self.node._manager.tracks), 2)
        self.assertIsNone(self.node._manager.target)
        self.assertEqual(self.node._manager.status, TargetStatus.AMBIGUOUS)
        self.assertEqual(self.node._last_observation_timestamp, 1.0)

    def test_empty_completed_frame_coasts_without_refreshing_measurement(self):
        self.frame(1.0, 1.1)
        self.frame(1.2, 1.3, xs=())
        self.assertEqual(self.node._last_observation_timestamp, 1.2)
        self.assertEqual(self.node._manager.status, TargetStatus.COASTING)
        self.assertEqual(self.node._manager.target.last_measurement_timestamp, 1.0)
        self.assertEqual(len(self.messages), 2)

    def test_mixed_stamp_array_is_rejected_as_a_whole(self):
        self.time = 1.2
        self.node._on_observation_frame(NS(
            header=NS(stamp=timing.stamp(1.0), frame_id="camera_optical"),
            observations=[timing.observation(1.0), timing.observation(1.1, 30.0)],
        ))
        self.assertEqual(self.messages, [])
        self.assertIsNone(self.node._last_observation_timestamp)
        self.assertIn("mixed acquisition", self.warnings[0])

    def test_stale_future_and_duplicate_complete_frames_are_rejected(self):
        self.frame(1.0, 1.1)
        for acquired, received in ((1.0, 1.2), (1.1, 1.8), (2.0, 1.9)):
            self.frame(acquired, received)
        self.assertEqual(self.node._last_observation_timestamp, 1.0)
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(len(self.warnings), 3)


if __name__ == "__main__":
    unittest.main()
