"""Causal, array-only v4 estimator comparison; no ROS, bags or truth in gating.

Registration and recording-export provenance are separate from numerical replay.
Computed metrics never change a flight verdict or certify online equivalence.

Normalized trial schema (schema_version=1):
  interval: follow_start_s, alignment_end_s, recorded_clock_end_s
  measurements: acquisition_id, source_s, available_s, record_sequence,
    target_uuid, track_id, reference_valid, reference_reason,
    position_world_m[3], R_geometry_world_m2[3,3], R_pose_world_m2[3,3]
  task_events: source_s, available_s, record_sequence, action=bind|state|clear;
    bind/state also name target_uuid/track_id and their actual visual state
  output_events: source_s (publication), state_source_s (actual state header),
    available_s (delivery), record_sequence
  truth_samples: time_s, independently mapped target_uuid, position_world_m,
    velocity_world_mps; nullable truth and missing rows remain unscored
All events retain original record order for equal timestamps. Measurements use
estimator processing availability; outputs use their separate recorder delivery.
No exporter, clock reconstruction or alignment fitting is implemented here.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from numbers import Real
from typing import Any

import numpy as np

from .core.kalman import ConstantVelocityKalman3D

METHODS = ("raw", "ema", "fixed_kf", "geometry_adaptive_kf")
CLASSES = ("person", "car")
SEEDS = tuple(range(1000, 1010))
SOURCE_FILES = ("uav_tracking/replay_comparison.py", "uav_tracking/core/kalman.py",
                "uav_tracking/core/models.py", "scripts/run_estimator_replay_v4.py")
EXPORT_SOURCE_FILES = (
    "scripts/export_estimator_replay_v4.py", "scripts/evaluate_stage1_flight.py",
    "scripts/run_estimator_replay_v4.py", "uav_tracking/replay_comparison.py", "scripts/evaluate_navigation_reference.py",
    "scripts/evaluate_online_state_accuracy.py", "scripts/extract_research_recording.py",
    "uav_tracking/replay_export.py", "uav_tracking/navigation_reproduction.py",
    "uav_tracking/core/uncertainty.py", "uav_tracking/research_labels.py",
    "ros2_ws/src/uav_tracking_interfaces/msg/TargetState.msg",
    "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/navigation_estimator.py",
    "uav_tracking/core/kalman.py", "uav_tracking/core/models.py")
EXPORT_EVIDENCE_KIND = "FILE_HASH_SOURCE_BOUND_EXPORT_AND_ONLINE_AUDIT"
DEVELOPMENT_EXPORT_EVIDENCE_KIND = "DEVELOPMENT_ONLY_FILE_HASH_SOURCE_BOUND_EXPORT_AND_ONLINE_AUDIT"
ONLINE_FLIGHT_SOURCE_FILES = ("ros2_ws/src/uav_tracking_interfaces/msg/TargetState.msg",
    "ros2_ws/src/uav_tracking_nodes/uav_tracking_nodes/navigation_estimator.py",
    "uav_tracking/core/kalman.py", "uav_tracking/core/models.py")
EXPORT_SIDECARS = {"online_equivalence.json":"online_equivalence_audit_sha256",
                   "native_state_audit.json":"native_state_audit_sha256",
                   "truth_alignment.json":"truth_alignment_evidence_sha256"}
PAYLOAD_EXCLUDED_FIELDS = ("export_audit", *EXPORT_SIDECARS.values())
VERIFIED_REPLAY_STATUS = "COMPUTED_WITH_VERIFIED_EXPORT_AND_ONLINE_EQUIVALENCE"
LIMITS = {"target_observation_age": .6, "prediction_age": .75,
          "vehicle_odometry_age": .5, "vehicle_future_tolerance": .05}
STUDY = "CONDITIONAL_SAME_MEASUREMENT_STATE_ESTIMATOR_COMPARISON"


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def configuration_digest(config: dict) -> str:
    copy = deepcopy(config)
    copy.get("registration", {}).pop("configuration_sha256", None)
    return canonical_sha256(copy)


def replay_payload_sha256(trial: dict) -> str:
    """Bind every exported input, excluding only the circular audit links."""
    return canonical_sha256({key:value for key,value in trial.items() if key not in PAYLOAD_EXCLUDED_FIELDS})


def scheduled_slots() -> list[str]:
    return [f"{cls}_stage1_velocity_seed{seed}" for cls in CLASSES for seed in SEEDS]


def _number(value, name, *, minimum=None, maximum=None):
    if (not isinstance(value, Real) or isinstance(value, (bool, np.bool_)) or not math.isfinite(float(value))
            or minimum is not None and value < minimum or maximum is not None and value > maximum):
        raise ValueError("Invalid finite numeric field: " + name)
    return float(value)


def _array(value, shape, name, *, covariance=False, positive=False):
    def has_boolean(item):
        if isinstance(item, (bool, np.bool_)):return True
        if isinstance(item, (list, tuple, np.ndarray)):return any(has_boolean(element) for element in item)
        return False
    result = np.asarray(value)
    if has_boolean(value) or result.shape != shape or result.dtype.kind not in "iuf" or not np.isfinite(result).all():
        raise ValueError("Invalid finite array: " + name)
    result = result.astype(float)
    if covariance and (not np.allclose(result, result.T, rtol=0., atol=1e-10)
                       or np.linalg.eigvalsh(result).min() < (-1e-10 if not positive else 1e-12)):
        raise ValueError("Invalid covariance: " + name)
    return result


def _hash(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Missing SHA256 binding: " + name)
    return value


def _hash_map(value, name):
    if not isinstance(value, dict) or not value or any(not isinstance(k, str) or not k for k in value):
        raise ValueError("Missing source/artifact hash map: " + name)
    for key, digest in value.items():
        _hash(digest, name + ":" + key)
    return value


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("A timezone-aware UTC registration/flight time is required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Invalid registration/flight UTC time") from error
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ValueError("Registration/flight times must explicitly use UTC")
    return result.astimezone(timezone.utc)


def validate_registered_config(config: dict) -> dict:
    """Resolve required parameters only; DRAFT cannot start a held-out replay."""
    if (type(config.get("schema_version")) is not int or config["schema_version"] != 1 or config.get("study_kind") != STUDY
            or config.get("status") != "REGISTERED"):
        raise ValueError("Replay requires a prospectively REGISTERED configuration; DRAFT supports plan/inventory only")
    registration = config["registration"]
    registered = _utc(registration["registered_utc"])
    if _hash(registration["configuration_sha256"], "configuration") != configuration_digest(config):
        raise ValueError("Registered configuration digest changed")
    sampling = config["sampling"]
    if set(config["methods"]) != set(METHODS):
        raise ValueError("Only the four preregistered methods are implemented")
    if (sampling["slot_ids"] != scheduled_slots() or sampling["classes"] != list(CLASSES)
            or sampling["group"] != "stage1_velocity" or sampling["seeds"] != list(SEEDS)
            or sampling["scheduled_recordings"] != 20 or sampling["scheduled_recordings_per_class"] != 10
            or sampling["methods_per_recording"] != 4):
        raise ValueError("Replay must retain the complete prospectively named 20-slot matrix")
    freeze = config["freeze_requirements"]
    if freeze["must_freeze_before_first_selected_formal_flight"] is not True:
        raise ValueError("Replay parameters must be frozen before the selected formal flights")
    for key in ("final_engineering_plan_file_sha256", "final_engineering_plan_digest"):
        _hash(freeze[key], key)
    for key in ("flight_source_hashes", "model_hashes", "runtime_and_magnetic_bindings",
                "offline_replay_source_hashes", "evaluation_source_hashes"):
        _hash_map(freeze[key], key)
    if set(SOURCE_FILES) - set(freeze["offline_replay_source_hashes"]):
        raise ValueError("Replay implementation and KF helper provenance must be frozen")
    evidence = freeze["development_calibration_evidence"]
    if evidence.get("scope") != "DEVELOPMENT_ONLY":
        raise ValueError("Estimator parameters require DEVELOPMENT_ONLY calibration provenance")
    _hash_map(evidence["artifact_hashes"], "development calibration")
    calibration = config["calibration"]
    if (calibration["status"] != "REGISTERED"
            or calibration["held_out_formal_data_for_parameter_selection_forbidden"] is not True):
        raise ValueError("All estimator parameters must be registered from development data")
    if freeze["registered_estimator_parameters"] != {"sha256":canonical_sha256(calibration)}:
        raise ValueError("Estimator parameter binding differs from registration")
    r0 = {cls:_array(calibration["R0_sensor_world_m2_by_class"][cls], (3, 3), "R0 " + cls,
                    covariance=True, positive=True) for cls in CLASSES}
    q = calibration["Q_model_and_parameters"]
    if q["model"] != "piecewise_constant_acceleration":
        raise ValueError("Only the explicitly declared piecewise-constant-acceleration Q is implemented")
    acceleration = _number(q["acceleration_std_mps2"], "Q acceleration std", minimum=1e-12)
    initial = calibration["P0_matrix_and_initial_velocity_policy"]
    p0 = _array(initial["covariance_6x6"], (6, 6), "P0", covariance=True, positive=True)
    if initial["velocity_policy"] != "registered_constant":
        raise ValueError("Only a registered common constant initial velocity is implemented")
    velocity = _array(initial["initial_velocity_mps"], (3,), "initial velocity")
    alpha = _number(calibration["ema_alpha"], "EMA alpha", minimum=1e-12, maximum=1.)
    gate = calibration["common_gate_R_and_initialization_policy"]
    if gate != {"measurement_covariance":"geometry_plus_pose", "initialization":"common_P0", "threshold_squared":9.21}:
        raise ValueError("Common causal gate must use declared geometry+pose R, common P0 and unchanged 9.21 threshold")
    coverage = _number(calibration["common_support_truth_coverage_requirement"], "common support requirement", minimum=0., maximum=1.)
    contract = config["common_replay_contract"]
    if contract["original_limits_s"] != LIMITS or contract["mahalanobis_gate_squared"] != 9.21:
        raise ValueError("Original freshness and innovation limits cannot be relaxed")
    statistics = config["statistics"]
    ci = statistics["confidence_interval"]
    if ci["confidence_level"] != .95 or type(ci["resamples"]) is not int or ci["resamples"] != 10000:
        raise ValueError("The preregistered 95%/10000 trial-block bootstrap is required")
    if type(ci["rng_seed"]) is not int or ci["rng_seed"] != 20261029:
        raise ValueError("The preregistered bootstrap RNG seed differs")
    return {"registered_utc":registered, "r0":r0, "acceleration":acceleration, "p0":p0,
            "initial_velocity":velocity, "alpha":alpha, "minimum_common_coverage":coverage}


def _identity(row):
    uuid, track = row.get("target_uuid"), row.get("track_id")
    if not isinstance(uuid, str) or not uuid or type(track) is not int or track < 0:
        raise ValueError("Explicit nonempty task UUID and integer track ID are required")
    return uuid, track


def _event(row, kind):
    source = _number(row["source_s"], kind + " source", minimum=0.)
    available = _number(row["available_s"], kind + " availability", minimum=source)
    sequence = row["record_sequence"]
    if type(sequence) is not int or sequence < 0:
        raise ValueError("Original nonnegative record_sequence is required")
    return source, available, sequence


def validate_trial_binding(trial: dict, config: dict, parameters: dict) -> None:
    cls, seed = trial["target_class"], trial["seed"]
    if (trial.get("schema_version") != 1 or cls not in CLASSES or type(seed) is not int or seed not in SEEDS
            or trial["slot_id"] != f"{cls}_stage1_velocity_seed{seed}" or trial["group"] != "stage1_velocity"):
        raise ValueError("Input is not one of the twenty preregistered trial slots")
    if _utc(trial["flight_started_utc"]) <= parameters["registered_utc"]:
        raise ValueError("Estimator registration must precede this held-out flight")
    binding = trial["bindings"]
    for key in ("final_engineering_plan_digest", "flight_source_hashes", "model_hashes", "runtime_and_magnetic_bindings"):
        if binding[key] != config["freeze_requirements"][key]:
            raise ValueError("Input does not match the frozen final flight revision: " + key)
    _hash_map(binding["recording_artifact_hashes"], "recording artifacts")
    _hash(binding["immutable_slot_record_sha256"], "terminal slot record")
    if trial["engineering_status"] not in {"PASS", "FAIL", "INTERRUPTED", "INCOMPLETE_EVIDENCE", "INFRASTRUCTURE_ERROR", "EVALUATION_PENDING"}:
        raise ValueError("Preserved engineering terminal status is required")


def _new_filter(parameters):
    return ConstantVelocityKalman3D(process_acceleration_std=parameters["acceleration"],
        measurement_noise_std=1., initial_velocity_covariance=1., initial_position_covariance=1.,
        adaptive_measurement_noise=False, gate_threshold=9.21, default_dt=.1)


def replay_states(measurements: list[dict], task_events: list[dict], output_events: list[dict],
                  interval: dict, parameters: dict, target_class: str) -> dict:
    """Generate delivered states from sensor/lifecycle arrays; there is no GT argument.

    measurement.available_s is estimator processing availability, not bag write
    time. output.source_s is publication; state_source_s is its actual header /
    projection time and available_s is delivery. A schema2 diagnostic cycle may
    share its original bag sequence across task/measurement/output kinds; only
    inside that same cycle is task -> measurement -> output causal ordering used.
    Scoring never extrapolates a carried output again.
    """
    start = max(_number(interval["follow_start_s"], "FOLLOW", minimum=0.),
                _number(interval["alignment_end_s"], "alignment end", minimum=0.))
    end = _number(interval["recorded_clock_end_s"], "full clock end", minimum=start)
    if end <= start:raise ValueError("A positive full recorded post-FOLLOW interval is required")
    events, sequences = [], set()
    suborder = {"task":0, "measurement":1, "output":2}
    for kind, rows in (("measurement", measurements), ("task", task_events), ("output", output_events)):
        if not isinstance(rows, list):
            raise ValueError("Replay inputs must be explicit arrays")
        for row in rows:
            source, available, seq = _event(row, kind)
            if (kind,seq) in sequences:
                raise ValueError("Each kind/record_sequence must be unique; cross-kind compound cycles may share the actual bag sequence")
            sequences.add((kind,seq))
            if source > end + 1e-9 or available > end + 1e-9:
                raise ValueError("An event exceeds the preserved full recorded clock end")
            if kind == "output":
                _number(row["state_source_s"], "output state header", minimum=0., maximum=source)
            events.append((source if kind == "output" else available, seq, suborder[kind], kind, row))
    events.sort(key=lambda value:(value[0], value[1], value[2]))
    filters = {method:_new_filter(parameters) for method in ("fixed_kf", "geometry_adaptive_kf")}
    gate = _new_filter(parameters)
    identity, state = None, "lost"
    closed_task_uuids = set()
    last_source = None
    positions, velocities = {}, {}
    seen_acquisitions = set()
    audit, deliveries, lifecycle = [], [], []

    def reset():
        nonlocal last_source
        gate.reset()
        for instance in filters.values():instance.reset()
        positions.clear(); velocities.clear(); last_source = None

    for _, sequence, _, kind, row in events:
        source, available, _ = _event(row, kind)
        if kind == "task":
            action = row["action"]
            if action == "clear":
                if identity is not None:closed_task_uuids.add(identity[0])
                identity, state = None, "lost"; reset()
            elif action == "bind":
                key = _identity(row)
                bound_state = row["state"]
                if bound_state not in {"tracking", "coasting", "reacquired", "ambiguous", "lost"}:
                    raise ValueError("Binding must explicitly preserve the current visual lifecycle state")
                if key[0] in closed_task_uuids:
                    raise ValueError("A lost/cleared task requires a new explicit task UUID")
                if identity is not None and key[0] != identity[0]:closed_task_uuids.add(identity[0])
                if key != identity:reset()
                identity, state = key, bound_state
                if state == "lost":closed_task_uuids.add(identity[0]); reset()
            elif action == "state":
                if _identity(row) != identity:
                    raise ValueError("Lifecycle event does not belong to the bound task")
                requested = row["state"]
                if requested not in {"tracking", "coasting", "reacquired", "ambiguous", "lost"}:
                    raise ValueError("Unknown visual lifecycle state")
                if identity[0] in closed_task_uuids and requested != "lost":
                    raise ValueError("Lifecycle cannot revive a lost UUID without reselection")
                state = requested
                if state == "lost":closed_task_uuids.add(identity[0]); reset()
            else:
                raise ValueError("Unsupported task action")
            lifecycle.append({"time_s":available, "record_sequence":sequence,
                              "identity":identity, "state":state})
        elif kind == "measurement":
            # Preselection / empty frames are real opportunities. They carry
            # no selected identity and must not force an invented task UUID.
            key = None if row.get("target_uuid") in {None, ""} else _identity(row)
            acquisition = row["acquisition_id"]
            if not isinstance(acquisition, str) or not acquisition:
                raise ValueError("An explicit acquisition_id is required even for empty/invalid frames")
            unique = (key, acquisition)
            if unique in seen_acquisitions:
                audit.append({"acquisition_id":acquisition,"accepted":False,"reason":"duplicate_acquisition"});continue
            seen_acquisitions.add(unique)
            reason, distance = None, None
            if key is None or key != identity:reason = "not_selected_task"
            elif state not in {"tracking", "coasting", "reacquired"}:reason = "visual_" + state
            elif available - source > .6 + 1e-9:reason = "stale_observation"
            elif last_source is not None and source <= last_source:reason = "nonmonotonic_acquisition"
            elif type(row.get("reference_valid")) is not bool:
                raise ValueError("reference_valid must be an explicit boolean")
            elif not row["reference_valid"]:reason = "invalid_reference:" + str(row.get("reference_reason", "unspecified"))
            if reason is not None:
                audit.append({"acquisition_id":acquisition,"source_s":source,"available_s":available,
                              "accepted":False,"reason":reason});continue
            position = _array(row["position_world_m"], (3,), "navigation measurement")
            geometry = _array(row["R_geometry_world_m2"], (3, 3), "geometry R", covariance=True)
            pose = _array(row["R_pose_world_m2"], (3, 3), "pose R", covariance=True)
            adaptive_r = geometry + pose
            fixed_r = parameters["r0"][target_class] + pose
            candidate = deepcopy(gate)
            if candidate.initialized:
                accepted = candidate.update(position, timestamp=source, measurement_covariance=adaptive_r)
                distance = candidate.last_mahalanobis_distance
            else:
                candidate.initialize(position, velocity=parameters["initial_velocity"], timestamp=source, covariance=parameters["p0"])
                accepted = True
            if not accepted:
                audit.append({"acquisition_id":acquisition,"source_s":source,"available_s":available,
                              "accepted":False,"reason":"common_mahalanobis_gate","mahalanobis_squared":distance});continue
            previous_source = last_source
            previous_positions = {method:value.copy() for method,value in positions.items()}
            gate = candidate
            for method, covariance in (("fixed_kf", fixed_r), ("geometry_adaptive_kf", adaptive_r)):
                instance = filters[method]
                if not instance.initialized:
                    instance.initialize(position, velocity=parameters["initial_velocity"], timestamp=source, covariance=parameters["p0"])
                else:
                    # The independent shadow gate is the ONLY acceptance gate.
                    instance.update(position, timestamp=source, measurement_covariance=covariance, gate_threshold=1e300)
            positions["raw"] = position.copy()
            positions["ema"] = (position.copy() if "ema" not in previous_positions else
                                parameters["alpha"] * position + (1. - parameters["alpha"]) * previous_positions["ema"])
            for method in ("raw", "ema"):
                dt = None if previous_source is None else source - previous_source
                velocities[method] = ((positions[method] - previous_positions[method]) / dt
                    if dt is not None and 0. < dt <= .75 + 1e-9 else parameters["initial_velocity"].copy())
            last_source = source
            audit.append({"acquisition_id":acquisition,"source_s":source,"available_s":available,
                          "accepted":True,"reason":"initialized" if previous_source is None else "accepted",
                          "mahalanobis_squared":distance,"R_geometry_world_m2":geometry.tolist(),
                          "R_pose_world_m2":pose.tolist(),"R_fixed_world_m2":fixed_r.tolist(),"R_adaptive_world_m2":adaptive_r.tolist()})
        else:
            state_source = row["state_source_s"]
            age = None if last_source is None else state_source - last_source
            valid = bool(identity is not None and state in {"tracking", "coasting", "reacquired"}
                         and age is not None and 0. <= age <= .75 + 1e-9
                         and source-last_source <= .75 + 1e-9)
            outputs = {}
            for method in METHODS:
                position = velocity = None
                if valid:
                    if method in filters:
                        estimate = filters[method].project(state_source)
                        position, velocity = estimate.position, estimate.velocity
                    else:position, velocity = positions[method], velocities[method]
                outputs[method] = {"valid":valid,"position_world_m":None if position is None else position.tolist(),
                                   "velocity_world_mps":None if velocity is None else velocity.tolist()}
            deliveries.append({"source_s":source,"state_source_s":state_source,"available_s":available,"record_sequence":sequence,
                               "identity":identity,"measured_source_s":last_source,"methods":outputs})
    deliveries.sort(key=lambda row:(row["available_s"],row["record_sequence"]))
    lifecycle.sort(key=lambda row:(row["time_s"],row["record_sequence"]))
    frames, delivered, active = [], None, None
    di = li = 0
    for index in range(int(math.floor((end-start)/.1 + 1e-8)) + 1):
        time = start + index*.1
        while di < len(deliveries) and deliveries[di]["available_s"] <= time + 1e-9:
            delivered = deliveries[di];di += 1
        while li < len(lifecycle) and lifecycle[li]["time_s"] <= time + 1e-9:
            active = lifecycle[li];li += 1
        methods = {}
        if delivered is None:reason = "no_delivered_output"
        elif active is None or active["identity"] is None:reason = "no_bound_task"
        elif delivered["identity"] != active["identity"]:reason = "task_identity_mismatch"
        elif active["state"] not in {"tracking","coasting","reacquired"}:reason = "visual_" + active["state"]
        elif time-delivered["available_s"] > .15 + 1e-9:reason = "output_stream_silent"
        elif delivered["measured_source_s"] is None:reason = "navigation_uninitialized"
        elif not 0. <= time-delivered["measured_source_s"] <= .75 + 1e-9:reason = "prediction_expired"
        elif not all(output["valid"] for output in delivered["methods"].values()):reason = "carried_output_invalid"
        else:reason = "valid"
        for method in METHODS:
            valid = bool(delivered and active and delivered["identity"] == active["identity"]
                and active["state"] in {"tracking","coasting","reacquired"}
                and time - delivered["available_s"] <= .15 + 1e-9
                and delivered["measured_source_s"] is not None
                and 0. <= time-delivered["measured_source_s"] <= .75 + 1e-9
                and delivered["methods"][method]["valid"])
            methods[method] = ({**delivered["methods"][method], "valid":True} if valid else
                {"valid":False,"position_world_m":None,"velocity_world_mps":None})
        frames.append({"time_s":time,"target_uuid":active["identity"][0] if active and active["identity"] else None,
            "delivered_output_source_s":delivered["state_source_s"] if delivered else None,
            "delivered_output_publication_s":delivered["source_s"] if delivered else None,
            "validity_reason":reason,"methods":methods})
    return {"interval":{"start_s":start,"end_s":end,"sample_period_s":.1},"frames":frames,
            "measurement_audit":audit,"measurement_counts":dict(Counter(row["reason"] for row in audit)),
            "recorded_output_opportunities":len(output_events)}


def score_states(replay: dict, truth_samples: list[dict]) -> dict:
    """Score only; truth has no path back to replay_states or its common gate."""
    truth = {}
    for row in truth_samples:
        time = _number(row["time_s"], "truth time", minimum=0.)
        key = round(time, 8)
        if key in truth:raise ValueError("Duplicate truth-grid sample")
        if not isinstance(row.get("target_uuid"), str):raise ValueError("Truth must explicitly name its independently mapped task")
        truth[key] = row
    errors = {method:{"position":[],"velocity":[],"short_occlusion":[],"valid":0} for method in METHODS}
    total, common_position, common_velocity = len(replay["frames"]), 0, 0
    for frame in replay["frames"]:
        row = truth.get(round(frame["time_s"],8))
        position = velocity = None
        if row is not None and row["target_uuid"] == frame["target_uuid"]:
            if row.get("position_world_m") is not None:position = _array(row["position_world_m"],(3,),"truth position")
            if row.get("velocity_world_mps") is not None:velocity = _array(row["velocity_world_mps"],(3,),"truth velocity")
        all_valid = all(frame["methods"][method]["valid"] for method in METHODS)
        common_position += bool(all_valid and position is not None)
        common_velocity += bool(all_valid and velocity is not None)
        for method in METHODS:
            state, result = frame["methods"][method], errors[method]
            result["valid"] += state["valid"]
            if all_valid and position is not None:
                error = float(np.linalg.norm(np.asarray(state["position_world_m"]) - position))
                result["position"].append(error)
                if row.get("short_occlusion") is True:result["short_occlusion"].append(error)
            if all_valid and velocity is not None:
                result["velocity"].append(float(np.linalg.norm(np.asarray(state["velocity_world_mps"]) - velocity)))

    def rmse(values):return float(np.sqrt(np.mean(np.square(values)))) if values else None
    return {"scheduled_samples":total,"common_position_samples":common_position,"common_velocity_samples":common_velocity,
        "common_position_truth_coverage":common_position / total if total else None,
        "methods":{method:{"position_rmse_m":rmse(row["position"]),"velocity_rmse_mps":rmse(row["velocity"]),
            "position_p95_m":float(np.percentile(row["position"],95)) if row["position"] else None,
            "short_occlusion_position_rmse_m":rmse(row["short_occlusion"]),
            "short_occlusion_samples":len(row["short_occlusion"]),"valid_samples":row["valid"],
            "valid_state_coverage":row["valid"] / total if total else None,
            "position_truth_coverage":len(row["position"]) / total if total else None,
            "velocity_truth_coverage":len(row["velocity"]) / total if total else None} for method,row in errors.items()}}


def export_evidence_issues(trial: dict, config: dict, evidence: dict | None) -> list[str]:
    """Check the CLI's file-verified receipt without performing file I/O.

    The file-opening verifier owns authenticity of its receipt. A bare PASS or
    boolean cannot upgrade a pure calculation; all hashes/counts bind this
    exact trial and registration. This receipt never controls filter updates.
    """
    try:
        if not isinstance(evidence, dict) or evidence.get("schema_version") != 1 or evidence.get("kind") != EXPORT_EVIDENCE_KIND:
            raise ValueError("Missing structured file/source-verified export receipt")
        if evidence.get("evidence_sha256") != canonical_sha256({k:v for k,v in evidence.items() if k != "evidence_sha256"}):
            raise ValueError("Export verification receipt digest changed")
        if (evidence.get("trial_input_sha256") != canonical_sha256(trial)
                or evidence.get("configuration_sha256") != configuration_digest(config)):
            raise ValueError("Export receipt belongs to another trial/registration")
        if evidence.get("replay_payload_sha256") != replay_payload_sha256(trial):
            raise ValueError("Export receipt does not bind the exact replay/scoring payload")
        expected_sidecars = {name:_hash(trial.get(field), field) for name,field in EXPORT_SIDECARS.items()}
        if evidence.get("sidecar_sha256") != expected_sidecars:
            raise ValueError("Export receipt sidecar bindings differ")
        expected_sources = {name:config["freeze_requirements"]["evaluation_source_hashes"][name] for name in EXPORT_SOURCE_FILES}
        if evidence.get("export_source_hashes") != expected_sources:
            raise ValueError("Export receipt evaluator/helper/message sources differ")
        for name in set(SOURCE_FILES) & set(EXPORT_SOURCE_FILES):
            if expected_sources[name] != config["freeze_requirements"]["offline_replay_source_hashes"][name]:
                raise ValueError("Overlapping export/replay source registrations disagree")
        if any(expected_sources[name] != config["freeze_requirements"]["flight_source_hashes"].get(name) for name in ONLINE_FLIGHT_SOURCE_FILES):
            raise ValueError("Reproduced online estimator/message/KF differs from the flight revision")
        sequences = [row["record_sequence"] for row in trial["output_events"]]
        counts = {"output_cycles":len(sequences), "measurements":len(trial["measurements"]),
                  "task_events":len(trial["task_events"])}
        if not sequences or evidence.get("counts") != counts or len(trial["task_events"]) != len(sequences):
            raise ValueError("Export receipt does not cover all output/task/measurement opportunities")
        if evidence.get("output_sequence_sha256") != canonical_sha256(sequences):
            raise ValueError("Export receipt cycle order differs")
        if evidence.get("truth_contract") != {"frame":"map", "rotation_policy":"declared_enu",
                "ego_calibration_duration_s":5., "velocity_derivative_half_window_s":.05}:
            raise ValueError("Export receipt lacks the frozen independent truth contract")
    except (KeyError, ValueError, TypeError) as error:
        return [str(error)]
    return []


def replay_trial(trial: dict, config: dict, *, export_evidence: dict | None = None) -> dict:
    parameters = validate_registered_config(config)
    validate_trial_binding(trial, config, parameters)
    if (trial["truth_frame"] != "map" or trial["truth_alignment_basis"] != "declared_enu_vehicle_only_frozen"):
        raise ValueError("Truth must use the separately frozen vehicle-only ENU alignment")
    _hash(trial["truth_alignment_evidence_sha256"], "independent truth alignment")
    replay = replay_states(trial["measurements"], trial["task_events"], trial["output_events"],
                           trial["interval"], parameters, trial["target_class"])
    metrics = score_states(replay, trial["truth_samples"])
    sufficient = (metrics["common_position_samples"] > 0
                  and metrics["common_position_truth_coverage"] >= parameters["minimum_common_coverage"])
    issues = export_evidence_issues(trial, config, export_evidence)
    return {"schema_version":1,"evaluation_status":VERIFIED_REPLAY_STATUS if not issues else "COMPUTED_PENDING_ONLINE_EQUIVALENCE",
        "slot_id":trial["slot_id"],"target_class":trial["target_class"],"seed":trial["seed"],
        "engineering_status":trial["engineering_status"],"configuration_sha256":configuration_digest(config),
        "trial_input_sha256":canonical_sha256(trial),"metrics":metrics,"common_support_requirement_met":sufficient,
        "input_replay_payload_sha256":replay_payload_sha256(trial),
        "input_event_counts":{"output_cycles":len(trial["output_events"]),"measurements":len(trial["measurements"]),"task_events":len(trial["task_events"])},
        "input_output_sequence_sha256":canonical_sha256([row["record_sequence"] for row in trial["output_events"]]),
        "replay":replay,"pending":["Independent recording-to-array export audit", "Frozen-online-navigation equivalence audit"] if issues else [],
        "export_evidence":deepcopy(export_evidence) if not issues else None, "export_evidence_issues":issues,
        "claim_boundary":"Conditional same-measurement state estimation only; no closed-loop counterfactual or flight PASS"}


def paired_trial_summary(reports: list[dict], config: dict) -> dict:
    validate_registered_config(config)
    by_slot = {}
    for report in reports:
        slot = report["slot_id"]
        if slot not in scheduled_slots() or slot in by_slot:
            raise ValueError("Unknown or duplicate trial-level replay report")
        if report["configuration_sha256"] != configuration_digest(config):
            raise ValueError("Replay results come from different parameter registrations")
        if slot != f"{report['target_class']}_stage1_velocity_seed{report['seed']}":
            raise ValueError("Trial report class/seed binding contradicts its slot")
        if type(report["common_support_requirement_met"]) is not bool:
            raise ValueError("Trial support eligibility must be an explicit boolean")
        # Revalidate receipts retained in trial reports. Status strings alone
        # never certify a file audit or complete a formal ten-pair matrix.
        evidence = report.get("export_evidence")
        verified = (isinstance(evidence, dict) and evidence.get("kind") == EXPORT_EVIDENCE_KIND
            and evidence.get("evidence_sha256") == canonical_sha256({k:v for k,v in evidence.items() if k != "evidence_sha256"})
            and evidence.get("trial_input_sha256") == report["trial_input_sha256"]
            and evidence.get("replay_payload_sha256") == report.get("input_replay_payload_sha256")
            and evidence.get("configuration_sha256") == configuration_digest(config)
            and evidence.get("export_source_hashes") == {name:config["freeze_requirements"]["evaluation_source_hashes"].get(name) for name in EXPORT_SOURCE_FILES}
            and all(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value) for value in evidence["export_source_hashes"].values())
            and all(evidence["export_source_hashes"].get(name) == config["freeze_requirements"]["flight_source_hashes"].get(name) for name in ONLINE_FLIGHT_SOURCE_FILES)
            and isinstance(evidence.get("sidecar_sha256"), dict) and set(evidence["sidecar_sha256"]) == set(EXPORT_SIDECARS)
            and all(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value) for value in evidence["sidecar_sha256"].values())
            and evidence.get("counts") == report.get("input_event_counts")
            and evidence.get("output_sequence_sha256") == report.get("input_output_sequence_sha256")
            and evidence.get("truth_contract") == {"frame":"map","rotation_policy":"declared_enu","ego_calibration_duration_s":5.,"velocity_derivative_half_window_s":.05}
            and report.get("evaluation_status") == VERIFIED_REPLAY_STATUS and report.get("pending") == [])
        report = {**report, "_export_verified":verified}
        for method in METHODS:
            value = report["metrics"]["methods"][method]["position_rmse_m"]
            if value is not None:_number(value,"trial position RMSE",minimum=0.)
        by_slot[slot] = report
    ci = config["statistics"]["confidence_interval"]
    classes = {}
    for cls in CLASSES:
        slots = [f"{cls}_stage1_velocity_seed{seed}" for seed in SEEDS]
        rows = [by_slot.get(slot) for slot in slots]
        contrasts = {}
        # One resampling matrix per class retains the complete method block.
        eligible = [i for i,row in enumerate(rows) if row and row["common_support_requirement_met"] is True
                    and all(row["metrics"]["methods"][method]["position_rmse_m"] is not None for method in METHODS)]
        verified_eligible = [i for i in eligible if rows[i]["_export_verified"]]
        rng = np.random.default_rng(ci["rng_seed"])
        indices = rng.integers(0,len(eligible),(ci["resamples"],len(eligible))) if eligible else None
        for baseline in ("fixed_kf","raw","ema"):
            differences = np.array([rows[i]["metrics"]["methods"]["geometry_adaptive_kf"]["position_rmse_m"]
                                  - rows[i]["metrics"]["methods"][baseline]["position_rmse_m"] for i in eligible],dtype=float)
            if len(differences) and not np.isfinite(differences).all():raise ValueError("Nonfinite per-trial summary metric")
            informative = len(differences) >= 2 and np.ptp(differences) > 1e-12
            interval = np.percentile(differences[indices].mean(axis=1),[2.5,97.5]).tolist() if informative else None
            contrasts["geometry_adaptive_kf_minus_"+baseline] = {"scheduled_pairs":10,"finite_pairs":len(eligible),
                "verified_pairs":len(verified_eligible), "verified_slots":[slots[i] for i in verified_eligible],
                "included_slots":[slots[i] for i in eligible],"missing_or_insufficient_slots":[slots[i] for i in range(10) if i not in eligible],
                "paired_differences":differences.tolist(),"mean_difference":float(differences.mean()) if len(differences) else None,
                "median_difference":float(np.median(differences)) if len(differences) else None,
                "ci95":interval,"ci_status":("COMPUTED_CONDITIONAL" if len(verified_eligible) == len(eligible) else "COMPUTED_CONDITIONAL_PENDING_EXPORT_AUDIT") if informative else "INSUFFICIENT_OR_DEGENERATE_TRIAL_VARIATION",
                "complete_numeric_ten_pair_matrix":len(eligible)==10,
                "complete_ten_pair_matrix":len(verified_eligible)==10}
        classes[cls] = {"scheduled_trials":10,"available_trial_reports":sum(row is not None for row in rows),
            "verified_trial_reports":sum(row is not None and row["_export_verified"] for row in rows),
            "pending_audit_slots":[slot for slot,row in zip(slots,rows) if row is not None and not row["_export_verified"]],
            "missing_slots":[slot for slot,row in zip(slots,rows) if row is None],
            "engineering_status_counts":dict(Counter(row["engineering_status"] if row else "MISSING_REPLAY_REPORT" for row in rows)),
            "contrasts":contrasts}
    verified_count = sum(row["_export_verified"] for row in by_slot.values())
    complete = len(reports) == 20 and verified_count == 20 and all(
        contrast["complete_ten_pair_matrix"] for group in classes.values() for contrast in group["contrasts"].values())
    return {"schema_version":1,"evaluation_status":VERIFIED_REPLAY_STATUS if complete else "PENDING_EXPORT_AND_ONLINE_EQUIVALENCE",
        "scheduled_trials":20,"available_trial_reports":len(reports),"classes":classes,
        "verified_trial_reports":verified_count, "complete_verified_matrix":complete,
        "bootstrap":{**ci,"unit":"trial/seed block; never frames"},
        "claim_boundary":"Conditional same-measurement paired effects; failures and missing slots retain the full 20-slot denominator"}
