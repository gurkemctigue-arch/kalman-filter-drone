"""Opt-in online estimator ablations with a shared safety/association gate.

The unchanged adaptive KF is the default. Other output strategies share its
shadow adaptive KF solely for acceptance and association, so changing the
control estimate cannot change which sensor observation passes the gate.
No baseline may extend measurement freshness, reset identity, or bypass the
common gate. The output covariance of raw/EMA is a declared heuristic, not a
claim of calibrated posterior uncertainty.
"""
from __future__ import annotations
from typing import Any,Sequence
import numpy as np
from .kalman import ConstantVelocityKalman3D,FilterEstimate

ESTIMATOR_METHODS=("raw","ema","fixed_kf","adaptive_kf")


class OutputStrategyEstimator3D:
    def __init__(self,method:str,*,ema_alpha:float=.35,**kwargs):
        if method not in ESTIMATOR_METHODS[:-1]:
            raise ValueError("OutputStrategyEstimator3D expects raw, ema or fixed_kf")
        if not 0<ema_alpha<=1:
            raise ValueError("EMA alpha must be in (0,1]")
        self.method,self.ema_alpha=method,float(ema_alpha)
        common=dict(kwargs,adaptive_measurement_noise=True)
        self._gate=ConstantVelocityKalman3D(**common)
        self._fixed=ConstantVelocityKalman3D(**dict(kwargs,adaptive_measurement_noise=False)) if method=="fixed_kf" else None
        self._position=np.zeros(3);self._velocity=np.zeros(3);self._output_stamp=None
        self._position_variance=np.square(self._gate.measurement_noise_std)
        self._velocity_variance=np.repeat(self._gate.initial_velocity_covariance,3)

    @property
    def initialized(self):return self._gate.initialized
    @property
    def timestamp(self):return self._gate.timestamp
    @property
    def association_position(self):return self._gate.position
    @property
    def position(self):return self._fixed.position if self._fixed else self._position.copy()
    @property
    def velocity(self):return self._fixed.velocity if self._fixed else self._velocity.copy()
    @property
    def covariance(self):
        if self._fixed:return self._fixed.covariance.copy()
        return self._heuristic_covariance(self.timestamp)
    @property
    def last_mahalanobis_distance(self):return self._gate.last_mahalanobis_distance
    @property
    def last_measurement_covariance(self):return self._gate.last_measurement_covariance.copy()
    @property
    def last_update_accepted(self):return self._gate.last_update_accepted
    @property
    def estimate(self):return FilterEstimate(self.position,self.velocity,self.covariance,self.timestamp,self.initialized)
    @property
    def x(self):return np.r_[self.position,self.velocity]
    @property
    def P(self):return self.covariance
    @property
    def R(self):return self.last_measurement_covariance

    def _heuristic_covariance(self,timestamp):
        age=0 if timestamp is None or self._output_stamp is None else max(0,float(timestamp)-self._output_stamp)
        drift=np.square(self._gate.process_acceleration_std*age*age/2)
        return np.diag(np.r_[self._position_variance+drift,self._velocity_variance+np.square(self._gate.process_acceleration_std*age)])

    def initialize(self,position,*,velocity=None,timestamp=None,covariance=None):
        self._gate.initialize(position,velocity=velocity,timestamp=timestamp,covariance=covariance)
        if self._fixed:self._fixed.initialize(position,velocity=velocity,timestamp=timestamp,covariance=covariance)
        self._position=np.asarray(position,dtype=float).copy()
        self._velocity=np.zeros(3) if velocity is None else np.asarray(velocity,dtype=float).copy()
        self._output_stamp=timestamp
        return self.estimate

    def reset(self):
        self._gate.reset()
        if self._fixed:self._fixed.reset()
        self._position[:]=0;self._velocity[:]=0;self._output_stamp=None
        self._position_variance=np.square(self._gate.measurement_noise_std)
        self._velocity_variance=np.repeat(self._gate.initial_velocity_covariance,3)

    def predict(self,dt=None,timestamp=None):
        self._gate.predict(dt=dt,timestamp=timestamp)
        if self._fixed:self._fixed.predict(dt=dt,timestamp=timestamp)
        # Raw and EMA use explicitly pre-registered zero-order position hold.
        # Their finite-difference velocity estimate is held for feedforward.
        return self.estimate

    def project(self,timestamp):
        gate=self._gate.project(timestamp)  # Validate timeline without mutation.
        if self._fixed:return self._fixed.project(timestamp)
        return FilterEstimate(self.position,self.velocity,self._heuristic_covariance(timestamp),gate.timestamp,self.initialized)

    def measurement_covariance(self,**kwargs):return self._gate.measurement_covariance(**kwargs)
    def mahalanobis_distance(self,measurement,**kwargs):return self._gate.mahalanobis_distance(measurement,**kwargs)

    def update(self,measurement,timestamp=None,**kwargs):
        if not self.initialized:
            accepted=self._gate.update(measurement,timestamp=timestamp,**kwargs)
            if self._fixed:self._fixed.initialize(measurement,timestamp=timestamp)
            self._position=np.asarray(measurement,dtype=float).copy();self._velocity=np.zeros(3)
            self._output_stamp=self.timestamp
            self._position_variance=np.diag(self._gate.last_measurement_covariance).copy()
            return accepted
        # The gate predicts to acquisition time and either accepts or rejects.
        # Fixed output propagation occurs even after a rejected sensor sample.
        accepted=self._gate.update(measurement,timestamp=timestamp,**kwargs)
        if self._fixed and timestamp is not None:self._fixed.predict(timestamp=timestamp)
        if not accepted:return False
        if self._fixed:
            output_kwargs={k:v for k,v in kwargs.items() if k!="gate_threshold"}
            # A second method-specific gate would break the paired protocol.
            # This update is reachable only after the unchanged common gate.
            self._fixed.update(measurement,timestamp=timestamp,gate_threshold=1e300,**output_kwargs)
            return True
        point=np.asarray(measurement,dtype=float)
        previous=self._position.copy()
        value=point if self.method=="raw" else self.ema_alpha*point+(1-self.ema_alpha)*previous
        effective_stamp=self.timestamp
        elapsed=self._gate.default_dt if self._output_stamp is None or effective_stamp is None else effective_stamp-self._output_stamp
        if elapsed>1e-9:
            self._velocity=(value-previous)/elapsed
            variance=np.diag(self._gate.last_measurement_covariance)
            old_variance=self._position_variance.copy()
            self._position_variance=variance if self.method=="raw" else self.ema_alpha**2*variance+(1-self.ema_alpha)**2*old_variance
            self._velocity_variance=np.maximum(1e-12,(self._position_variance+old_variance)/(elapsed*elapsed))
        self._position=value;self._output_stamp=effective_stamp
        return True


def make_state_estimator(method:str="adaptive_kf",*,ema_alpha:float=.35,**kwargs):
    if method not in ESTIMATOR_METHODS:
        raise ValueError(f"estimator_method must be one of {ESTIMATOR_METHODS}")
    if method=="adaptive_kf":
        # Preserve the actual established implementation and its timings.
        return ConstantVelocityKalman3D(**dict(kwargs,adaptive_measurement_noise=True))
    return OutputStrategyEstimator3D(method,ema_alpha=ema_alpha,**kwargs)
