"""Acquisition evidence must explain decisions without changing the filter."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

import numpy as np

from uav_tracking.core import ConstantVelocityKalman3D, Detection, TargetManager
from uav_tracking.core.estimator_strategies import ESTIMATOR_METHODS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_nodes"))
from uav_tracking_nodes.stage2_telemetry import track_snapshot


def detection(timestamp, position=(0., 0., 5.), *, box=(10., 20., 50., 80.), candidate=0):
    return Detection(box, "car", .9, timestamp, position,
                     depth_stats={"valid_fraction": 1., "std": .03},
                     metadata={"candidate_id": candidate})


class EstimationDiagnosticTests(unittest.TestCase):
    def test_innovation_prior_posterior_and_nis_use_the_acquisition_time(self):
        estimator = ConstantVelocityKalman3D(measurement_noise_std=[.1, .2, .3])
        estimator.initialize([0., 0., 5.], velocity=[1., 0., 0.], timestamp=1.)
        prior = estimator.project(1.2)
        measurement = np.array([.24, -.02, 5.01])
        covariance = estimator.measurement_covariance(confidence=.9)
        innovation = measurement - prior.position
        innovation_covariance = prior.covariance[:3, :3] + covariance
        self.assertTrue(estimator.update(measurement, timestamp=1.2, confidence=.9))
        record = estimator.last_update_diagnostics
        self.assertEqual(record["measurement_timestamp_s"], 1.2)
        self.assertEqual(record["reason"], "ACCEPTED")
        np.testing.assert_allclose(record["prior_state"], np.r_[prior.position, prior.velocity])
        np.testing.assert_array_equal(record["prior_covariance"], prior.covariance)
        np.testing.assert_allclose(record["innovation_m"], innovation)
        np.testing.assert_array_equal(record["innovation_covariance"], innovation_covariance)
        np.testing.assert_array_equal(record["measurement_covariance"], covariance)
        self.assertAlmostEqual(record["mahalanobis_squared"], innovation @ np.linalg.solve(innovation_covariance, innovation))
        np.testing.assert_array_equal(record["posterior_state"], estimator.x)
        np.testing.assert_array_equal(record["posterior_covariance"], estimator.P)

    def test_rejected_record_is_detached_and_prediction_does_not_relabel_it(self):
        estimator = ConstantVelocityKalman3D(gate_threshold=9.21)
        estimator.initialize([0., 0., 5.], timestamp=0.)
        self.assertFalse(estimator.update([100., 0., 5.], timestamp=.2))
        original = estimator.last_update_diagnostics
        self.assertFalse(original["accepted"])
        self.assertEqual(original["reason"], "MAHALANOBIS_GATE")
        self.assertGreater(original["mahalanobis_squared"], 9.21)
        np.testing.assert_array_equal(original["prior_state"], original["posterior_state"])
        np.testing.assert_array_equal(original["prior_covariance"], original["posterior_covariance"])
        external = estimator.last_update_diagnostics
        external["posterior_covariance"][0][0] = -100
        external["raw_measurement_m"][0] = -100
        estimator.project(.3)
        estimator.predict(timestamp=.3)
        self.assertEqual(estimator.last_update_diagnostics, original)
        json.dumps(original, allow_nan=False)
        estimator.reset()
        self.assertEqual(estimator.last_update_diagnostics, {})

    def test_recorder_does_not_change_gate_state_covariance_or_timestamp(self):
        with_logging = ConstantVelocityKalman3D()
        without_logging = ConstantVelocityKalman3D()
        without_logging._record_update = lambda *args, **kwargs: None
        for index in range(20):
            position = [index * .02, 0., 5.]
            if index in (7, 12):
                position[1] = 100.
            decisions = [value.update(position, timestamp=index * .1, confidence=.8)
                         for value in (with_logging, without_logging)]
            self.assertEqual(decisions[0], decisions[1])
            np.testing.assert_array_equal(with_logging.x, without_logging.x)
            np.testing.assert_array_equal(with_logging.P, without_logging.P)
            self.assertEqual(with_logging.timestamp, without_logging.timestamp)

    def test_all_output_methods_expose_the_shared_gate_and_rejected_candidate(self):
        evidence = []
        for method in ESTIMATOR_METHODS:
            manager = TargetManager(target_class="car", min_hits=1, estimator_method=method,
                                    max_coast_duration_s=.75, gate_threshold=9.21)
            manager.update_with_result([detection(0.)], timestamp=0.)
            self.assertEqual(manager.target.last_measurement_diagnostics["reason"], "INITIALIZED")
            result = manager.update_with_result([detection(.2, (100., 0., 5.),
                                                box=(11., 20., 51., 80.), candidate=7)], timestamp=.2)
            track = result.target
            self.assertEqual(track.bbox, (10., 20., 50., 80.))
            self.assertEqual(track.last_measurement_timestamp, 0.)
            self.assertEqual(track.rejected_measurements, 1)
            record = track.last_measurement_diagnostics
            self.assertEqual(record["attempted_candidate_id"], 7)
            self.assertEqual(record["attempted_bbox_xyxy"], [11., 20., 51., 80.])
            self.assertEqual(record["raw_measurement_m"], [100., 0., 5.])
            self.assertFalse(record["accepted"])
            self.assertEqual(record["estimator_method"], method)
            payload = track_snapshot(result, target_uuid=manager.target_uuid, acquisition_s=.2,
                                     output_s=.2, frame_id="map", projected=False)
            self.assertTrue(payload["tracks"][0]["measurement_diagnostics_current_frame"])
            evidence.append({key: value for key, value in record.items() if key != "estimator_method"})
            json.dumps(payload, allow_nan=False)
        for item in evidence[1:]:
            self.assertEqual(item, evidence[0])

    def test_projected_track_and_serialized_payload_do_not_alias_live_evidence(self):
        manager = TargetManager(target_class="car", min_hits=1, max_coast_duration_s=.75)
        manager.update_with_result([detection(0.)], timestamp=0.)
        original = deepcopy(manager.target.last_measurement_diagnostics)
        projected = manager.predict_with_result(.3)
        payload = track_snapshot(projected, target_uuid=manager.target_uuid, acquisition_s=0.,
                                 output_s=.3, frame_id="map", projected=True)
        self.assertFalse(payload["tracks"][0]["measurement_diagnostics_current_frame"])
        payload["tracks"][0]["measurement_diagnostics"]["posterior_covariance"][0][0] = -7
        projected.target.last_measurement_diagnostics["raw_measurement_m"][0] = -9
        self.assertEqual(manager.target.last_measurement_diagnostics, original)
        self.assertEqual(manager.target._filter.last_update_diagnostics["raw_measurement_m"], [0., 0., 5.])

    def test_missing_world_measurement_cannot_report_a_previous_accept_as_current(self):
        manager = TargetManager(target_class="car", min_hits=1, max_coast_duration_s=.75)
        manager.update_with_result([detection(0.)], timestamp=0.)
        result = manager.update_with_result([detection(.2, position=None)], timestamp=.2)
        record = result.target.last_measurement_diagnostics
        self.assertEqual(record["reason"], "NO_WORLD_MEASUREMENT")
        self.assertFalse(record["accepted"])
        self.assertFalse(record["gate_applied"])
        self.assertIsNone(record["raw_measurement_m"])
        self.assertIsNone(record["innovation_m"])
        self.assertEqual(result.target.last_measurement_timestamp, 0.)


if __name__ == "__main__":
    unittest.main()
