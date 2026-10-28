"""Causal paired estimator replay of recorded RGB-D measurements.

This module neither reruns a flight nor replaces the recorded task state
machine. Each input row has acquisition ``time_s`` and arrival ``arrival_s``;
the output is evaluated at arrival, so delay is not hidden by backdating.
GT is used only to score estimates. A frozen surface anchor is fitted on a
disjoint calibration segment and explicitly remains a calibrated reference.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib
import json
from typing import Sequence
import numpy as np
from .core import ConstantVelocityKalman3D
from .research_metrics import numeric_summary, paired_bootstrap, wilson_interval

METHODS = ("raw", "ema", "fixed_kf", "adaptive_kf")


@dataclass(frozen=True)
class Perturbation:
    name: str
    noise_std_m: float = 0.0
    dropout_probability: float = 0.0
    hole_probability: float = 0.0
    extra_delay_s: float = 0.0
    delay_jitter_s: float = 0.0


CONDITIONS = (Perturbation("recorded"), Perturbation("depth_noise", noise_std_m=.08),
              Perturbation("depth_holes", hole_probability=.20),
              Perturbation("frame_dropout", dropout_probability=.20),
              Perturbation("communication_delay", extra_delay_s=.15, delay_jitter_s=.05),
              Perturbation("combined", .08, .10, .10, .10, .03))


def perturb(rows: Sequence[dict], condition: Perturbation, seed: int) -> list[dict]:
    """Generate the sequence once per pair; never once per estimator."""
    rng = np.random.default_rng(seed)
    result = []
    for original in rows:
        row = dict(original)
        point = original.get("point_world_m")
        noise = rng.normal(0, condition.noise_std_m, 3)
        dropout = rng.random() < condition.dropout_probability
        hole = rng.random() < condition.hole_probability
        delay = max(0,condition.extra_delay_s+rng.normal(0,condition.delay_jitter_s))
        row["arrival_s"] = float(original["arrival_s"])+delay
        if point is not None:
            row["point_world_m"] = None if dropout or hole else (np.asarray(point)+noise).tolist()
        if hole:
            row["valid_fraction"] = 0.0
        row["depth_std_m"] = float(np.hypot(original.get("depth_std_m",0),condition.noise_std_m))
        row["injected_dropout"], row["injected_hole"] = bool(dropout), bool(hole)
        row["injected_delay_s"] = delay
        result.append(row)
    return sorted(result,key=lambda row:(row["arrival_s"],row["time_s"]))


def fit_surface_anchor(rows: Sequence[dict], calibration_end_s: float) -> dict:
    samples = [row for row in rows if row["time_s"] <= calibration_end_s and row.get("calibration_eligible",True) and row.get("point_world_m") is not None
               and row.get("truth_position_m") is not None and row.get("truth_rotation") is not None]
    if len(samples) < 10:
        raise ValueError("At least 10 disjoint calibration observations are required")
    offsets = np.asarray([np.asarray(r["truth_rotation"]).T@(np.asarray(r["point_world_m"])-r["truth_position_m"]) for r in samples])
    anchor = np.median(offsets,axis=0)
    residual = np.linalg.norm(offsets-anchor,axis=1)
    return {"model_local_anchor_m":anchor.tolist(),"calibration_end_s":float(calibration_end_s),
            "calibration_observations":len(samples),"calibration_residual_rmse_m":float(np.sqrt(np.mean(residual**2))),
            "calibration_residual_p95_m":float(np.percentile(residual,95)),
            "reference_type":"calibrated_visible_surface_anchor_not_model_center",
            "limitation":"A fixed anchor approximates a view-dependent visible surface. Viewpoint changes can invalidate it; holdout residuals are always reported. This is not independent target-center accuracy."}


def _reference_at(row: dict, timestamp: float, anchor: np.ndarray, cache: dict | None=None) -> tuple[np.ndarray | None,np.ndarray | None]:
    # Extractor provides GT at acquisition and a finite-difference velocity.
    # For extra injected delays use full independent GT trajectory if present.
    positions = row.get("reference_samples")
    if positions:
        key=id(positions)
        cached=cache.get(key) if cache is not None else None
        if cached is None:
            times=np.asarray([p[0] for p in positions])
            values=np.asarray([p[1] for p in positions])
            if cache is not None:
                cache[key]=(times,values)
        else:
            times,values=cached
        if timestamp < times[0] or timestamp > times[-1]:
            return None,None
        position = np.asarray([np.interp(timestamp,times,values[:,axis]) for axis in range(3)])
        index = min(max(1,int(np.searchsorted(times,timestamp))),len(times)-1)
        velocity = (values[index]-values[index-1])/(times[index]-times[index-1])
        return position,velocity
    # Explicitly refuse to extrapolate GT to make delayed estimates look good.
    if abs(timestamp-float(row.get("truth_arrival_s",row["arrival_s"]))) > 1e-6:
        return None,None
    if row.get("truth_arrival_position_m") is None:
        return None,None
    rotation = np.asarray(row["truth_arrival_rotation"])
    return np.asarray(row["truth_arrival_position_m"])+rotation@anchor,np.asarray(row["truth_velocity_mps"])


def replay(rows: Sequence[dict], method: str, *, anchor_m: Sequence[float], evaluation_start_s: float,
           max_age_s: float=.75, noise_std_m: Sequence[float]=(.05,.05,.10)) -> tuple[dict,list[dict]]:
    if method not in METHODS:
        raise ValueError("Unknown estimator")
    anchor = np.asarray(anchor_m)
    kalman = ConstantVelocityKalman3D(process_acceleration_std=1.0, measurement_noise_std=noise_std_m,
                                     adaptive_measurement_noise=method=="adaptive_kf")
    last_stamp, last_value, last_velocity = None,None,np.zeros(3)
    watermark = None
    rejected, stale_arrivals, outputs = 0,0,[]
    reference_cache={}
    for row in sorted(rows,key=lambda r:(r["arrival_s"],r["time_s"])):
        timestamp, arrival = float(row["time_s"]),float(row["arrival_s"])
        measurement = row.get("point_world_m")
        valid = measurement is not None and float(row.get("valid_fraction",1)) >= .35
        if valid and (watermark is None or timestamp > watermark):
            watermark = timestamp
            measurement = np.asarray(measurement,dtype=float)
            if method in ("raw","ema"):
                value = measurement if method=="raw" or last_value is None else .35*measurement+.65*last_value
                velocity = np.zeros(3) if last_stamp is None else (value-last_value)/(timestamp-last_stamp)
                last_value,last_velocity,last_stamp = value,velocity,timestamp
            else:
                accepted = kalman.update(measurement,timestamp=timestamp,
                    confidence=row.get("confidence",1),depth_stats={"valid_fraction":row.get("valid_fraction",1),"std":row.get("depth_std_m",0)})
                rejected += int(not accepted)
                if accepted:
                    last_stamp = timestamp
        elif valid:
            stale_arrivals += 1
        if timestamp < evaluation_start_s:
            continue
        fresh = last_stamp is not None and 0 <= arrival-last_stamp <= max_age_s
        position,velocity = None,None
        if fresh:
            if method in ("raw","ema"):
                position,velocity = last_value,last_velocity
            elif kalman.initialized and arrival >= kalman.timestamp:
                estimate = kalman.project(arrival)
                position,velocity = estimate.position,estimate.velocity
        reference,reference_velocity = _reference_at(row,arrival,anchor,reference_cache)
        outputs.append({"time_s":timestamp,"arrival_s":arrival,"available":position is not None,
                        "reference_available":reference is not None,
                        "position_error_m":float(np.linalg.norm(position-reference)) if position is not None and reference is not None else None,
                        "velocity_error_mps":float(np.linalg.norm(velocity-reference_velocity)) if velocity is not None and reference_velocity is not None else None,
                        "prediction_age_s":arrival-last_stamp if last_stamp is not None else None,
                        "position_m":position.tolist() if position is not None else None})
    position_errors = [o["position_error_m"] for o in outputs if o["position_error_m"] is not None]
    velocity_errors = [o["velocity_error_mps"] for o in outputs if o["velocity_error_mps"] is not None]
    available = sum(o["available"] for o in outputs)
    metrics = {"estimator":method,"frames":len(outputs),"available_frames":available,
               "unavailable_frames":len(outputs)-available,"coverage":available/len(outputs) if outputs else 0,
               "matched_reference_frames":len(position_errors),"missing_reference_frames":sum(not o["reference_available"] for o in outputs),
               "position_rmse_m":float(np.sqrt(np.mean(np.square(position_errors)))) if position_errors else None,
               "position_p95_m":float(np.percentile(position_errors,95)) if position_errors else None,
               "velocity_rmse_mps":float(np.sqrt(np.mean(np.square(velocity_errors)))) if velocity_errors else None,
               "rejected_measurements":rejected,"out_of_order_arrivals":stale_arrivals,
               "result":"PASS" if outputs and len(position_errors)>0 and available/len(outputs)>=.9 else "FAIL_OR_INCOMPLETE",
               "failure_definition":"Replay availability >=90% of all holdout frame opportunities, and at least one matched independent pose-derived reference; this is an offline estimator coverage criterion, not flight acceptance"}
    return metrics,outputs


def benchmark_recording(rows: Sequence[dict], anchor: dict, *, seeds=range(10), conditions=CONDITIONS) -> dict:
    records = []
    reference = np.asarray(anchor["model_local_anchor_m"])
    # Full pose-derived anchor trajectory, shared by all perturbations.
    truth = [(r["time_s"],(np.asarray(r["truth_position_m"])+np.asarray(r["truth_rotation"])@reference).tolist())
             for r in rows if r.get("truth_position_m") is not None]
    # Independent GT samples ideally supplied at 30 Hz by the extractor;
    # fallback sampling at recorded detector times is explicitly metadata.
    if rows and rows[0].get("truth_trajectory"):
        truth = [(p["time_s"],(np.asarray(p["position_m"])+np.asarray(p["rotation"])@reference).tolist())
                 for p in rows[0]["truth_trajectory"]]
    prepared = [dict(row,reference_samples=truth) for row in rows]
    for condition in conditions:
        actual_seeds = [0] if condition.name=="recorded" else list(seeds)
        for seed in actual_seeds:
            sequence = perturb(prepared,condition,seed)
            digest_rows = [{k:v for k,v in row.items() if k not in ("reference_samples","truth_trajectory")} for row in sequence]
            digest = hashlib.sha256(json.dumps(digest_rows,sort_keys=True,allow_nan=False).encode()).hexdigest()
            pair=[]
            for method in METHODS:
                metric,outputs = replay(sequence,method,anchor_m=reference,evaluation_start_s=anchor["calibration_end_s"]+1e-6)
                pair.append((metric,outputs))
            common=[i for i in range(len(pair[0][1])) if all(outputs[i]["position_error_m"] is not None for _metric,outputs in pair)]
            for metric,outputs in pair:
                common_errors=[outputs[i]["position_error_m"] for i in common]
                records.append({**metric,"condition":condition.name,"seed":seed,"input_sha256":digest,
                                "common_support_frames":len(common),
                                "common_support_position_rmse_m":float(np.sqrt(np.mean(np.square(common_errors)))) if common_errors else None,
                                "perturbation":asdict(condition)})
    groups = {}
    for condition in conditions:
        subset = [r for r in records if r["condition"]==condition.name]
        methods = {}
        for method in METHODS:
            trials = [r for r in subset if r["estimator"]==method]
            methods[method] = {"repetitions":len(trials),
                "position_rmse_m":numeric_summary(r["position_rmse_m"] for r in trials),
                "common_support_position_rmse_m":numeric_summary(r["common_support_position_rmse_m"] for r in trials),
                "velocity_rmse_mps":numeric_summary(r["velocity_rmse_mps"] for r in trials),
                "coverage":numeric_summary(r["coverage"] for r in trials),
                "failure_rate":wilson_interval(sum(r["result"]!="PASS" for r in trials),len(trials))}
        paired = {}
        adaptive = [r for r in subset if r["estimator"]=="adaptive_kf"]
        for method in METHODS[:-1]:
            base = [r for r in subset if r["estimator"]==method]
            paired[method] = paired_bootstrap([r["common_support_position_rmse_m"] for r in adaptive],[r["common_support_position_rmse_m"] for r in base])
        groups[condition.name] = {"methods":methods,"adaptive_minus_baseline_position_rmse_m":paired}
    return {"schema_version":1,"anchor":anchor,"groups":groups,"trials":records,
            "scope":"Paired offline replay of one real recorded visual flight. Seed repetitions randomize injected faults on the same source and are conditional on that source, not independent flight repetitions. Recorded condition runs once to avoid 10 identical pseudo-replicates.",
            "causality":"Acquisition-time updates; arrival-time evaluation; out-of-order acquisition drops; no GT extrapolation beyond recorded truth; max .75s prediction availability; no future measurement access",
            "comparison_support":"Paired RMSE differences use exactly the frame intersection available for all four estimators in a seed. Per-method availability and own-support errors are separately reported; failed/incomplete seeds remain counted."}
