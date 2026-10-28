"""Offline transient metrics; absent evidence cannot certify settling."""
from __future__ import annotations

import math


def transient_metrics(rows, start_s, end_s, *, band_m, sustain_s=3., maximum_gap_s=.15):
    """Error around a constant distance/height reference during a moving task.

    Rows have time_s, error_m (None for missing truth), active. Settling
    requires a continuous, active, in-band suffix through the recorded end.
    This is not a classical percentage step overshoot of a stationary plant.
    """
    if not all(math.isfinite(x) for x in (start_s, end_s, band_m, sustain_s, maximum_gap_s)):
        raise ValueError("Finite metric parameters required")
    if end_s <= start_s or min(band_m, sustain_s, maximum_gap_s) <= 0:
        raise ValueError("Positive interval, band, duration and gap required")
    samples = sorted((r for r in rows if start_s <= r["time_s"] <= end_s), key=lambda r:r["time_s"])
    valid = [r for r in samples if r.get("error_m") is not None and math.isfinite(r["error_m"])]
    # Initial direction must come from the first scheduled sample, never a
    # later convenient sample after missing initial truth.
    initial = samples[0].get("error_m") if samples and samples[0]["time_s"]-start_s <= maximum_gap_s else None
    if initial is not None and not math.isfinite(initial):initial=None
    direction = math.copysign(1., initial) if initial is not None and abs(initial)>1e-9 else None
    overshoot = max([0.]+[-direction*r["error_m"] for r in valid]) if direction is not None else None
    suffix_start = None
    previous = start_s
    duplicates = False
    first_band = None
    current_start = None
    for index, row in enumerate(samples):
        t = row["time_s"]
        if index and t <= previous:duplicates=True
        continuous = t-previous <= maximum_gap_s and (index == 0 or t>previous)
        error = row.get("error_m")
        inside = error is not None and math.isfinite(error) and abs(error)<=band_m and row.get("active") is True
        if not inside:
            current_start=None
        elif current_start is None or not continuous:
            current_start=t
        if current_start is not None and t-current_start>=sustain_s-1e-8 and first_band is None:
            first_band=current_start-start_s
        previous=t
    suffix_start=current_start
    has_tail=bool(samples and end_s-samples[-1]["time_s"] <= maximum_gap_s)
    settled=bool(has_tail and suffix_start is not None and end_s-suffix_start >= sustain_s-1e-8 and not duplicates)
    return {"scheduled_samples":len(samples),"valid_truth_samples":len(valid),
            "truth_coverage":len(valid)/len(samples) if samples else None,
            "initial_error_m":initial,"initial_direction":direction,
            "opposite_side_overshoot_m":overshoot,
            "band_m":band_m,"minimum_in_band_duration_s":sustain_s,
            "first_sustained_in_band_time_s":first_band,
            "settled_through_interval_end":settled,
            "settling_time_s":suffix_start-start_s if settled else None,
            "settling_right_censored":not settled,"observed_interval_s":end_s-start_s,
            "duplicate_source_times":duplicates,
            "definition":"Absolute opposite-side crossing relative to initial error sign; no percent step normalization. Settling is the start of the final active, in-band, continuously evidenced suffix lasting >=3 s through the interval end. Missing truth, inactive control and gaps interrupt the suffix; null settling is right-censored, never zero."}
