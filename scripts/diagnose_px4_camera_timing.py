"""Read-only, vehicle-only PX4/ROS clock and pose-phase diagnosis.

Lag/yaw fits are labelled offline sensitivities. They must never be applied as
truth-derived online corrections. Images and target poses are not retained.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ros2_ws/src/uav_tracking_px4_adapter"))
import evaluate_stage1_flight as bag_tools
from evaluate_stage1_flight import stamp_s, summary, vector
from evaluate_online_state_accuracy import PoseSeries, freeze_ego_alignment, rotation_error_rad
from extract_research_recording import pose_dict
from uav_tracking.research_labels import quaternion_matrix
from uav_tracking_px4_adapter.adapter_node import px4_odometry_to_enu


def wrapped(value):
    return (value + math.pi) % (2 * math.pi) - math.pi


def rpy(matrix):
    return np.array([math.atan2(matrix[2, 1], matrix[2, 2]),
                     math.asin(float(np.clip(-matrix[2, 0], -1, 1))),
                     math.atan2(matrix[1, 0], matrix[0, 0])])


def finite_array(values):
    return [float(value) if math.isfinite(float(value)) else None for value in values]


def extract(trial):
    previous = bag_tools.TOPICS
    try:
        bag_tools.TOPICS = ("/clock", "/vehicle/odometry", "/fmu/out/vehicle_odometry",
                            "/ground_truth/poses", "/ground_truth/vehicle_poses",
                            "/ground_truth/world_poses", "/ground_truth/uav_poses")
        records, metadata = bag_tools.read_rosbag(trial / "rosbag")
    finally:
        bag_tools.TOPICS = previous
    raw = []; odometry = []; truth = defaultdict(dict)
    for record in records:
        message = record.message
        if record.topic.startswith("/ground_truth/"):
            for transform in message.transforms:
                name = transform.child_frame_id.strip("/")
                if name == "stage1_uav" or name.endswith("::stage1_uav") or name.rsplit("/", 1)[-1] == "stage1_uav":
                    row = pose_dict(transform)
                    truth[name][row["time_s"]] = row
        elif record.topic == "/vehicle/odometry":
            q = message.pose.pose.orientation
            odometry.append({"time_s":stamp_s(message.header.stamp), "received_sim_s":record.received_sim_s,
                             "position_m":list(vector(message.pose.pose.position)), "quaternion_xyzw":[q.x, q.y, q.z, q.w]})
        elif record.topic == "/fmu/out/vehicle_odometry":
            p, v, q = px4_odometry_to_enu(message)
            raw.append({"time_s":record.received_sim_s if record.received_sim_s is not None else record.time_s,
                        "timestamp_s":int(message.timestamp) * 1e-6,
                        "timestamp_sample_s":int(message.timestamp_sample) * 1e-6,
                        "position_m":list(p), "velocity_mps":list(v), "quaternion_xyzw":list(q),
                        "orientation_variance_rad2":finite_array(message.orientation_variance),
                        "position_variance_m2":finite_array(message.position_variance),
                        "velocity_variance_m2ps2":finite_array(message.velocity_variance),
                        "reset_counter":int(message.reset_counter), "quality":int(message.quality),
                        "record_sequence":record.record_sequence})
    if len(truth) != 1:
        raise ValueError("Missing or ambiguous independent UAV truth: " + str(list(truth)))
    return {"schema_version":1, "trial":str(trial), "bag":metadata, "raw":raw, "odometry":odometry,
            "vehicle_truth":list(next(iter(truth.values())).values()),
            "target_data_used":False}


def fit_clock_map(raw, duration_s=5.):
    start = raw[0]["time_s"]
    train = [row for row in raw if row["time_s"] <= start + duration_s]
    origin = train[0]["timestamp_s"]
    x = np.array([row["timestamp_s"] - origin for row in train])
    y = np.array([row["time_s"] for row in train])
    slope, intercept = np.polyfit(x, y, 1)
    holdout = summary(row["time_s"] - (slope * (row["timestamp_s"] - origin) + intercept)
                      for row in raw if row["time_s"] > start + duration_s)
    return {"slope_sim_per_px4":float(slope), "px4_origin_s":origin, "sim_intercept_s":float(intercept),
            "calibration_start_s":start, "calibration_end_s":start + duration_s, "training_pairs":len(train),
            "method":"Fixed first-5-s least squares receipt-clock versus PX4 publish timestamp. No GT. Diagnostic only: receipt jitter and changing timesync can bias this map.",
            "holdout_receipt_minus_mapped_publish_s":holdout,
            "valid_for_source_timestamping":bool(holdout["max_absolute"] is not None and holdout["max_absolute"] <= .02),
            "validation_boundary":"Reject this clock map for online timestamps if held-out clock residual exceeds 20ms; affine sensitivity results then have no timing-correction interpretation."}


def mapped_time(row, basis, mapping):
    if basis == "receipt_clock":
        return row["time_s"]
    if basis.startswith("affine_"):
        key = "timestamp_sample_s" if basis.endswith("sample") else "timestamp_s"
        return mapping["slope_sim_per_px4"] * (row[key] - mapping["px4_origin_s"]) + mapping["sim_intercept_s"]
    return row["timestamp_sample_s" if basis == "source_sample_identity" else "timestamp_s"]


def score_pose(rows, vehicle, alignment, basis, mapping, lag_s, start_s, end_s, *, include_frames=False):
    translation = np.asarray(alignment["translation_world_from_map_m"])
    offset = np.array([0., 0., .24])
    errors = []; positions = []; yaw = []; roll = []; pitch = []; frames = []
    for row in rows:
        # Keep the exact same received rows in every lag sensitivity. A lag
        # changes queried vehicle GT time, not which target/flight samples fit.
        if not start_s <= row["time_s"] <= end_s:
            continue
        timestamp = mapped_time(row, basis, mapping)
        pose = vehicle.at(timestamp + lag_s)
        if pose is None:
            continue
        true_p, true_r = pose
        estimate_r = quaternion_matrix(row["quaternion_xyzw"])
        error = rotation_error_rad(estimate_r, true_r)
        position_error = np.asarray(row["position_m"]) + translation - (true_p + true_r @ offset)
        euler = np.array([wrapped(value) for value in rpy(estimate_r) - rpy(true_r)])
        errors.append(error); positions.append(float(np.linalg.norm(position_error)))
        roll.append(float(euler[0])); pitch.append(float(euler[1])); yaw.append(float(euler[2]))
        if include_frames:
            frames.append({"receipt_s":row["time_s"], "pose_label_s":timestamp, "queried_truth_s":timestamp + lag_s,
                           "attitude_error_rad":error, "rpy_error_rad":euler.tolist(),
                           "position_error_vector_m":position_error.tolist(),
                           "estimated_rpy_rad":rpy(estimate_r).tolist(), "true_rpy_rad":rpy(true_r).tolist(),
                           "timestamp_s":row.get("timestamp_s"), "timestamp_sample_s":row.get("timestamp_sample_s"),
                           "orientation_variance_rad2":row.get("orientation_variance_rad2"),
                           "position_variance_m2":row.get("position_variance_m2")})
    yaw_bias = float(np.median(yaw)) if yaw else None
    return {"lag_s":float(lag_s), "attitude_error_rad":summary(errors), "position_error_m":summary(positions),
            "roll_error_rad":summary(roll), "pitch_error_rad":summary(pitch), "yaw_error_rad":summary(yaw),
            "diagnostic_median_yaw_bias_rad":yaw_bias,
            "diagnostic_yaw_after_median_removal_rad":summary(wrapped(value - yaw_bias) for value in yaw) if yaw else summary([]),
            **({"frames":frames} if include_frames else {})}


def variance_summary(rows):
    result = {}
    for field in ("orientation_variance_rad2", "position_variance_m2", "velocity_variance_m2ps2"):
        result[field] = [summary(row[field][axis] for row in rows) for axis in range(3)]
    result["samples"] = len(rows)
    result["interpretation"] = "PX4 state-estimator declared variance; quaternion attitude small-angle axes remain body-referenced while scalar norms are invariant. These are not independent truth error bounds."
    return result


def evaluate(data):
    raw = sorted(data["raw"], key=lambda row:row["time_s"])
    odometry = sorted(data["odometry"], key=lambda row:row["time_s"])
    truth = PoseSeries(data["vehicle_truth"])
    alignment = freeze_ego_alignment(odometry, truth, np.array([0, 0, .24]), np.eye(3))
    mapping = fit_clock_map(raw)
    end = min(max(row["time_s"] for row in raw), truth.times[-1])
    clock = {"raw_messages":len(raw), "adapted_odometry_messages":len(odometry),
             "receipt_minus_timestamp_s":summary(row["time_s"] - row["timestamp_s"] for row in raw),
             "receipt_minus_timestamp_sample_s":summary(row["time_s"] - row["timestamp_sample_s"] for row in raw),
             "publish_minus_sample_s":summary(row["timestamp_s"] - row["timestamp_sample_s"] for row in raw),
             "raw_time_examples":raw[:3] + raw[-3:], "receipt_only_first5_clock_mapping":mapping}
    clock["publish_time_mapping_discontinuities"] = [
        {"previous_receipt_s":before["time_s"], "receipt_s":after["time_s"],
         "previous_timestamp_s":before["timestamp_s"], "timestamp_s":after["timestamp_s"],
         "timestamp_increment_minus_receipt_increment_s":(after["timestamp_s"] - before["timestamp_s"]) - (after["time_s"] - before["time_s"])}
        for before, after in zip(raw, raw[1:])
        if abs((after["timestamp_s"] - before["timestamp_s"]) - (after["time_s"] - before["time_s"])) > .05]
    windows = [("after_10s", 10., end), ("pre_failure_12_16", 12., 16.),
               ("dynamic_16_20", 16., 20.), ("failure_17_20", 17., 20.)]
    scans = {}
    bases = ("receipt_clock", "source_publish_identity", "source_sample_identity", "affine_publish", "affine_sample")
    for name, start, stop in windows:
        scans[name] = {"interval_s":[start, stop], "bases":{}}
        for basis in bases:
            sweep = [score_pose(raw, truth, alignment, basis, mapping, lag, start, stop)
                     for lag in np.linspace(-.5, .5, 101)]
            valid = [row for row in sweep if row["attitude_error_rad"]["count"] >= 10]
            best = min(valid, key=lambda row:row["attitude_error_rad"]["rmse"]) if valid else None
            # A second optimum removes a constant signed yaw bias only to
            # diagnose delay versus heading offset, not to improve reports.
            best_dynamic = min(valid, key=lambda row:row["diagnostic_yaw_after_median_removal_rad"]["rmse"]) if valid else None
            zero = next(row for row in sweep if abs(row["lag_s"]) < 1e-9)
            scans[name]["bases"][basis] = {"zero_lag":zero, "best_attitude_lag":best,
                                           "best_yaw_dynamics_lag_after_bias_removal":best_dynamic,
                                           "interpretation_valid":basis == "receipt_clock" or (basis.startswith("affine_") and mapping["valid_for_source_timestamping"]),
                                           "lag_sweep":sweep}
        scans[name]["raw_px4_variance"] = variance_summary([row for row in raw if start <= row["time_s"] <= stop])
    detail = score_pose(raw, truth, alignment, "receipt_clock", mapping, 0., 16., 20., include_frames=True)
    concise = {name:{basis:{"zero_attitude_rmse_rad":entry["zero_lag"]["attitude_error_rad"]["rmse"],
                            "zero_yaw_mean_rad":entry["zero_lag"]["yaw_error_rad"]["mean"],
                            "best_lag_s":entry["best_attitude_lag"]["lag_s"] if entry["best_attitude_lag"] else None,
                            "best_attitude_rmse_rad":entry["best_attitude_lag"]["attitude_error_rad"]["rmse"] if entry["best_attitude_lag"] else None,
                            "best_yaw_bias_rad":entry["best_attitude_lag"]["diagnostic_median_yaw_bias_rad"] if entry["best_attitude_lag"] else None}
                    for basis, entry in value["bases"].items()} for name, value in scans.items()}
    return {"schema_version":1, "trial":data["trial"], "clock":clock, "ego_alignment":alignment,
            "lag_sign":"Estimate labelled t is compared to independent UAV GT at t+lag. Negative optimum means pose lags its label.",
            "lag_sweep_s":[-.5, .5, .01], "window_summaries":concise, "windows":scans,
            "dynamic_frames":detail["frames"],
            "claim_boundary":"Vehicle truth only; target poses/images never retained or used. Lag/fixed yaw fits are retrospective sensitivities, never runtime corrections. ENU axes and .24m vehicle base_link offset are declared offline geometry. Clock mapping uses receipt/PX4 time only on a fixed first5s, not GT; it is diagnostic and does not establish portable synchronization."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input-json", type=Path)
    args = parser.parse_args()
    if args.input_json:
        data = json.loads(args.input_json.read_text())
    else:
        data = extract(args.trial)
        cache = args.output.with_suffix(".vehicle_only_input.json")
        cache.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
        print(json.dumps({"vehicle_only_cache":str(cache), "raw":len(data["raw"]), "odom":len(data["odometry"]),
                          "first_raw":data["raw"][:1]}, allow_nan=False), flush=True)
    result = evaluate(data)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output":str(args.output), "clock":result["clock"], "window_summaries":result["window_summaries"]}, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
