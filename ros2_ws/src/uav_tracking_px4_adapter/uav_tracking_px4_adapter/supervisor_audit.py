"""Bounded scalar observation of supervisor callbacks; never a flight guard.

Only caller-supplied observations are stored. Sampling this audit never invokes
the source-clock validator or updates accepted control freshness.
"""
from __future__ import annotations

from collections import Counter
import math
from numbers import Integral, Real


def finite(value):
    return float(value) if isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value)) else None


def integer(value):
    return int(value) if isinstance(value, Integral) and not isinstance(value, bool) else None


def elapsed(now, then):
    now, then = finite(now), finite(then)
    return now - then if now is not None and then is not None else None


class SupervisorTimingAudit:
    def __init__(self):
        self.raw_received = self.accepted = self.rejected = 0
        self.rejection_counts = Counter()
        self.last_raw = self.last_accepted = self.last_rejected = None
        self.last_tick = self.last_diagnostic = None
        self.tick_count = self.diagnostic_count = 0
        self.max_raw_gap = self.max_accepted_gap = self.max_tick_gap = self.max_diagnostic_gap = None
        self.last_diagnostic_ros_ns = self.last_ros_change_wall_s = None
        self.diagnostic_ros_regressions = 0

    @staticmethod
    def _entry(wall_s, ros_ns, source_ns):
        return {"wall_monotonic_s": finite(wall_s), "receipt_ros_ns": integer(ros_ns),
                "source_stamp_ns": integer(source_ns)}

    @staticmethod
    def _max_gap(previous, current, maximum):
        gap = elapsed(current, previous)
        return max(maximum or 0.0, gap) if gap is not None and gap >= 0 else maximum

    def receive(self, wall_s, ros_ns, source_ns):
        previous = (self.last_raw or {}).get("wall_monotonic_s")
        self.max_raw_gap = self._max_gap(previous, wall_s, self.max_raw_gap)
        self.raw_received += 1
        self.last_raw = self._entry(wall_s, ros_ns, source_ns)

    def accept(self, wall_s, ros_ns, source_ns):
        previous = (self.last_accepted or {}).get("wall_monotonic_s")
        self.max_accepted_gap = self._max_gap(previous, wall_s, self.max_accepted_gap)
        self.accepted += 1
        self.last_accepted = self._entry(wall_s, ros_ns, source_ns)

    def reject(self, wall_s, ros_ns, source_ns, reason):
        self.rejected += 1
        self.rejection_counts[str(reason)] += 1
        self.last_rejected = {**self._entry(wall_s, ros_ns, source_ns), "reason": str(reason)}

    def tick(self, wall_s):
        self.max_tick_gap = self._max_gap(self.last_tick, wall_s, self.max_tick_gap)
        self.last_tick = finite(wall_s)
        self.tick_count += 1

    def snapshot(self, *, wall_s, ros_ns, unix_ns):
        """Observe a diagnostic timer callback; no control/time-acceptance state."""
        ros_ns = integer(ros_ns)
        wall_delta = elapsed(wall_s, self.last_diagnostic)
        ros_delta = ((ros_ns - self.last_diagnostic_ros_ns) / 1e9
                     if ros_ns is not None and self.last_diagnostic_ros_ns is not None else None)
        if ros_delta is not None and ros_delta < 0:
            self.diagnostic_ros_regressions += 1
        if ros_ns is not None and (self.last_diagnostic_ros_ns is None or ros_delta != 0):
            self.last_ros_change_wall_s = finite(wall_s)
        self.max_diagnostic_gap = self._max_gap(self.last_diagnostic, wall_s, self.max_diagnostic_gap)
        self.last_diagnostic, self.last_diagnostic_ros_ns = finite(wall_s), ros_ns
        self.diagnostic_count += 1

        def entry(value):
            if value is None:
                return None
            return {**value, "age_wall_s": elapsed(wall_s, value["wall_monotonic_s"]),
                    "age_source_s": (ros_ns - value["source_stamp_ns"]) / 1e9
                    if ros_ns is not None and value["source_stamp_ns"] is not None else None}

        return {
            "schema_version": 1, "scope": "CALLBACK_OBSERVATIONS_ONLY_NOT_TRANSPORT_OR_PUBLICATION_PROOF",
            "sample_monotonic_s": finite(wall_s), "sample_unix_ns": integer(unix_ns), "sample_ros_ns": ros_ns,
            "status_counts": {"raw_received": self.raw_received, "accepted": self.accepted,
                              "rejected": self.rejected,
                              "raw_without_recorded_outcome": self.raw_received - self.accepted - self.rejected},
            "status_rejections_by_reason": dict(self.rejection_counts),
            "last_raw_status": entry(self.last_raw), "last_accepted_status": entry(self.last_accepted),
            "last_rejected_status": entry(self.last_rejected),
            "control_tick": {"count": self.tick_count, "last_wall_monotonic_s": self.last_tick,
                             "age_wall_s": elapsed(wall_s, self.last_tick)},
            "completed_max_wall_gaps_s": {"raw_status_callbacks": self.max_raw_gap,
                                          "accepted_status_callbacks": self.max_accepted_gap,
                                          "control_ticks": self.max_tick_gap,
                                          "diagnostic_callbacks": self.max_diagnostic_gap},
            "diagnostic_clock": {"callback_count": self.diagnostic_count, "wall_delta_s": wall_delta,
                                 "ros_delta_s": ros_delta,
                                 "observed_ros_progress_per_wall": ros_delta / wall_delta
                                 if wall_delta is not None and wall_delta > 0 and ros_delta is not None else None,
                                 "wall_since_observed_ros_change_s": elapsed(wall_s, self.last_ros_change_wall_s),
                                 "observed_ros_regressions": self.diagnostic_ros_regressions},
            "timer_contract": {"clock": "STEADY_TIME", "period_wall_s": 1.0,
                               "executor": "SAME_SINGLE_THREADED_EXECUTOR_AS_CONTROL",
                               "limitation": "Continues when ROS time pauses only if the executor is scheduled; executor stalls also delay this diagnostic. It is not an independent DDS observer."},
        }
