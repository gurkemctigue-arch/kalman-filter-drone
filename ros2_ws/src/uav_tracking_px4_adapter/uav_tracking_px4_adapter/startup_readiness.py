"""Pure readiness checks for the explicit native-takeoff startup contract.

PX4 owns takeoff and its normal in-flight magnetic alignment. These checks
only authorize a later Offboard handoff; they never waive an active frame or
clock reset. Status, native-mode acknowledgement and physical settle checks
belong to the supervisor. All timestamps here use the source_sim clock.
"""
from __future__ import annotations

import math
from numbers import Integral, Real
from typing import Any


MAX_SOURCE_AGE_S = .50
MAX_FLAGS_SOURCE_AGE_S = 1.50  # EKF2 publishes nominally at 1 Hz, or on a flag change.
MAX_FUTURE_S = .05
TIME_EPSILON_S = 1e-9


def readiness_issues(local_position: Any, estimator_flags: Any, now_s: float, *,
                     require_inflight_alignment: bool = False) -> list[str]:
    """Return all observed reasons to keep waiting; an empty list is ready.

    Ground yaw alignment is distinct from final in-flight alignment. In PX4
    this pin's ``heading_good_for_control`` only becomes true after magnetic
    alignment in flight; requiring it on the ground would prevent takeoff.
    Missing fields are invalid evidence, never implicitly healthy defaults.
    """
    issues: list[str] = []
    if local_position is None:
        issues.append("local_position_missing")
    if estimator_flags is None:
        issues.append("estimator_flags_missing")
    if (isinstance(now_s, bool) or not isinstance(now_s, Real)
            or not math.isfinite(float(now_s)) or now_s <= 0):
        return issues + ["source_sim_clock_not_started_or_invalid"]

    def source_time(message: Any, name: str, maximum_age_s: float) -> None:
        sample = getattr(message, "timestamp_sample", None)
        publication = getattr(message, "timestamp", None)
        valid_sample = isinstance(sample, Integral) and not isinstance(sample, bool) and 0 < sample < 2**64
        valid_publication = isinstance(publication, Integral) and not isinstance(publication, bool) and 0 < publication < 2**64
        if not valid_sample:
            issues.append(name + "_source_timestamp_invalid")
        if not valid_publication:
            issues.append(name + "_publication_timestamp_invalid")
        for label, value, valid in (("source", sample, valid_sample),
                                    ("publication", publication, valid_publication)):
            if valid:
                age = float(now_s) - int(value) * 1e-6
                if age < -MAX_FUTURE_S - TIME_EPSILON_S:
                    issues.append(name + "_" + label + "_future")
                elif age > maximum_age_s + TIME_EPSILON_S:
                    issues.append(name + "_" + label + "_stale")
        if valid_sample and valid_publication and sample > publication:
            issues.append(name + "_sample_after_publication")

    def flag(message: Any, field: str, expected: bool, name: str) -> None:
        value = getattr(message, field, None)
        if type(value) is not bool:
            issues.append(name + "_" + field + "_unknown")
        elif value != expected:
            issues.append(name + "_" + field + ("_not_ready" if expected else "_active"))

    if local_position is not None:
        source_time(local_position, "local_position", MAX_SOURCE_AGE_S)
        for field in ("xy_valid", "z_valid", "v_xy_valid", "v_z_valid", "xy_global", "z_global"):
            flag(local_position, field, True, "local_position")
        flag(local_position, "dead_reckoning", False, "local_position")
        for field in ("x", "y", "z", "vx", "vy", "vz", "heading"):
            value = getattr(local_position, field, None)
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
                issues.append("local_position_" + field + "_invalid")
        if require_inflight_alignment:
            flag(local_position, "heading_good_for_control", True, "local_position")
    if estimator_flags is not None:
        source_time(estimator_flags, "estimator_flags", MAX_FLAGS_SOURCE_AGE_S)
        for field in ("cs_tilt_align", "cs_yaw_align", "cs_gnss_pos", "cs_gnss_vel"):
            flag(estimator_flags, field, True, "estimator_flags")
        for field in ("cs_inertial_dead_reckoning", "cs_wind_dead_reckoning", "cs_gnss_fault",
                      "cs_mag_fault", "cs_mag_field_disturbed"):
            flag(estimator_flags, field, False, "estimator_flags")
        if require_inflight_alignment:
            for field in ("cs_in_air", "cs_mag_aligned_in_flight"):
                flag(estimator_flags, field, True, "estimator_flags")
    return issues
