"""Independent navigation freshness and identity safety regression checks."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import numpy as np
from uav_tracking.core.models import TargetStatus
from uav_tracking.core.navigation import NavigationEstimate
NODES_SOURCE = Path(__file__).resolve().parents[1] / 'ros2_ws' / 'src' / 'uav_tracking_nodes'
if str(NODES_SOURCE) not in sys.path:
    sys.path.insert(0, str(NODES_SOURCE))
from uav_tracking_nodes.navigation_estimator import NavigationEstimator  # noqa: E402

def reference(position=(0.0, 0.0, 0.0), covariance=None):
    return NavigationEstimate(position_world_m=np.asarray(position, dtype=float), covariance=np.eye(3) * 0.04 if covariance is None else covariance, valid=True, reason='measured', heading_source='velocity')

def initialized():
    estimator = NavigationEstimator(gate_threshold=9.21)
    assert estimator.update(reference(), 10.0, 'task-a', 1, [1, 0, 0]).accepted
    return estimator

class NavigationEstimatorTests(unittest.TestCase):

    def test_acquisition_time_projection_leaves_delayed_measurement_fusable(self):
        estimator = initialized()
        first = estimator.project(10.0, 'task-a', 1)
        for now in np.arange(10.02, 10.61, 0.02):
            assert estimator.project(float(now), 'task-a', 1, surface_status=TargetStatus.COASTING).valid
        projected = estimator.project(10.6, 'task-a', 1)
        np.testing.assert_allclose(projected.position_world_m, [0.6, 0, 0])
        np.testing.assert_array_equal(estimator.project(10.0, 'task-a', 1).covariance, first.covariance)
        assert estimator.measured_timestamp_s == 10.0
        assert estimator.update(reference([0.2, 0, 0]), 10.2, 'task-a', 1).accepted
        self.assertAlmostEqual(estimator.project(10.6, 'task-a', 1).measurement_age_s, 0.4)

    def test_missing_nav_does_not_borrow_fresh_surface_timestamp(self):
        estimator = initialized()
        for stamp in [10.2, 10.4, 10.6]:
            result = estimator.update(NavigationEstimate(reason='ground_unobservable'), stamp, 'task-a', 1)
            assert not result.accepted
            assert result.diagnostics['reference_reason'] == 'ground_unobservable'
        assert estimator.project(10.75, 'task-a', 1).valid
        stale = estimator.project(10.751, 'task-a', 1)
        assert not stale.valid and stale.reason == 'stale_navigation_measurement'
        assert stale.measured_timestamp_s == 10.0
        assert stale.position_world_m is None

    def test_innovation_rejection_preserves_posterior_and_freshness(self):
        estimator = initialized()
        before = estimator.project(10.2, 'task-a', 1)
        result = estimator.update(reference([1000, 0, 0]), 10.2, 'task-a', 1)
        assert not result.accepted and result.reason == 'mahalanobis_gate'
        assert result.diagnostics['filter']['gate_threshold'] == 9.21
        assert result.diagnostics['filter']['mahalanobis_squared'] > 9.21
        after = estimator.project(10.2, 'task-a', 1)
        np.testing.assert_array_equal(after.position_world_m, before.position_world_m)
        np.testing.assert_array_equal(after.covariance, before.covariance)
        assert after.measured_timestamp_s == 10.0
        assert not estimator.project(10.751, 'task-a', 1).valid

    def test_identity_change_with_invalid_reference_cannot_reuse_old_state(self):
        for new_uuid, new_track in [('task-b', 1), ('task-a', 2)]:
            with self.subTest(new_uuid=new_uuid, new_track=new_track):
                estimator = initialized()
                assert not estimator.update(NavigationEstimate(reason='missing'), 10.1, new_uuid, new_track).accepted
                snapshot = estimator.project(10.2, new_uuid, new_track)
                assert not snapshot.valid and snapshot.reason == 'navigation_uninitialized'
                assert snapshot.measured_timestamp_s is None
                assert estimator.update(reference([20, 0, 0]), 10.3, new_uuid, new_track).accepted
                np.testing.assert_array_equal(estimator.project(10.3, new_uuid, new_track).position_world_m, [20, 0, 0])
                np.testing.assert_array_equal(estimator.project(10.3, new_uuid, new_track).velocity_world_mps, [0, 0, 0])

    def test_identity_change_detected_by_projection_also_discards_previous_state(self):
        estimator = initialized()
        assert not estimator.project(10.1, 'task-b', 1).valid
        assert estimator.measured_timestamp_s is None
        assert not estimator.project(10.2, 'task-a', 1).valid

    def test_ambiguous_surface_prohibits_output_even_with_fresh_navigation(self):
        estimator = initialized()
        blocked = estimator.project(10.1, 'task-a', 1, surface_status=TargetStatus.AMBIGUOUS)
        assert not blocked.valid and blocked.reason == 'surface_ambiguous'
        assert blocked.position_world_m is None and blocked.velocity_world_mps is None
        self.assertAlmostEqual(blocked.measurement_age_s, 0.1)
        assert estimator.measured_timestamp_s == 10.0

    def test_surface_loss_clears_nav_and_cannot_revive_via_status_change(self):
        estimator = initialized()
        assert estimator.project(10.1, 'task-a', 1, surface_status='lost').reason == 'surface_lost'
        assert not estimator.project(10.2, 'task-a', 1, surface_status='tracking').valid
        assert estimator.measured_timestamp_s is None

    def test_invalid_or_nonmonotonic_sources_do_not_refresh_navigation(self):
        for stamp in [10.0, 9.9, float('nan'), float('inf'), -1]:
            with self.subTest(stamp=stamp):
                estimator = initialized()
                assert not estimator.update(reference([10, 0, 0]), stamp, 'task-a', 1).accepted
                assert estimator.measured_timestamp_s == 10.0
                np.testing.assert_allclose(estimator.project(10.2, 'task-a', 1).position_world_m, [0.2, 0, 0])

    def test_bad_covariance_never_enters_filter_or_refreshes_age(self):
        for covariance in [np.ones((2, 2)), np.diag([-1.0, 1, 1]), [[1, 0.2, 0], [0, 1, 0], [0, 0, 1]], np.diag([float('nan'), 1, 1]), None]:
            with self.subTest(covariance=covariance):
                estimator = initialized()
                malformed = SimpleNamespace(valid=True, position_world_m=[0.1, 0, 0], covariance=covariance)
                assert not estimator.update(malformed, 10.2, 'task-a', 1).accepted
                assert estimator.measured_timestamp_s == 10.0
                assert not estimator.project(10.751, 'task-a', 1).valid

    def test_initial_covariance_comes_from_navigation_measurement_and_outputs_are_detached(self):
        covariance = np.diag([0.25, 0.36, 0.49])
        estimator = NavigationEstimator()
        ref = reference([1, 2, 3], covariance)
        assert estimator.update(ref, 0.0, 'new', 1).accepted
        first = estimator.project(0.0, 'new', 1)
        np.testing.assert_array_equal(first.covariance[:3, :3], covariance)
        covariance[:] = 100
        first.position_world_m[:] = 100
        first.covariance[:] = 100
        again = estimator.project(0.0, 'new', 1)
        np.testing.assert_array_equal(again.position_world_m, [1, 2, 3])
        np.testing.assert_array_equal(np.diag(again.covariance)[:3], [0.25, 0.36, 0.49])
        diagnostics = estimator.last_update_diagnostics
        diagnostics['raw_measurement_m'][0] = 100
        assert estimator.last_update_diagnostics['raw_measurement_m'][0] == 1

    def test_invalid_projection_inputs_fail_closed(self):
        for now, age, status, reason in [(9.9, 0.75, 'tracking', 'future_navigation_measurement'), (float('nan'), 0.75, 'tracking', 'invalid_projection_timestamp'), (10.1, 0, 'tracking', 'invalid_navigation_max_age'), (10.1, float('inf'), 'tracking', 'invalid_navigation_max_age'), (10.1, 0.75, 'uninitialized', 'surface_uninitialized')]:
            with self.subTest(now=now, age=age, status=status):
                estimator = initialized()
                snapshot = estimator.project(now, 'task-a', 1, max_age=age, surface_status=status)
                assert not snapshot.valid and snapshot.reason == reason
                assert snapshot.position_world_m is None
                assert estimator.measured_timestamp_s == 10.0

    def test_invalid_identity_and_explicit_reset_remove_all_old_navigation_data(self):
        estimator = initialized()
        assert not estimator.project(10.1, '', 1).valid
        assert estimator.measured_timestamp_s is None
        assert not estimator.project(10.1, 'task-a', 1).valid
        assert estimator.update(reference(), 10.2, 'task-a', 1).accepted
        estimator.reset()
        assert estimator.last_update_diagnostics == {}
        assert not estimator.project(10.2, 'task-a', 1).valid

    def test_manager_confirmed_short_reacquisition_keeps_fresh_navigation_valid(self):
        estimator = initialized()
        assert estimator.project(10.2, 'task-a', 1, surface_status=TargetStatus.COASTING).valid
        assert estimator.update(reference([.3, 0, 0]), 10.3, 'task-a', 1).accepted
        recovered = estimator.project(10.3, 'task-a', 1, surface_status=TargetStatus.REACQUIRED)
        assert recovered.valid
        assert recovered.measured_timestamp_s == 10.3
        assert not estimator.project(11.051, 'task-a', 1, surface_status=TargetStatus.REACQUIRED).valid

    def test_nonfinite_initial_velocity_uncertainty_is_rejected(self):
        for covariance in [float('nan'), float('inf'), 0, -1]:
            with self.subTest(covariance=covariance), self.assertRaises(ValueError):
                NavigationEstimator(initial_velocity_covariance=covariance)


if __name__ == '__main__':
    unittest.main()
