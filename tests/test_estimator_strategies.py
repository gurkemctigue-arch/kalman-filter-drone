from __future__ import annotations
import unittest
import numpy as np
from uav_tracking.core.estimator_strategies import make_state_estimator,ESTIMATOR_METHODS
from uav_tracking.core.kalman import ConstantVelocityKalman3D
from uav_tracking.core import TargetManager,Detection


class OnlineEstimatorStrategyTests(unittest.TestCase):
    def test_default_is_original_kf_with_identical_values(self):
        configured=make_state_estimator("adaptive_kf",measurement_noise_std=[.1,.1,.2])
        original=ConstantVelocityKalman3D(measurement_noise_std=[.1,.1,.2])
        self.assertIs(type(configured),ConstantVelocityKalman3D)
        for i in range(20):
            for estimator in (configured,original):
                estimator.update([i*.03,0,1],timestamp=i*.1,confidence=.7,depth_stats={"valid_fraction":.8,"std":.05})
            np.testing.assert_array_equal(configured.state,original.state)
            np.testing.assert_array_equal(configured.covariance,original.covariance)

    def test_all_methods_share_gate_decisions_and_association_state(self):
        filters=[make_state_estimator(kind,measurement_noise_std=.15) for kind in ESTIMATOR_METHODS]
        rng=np.random.default_rng(8)
        for i in range(50):
            point=np.asarray([i*.02,0,1])+rng.normal(0,.03,3)
            if i in (15,30):point+=100
            decisions=[filter_.update(point,timestamp=i*.1,confidence=.7,depth_stats={"valid_fraction":.6,"std":.1}) for filter_ in filters]
            self.assertEqual(len(set(decisions)),1)
            gate_positions=[getattr(filter_,"association_position",filter_.position) for filter_ in filters]
            for position in gate_positions[1:]:np.testing.assert_array_equal(position,gate_positions[0])
        self.assertFalse(decisions[0] is None)

    def test_raw_and_ema_are_zero_order_position_hold_with_real_dt_velocity(self):
        raw=make_state_estimator("raw",measurement_noise_std=1)
        ema=make_state_estimator("ema",measurement_noise_std=1,ema_alpha=.35)
        for filter_ in (raw,ema):
            filter_.initialize([0,0,1],timestamp=0)
            self.assertTrue(filter_.update([1,0,1],timestamp=.5))
        np.testing.assert_allclose(raw.position,[1,0,1])
        np.testing.assert_allclose(raw.velocity,[2,0,0])
        np.testing.assert_allclose(ema.position,[.35,0,1])
        np.testing.assert_allclose(ema.velocity,[.7,0,0])
        for filter_ in (raw,ema):
            before=filter_.position.copy();stamp=filter_.timestamp
            projected=filter_.project(.7)
            np.testing.assert_array_equal(projected.position,before)
            self.assertEqual(filter_.timestamp,stamp)
            self.assertTrue(np.all(np.linalg.eigvalsh(projected.covariance)>=0))

    def test_same_selector_uuid_and_measurement_age_across_methods(self):
        managers=[TargetManager(target_class="person",min_hits=1,max_coast_duration_s=.75,
                                estimator_method=kind,kf_kwargs={"measurement_noise_std":.2}) for kind in ESTIMATOR_METHODS]
        for index in range(10):
            detection=Detection(bbox=(0,0,50,100),class_id="person",confidence=.9,
                                position_3d=(index*.02,0,1),timestamp=index*.1)
            for manager in managers:manager.update_with_result([detection],timestamp=index*.1)
            self.assertEqual({manager.target_track_id for manager in managers},{1})
            self.assertEqual(len({manager.target.last_measurement_timestamp for manager in managers}),1)
        for manager in managers:
            uuid=manager.target_uuid
            result=manager.predict_with_result(1.7)
            self.assertEqual(result.status.value,"lost")
            self.assertEqual(manager.target_uuid,uuid)
            late=manager.update_with_result([Detection(bbox=(0,0,50,100),class_id="person",confidence=.9,
                                             position_3d=(.2,0,1),timestamp=1.8)],timestamp=1.8)
            self.assertEqual(late.status.value,"lost")

    def test_fixed_output_covariance_differs_from_adaptive_with_same_gate(self):
        fixed=make_state_estimator("fixed_kf",measurement_noise_std=.1)
        adaptive=make_state_estimator("adaptive_kf",measurement_noise_std=.1)
        for i in range(20):
            for filter_ in (fixed,adaptive):filter_.update([i*.01,0,1],timestamp=i*.1,confidence=.2,
                                                         depth_stats={"valid_fraction":.2,"std":.5})
        self.assertLess(fixed.covariance[0,0],adaptive.covariance[0,0])
        np.testing.assert_array_equal(fixed.association_position,adaptive.position)

    def test_method_and_alpha_validation(self):
        with self.assertRaises(ValueError):make_state_estimator("typo")
        with self.assertRaises(ValueError):make_state_estimator("ema",ema_alpha=0)


if __name__=="__main__":unittest.main()
