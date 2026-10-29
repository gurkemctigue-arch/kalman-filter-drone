"""Read-only evaluation of physical three-axis gimbal bags.

The feedback/TF/ground-truth geometry checks use independent recorded
channels. Image centering uses detected box centers, not annotated ground
truth. Use --compare-midpoint for a matched stationary-gimbal comparison.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
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


def read_records(bag: Path, *, preserve_clock: bool = True):
    original = stage1.TOPICS
    try:
        stage1.TOPICS = TOPICS
        records, metadata = stage1.read_rosbag(bag, preserve_clock=preserve_clock)
    finally:
        stage1.TOPICS = original
    return records, metadata


def small_file_binding(path: Path) -> dict[str, str]:
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Expected a small provenance file: " + str(path))
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def evaluation_source_provenance() -> dict[str, Any]:
    script = Path(__file__).resolve()
    root = script.parent.parent
    helpers = (root / "scripts/evaluate_stage1_flight.py", root / "uav_tracking/control/gimbal_geometry.py")
    return {"script": str(script), "script_sha256": small_file_binding(script)["sha256"],
            "dependencies": {str(path): small_file_binding(path)["sha256"] for path in helpers},
            "scope": "Offline physical gimbal geometry and complete recorded Clock/closure-bound terminal redundant feedback audit"}


def complete_joint_payload(message: Any) -> tuple:
    """Compare every JointState field, including ordering and IEEE float bits."""
    header = message.header
    if not isinstance(header.frame_id, str):
        raise ValueError("invalid JointState frame")
    names = tuple(message.name)
    if not names or not all(isinstance(name, str) for name in names):
        raise ValueError("invalid JointState names")
    arrays = []
    for field in ("position", "velocity", "effort"):
        values = tuple(getattr(message, field))
        if len(values) not in ({len(names)} if field == "position" else {0, len(names)}):
            raise ValueError("incomplete JointState " + field)
        if any(stage1.finite(value) is None for value in values):
            raise ValueError("nonfinite JointState " + field)
        arrays.append(tuple(struct.pack("!d", float(value)).hex() for value in values))
    return (int(header.stamp.sec), int(header.stamp.nanosec), header.frame_id, names, *arrays)


def terminal_redundant_audit(records, metadata, feedback_records, pause_context):
    """Never infer a pause merely from a repeated stamp or unchanged angles."""
    audit = {"enabled": pause_context is not None, "valid_pause_evidence": False,
             "failure_reasons": [], "accepted_redundant_samples": 0, "final_clock_s": None,
             "accepted_feedback_indices": [], "complete_payload_sha256": None}
    if pause_context is None:
        return audit
    errors = audit["failure_reasons"]
    try:
        closure, archive = pause_context["recording_closure"], pause_context["bag_integrity"]
        request = closure["pause_request"]
        observed = closure["observations"][-1]
        if (closure.get("schema_version") != 1 or closure.get("status") != "PASS"
                or closure.get("scope") != "WORLD_PAUSE_ACK_AND_OBSERVED_FINAL_SOURCE_CORRESPONDENCE_BEFORE_RECORDER_CLOSE"
                or request.get("command_pause") is not True or request.get("returncode") != 0
                or request.get("response", "").strip() != "data: true"
                or closure.get("observer_cleanup_completed") is not True
                or observed.get("ready") is not True or observed.get("failures") or observed.get("errors")
                or stage1.finite(closure.get("pause_ack_elapsed_wall_s")) is None
                or closure["pause_ack_elapsed_wall_s"] < 0):
            errors.append("missing_successful_pause_ack_and_final_closure")
        if (archive.get("schema_version") != 1 or archive.get("status") != "PASS"
                or archive.get("recorder_exit_code") != 0
                or archive.get("raw_validation", {}).get("status") != "PASS"
                or archive.get("native_reader_validation", {}).get("status") != "PASS"):
            errors.append("missing_successful_closed_archive")
        clocks = [row for row in records if row.topic == "/clock"]
        values = [stage1.stamp_s(row.message.clock) for row in clocks]
        expected = archive["native_reader_validation"]["topic_counts"]["/clock"]
        if (not values or metadata.get("clock_records_preserved") is not True
                or metadata.get("clock_samples_read") != len(values) or len(values) != expected
                or metadata.get("read_errors") or metadata.get("unavailable_types")
                or any(stage1.finite(value) is None or value < 0 for value in values)
                or any(after < before for before, after in zip(values, values[1:]))):
            errors.append("incomplete_or_regressing_recorded_clock")
        final = values[-1] if values else None
        audit["final_clock_s"] = final
        if (final is None or final <= 0 or round(final * 1e9) != observed.get("last_clock_ns")
                or any(row.received_sim_s is not None and row.received_sim_s > final + 1e-9 for row in records)):
            errors.append("closure_final_clock_mismatch")
        if errors:
            return audit
        audit["valid_pause_evidence"] = True
        # A suffix in the original JointState delivery stream only. A live
        # duplicate or an earlier pause followed by resumed time is retained.
        start = len(feedback_records)
        while start and feedback_records[start - 1].time_s == final and feedback_records[start - 1].received_sim_s == final:
            start -= 1
        if len(feedback_records) - start < 1:
            return audit
        payload = complete_joint_payload(feedback_records[start].message)
        if any(complete_joint_payload(row.message) != payload for row in feedback_records[start:]):
            errors.append("conflicting_complete_terminal_jointstate_payload")
            return audit
        retained = start
        retention_mode = "first_terminal_sample"
        boundary_rejections = []
        # The first real final-source message may arrive just before its
        # cross-topic Clock callback. Keep that real sample; only messages
        # actually received at the final Clock can be redundant copies.
        if start and feedback_records[start - 1].time_s == final:
            prior = feedback_records[start - 1]
            lead_ns = (None if stage1.finite(prior.received_sim_s) is None
                       else round(final * 1e9) - round(prior.received_sim_s * 1e9))
            sequences = [row.record_sequence for row in records]
            if (any(type(value) is not int or value < 0 for value in sequences)
                    or any(after <= before for before, after in zip(sequences, sequences[1:]))):
                boundary_rejections.append("missing_or_nonincreasing_complete_delivery_sequence")
            if lead_ns is None or not 0 < lead_ns <= 50_000_000:
                boundary_rejections.append("preceding_final_source_not_within_existing_future_tolerance")
            if any(row.time_s == final for row in feedback_records[:start - 1]):
                boundary_rejections.append("earlier_final_source_feedback_already_exists")
            if not boundary_rejections:
                previous_clocks = [row for row in records if row.topic == "/clock" and row.record_sequence < prior.record_sequence]
                later_clocks = [row for row in records if row.topic == "/clock" and row.record_sequence > prior.record_sequence]
                if (not previous_clocks or stage1.stamp_s(previous_clocks[-1].message.clock) != prior.received_sim_s
                        or not later_clocks or stage1.stamp_s(later_clocks[0].message.clock) != final
                        or feedback_records[start].record_sequence <= later_clocks[0].record_sequence):
                    boundary_rejections.append("preceding_feedback_does_not_immediately_cross_final_clock")
            try:
                if complete_joint_payload(prior.message) != payload:
                    boundary_rejections.append("preceding_complete_jointstate_payload_conflicts")
            except (AttributeError, TypeError, ValueError):
                boundary_rejections.append("preceding_complete_jointstate_payload_unavailable")
            if not boundary_rejections:
                retained = start - 1
                retention_mode = "real_feedback_before_immediately_following_final_clock"
        accepted = list(range(start if retained < start else start + 1, len(feedback_records)))
        retained_record = feedback_records[retained]
        audit.update(accepted_feedback_indices=accepted, accepted_redundant_samples=len(accepted),
                     complete_payload_sha256=hashlib.sha256(repr(payload).encode()).hexdigest(),
                     retained_unique_feedback_index=retained, retention_mode=retention_mode,
                     preceding_retention_rejected_reasons=boundary_rejections,
                     retained_source_s=retained_record.time_s,
                     retained_received_sim_s=retained_record.received_sim_s,
                     retained_record_sequence=retained_record.record_sequence)
    except (AttributeError, KeyError, TypeError, ValueError, IndexError) as error:
        errors.append("invalid_pause_evidence: " + str(error))
    return audit


def evaluate_records(records: list[stage1.Record], metadata: dict[str, Any], mode: str,
                     selected_target: bool = False, pause_context: dict[str, Any] | None = None) -> dict[str, Any]:
    if mode not in {"active", "midpoint"}:
        raise ValueError("mode must be active or midpoint")
    # Preserve recorded delivery order for epoch checks before sorting the
    # remaining channels by their source timestamps.
    feedback_records = [row for row in records if row.topic == "/gimbal/joint_states"]
    pause_audit = terminal_redundant_audit(records, metadata, feedback_records, pause_context)
    redundant = set(pause_audit["accepted_feedback_indices"])
    records = sorted(records, key=lambda row: row.time_s)
    groups: dict[str, list[stage1.Record]] = {}
    for row in records:
        groups.setdefault(row.topic, []).append(row)
    failures: Counter[str] = Counter()
    for error in pause_audit["failure_reasons"]:
        failures["terminal_pause_audit: " + error] += 1
    feedback, startup_feedback, feedback_order_errors = [], [], []
    raw_feedback, raw_order_errors = [], []
    previous_positive_source = None
    raw_previous_positive_source = None
    for feedback_index, row in enumerate(feedback_records):
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
            if raw_previous_positive_source is not None and timestamp <= raw_previous_positive_source:
                raw_order_errors.append({"previous_source_s": raw_previous_positive_source, "source_s": timestamp,
                                         "received_sim_s": row.received_sim_s})
            raw_previous_positive_source = timestamp
            raw_feedback.append((timestamp, angles))
            if feedback_index in redundant:
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
    raw_feedback.sort(key=lambda row: row[0])
    raw_duplicate_pairs = [(before, after) for before, after in zip(raw_feedback, raw_feedback[1:]) if after[0] <= before[0]]
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
        "schema_version": 3, "evaluator_version": "5_clock_boundary_terminal_redundancy",
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
                              "delivery_source_order_errors": raw_order_errors,
                              "duplicate_or_nonincreasing_source_stamps": len(raw_duplicate_pairs),
                              "conflicting_duplicate_source_stamps": sum(not np.array_equal(before[1], after[1]) for before, after in raw_duplicate_pairs),
                              "effective_delivery_source_order_errors": feedback_order_errors,
                              "effective_duplicate_or_nonincreasing_source_stamps": duplicate_feedback,
                              "effective_conflicting_duplicate_source_stamps": duplicate_conflicts,
                              "terminal_redundant_message_audit": pause_audit,
                              "nonpositive_source_stamp_samples": sum(stage1.finite(row.time_s) is not None and row.time_s <= 0
                                                                        for row in feedback_records),
                              "duplicate_source_examples": [
                                  {"prior_source_s": before[0], "source_s": after[0],
                                   "prior_angles_rad": before[1].tolist(), "angles_rad": after[1].tolist(),
                                   "same_angles": bool(np.array_equal(before[1], after[1]))}
                                  for before, after in raw_duplicate_pairs[:20]],
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
                         "Only a complete identical terminal JointState suffix at the global final source/receipt Clock may be audited as redundant after independent successful pause-ACK/recording-closure and complete nonregressing Clock/archive validation; raw errors remain recorded and redundant copies supply no timed evidence.",
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bag", type=Path)
    parser.add_argument("--mode", choices=["active", "midpoint"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare-midpoint", type=Path, help="Previously evaluated midpoint JSON")
    parser.add_argument("--selected-target", action="store_true", help="Multi-target trials: use only the selected fresh track box for centering")
    parser.add_argument("--recording-closure", type=Path, help="Defaults to the trial recording_closure.json")
    parser.add_argument("--bag-integrity", type=Path, help="Defaults to the trial bag_integrity.json")
    parser.add_argument("--source-plan", type=Path, help="Reevaluation: immutable original plan, with --slot-record and --original-report")
    parser.add_argument("--slot-record", type=Path)
    parser.add_argument("--original-report", type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError("Refusing to replace an existing report: " + str(args.output))
    trial = args.bag.resolve().parent
    bound_paths = {"recording_closure": args.recording_closure or trial / "recording_closure.json",
                   "bag_integrity": args.bag_integrity or trial / "bag_integrity.json"}
    historical = (args.source_plan, args.slot_record, args.original_report)
    if any(historical) and not all(historical):
        parser.error("Reevaluation requires --source-plan, --slot-record and --original-report together")
    if all(historical):
        if args.original_report.resolve() == args.output.resolve():
            parser.error("Reevaluation output must preserve the original report")
        bound_paths.update(source_plan=args.source_plan, slot_record=args.slot_record, original_report=args.original_report)
    bindings, context = {}, {}
    for name, path in bound_paths.items():
        bindings[name] = small_file_binding(path)
        if name in {"recording_closure", "bag_integrity"}:
            if path.resolve().parent != trial:
                parser.error("Closure/archive proof must belong to this trial")
            context[name] = json.loads(path.read_text(encoding="utf-8-sig"))
    archive = context["bag_integrity"]
    if Path(archive.get("destination", "")).resolve() != args.bag.resolve():
        parser.error("Archive destination does not bind this bag")
    records, metadata = read_records(args.bag)
    report = evaluate_records(records, metadata, args.mode, args.selected_target, context)
    report.update(trial=str(trial), evaluation_source=evaluation_source_provenance(), input_bindings=bindings,
                  created_utc=datetime.now(timezone.utc).isoformat())
    if args.compare_midpoint:
        report["matched_midpoint_comparison"] = compare_reports(report, json.loads(args.compare_midpoint.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Recheck small inputs after bag deserialization; no large bag is hashed.
    if any(small_file_binding(path) != bindings[name] for name, path in bound_paths.items()):
        raise ValueError("Evaluation provenance input changed while reading the bag")
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"result": report["result"], "checks": report["checks"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
