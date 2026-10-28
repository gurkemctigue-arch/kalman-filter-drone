"""Independent v4 ground-footprint navigation and physical following audit.

The pure evaluate() API accepts already deserialized records. Only the CLI
reads a bag. No truth or alignment in this module feeds the online system.
The legacy visible-surface and model-origin evaluators remain unchanged.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import evaluate_stage1_flight as bag_tools
from evaluate_stage1_flight import read_monitor_events, shutter_windows, stamp_s, summary, vector
from evaluate_online_state_accuracy import (
    PoseSeries, anchor_truth, declared_enu_evidence, freeze_ego_alignment,
)
from extract_research_recording import pose_dict
from uav_tracking.research_dynamics import transient_metrics

STATE_TOPIC = "/tracking/navigation_state"
DIAGNOSTIC_TOPIC = "/tracking/navigation_diagnostics"
GRID_DT_S = .1
STREAM_TIMEOUT_S = .15
MAX_PREDICTION_S = .75
MAX_OBSERVATION_S = .60


def _finite(value):
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


def _xyz(value):
    try:
        array = np.asarray(value, dtype=float)
    except (ValueError, TypeError):
        return None
    return array if array.shape == (3,) and np.isfinite(array).all() else None


def _configuration(config):
    if config.get("control_reference") != "ground_footprint":
        raise ValueError("This evaluator requires control_reference=ground_footprint")
    for key in ("desired_distance_m", "desired_height_m"):
        value = _finite(config.get(key))
        if value is None or value <= 0:
            raise ValueError("Missing/invalid recorded controller reference: " + key)
    offset = _xyz(config.get("vehicle_control_point_offset_flu_m"))
    if offset is None:
        raise ValueError("Explicit vehicle_control_point_offset_flu_m is required; never infer it from target errors")
    if config.get("target_class") not in {"person", "car"}:
        raise ValueError("Unsupported target_class")
    if config.get("navigation_frame_id", "map") != "map":
        raise ValueError("Navigation geometry requires the recorded map frame")
    return offset


def recorded_configuration(trial, target_class):
    """Require actual runtime parameters and recorded ENU evidence, no fallback."""
    trial = Path(trial)
    config = json.loads((trial / "run_config.json").read_text(encoding="utf-8"))
    if config.get("target_class", target_class) != target_class:
        raise ValueError("Requested class contradicts run_config")
    config["target_class"] = target_class
    path = trial / "configuration/runtime_parameters.yaml"
    if not path.is_file():
        raise ValueError("Recorded runtime_parameters.yaml is required; class/source defaults are insufficient")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    controller = document["uav_tracking_controller"]["ros__parameters"]
    estimator = document["uav_tracking_state_estimator"]["ros__parameters"]
    detector = document["uav_tracking_detection"]["ros__parameters"]
    if controller.get("state_topic") != STATE_TOPIC:
        raise ValueError("Saved controller did not consume /tracking/navigation_state")
    if not estimator.get("navigation_enabled") or not detector.get("navigation_enabled"):
        raise ValueError("Recorded detector and estimator must both enable navigation")
    config["navigation_frame_id"] = estimator.get("state_frame")
    for key in ("desired_distance_m", "desired_height_m"):
        value = _finite(controller.get(key))
        if value is None or value <= 0:
            raise ValueError("Missing/invalid saved runtime reference: " + key)
        if config.get(key) is not None and not math.isclose(float(config[key]), value, abs_tol=1e-6):
            raise ValueError("run_config contradicts runtime controller reference: " + key)
        config[key] = value
    for params, key, expected in (
        (estimator, "max_observation_age_s", MAX_OBSERVATION_S),
        (estimator, "max_prediction_duration_s", MAX_PREDICTION_S),
        (controller, "prediction_timeout_s", MAX_PREDICTION_S),
    ):
        value = _finite(params.get(key))
        if value is None or not math.isclose(value, expected, abs_tol=1e-9):
            raise ValueError("Recorded original age gate must remain unchanged: " + key)
    offset = _xyz(controller.get("desired_offset_m"))
    if offset is None or np.any(np.abs(offset) > 1e-9):
        raise ValueError("Distance/height audit requires recorded desired_offset_m=[0,0,0]")
    _configuration(config)
    # Check the snapshot exists BEFORE calling the historical helper, whose
    # backwards-compatible source fallback is inappropriate for new v4 trials.
    if not list((trial / "configuration").glob("*.sdf")):
        raise ValueError("Recorded runtime world evidence is required; current source cannot establish historical axes")
    evidence = declared_enu_evidence(trial, target_class)
    if not evidence["world_selection"].startswith("RECORDED_"):
        raise ValueError("Source-fallback ENU evidence is not allowed for v4")
    config["declared_frame_evidence"] = evidence
    config["controller_reference_evidence"] = {
        "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "selection": "RECORDED_RUNTIME_PARAMETERS", "state_topic": controller["state_topic"],
    }
    return config


def _operational(record):
    return max(record.time_s, record.received_sim_s) if record.received_sim_s is not None else record.time_s


def _preceding(rows, times, timestamp, timeout=None):
    index = bisect_right(times, timestamp + 1e-9) - 1
    if index < 0 or (timeout is not None and timestamp - times[index] > timeout + 1e-9):
        return None
    return rows[index][1]


def _state_reason(message, timestamp, expected_uuid=None):
    if message is None:
        return "missing_navigation_stream"
    if int(message.state) not in (1, 2):
        return {0: "uninitialized", 3: "lost", 4: "ambiguous"}.get(int(message.state), "invalid_state")
    if message.header.frame_id != "map":
        return "unexpected_state_frame"
    if int(message.track_id) == 0 or not str(message.target_uuid):
        return "missing_task_or_track_identity"
    if expected_uuid is not None and str(message.target_uuid) != expected_uuid:
        return "requested_task_mismatch"
    age = _finite(message.prediction_age_s)
    stamp = stamp_s(message.header.stamp)
    if age is None or age < 0 or stamp > timestamp + 1e-8:
        return "invalid_state_time"
    if age + timestamp - stamp > MAX_PREDICTION_S + 1e-9:
        return "stale_navigation_measurement"
    if _xyz(vector(message.position_m)) is None or _xyz(vector(message.velocity_mps)) is None:
        return "nonfinite_state_vector"
    return None


def _metrics(rows, keys):
    return {key: summary(row.get(key) for row in rows) for key in keys}


def _valid_reference_kind(payload, target_class):
    kind = payload.get("reference_kind")
    if kind == ("car_cuboid_ground_center" if target_class == "car" else "person_ground_contact"):
        return True
    # A generic future reference must name its class explicitly; an unknown
    # or contradictory class cannot silently become ground-truth evidence.
    return kind == "ground_footprint_center" and payload.get("class_name") == target_class


def evaluation_source_provenance():
    """Actual evaluator source, separate from the flight's frozen revision."""
    script = Path(__file__).resolve()
    dependencies = [script.parent / name for name in (
        "evaluate_stage1_flight.py", "evaluate_online_state_accuracy.py", "extract_research_recording.py")]
    dependencies += [ROOT / "uav_tracking" / name for name in ("research_dynamics.py", "research_labels.py")]
    return {"script":str(script), "script_sha256":hashlib.sha256(script.read_bytes()).hexdigest(),
            "dependencies":{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in dependencies},
            "scope":"Offline evaluation source hashes; these do not replace or assert flight-frozen code hashes."}


def _transients(samples, start, end, distance, *, task=None):
    result = {}
    for reference in ("base_link", "model_origin"):
        result[reference] = {}
        for dimension, band in (("distance", max(.5, .1 * distance)), ("height", .25)):
            scoped = [{"time_s":row["time_s"],
                       "error_m":row[reference + "_" + dimension + "_error_m"]
                       if task is None or row["reference_task_uuid"] == task else None,
                       "active":row["active"] and (task is None or row["target_uuid"] == task)}
                      for row in samples]
            result[reference][dimension] = transient_metrics(scoped, start, end, band_m=band) if end > start else None
    return result


def evaluate(records, config, *, physical=None, events=None):
    """Score independent ground centers; silent streams and hover tails persist.

    ``config`` is a mapping containing recorded desired distance/height,
    target_class, control_reference, and the explicitly declared offline
    vehicle_control_point_offset_flu_m. The CLI verifies saved source evidence.
    Multi-target truth requires a REQUEST-box physical identity report; no
    nearest-actor, estimated-state, or reported-track-ID truth selection.
    """
    body_offset = _configuration(config)
    records = list(records)
    trajectories = defaultdict(list)
    odometry = []; states = []; statuses = []; selections = []; diagnostics = []
    follow = None
    malformed = Counter()
    for record in records:
        message = record.message
        operational = _operational(record)
        if record.topic == "/clock":
            # Clock is retained for the whole-record end below. It is not
            # a vehicle/target sample and cannot fill any silent state stream.
            continue
        if record.topic.startswith("/ground_truth/"):
            for transform in message.transforms:
                trajectories[transform.child_frame_id.strip("/")].append(pose_dict(transform))
        elif record.topic == "/vehicle/odometry":
            q = message.pose.pose.orientation
            if message.header.frame_id != "map" or getattr(message, "child_frame_id", None) != "base_link":
                malformed["unexpected_odometry_parent_or_child_frame"] += 1
                continue
            quaternion = np.asarray([q.x, q.y, q.z, q.w], dtype=float)
            if (_xyz(vector(message.pose.pose.position)) is None or not np.isfinite(quaternion).all()
                    or np.linalg.norm(quaternion) < 1e-9):
                malformed["nonfinite_or_degenerate_odometry_pose"] += 1
                continue
            odometry.append({"time_s":stamp_s(message.header.stamp),
                             "position_m":vector(message.pose.pose.position),
                             "quaternion_xyzw":[q.x, q.y, q.z, q.w]})
        elif record.topic == "/tracking/flight_phase" and message.data.split(":", 1)[0].strip() == "FOLLOW":
            follow = operational if follow is None else min(follow, operational)
        elif record.topic == STATE_TOPIC:
            states.append((operational, message))
        elif record.topic == "/tracking/status":
            statuses.append((operational, message))
        elif record.topic == "/tracking/selection" and message.action == 0:
            selections.append((operational, message))
        elif record.topic == DIAGNOSTIC_TOPIC:
            try:
                payload = json.loads(message.data)
                if not isinstance(payload, dict):
                    raise ValueError("Navigation diagnostic must be an object")
                # String diagnostics have no ROS header. Their output_s is
                # the publisher's simulation timestamp; latest recorded
                # /clock can lag it by one recorder sample. A later receipt
                # still wins, so this never backdates delivered evidence.
                output = _finite(payload.get("output_s"))
                diagnostics.append((max(operational, output) if output is not None else operational, payload))
            except (TypeError, ValueError):
                malformed["malformed_navigation_diagnostic"] += 1
    if follow is None or not records:
        return {"evaluation_status":"INCOMPLETE_EVIDENCE", "reason":"No recorded FOLLOW handoff"}
    end = max([_operational(row) for row in records] + [timestamp for timestamp, _ in diagnostics])
    if end <= follow:
        return {"evaluation_status":"INCOMPLETE_EVIDENCE", "reason":"No post-FOLLOW interval"}

    def series(name):
        keys = [key for key in trajectories if key == name or key.endswith("::" + name) or key.rsplit("/", 1)[-1] == name]
        if len(keys) != 1:
            return None
        # Multiple GT bridge topics may repeat exact source stamps. Identical
        # duplicates do not create extra interpolation or calibration weight.
        unique = {float(row["time_s"]): row for row in trajectories[keys[0]]}
        return PoseSeries(list(unique.values()))

    vehicle = series(config.get("vehicle_model_name", "stage1_uav"))
    multi = int(config.get("stage", 1)) == 2 or bool(config.get("multi_target", False))
    mapping = {str(uuid): task.get("initial_mapping", {}).get("physical_id")
               for uuid, task in (physical or {}).get("tasks", {}).items()}
    targets = {identity: series(identity) for identity in set(mapping.values()) if identity}
    single = None if multi else series("target_" + config["target_class"])
    for rows in (states, statuses, selections, diagnostics):
        rows.sort(key=lambda row: row[0])
    state_times = [row[0] for row in states]; status_times = [row[0] for row in statuses]
    selection_times = [row[0] for row in selections]

    def request_at(timestamp):
        request = _preceding(selections, selection_times, timestamp)
        return str(request.target_uuid) if request is not None else None

    def target_for(uuid):
        return targets.get(mapping.get(uuid)) if multi else single

    incomplete = []
    alignment = None
    if vehicle is None:
        incomplete.append("missing_or_ambiguous_independent_vehicle_truth")
    else:
        try:
            alignment = freeze_ego_alignment(sorted(odometry, key=lambda row: row["time_s"]), vehicle,
                                            body_offset, np.eye(3), calibration_duration_s=5.)
        except ValueError as exc:
            incomplete.append("ego_alignment: " + str(exc))
    if not states:
        incomplete.append("no_recorded_navigation_state")
    if not diagnostics:
        incomplete.append("no_recorded_navigation_diagnostics")
    if not multi and single is None:
        incomplete.append("missing_or_ambiguous_independent_target_truth")
    rotation = np.asarray(alignment["rotation_world_from_map"]) if alignment else None
    translation = np.asarray(alignment["translation_world_from_map_m"]) if alignment else None
    evaluation_start = max(follow, alignment["calibration_end_s"]) if alignment else follow
    if evaluation_start >= end:
        incomplete.append("no_post_calibration_navigation_interval")

    # Physical following is independent of the navigation stream. Target truth
    # is chosen by the requested task even after every navigation message stops.
    distance = float(config["desired_distance_m"]); height = float(config["desired_height_m"])
    samples = []; kf_counts = Counter(); truth_counts = Counter()
    for index in range(int(math.floor((end - follow) / GRID_DT_S + 1e-8)) + 1):
        timestamp = follow + index * GRID_DT_S
        state = _preceding(states, state_times, timestamp, STREAM_TIMEOUT_S)
        status = _preceding(statuses, status_times, timestamp, STREAM_TIMEOUT_S)
        task = request_at(timestamp)
        target = target_for(task)
        vp = vehicle.at(timestamp) if vehicle else None
        tp = target.at(timestamp) if target else None
        row = {"time_s":timestamp, "target_uuid":str(state.target_uuid) if state is not None else None,
               "reference_task_uuid":task, "expected_physical_id":mapping.get(task) if multi else "target_" + config["target_class"],
               "base_link_distance_error_m":None, "base_link_height_error_m":None,
               "model_origin_distance_error_m":None, "model_origin_height_error_m":None}
        if vp is not None and tp is not None:
            body = vp[0] + vp[1] @ body_offset
            row.update(base_link_distance_error_m=float(np.linalg.norm((tp[0] - body)[:2]) - distance),
                       base_link_height_error_m=float(body[2] - tp[0][2] - height),
                       model_origin_distance_error_m=float(np.linalg.norm((tp[0] - vp[0])[:2]) - distance),
                       model_origin_height_error_m=float(vp[0][2] - tp[0][2] - height))
        elif multi and mapping.get(task) is None:
            truth_counts["unknown_independent_requested_task"] += 1
        else:
            truth_counts["missing_bracketed_vehicle_or_target_truth"] += 1
        reason = _state_reason(state, timestamp, task if multi else None)
        row["navigation_valid"] = reason is None
        row["navigation_reason"] = reason or "valid"
        row["active"] = bool(reason is None and status is not None and int(status.lifecycle) in (2, 3)
                             and int(status.track_id) == int(state.track_id))
        if timestamp >= evaluation_start - 1e-9:
            kf_counts["scheduled_samples"] += 1
            if reason:
                kf_counts[reason] += 1
            else:
                kf_counts["valid_navigation_samples"] += 1
                if alignment is None:
                    kf_counts["missing_independent_ego_alignment"] += 1
                elif target is None:
                    kf_counts["unknown_or_missing_independent_target_truth"] += 1
                else:
                    truth = anchor_truth(target, timestamp, np.zeros(3))
                    if truth is None:
                        kf_counts["missing_bracketed_target_truth"] += 1
                    else:
                        p = rotation @ np.asarray(vector(state.position_m)) + translation
                        v = rotation @ np.asarray(vector(state.velocity_mps))
                        row["kf_position_error_m"] = float(np.linalg.norm(p - truth[0]))
                        if truth[1] is not None:
                            row["kf_velocity_error_mps"] = float(np.linalg.norm(v - truth[1]))
        samples.append(row)

    # Raw geometry is image-acquisition based. Timer diagnostics repeat the
    # previous geometry; retain the earliest publication once per task/track/
    # acquisition, not one apparent observation per timer tick.
    unique_raw = {}; duplicate_diagnostics = 0; diagnostic_reasons = Counter()
    for operational, payload in diagnostics:
        acquisition = _finite(payload.get("acquisition_s"))
        if acquisition is None:
            diagnostic_reasons["missing_acquisition_timestamp"] += 1
            continue
        if not evaluation_start - 1e-9 <= acquisition <= end + 1e-9:
            continue
        key = (str(payload.get("target_uuid", "")), str(payload.get("track_id", "")), round(acquisition, 9))
        if key in unique_raw:
            duplicate_diagnostics += 1
            continue
        unique_raw[key] = (operational, payload)
    raw_frames = []; raw_counts = Counter(); previous = {}
    for _key, (operational, payload) in sorted(unique_raw.items(), key=lambda item: item[1][1]["acquisition_s"]):
        timestamp = float(payload["acquisition_s"]); uuid = str(payload.get("target_uuid", ""))
        track = str(payload.get("track_id", "")); task = request_at(operational)
        row = {"time_s":timestamp, "received_sim_s":operational, "target_uuid":uuid,
               "track_id":payload.get("track_id"), "fusion_accepted":bool(payload.get("fusion_accepted")),
               "fusion_reason":payload.get("fusion_reason"), "reason":"valid"}
        raw_counts["unique_acquisition_opportunities"] += 1
        diagnostic_reasons["reference:" + str(payload.get("reference_reason", "missing"))] += 1
        diagnostic_reasons["fusion:" + str(payload.get("fusion_reason", "missing"))] += 1
        if not payload.get("reference_valid"):
            row["reason"] = "invalid_reference:" + str(payload.get("reference_reason", "missing"))
        elif not _valid_reference_kind(payload, config["target_class"]):
            row["reason"] = "unexpected_reference_kind"
        elif operational < timestamp - 1e-8:
            row["reason"] = "acquisition_after_receipt"
        elif operational - timestamp > MAX_OBSERVATION_S + 1e-9:
            row["reason"] = "stale_raw_measurement"
        elif not uuid or track in {"", "0", "None"}:
            row["reason"] = "missing_task_or_track_identity"
        elif multi and task != uuid:
            row["reason"] = "requested_task_mismatch"
        else:
            point = _xyz(payload.get("raw_position_world_m"))
            target = target_for(uuid)
            truth = target.at(timestamp) if target else None
            if point is None:
                row["reason"] = "nonfinite_raw_position"
            elif alignment is None:
                row["reason"] = "missing_independent_ego_alignment"
            elif truth is None:
                row["reason"] = "unknown_or_missing_bracketed_target_truth"
            else:
                aligned = rotation @ point + translation
                row["position_error_m"] = float(np.linalg.norm(aligned - truth[0]))
                key = (uuid, track)
                before = previous.get(key)
                # A secant measures the mean velocity over the SAME interval
                # on both estimate and independent truth; no zero-velocity
                # assumption and no derivative across task/track/loss gaps.
                if before is not None and 0 < timestamp - before[0] <= MAX_PREDICTION_S + 1e-9:
                    dt = timestamp - before[0]
                    row["velocity_pair_dt_s"] = dt
                    row["velocity_error_mps"] = float(np.linalg.norm((aligned - before[1]) / dt - (truth[0] - before[2]) / dt))
                previous[key] = (timestamp, aligned, truth[0])
        if row["reason"] != "valid":
            raw_counts[row["reason"]] += 1
            previous.pop((uuid, track), None)
        else:
            raw_counts["valid_reference_samples"] += 1
        raw_frames.append(row)

    # Message-level state-stamp diagnostics complement, never replace, the
    # fixed-grid primary denominator. They expose transport age separately.
    message_frames = []; message_counts = Counter()
    for operational, state in states:
        timestamp = stamp_s(state.header.stamp)
        if not evaluation_start - 1e-9 <= operational <= end + 1e-9:
            continue
        reason = _state_reason(state, operational, request_at(operational) if multi else None)
        row = {"time_s":timestamp, "received_sim_s":operational, "reason":reason or "valid",
               "target_uuid":str(state.target_uuid)}
        message_counts["recorded_messages"] += 1
        if reason:
            message_counts[reason] += 1
        elif alignment is not None:
            target = target_for(str(state.target_uuid))
            truth = anchor_truth(target, timestamp, np.zeros(3)) if target else None
            if truth:
                p = rotation @ np.asarray(vector(state.position_m)) + translation
                v = rotation @ np.asarray(vector(state.velocity_mps))
                row["position_error_m"] = float(np.linalg.norm(p - truth[0]))
                if truth[1] is not None:
                    row["velocity_error_mps"] = float(np.linalg.norm(v - truth[1]))
                row["delivery_age_s"] = operational - timestamp
            else:
                message_counts["unknown_or_missing_bracketed_target_truth"] += 1
        message_frames.append(row)

    shutters = shutter_windows(events or [])
    first_end = min([end] + [window["start_s"] for window in shutters if window["start_s"] > follow]
                    + [timestamp for timestamp, _ in selections if timestamp > follow])
    windows = [{"kind":"initial_follow_before_first_shutter", "start_s":follow, "end_s":first_end}]
    requests = [(timestamp, request) for timestamp, request in selections if timestamp >= follow]
    for index, (timestamp, request) in enumerate(requests):
        stop = requests[index + 1][0] if index + 1 < len(requests) else end
        uuid = str(request.target_uuid)
        confirm = next((received for received, state in states if timestamp <= received <= stop
                        and str(state.target_uuid) == uuid and int(state.state) == 1
                        and _state_reason(state, received, uuid) is None), None)
        windows.append({"kind":"explicit_selection", "target_uuid":uuid, "start_s":timestamp, "end_s":stop,
                        "first_measured_confirmation_after_request_s":confirm - timestamp if confirm is not None else None,
                        "confirmation_censored":confirm is None})
    for window in windows:
        window.update(_transients(samples, window["start_s"], window["end_s"], distance,
                                  task=window.get("target_uuid")))
    keys = [reference + "_" + dimension + "_error_m" for reference in ("base_link", "model_origin")
            for dimension in ("distance", "height")]
    kf = _metrics(samples, ("kf_position_error_m", "kf_velocity_error_mps"))
    total = kf_counts["scheduled_samples"]
    raw_total = raw_counts["unique_acquisition_opportunities"]
    return {
        "schema_version":1,
        "evaluation_status":"INCOMPLETE_EVIDENCE" if incomplete else "RECORDED_WITH_CENSORED_FAILURES",
        "incomplete_reasons":incomplete,
        "interval":{"start_s":follow, "end_s":end, "navigation_evaluation_start_s":evaluation_start,
                    "sample_period_s":GRID_DT_S},
        "reference":{"kind":"ground_footprint_center", "target_truth":"Independent target model origin on ground",
                     "controlled_vehicle_point":"base_link", "vehicle_control_point_offset_flu_m":body_offset.tolist(),
                     "offset_scope":"Explicit declared vehicle geometry applied to offline GT only; never target-derived or runtime compensation",
                     "desired_horizontal_distance_m":distance, "desired_height_m":height,
                     "recorded_parameters":config.get("controller_reference_evidence"),
                     "declared_frame_evidence":config.get("declared_frame_evidence"),
                     "multi_target_mapping":"Independent REQUEST-box physical identity report; unknown tasks remain unscored" if multi else "Unique target model"},
        "ego_alignment":alignment,
        "raw_navigation":{"counts":dict(raw_counts),
                          "invalid_reason_counts":{key:value for key, value in raw_counts.items()
                                                   if key not in {"unique_acquisition_opportunities", "valid_reference_samples"}},
                          "diagnostic_reason_counts":dict(diagnostic_reasons),
                          "deduplicated_timer_repeats":duplicate_diagnostics,
                          "valid_reference_coverage":raw_counts["valid_reference_samples"] / raw_total if raw_total else None,
                          "metrics":_metrics(raw_frames, ("position_error_m", "velocity_error_mps", "velocity_pair_dt_s"))},
        "kf_navigation":{"counts":dict(kf_counts), "metrics":kf,
                         "valid_state_coverage":kf_counts["valid_navigation_samples"] / total if total else None,
                         "position_truth_coverage":kf["kf_position_error_m"]["count"] / total if total else None,
                         "velocity_truth_coverage":kf["kf_velocity_error_mps"]["count"] / total if total else None,
                         "message_level":{"counts":dict(message_counts),
                                          "metrics":_metrics(message_frames, ("position_error_m", "velocity_error_mps", "delivery_age_s"))}},
        "whole_interval":{"scheduled_samples":len(samples),
                          "matched_truth_samples":sum(row["base_link_distance_error_m"] is not None for row in samples),
                          "inactive_control_samples":sum(not row["active"] for row in samples),
                          "truth_missing_reasons":dict(truth_counts), "metrics":_metrics(samples, keys),
                          "transients":_transients(samples, follow, end, distance)},
        "windows":windows, "malformed_input_counts":dict(malformed),
        "frames":samples, "raw_frames":raw_frames, "message_frames":message_frames,
        "claim_boundary":(
            "No target truth fits navigation, its dimensions, heading, alignment, or controller. Primary map-to-GT alignment is "
            "independently frozen on vehicle-only first 5 s with declared identical ENU axes and separate ego holdout. "
            "Raw accuracy is deduplicated observed acquisition coverage, not image/stream availability; its velocity compares "
            "same-interval secants, not instantaneous KF derivatives. Primary KF coverage is fixed 10 Hz from the later of "
            "FOLLOW/calibration end through full recording end. It compares the received carried state directly with current "
            "GT, without ideal extrapolation to hide transport age. Navigation validity and active control are separate. "
            "Independent physical follow errors retain all long-loss/hover tails even if the state stream stops. "
            "Both base_link and original model-origin metrics are reported; historical evaluators/results are not changed. "
            "Distance band is max(0.5 m,10% requested distance), height band 0.25 m, final active dwell >=3 s; "
            "missing truth, stale data, ambiguous identity and inactive control censor settling. This is a moving-task "
            "transient audit, not a stationary step response or flight-safety certification."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial", type=Path)
    parser.add_argument("--target-class", choices=("person", "car"), required=True)
    parser.add_argument("--physical-identity-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    config = recorded_configuration(args.trial, args.target_class)
    physical = json.loads(args.physical_identity_report.read_text(encoding="utf-8")) if args.physical_identity_report else None
    previous_topics = bag_tools.TOPICS
    try:
        bag_tools.TOPICS = tuple(dict.fromkeys(previous_topics + (STATE_TOPIC, DIAGNOSTIC_TOPIC)))
        records, metadata = bag_tools.read_rosbag(args.trial / "rosbag", preserve_clock=True)
    finally:
        bag_tools.TOPICS = previous_topics
    events, _ = read_monitor_events(args.trial / "telemetry.jsonl", args.trial / "summary.json")
    result = evaluate(records, config, physical=physical, events=events)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sidecars = {}
    for name in ("frames", "raw_frames", "message_frames"):
        rows = result.pop(name, [])
        path = args.output.with_suffix("." + name + ".jsonl")
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, allow_nan=False) + "\n")
        sidecars[name] = str(path)
    result.update(trial=str(args.trial), bag=metadata, sidecars=sidecars,
                  evaluation_source=evaluation_source_provenance(),
                  physical_identity_sha256=hashlib.sha256(args.physical_identity_report.read_bytes()).hexdigest()
                  if args.physical_identity_report else None)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status":result["evaluation_status"], "output":str(args.output)}))
    return 0 if result["evaluation_status"] == "RECORDED_WITH_CENSORED_FAILURES" else 2


if __name__ == "__main__":
    raise SystemExit(main())
