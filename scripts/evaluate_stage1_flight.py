"""Read-only stage-one flight rosbag evaluation; no ROS node is created.

Run after sourcing ROS, px4_msgs and this workspace's message packages:
  python scripts/evaluate_stage1_flight.py BAG --output report.json \
      --target-class person --telemetry-jsonl TRIAL/telemetry.jsonl

All losses, empty detector frames and failed occlusion checks remain in the
report. Detection availability is not detector precision/recall. Estimated
following errors are not ground-truth accuracy. No offset or trajectory fit
is performed to conceal the difference between PX4 map and Gazebo world.
"""

from __future__ import annotations

import argparse
import base64
from bisect import bisect_left, bisect_right
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable


STATE_NAMES = {0: "UNINITIALIZED", 1: "MEASURED", 2: "PREDICTED", 3: "LOST", 4: "AMBIGUOUS"}
EVALUATION_REVISION = 3
LIFECYCLE_NAMES = {0: "IDLE", 1: "ACQUIRE", 2: "FOLLOW", 3: "PREDICT", 4: "HOVER", 5: "SEARCH", 6: "FAILSAFE"}
TOPICS = (
    "/clock", "/ground_truth/poses", "/ground_truth/world_poses", "/ground_truth/uav_poses", "/ground_truth/vehicle_poses",
    "/tracking/state", "/vehicle/odometry", "/tracking/status", "/tracking/observations", "/observations",
    "/fmu/out/vehicle_status_v1", "/fmu/out/vehicle_status",
    "/tracking/detection_diagnostics", "/tracking/flight_phase", "/tracking/command", "/tracking/selection",
)


@dataclass(frozen=True)
class Record:
    topic: str
    time_s: float
    message: Any
    received_sim_s: float | None = None
    record_sequence: int | None = None


def with_record_sequence(records: list[Record]) -> list[Record]:
    """Preserve reader/input order before any acquisition-time sorting."""

    if all(row.record_sequence is not None for row in records):
        return records
    if any(row.record_sequence is not None for row in records):
        raise ValueError("Evaluation records must have either all or no recording sequence numbers")
    return [replace(row, record_sequence=index) for index, row in enumerate(records)]


@dataclass(frozen=True)
class EvaluationConfig:
    target_class: str = "person"
    desired_distance_m: float = 5.0
    desired_height_m: float = 2.0
    max_prediction_s: float = 0.75
    hover_speed_mps: float = 0.30
    hover_sustain_s: float = 0.40
    braking_window_s: float = 2.0
    recovery_window_s: float = 3.0
    max_sync_error_s: float = 0.10
    start_s: float | None = None
    end_s: float | None = None


def finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def stamp_s(stamp: Any) -> float:
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def vector(point: Any) -> tuple[float, float, float]:
    return float(point.x), float(point.y), float(point.z)


def summary(values: Iterable[Any]) -> dict[str, Any]:
    ordered = sorted(number for value in values if (number := finite(value)) is not None)
    if not ordered:
        return {"count": 0, "mean": None, "median": None, "p95": None, "max": None, "rmse": None,
                "mean_absolute": None, "p95_absolute": None, "max_absolute": None}

    def quantile(q: float) -> float:
        index = (len(ordered) - 1) * q
        lower = math.floor(index)
        upper = math.ceil(index)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)

    absolute = sorted(abs(value) for value in ordered)
    abs_index = (len(absolute) - 1) * 0.95
    abs_lower, abs_upper = math.floor(abs_index), math.ceil(abs_index)
    return {
        "count": len(ordered), "mean": sum(ordered) / len(ordered), "median": quantile(0.5),
        "p95": quantile(0.95), "max": ordered[-1],
        "rmse": math.sqrt(sum(value * value for value in ordered) / len(ordered)),
        "mean_absolute": sum(absolute) / len(absolute),
        "p95_absolute": absolute[abs_lower] + (absolute[abs_upper] - absolute[abs_lower]) * (abs_index - abs_lower),
        "max_absolute": absolute[-1],
    }


def nearest(rows: list[Record], times: list[float], timestamp: float, tolerance: float) -> Record | None:
    index = bisect_left(times, timestamp)
    candidates = rows[max(0, index - 1): min(len(rows), index + 1)]
    if not candidates:
        return None
    match = min(candidates, key=lambda row: abs(row.time_s - timestamp))
    return match if abs(match.time_s - timestamp) <= tolerance else None


def occupancy(rows: list[Record], attribute: str, names: dict[int, str], start: float, end: float) -> dict[str, float]:
    durations: Counter[str] = Counter()
    for index, row in enumerate(rows):
        next_time = rows[index + 1].time_s if index + 1 < len(rows) else end
        duration = max(0.0, min(end, next_time) - max(start, row.time_s))
        durations[names.get(int(getattr(row.message, attribute)), "UNKNOWN")] += duration
    return dict(durations)


@contextmanager
def open_bag_reader(path: Path, rosbag2_py: Any):
    """Choose the compression reader and keep decompression out of source bags."""

    metadata = rosbag2_py.Info().read_metadata(str(path), "")
    compression_format = str(metadata.compression_format)
    compression_mode = str(metadata.compression_mode).lower()
    compressed = bool(compression_format and compression_mode not in {"", "none"})
    reader_type = rosbag2_py.SequentialCompressionReader if compressed else rosbag2_py.SequentialReader
    temporary = tempfile.TemporaryDirectory(prefix="stage1_bag_read_") if compressed else None
    try:
        uri = path
        if temporary is not None:
            # File decompression otherwise creates a .db3 alongside the source
            # .db3.zstd. Stage links so only disposable files are created.
            uri = Path(temporary.name)
            shutil.copy2(path / "metadata.yaml", uri / "metadata.yaml")
            for relative in metadata.relative_file_paths:
                destination = uri / relative
                if not destination.resolve().is_relative_to(uri.resolve()):
                    raise ValueError("Bag storage filename escapes the bag directory")
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    destination.hardlink_to((path / relative).resolve())
                except OSError:  # Cross-filesystem and Windows privilege fallback.
                    shutil.copy2(path / relative, destination)
        reader = reader_type()
        reader.open(rosbag2_py.StorageOptions(uri=str(uri), storage_id=metadata.storage_identifier),
                    rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"))
        yield reader, {
            "storage_identifier": metadata.storage_identifier,
            "compression_format": compression_format, "compression_mode": compression_mode,
            "reader": type(reader).__name__, "source_bag_read_only": True,
            "decompression_cache": "temporary directory, removed after reading" if compressed else None,
        }
    finally:
        if temporary is not None:
            temporary.cleanup()


def read_rosbag(path: Path, *, preserve_clock: bool = False) -> tuple[list[Record], dict[str, Any]]:
    """Deserialize selected topics, mapping unheadered messages with /clock.

    Recorder timestamps may use wall time, so they are never blindly mixed
    with sensor simulation timestamps. A prior /clock sample supplies receive
    simulation time. Diagnostics carry their own completed_s timestamp.
    preserve_clock=True also returns Clock records so independent evaluations
    retain silence through the full recorded clock tail. False preserves the
    established historical evaluator input/interval behavior.
    """
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as exc:
        raise RuntimeError("Source ROS, px4_msgs and the project install before reading a bag") from exc

    with open_bag_reader(path, rosbag2_py) as (reader, storage_metadata):
        records, read_metadata = _deserialize_bag(reader, rosbag2_py, deserialize_message, get_message,
                                                preserve_clock=preserve_clock)
    return records, {"bag": str(path.resolve()), **storage_metadata, **read_metadata}


def _deserialize_bag(reader: Any, rosbag2_py: Any, deserialize_message: Any, get_message: Any,
                     *, preserve_clock: bool = False):
    types = {topic.name: topic.type for topic in reader.get_all_topics_and_types()}
    reader.set_filter(rosbag2_py.StorageFilter(topics=[topic for topic in TOPICS if topic in types]))
    classes, unavailable, errors = {}, {}, Counter()
    startup_unclocked: Counter[str] = Counter()
    startup_unclocked_records = []
    for topic, type_name in types.items():
        if topic not in TOPICS:
            continue
        try:
            classes[topic] = get_message(type_name)
        except (ImportError, AttributeError, ValueError) as exc:
            unavailable[topic] = f"{type(exc).__name__}: {exc}"
    records: list[Record] = []
    clock = None
    clock_samples_read = 0
    time_sources: Counter[str] = Counter()
    record_sequence = -1
    while reader.has_next():
        topic, serialized, _record_timestamp_ns = reader.read_next()
        record_sequence += 1
        if topic not in classes:
            continue
        try:
            message = deserialize_message(serialized, classes[topic])
            if topic == "/clock":
                clock = stamp_s(message.clock)
                clock_samples_read += 1
                if preserve_clock:
                    if finite(clock) is None:
                        raise ValueError("nonfinite recorded clock timestamp")
                    records.append(Record(topic, clock, message, clock, record_sequence))
                continue
            if topic == "/tracking/detection_diagnostics":
                payload = json.loads(message.data)
                timestamp = finite(payload.get("completed_s"))
                if timestamp is None:
                    raise ValueError("diagnostic completed_s is absent or invalid")
                time_sources["diagnostic_completed_s"] += 1
            elif hasattr(message, "header"):
                timestamp = stamp_s(message.header.stamp)
                time_sources["header"] += 1
            elif hasattr(message, "transforms") and message.transforms:
                timestamp = stamp_s(message.transforms[0].header.stamp)
                time_sources["transform_header"] += 1
            elif clock is not None:
                timestamp = clock
                time_sources["latest_clock"] += 1
            else:
                # Deserialization succeeded. Preserve this untimed startup
                # evidence separately instead of inventing simulation time or
                # misreporting an ordinary recorder startup race as corruption.
                startup_unclocked[topic] += 1
                startup_unclocked_records.append({
                    "topic": topic, "record_timestamp_ns": int(_record_timestamp_ns),
                    "serialized_cdr_base64": base64.b64encode(serialized).decode("ascii"),
                })
                continue
            if finite(timestamp) is None:
                raise ValueError("nonfinite simulation timestamp")
            records.append(Record(topic, timestamp, message, clock, record_sequence))
        except Exception as exc:  # A corrupt/mismatched message remains a reported failure.
            errors[f"{topic}: {type(exc).__name__}: {exc}"] += 1
    return records, {
        "topic_types": {key: value for key, value in types.items() if key in TOPICS},
        "unavailable_types": unavailable, "read_errors": dict(errors), "time_sources": dict(time_sources),
        "clock_recorded": "/clock" in types,
        "clock_samples_read": clock_samples_read,
        "clock_records_preserved": preserve_clock,
        "startup_unclocked_messages": dict(startup_unclocked),
        "startup_unclocked_records": startup_unclocked_records,
        "startup_unclocked_note": "Successfully decoded messages before the first recorded /clock remain here with original recorder timestamps and exact CDR bytes; no simulation timestamp is assigned and they are excluded from timed metrics",
        "receive_time_note": "received_sim_s uses the latest recorded /clock; recorder wall timestamps are not compared with sim time",
        "record_sequence_note": "Zero-based filtered reader order, including clock/unreadable entries; equal operational timestamps retain this order",
    }


def read_monitor_events(telemetry: Path | None, monitor_summary: Path | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events, metadata = [], {}
    if telemetry is not None:
        for line_number, line in enumerate(telemetry.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if row.get("kind") in {"shutter", "shutter_service_result", "phase"}:
                    events.append(row)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid telemetry JSON at line {line_number}") from exc
        metadata["telemetry_jsonl"] = str(telemetry.resolve())
    if monitor_summary is not None:
        data = json.loads(monitor_summary.read_text(encoding="utf-8"))
        metadata["monitor_summary"] = str(monitor_summary.resolve())
        metadata["follow_start_s"] = data.get("follow_start_s")
        if not any(row.get("kind") == "shutter" for row in events):
            events.extend({"kind": "shutter", **row} for row in data.get("shutter_events", []))
    return sorted(events, key=lambda row: float(row.get("time_s", 0))), metadata


def shutter_windows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    windows, active_start = [], None
    for row in events:
        if row.get("kind") != "shutter":
            continue
        timestamp = finite(row.get("time_s"))
        if timestamp is None:
            continue
        if row.get("active") and active_start is None:
            active_start = row
        elif not row.get("active") and active_start is not None:
            windows.append({"start_s": float(active_start["time_s"]), "end_s": timestamp, "complete": True,
                            "close_request_id": active_start.get("request_id"), "open_request_id": row.get("request_id")})
            active_start = None
    if active_start is not None:
        windows.append({"start_s": float(active_start["time_s"]), "end_s": None, "complete": False,
                        "close_request_id": active_start.get("request_id"), "open_request_id": None})
    return windows


def _first_time(rows: list[Record], predicate, start: float, end: float) -> float | None:
    return next((row.time_s for row in rows if start <= row.time_s <= end and predicate(row.message)), None)


def _speed(row: Record) -> float:
    return math.sqrt(sum(value * value for value in vector(row.message.twist.twist.linear)))


def shutter_execution(window: dict[str, Any], responses: list[dict[str, Any]]) -> dict[str, Any]:
    """Match each requested shutter action to its own successful response."""

    def response_for(request_id: Any, active: bool, request_time: float | None) -> dict[str, Any]:
        result = {"request_id": request_id, "response_s": None, "success": None, "reason": None}
        if type(request_id) is not int or request_id <= 0 or request_time is None:
            result["reason"] = "missing_request_identity"
            return result
        matching = [row for row in responses if row.get("request_id") == request_id]
        if not matching:
            result["reason"] = "missing_service_response"
            return result
        if len(matching) != 1:
            result.update(success=False, reason="duplicate_service_response")
            return result
        row = matching[0]
        response_time = finite(row.get("time_s"))
        source_time = finite(row.get("request_time_s"))
        valid = (row.get("active") is active and source_time is not None
                 and abs(source_time - request_time) <= 1e-9
                 and response_time is not None and response_time >= request_time)
        result.update(response_s=response_time, success=bool(valid and row.get("success") is True),
                      reason=None if valid and row.get("success") is True else "failed_or_mismatched_service_response")
        return result

    close = response_for(window.get("close_request_id"), True, finite(window.get("start_s")))
    opened = response_for(window.get("open_request_id"), False, finite(window.get("end_s")))
    end = finite(window.get("end_s"))
    close_before_open = (close["response_s"] <= end
                         if close["success"] is True and end is not None else None)
    return {
        "close_request_id": close["request_id"], "open_request_id": opened["request_id"],
        "close_response_s": close["response_s"], "open_response_s": opened["response_s"],
        "close_success": close["success"], "open_success": opened["success"],
        "close_ack_before_open_request": close_before_open,
        "close_reason": close["reason"], "open_reason": opened["reason"],
        "successful_close_response_to_open_request_s": end - close["response_s"] if close_before_open is True else None,
        "semantics": "Matched SetEntityPose acknowledgements corroborate execution; request intervals are not exact rendered-image occlusion durations",
    }


def reselection_evidence(states: list[Record], selections: list[Record], lost: float,
                        opened: float, trial_end: float, config: EvaluationConfig) -> dict[str, Any]:
    """Authorize a new task only after a valid operation and new-UUID measurement."""

    before = [row for row in states if row.time_s <= lost and getattr(row.message, "target_uuid", "")]
    original_uuid = str(before[-1].message.target_uuid).strip() if before else None
    result = {
        "confirmed": False, "original_target_uuid": original_uuid, "requested_target_uuid": None,
        "confirmed_target_uuid": None, "selection_time_s": None, "confirmation_time_s": None,
        "confirmation_record_sequence": None, "confirmation_state_index": None,
        "confirmation_image_stamp_s": None, "confirmed_track_id": None, "action": None,
        "selection_action_code": None, "first_valid_request_s": None, "invalid_candidates": [],
    }
    candidates = sorted(selections, key=lambda row: (
        max(row.time_s, row.received_sim_s if row.received_sim_s is not None else row.time_s),
        row.record_sequence if row.record_sequence is not None else 0))
    for selection in candidates:
        message = selection.message
        action = getattr(message, "action", None)
        if action not in {0, 2}:
            continue  # CLEAR never authorizes an automatic return.
        source_time = stamp_s(message.header.stamp)
        received = finite(selection.received_sim_s)
        request_time = max(selection.time_s, received if received is not None else selection.time_s)
        if request_time < lost or request_time > trial_end:
            continue
        reasons = []
        if not original_uuid:
            reasons.append("missing_original_uuid")
        if source_time <= 0 or source_time < lost or received is None or received < lost or source_time - received > 0.05:
            reasons.append("invalid_selection_time")
        requested_uuid = str(getattr(message, "target_uuid", "") or "").strip()
        track_id = getattr(message, "track_id", 0)
        category = str(getattr(message, "class_name", "") or "")
        if action == 0:
            if not requested_uuid or requested_uuid == original_uuid:
                reasons.append("selection_requires_new_uuid")
            if category and category != config.target_class:
                reasons.append("selection_class_mismatch")
            width, height = finite(getattr(message, "width_px", None)), finite(getattr(message, "height_px", None))
            center_u, center_v = finite(getattr(message, "center_u_px", None)), finite(getattr(message, "center_v_px", None))
            valid_track = type(track_id) is int and track_id > 0
            valid_box = (width is not None and height is not None and width > 0 and height > 0
                         and center_u is not None and center_v is not None)
            if not valid_track and not valid_box:
                reasons.append("selection_has_no_valid_track_or_box")
        if not reasons:
            if result["first_valid_request_s"] is None:
                result["first_valid_request_s"] = request_time
            # The first active state must itself confirm the newly selected
            # task. A stale/old-UUID return cannot be retroactively authorized
            # by some later matching measurement.
            request_sequence = selection.record_sequence
            active_entries = [(index, row) for index, row in enumerate(states)
                              if row.time_s <= trial_end and row.message.state in {1, 2}
                              and (row.time_s >= request_time or (
                                  request_sequence is not None and row.record_sequence is not None
                                  and row.record_sequence >= request_sequence))]
            # Keep all previously eligible candidates, and also retain an
            # active state recorded after the request whose time regressed.
            # Source/operational-time sorting must not skip the first return.
            active_entry = min(active_entries, key=lambda entry: (
                entry[1].record_sequence if entry[1].record_sequence is not None else entry[0]), default=None)
            if active_entry is None:
                reasons.append("no_measured_confirmation")
            else:
                active_index, active = active_entry
                confirmed_uuid = str(getattr(active.message, "target_uuid", "") or "").strip()
                image_time = stamp_s(active.message.header.stamp)
                delivery = finite(active.received_sim_s)
                prediction_age = finite(getattr(active.message, "prediction_age_s", None))
                fresh = (active.message.state == 1 and active.time_s >= request_time
                         and delivery is not None and delivery >= request_time
                         and image_time >= opened and prediction_age is not None and prediction_age >= 0
                         and prediction_age + max(0.0, delivery - image_time) <= config.max_prediction_s)
                same_class = str(getattr(active.message, "class_name", "")) == config.target_class
                correct_uuid = bool(confirmed_uuid and confirmed_uuid != original_uuid
                                    and (action == 2 or confirmed_uuid == requested_uuid))
                correct_track = int(getattr(active.message, "track_id", 0)) > 0 and (
                    action == 2 or not (type(track_id) is int and track_id > 0) or active.message.track_id == track_id)
                if fresh and same_class and correct_uuid and correct_track:
                    result.update(confirmed=True, requested_target_uuid=requested_uuid if action == 0 else None,
                                  confirmed_target_uuid=confirmed_uuid, selection_time_s=request_time,
                                  confirmation_time_s=active.time_s, confirmation_image_stamp_s=image_time,
                                  confirmation_record_sequence=active.record_sequence,
                                  confirmation_state_index=active_index,
                                  confirmed_track_id=int(active.message.track_id),
                                  action="SELECT" if action == 0 else "RESET", selection_action_code=int(action))
                    return result
                reasons.append("first_active_state_does_not_confirm_fresh_new_task")
        result["invalid_candidates"].append({"time_s": request_time, "action": int(action),
                                               "requested_target_uuid": requested_uuid, "reasons": reasons})
    return result


def post_reselection_tracking(states: list[Record], statuses: list[Record],
                              selection: dict[str, Any] | None, trial_end: float,
                              config: EvaluationConfig) -> dict[str, Any]:
    """Require sustained observed tracking after a confirmed new task, through trial end."""

    minimum_duration, tail_freshness, maximum_gap, control_grace = 5.0, 0.5, 0.5, 0.10
    check_names = (
        "minimum_recording_duration", "minimum_state_span", "minimum_control_span",
        "same_target_active_states_only", "tracking_control_only_after_grace",
        "continuous_state_evidence", "continuous_control_evidence",
        "fresh_state_at_trial_end", "tracking_control_at_trial_end",
        "chronological_state_and_control_evidence",
    )
    result = {
        "result": "INCOMPLETE_EVIDENCE", "checks": dict.fromkeys(check_names),
        "confirmed_target_uuid": (selection or {}).get("confirmed_target_uuid"),
        "confirmation_time_s": (selection or {}).get("confirmation_time_s"),
        "confirmation_record_sequence": (selection or {}).get("confirmation_record_sequence"),
        "confirmation_state_index": (selection or {}).get("confirmation_state_index"),
        "trial_end_s": trial_end, "minimum_duration_s": minimum_duration,
        "tail_freshness_s": tail_freshness, "maximum_evidence_gap_s": maximum_gap,
        "control_grace_s": control_grace, "maximum_measurement_age_s": config.max_prediction_s,
        "observed_duration_s": None, "state_span_s": None, "control_span_s": None,
        "last_state_age_to_trial_end_s": None, "last_control_age_to_trial_end_s": None,
        "last_state_measurement_age_at_trial_end_s": None,
        "maximum_state_evidence_gap_s": None, "maximum_control_evidence_gap_s": None,
        "state_count": 0, "tracking_control_count": 0,
        "state_counts": {}, "lifecycle_counts": {}, "first_invalid_state_s": None,
        "first_uuid_mismatch_s": None, "first_nontracking_control_after_grace_s": None,
        "state_time_regression_count": 0, "control_time_regression_count": 0,
        "receive_clock_regression_count": 0, "invalid_receive_clock_count": 0,
        "chronology_time_basis": "received_sim_s",
        "receive_clock_order_scope": None,
        "operational_time_regressions_are_diagnostic_only": True,
        "boundary_evidence": "UNAVAILABLE",
        "semantics": "The exact confirmation record starts the sustained interval. Recording order, not a float-time window, selects later records; equal-time or backdated later faults remain evidence. Receive /clock values must be valid and nondecreasing. Derived max(header, receive) time regressions are diagnostic because measurement and prediction headers have different meanings. A brief confirmation cannot certify sustained tracking",
    }
    if not selection or selection.get("confirmed") is not True:
        return result
    start = finite(selection.get("confirmation_time_s"))
    target_uuid = selection.get("confirmed_target_uuid")
    if start is None or not target_uuid:
        return result
    sequence = selection.get("confirmation_record_sequence")
    boundary_index = selection.get("confirmation_state_index")
    if type(sequence) is int:
        matches = [index for index, row in enumerate(states) if row.record_sequence == sequence]
        if len(matches) != 1:
            return result
        boundary_index = matches[0]
        result["boundary_evidence"] = "RECORD_SEQUENCE"
        if any(row.record_sequence is None for row in states + statuses):
            result["boundary_evidence"] = "MISSING_RECORD_SEQUENCE"
            return result
    elif type(boundary_index) is int and 0 <= boundary_index < len(states):
        # In-memory callers can retain the exact state-list index. Never
        # invent a boundary by finding a later state with a matching UUID.
        result["boundary_evidence"] = "EXACT_STATE_LIST_INDEX"
        sequence = None
    else:
        return result
    boundary = states[boundary_index]
    if boundary.time_s != start:
        result["boundary_evidence"] = "INVALID_BOUNDARY_TIME"
        return result
    result["confirmation_state_index"] = boundary_index
    if sequence is not None:
        state_rows = sorted((row for row in states if row.record_sequence >= sequence and row.time_s <= trial_end),
                            key=lambda row: row.record_sequence)
        control_rows = sorted((row for row in statuses if row.record_sequence >= sequence and row.time_s <= trial_end),
                              key=lambda row: row.record_sequence)
    else:
        state_rows = [row for row in states[boundary_index:] if row.time_s <= trial_end]
        # A standalone state-list index carries no cross-topic ordering.
        # Production evaluate() always supplies sequences for both streams.
        control_rows = sorted((row for row in statuses if start <= row.time_s <= trial_end), key=lambda row: row.time_s)
    active_controls = [row for row in control_rows if row.message.lifecycle in {2, 3}]
    invalid_states = [row for row in state_rows if row.message.state not in {1, 2}
                      or getattr(row.message, "target_uuid", "") != target_uuid
                      or getattr(row.message, "class_name", "") != config.target_class
                      or int(getattr(row.message, "track_id", 0)) <= 0]
    wrong_uuids = [row for row in state_rows if getattr(row.message, "target_uuid", "") != target_uuid]
    invalid_controls = [row for row in control_rows
                        if row.time_s >= start + control_grace and row.message.lifecycle not in {2, 3}]

    def time_regressions(rows: list[Record]) -> int:
        times = [start] + [row.time_s for row in rows]
        return sum(right < left for left, right in zip(times, times[1:]))

    state_regressions, control_regressions = time_regressions(state_rows), time_regressions(control_rows)
    def valid_receive(row: Record) -> float | None:
        received = finite(row.received_sim_s)
        return received if received is not None and received >= 0 else None

    initial_receive = valid_receive(boundary)
    if sequence is not None:
        clock_groups = [sorted(state_rows + control_rows, key=lambda row: row.record_sequence)]
        result["receive_clock_order_scope"] = "GLOBAL_RECORD_SEQUENCE"
    else:
        # Exact state indices preserve only their own stream's order. This
        # fallback is for direct in-memory calls; production entry points
        # number all input records before filtering or sorting.
        clock_groups = [state_rows, control_rows]
        result["receive_clock_order_scope"] = "PER_STREAM_IN_MEMORY"
    invalid_receive = sum(valid_receive(row) is None for rows in clock_groups for row in rows)
    receive_regressions = 0
    for rows in clock_groups:
        previous_receive = initial_receive
        for row in rows:
            received = valid_receive(row)
            if received is not None:
                receive_regressions += previous_receive is not None and received < previous_receive
                previous_receive = received

    def span(rows: list[Record]) -> float | None:
        return rows[-1].time_s - rows[0].time_s if rows else None

    def evidence_gap(rows: list[Record]) -> float | None:
        if not rows:
            return None
        times = [start] + [row.time_s for row in rows] + [trial_end]
        return max(right - left for left, right in zip(times, times[1:]))

    last_state = state_rows[-1] if state_rows else None
    last_control = control_rows[-1] if control_rows else None
    state_tail = trial_end - last_state.time_s if last_state is not None else None
    control_tail = trial_end - last_control.time_s if last_control is not None else None
    measurement_age = None
    if last_state is not None:
        image_time = stamp_s(last_state.message.header.stamp)
        reported_age = finite(getattr(last_state.message, "prediction_age_s", None))
        received = finite(last_state.received_sim_s)
        if reported_age is not None and reported_age >= 0 and received is not None and image_time <= received + 0.05:
            measurement_age = reported_age + max(0.0, trial_end - image_time)
    state_span, control_span = span(state_rows), span(active_controls)
    state_gap, control_gap = evidence_gap(state_rows), evidence_gap(control_rows)
    checks = {
        "minimum_recording_duration": trial_end - start >= minimum_duration,
        "minimum_state_span": state_span >= minimum_duration if state_span is not None else None,
        "minimum_control_span": control_span >= minimum_duration if control_span is not None else None,
        "same_target_active_states_only": not invalid_states if state_rows else None,
        "tracking_control_only_after_grace": (
            not invalid_controls and active_controls[0].time_s <= start + control_grace
        ) if active_controls else None,
        "continuous_state_evidence": state_gap <= maximum_gap if state_gap is not None else None,
        "continuous_control_evidence": control_gap <= maximum_gap if control_gap is not None else None,
        "fresh_state_at_trial_end": (
            state_tail <= tail_freshness and last_state not in invalid_states
            and measurement_age <= config.max_prediction_s
        ) if last_state is not None and measurement_age is not None else None,
        "tracking_control_at_trial_end": (
            control_tail <= tail_freshness and last_control.message.lifecycle in {2, 3}
        ) if last_control is not None else None,
        "chronological_state_and_control_evidence": (
            receive_regressions == 0) if state_rows and control_rows and initial_receive is not None
            and invalid_receive == 0 else None,
    }
    result.update(
        result="FAIL" if any(value is False for value in checks.values()) else (
            "INCOMPLETE_EVIDENCE" if any(value is None for value in checks.values()) else "PASS"),
        checks=checks, observed_duration_s=trial_end - start,
        state_span_s=state_span, control_span_s=control_span,
        last_state_age_to_trial_end_s=state_tail, last_control_age_to_trial_end_s=control_tail,
        last_state_measurement_age_at_trial_end_s=measurement_age,
        maximum_state_evidence_gap_s=state_gap, maximum_control_evidence_gap_s=control_gap,
        state_count=len(state_rows), tracking_control_count=len(active_controls),
        state_counts=dict(Counter(STATE_NAMES.get(int(row.message.state), "UNKNOWN") for row in state_rows)),
        lifecycle_counts=dict(Counter(LIFECYCLE_NAMES.get(int(row.message.lifecycle), "UNKNOWN") for row in control_rows)),
        first_invalid_state_s=invalid_states[0].time_s if invalid_states else None,
        first_uuid_mismatch_s=wrong_uuids[0].time_s if wrong_uuids else None,
        first_nontracking_control_after_grace_s=invalid_controls[0].time_s if invalid_controls else None,
        state_time_regression_count=state_regressions, control_time_regression_count=control_regressions,
        receive_clock_regression_count=receive_regressions, invalid_receive_clock_count=invalid_receive,
    )
    return result


def evaluate_occlusion(window: dict[str, Any], states: list[Record], statuses: list[Record],
                       odometry: list[Record], diagnostics: list[dict[str, Any]],
                       config: EvaluationConfig, trial_end: float,
                       selections: list[Record] | None = None,
                       shutter_service_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    start = window["start_s"]
    end = window["end_s"] if window["end_s"] is not None else trial_end
    duration = end - start
    recovery_end = min(trial_end, end + config.recovery_window_s)
    predicted = _first_time(states, lambda msg: msg.state == 2, start, recovery_end)
    lost = _first_time(states, lambda msg: msg.state == 3, start, recovery_end)
    hover = _first_time(statuses, lambda msg: msg.lifecycle == 4, start, recovery_end)
    # Both clocks are evidence: an old image can arrive after opening, and a
    # future-dated image can have been received before opening.  Neither can
    # certify recovery. Missing receive time remains incomplete evidence.
    pre_states = [row for row in states if start - 1.0 <= row.time_s < start and row.message.track_id]
    post_states = [row for row in states if end <= row.time_s <= recovery_end and row.message.state == 1
                   and stamp_s(row.message.header.stamp) >= end
                   and row.received_sim_s is not None and row.received_sim_s >= end]
    resumed = post_states[0].time_s if post_states else None
    missing_recovery_receive = sum(
        end <= row.time_s <= recovery_end and row.message.state == 1
        and stamp_s(row.message.header.stamp) >= end and row.received_sim_s is None
        for row in states
    )
    identity_preserved = None
    if pre_states and post_states:
        before, after = pre_states[-1].message, post_states[0].message
        identity_preserved = bool(before.track_id == after.track_id and before.target_uuid == after.target_uuid)
    inside = [row for row in diagnostics if start <= row["stamp_s"] <= end]
    valid_times = sorted(row["stamp_s"] for row in diagnostics if row["valid_depth"])
    preceding = [value for value in valid_times if value < start]
    succeeding = [value for value in valid_times if value > end]
    gap = succeeding[0] - preceding[-1] if preceding and succeeding else None
    # Only count odometry while HOVER persists; recovered tracking may move again.
    hover_end = None
    if hover is not None:
        hover_end = next((row.time_s for row in statuses if row.time_s > hover and row.message.lifecycle != 4), recovery_end)
    brake_end = min(hover + config.braking_window_s, hover_end, trial_end) if hover is not None else None
    stop_time = None
    braking_rows = [row for row in odometry if hover is not None and hover <= row.time_s <= brake_end]
    # A sustained slow interval must have continuous odometry evidence. One
    # isolated low-speed sample cannot certify braking.
    low_start = previous_time = None
    for row in braking_rows:
        if _speed(row) <= config.hover_speed_mps:
            if low_start is None or (previous_time is not None and row.time_s - previous_time > 0.25):
                low_start = row.time_s
            if row.time_s - low_start >= config.hover_sustain_s:
                stop_time = low_start
                break
        else:
            low_start = None
        previous_time = row.time_s
    entry_candidates = [row for row in odometry if start - 0.5 <= row.time_s <= start]
    hover_entry = [row for row in odometry if hover is not None and hover - 0.2 <= row.time_s <= hover + 0.1]
    speed_at_shutter = finite(_speed(entry_candidates[-1])) if entry_candidates else None
    speed_at_hover = finite(_speed(min(hover_entry, key=lambda row: abs(row.time_s - hover)))) if hover_entry else None
    long_occlusion = duration > config.max_prediction_s
    reselection = (reselection_evidence(states, selections or [], lost, end, trial_end, config)
                   if long_occlusion and lost is not None else None)
    explicit_reselection = reselection["selection_time_s"] if reselection is not None and reselection["confirmed"] else None
    sustained_tracking = post_reselection_tracking(states, statuses, reselection, trial_end, config) if long_occlusion else None
    execution = shutter_execution(window, shutter_service_results or [])
    # A long loss terminates identity continuity. Neither a measured nor a
    # predicted state can reactivate the task before recorded SELECT/RESET.
    # Independently watch controller status, allowing two 20-Hz ticks for a
    # previously queued status to cross the loss boundary.
    unauthorized_end = explicit_reselection - 1e-9 if explicit_reselection is not None else trial_end
    unauthorized_measured = (_first_time(states, lambda msg: msg.state == 1, lost, unauthorized_end)
                             if long_occlusion and lost is not None else None)
    unauthorized_predicted = (_first_time(states, lambda msg: msg.state == 2, lost, unauthorized_end)
                              if long_occlusion and lost is not None else None)
    unauthorized_state_times = [value for value in (unauthorized_measured, unauthorized_predicted) if value is not None]
    unauthorized_recovery = min(unauthorized_state_times) if unauthorized_state_times else None
    control_grace_s = 0.10
    unauthorized_control = (_first_time(statuses, lambda msg: msg.lifecycle in {2, 3},
                                        lost + control_grace_s, unauthorized_end)
                            if long_occlusion and lost is not None else None)
    lost_during_short = lost is not None and lost <= (resumed if resumed is not None else recovery_end)
    event_states = any(start <= row.time_s <= recovery_end for row in states)
    event_statuses = any(start <= row.time_s <= recovery_end for row in statuses)
    checks = {
        "recorded_close_event": bool(window["complete"]),
        "shutter_close_service_succeeded": execution["close_success"],
        "shutter_open_service_succeeded": execution["open_success"],
        "shutter_close_ack_before_open_request": execution["close_ack_before_open_request"],
        "detector_interruption_observed": any(not row["has_candidate"] for row in inside) if inside else None,
        "prediction_observed": (predicted is not None) if event_states else None,
        "lost_observed_for_long_occlusion": (lost is not None and lost <= end) if long_occlusion and event_states else None,
        "hover_observed_for_long_occlusion": (hover is not None and hover <= end) if long_occlusion and event_statuses else None,
        "sustained_low_speed_after_hover": (stop_time is not None) if long_occlusion and braking_rows else None,
        "no_automatic_recovery_after_long_loss": (unauthorized_recovery is None) if long_occlusion and lost is not None else None,
        "no_tracking_control_before_reselection_after_long_loss": (unauthorized_control is None) if long_occlusion and lost is not None and event_statuses else None,
        "sustained_tracking_after_reselection": (
            True if sustained_tracking["result"] == "PASS" else False if sustained_tracking["result"] == "FAIL" else None
        ) if long_occlusion else None,
        "no_loss_during_short_occlusion": (not lost_during_short) if not long_occlusion and states else None,
        "identity_preserved_on_observed_recovery": identity_preserved,
    }
    required = ["recorded_close_event", "shutter_close_service_succeeded", "shutter_open_service_succeeded",
                "shutter_close_ack_before_open_request", "detector_interruption_observed", "prediction_observed"]
    required += (["lost_observed_for_long_occlusion", "hover_observed_for_long_occlusion", "sustained_low_speed_after_hover",
                  "no_automatic_recovery_after_long_loss", "no_tracking_control_before_reselection_after_long_loss",
                  "sustained_tracking_after_reselection"]
                 if long_occlusion else ["no_loss_during_short_occlusion", "identity_preserved_on_observed_recovery"])
    result = "FAIL" if any(checks[key] is False for key in required) else (
        "INCOMPLETE_EVIDENCE" if any(checks[key] is None for key in required) else "PASS")
    return {
        **window, "duration_s": duration, "kind": "long" if long_occlusion else "short",
        "event_semantics": "requested shutter pose interval, not an independently measured occluder state",
        "shutter_execution": execution,
        "explicit_reselection": reselection,
        "post_reselection_tracking": sustained_tracking,
        "first_predicted_s": predicted, "first_lost_s": lost, "first_hover_s": hover,
        "first_measured_after_open_s": resumed,
        "first_explicit_reselection_s": explicit_reselection,
        "first_unrequested_measured_after_loss_s": unauthorized_measured,
        "first_unrequested_predicted_after_loss_s": unauthorized_predicted,
        "first_unrequested_active_state_after_loss_s": unauthorized_recovery,
        "first_unrequested_tracking_control_after_loss_s": unauthorized_control,
        "tracking_control_grace_after_loss_s": control_grace_s,
        "post_open_measured_missing_receive_time_count": missing_recovery_receive,
        "recovery_after_open_s": resumed - end if resumed is not None else None,
        "valid_depth_gap_straddling_event_s": gap,
        "diagnostic_frames_inside": len(inside),
        "candidate_free_frames_inside": sum(not row["has_candidate"] for row in inside),
        "valid_depth_frames_inside": sum(row["valid_depth"] for row in inside),
        "speed_at_shutter_start_mps": speed_at_shutter, "speed_at_hover_entry_mps": speed_at_hover,
        "braking_observation_end_s": brake_end,
        "braking_speed_mps": summary(_speed(row) for row in braking_rows),
        "sustained_low_speed_start_s": stop_time,
        "time_to_sustained_low_speed_after_hover_s": stop_time - hover if stop_time is not None else None,
        "braking_from_motion_demonstrated": bool(speed_at_hover is not None and speed_at_hover > config.hover_speed_mps and stop_time is not None),
        "checks": checks, "result": result,
    }


def _truth_rows(records: list[Record], entity: str) -> list[Record]:
    rows = []
    for row in records:
        if not row.topic.startswith("/ground_truth/"):
            continue
        for transform in getattr(row.message, "transforms", []):
            child = transform.child_frame_id.strip("/")
            if child == entity or child.endswith("::" + entity) or child.rsplit("/", 1)[-1] == entity:
                rows.append(Record(row.topic, stamp_s(transform.header.stamp), transform, row.received_sim_s, row.record_sequence))
    return sorted(rows, key=lambda row: row.time_s)


def evaluate_truth(records: list[Record], config: EvaluationConfig, start: float, end: float,
                   statuses: list[Record] | None = None) -> dict[str, Any]:
    targets = [row for row in _truth_rows(records, f"target_{config.target_class}") if start <= row.time_s <= end]
    vehicles = _truth_rows(records, "stage1_uav")
    vehicle_times = [row.time_s for row in vehicles]
    distance_errors, height_errors, sync_errors = [], [], []
    active_distance_errors, active_height_errors, active_sync_errors = [], [], []
    statuses = sorted(statuses or [], key=lambda row: row.time_s)
    status_times = [row.time_s for row in statuses]
    active_target_samples = 0
    mismatched_frames = 0
    for target in targets:
        status_index = bisect_right(status_times, target.time_s) - 1
        active = status_index >= 0 and int(statuses[status_index].message.lifecycle) in {2, 3}
        active_target_samples += int(active)
        vehicle = nearest(vehicles, vehicle_times, target.time_s, config.max_sync_error_s)
        if vehicle is None:
            continue
        if target.message.header.frame_id != vehicle.message.header.frame_id:
            mismatched_frames += 1
            continue
        target_position, vehicle_position = vector(target.message.transform.translation), vector(vehicle.message.transform.translation)
        if any(finite(value) is None for value in (*target_position, *vehicle_position)):
            continue
        distance_errors.append(math.hypot(target_position[0] - vehicle_position[0], target_position[1] - vehicle_position[1]) - config.desired_distance_m)
        height_errors.append(vehicle_position[2] - target_position[2] - config.desired_height_m)
        sync_errors.append(abs(target.time_s - vehicle.time_s))
        if active:
            active_distance_errors.append(distance_errors[-1])
            active_height_errors.append(height_errors[-1])
            active_sync_errors.append(sync_errors[-1])
    lifecycle_durations = occupancy(statuses, "lifecycle", LIFECYCLE_NAMES, start, end)
    return {
        "available": bool(distance_errors), "target_pose_samples": len(targets), "vehicle_pose_samples": len(vehicles),
        "matched_samples": len(distance_errors), "mismatched_parent_frames": mismatched_frames,
        "sync_error_s": summary(sync_errors),
        "horizontal_distance_error_m": summary(distance_errors), "height_above_target_origin_error_m": summary(height_errors),
        "active_tracking": {
            "available": bool(active_distance_errors),
            "scope": "Only controller FOLLOW/PREDICT; each truth sample uses the most recent status at or before its time, held until the next status/end; no future status is used",
            "active_duration_s": sum(lifecycle_durations.get(name, 0.0) for name in ("FOLLOW", "PREDICT")),
            "target_pose_samples": active_target_samples, "matched_samples": len(active_distance_errors),
            "matched_fraction_of_whole_interval": len(active_distance_errors) / len(distance_errors) if distance_errors else None,
            "horizontal_distance_error_m": summary(active_distance_errors),
            "height_above_target_origin_error_m": summary(active_height_errors),
            "sync_error_s": summary(active_sync_errors),
            "reference": "Same uncorrected Gazebo model origins and desired distances as the whole-interval metrics; RGB-D surface/model-origin offsets remain",
        },
        "scope_note": "Top-level metrics retain the entire evaluation interval including loss/HOVER; the physical target continues moving while the UAV hovers, so distance error may grow. active_tracking is a separately labelled subset and does not remove those failures",
        "reference": "Gazebo model origins for both target and UAV; height is above target model origin, not YOLO box/depth surface",
        "position_estimation_rmse_m": None,
        "position_estimation_rmse_reason": "Not evaluated: PX4 map/world transform and the target's RGB-D measurement anchor are not independently calibrated; no fitted bias correction is applied",
        "missing_truth_reason": None if distance_errors else "No time-matched target and stage1_uav truth in one parent frame; PX4 odometry is not substituted for Gazebo UAV truth",
    }


def evaluate(records: list[Record], events: list[dict[str, Any]], config: EvaluationConfig,
             input_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    records = sorted(with_record_sequence(records), key=lambda row: row.time_s)
    if not records:
        raise ValueError("No readable evaluation messages in the bag")
    phases = [row for row in records if row.topic == "/tracking/flight_phase"]
    follow_start = next((row.time_s for row in phases if row.message.data.split(":", 1)[0].strip().upper() == "FOLLOW"), None)
    if follow_start is None:
        follow_start = next((finite(row.get("time_s")) for row in events if row.get("kind") == "phase" and row.get("phase", "").upper() == "FOLLOW"), None)
    start = config.start_s if config.start_s is not None else (follow_start if follow_start is not None else records[0].time_s)
    recorded_end = max(max(row.time_s, row.received_sim_s if row.received_sim_s is not None else row.time_s)
                       for row in records)
    end = config.end_s if config.end_s is not None else recorded_end
    if end <= start:
        raise ValueError("Evaluation interval must have positive duration")
    selected = [row for row in records if start <= row.time_s <= end]

    def topic(*names: str) -> list[Record]:
        rows = []
        for row in records:
            if row.topic not in names:
                continue
            # A measured TargetState retains camera acquisition time. Its
            # operational recovery cannot precede delivery to the controller.
            timestamp = max(row.time_s, row.received_sim_s) if row.topic == "/tracking/state" and row.received_sim_s is not None else row.time_s
            if start <= timestamp <= end:
                rows.append(Record(row.topic, timestamp, row.message, row.received_sim_s, row.record_sequence))
        return sorted(rows, key=lambda row: (row.time_s, row.record_sequence))

    states, statuses = topic("/tracking/state"), topic("/tracking/status")
    odometry = topic("/vehicle/odometry")
    observations = topic("/tracking/observations", "/observations")
    vehicle_status = topic("/fmu/out/vehicle_status_v1", "/fmu/out/vehicle_status")
    commands = topic("/tracking/command")
    diagnostics, diagnostic_errors = [], 0
    for row in topic("/tracking/detection_diagnostics"):
        try:
            data = json.loads(row.message.data)
            if data.get("class_name", config.target_class) != config.target_class:
                continue
            detections = data["detections"]
            diagnostics.append({**data, "has_candidate": bool(detections), "valid_depth": any(det.get("depth_valid", False) for det in detections)})
        except (KeyError, TypeError, ValueError):
            diagnostic_errors += 1
    diagnostics.sort(key=lambda row: row["stamp_s"])
    diagnostic_span = diagnostics[-1]["stamp_s"] - diagnostics[0]["stamp_s"] if len(diagnostics) > 1 else 0.0
    latencies = [row["completed_s"] - row["stamp_s"] for row in diagnostics]
    tracking_status = [row for row in statuses if row.message.lifecycle in {2, 3}]
    depth_count = sum(bool(row.message.depth_valid) for row in observations)
    state_counts = Counter(STATE_NAMES.get(int(row.message.state), "UNKNOWN") for row in states)
    lifecycle_counts = Counter(LIFECYCLE_NAMES.get(int(row.message.lifecycle), "UNKNOWN") for row in statuses)
    windows = [window for window in shutter_windows(events) if window["start_s"] <= end and (window["end_s"] is None or window["end_s"] >= start)]
    occlusions = [evaluate_occlusion(window, states, statuses, odometry, diagnostics, config, end,
                                    topic("/tracking/selection"),
                                    [row for row in events if row.get("kind") == "shutter_service_result"]) for window in windows]
    truth = evaluate_truth(records, config, start, end,
                           [row for row in records if row.topic == "/tracking/status"])
    limitations = [
        "Estimated following error uses the same target estimate that controls the vehicle; it is an internal consistency metric, not independent accuracy.",
        "Detector frame availability uses completed diagnostic inference frames, not all camera frames and not precision/recall or mAP.",
        "Shutter events are pose-change requests. Candidate-free detector frames corroborate image interruption; service success/video should also be inspected.",
        "A single flight is one trial. Frame counts are not independent experimental repetitions.",
    ]
    required_topics = {"/tracking/state", "/vehicle/odometry", "/tracking/status", "/tracking/detection_diagnostics"}
    missing = sorted(required_topics - {row.topic for row in selected})
    if missing:
        limitations.append("Missing required metric topics: " + ", ".join(missing))
    if follow_start is None and config.start_s is None:
        limitations.append("FOLLOW handoff time unavailable; statistics cover all readable messages, potentially including takeoff.")
    if not truth["available"]:
        limitations.append(truth["missing_truth_reason"])
    metadata = input_metadata or {}
    startup_unclocked = metadata.get("startup_unclocked_messages", {})
    if startup_unclocked:
        limitations.append("Messages preceding the first /clock were decoded but cannot be placed on the simulation timeline: "
                           + json.dumps(startup_unclocked, sort_keys=True)
                           + ". Original recorder timestamps/CDR remain in inputs.startup_unclocked_records; timed metrics exclude them.")
    clock_available = metadata.get("clock_recorded") is not False and metadata.get("clock_samples_read", 1) > 0
    if not clock_available:
        limitations.append("No readable /clock samples: unheadered messages have no simulation timebase; this trial cannot receive PASS.")
    armed_seen = any(int(row.message.arming_state) == int(getattr(row.message, "ARMING_STATE_ARMED", 2)) for row in vehicle_status)
    offboard_seen = any(int(row.message.nav_state) == int(getattr(row.message, "NAVIGATION_STATE_OFFBOARD", 14)) for row in vehicle_status)
    has_short = any(row["kind"] == "short" for row in occlusions)
    has_long = any(row["kind"] == "long" for row in occlusions)
    outcome = "FAIL" if any(row["result"] == "FAIL" for row in occlusions) else "INCOMPLETE_EVIDENCE"
    read_errors = (input_metadata or {}).get("read_errors", {})
    if occlusions and has_short and has_long and all(row["result"] == "PASS" for row in occlusions) and not missing and armed_seen and offboard_seen and not read_errors and not diagnostic_errors and clock_available:
        outcome = "PASS"
    return {
        "schema_version": 3, "evaluation_revision": EVALUATION_REVISION,
        "source": "OFFLINE_STAGE1_ROSBAG_EVALUATION", "target_class": config.target_class,
        "inputs": input_metadata or {}, "interval": {
            "start_s": start, "end_s": end, "duration_s": end - start, "follow_start_s": follow_start,
            "recorded_end_s": recorded_end, "covers_recorded_trial_end": end >= recorded_end - 1e-9,
        },
        "configuration": config.__dict__, "topic_message_counts": dict(Counter(row.topic for row in selected)),
        "flight_evidence": {"armed_seen": armed_seen if vehicle_status else None, "offboard_seen": offboard_seen if vehicle_status else None,
                            "vehicle_speed_mps": summary(_speed(row) for row in odometry),
                            "valid_command_count": sum(bool(row.message.valid) for row in commands)},
        "detector": {
            "completed_inference_frames": len(diagnostics), "invalid_diagnostic_messages": diagnostic_errors,
            "frames_with_candidate": sum(row["has_candidate"] for row in diagnostics),
            "frames_with_valid_depth": sum(row["valid_depth"] for row in diagnostics),
            "candidate_frame_fraction": sum(row["has_candidate"] for row in diagnostics) / len(diagnostics) if diagnostics else None,
            "valid_depth_frame_fraction": sum(row["valid_depth"] for row in diagnostics) / len(diagnostics) if diagnostics else None,
            "processed_fps_in_sim_time": (len(diagnostics) - 1) / diagnostic_span if diagnostic_span > 0 else None,
            "acquisition_to_completed_sim_latency_s": summary(value for value in latencies if value >= 0),
            "negative_latency_count": sum(value < 0 for value in latencies),
            "inference_wall_s": summary(row.get("inference_wall_s") for row in diagnostics),
            "rgb_depth_sync_error_s": summary(row.get("rgb_depth_sync_error_s") for row in diagnostics),
            "observation_count": len(observations), "valid_depth_observation_count": depth_count,
            "valid_depth_observation_fraction": depth_count / len(observations) if observations else None,
            "precision": None, "recall": None, "mAP": None,
            "label_metric_reason": "No annotated per-frame boxes; availability fractions must not be interpreted as detection accuracy",
        },
        "estimator": {
            "state_counts": dict(state_counts), "state_duration_s": occupancy(states, "state", STATE_NAMES, start, end),
            "published_prediction_age_s": summary(row.message.prediction_age_s for row in states),
            "measured_message_receive_lag_s": summary(row.received_sim_s - stamp_s(row.message.header.stamp) for row in states if row.message.state == 1 and row.received_sim_s is not None and row.received_sim_s >= stamp_s(row.message.header.stamp)),
            "transition_time_semantics": "TargetState transitions use max(header stamp, receive /clock), with recording sequence breaking equal-time ties. Measured states carry acquisition stamps, so recovery is never backdated before receipt; /clock sample timing remains approximate.",
            "position_rmse_m": None, "velocity_rmse_mps": None,
            "accuracy_unavailable_reason": truth["position_estimation_rmse_reason"],
        },
        "controller": {
            "lifecycle_counts": dict(lifecycle_counts), "lifecycle_duration_s": occupancy(statuses, "lifecycle", LIFECYCLE_NAMES, start, end),
            "reasons": dict(Counter(row.message.reason for row in statuses)),
            "estimated_horizontal_distance_error_m": summary(row.message.distance_error_m for row in tracking_status),
            "estimated_height_error_m": summary(row.message.height_error_m for row in tracking_status),
            "error_sample_scope": "FOLLOW and PREDICT only; HOVER/default zero errors are excluded, while their durations/failures remain above",
        },
        "ground_truth": truth, "occlusions": occlusions,
        "shutter_service_results": [row for row in events if row.get("kind") == "shutter_service_result"],
        "acceptance": {"result": outcome, "scope": "Observed flight/occlusion behavior only; no ground-truth accuracy threshold is asserted",
                       "short_occlusion_recorded": has_short, "long_occlusion_recorded": has_long,
                       "clock_timebase_available": clock_available,
                       "missing_topics": missing, "input_read_error_count": sum(read_errors.values()), "failed_events_retained": True},
        "limitations": limitations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bag", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-class", choices=["person", "car"], default="person")
    parser.add_argument("--telemetry-jsonl", type=Path)
    parser.add_argument("--monitor-summary", type=Path)
    parser.add_argument("--start-s", type=float)
    parser.add_argument("--end-s", type=float)
    parser.add_argument("--desired-distance-m", type=float, default=5.0)
    parser.add_argument("--desired-height-m", type=float, default=2.0)
    parser.add_argument("--max-prediction-s", type=float, default=0.75)
    parser.add_argument("--hover-speed-mps", type=float, default=0.30)
    parser.add_argument("--hover-sustain-s", type=float, default=0.40)
    parser.add_argument("--braking-window-s", type=float, default=2.0)
    parser.add_argument("--max-sync-error-s", type=float, default=0.10)
    args = parser.parse_args()
    config = EvaluationConfig(target_class=args.target_class, desired_distance_m=args.desired_distance_m,
                              desired_height_m=args.desired_height_m, max_prediction_s=args.max_prediction_s,
                              hover_speed_mps=args.hover_speed_mps, hover_sustain_s=args.hover_sustain_s,
                              braking_window_s=args.braking_window_s, max_sync_error_s=args.max_sync_error_s,
                              start_s=args.start_s, end_s=args.end_s)
    for name in ("max_prediction_s", "hover_speed_mps", "hover_sustain_s", "braking_window_s", "max_sync_error_s"):
        value = getattr(config, name)
        if not math.isfinite(value) or value <= 0:
            parser.error(f"{name} must be positive and finite")
    records, metadata = read_rosbag(args.bag)
    events, monitor_metadata = read_monitor_events(args.telemetry_jsonl, args.monitor_summary)
    # The summary can supply a handoff timestamp even if /flight_phase was not recorded.
    if not any(row.get("kind") == "phase" and row.get("phase", "").upper() == "FOLLOW" for row in events):
        follow_start = finite(monitor_metadata.get("follow_start_s"))
        if follow_start is not None:
            events.append({"kind": "phase", "phase": "FOLLOW", "time_s": follow_start})
    report = evaluate(records, events, config, {**metadata, **monitor_metadata})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output.resolve()), "acceptance": report["acceptance"],
                      "occlusions": [{"kind": row["kind"], "result": row["result"]} for row in report["occlusions"]]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
