"""Read-only evaluation of physical three-axis gimbal bags.

The feedback/TF/ground-truth geometry checks use independent recorded
channels. Image centering uses detected box centers, not annotated ground
truth. Use --compare-midpoint for a matched stationary-gimbal comparison.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

import evaluate_stage1_flight as stage1
from uav_tracking.control.gimbal_geometry import (
    JOINT_NAMES, MOUNT_TRANSLATION, camera_optical_quaternion,
    ordered_joint_positions, quaternion_rotation,
)

TOPICS = ("/clock", "/tf", "/tf_static", "/gimbal/joint_states", "/gimbal/diagnostics",
          "/gimbal/yaw/cmd_pos", "/gimbal/pitch/cmd_pos", "/gimbal/roll/cmd_pos",
          "/gimbal/body_yaw_reference", "/ground_truth/vehicle_poses",
          "/vehicle/odometry", "/tracking/observations", "/tracking/flight_phase", "/tracking/state",
          "/tracking/tracks")


def angle_distance(left: np.ndarray, right: np.ndarray) -> float:
    relative = left.T @ right
    return math.acos(float(np.clip((np.trace(relative) - 1.0) / 2.0, -1.0, 1.0)))


def interpolate_vector(rows: list[tuple[float, np.ndarray]], timestamp: float, max_gap: float = 0.10) -> np.ndarray | None:
    if not rows:
        return None
    times = [row[0] for row in rows]
    index = bisect_left(times, timestamp)
    if index < len(rows) and abs(times[index] - timestamp) < 1e-8:
        return rows[index][1].copy()
    if index == 0 or index == len(rows):
        return None
    before, after = rows[index - 1], rows[index]
    if after[0] - before[0] > max_gap or after[0] <= before[0]:
        return None
    fraction = (timestamp - before[0]) / (after[0] - before[0])
    return before[1] * (1 - fraction) + after[1] * fraction


def quaternion_of(transform: Any) -> list[float]:
    q = transform.transform.rotation
    return [q.x, q.y, q.z, q.w]


def position_of(transform: Any) -> np.ndarray:
    p = transform.transform.translation
    return np.array([p.x, p.y, p.z], dtype=float)


def gazebo_frame_key(frame: str) -> str:
    """Normalize Gazebo scoped names before comparing bridged TF frames.

    PosePublisher uses ``::`` scopes internally; ros_gz_bridge converts
    them to ``/`` in TFMessage frame IDs. Keep the full scope for parent
    checks instead of confusing a model-relative link pose with world TF.
    """
    return frame.replace("::", "/").strip("/")


def read_records(bag: Path):
    original = stage1.TOPICS
    try:
        stage1.TOPICS = TOPICS
        records, metadata = stage1.read_rosbag(bag)
    finally:
        stage1.TOPICS = original
    return records, metadata


def evaluate_records(records: list[stage1.Record], metadata: dict[str, Any], mode: str,
                     selected_target: bool = False) -> dict[str, Any]:
    if mode not in {"active", "midpoint"}:
        raise ValueError("mode must be active or midpoint")
    # Preserve recorded delivery order for epoch checks before sorting the
    # remaining channels by their source timestamps.
    feedback_records = [row for row in records if row.topic == "/gimbal/joint_states"]
    records = sorted(records, key=lambda row: row.time_s)
    groups: dict[str, list[stage1.Record]] = {}
    for row in records:
        groups.setdefault(row.topic, []).append(row)
    failures: Counter[str] = Counter()
    feedback, startup_feedback, feedback_order_errors = [], [], []
    previous_positive_source = None
    for row in feedback_records:
        try:
            angles = ordered_joint_positions(row.message.name, row.message.position)
            timestamp = stage1.finite(row.time_s)
            if timestamp is None or timestamp < 0:
                raise ValueError("invalid feedback source timestamp")
            if timestamp == 0:
                if previous_positive_source is not None:
                    raise ValueError("feedback source clock returned to zero after startup")
                startup_feedback.append((timestamp, angles))
                if not np.array_equal(startup_feedback[0][1], angles):
                    raise ValueError("conflicting startup feedback without advancing source time")
                continue
            if previous_positive_source is not None and timestamp <= previous_positive_source:
                feedback_order_errors.append({"previous_source_s": previous_positive_source,
                                              "source_s": timestamp,
                                              "received_sim_s": row.received_sim_s})
            previous_positive_source = timestamp
            feedback.append((timestamp, angles))
        except ValueError as error:
            failures[f"feedback: {error}"] += 1
    feedback.sort(key=lambda row: row[0])
    # Positive duplicate/backwards timestamps remain errors. Stamp-zero
    # feedback while the world is initially paused is audited separately;
    # it has no usable simulation source time and contributes no evidence.
    duplicate_feedback = sum(after[0] <= before[0] for before, after in zip(feedback, feedback[1:]))
    duplicate_pairs = [(before, after) for before, after in zip(feedback, feedback[1:]) if after[0] <= before[0]]
    duplicate_conflicts = sum(not np.array_equal(before[1], after[1]) for before, after in duplicate_pairs)
    diagnostics = []
    for row in groups.get("/gimbal/diagnostics", []):
        try:
            payload = json.loads(row.message.data)
            if not math.isfinite(float(payload["time_s"])):
                raise ValueError("invalid diagnostic source time")
            diagnostics.append((float(payload["time_s"]), payload))
        except (ValueError, KeyError, TypeError) as error:
            failures[f"diagnostic: {error}"] += 1
    camera_tf, body_tf, static_camera_count = [], [], 0
    for topic in ("/tf", "/tf_static"):
        for row in groups.get(topic, []):
            for transform in row.message.transforms:
                pair = (transform.header.frame_id, transform.child_frame_id)
                timestamp = stage1.stamp_s(transform.header.stamp)
                if pair == ("base_link", "camera_link"):
                    if topic == "/tf_static":
                        static_camera_count += 1
                    else:
                        camera_tf.append((timestamp, transform))
                elif pair == ("map", "base_link") and topic == "/tf":
                    body_tf.append((timestamp, transform))
    camera_tf.sort(key=lambda row: row[0])
    body_tf.sort(key=lambda row: row[0])
    tf_angle_errors, tf_translation_errors, tf_source_stamps = [], [], 0
    feedback_by_stamp = {round(timestamp * 1e9): angles for timestamp, angles in feedback}
    for timestamp, transform in camera_tf:
        angles = feedback_by_stamp.get(round(timestamp * 1e9))
        if angles is None:
            failures["camera_tf_without_exact_feedback_source_stamp"] += 1
            continue
        tf_source_stamps += 1
        tf_angle_errors.append(angle_distance(quaternion_rotation(quaternion_of(transform)),
                                             quaternion_rotation(camera_optical_quaternion(angles))))
        tf_translation_errors.append(float(np.linalg.norm(position_of(transform) - MOUNT_TRANSLATION)))
    geometry_errors, geometry_translation_errors, gt_horizon, body_rolls = [], [], [], []
    # PosePublisher emits each link pose relative to the UAV model. Compare
    # base<-mount from actual physics link poses with encoder FK. This also
    # catches a wrong joint axis, zero/bias or source/optical frame convention.
    for row in groups.get("/ground_truth/vehicle_poses", []):
        transforms = {gazebo_frame_key(transform.child_frame_id).rsplit("/", 1)[-1]: transform
                      for transform in row.message.transforms}
        base, camera = transforms.get("base_link"), transforms.get("tracking_camera_mount")
        vehicle = transforms.get("stage1_uav")
        if base is None or camera is None:
            continue
        parent = gazebo_frame_key(base.header.frame_id)
        if gazebo_frame_key(camera.header.frame_id) != parent:
            failures["ground_truth_links_have_different_parent_frames"] += 1
            continue
        if vehicle is not None and gazebo_frame_key(vehicle.child_frame_id) != parent:
            failures["ground_truth_model_does_not_match_link_parent"] += 1
            continue
        timestamp = stage1.stamp_s(camera.header.stamp)
        angles = interpolate_vector(feedback, timestamp)
        if angles is None:
            continue
        try:
            model_from_base = quaternion_rotation(quaternion_of(base))
            model_from_camera = quaternion_rotation(quaternion_of(camera))
            body_from_camera_optical = model_from_base.T @ model_from_camera @ quaternion_rotation([-0.5, 0.5, -0.5, 0.5])
            expected = quaternion_rotation(camera_optical_quaternion(angles))
            geometry_errors.append(angle_distance(expected, body_from_camera_optical))
            actual_mount = model_from_base.T @ (position_of(camera) - position_of(base))
            geometry_translation_errors.append(float(np.linalg.norm(actual_mount - MOUNT_TRANSLATION)))
            if vehicle is not None:
                world_from_model = quaternion_rotation(quaternion_of(vehicle))
                world_from_camera = world_from_model @ model_from_camera
                world_from_base = world_from_model @ model_from_base
                gt_horizon.append((timestamp, math.asin(float(np.clip(-world_from_camera[2, 1], -1.0, 1.0)))))
                body_rolls.append((timestamp, math.atan2(float(world_from_base[2, 1]), float(world_from_base[2, 2]))))
        except ValueError as error:
            failures[f"ground_truth_geometry: {error}"] += 1
    follow = [row.time_s for row in groups.get("/tracking/flight_phase", []) if row.message.data.split(":", 1)[0] == "FOLLOW"]
    metric_start = min(follow) + 2.0 if follow else math.inf
    active_diagnostics = [(time, data) for time, data in diagnostics if data.get("active") is True]
    # An observation has no persistent track ID. In combined multi-target
    # trials use the selected fresh track box, never every same-class box.
    # Default single-target trials retain their original detection metric.
    if selected_target:
        centering_by_stamp = {}
        for row in groups.get("/tracking/tracks", []):
            try:
                payload = json.loads(row.message.data)
                acquired = stage1.finite(payload["acquisition_s"])
                if payload.get("schema_version") != 1 or acquired is None or not isinstance(payload["tracks"], list):
                    raise ValueError("invalid selected-track snapshot")
                if (payload.get("projected") is not False or acquired < metric_start
                        or not payload.get("target_uuid")
                        or payload.get("target_status") not in {"tracking", "reacquired"}):
                    continue
                chosen = [item for item in payload["tracks"]
                          if item.get("track_id") == payload.get("target_track_id") and item.get("matched") is True]
                if len(chosen) != 1:
                    continue
                box = chosen[0]["bbox_xyxy"]
                if (len(box) != 4 or any(stage1.finite(value) is None for value in box)
                        or box[0] >= box[2] or box[1] >= box[3]):
                    raise ValueError("invalid selected-track box")
                centering_by_stamp[acquired] = math.hypot(((box[0]+box[2])/2 - 320.) / 640.,
                                                        ((box[1]+box[3])/2 - 240.) / 480.)
            except (KeyError, TypeError, ValueError) as error:
                failures[f"selected_track_centering: {error}"] += 1
        centering = list(centering_by_stamp.values())
    else:
        centering = [math.hypot((float(row.message.center_u_px) - 320.0) / 640.0,
                               (float(row.message.center_v_px) - 240.0) / 480.0)
                     for row in groups.get("/tracking/observations", []) if row.time_s >= metric_start]
    horizon = [value for timestamp, value in gt_horizon if timestamp >= metric_start]
    roll_excitation = [value for timestamp, value in body_rolls if timestamp >= metric_start]
    # Demonstrate that the command and encoder channels are distinct. Use
    # original diagnostic pairs from one control tick, then independently
    # compare those measured values to the raw encoder stream.
    differences, diagnostic_feedback_errors, not_ready_diagnostics = [], [], []
    for timestamp, data in diagnostics:
        measured, command = data.get("feedback_angles_rad"), data.get("command_angles_rad")
        claims_ready = data.get("active") is True or data.get("reason") in {"tracking", "midpoint"}
        if measured is None or command is None:
            if claims_ready:
                failures["diagnostic_channels: ready diagnostic has no measured/command angles"] += 1
            continue
        try:
            measured, command = np.asarray(measured, dtype=float), np.asarray(command, dtype=float)
            if measured.shape != (3,) or command.shape != (3,) or not np.all(np.isfinite([measured, command])):
                raise ValueError("invalid diagnostic angles")
            # The adapter may parse angles from an initial stamp-zero joint
            # sample, reject its source time, then explicitly freeze to those
            # angles. This invalid/not-ready report makes no usable source-age
            # claim. Keep it in the audit, not in encoder/lag metrics. A
            # tracking/midpoint report with the same missing field must fail.
            if "joint_age_s" not in data and data.get("reason") == "invalid source timestamp":
                if (data.get("active") is not False or data.get("desired_angles_rad") is not None
                        or data.get("commanded_rates_radps") is not None
                        or not np.array_equal(measured, command)):
                    raise ValueError("invalid-source diagnostic does not freeze safely")
                not_ready_diagnostics.append({"time_s": timestamp, "reason": data["reason"],
                                              "feedback_angles_rad": measured.tolist(),
                                              "command_angles_rad": command.tolist()})
                continue
            age = stage1.finite(data["joint_age_s"])
            if age is None or age < 0 or timestamp - age <= 0:
                raise ValueError("invalid diagnostic joint age")
            differences.append(np.abs(command - measured))
            source = timestamp - age
            actual = feedback_by_stamp.get(round(source * 1e9))
            if actual is not None:
                diagnostic_feedback_errors.append(float(np.max(np.abs(actual - measured))))
        except (ValueError, TypeError, KeyError) as error:
            failures[f"diagnostic_channels: {error}"] += 1
    joint_span = np.ptp(np.vstack([angles for _, angles in feedback]), axis=0).tolist() if feedback else [0, 0, 0]
    max_lag = np.max(np.vstack(differences), axis=0).tolist() if differences else [0, 0, 0]
    # Availability at the image timestamp needs both sides of the dynamic
    # interpolation interval; nearest/future-only TF does not count.
    tf_coverage = []
    tf_dummy = [(timestamp, np.zeros(1)) for timestamp, _ in camera_tf]
    body_dummy = [(timestamp, np.zeros(1)) for timestamp, _ in body_tf]
    for row in groups.get("/tracking/observations", []):
        tf_coverage.append(interpolate_vector(tf_dummy, row.time_s) is not None and
                           interpolate_vector(body_dummy, row.time_s) is not None)
    coverage = sum(tf_coverage) / len(tf_coverage) if tf_coverage else 0.0
    checks = {
        "no_bag_read_or_channel_errors": not metadata.get("read_errors") and not metadata.get("unavailable_types") and not failures,
        "three_encoder_joints_recorded": len(feedback) >= 50 and duplicate_feedback == 0 and not feedback_order_errors,
        "all_three_commands_recorded": all(len(groups.get(f"/gimbal/{axis}/cmd_pos", [])) >= 10 for axis in ("yaw", "pitch", "roll")),
        "camera_tf_is_dynamic_feedback_only": static_camera_count == 0 and len(camera_tf) >= 50 and tf_source_stamps == len(camera_tf),
        "tf_matches_source_feedback_geometry": len(tf_angle_errors) >= 50 and max(tf_angle_errors) < 1e-5 and max(tf_translation_errors, default=1) < 1e-8,
        "physical_link_pose_matches_feedback_geometry": len(geometry_errors) >= 30 and max(geometry_errors) < 0.03 and max(geometry_translation_errors, default=1) < 0.005,
        "dynamic_tf_available_at_image_timestamps": len(tf_coverage) >= 10 and coverage >= 0.98,
        "diagnostic_feedback_matches_raw_encoders": len(diagnostic_feedback_errors) >= 30 and max(diagnostic_feedback_errors) < 1e-9,
        "follow_and_visual_metrics_recorded": bool(follow) and len(centering) >= 10 and len(horizon) >= 30,
    }
    if mode == "active":
        checks.update(active_tracking_is_sustained=len(active_diagnostics) >= 100 and active_diagnostics[-1][0] - active_diagnostics[0][0] >= 2.0,
                      all_three_real_joints_move=all(span > 0.003 for span in joint_span),
                      commands_and_encoders_have_physical_lag=all(value > 1e-5 for value in max_lag),
                      body_yaw_reference_recorded=len(groups.get("/gimbal/body_yaw_reference", [])) >= 20)
    else:
        checks.update(midpoint_never_publishes_active_yaw=len(groups.get("/gimbal/body_yaw_reference", [])) == 0 and not active_diagnostics,
                      midpoint_setpoint_is_zero=bool(diagnostics) and all(data.get("desired_angles_rad") in (None, [0.0, 0.0, 0.0]) for _, data in diagnostics))
    return {
        "schema_version": 3, "evaluator_version": "3_audited_paused_startup_feedback",
        "mode": mode, "result": "PASS" if all(checks.values()) else "FAIL_OR_INCOMPLETE",
        "centering_source": "selected_fresh_track_box" if selected_target else "all_detections_in_single_target_world",
        "checks": checks, "metadata": metadata, "channel_errors": dict(failures),
        "not_ready_diagnostics": not_ready_diagnostics,
        "interval": {"metric_start_s": None if not math.isfinite(metric_start) else metric_start,
                     "recorded_end_s": max((row.received_sim_s or row.time_s for row in records), default=None)},
        "physical_feedback": {"samples": len(feedback), "joint_order": JOINT_NAMES, "span_rad": joint_span,
                              "recorded_samples": len(feedback_records),
                              "startup_unready_samples": len(startup_feedback),
                              "startup_unready_angles_rad": startup_feedback[0][1].tolist() if startup_feedback else None,
                              "delivery_source_order_errors": feedback_order_errors,
                              "duplicate_or_nonincreasing_source_stamps": duplicate_feedback,
                              "conflicting_duplicate_source_stamps": duplicate_conflicts,
                              "nonpositive_source_stamp_samples": sum(stage1.finite(row.time_s) is not None and row.time_s <= 0
                                                                        for row in feedback_records),
                              "duplicate_source_examples": [
                                  {"prior_source_s": before[0], "source_s": after[0],
                                   "prior_angles_rad": before[1].tolist(), "angles_rad": after[1].tolist(),
                                   "same_angles": bool(np.array_equal(before[1], after[1]))}
                                  for before, after in duplicate_pairs[:20]],
                              "max_command_encoder_difference_rad": max_lag, "diagnostic_encoder_error_rad": stage1.summary(diagnostic_feedback_errors)},
        "geometry": {"tf_source_stamp_samples": tf_source_stamps, "static_camera_tf_count": static_camera_count,
                     "tf_angle_error_rad": stage1.summary(tf_angle_errors), "tf_translation_error_m": stage1.summary(tf_translation_errors),
                     "physics_link_angle_error_rad": stage1.summary(geometry_errors), "physics_link_translation_error_m": stage1.summary(geometry_translation_errors),
                     "image_timestamp_tf_coverage": coverage},
        "metrics": {"detected_center_normalized_error": stage1.summary(centering),
                    "true_image_horizon_error_rad": stage1.summary(horizon), "true_body_roll_rad": stage1.summary(roll_excitation)},
        "metric_notes": ["Centering uses detected box centers, not manually annotated target centers.",
                         "Horizon uses independent Gazebo physics link poses, never controller diagnostics.",
                         "Physics link pose comparison uses linear encoder interpolation across at most 0.10 s.",
                         "A physical lag check is evidence of distinct channels; it is not a calibrated servo bandwidth measurement.",
                         "Explicit inactive invalid-source diagnostics with frozen commands are audited as not-ready and excluded from source-aligned encoder/lag metrics; ready diagnostics remain strict.",
                         "Initial identical stamp-zero joint feedback from a paused world is audited without counting as timed evidence; conflicts, positive-time duplicates/backtracking, and later zero stamps remain failures.",
                         "Hard yaw lead projection/reset takes precedence over reference derivative bounds during external body-yaw jumps."],
    }


def compare_reports(active: dict[str, Any], midpoint: dict[str, Any]) -> dict[str, Any]:
    comparisons = {}
    for metric in ("detected_center_normalized_error", "true_image_horizon_error_rad"):
        active_value = active["metrics"][metric]["rmse"]
        midpoint_value = midpoint["metrics"][metric]["rmse"]
        comparisons[metric] = {"active_rmse": active_value, "midpoint_rmse": midpoint_value,
                               "active_minus_midpoint": None if active_value is None or midpoint_value is None else active_value - midpoint_value,
                               "improves": active_value is not None and midpoint_value is not None and active_value < midpoint_value}
    return {"schema_version": 1, "result": "PASS" if active["result"] == midpoint["result"] == "PASS" and all(item["improves"] for item in comparisons.values()) else "FAIL_OR_INCOMPLETE",
            "comparisons": comparisons, "notes": ["Pair the same class, target speed/profile and controller settings.",
                                                    "One paired trial demonstrates engineering behavior, not statistical significance."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag", type=Path)
    parser.add_argument("--mode", choices=["active", "midpoint"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare-midpoint", type=Path, help="Previously evaluated midpoint JSON")
    parser.add_argument("--selected-target", action="store_true", help="Multi-target trials: use only the selected fresh track box for centering")
    args = parser.parse_args()
    records, metadata = read_records(args.bag)
    report = evaluate_records(records, metadata, args.mode, args.selected_target)
    if args.compare_midpoint:
        report["matched_midpoint_comparison"] = compare_reports(report, json.loads(args.compare_midpoint.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"result": report["result"], "checks": report["checks"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
