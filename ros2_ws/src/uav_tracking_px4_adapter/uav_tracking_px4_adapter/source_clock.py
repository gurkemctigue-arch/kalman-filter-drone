"""Validate an explicitly declared PX4/ROS source clock, without fitting it.

Simulation uses Gazebo's clock and UXRCE_DDS_SYNCT=0. Real vehicles use a
verified Agent/system clock. Receipt stamping is an explicit legacy mode.
No clock offset is inferred from target data or message arrival times.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Integral


@dataclass(frozen=True)
class SourceStamp:
    accepted: bool
    reason: str
    header_ns: int | None
    source_sample_ns: int | None
    source_publication_ns: int | None
    receipt_ns: int

    def diagnostics(self, mode: str) -> dict:
        return {
            "schema_version": 1, "mode": mode, "accepted": self.accepted,
            "reason": self.reason, "output_s": self.receipt_ns / 1e9,
            "receipt_ros_s": self.receipt_ns / 1e9,
            "source_sample_s": self.source_sample_ns / 1e9 if self.source_sample_ns is not None else None,
            "source_publication_s": self.source_publication_ns / 1e9 if self.source_publication_ns is not None else None,
            "odometry_header_s": self.header_ns / 1e9 if self.header_ns is not None else None,
            "source_to_receipt_s": (self.receipt_ns - self.source_sample_ns) / 1e9
            if self.source_sample_ns is not None else None,
        }


class OdometrySourceClock:
    """Reject wrong domains, stale/future samples and source/ROS regressions.

    A clock regression latches invalid until the node is restarted. Silently
    rebasing a running TF tree after a reboot could mix unrelated histories.
    Duplicate samples do not refresh an odometry stream. Limits describe the
    clock/transport contract; controller freshness checks still apply.
    """
    MODES = ("receipt", "source_sim", "source_system")

    def __init__(self, mode: str = "receipt", *, use_sim_time: bool = False,
                 max_age_s: float = .50, max_future_s: float = .05) -> None:
        if mode not in self.MODES:
            raise ValueError("unsupported odometry timestamp mode")
        if mode == "source_sim" and not use_sim_time:
            raise ValueError("source_sim requires use_sim_time=true and UXRCE_DDS_SYNCT=0")
        if mode == "source_system" and use_sim_time:
            raise ValueError("source_system requires use_sim_time=false and a verified Agent/system clock")
        if not math.isfinite(max_age_s) or max_age_s <= 0 or not math.isfinite(max_future_s) or max_future_s < 0:
            raise ValueError("invalid source clock limits")
        self.mode = mode
        self.max_age_ns = round(max_age_s * 1e9)
        self.max_future_ns = round(max_future_s * 1e9)
        self._last_receipt_ns: int | None = None
        self._last_sample_ns: int | None = None
        self._last_publication_ns: int | None = None
        self._latched_reason: str | None = None

    @staticmethod
    def _source_ns(value) -> int | None:
        if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0 or value > (2**63 - 1) // 1000:
            return None
        return int(value) * 1000

    @property
    def latched(self) -> bool:
        return self._latched_reason is not None

    def resolve(self, sample_us, publication_us, receipt_ns: int) -> SourceStamp:
        if isinstance(receipt_ns, bool) or not isinstance(receipt_ns, Integral):
            raise ValueError("receipt must be integer ROS nanoseconds")
        receipt_ns = int(receipt_ns)
        sample = self._source_ns(sample_us)
        publication = self._source_ns(publication_us)

        def result(reason, accepted=False):
            stamp = receipt_ns if self.mode == "receipt" else sample
            return SourceStamp(accepted, reason, stamp if accepted else None, sample, publication, receipt_ns)

        if receipt_ns <= 0:
            return result("ros_clock_not_started")
        if self.mode == "receipt":
            return result("legacy_receipt_stamp", True)
        if self._latched_reason is not None:
            return result(self._latched_reason)
        if self._last_receipt_ns is not None and receipt_ns < self._last_receipt_ns:
            self._latched_reason = "ros_clock_regression_restart_required"
            return result(self._latched_reason)
        self._last_receipt_ns = receipt_ns
        if sample is None or publication is None:
            return result("invalid_source_timestamp")
        if sample > publication:
            return result("sample_after_publication")
        if self._last_sample_ns is not None:
            if sample < self._last_sample_ns or publication < self._last_publication_ns:
                self._latched_reason = "source_clock_regression_restart_required"
                return result(self._latched_reason)
            if sample == self._last_sample_ns:
                return result("duplicate_source_sample")
        age = receipt_ns - sample
        if age < -self.max_future_ns or publication - receipt_ns > self.max_future_ns:
            return result("future_or_wrong_domain_source_timestamp")
        if age > self.max_age_ns:
            return result("stale_or_wrong_domain_source_timestamp")
        self._last_sample_ns, self._last_publication_ns = sample, publication
        return result("validated_source_stamp", True)
